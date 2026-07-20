"""Frozen authority loading and R01-free LM9B-C handoff for LM9B-P."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence
from uuid import uuid4

from jsonschema import Draft202012Validator
from rook.validation_kernel.canonical_json import canonical_fingerprint, sha256_prefixed
from rook.validation_kernel.owned_json import own_trusted_json

from lm9b_p_planner_recipe_transfer_support import (
    MechanicalGateResult,
    NormalizationProfile,
    PLANNER_MAX_TURNS,
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


@dataclass(frozen=True)
class SealedPlannerCheckpointArchive:
    archive_dir: Path
    aggregate_identity: str
    checksums_raw_sha256: str


_CHECKPOINT_CHECKSUMS_SCHEMA = "rook.lm9b_p.checkpoint_checksums:v1"
_CHECKPOINT_IDENTITY_SCHEMA = "rook.lm9b_p.checkpoint_identity:v1"
_CHECKPOINT_CLASSIFICATION_SCHEMA = "rook.lm9b_p.checkpoint_classification:v1"


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


def derive_checkpoint_classification(
    planner_session: object, evaluator: object | None
) -> str:
    """Derive the sole Checkpoint 1 classification from captured outcomes."""

    termination = getattr(planner_session, "termination", None)
    if termination == "mechanically_rejected":
        return "probe_mechanically_rejected"
    if termination != "mechanically_accepted" or evaluator is None:
        return "probe_inconclusive"
    if getattr(evaluator, "termination", None) != "valid_recommendation":
        return "probe_inconclusive"
    classifications = {
        "faithful_blocked": "probe_candidate_blocked",
        "planner_failure": "probe_planner_failure",
        "faithful_ready": "probe_candidate_ready",
    }
    recommendation = getattr(evaluator, "recommendation", None)
    if recommendation not in classifications:
        raise ValueError("invalid evaluator recommendation for checkpoint")
    return classifications[recommendation]


def _archive_json_bytes(value: object) -> bytes:
    return (
        json.dumps(_thaw_json(value), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    ).encode("utf-8")


def _archive_write(
    root: Path,
    records: list[dict[str, object]],
    *,
    role: str,
    relative_path: str,
    raw: bytes,
) -> bytes:
    path = root / relative_path
    if path.exists():
        raise ValueError(f"duplicate sealed checkpoint archive path: {relative_path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    persisted = path.read_bytes()
    if persisted != raw:
        raise ValueError(f"sealed checkpoint archive write verification failed: {role}")
    records.append(
        {
            "role": role,
            "path": relative_path,
            "raw_sha256": sha256_prefixed(persisted),
            "byte_length": len(persisted),
        }
    )
    return persisted


def _gate_feedback(gate_result: object | None) -> Mapping[str, object]:
    if gate_result is None:
        return {
            "schema": "rook.lm9b_p.planner_feedback:v1",
            "status": "no_submission",
            "diagnostics": [],
            "recipe_value_fingerprint": None,
            "ratified_recipe_fingerprint": None,
            "historical_recipe_fingerprint": None,
        }
    diagnostics = []
    for diagnostic in getattr(gate_result, "diagnostics", ()):
        diagnostics.append(
            {
                "code": diagnostic.code,
                "path": diagnostic.path,
                "message": diagnostic.message,
            }
        )
    return {
        "schema": "rook.lm9b_p.planner_feedback:v1",
        "status": getattr(gate_result, "status", None),
        "diagnostics": diagnostics,
        "recipe_value_fingerprint": getattr(
            gate_result, "recipe_value_fingerprint", None
        ),
        "ratified_recipe_fingerprint": getattr(
            gate_result, "ratified_recipe_fingerprint", None
        ),
        "historical_recipe_fingerprint": getattr(
            gate_result, "historical_recipe_fingerprint", None
        ),
    }


def _provider_identity(
    turns: Sequence[object],
    label: str,
    *,
    declared_model: str,
    declared_profile: str,
) -> tuple[str, str]:
    if not turns:
        return declared_model, declared_profile
    models: set[str] = set()
    profiles: set[str] = set()
    for turn in turns:
        metadata = getattr(turn, "provider_metadata", None)
        if not isinstance(metadata, Mapping):
            raise ValueError(f"{label} provider metadata is invalid")
        model = metadata.get("model_identity")
        profile = metadata.get("profile_identity")
        if not isinstance(model, str) or not model:
            raise ValueError(f"{label} model identity is required")
        if not isinstance(profile, str) or not profile:
            raise ValueError(f"{label} profile identity is required")
        models.add(model)
        profiles.add(profile)
    if len(models) != 1 or len(profiles) != 1:
        raise ValueError(f"{label} provider identity is not exact")
    model = next(iter(models))
    profile = next(iter(profiles))
    if model != declared_model or profile != declared_profile:
        raise ValueError(f"{label} provider identity does not match declared identity")
    return model, profile


def _verify_archive_checksums(archive_dir: Path) -> SealedPlannerCheckpointArchive:
    checksums_path = archive_dir / "checksums.json"
    try:
        checksums_raw = checksums_path.read_bytes()
        checksums = parse_strict_json(checksums_raw)
    except (OSError, ValueError) as exc:
        raise ValueError("sealed checkpoint archive checksums are unavailable") from exc
    if not isinstance(checksums, dict) or set(checksums) != {
        "schema",
        "records",
        "aggregate_identity",
    } or checksums.get("schema") != _CHECKPOINT_CHECKSUMS_SCHEMA:
        raise ValueError("sealed checkpoint archive checksum shape is invalid")
    records = checksums.get("records")
    aggregate_identity = checksums.get("aggregate_identity")
    if not isinstance(records, list) or not isinstance(aggregate_identity, str):
        raise ValueError("sealed checkpoint archive checksum values are invalid")
    paths: list[str] = []
    for record in records:
        if not isinstance(record, dict) or set(record) != {
            "role",
            "path",
            "raw_sha256",
            "byte_length",
        }:
            raise ValueError("sealed checkpoint archive checksum record is invalid")
        path_value = record["path"]
        if (
            not isinstance(path_value, str)
            or not path_value
            or Path(path_value).is_absolute()
            or ".." in Path(path_value).parts
        ):
            raise ValueError("sealed checkpoint archive checksum path is invalid")
        if not isinstance(record["role"], str) or not isinstance(
            record["raw_sha256"], str
        ) or not isinstance(record["byte_length"], int):
            raise ValueError("sealed checkpoint archive checksum value is invalid")
        paths.append(path_value)
    if paths != sorted(paths) or len(set(paths)) != len(paths):
        raise ValueError("sealed checkpoint archive checksum order is invalid")
    expected_aggregate = canonical_fingerprint(
        own_trusted_json(
            {
                "schema": _CHECKPOINT_CHECKSUMS_SCHEMA,
                "records": records,
            }
        )
    )
    if aggregate_identity != expected_aggregate:
        raise ValueError("sealed checkpoint archive aggregate identity is invalid")
    expected_files = set(paths) | {"checksums.json"}
    actual_files = {
        path.relative_to(archive_dir).as_posix()
        for path in archive_dir.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        raise ValueError("sealed checkpoint archive file set is invalid")
    for record in records:
        persisted = (archive_dir / record["path"]).read_bytes()
        if (
            sha256_prefixed(persisted) != record["raw_sha256"]
            or len(persisted) != record["byte_length"]
        ):
            raise ValueError(
                f"sealed checkpoint archive checksum mismatch: {record['path']}"
            )
    return SealedPlannerCheckpointArchive(
        archive_dir=archive_dir,
        aggregate_identity=aggregate_identity,
        checksums_raw_sha256=sha256_prefixed(checksums_raw),
    )


def verify_sealed_planner_checkpoint_archive(
    archive_dir: Path,
) -> SealedPlannerCheckpointArchive:
    """Verify a published Checkpoint 1 seal without changing it."""

    archive_dir = Path(archive_dir).resolve()
    if not archive_dir.is_dir():
        raise ValueError("sealed checkpoint archive directory is unavailable")
    return _verify_archive_checksums(archive_dir)


def seal_planner_checkpoint_archive(
    *,
    destination: Path,
    inputs: FrozenPlannerInputs,
    planner_request: RenderedRequest,
    planner_session: object,
    evaluator: object | None,
    evaluator_request: RenderedRequest | None,
    planner_provider_turns: Sequence[object],
    evaluator_provider_turns: Sequence[object],
    evaluator_elapsed_ms: int | None,
    classification: str,
    archive_identity: Mapping[str, object],
) -> SealedPlannerCheckpointArchive:
    """Persist complete Checkpoint 1 evidence through one no-overwrite rename."""

    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(f"sealed checkpoint archive already exists: {destination}")
    _verify_frozen_planner_inputs(inputs)
    if classification != derive_checkpoint_classification(planner_session, evaluator):
        raise ValueError("checkpoint classification is not mechanically derived")
    git_commit_sha = archive_identity.get("git_commit_sha")
    if (
        not isinstance(git_commit_sha, str)
        or len(git_commit_sha) != 40
        or any(character not in "0123456789abcdef" for character in git_commit_sha)
    ):
        raise ValueError("exact committed git SHA is required")
    planner_model_identity = archive_identity.get("planner_model_identity")
    evaluator_model_identity = archive_identity.get("evaluator_model_identity")
    provider_profile_identity = archive_identity.get("provider_profile_identity")
    if not all(
        isinstance(value, str) and value
        for value in (
            planner_model_identity,
            evaluator_model_identity,
            provider_profile_identity,
        )
    ):
        raise ValueError("exact model and profile identities are required")
    assert isinstance(planner_model_identity, str)
    assert isinstance(evaluator_model_identity, str)
    assert isinstance(provider_profile_identity, str)
    session_turns = tuple(getattr(planner_session, "turns", ()))
    if len(session_turns) != len(planner_provider_turns):
        raise ValueError("Planner turn archive is incomplete")
    for session_turn, provider_turn in zip(session_turns, planner_provider_turns):
        if (
            getattr(session_turn, "raw_response", None)
            != getattr(provider_turn, "raw_response", None)
            or getattr(session_turn, "tool_arguments", None)
            != _planner_tool_arguments(provider_turn)
            or getattr(session_turn, "usage", None)
            != getattr(provider_turn, "usage", None)
        ):
            raise ValueError("Planner turn archive does not match execution")
    if evaluator is not None and len(evaluator_provider_turns) != 1:
        raise ValueError("evaluator turn archive is incomplete")
    if evaluator is None and evaluator_provider_turns:
        raise ValueError("unexpected evaluator turn archive")
    temporary = destination.parent / f".{destination.name}.tmp-{uuid4().hex}"
    temporary.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, object]] = []
    try:
        input_records: list[dict[str, object]] = []
        for record in inputs.records:
            persisted = _archive_write(
                temporary,
                records,
                role=f"input:{record.role}",
                relative_path=f"inputs/{record.relative_path}",
                raw=record.raw_bytes,
            )
            input_records.append(
                {
                    "role": record.role,
                    "path": record.relative_path,
                    "raw_sha256": sha256_prefixed(persisted),
                    "canonical_fingerprint": record.canonical_fingerprint,
                }
            )
        _archive_write(
            temporary,
            records,
            role="inputs_manifest",
            relative_path="inputs/manifest.json",
            raw=_archive_json_bytes(
                {
                    "schema": "rook.lm9b_p.planner_input_manifest:v1",
                    "records": input_records,
                }
            ),
        )
        _archive_write(
            temporary,
            records,
            role="planner_request",
            relative_path="planner/request.json",
            raw=planner_request.raw_bytes,
        )
        for index, (session_turn, provider_turn) in enumerate(
            zip(session_turns, planner_provider_turns)
        ):
            prefix = f"planner/turns/{index:03d}"
            _archive_write(
                temporary,
                records,
                role=f"planner_turn:{index}:raw_request",
                relative_path=f"{prefix}/raw_request.bin",
                raw=getattr(provider_turn, "raw_request"),
            )
            _archive_write(
                temporary,
                records,
                role=f"planner_turn:{index}:raw_response",
                relative_path=f"{prefix}/raw_response.bin",
                raw=getattr(session_turn, "raw_response"),
            )
            tool_arguments = getattr(session_turn, "tool_arguments")
            _archive_write(
                temporary,
                records,
                role=f"planner_turn:{index}:tool_arguments",
                relative_path=f"{prefix}/tool_arguments.bin",
                raw=tool_arguments if tool_arguments is not None else b"",
            )
            _archive_write(
                temporary,
                records,
                role=f"planner_turn:{index}:feedback",
                relative_path=f"{prefix}/feedback.json",
                raw=_archive_json_bytes(_gate_feedback(getattr(session_turn, "gate_result"))),
            )
            _archive_write(
                temporary,
                records,
                role=f"planner_turn:{index}:usage",
                relative_path=f"{prefix}/usage.json",
                raw=_archive_json_bytes(getattr(session_turn, "usage")),
            )
            _archive_write(
                temporary,
                records,
                role=f"planner_turn:{index}:timing",
                relative_path=f"{prefix}/timing.json",
                raw=_archive_json_bytes(
                    {"elapsed_ms": getattr(session_turn, "elapsed_ms")}
                ),
            )
        final_recipe_bytes = getattr(planner_session, "final_recipe_bytes", None)
        if final_recipe_bytes is not None:
            persisted_recipe = _archive_write(
                temporary,
                records,
                role="planner_final_recipe",
                relative_path="planner/final_recipe.json",
                raw=final_recipe_bytes,
            )
            persisted_gate = evaluate_mechanical_gate(
                recipe_bytes=persisted_recipe,
                authority=inputs.authority,
                recipe_schema=inputs.recipe_schema,
                normalization_profile=inputs.authority.normalization_profile,
                exclusion_policy=inputs.exclusion_policy,
            )
            _archive_write(
                temporary,
                records,
                role="planner_final_recipe_identity",
                relative_path="planner/final_recipe_identity.json",
                raw=_archive_json_bytes(
                    {
                        "raw_sha256": sha256_prefixed(persisted_recipe),
                        "mechanical_status": persisted_gate.status,
                        "recipe_value_fingerprint": persisted_gate.recipe_value_fingerprint,
                        "ratified_recipe_fingerprint": persisted_gate.ratified_recipe_fingerprint,
                        "historical_recipe_fingerprint": persisted_gate.historical_recipe_fingerprint,
                    }
                ),
            )
        if evaluator_request is not None:
            _archive_write(
                temporary,
                records,
                role="evaluator_request",
                relative_path="evaluator/request.json",
                raw=evaluator_request.raw_bytes,
            )
        if evaluator is not None:
            evaluator_turn = evaluator_provider_turns[0]
            raw_response = getattr(evaluator, "raw_response", None)
            if raw_response != getattr(evaluator_turn, "raw_response", None):
                raise ValueError("evaluator response archive does not match execution")
            if raw_response is not None:
                _archive_write(
                    temporary,
                    records,
                    role="evaluator_raw_response",
                    relative_path="evaluator/raw_response.bin",
                    raw=raw_response,
                )
            _archive_write(
                temporary,
                records,
                role="evaluator_report",
                relative_path="evaluator/report.json",
                raw=_archive_json_bytes(
                    {
                        "termination": getattr(evaluator, "termination"),
                        "recommendation": getattr(evaluator, "recommendation"),
                        "evidence": getattr(evaluator, "evidence"),
                        "raw_response_sha256": (
                            sha256_prefixed(raw_response)
                            if raw_response is not None
                            else None
                        ),
                    }
                ),
            )
            _archive_write(
                temporary,
                records,
                role="evaluator_usage",
                relative_path="evaluator/usage.json",
                raw=_archive_json_bytes(
                    getattr(evaluator, "usage", None) or {"available": False}
                ),
            )
            _archive_write(
                temporary,
                records,
                role="evaluator_timing",
                relative_path="evaluator/timing.json",
                raw=_archive_json_bytes(
                    {
                        "elapsed_ms": evaluator_elapsed_ms,
                        "attempts": len(evaluator_provider_turns),
                    }
                ),
            )
        else:
            _archive_write(
                temporary,
                records,
                role="evaluator_not_run",
                relative_path="evaluator/not_run.json",
                raw=_archive_json_bytes({"status": "not_run"}),
            )
        _archive_write(
            temporary,
            records,
            role="checkpoint_classification",
            relative_path="checkpoint/classification.json",
            raw=_archive_json_bytes(
                {
                    "schema": _CHECKPOINT_CLASSIFICATION_SCHEMA,
                    "classification": classification,
                    "checkpoint_2": "not_evaluated",
                }
            ),
        )
        planner_model, planner_profile = _provider_identity(
            planner_provider_turns,
            "Planner",
            declared_model=planner_model_identity,
            declared_profile=provider_profile_identity,
        )
        evaluator_model, evaluator_profile = _provider_identity(
            evaluator_provider_turns,
            "evaluator",
            declared_model=evaluator_model_identity,
            declared_profile=provider_profile_identity,
        )
        if planner_profile != evaluator_profile:
            raise ValueError("provider profile identity mismatch")
        _archive_write(
            temporary,
            records,
            role="identity",
            relative_path="identity.json",
            raw=_archive_json_bytes(
                {
                    "schema": _CHECKPOINT_IDENTITY_SCHEMA,
                    "git_commit_sha": git_commit_sha,
                    "planner_model_identity": planner_model,
                    "evaluator_model_identity": evaluator_model,
                    "provider_profile_identity": planner_profile,
                    "normalization_profile_identity": {
                        "profile_id": inputs.authority.normalization_profile.profile_id,
                        "profile_fingerprint": inputs.authority.normalization_profile.profile_fingerprint,
                    },
                    "bounds": {
                        "planner_max_turns": PLANNER_MAX_TURNS,
                        "evaluator_max_attempts": 1,
                    },
                    "execution_permitted": False,
                }
            ),
        )
        ordered_records = sorted(records, key=lambda record: record["path"])
        checksums = {
            "schema": _CHECKPOINT_CHECKSUMS_SCHEMA,
            "records": ordered_records,
            "aggregate_identity": canonical_fingerprint(
                own_trusted_json(
                    {
                        "schema": _CHECKPOINT_CHECKSUMS_SCHEMA,
                        "records": ordered_records,
                    }
                )
            ),
        }
        checksums_path = temporary / "checksums.json"
        checksums_path.write_bytes(_archive_json_bytes(checksums))
        _verify_archive_checksums(temporary)
        if destination.exists():
            raise FileExistsError(
                f"sealed checkpoint archive already exists: {destination}"
            )
        temporary.rename(destination)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return verify_sealed_planner_checkpoint_archive(destination)


def _planner_tool_arguments(provider_turn: object) -> bytes | None:
    assistant_message = getattr(provider_turn, "assistant_message", None)
    if not isinstance(assistant_message, Mapping):
        return None
    calls = assistant_message.get("tool_calls")
    if not isinstance(calls, list) or not calls:
        return None
    first = calls[0]
    if not isinstance(first, Mapping):
        return None
    function = first.get("function")
    if not isinstance(function, Mapping):
        return None
    arguments = function.get("arguments")
    return arguments.encode("utf-8") if isinstance(arguments, str) else None


def compare_sealed_checkpoint_with_r01(
    *,
    archive_dir: Path,
    sealed_aggregate_identity: str,
    r01_recipe_path: Path,
) -> Mapping[str, object]:
    """Compare R01 only after independently verifying an immutable checkpoint seal."""

    sealed = verify_sealed_planner_checkpoint_archive(archive_dir)
    if sealed.aggregate_identity != sealed_aggregate_identity:
        raise ValueError("sealed aggregate identity does not match verified archive")
    recipe_path = sealed.archive_dir / "planner" / "final_recipe.json"
    try:
        persisted_recipe = recipe_path.read_bytes()
    except OSError as exc:
        raise ValueError("sealed checkpoint archive has no final recipe") from exc
    r01_bytes = Path(r01_recipe_path).read_bytes()
    return MappingProxyType(
        {
            "sealed_aggregate_identity": sealed.aggregate_identity,
            "sealed_recipe_raw_sha256": sha256_prefixed(persisted_recipe),
            "r01_raw_sha256": sha256_prefixed(r01_bytes),
            "raw_bytes_match": persisted_recipe == r01_bytes,
        }
    )


__all__ = (
    "FrozenPlannerAuthority",
    "FrozenPlannerInputs",
    "Lm9bcHandoff",
    "PlannerInputRecord",
    "RenderedRequest",
    "SealedPlannerCheckpointArchive",
    "build_lm9bc_handoff",
    "compare_sealed_checkpoint_with_r01",
    "derive_checkpoint_classification",
    "load_planner_authority_context",
    "load_planner_inputs",
    "render_planner_evaluator_request",
    "render_planner_request",
    "seal_planner_checkpoint_archive",
    "verify_sealed_planner_checkpoint_archive",
)
