from __future__ import annotations

import copy
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
MCP_SRC = ROOT / "mcp_server" / "src"
for entry in (SCRIPTS, MCP_SRC):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import lm9_semantic_typed_values as TYPED_VALUES
import lm9b_p_governed_resolution_artifacts as ARTIFACTS
import lm9b_p_governed_resolution_support as SUPPORT
import lm9b_p_planner_recipe_transfer_support as PLANNER_SUPPORT
import lm9_typed_fact_carrier_artifacts as CARRIER


HISTORICAL_SOURCE = Path(
    r"C:\Users\bring\rook-lm9b-p-attempts\2026-07-22-visibility-intervention"
)
DERIVATIVE_ARCHIVE = Path(
    r"C:\Users\bring\rook-lm9b-p-attempts"
    r"\2026-07-22-evaluator-only-continuation"
    r"\derivatives\visibility-evaluator-01"
)
CARRIER_QUALIFICATION = Path(
    r"C:\Users\bring\rook-lm9b-p-attempts"
    r"\2026-07-23-typed-fact-carrier-post-merge"
    r"\d6330a61a21d56abf16af6ba3b8f1678ede2c3ec"
)
ISOLATED_SUCCESSOR_RECIPE = (
    SCRIPTS
    / "lm9b_p_governed_resolution_fixtures"
    / "radial_isolated_successor_recipe.json"
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _binding(envelope: dict[str, object], key: str) -> dict[str, object]:
    rows = envelope["value_bindings"]
    assert isinstance(rows, list)
    return next(row for row in rows if row["semantic_key"] == key)


def _reclose(envelope: dict[str, object]) -> bytes:
    envelope["artifact_fingerprint"] = TYPED_VALUES.fingerprint_without(
        envelope, "artifact_fingerprint"
    )
    return _canonical_bytes(envelope)


def _reclose_fact(envelope: dict[str, object], key: str) -> bytes:
    facts = envelope["payload"]["facts"]
    fact = facts[key]
    row = _binding(envelope, key)
    row["value_schema"] = fact["schema"]
    row["typed_value_fingerprint"] = TYPED_VALUES.fingerprint(fact)
    return _reclose(envelope)


def _load_with_successor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, raw: bytes
) -> object:
    successor = tmp_path / "successor.json"
    successor.write_bytes(raw)
    monkeypatch.setattr(ARTIFACTS, "SUCCESSOR_ENVELOPE_PATH", successor)
    return ARTIFACTS.load_verified_resolution_sources(
        historical_source_dir=HISTORICAL_SOURCE,
        derivative_archive=DERIVATIVE_ARCHIVE,
        derivative_identity=ARTIFACTS.OFFICIAL_DERIVATIVE_IDENTITY,
        carrier_qualification_archive=CARRIER_QUALIFICATION,
        carrier_qualification_identity=(
            ARTIFACTS.HISTORICAL_CARRIER_QUALIFICATION_IDENTITY
        ),
        repo_root=ROOT,
        successor_envelope_path=successor,
    )


def _resolution_inputs():
    sources = ARTIFACTS.load_verified_resolution_sources(
        historical_source_dir=HISTORICAL_SOURCE,
        derivative_archive=DERIVATIVE_ARCHIVE,
        derivative_identity=ARTIFACTS.OFFICIAL_DERIVATIVE_IDENTITY,
        carrier_qualification_archive=CARRIER_QUALIFICATION,
        carrier_qualification_identity=(
            ARTIFACTS.HISTORICAL_CARRIER_QUALIFICATION_IDENTITY
        ),
        repo_root=ROOT,
        successor_envelope_path=ARTIFACTS.SUCCESSOR_ENVELOPE_PATH,
    )
    return ARTIFACTS.assemble_resolution_instrument(
        sources=sources,
        isolation_policy_path=ARTIFACTS.ISOLATION_POLICY_PATH,
        evaluation_rubric_path=ARTIFACTS.EVALUATION_RUBRIC_PATH,
    ).inputs


def _reclose_recipe(value: dict[str, object], inputs: object) -> bytes:
    projection = {
        key: item for key, item in value.items() if key != "recipe_fingerprint"
    }
    normalized = PLANNER_SUPPORT.normalize_recipe(
        copy.deepcopy(projection), inputs.normalization_profile
    )
    value["recipe_fingerprint"] = PLANNER_SUPPORT.fingerprint(normalized)
    return _canonical_bytes(value)


ISOLATION_MUTATIONS = (
    "wrong_source_task_fingerprint",
    "other_source_descriptor_field",
    "retained_unresolved_row",
    "new_unresolved_row",
    "wrong_goal_unresolved_ids",
    "goal_statement",
    "affected_clause_statement",
    "affected_clause_id",
    "affected_clause_category",
    "affected_clause_location",
    "missing_required_reference",
    "extra_reference",
    "duplicate_reference",
    "noncanonical_reference_order",
    "assumption",
    "derived_fact",
    "invariant",
    "capability",
    "shape",
    "worker_slot",
    "postcondition",
    "authority_descriptor",
    "remove_retained_descriptor",
    "retain_derived_removable_descriptor",
    "add_authority_descriptor",
    "reorder_authority_descriptors",
    "mutate_retained_authority_descriptor",
    "unrelated_reference",
    "claimed_fingerprint",
)


def _mutated_isolation_candidate(
    mutation: str, inputs: object
) -> tuple[dict[str, object], bool]:
    candidate = json.loads(ISOLATED_SUCCESSOR_RECIPE.read_bytes())
    parent = PLANNER_SUPPORT._json_builtins(inputs.parent_recipe)
    affected = inputs.policy_instance.value["affected_clauses"][0]
    category = affected["category"]
    pointer = affected["pointer"]
    clause = PLANNER_SUPPORT.resolve_json_pointer(candidate, pointer)
    parent_clause = PLANNER_SUPPORT.resolve_json_pointer(parent, pointer)
    reclose = True
    if mutation == "wrong_source_task_fingerprint":
        candidate["source_task"]["fingerprint"] = "sha256:" + "1" * 64
    elif mutation == "other_source_descriptor_field":
        candidate["source_task"]["artifact_kind"] = "other_task"
    elif mutation == "retained_unresolved_row":
        candidate["unresolved_intent"] = [parent["unresolved_intent"][0]]
    elif mutation == "new_unresolved_row":
        row = copy.deepcopy(parent["unresolved_intent"][0])
        row["intent_id"] = "unresolved.unrelated"
        row["semantic_key"] = "unrelated"
        candidate["unresolved_intent"] = [row]
    elif mutation == "wrong_goal_unresolved_ids":
        candidate["goal"]["projected_into"]["unresolved_intent_ids"] = [
            parent["unresolved_intent"][0]["intent_id"]
        ]
    elif mutation == "goal_statement":
        candidate["goal"]["statement"] += " Changed."
    elif mutation == "affected_clause_statement":
        clause["statement"] += " Changed."
    elif mutation == "affected_clause_id":
        clause["clause_id"] = "maintain.changed"
    elif mutation == "affected_clause_category":
        candidate[category].remove(clause)
        candidate["requires"].append(clause)
    elif mutation == "affected_clause_location":
        candidate[category].insert(
            0,
            {
                **copy.deepcopy(parent_clause),
                "clause_id": "maintain.unrelated.location",
            },
        )
    elif mutation == "missing_required_reference":
        clause["source_refs"].pop()
    elif mutation == "extra_reference":
        clause["source_refs"].append(
            {
                "kind": "artifact_value",
                "artifact_id": "task_envelope",
                "json_pointer": "/facts/unrelated",
            }
        )
    elif mutation == "duplicate_reference":
        clause["source_refs"].append(copy.deepcopy(clause["source_refs"][0]))
        reclose = False
    elif mutation == "noncanonical_reference_order":
        clause["source_refs"].reverse()
        reclose = False
    elif mutation == "assumption":
        candidate["assumptions"] = [{"assumption_id": "assumption.unrelated"}]
    elif mutation == "derived_fact":
        candidate["derived_facts"] = [
            {"derived_fact_id": "derived.unrelated"}
        ]
    elif mutation == "invariant":
        candidate["invariants"][0]["statement"] += " Changed."
    elif mutation == "capability":
        candidate["required_capabilities"]["entries"].append(
            {"capability_id": "capability.unrelated"}
        )
    elif mutation == "shape":
        candidate["shape"]["self"].append(
            {"shape_id": "shape.unrelated", "statement": "Unrelated shape."}
        )
    elif mutation == "worker_slot":
        candidate["worker_slots"]["entries"].append(
            {"worker_slot_id": "worker.unrelated"}
        )
        reclose = False
    elif mutation == "postcondition":
        clause["postconditions"][0]["statement"] += " Changed."
    elif mutation == "authority_descriptor":
        candidate["authority_artifacts"][0]["artifact_kind"] = "other"
    elif mutation == "remove_retained_descriptor":
        candidate["authority_artifacts"] = []
    elif mutation == "retain_derived_removable_descriptor":
        candidate["authority_artifacts"].append(parent["authority_artifacts"][1])
    elif mutation == "add_authority_descriptor":
        candidate["authority_artifacts"].append(
            {
                "artifact_id": "unrelated_authority",
                "artifact_kind": "task_authority",
                "schema": "rook.unrelated:v1",
                "fingerprint": "sha256:" + "2" * 64,
            }
        )
    elif mutation == "reorder_authority_descriptors":
        candidate["authority_artifacts"].append(parent["authority_artifacts"][1])
        candidate["authority_artifacts"].reverse()
        reclose = False
    elif mutation == "mutate_retained_authority_descriptor":
        candidate["authority_artifacts"][0]["fingerprint"] = "sha256:" + "3" * 64
    elif mutation == "unrelated_reference":
        candidate["goal"]["source_refs"].append(
            {
                "kind": "artifact_value",
                "artifact_id": "task_envelope",
                "json_pointer": "/facts/unrelated",
            }
        )
    elif mutation == "claimed_fingerprint":
        candidate["recipe_fingerprint"] = "sha256:" + "4" * 64
        reclose = False
    else:  # pragma: no cover - protects the table itself
        raise AssertionError(mutation)
    return candidate, reclose


@pytest.mark.parametrize("mutation", ISOLATION_MUTATIONS)
def test_task3_isolation_mutation_is_completed_rejection(mutation: str) -> None:
    inputs = _resolution_inputs()
    candidate, reclose = _mutated_isolation_candidate(mutation, inputs)
    raw = _reclose_recipe(candidate, inputs) if reclose else _canonical_bytes(candidate)
    result = SUPPORT.evaluate_resolution_isolation(
        inputs=inputs,
        candidate_recipe_bytes=raw,
    )
    assert result.status == "isolation_rejected"
    assert result.bounded_differences


POLICY_CONTROL_FAILURES = (
    "unresolved_parent_clause_id",
    "multiply_resolved_parent_clause_id",
    "overlapping_equation_ownership",
    "duplicate_erased_location",
    "unconsumed_erased_location",
    "normalization_identity_mismatch",
    "policy_instance_fingerprint",
    "parent_proof_carrier",
)


@pytest.mark.parametrize("mutation", POLICY_CONTROL_FAILURES)
def test_task3_policy_control_failure_refuses_without_verdict(mutation: str) -> None:
    issued = _resolution_inputs()
    inputs = issued
    if mutation == "parent_proof_carrier":
        inputs = replace(issued)
    elif mutation in {
        "unresolved_parent_clause_id",
        "multiply_resolved_parent_clause_id",
    }:
        parent = PLANNER_SUPPORT._json_builtins(issued.parent_recipe)
        if mutation == "unresolved_parent_clause_id":
            parent["unresolved_intent"][0]["affected_clause_ids"] = [
                "maintain.absent"
            ]
        else:
            parent["maintains"].append(copy.deepcopy(parent["maintains"][0]))
        object.__setattr__(issued, "parent_recipe", MappingProxyType(parent))
    elif mutation == "normalization_identity_mismatch":
        object.__setattr__(
            issued,
            "normalization_profile",
            replace(
                issued.normalization_profile,
                profile_fingerprint="sha256:" + "5" * 64,
            ),
        )
    else:
        policy = copy.deepcopy(
            PLANNER_SUPPORT._json_builtins(issued.policy_instance.value)
        )
        if mutation == "overlapping_equation_ownership":
            policy["residual_ownership"].append(
                copy.deepcopy(policy["residual_ownership"][0])
            )
            policy["residual_ownership"][-1]["equation_id"] = (
                "authority_reference_additions"
            )
        elif mutation == "duplicate_erased_location":
            policy["residual_ownership"].append(
                copy.deepcopy(policy["residual_ownership"][0])
            )
        elif mutation == "unconsumed_erased_location":
            policy["residual_ownership"].append(
                {
                    "equation_id": "source_descriptor",
                    "pointer": "/unconsumed",
                }
            )
        policy_instance = replace(
            issued.policy_instance,
            value=MappingProxyType(policy),
            instance_fingerprint=(
                "sha256:" + "6" * 64
                if mutation == "policy_instance_fingerprint"
                else PLANNER_SUPPORT.fingerprint(policy)
            ),
        )
        object.__setattr__(issued, "policy_instance", policy_instance)

    if mutation != "parent_proof_carrier":
        with pytest.raises(ValueError, match="policy|ownership|parent|normalization"):
            SUPPORT._validate_isolation_control(inputs)
    with pytest.raises((TypeError, ValueError), match="proof|policy|ownership|parent|normalization"):
        SUPPORT.evaluate_resolution_isolation(
            inputs=inputs,
            candidate_recipe_bytes=ISOLATED_SUCCESSOR_RECIPE.read_bytes(),
        )


def test_task3_isolation_positive_has_exact_named_equation_order() -> None:
    inputs = _resolution_inputs()
    result = SUPPORT.evaluate_resolution_isolation(
        inputs=inputs,
        candidate_recipe_bytes=ISOLATED_SUCCESSOR_RECIPE.read_bytes(),
    )
    assert result.status == "isolated", [dict(row) for row in result.equations]
    assert [row["equation_id"] for row in result.equations] == [
        "source_descriptor",
        "resolved_unresolved_rows",
        "authority_descriptor_reachability",
        "goal_unresolved_projection",
        "clause_ownership",
        "authority_reference_additions",
        "affected_clause_residual",
        "recipe_fingerprint",
        "global_residual_equality",
    ]
    assert all(
        set(row)
        == {
            "equation_id",
            "status",
            "passed",
            "owned_pointers",
            "input_fingerprints",
        }
        for row in result.equations
    )
    assert len(inputs.correspondence) == 5
    assert {
        row["category"] for row in inputs.policy_instance.value["affected_clauses"]
    } == {"maintains"}
    assert inputs.policy_instance.value["descriptor_removal_eligible_ids"] == (
        "planning_policy",
    )


def test_task3_verified_inputs_capability_exposes_no_raw_issuer() -> None:
    assert not hasattr(SUPPORT, "_register_verified_resolution_inputs")
    assert not hasattr(SUPPORT, "_issue_verified_resolution_inputs")
    assert SUPPORT.assemble_verified_resolution_inputs.__name__ == "derive"


def _rewrite_fixture_value(value: object, replacements: dict[str, str]) -> object:
    if isinstance(value, dict):
        return {
            replacements.get(key, key): _rewrite_fixture_value(item, replacements)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_rewrite_fixture_value(item, replacements) for item in value]
    if isinstance(value, str):
        rewritten = value
        for old, new in replacements.items():
            rewritten = rewritten.replace(old, new)
        return rewritten
    return value


def test_task3_non_radial_policy_mechanics_witness_uses_same_gate() -> None:
    issued = _resolution_inputs()
    replacements = {
        "box_footprint_x": "annotation_text",
        "box_footprint_y": "annotation_count",
        "grid_spacing": "leaders_enabled",
        "minimum_height": "text_height",
        "maximum_height": "leader_length",
        "maintain.radial_box_array_semantics": "maintain.annotation_semantics",
    }
    parent = _rewrite_fixture_value(
        PLANNER_SUPPORT._json_builtins(issued.parent_recipe), replacements
    )
    candidate = _rewrite_fixture_value(
        json.loads(ISOLATED_SUCCESSOR_RECIPE.read_bytes()), replacements
    )
    successor = _rewrite_fixture_value(
        PLANNER_SUPPORT._json_builtins(issued.successor_envelope), replacements
    )
    successor["artifact_fingerprint"] = TYPED_VALUES.fingerprint_without(
        successor, "artifact_fingerprint"
    )
    candidate["source_task"]["fingerprint"] = successor["artifact_fingerprint"]
    parent = json.loads(_reclose_recipe(parent, issued))
    candidate_projection = {
        key: value for key, value in candidate.items() if key != "recipe_fingerprint"
    }
    candidate = PLANNER_SUPPORT.normalize_recipe(
        candidate_projection, issued.normalization_profile
    )
    candidate["recipe_fingerprint"] = PLANNER_SUPPORT.fingerprint(candidate)
    candidate_raw = _canonical_bytes(candidate)
    correspondence = tuple(
        MappingProxyType(
            {
                **_rewrite_fixture_value(dict(row), replacements),
                "successor_envelope_fingerprint": successor[
                    "artifact_fingerprint"
                ],
            }
        )
        for row in issued.correspondence
    )
    policy_value = SUPPORT._derive_isolation_policy_instance_value(
        parent_recipe=parent,
        successor_envelope_fingerprint=successor["artifact_fingerprint"],
        correspondence=correspondence,
        definition_id=issued.policy_instance.definition_id,
        definition_fingerprint=issued.policy_instance.definition_fingerprint,
        model_obligations=issued.policy_instance.value["model_obligations"],
        normalization_profile=issued.normalization_profile,
    )
    policy_instance = SUPPORT.IsolationPolicyInstance(
        definition_id=issued.policy_instance.definition_id,
        definition_fingerprint=issued.policy_instance.definition_fingerprint,
        value=MappingProxyType(policy_value),
        instance_fingerprint=PLANNER_SUPPORT.fingerprint(policy_value),
    )
    unrelated_inputs = replace(
        issued,
        parent_recipe=MappingProxyType(parent),
        successor_envelope=MappingProxyType(successor),
        correspondence=correspondence,
        policy_instance=policy_instance,
    )
    result = SUPPORT._evaluate_resolution_isolation_verified(
        inputs=unrelated_inputs,
        candidate_recipe_bytes=candidate_raw,
    )
    assert result.status == "isolated", [dict(row) for row in result.equations]
    assert policy_value["affected_clauses"] == [
        {
            "clause_id": "maintain.annotation_semantics",
            "category": "maintains",
            "pointer": "/maintains/0",
        }
    ]


AUTHORITY_MUTATIONS = (
    "missing_successor_key",
    "extra_successor_key",
    "wrong_delta_schema",
    "wrong_delta_pointer",
    "wrong_delta_unit_context",
    "wrong_task_session",
    "retained_typed_value",
    "retained_authority_kind",
    "retained_provenance",
)


@pytest.mark.parametrize("mutation", AUTHORITY_MUTATIONS)
def test_task2_authority_mutation_refuses_fully_reclosed_successor(
    mutation: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    envelope = json.loads(ARTIFACTS.SUCCESSOR_ENVELOPE_PATH.read_bytes())
    facts = envelope["payload"]["facts"]
    rows = envelope["value_bindings"]
    if mutation == "missing_successor_key":
        del facts["grid_spacing"]
        rows.remove(_binding(envelope, "grid_spacing"))
        raw = _reclose(envelope)
    elif mutation == "extra_successor_key":
        facts["unrelated_extra"] = {
            "schema": "rook.semantic_string:v1",
            "value": "extra",
            "unit": None,
            "unit_context_ref": None,
        }
        rows.append(
            {
                "authority_kind": "user_fact",
                "binding_id": "task-value.unrelated_extra",
                "json_pointer": "/facts/unrelated_extra",
                "provenance": {
                    "issuer_id": "lm9b-p-governed-resolution-fixture",
                    "issuer_kind": "deterministic_fixture",
                },
                "semantic_key": "unrelated_extra",
                "typed_value_fingerprint": TYPED_VALUES.fingerprint(
                    facts["unrelated_extra"]
                ),
                "value_schema": "rook.semantic_string:v1",
            }
        )
        rows.sort(key=lambda row: row["semantic_key"].encode("utf-16-be"))
        raw = _reclose(envelope)
    elif mutation == "wrong_delta_schema":
        facts["grid_spacing"] = {
            "schema": "rook.semantic_string:v1",
            "value": "2",
            "unit": None,
            "unit_context_ref": None,
        }
        raw = _reclose_fact(envelope, "grid_spacing")
    elif mutation == "wrong_delta_pointer":
        _binding(envelope, "grid_spacing")["json_pointer"] = "/facts/minimum_height"
        raw = _reclose(envelope)
    elif mutation == "wrong_delta_unit_context":
        facts["grid_spacing"]["unit_context_ref"] = {
            "kind": "artifact_value",
            "artifact_id": "environment_snapshot",
            "json_pointer": "/document/other_unit_context",
        }
        raw = _reclose_fact(envelope, "grid_spacing")
    elif mutation == "wrong_task_session":
        envelope["task_session_id"] = "other-task-session"
        raw = _reclose(envelope)
    elif mutation == "retained_typed_value":
        facts["element_kind"]["value"] = "sphere"
        raw = _reclose_fact(envelope, "element_kind")
    elif mutation == "retained_authority_kind":
        _binding(envelope, "element_kind")["authority_kind"] = "task_fact"
        raw = _reclose(envelope)
    else:
        _binding(envelope, "element_kind")["provenance"]["issuer_id"] = (
            "different-fixture-issuer"
        )
        raw = _reclose(envelope)

    with pytest.raises(ValueError):
        _load_with_successor(monkeypatch, tmp_path, raw)


def test_task2_authority_mutation_rejects_unreviewed_successor_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A fully valid reclosed fixture is still not reviewed instrument input."""
    envelope = json.loads(ARTIFACTS.SUCCESSOR_ENVELOPE_PATH.read_bytes())
    envelope["issued_at"] = "2026-07-23T12:00:01Z"
    raw = _reclose(envelope)
    with pytest.raises(ValueError, match="reviewed (Git object|checkout)"):
        _load_with_successor(monkeypatch, tmp_path, raw)


def test_task2_authority_mutation_rejects_extra_carrier_contract() -> None:
    sources = ARTIFACTS.load_verified_resolution_sources(
        historical_source_dir=HISTORICAL_SOURCE,
        derivative_archive=DERIVATIVE_ARCHIVE,
        derivative_identity=ARTIFACTS.OFFICIAL_DERIVATIVE_IDENTITY,
        carrier_qualification_archive=CARRIER_QUALIFICATION,
        carrier_qualification_identity=(
            ARTIFACTS.HISTORICAL_CARRIER_QUALIFICATION_IDENTITY
        ),
        repo_root=ROOT,
        successor_envelope_path=ARTIFACTS.SUCCESSOR_ENVELOPE_PATH,
    )
    object.__setattr__(
        sources,
        "exact_contract_bytes",
        {**sources.exact_contract_bytes, "extra": b"{}"},
    )
    with pytest.raises(ValueError, match="closure-issued"):
        ARTIFACTS.consume_verified_resolution_sources(sources)


def test_task2_authority_mutation_rejects_parent_established_unresolved_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = CARRIER.derive_authority_partition

    def overlapping_partition(**kwargs: object):
        value = original(**kwargs)
        overlap = value.required_delta_keys[0]
        return replace(
            value,
            parent_keys=tuple(
                sorted((*value.parent_keys, overlap), key=lambda key: key.encode("utf-16-be"))
            ),
        )

    monkeypatch.setattr(CARRIER, "derive_authority_partition", overlapping_partition)
    sources = ARTIFACTS.load_verified_resolution_sources(
        historical_source_dir=HISTORICAL_SOURCE,
        derivative_archive=DERIVATIVE_ARCHIVE,
        derivative_identity=ARTIFACTS.OFFICIAL_DERIVATIVE_IDENTITY,
        carrier_qualification_archive=CARRIER_QUALIFICATION,
        carrier_qualification_identity=(
            ARTIFACTS.HISTORICAL_CARRIER_QUALIFICATION_IDENTITY
        ),
        repo_root=ROOT,
        successor_envelope_path=ARTIFACTS.SUCCESSOR_ENVELOPE_PATH,
    )
    with pytest.raises(ValueError, match="overlap"):
        ARTIFACTS.assemble_resolution_instrument(
            sources=sources,
            isolation_policy_path=ARTIFACTS.ISOLATION_POLICY_PATH,
            evaluation_rubric_path=ARTIFACTS.EVALUATION_RUBRIC_PATH,
        )


@pytest.mark.parametrize("role", ("authority.environment_snapshot", "authority.planning_policy"))
def test_task2_authority_mutation_rejects_replacement_historical_authority_source(
    role: str, tmp_path: Path
) -> None:
    replacement_source = tmp_path / role.replace(".", "-")
    replacement_source.mkdir()
    with pytest.raises(ValueError, match="historical source location"):
        ARTIFACTS.load_verified_resolution_sources(
            historical_source_dir=replacement_source,
            derivative_archive=DERIVATIVE_ARCHIVE,
            derivative_identity=ARTIFACTS.OFFICIAL_DERIVATIVE_IDENTITY,
            carrier_qualification_archive=CARRIER_QUALIFICATION,
            carrier_qualification_identity=(
                ARTIFACTS.HISTORICAL_CARRIER_QUALIFICATION_IDENTITY
            ),
            repo_root=ROOT,
            successor_envelope_path=ARTIFACTS.SUCCESSOR_ENVELOPE_PATH,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "typed_value_helper_drift",
        "carrier_artifact_helper_drift",
        "profile_drift",
        "registry_drift",
        "payload_schema_drift",
        "carrier_runtime_drift",
        "carrier_contract_identity_drift",
    ),
)
def test_task2_authority_mutation_rejects_carrier_instrument_drift(
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if mutation in {"typed_value_helper_drift", "carrier_artifact_helper_drift"}:
        original = ARTIFACTS._git_object
        target = (
            "scripts/lm9_semantic_typed_values.py"
            if mutation == "typed_value_helper_drift"
            else "scripts/lm9_typed_fact_carrier_artifacts.py"
        )

        def changed_git_object(repo: Path, commit: str, relative_path: str) -> bytes:
            raw = original(repo, commit, relative_path)
            if commit != ARTIFACTS.HISTORICAL_CARRIER_COMMIT and relative_path == target:
                return raw + b"\n# drift"
            return raw

        monkeypatch.setattr(ARTIFACTS, "_git_object", changed_git_object)
    elif mutation == "profile_drift":
        monkeypatch.setattr(TYPED_VALUES, "PROFILE_ID", "rook.json_schema_profile:drift")
    elif mutation in {"registry_drift", "payload_schema_drift"}:
        changed = tmp_path / f"{mutation}.json"
        changed.write_bytes(b"{}")
        monkeypatch.setattr(
            CARRIER,
            "REGISTRY_PATH" if mutation == "registry_drift" else "PAYLOAD_SCHEMA_PATH",
            changed,
        )
    elif mutation == "carrier_runtime_drift":
        original_runtime = TYPED_VALUES.current_runtime_identity

        def changed_runtime():
            value = original_runtime()
            return replace(value, version=value.version + "-drift")

        monkeypatch.setattr(TYPED_VALUES, "current_runtime_identity", changed_runtime)
    else:
        monkeypatch.setattr(TYPED_VALUES, "HELPER_CONTRACT_ID", "lm9.typed_values:drift")

    with pytest.raises((TypeError, ValueError, subprocess.CalledProcessError)):
        ARTIFACTS.load_verified_resolution_sources(
            historical_source_dir=HISTORICAL_SOURCE,
            derivative_archive=DERIVATIVE_ARCHIVE,
            derivative_identity=ARTIFACTS.OFFICIAL_DERIVATIVE_IDENTITY,
            carrier_qualification_archive=CARRIER_QUALIFICATION,
            carrier_qualification_identity=(
                ARTIFACTS.HISTORICAL_CARRIER_QUALIFICATION_IDENTITY
            ),
            repo_root=ROOT,
            successor_envelope_path=ARTIFACTS.SUCCESSOR_ENVELOPE_PATH,
        )


def test_task3_missing_affected_clause_is_total_isolation_rejection() -> None:
    inputs = _resolution_inputs()
    candidate = json.loads(ISOLATED_SUCCESSOR_RECIPE.read_bytes())
    affected = inputs.policy_instance.value["affected_clauses"][0]
    category = affected["category"]
    clause_id = affected["clause_id"]
    candidate[category] = [
        row for row in candidate[category] if row["clause_id"] != clause_id
    ]
    raw = _reclose_recipe(candidate, inputs)
    try:
        result = SUPPORT.evaluate_resolution_isolation(
            inputs=inputs,
            candidate_recipe_bytes=raw,
        )
    except KeyError as exc:
        pytest.fail(f"isolation gate is not total for a missing clause: {exc}")
    assert result.status == "isolation_rejected"
    assert "clause_ownership" in {
        row["equation_id"] for row in result.bounded_differences
    }
