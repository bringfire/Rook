from __future__ import annotations

import dataclasses
import functools
import json
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import lm9_semantic_typed_values as TYPED_VALUES
import lm9_typed_fact_carrier_artifacts as CARRIER
import lm9_typed_fact_carrier_qualification as QUALIFICATION
import lm9b_p_evaluator_only_continuation as CONTINUATION
import lm9b_p_planner_recipe_transfer_artifacts as PLANNER_ARTIFACTS


RADIAL_KEYS = {
    "box_footprint_x",
    "box_footprint_y",
    "grid_spacing",
    "maximum_height",
    "minimum_height",
}
ANNOTATION_KEYS = {
    "annotation_count",
    "annotation_text",
    "leaders_enabled",
    "text_height",
}


@functools.lru_cache(maxsize=1)
def _transition() -> dict[str, object]:
    return QUALIFICATION._derive_transition(ROOT)


def _validate(raw: bytes) -> CARRIER.VerifiedForwardTaskEnvelope:
    transition = _transition()
    return CARRIER.validate_forward_task_envelope(
        raw,
        payload_schema_raw_bytes=transition["payload_schema_raw"],
        registry_raw_bytes=transition["registry_raw"],
        unit_context_index=transition["unit_context_index"],
        runtime=transition["runtime"],
    )


def _reclose(envelope: dict[str, object]) -> bytes:
    envelope["artifact_fingerprint"] = TYPED_VALUES.fingerprint_without(
        envelope, "artifact_fingerprint"
    )
    return TYPED_VALUES.canonical_json_bytes(envelope) + b"\n"


def _fixture(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    assert type(value) is dict
    return value


def _binding(envelope: dict[str, object], key: str) -> dict[str, object]:
    return next(
        row for row in envelope["value_bindings"] if row["semantic_key"] == key
    )


def _reclose_fact(envelope: dict[str, object], key: str) -> bytes:
    row = _binding(envelope, key)
    fact = envelope["payload"]["facts"][key]
    row["value_schema"] = fact["schema"]
    row["typed_value_fingerprint"] = TYPED_VALUES.fingerprint(fact)
    return _reclose(envelope)


def _one_fact_envelope_bytes(key: str) -> bytes:
    payload_schema = json.loads(CARRIER.PAYLOAD_SCHEMA_PATH.read_bytes())
    return CARRIER.issue_fixture_task_envelope(
        task_session_id="lm9b-c-r01-task-session",
        facts={
            key: {
                "schema": "rook.semantic_string:v1",
                "value": "value",
                "unit": None,
                "unit_context_ref": None,
            }
        },
        authority_by_key={
            key: {
                "authority_kind": "user_fact",
                "provenance": {
                    "issuer_kind": "deterministic_fixture",
                    "issuer_id": "generic-carrier-test",
                },
            }
        },
        payload_schema=payload_schema,
    )


def test_maximum_fact_key_produces_valid_binding_id() -> None:
    verified = _validate(_one_fact_envelope_bytes("a" * 245))
    binding = next(iter(verified.bindings.values()))
    assert len(binding["binding_id"]) == 256


@pytest.mark.parametrize("key", ["", "A", "bad/key", "a" * 246])
def test_forward_envelope_refuses_invalid_semantic_key(key: str) -> None:
    with pytest.raises(ValueError):
        _validate(_one_fact_envelope_bytes(key))


def test_duplicate_fact_property_fails_during_strict_parsing() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        _validate(b'{"payload":{"facts":{"x":1,"x":2}}}')


def test_raw_envelope_and_registry_limits_precede_strict_parsing() -> None:
    transition = _transition()
    with pytest.raises(ValueError, match="task-envelope byte limit"):
        _validate(b"!" * (TYPED_VALUES.MAX_ENVELOPE_BYTES + 1))
    with pytest.raises(ValueError, match="registry byte limit"):
        CARRIER.validate_forward_task_envelope(
            CARRIER.ANNOTATION_FIXTURE_PATH.read_bytes(),
            payload_schema_raw_bytes=transition["payload_schema_raw"],
            registry_raw_bytes=b"!" * (TYPED_VALUES.MAX_REGISTRY_BYTES + 1),
            unit_context_index=transition["unit_context_index"],
            runtime=transition["runtime"],
        )


@pytest.mark.parametrize(
    "issued_at",
    (
        {"unchecked": True},
        "2026-07-23T12:00:00+00:00",
        "2026-7-23T12:00:00Z",
        "2026-02-30T12:00:00Z",
        "2026-07-23T12:00:00.000Z",
    ),
)
def test_forward_envelope_refuses_noncanonical_issued_at(issued_at: object) -> None:
    envelope = _fixture(CARRIER.ANNOTATION_FIXTURE_PATH)
    envelope["issued_at"] = issued_at

    with pytest.raises(ValueError, match="issued_at"):
        _validate(_reclose(envelope))


def test_issued_at_is_format_only_and_grants_no_freshness_authority() -> None:
    envelope = _fixture(CARRIER.ANNOTATION_FIXTURE_PATH)
    envelope["issued_at"] = "2099-12-31T23:59:59Z"

    verified = _validate(_reclose(envelope))

    assert verified.envelope["issued_at"] == "2099-12-31T23:59:59Z"


@pytest.mark.parametrize(
    "case",
    (
        "missing_binding",
        "extra_binding",
        "duplicate_identity",
        "unsorted",
        "binding_id",
        "pointer",
        "value_schema",
        "typed_fingerprint",
        "authority_kind",
        "issuer_kind",
        "empty_issuer",
        "extra_binding_field",
        "extra_envelope_field",
        "payload_schema_fingerprint",
        "artifact_fingerprint",
    ),
)
def test_forward_envelope_refuses_reclosed_binding_and_identity_mutations(
    case: str,
) -> None:
    envelope = _fixture(CARRIER.ANNOTATION_FIXTURE_PATH)
    rows = envelope["value_bindings"]
    if case == "missing_binding":
        rows.pop()
    elif case == "extra_binding":
        rows.append(dict(rows[-1]))
    elif case == "duplicate_identity":
        rows[1]["binding_id"] = rows[0]["binding_id"]
    elif case == "unsorted":
        rows.reverse()
    elif case == "binding_id":
        rows[0]["binding_id"] = "task-value.other"
    elif case == "pointer":
        rows[0]["json_pointer"] = "/facts/other"
    elif case == "value_schema":
        rows[0]["value_schema"] = "rook.semantic_string:v1"
    elif case == "typed_fingerprint":
        rows[0]["typed_value_fingerprint"] = "sha256:" + "0" * 64
    elif case == "authority_kind":
        rows[0]["authority_kind"] = "planner_assumption"
    elif case == "issuer_kind":
        rows[0]["provenance"]["issuer_kind"] = "unknown"
    elif case == "empty_issuer":
        rows[0]["provenance"]["issuer_id"] = ""
    elif case == "extra_binding_field":
        rows[0]["extra"] = True
    elif case == "extra_envelope_field":
        envelope["extra"] = True
    elif case == "payload_schema_fingerprint":
        envelope["payload_schema_fingerprint"] = "sha256:" + "0" * 64
    elif case == "artifact_fingerprint":
        envelope["artifact_fingerprint"] = "sha256:" + "0" * 64
        with pytest.raises(ValueError):
            _validate(TYPED_VALUES.canonical_json_bytes(envelope) + b"\n")
        return
    with pytest.raises(ValueError):
        _validate(_reclose(envelope))


def test_radial_and_annotation_fixtures_use_one_generic_path() -> None:
    radial = _validate(CARRIER.RADIAL_FIXTURE_PATH.read_bytes())
    annotation = _validate(CARRIER.ANNOTATION_FIXTURE_PATH.read_bytes())
    assert len(radial.facts) == 12
    assert set(radial.facts) - set(_parent_values()) == RADIAL_KEYS
    assert {key: radial.facts[key].value["value"] for key in RADIAL_KEYS} == {
        "box_footprint_x": "1",
        "box_footprint_y": "1",
        "grid_spacing": "2",
        "maximum_height": "10",
        "minimum_height": "1",
    }
    assert all(
        radial.facts[key].value["unit"] == "model_unit"
        and radial.facts[key].value["unit_context_ref"]
        == {
            "kind": "artifact_value",
            "artifact_id": "environment_snapshot",
            "json_pointer": "/document/unit_context",
        }
        for key in RADIAL_KEYS
    )
    assert {radial.bindings[key]["authority_kind"] for key in RADIAL_KEYS} == {
        "user_fact"
    }
    assert set(annotation.facts) == ANNOTATION_KEYS
    assert {
        key: fact.value["value"] for key, fact in annotation.facts.items()
    } == {
        "annotation_count": 3,
        "annotation_text": "revision_note",
        "leaders_enabled": True,
        "text_height": "2.5",
    }
    assert {fact.schema.schema_id for fact in annotation.facts.values()} == {
        "rook.semantic_string:v1",
        "rook.semantic_integer:v1",
        "rook.semantic_boolean:v1",
        "rook.semantic_scalar:v1",
    }
    assert all(
        row["authority_kind"] == "user_fact"
        for row in annotation.bindings.values()
    )


@functools.lru_cache(maxsize=1)
def _parent_values():
    transition = _transition()
    return CARRIER.reconstruct_observed_historical_task_values(
        transition["source"],
        registry=transition["registry"],
        unit_context_index=transition["unit_context_index"],
    )


def _partition_inputs(successor: CARRIER.VerifiedForwardTaskEnvelope):
    transition = _transition()
    source = transition["source"]
    parent_recipe = json.loads(source.final_recipe_bytes)
    parent_bindings = CARRIER.historical_task_bindings(source)
    partition = CARRIER.derive_authority_partition(
        parent_values=_parent_values(),
        parent_bindings=parent_bindings,
        successor=successor,
        parent_recipe=parent_recipe,
    )
    return parent_bindings, partition


def test_exact_parent_migration_and_authority_partition() -> None:
    successor = _validate(CARRIER.RADIAL_FIXTURE_PATH.read_bytes())
    parent_bindings, partition = _partition_inputs(successor)
    ledger = CARRIER.verify_exact_migration(
        parent_values=_parent_values(),
        parent_bindings=parent_bindings,
        successor=successor,
        partition=partition,
    )
    assert partition.migration_keys == partition.parent_keys
    assert set(partition.authority_delta_keys) == set(partition.required_delta_keys)
    assert len(partition.authority_delta_keys) == 5
    assert len(ledger) == 7
    assert all(value.value["unit"] is None for value in _parent_values().values())
    assert all(
        value.value["unit_context_ref"] is None
        for value in _parent_values().values()
    )


@pytest.mark.parametrize(
    "case",
    (
        "retained_value",
        "retained_type",
        "retained_provenance",
        "retained_authority_kind",
        "removed_parent",
        "extra_delta",
        "omitted_required",
        "non_user_delta",
    ),
)
def test_migration_and_partition_refuse_reclosed_nonisolated_successor(
    case: str,
) -> None:
    envelope = _fixture(CARRIER.RADIAL_FIXTURE_PATH)
    if case == "retained_value":
        envelope["payload"]["facts"]["element_kind"]["value"] = "sphere"
        raw = _reclose_fact(envelope, "element_kind")
    elif case == "retained_type":
        envelope["payload"]["facts"]["grid_count_x"] = {
            "schema": "rook.semantic_string:v1",
            "value": "10",
            "unit": None,
            "unit_context_ref": None,
        }
        raw = _reclose_fact(envelope, "grid_count_x")
    elif case == "retained_provenance":
        _binding(envelope, "element_kind")["provenance"]["issuer_id"] = "other"
        raw = _reclose(envelope)
    elif case == "retained_authority_kind":
        _binding(envelope, "element_kind")["authority_kind"] = "task_fact"
        raw = _reclose(envelope)
    elif case in {"removed_parent", "omitted_required"}:
        key = "element_kind" if case == "removed_parent" else "grid_spacing"
        del envelope["payload"]["facts"][key]
        envelope["value_bindings"] = [
            row for row in envelope["value_bindings"] if row["semantic_key"] != key
        ]
        raw = _reclose(envelope)
    elif case == "extra_delta":
        envelope["payload"]["facts"]["unrequested_fact"] = {
            "schema": "rook.semantic_string:v1",
            "value": "extra",
            "unit": None,
            "unit_context_ref": None,
        }
        envelope["value_bindings"].append(
            {
                "authority_kind": "user_fact",
                "binding_id": "task-value.unrequested_fact",
                "json_pointer": "/facts/unrequested_fact",
                "provenance": {
                    "issuer_id": "generic-carrier-test",
                    "issuer_kind": "deterministic_fixture",
                },
                "semantic_key": "unrequested_fact",
                "typed_value_fingerprint": TYPED_VALUES.fingerprint(
                    envelope["payload"]["facts"]["unrequested_fact"]
                ),
                "value_schema": "rook.semantic_string:v1",
            }
        )
        envelope["value_bindings"].sort(
            key=lambda row: row["semantic_key"].encode("utf-16-be")
        )
        raw = _reclose(envelope)
    else:
        _binding(envelope, "grid_spacing")["authority_kind"] = "task_fact"
        raw = _reclose(envelope)
    successor = _validate(raw)
    if case in {
        "retained_value",
        "retained_type",
        "retained_provenance",
        "retained_authority_kind",
    }:
        parent_bindings, partition = _partition_inputs(successor)
        with pytest.raises(ValueError, match="retained"):
            CARRIER.verify_exact_migration(
                parent_values=_parent_values(),
                parent_bindings=parent_bindings,
                successor=successor,
                partition=partition,
            )
    else:
        with pytest.raises(ValueError):
            _partition_inputs(successor)


def _mutated_historical_source(
    value: object,
    *,
    value_schema: str | None = None,
):
    source = _transition()["source"]
    records = list(source.input_records)
    index = next(
        i for i, row in enumerate(records) if row.role == "authority.task_envelope"
    )
    task = json.loads(records[index].raw_bytes)
    task["payload"]["facts"]["element_kind"] = value
    binding = next(
        row
        for row in task["value_bindings"]
        if row["semantic_key"] == "element_kind"
    )
    if type(value) is str:
        binding["value_schema"] = value_schema or "rook.semantic_string:v1"
        binding["typed_value_fingerprint"] = TYPED_VALUES.fingerprint(
            {"schema": binding["value_schema"], "value": value}
        )
    task["artifact_fingerprint"] = TYPED_VALUES.fingerprint_without(
        task, "artifact_fingerprint"
    )
    raw = TYPED_VALUES.canonical_json_bytes(task) + b"\n"
    records[index] = PLANNER_ARTIFACTS.planner_input_record_from_bytes(
        role="authority.task_envelope",
        relative_path=records[index].relative_path,
        raw_bytes=raw,
    )
    return dataclasses.replace(source, input_records=tuple(records))


@pytest.mark.parametrize(
    ("value", "value_schema"),
    [
        ("sphere", None),
        (True, None),
        (None, None),
        ({}, None),
        ([], None),
        ("2", "rook.semantic_scalar:v1"),
    ],
)
def test_historical_adapter_accepts_only_exact_production_source(
    value: object,
    value_schema: str | None,
) -> None:
    transition = _transition()
    with pytest.raises(ValueError, match="historical source"):
        CARRIER.reconstruct_observed_historical_task_values(
            _mutated_historical_source(value, value_schema=value_schema),
            registry=transition["registry"],
            unit_context_index=transition["unit_context_index"],
        )


def test_neutral_sources_contain_no_fixture_semantic_keys() -> None:
    paths = [
        SCRIPTS / "lm9_semantic_typed_values.py",
        SCRIPTS / "lm9_typed_fact_carrier_artifacts.py",
        *sorted(CARRIER.CONTRACTS_DIR.glob("*.json")),
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert not ((RADIAL_KEYS | ANNOTATION_KEYS) & set(source.split()))
    for key in RADIAL_KEYS | ANNOTATION_KEYS:
        assert key not in source


def test_required_negative_manifest_is_executable_and_closed() -> None:
    transition = _transition()
    source = transition["source"]
    records = {row.role: row for row in source.input_records}
    results = CARRIER.run_required_negative_cases(
        runtime=transition["runtime"],
        registry_raw_bytes=transition["registry_raw"],
        payload_schema_raw_bytes=transition["payload_schema_raw"],
        unit_context_index=transition["unit_context_index"],
        parent_task_envelope=records["authority.task_envelope"].value,
        parent_recipe=json.loads(source.final_recipe_bytes),
        radial_envelope_bytes=CARRIER.RADIAL_FIXTURE_PATH.read_bytes(),
        annotation_envelope_bytes=CARRIER.ANNOTATION_FIXTURE_PATH.read_bytes(),
    )
    assert tuple(row.case_id for row in results) == CARRIER.required_negative_case_ids()
    assert all(row.status == "deterministically_refused" for row in results)
    assert len({row.evidence_fingerprint for row in results}) == len(results)


def _boom(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("provider, Planner, evaluator, or compiler path was reached")


def test_exact_production_parent_remains_faithful_and_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    verify_source = CARRIER.CONT_ARTIFACTS.verify_historical_source
    parse_strict = CARRIER.TYPED_VALUES.parse_strict_json
    validate_occurrences = CARRIER._validate_parent_recipe_occurrences
    evaluate_gate = CARRIER.SUPPORT.evaluate_mechanical_gate
    verify_derivative = CARRIER.CONT_ARTIFACTS.verify_sealed_derivative_archive
    classify = CARRIER.PLANNER_ARTIFACTS.derive_evaluated_recipe_classification

    def recording_source(*args: object, **kwargs: object):
        order.append("source")
        return verify_source(*args, **kwargs)

    def recording_parse(*args: object, **kwargs: object):
        if kwargs.get("label") == "parent recipe":
            order.append("parent_recipe")
        return parse_strict(*args, **kwargs)

    def recording_occurrences(*args: object, **kwargs: object):
        order.append("typed_occurrences")
        return validate_occurrences(*args, **kwargs)

    def recording_gate(*args: object, **kwargs: object):
        order.append("mechanical_gate")
        return evaluate_gate(*args, **kwargs)

    def recording_derivative(*args: object, **kwargs: object):
        order.append("derivative")
        return verify_derivative(*args, **kwargs)

    def recording_classification(*args: object, **kwargs: object):
        order.append("classification")
        return classify(*args, **kwargs)

    monkeypatch.setattr(
        CARRIER.CONT_ARTIFACTS, "verify_historical_source", recording_source
    )
    monkeypatch.setattr(CARRIER.TYPED_VALUES, "parse_strict_json", recording_parse)
    monkeypatch.setattr(
        CARRIER, "_validate_parent_recipe_occurrences", recording_occurrences
    )
    monkeypatch.setattr(
        CARRIER.SUPPORT, "evaluate_mechanical_gate", recording_gate
    )
    monkeypatch.setattr(
        CARRIER.CONT_ARTIFACTS,
        "verify_sealed_derivative_archive",
        recording_derivative,
    )
    monkeypatch.setattr(
        CARRIER.PLANNER_ARTIFACTS,
        "derive_evaluated_recipe_classification",
        recording_classification,
    )
    monkeypatch.setattr(CARRIER.SUPPORT, "run_planner_session", _boom)
    monkeypatch.setattr(CARRIER.SUPPORT, "run_planner_evaluation", _boom)
    monkeypatch.setattr(CARRIER.PLANNER_ARTIFACTS, "build_lm9bc_handoff", _boom)
    monkeypatch.setattr(CONTINUATION, "_build_evaluator_provider", _boom)

    witness = CARRIER.build_outcome_neutral_parent_witness(
        derivative_archive=CARRIER.OFFICIAL_DERIVATIVE,
        runtime=TYPED_VALUES.current_runtime_identity(),
    )

    assert witness.source_manifest_raw_sha256 == (
        "sha256:ac7716b7d5a61e2e6359bc0e01e145d7d17e0871ff03d1d5329710541d274c90"
    )
    assert witness.recipe_raw_sha256 == (
        "sha256:5c5dba9def1ffc3002240f3154f02f36e60134019659d5e6a9d546b0317965af"
    )
    assert witness.recipe_fingerprint == (
        "sha256:eb70994fa9ead99fbe75f6f25e81327045258389d46e91474cc5b581befc068a"
    )
    assert witness.typed_value_validation_fingerprint == (
        "sha256:a4538805f16778589c5c734d90243dc3f34da0bd9bf4674ac55b9087f1715190"
    )
    assert witness.mechanical_gate_status == "mechanically_accepted"
    assert type(witness.unresolved_keys) is tuple
    assert witness.unresolved_keys == tuple(
        sorted(RADIAL_KEYS, key=lambda item: item.encode("utf-16-be"))
    )
    assert witness.derivative_archive_identity == CARRIER.OFFICIAL_DERIVATIVE_IDENTITY
    assert witness.evaluator_recommendation == "semantically_faithful"
    assert witness.classification == "probe_candidate_blocked"
    assert witness.witness_fingerprint == (
        "sha256:07a57f8566cdb4d331fe15a840bd3b73496187c638e6647d89f0a70a86fc58c8"
    )
    assert order[:5] == [
        "source",
        "parent_recipe",
        "typed_occurrences",
        "mechanical_gate",
        "derivative",
    ]
    assert order[-1] == "classification"


def test_accepted_controls_preserve_occurrence_shapes_and_real_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transition = _transition()
    calls: list[str] = []
    validate = CARRIER.TYPED_VALUES.validate_typed_value

    def recording_validate(*args: object, **kwargs: object):
        calls.append(kwargs["required_presence"])
        return validate(*args, **kwargs)

    monkeypatch.setattr(CARRIER.TYPED_VALUES, "validate_typed_value", recording_validate)
    frozen = CARRIER.frozen_gate_inputs(transition["source"])
    controls = (
        (
            ROOT / "scripts/lm9b_c_fixtures/r01_recipe.json",
            "lm9b_c_frozen_input",
            None,
        ),
        (
            ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json",
            "planner_mechanical_gate",
            frozen,
        ),
    )

    witnesses = tuple(
        CARRIER.build_control_compatibility_witness(
            path,
            acceptance_boundary=acceptance_boundary,
            frozen_inputs=control_inputs,
            registry=transition["registry"],
            unit_context_index=transition["unit_context_index"],
        )
        for path, acceptance_boundary, control_inputs in controls
    )

    assert [row.recipe_raw_sha256 for row in witnesses] == [
        "sha256:c2a504e7a089c37fc174d53eeb7cd409690a63e7709cfea8ea7ce7a3c13ddad2",
        "sha256:d5fb1589b9d3b463fa16caf8c9c831f5b68fc73062ab831b091520aae9abe724",
    ]
    assert all(row.assumption_count == 9 for row in witnesses)
    assert all(row.derived_fact_count == 1 for row in witnesses)
    assert [row.acceptance_boundary for row in witnesses] == [
        "lm9b_c_frozen_input",
        "planner_mechanical_gate",
    ]
    assert [row.acceptance_status for row in witnesses] == [
        "frozen_inputs_accepted",
        "mechanically_accepted",
    ]
    assert {
        row.typed_value_validation_fingerprint for row in witnesses
    } == {
        "sha256:5c027bd018b5cd5a48e5b02daab649e4a509a04bcc0690b18f5c52f1c2f68677"
    }
    assert calls == ["recipe_assumption"] * 9 + ["recipe_derived"] + (
        ["recipe_assumption"] * 9 + ["recipe_derived"]
    )


def test_copied_mutated_historical_source_fails_production_pins(tmp_path: Path) -> None:
    source = CARRIER.CONT_ARTIFACTS.verify_historical_source()
    copied = tmp_path / "historical-source"
    shutil.copytree(source.source_root, copied)
    recipe_path = copied / "checkpoint-1/planner/final_recipe.json"
    recipe = json.loads(recipe_path.read_bytes())
    recipe["goal"]["statement"] = "mutated copied evidence"
    recipe["recipe_fingerprint"] = TYPED_VALUES.fingerprint_without(
        recipe, "recipe_fingerprint"
    )
    recipe_path.write_bytes(TYPED_VALUES.canonical_json_bytes(recipe) + b"\n")
    copied_pins = dataclasses.replace(
        CARRIER.CONT_ARTIFACTS.PRODUCTION_SOURCE_PINS,
        source_root=copied,
    )

    with pytest.raises(ValueError):
        CARRIER.CONT_ARTIFACTS._verify_historical_source(copied_pins)


def test_copied_derivative_cannot_substitute_for_canonical_archive(
    tmp_path: Path,
) -> None:
    copied = tmp_path / "copied-derivative"
    shutil.copytree(CARRIER.OFFICIAL_DERIVATIVE, copied)

    with pytest.raises(ValueError, match="destination|archive"):
        CARRIER.CONT_ARTIFACTS.verify_sealed_derivative_archive(
            copied,
            expected_derivative_identity=CARRIER.OFFICIAL_DERIVATIVE_IDENTITY,
        )


def test_parent_witness_refuses_shared_classification_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        CARRIER.PLANNER_ARTIFACTS,
        "derive_evaluated_recipe_classification",
        lambda *_args, **_kwargs: "probe_candidate_ready",
    )

    with pytest.raises(ValueError, match="classification"):
        CARRIER.build_outcome_neutral_parent_witness(
            derivative_archive=CARRIER.OFFICIAL_DERIVATIVE,
            runtime=TYPED_VALUES.current_runtime_identity(),
        )


def test_parent_witness_refuses_semantic_recommendation_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sealed = CARRIER.CONT_ARTIFACTS.verify_sealed_derivative_archive(
        CARRIER.OFFICIAL_DERIVATIVE,
        expected_derivative_identity=CARRIER.OFFICIAL_DERIVATIVE_IDENTITY,
    )
    altered_result = dataclasses.replace(
        sealed.evaluator_result,
        recommendation="semantically_unfaithful",
    )
    monkeypatch.setattr(
        CARRIER.CONT_ARTIFACTS,
        "verify_sealed_derivative_archive",
        lambda *_args, **_kwargs: dataclasses.replace(
            sealed,
            evaluator_result=altered_result,
        ),
    )

    with pytest.raises(ValueError, match="recommendation"):
        CARRIER.build_outcome_neutral_parent_witness(
            derivative_archive=CARRIER.OFFICIAL_DERIVATIVE,
            runtime=TYPED_VALUES.current_runtime_identity(),
        )


def test_r01_control_refuses_counterfeit_planner_acceptance() -> None:
    transition = _transition()

    with pytest.raises(ValueError, match="control recipe outcome"):
        CARRIER.build_control_compatibility_witness(
            ROOT / "scripts/lm9b_c_fixtures/r01_recipe.json",
            acceptance_boundary="planner_mechanical_gate",
            frozen_inputs=CARRIER.frozen_gate_inputs(transition["source"]),
            registry=transition["registry"],
            unit_context_index=transition["unit_context_index"],
        )


def test_r01_control_refuses_recipe_drift_at_manifest_boundary(
    tmp_path: Path,
) -> None:
    transition = _transition()
    copied = tmp_path / "lm9b-c-control"
    shutil.copytree(ROOT / "scripts/lm9b_c_fixtures", copied)
    recipe_path = copied / "r01_recipe.json"
    recipe = json.loads(recipe_path.read_bytes())
    integer = recipe["derived_facts"][0]
    integer["typed_value"]["value"] += 1
    recipe["recipe_fingerprint"] = TYPED_VALUES.fingerprint_without(
        recipe, "recipe_fingerprint"
    )
    recipe_path.write_bytes(TYPED_VALUES.canonical_json_bytes(recipe) + b"\n")

    with pytest.raises(ValueError, match="raw hash mismatch"):
        CARRIER.build_control_compatibility_witness(
            recipe_path,
            acceptance_boundary="lm9b_c_frozen_input",
            frozen_inputs=None,
            registry=transition["registry"],
            unit_context_index=transition["unit_context_index"],
        )


def test_control_witness_refuses_reclosed_invalid_typed_value(tmp_path: Path) -> None:
    transition = _transition()
    source_path = ROOT / "scripts/lm9b_c_fixtures/r01_recipe.json"
    recipe = json.loads(source_path.read_bytes())
    scalar = next(
        row
        for row in recipe["assumptions"]
        if row["typed_value"]["schema"] == "rook.semantic_scalar:v1"
    )
    scalar["typed_value"]["value"] = "2.0"
    recipe["recipe_fingerprint"] = TYPED_VALUES.fingerprint_without(
        recipe, "recipe_fingerprint"
    )
    copied = tmp_path / "reclosed-invalid-control.json"
    copied.write_bytes(TYPED_VALUES.canonical_json_bytes(recipe) + b"\n")

    with pytest.raises(ValueError, match="typed value failed"):
        CARRIER.build_control_compatibility_witness(
            copied,
            acceptance_boundary="lm9b_c_frozen_input",
            frozen_inputs=None,
            registry=transition["registry"],
            unit_context_index=transition["unit_context_index"],
        )
