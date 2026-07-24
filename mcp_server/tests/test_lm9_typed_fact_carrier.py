from __future__ import annotations

import dataclasses
import functools
import json
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
        "retained_provenance",
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
    elif case == "retained_provenance":
        _binding(envelope, "element_kind")["provenance"]["issuer_id"] = "other"
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
    if case in {"retained_value", "retained_provenance"}:
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
