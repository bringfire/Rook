"""Frozen authority loading and R01-free LM9B-C handoff for LM9B-P."""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from jsonschema import Draft202012Validator
from rook.validation_kernel.canonical_json import canonical_fingerprint, sha256_prefixed
from rook.validation_kernel.owned_json import own_trusted_json

from lm9b_p_planner_recipe_transfer_support import (
    MechanicalGateResult,
    NormalizationProfile,
    evaluate_mechanical_gate,
    fingerprint,
    fingerprint_without,
    load_normalization_profile,
    normalization_profile_from_value,
    parse_strict_json,
    resolve_json_pointer,
    validate_exclusion_policy,
)


_VOCABULARY_FILES = {
    "semantic_authority_code_vocabulary": "semantic_authority_code_vocabulary.json",
    "semantic_capability_code_vocabulary": "semantic_capability_code_vocabulary.json",
    "worker_slot_code_vocabulary": "worker_slot_code_vocabulary.json",
    "semantic_materiality_code_vocabulary": "semantic_materiality_code_vocabulary.json",
    "semantic_value_schema_registry": "semantic_value_schema_registry.json",
}
_AUTHORITY_FILES = {
    "task_envelope": "task_envelope.json",
    "environment_snapshot": "environment_snapshot.json",
    "planning_policy": "planning_policy.json",
}
_PLANNER_INPUT_FILES = (
    ("attempt_context", "attempt_context.json", "json"),
    ("brief", "radial_brief.txt", "text"),
    ("authority.task_envelope", "task_envelope.json", "json"),
    ("authority.environment_snapshot", "environment_snapshot.json", "json"),
    ("authority.planning_policy", "planning_policy.json", "json"),
    ("registry.payload_schemas", "payload_schema_registry.json", "json"),
    ("registry.capabilities", "capability_registry.json", "json"),
    (
        "vocabulary.semantic_authority_codes",
        "semantic_authority_code_vocabulary.json",
        "json",
    ),
    (
        "vocabulary.semantic_capability_codes",
        "semantic_capability_code_vocabulary.json",
        "json",
    ),
    ("vocabulary.worker_slot_codes", "worker_slot_code_vocabulary.json", "json"),
    (
        "vocabulary.semantic_materiality_codes",
        "semantic_materiality_code_vocabulary.json",
        "json",
    ),
    (
        "vocabulary.semantic_value_schemas",
        "semantic_value_schema_registry.json",
        "json",
    ),
    ("recipe_schema", "planner_recipe_probe_schema.json", "json"),
    ("normalization_profile", "recipe_normalization_profile.json", "json"),
    ("authoring_contract", "planner_authoring_contract.json", "json"),
    ("exclusion_policy", "planner_exclusion_policy.json", "json"),
    ("evaluation_rubric", "planner_evaluation_rubric.json", "json"),
)
PLANNER_RENDERER_ID = "lm9b_p.planner_request_renderer:v1"
PLANNER_EVALUATOR_RENDERER_ID = "lm9b_p.planner_evaluator_request_renderer:v1"


@dataclass(frozen=True)
class FrozenPlannerAuthority:
    fixture_dir: Path
    artifacts: Mapping[str, Mapping[str, object]]
    vocabularies: Mapping[str, Mapping[str, object]]
    payload_schema_registry: Mapping[str, object]
    capability_registry: Mapping[str, object]
    recipe_schema: Mapping[str, object]
    normalization_profile: NormalizationProfile
    attempt_context: Mapping[str, object]
    exclusion_policy: Mapping[str, object]
    evaluated_at: str


@dataclass(frozen=True)
class PlannerInputRecord:
    role: str
    relative_path: str
    raw_sha256: str
    canonical_fingerprint: str
    raw_bytes: bytes
    value: object


@dataclass(frozen=True)
class FrozenPlannerInputs:
    records: tuple[PlannerInputRecord, ...]
    brief: str
    authority: FrozenPlannerAuthority
    authority_context: Mapping[str, object]
    recipe_schema: Mapping[str, object]
    normalization_profile: Mapping[str, object]
    authoring_contract: Mapping[str, object]
    exclusion_policy: Mapping[str, object]
    evaluation_rubric: Mapping[str, object]
    attempt_context: Mapping[str, object]


@dataclass(frozen=True)
class RenderedRequest:
    renderer_id: str
    payload: Mapping[str, object]
    raw_bytes: bytes
    raw_sha256: str
    canonical_fingerprint: str


@dataclass(frozen=True)
class Lm9bcHandoff:
    fixture_dir: Path
    manifest: Mapping[str, object]
    manifest_raw_sha256: str
    manifest_canonical_fingerprint: str
    archived_recipe_bytes: bytes
    compiler_renderer_id: str
    attempt_context_fingerprint: str


def _object(path: Path) -> Mapping[str, object]:
    value = parse_strict_json(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must be an object")
    return value


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _verify_fingerprint(value: Mapping[str, object], field: str, label: str) -> None:
    if value.get(field) != fingerprint_without(value, field):
        raise ValueError(f"{label} fingerprint mismatch")


def _instant(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"invalid {label}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"invalid {label}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"invalid {label}")
    return parsed


def _require_fresh(
    value: Mapping[str, object], evaluated_at: datetime, label: str
) -> None:
    observed_field = "observed_at" if "observed_at" in value else "issued_at"
    observed = _instant(value[observed_field], f"{label} {observed_field}")
    expires = _instant(value["expires_at"], f"{label} expires_at")
    if not observed <= evaluated_at < expires:
        raise ValueError(f"{label} is stale at frozen evaluation time")


def _validate_authority_components(
    *,
    attempt_context: Mapping[str, object],
    artifacts: Mapping[str, Mapping[str, object]],
    vocabularies: Mapping[str, Mapping[str, object]],
    payload_registry: Mapping[str, object],
    capability_registry: Mapping[str, object],
) -> str:
    if set(artifacts) != set(_AUTHORITY_FILES):
        raise ValueError("invalid authority artifact set")
    if set(vocabularies) != set(_VOCABULARY_FILES):
        raise ValueError("invalid authority vocabulary set")
    if set(attempt_context) != {
        "schema",
        "attempt_id",
        "evaluated_at",
        "trusted_clock_source",
        "task_session_id",
        "environment_session_id",
        "capability_registry_session_id",
        "context_fingerprint",
    } or attempt_context.get("schema") != "rook.lm9b_p.probe_attempt_context:v1":
        raise ValueError("invalid attempt context shape")
    _verify_fingerprint(attempt_context, "context_fingerprint", "attempt context")
    if attempt_context.get("trusted_clock_source") != "deterministic_fixture":
        raise ValueError("attempt context requires deterministic fixture clock")
    evaluated_at_text = attempt_context.get("evaluated_at")
    evaluated_at = _instant(evaluated_at_text, "attempt evaluated_at")
    assert isinstance(evaluated_at_text, str)
    for artifact_id, artifact in artifacts.items():
        _verify_fingerprint(artifact, "artifact_fingerprint", artifact_id)

    for name, vocabulary in vocabularies.items():
        _verify_fingerprint(vocabulary, "vocabulary_fingerprint", name)

    _verify_fingerprint(payload_registry, "registry_fingerprint", "payload schema registry")
    payload_entries = {
        entry["schema_id"]: entry for entry in payload_registry["entries"]
    }
    if len(payload_entries) != len(payload_registry["entries"]):
        raise ValueError("duplicate payload schema ID")
    for artifact_id in ("task_envelope", "environment_snapshot"):
        artifact = artifacts[artifact_id]
        entry = payload_entries.get(artifact["payload_schema"])
        if entry is None:
            raise ValueError(f"payload schema is unbound: {artifact_id}")
        if entry["schema_fingerprint"] != fingerprint(entry["schema_document"]):
            raise ValueError(f"payload schema fingerprint mismatch: {artifact_id}")
        if artifact["payload_schema_fingerprint"] != entry["schema_fingerprint"]:
            raise ValueError(f"artifact payload schema mismatch: {artifact_id}")
        payload_errors = list(
            Draft202012Validator(_thaw_json(entry["schema_document"])).iter_errors(
                _thaw_json(artifact["payload"])
            )
        )
        if payload_errors:
            raise ValueError(f"artifact payload schema failed: {artifact_id}")
        pointers: set[str] = set()
        for binding in artifact["value_bindings"]:
            pointer = binding["json_pointer"]
            if pointer in pointers:
                raise ValueError(f"duplicate value binding pointer: {artifact_id}")
            pointers.add(pointer)
            resolved = resolve_json_pointer(artifact["payload"], pointer)
            expected = fingerprint(
                {"schema": binding["value_schema"], "value": resolved}
            )
            if binding["typed_value_fingerprint"] != expected:
                raise ValueError(f"typed value fingerprint mismatch: {artifact_id}")

    _verify_fingerprint(capability_registry, "registry_fingerprint", "capability registry")
    if artifacts["task_envelope"].get("task_session_id") != attempt_context.get(
        "task_session_id"
    ):
        raise ValueError("task session mismatch")
    if artifacts["environment_snapshot"].get(
        "environment_session_id"
    ) != attempt_context.get("environment_session_id"):
        raise ValueError("environment session mismatch")
    if capability_registry.get("registry_session_id") != attempt_context.get(
        "capability_registry_session_id"
    ):
        raise ValueError("capability registry session mismatch")
    _require_fresh(artifacts["environment_snapshot"], evaluated_at, "environment snapshot")
    _require_fresh(artifacts["planning_policy"], evaluated_at, "planning policy")
    _require_fresh(capability_registry, evaluated_at, "capability registry")
    return evaluated_at_text


def load_planner_authority_context(fixture_dir: Path) -> FrozenPlannerAuthority:
    fixture_dir = Path(fixture_dir).resolve()
    attempt_context = _object(fixture_dir / "attempt_context.json")
    artifacts = {
        artifact_id: _object(fixture_dir / filename)
        for artifact_id, filename in _AUTHORITY_FILES.items()
    }
    vocabularies = {
        name: _object(fixture_dir / filename)
        for name, filename in _VOCABULARY_FILES.items()
    }
    payload_registry = _object(fixture_dir / "payload_schema_registry.json")
    capability_registry = _object(fixture_dir / "capability_registry.json")
    evaluated_at_text = _validate_authority_components(
        attempt_context=attempt_context,
        artifacts=artifacts,
        vocabularies=vocabularies,
        payload_registry=payload_registry,
        capability_registry=capability_registry,
    )
    recipe_schema = _object(fixture_dir / "planner_recipe_probe_schema.json")
    profile = load_normalization_profile(fixture_dir / "recipe_normalization_profile.json")
    exclusion_policy = _object(fixture_dir / "planner_exclusion_policy.json")
    validate_exclusion_policy(exclusion_policy)
    return FrozenPlannerAuthority(
        fixture_dir=fixture_dir,
        artifacts=_freeze_json(artifacts),
        vocabularies=_freeze_json(vocabularies),
        payload_schema_registry=_freeze_json(payload_registry),
        capability_registry=_freeze_json(capability_registry),
        recipe_schema=_freeze_json(recipe_schema),
        normalization_profile=profile,
        attempt_context=_freeze_json(attempt_context),
        exclusion_policy=_freeze_json(exclusion_policy),
        evaluated_at=evaluated_at_text,
    )


def _planner_input_record(
    fixture_dir: Path, role: str, filename: str, kind: str
) -> PlannerInputRecord:
    raw = (fixture_dir / filename).read_bytes()
    if kind == "text":
        if raw.startswith(b"\xef\xbb\xbf"):
            raise ValueError(f"{filename} must not contain a UTF-8 BOM")
        try:
            decoded = raw.decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise ValueError(f"{filename} is not UTF-8") from exc
        if "\r" in decoded or decoded.count("\n") > 1 or not decoded.endswith("\n"):
            raise ValueError(f"{filename} must contain one LF-terminated line")
        value: object = decoded[:-1]
        if not value:
            raise ValueError(f"{filename} must not be empty")
    else:
        value = parse_strict_json(raw)
        if not isinstance(value, dict):
            raise ValueError(f"{filename} must be an object")
    return PlannerInputRecord(
        role=role,
        relative_path=filename,
        raw_sha256=sha256_prefixed(raw),
        canonical_fingerprint=fingerprint(value),
        raw_bytes=raw,
        value=_freeze_json(value),
    )


def _verify_authoring_contract(value: Mapping[str, object]) -> None:
    if set(value) != {
        "schema",
        "contract_id",
        "recipe_schema",
        "recipe_profile",
        "language_boundary",
        "relational_invariants",
        "authoring_rules",
        "non_claims",
        "contract_fingerprint",
    }:
        raise ValueError("invalid authoring contract shape")
    if value.get("schema") != "rook.lm9b_p.planner_authoring_contract:v1":
        raise ValueError("invalid authoring contract schema")
    _verify_fingerprint(value, "contract_fingerprint", "authoring contract")
    expected_boundary = {
        "clause_source_reference_kind": "artifact_value",
        "clause_local_reference_kinds": ["assumption", "derived_fact"],
        "synthesis_codes": {
            "canonicalization": "planner_semantic_classification",
            "goal": "planner_goal_synthesis",
            "invariant": "planner_invariant_projection",
            "maintains": "planner_semantic_synthesis",
            "postcondition": "planner_postcondition_projection",
            "requires": "planner_requirement_synthesis",
        },
        "assumption_unit_context_reference_kind": "artifact_value",
        "assumption_basis_reference_kinds": [
            "artifact_value",
            "assumption",
            "capability",
            "clause",
            "derived_fact",
            "policy_rule",
            "shape",
            "unresolved_intent",
        ],
        "assumption_policy_reference_kind": "policy_rule",
        "derived_fact_operators": ["multiply"],
        "derived_fact_input_reference_kind": "artifact_value",
        "unresolved_policy_reference_kind": "policy_rule",
        "unresolved_unit_context_reference_kind": "artifact_value",
        "worker_slots_max_entries": 0,
        "confirmation_receipts_admitted": False,
    }
    if _thaw_json(value.get("language_boundary")) != expected_boundary:
        raise ValueError("authoring contract language boundary mismatch")


def _verify_evaluation_rubric(
    value: Mapping[str, object], contract: Mapping[str, object]
) -> None:
    if set(value) != {
        "schema",
        "rubric_id",
        "authoring_contract_binding",
        "scenario_obligations",
        "criteria",
        "recommendations",
        "forbidden_dependencies",
        "rubric_fingerprint",
    }:
        raise ValueError("invalid evaluation rubric shape")
    if value.get("schema") != "rook.lm9b_p.planner_evaluation_rubric:v1":
        raise ValueError("invalid evaluation rubric schema")
    _verify_fingerprint(value, "rubric_fingerprint", "evaluation rubric")
    expected_binding = {
        "contract_id": contract["contract_id"],
        "contract_fingerprint": contract["contract_fingerprint"],
        "recipe_schema": contract["recipe_schema"],
    }
    if _thaw_json(value.get("authoring_contract_binding")) != expected_binding:
        raise ValueError("evaluation rubric contract binding mismatch")
    if _thaw_json(value.get("recommendations")) != [
        "faithful_blocked",
        "faithful_ready",
        "planner_failure",
    ]:
        raise ValueError("invalid evaluation rubric recommendation vocabulary")
    criteria = _thaw_json(value.get("criteria"))
    if not isinstance(criteria, list) or [
        item.get("criterion_id") if isinstance(item, dict) else None
        for item in criteria
    ] != [
        "brief_fidelity",
        "provenance_fidelity",
        "material_authority",
        "unresolved_intent_honesty",
        "implementation_leakage",
    ]:
        raise ValueError("invalid evaluation rubric criteria")


def _planner_capability_evidence(
    registry: Mapping[str, object],
) -> Mapping[str, object]:
    return {
        "schema": "rook.lm9b_p.planner_capability_evidence:v1",
        "source_registry_id": registry["registry_id"],
        "source_registry_session_id": registry["registry_session_id"],
        "source_registry_fingerprint": registry["registry_fingerprint"],
        "observed_at": registry["observed_at"],
        "expires_at": registry["expires_at"],
        "entries": [
            {
                "capability_code": entry["capability_code"],
                "availability": entry["availability"],
                "constraints_fingerprint": entry["constraints_fingerprint"],
            }
            for entry in registry["entries"]
        ],
    }


def load_planner_inputs(fixture_dir: Path) -> FrozenPlannerInputs:
    fixture_dir = Path(fixture_dir).resolve()
    records = tuple(
        _planner_input_record(fixture_dir, role, filename, kind)
        for role, filename, kind in _PLANNER_INPUT_FILES
    )
    by_role = {record.role: record for record in records}
    if len(by_role) != len(records):
        raise ValueError("duplicate Planner input role")
    authority = load_planner_authority_context(fixture_dir)
    contract = by_role["authoring_contract"].value
    exclusion_policy = by_role["exclusion_policy"].value
    rubric = by_role["evaluation_rubric"].value
    recipe_schema = by_role["recipe_schema"].value
    normalization_profile = by_role["normalization_profile"].value
    assert isinstance(contract, Mapping)
    assert isinstance(exclusion_policy, Mapping)
    assert isinstance(rubric, Mapping)
    assert isinstance(recipe_schema, Mapping)
    assert isinstance(normalization_profile, Mapping)
    _verify_authoring_contract(contract)
    validate_exclusion_policy(exclusion_policy)
    _verify_evaluation_rubric(rubric, contract)
    if recipe_schema.get("$id") != "rook.lm9b_p.planner_recipe_probe_schema:v1":
        raise ValueError("invalid Planner recipe probe schema")
    if normalization_profile.get("profile_id") != authority.normalization_profile.profile_id:
        raise ValueError("normalization profile identity mismatch")
    snapshot_bindings = {
        "attempt_context": authority.attempt_context,
        "authority.task_envelope": authority.artifacts["task_envelope"],
        "authority.environment_snapshot": authority.artifacts[
            "environment_snapshot"
        ],
        "authority.planning_policy": authority.artifacts["planning_policy"],
        "registry.payload_schemas": authority.payload_schema_registry,
        "registry.capabilities": authority.capability_registry,
        "vocabulary.semantic_authority_codes": authority.vocabularies[
            "semantic_authority_code_vocabulary"
        ],
        "vocabulary.semantic_capability_codes": authority.vocabularies[
            "semantic_capability_code_vocabulary"
        ],
        "vocabulary.worker_slot_codes": authority.vocabularies[
            "worker_slot_code_vocabulary"
        ],
        "vocabulary.semantic_materiality_codes": authority.vocabularies[
            "semantic_materiality_code_vocabulary"
        ],
        "vocabulary.semantic_value_schemas": authority.vocabularies[
            "semantic_value_schema_registry"
        ],
        "recipe_schema": authority.recipe_schema,
        "exclusion_policy": authority.exclusion_policy,
    }
    for role, trusted_value in snapshot_bindings.items():
        if by_role[role].value != trusted_value:
            raise ValueError(f"Planner input snapshot mismatch: {role}")
    if (
        normalization_profile.get("profile_fingerprint")
        != authority.normalization_profile.profile_fingerprint
    ):
        raise ValueError("Planner input snapshot mismatch: normalization_profile")
    authority_context = _freeze_json({
        "artifacts": authority.artifacts,
        "payload_schema_registry": authority.payload_schema_registry,
        "capability_registry": _planner_capability_evidence(
            authority.capability_registry
        ),
        "vocabularies": authority.vocabularies,
    })
    assert isinstance(authority_context, Mapping)
    brief = by_role["brief"].value
    assert isinstance(brief, str)
    return FrozenPlannerInputs(
        records=records,
        brief=brief,
        authority=authority,
        authority_context=authority_context,
        recipe_schema=recipe_schema,
        normalization_profile=normalization_profile,
        authoring_contract=contract,
        exclusion_policy=exclusion_policy,
        evaluation_rubric=rubric,
        attempt_context=authority.attempt_context,
    )


def _render_request(renderer_id: str, payload: Mapping[str, object]) -> RenderedRequest:
    frozen_payload = _freeze_json(dict(payload))
    assert isinstance(frozen_payload, Mapping)
    builtin_payload = _thaw_json(frozen_payload)
    raw = json.dumps(
        builtin_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return RenderedRequest(
        renderer_id=renderer_id,
        payload=frozen_payload,
        raw_bytes=raw,
        raw_sha256=sha256_prefixed(raw),
        canonical_fingerprint=fingerprint(frozen_payload),
    )


def render_planner_request(inputs: FrozenPlannerInputs) -> RenderedRequest:
    _verify_frozen_planner_inputs(inputs)
    _, forbidden_request_markers = validate_exclusion_policy(
        inputs.exclusion_policy
    )
    payload = {
        "schema": "rook.lm9b_p.planner_authoring_request:v1",
        "renderer_id": PLANNER_RENDERER_ID,
        "attempt_context": inputs.attempt_context,
        "brief": inputs.brief,
        "authority_context": inputs.authority_context,
        "authoring_contract": inputs.authoring_contract,
        "recipe_schema": inputs.recipe_schema,
        "normalization_profile": inputs.normalization_profile,
        "exclusion_policy_binding": {
            "policy_id": inputs.exclusion_policy["policy_id"],
            "policy_fingerprint": inputs.exclusion_policy["policy_fingerprint"],
        },
    }
    rendered = _render_request(PLANNER_RENDERER_ID, payload)
    folded = rendered.raw_bytes.decode("utf-8").casefold()
    if any(marker.casefold() in folded for marker in forbidden_request_markers):
        raise ValueError("Planner request contains forbidden context")
    return rendered


def _accepted_gate_result(
    inputs: FrozenPlannerInputs, gate_result: MechanicalGateResult
) -> MechanicalGateResult:
    _verify_frozen_planner_inputs(inputs)
    if (
        type(gate_result) is not MechanicalGateResult
        or gate_result.status != "mechanically_accepted"
        or gate_result.diagnostics
        or gate_result.final_recipe_bytes is None
        or gate_result.recipe_value_fingerprint is None
        or gate_result.ratified_recipe_fingerprint is None
        or gate_result.historical_recipe_fingerprint is None
    ):
        raise ValueError("accepted gate result is required")
    recomputed = evaluate_mechanical_gate(
        recipe_bytes=gate_result.final_recipe_bytes,
        authority=inputs.authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.authority.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )
    if (
        recomputed.status != "mechanically_accepted"
        or recomputed.diagnostics
        or recomputed.final_recipe_bytes is None
        or recomputed.recipe_value_fingerprint is None
        or recomputed.ratified_recipe_fingerprint is None
        or recomputed.historical_recipe_fingerprint is None
        or recomputed != gate_result
    ):
        raise ValueError("accepted gate result does not match frozen Planner inputs")
    return recomputed


def render_planner_evaluator_request(
    inputs: FrozenPlannerInputs,
    *,
    gate_result: MechanicalGateResult,
) -> RenderedRequest:
    accepted_result = _accepted_gate_result(inputs, gate_result)
    final_recipe_bytes = accepted_result.final_recipe_bytes
    assert final_recipe_bytes is not None
    try:
        recipe_text = final_recipe_bytes.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ValueError("final recipe is not UTF-8") from exc
    recipe_value = parse_strict_json(final_recipe_bytes)
    if not isinstance(recipe_value, dict):
        raise ValueError("final recipe must be an object")
    forbidden_recipe_markers, _ = validate_exclusion_policy(
        inputs.exclusion_policy
    )
    folded_recipe = recipe_text.casefold()
    if any(marker.casefold() in folded_recipe for marker in forbidden_recipe_markers):
        raise ValueError("final recipe contains forbidden context")
    payload = {
        "schema": "rook.lm9b_p.planner_evaluation_request:v1",
        "renderer_id": PLANNER_EVALUATOR_RENDERER_ID,
        "attempt_context": inputs.attempt_context,
        "brief": inputs.brief,
        "authority_context": inputs.authority_context,
        "final_recipe_json": recipe_text,
        "final_recipe_raw_sha256": sha256_prefixed(final_recipe_bytes),
        "deterministic_findings": {
            "status": accepted_result.status,
            "diagnostics": [
                {
                    "code": item.code,
                    "path": item.path,
                    "message": item.message,
                }
                for item in accepted_result.diagnostics
            ],
        },
        "evaluation_rubric": inputs.evaluation_rubric,
    }
    return _render_request(PLANNER_EVALUATOR_RENDERER_ID, payload)


def _load_lm9bc_artifacts_module():
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    path = Path(__file__).with_name("lm9b_c_compiler_sufficiency_artifacts.py")
    name = "lm9b_c_compiler_sufficiency_artifacts_for_lm9b_p"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("LM9B-C artifacts module is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_bytes(path: Path, raw: bytes) -> None:
    path.write_bytes(raw)


def _verified_planner_record(
    inputs: FrozenPlannerInputs, role: str
) -> PlannerInputRecord:
    matches = tuple(record for record in inputs.records if record.role == role)
    if len(matches) != 1:
        raise ValueError(f"frozen Planner input role is not unique: {role}")
    record = matches[0]
    if record.raw_sha256 != sha256_prefixed(record.raw_bytes):
        raise ValueError(f"frozen Planner input raw hash mismatch: {role}")
    if record.canonical_fingerprint != fingerprint(record.value):
        raise ValueError(f"frozen Planner input canonical hash mismatch: {role}")
    return record


def _verify_frozen_planner_inputs(
    inputs: FrozenPlannerInputs,
) -> Mapping[str, PlannerInputRecord]:
    expected_files = {
        role: (filename, kind) for role, filename, kind in _PLANNER_INPUT_FILES
    }
    if tuple(record.role for record in inputs.records) != tuple(expected_files):
        raise ValueError("frozen Planner input role order mismatch")
    records = {record.role: record for record in inputs.records}
    if len(records) != len(expected_files):
        raise ValueError("frozen Planner input role duplication")
    for role, (filename, kind) in expected_files.items():
        record = _verified_planner_record(inputs, role)
        if record.relative_path != filename:
            raise ValueError(f"frozen Planner input path mismatch: {role}")
        if kind == "text":
            try:
                parsed: object = record.raw_bytes.decode("utf-8", errors="strict")
            except UnicodeError as exc:
                raise ValueError(f"frozen Planner input is not UTF-8: {role}") from exc
            if not parsed.endswith("\n"):
                raise ValueError(f"frozen Planner text is not LF-terminated: {role}")
            parsed = parsed[:-1]
        else:
            parsed = parse_strict_json(record.raw_bytes)
        if _freeze_json(parsed) != record.value:
            raise ValueError(f"frozen Planner input value mismatch: {role}")

    expected_values = {
        "attempt_context": inputs.attempt_context,
        "brief": inputs.brief,
        "authority.task_envelope": inputs.authority.artifacts["task_envelope"],
        "authority.environment_snapshot": inputs.authority.artifacts[
            "environment_snapshot"
        ],
        "authority.planning_policy": inputs.authority.artifacts[
            "planning_policy"
        ],
        "registry.payload_schemas": inputs.authority.payload_schema_registry,
        "registry.capabilities": inputs.authority.capability_registry,
        "vocabulary.semantic_authority_codes": inputs.authority.vocabularies[
            "semantic_authority_code_vocabulary"
        ],
        "vocabulary.semantic_capability_codes": inputs.authority.vocabularies[
            "semantic_capability_code_vocabulary"
        ],
        "vocabulary.worker_slot_codes": inputs.authority.vocabularies[
            "worker_slot_code_vocabulary"
        ],
        "vocabulary.semantic_materiality_codes": inputs.authority.vocabularies[
            "semantic_materiality_code_vocabulary"
        ],
        "vocabulary.semantic_value_schemas": inputs.authority.vocabularies[
            "semantic_value_schema_registry"
        ],
        "recipe_schema": inputs.authority.recipe_schema,
        "normalization_profile": inputs.normalization_profile,
        "authoring_contract": inputs.authoring_contract,
        "exclusion_policy": inputs.exclusion_policy,
        "evaluation_rubric": inputs.evaluation_rubric,
    }
    for role, expected in expected_values.items():
        if records[role].value != expected:
            raise ValueError(f"frozen Planner authority binding mismatch: {role}")
    if inputs.attempt_context != inputs.authority.attempt_context:
        raise ValueError("frozen Planner attempt context binding mismatch")
    if inputs.recipe_schema != inputs.authority.recipe_schema:
        raise ValueError("frozen Planner recipe schema authority binding mismatch")
    if inputs.exclusion_policy != inputs.authority.exclusion_policy:
        raise ValueError("frozen Planner exclusion policy binding mismatch")
    if (
        type(inputs.authority.normalization_profile) is not NormalizationProfile
        or normalization_profile_from_value(inputs.normalization_profile)
        != inputs.authority.normalization_profile
    ):
        raise ValueError(
            "frozen Planner normalization profile authority binding mismatch"
        )
    expected_authority_context = _freeze_json(
        {
            "artifacts": inputs.authority.artifacts,
            "payload_schema_registry": inputs.authority.payload_schema_registry,
            "capability_registry": _planner_capability_evidence(
                inputs.authority.capability_registry
            ),
            "vocabularies": inputs.authority.vocabularies,
        }
    )
    if inputs.authority_context != expected_authority_context:
        raise ValueError("frozen Planner authority context binding mismatch")
    _verify_authoring_contract(inputs.authoring_contract)
    _verify_evaluation_rubric(
        inputs.evaluation_rubric, inputs.authoring_contract
    )
    if inputs.recipe_schema.get("$id") != "rook.lm9b_p.planner_recipe_probe_schema:v1":
        raise ValueError("invalid Planner recipe probe schema")
    evaluated_at = _validate_authority_components(
        attempt_context=inputs.attempt_context,
        artifacts=inputs.authority.artifacts,
        vocabularies=inputs.authority.vocabularies,
        payload_registry=inputs.authority.payload_schema_registry,
        capability_registry=inputs.authority.capability_registry,
    )
    if evaluated_at != inputs.authority.evaluated_at:
        raise ValueError("frozen Planner evaluation time binding mismatch")
    validate_exclusion_policy(inputs.exclusion_policy)
    return MappingProxyType(records)


def build_lm9bc_handoff(
    *,
    planner_inputs: FrozenPlannerInputs,
    gate_result: MechanicalGateResult,
    compiler_fixture_dir: Path,
    destination: Path,
) -> Lm9bcHandoff:
    """Build the LM9B-C boundary without reading R01 or its source manifest."""

    compiler_fixture_dir = Path(compiler_fixture_dir).resolve()
    destination = Path(destination).resolve()

    accepted_result = _accepted_gate_result(planner_inputs, gate_result)
    accepted_recipe_bytes = accepted_result.final_recipe_bytes
    assert accepted_recipe_bytes is not None
    planner_records = _verify_frozen_planner_inputs(planner_inputs)
    recipe = parse_strict_json(accepted_recipe_bytes)
    if not isinstance(recipe, dict):
        raise ValueError("accepted recipe must be an object")
    if recipe.get("recipe_fingerprint") != accepted_result.ratified_recipe_fingerprint:
        raise ValueError("accepted recipe fingerprint mismatch")

    task_record = planner_records["authority.task_envelope"]
    environment_record = planner_records["authority.environment_snapshot"]
    policy_record = planner_records["authority.planning_policy"]

    destination.mkdir(parents=True, exist_ok=False)

    rows = (
        ("recipe", "accepted_recipe.json", accepted_recipe_bytes),
        ("authority.task_envelope", "task_envelope.json", task_record.raw_bytes),
        ("authority.environment_snapshot", "environment_snapshot.json", environment_record.raw_bytes),
        ("authority.planning_policy", "planning_policy.json", policy_record.raw_bytes),
        ("implementation_context", "implementation_context.json", (compiler_fixture_dir / "implementation_context.json").read_bytes()),
        ("exclusion_policy", "exclusion_policy.json", (compiler_fixture_dir / "exclusion_policy.json").read_bytes()),
        ("evaluation_rubric", "evaluation_rubric.json", (compiler_fixture_dir / "evaluation_rubric.json").read_bytes()),
    )
    records: list[dict[str, object]] = []
    for role, filename, raw in rows:
        path = destination / filename
        _write_bytes(path, raw)
        persisted = path.read_bytes()
        if persisted != raw:
            raise ValueError(f"handoff write verification failed: {role}")
        value = parse_strict_json(persisted)
        if not isinstance(value, dict):
            raise ValueError(f"handoff record is not an object: {role}")
        records.append(
            {
                "role": role,
                "path": filename,
                "raw_sha256": sha256_prefixed(persisted),
                "canonical_fingerprint": canonical_fingerprint(own_trusted_json(value)),
            }
        )

    lm9bc = _load_lm9bc_artifacts_module()
    manifest = {
        "schema": lm9bc.MANIFEST_SCHEMA_ID,
        "renderer_id": lm9bc.COMPILER_RENDERER_ID,
        "probe_attempt_context": planner_inputs.attempt_context,
        "records": records,
    }
    manifest_raw = (
        json.dumps(_thaw_json(manifest), ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    manifest_path = destination / "input_manifest.json"
    _write_bytes(manifest_path, manifest_raw)
    persisted_manifest = manifest_path.read_bytes()
    if persisted_manifest != manifest_raw:
        raise ValueError("handoff manifest write verification failed")
    persisted_manifest_value = parse_strict_json(persisted_manifest)
    if not isinstance(persisted_manifest_value, dict):
        raise ValueError("persisted handoff manifest is not an object")
    archived_recipe_bytes = (destination / "accepted_recipe.json").read_bytes()
    if archived_recipe_bytes != accepted_recipe_bytes:
        raise ValueError("handoff recipe read-back verification failed")
    return Lm9bcHandoff(
        fixture_dir=destination,
        manifest=persisted_manifest_value,
        manifest_raw_sha256=sha256_prefixed(persisted_manifest),
        manifest_canonical_fingerprint=canonical_fingerprint(
            own_trusted_json(persisted_manifest_value)
        ),
        archived_recipe_bytes=archived_recipe_bytes,
        compiler_renderer_id=lm9bc.COMPILER_RENDERER_ID,
        attempt_context_fingerprint=planner_inputs.attempt_context[
            "context_fingerprint"
        ],
    )


__all__ = (
    "FrozenPlannerAuthority",
    "FrozenPlannerInputs",
    "Lm9bcHandoff",
    "PlannerInputRecord",
    "RenderedRequest",
    "build_lm9bc_handoff",
    "load_planner_authority_context",
    "load_planner_inputs",
    "render_planner_evaluator_request",
    "render_planner_request",
)
