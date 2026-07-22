"""Frozen authority loading and matched-control-free LM9B-C handoff for LM9B-P."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
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
    PLANNER_EVALUATION_RECOMMENDATION_MEANINGS,
    PLANNER_EVALUATION_REPORT_SCHEMA,
    PLANNER_MAX_TURNS,
    ProviderTurn,
    evaluate_mechanical_gate,
    fingerprint,
    fingerprint_without,
    load_normalization_profile,
    normalization_profile_from_value,
    parse_archive_json,
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


_JOIN_PROOF_TOKEN = object()


@dataclass(frozen=True)
class VerifiedPlannerCheckpointJoin:
    checkpoint_archive: SealedPlannerCheckpointArchive
    planner_inputs: FrozenPlannerInputs
    gate_result: MechanicalGateResult
    final_recipe_bytes: bytes
    final_recipe_raw_sha256: str
    recipe_value_fingerprint: str
    ratified_recipe_fingerprint: str
    historical_recipe_fingerprint: str
    planner_records: tuple[PlannerInputRecord, ...]
    record_identities: tuple[tuple[str, str, str, str], ...]
    _verified_checkpoint_archive: SealedPlannerCheckpointArchive = field(
        repr=False, compare=False
    )
    _verified_planner_inputs: FrozenPlannerInputs = field(repr=False, compare=False)
    _verified_gate_result: MechanicalGateResult = field(repr=False, compare=False)
    _verified_final_recipe_bytes: bytes = field(repr=False, compare=False)
    _verification_token: object = field(repr=False, compare=False)


@dataclass(frozen=True)
class SealedJoinedAggregate:
    archive_dir: Path
    aggregate_identity: str
    checksums_raw_sha256: str


@dataclass
class ProviderAttemptEvidence:
    """Probe-bound provider attempt snapshot, including an invocation that raises."""

    provider_request_bytes: bytes
    outcome: str = "pending"
    provider_turn: object | None = None
    exception_type: str | None = None
    exception_message: str | None = None
    failure_type: str | None = None
    raw_request: bytes | None = None
    raw_error: bytes | None = None
    elapsed_ms: int | None = None

    def record_return(self, provider_turn: object, started_at: float) -> None:
        self.outcome = "returned"
        self.provider_turn = provider_turn
        self.elapsed_ms = max(0, int((time.perf_counter() - started_at) * 1000))

    def record_exception(self, exception: BaseException, started_at: float) -> None:
        self.outcome = "raised"
        self.exception_type = type(exception).__name__
        self.exception_message = str(exception)
        exception_class = type(exception)
        transport_request = getattr(exception, "raw_request", None)
        transport_error = getattr(exception, "raw_error", None)
        if (
            exception_class.__module__ == "lm9b_c_compiler_sufficiency_support"
            and exception_class.__name__ == "ProviderCallFailure"
            and type(getattr(exception, "failure_type", None)) is str
            and type(getattr(exception, "message", None)) is str
            and type(transport_request) is bytes
            and type(transport_error) is bytes
        ):
            self.failure_type = getattr(exception, "failure_type")
            self.raw_request = transport_request
            self.raw_error = transport_error
        self.elapsed_ms = max(0, int((time.perf_counter() - started_at) * 1000))


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
        # Descriptor-language visibility (LM9B-P closure M1/M2/M3/M4): the accepted
        # descriptor kind vocabulary, kind->schema pairing, reserved source_task
        # identity, and the identifier/policy-pointer grammars are declared here so
        # the Planner receives them. Mirrored by the recipe schema; enforced by the
        # unchanged mechanical gate.
        "source_task_artifact_kind": "task_envelope",
        "source_task_schema": "rook.planner_task_envelope:v1",
        "authority_artifact_kinds": ["environment_snapshot", "planning_policy"],
        "descriptor_kind_schema": {
            "environment_snapshot": "rook.environment_snapshot:v1",
            "planning_policy": "rook.planning_policy:v1",
            "task_envelope": "rook.planner_task_envelope:v1",
        },
        "machine_identifier_pattern": "^[a-z0-9]+(?:[._:-][a-z0-9]+)*$",
        "policy_pointer_pattern": "^/rules/[a-z0-9]+(?:[._:-][a-z0-9]+)*$",
    }
    if _thaw_json(value.get("language_boundary")) != expected_boundary:
        raise ValueError("authoring contract language boundary mismatch")
    # Pin the complete relational-invariant statements too. M1/M5/M6 are carried
    # here (not expressible in JSON Schema), so a self-consistent fingerprint must
    # not be able to silently remove a model-visible rule.
    expected_invariants = [
        "Every clause has direct source, assumption, or permitted derived-fact support, or a non-null clause-appropriate synthesis.",
        "Nested canonicalization applies only to its containing maintains clause.",
        "Nested canonicalization and postconditions may inherit only from their containing maintains clause.",
        "Descriptor artifact IDs are globally unique across source_task and authority_artifacts; identifiers are unique within each declaration namespace.",
        "The reserved artifact ID task_envelope appears only as source_task and never in authority_artifacts.",
        "Every recipe-bound authority descriptor is referenced by recipe content.",
        "Every local semantic reference resolves to a declared symbol of its declared kind.",
    ]
    if _thaw_json(value.get("relational_invariants")) != expected_invariants:
        raise ValueError("authoring contract relational invariants mismatch")


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
    # Semantic-only vocabulary (authority split): the evaluator judges fidelity;
    # blocked-vs-ready is derived deterministically from recipe state.
    if _thaw_json(value.get("recommendations")) != [
        "evaluation_inconclusive",
        "semantically_faithful",
        "semantically_unfaithful",
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
        # Report-contract visibility: the exact closed schema the parser
        # validates with, rendered from its single source of truth, plus the
        # recommendation meanings (which state that readiness is derived by
        # the system, not judged by the evaluator).
        "evaluation_report_contract": {
            "argument": "evaluation_json",
            "report_schema": PLANNER_EVALUATION_REPORT_SCHEMA,
            "recommendation_meanings": PLANNER_EVALUATION_RECOMMENDATION_MEANINGS,
        },
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


def verify_ready_checkpoint_for_join(
    *,
    checkpoint_archive: SealedPlannerCheckpointArchive,
    checkpoint_classification: str,
    planner_inputs: FrozenPlannerInputs,
    gate_result: MechanicalGateResult,
    final_recipe_bytes: bytes,
) -> VerifiedPlannerCheckpointJoin:
    """Issue the proof carried from a retained, sealed ready Checkpoint 1."""

    if type(checkpoint_archive) is not SealedPlannerCheckpointArchive:
        raise TypeError("sealed Checkpoint 1 archive is required")
    verified_archive = verify_sealed_planner_checkpoint_archive(
        checkpoint_archive.archive_dir,
        expected_aggregate_identity=checkpoint_archive.aggregate_identity,
    )
    if verified_archive != checkpoint_archive:
        raise ValueError("retained Checkpoint 1 seal identity mismatch")
    if checkpoint_classification != "probe_candidate_ready":
        raise ValueError("only a ready Checkpoint 1 can produce a join proof")
    if type(planner_inputs) is not FrozenPlannerInputs:
        raise TypeError("exact frozen Planner inputs are required")
    if type(gate_result) is not MechanicalGateResult:
        raise ValueError("exact accepted gate result is required")
    if (
        gate_result.status != "mechanically_accepted"
        or gate_result.diagnostics != ()
        or type(final_recipe_bytes) is not bytes
        or gate_result.final_recipe_bytes is not final_recipe_bytes
        or not all(
            isinstance(value, str) and value.startswith("sha256:")
            for value in (
                gate_result.recipe_value_fingerprint,
                gate_result.ratified_recipe_fingerprint,
                gate_result.historical_recipe_fingerprint,
            )
        )
    ):
        raise ValueError("exact accepted gate result is required")

    classification = _archive_object(
        verified_archive.archive_dir / "checkpoint/classification.json",
        "classification",
    )
    if (
        classification.get("classification") != checkpoint_classification
        or classification.get("checkpoint_2") != "not_evaluated"
    ):
        raise ValueError("ready Checkpoint 1 classification is not bound to its seal")

    records = _verify_frozen_planner_inputs(planner_inputs)
    manifest = _archive_object(
        verified_archive.archive_dir / "inputs/manifest.json",
        "Planner input manifest",
    )
    expected_manifest_records = [
        {
            "role": record.role,
            "path": record.relative_path,
            "raw_sha256": record.raw_sha256,
            "canonical_fingerprint": record.canonical_fingerprint,
        }
        for record in planner_inputs.records
    ]
    if (
        manifest.get("schema") != "rook.lm9b_p.planner_input_manifest:v1"
        or manifest.get("records") != expected_manifest_records
    ):
        raise ValueError("frozen Planner inputs are not bound to the retained seal")
    for record in planner_inputs.records:
        archived = (
            verified_archive.archive_dir / "inputs" / record.relative_path
        ).read_bytes()
        if archived != record.raw_bytes:
            raise ValueError(f"sealed Planner input byte mismatch: {record.role}")

    archived_recipe = (
        verified_archive.archive_dir / "planner/final_recipe.json"
    ).read_bytes()
    recipe_identity = _archive_object(
        verified_archive.archive_dir / "planner/final_recipe_identity.json",
        "final recipe identity",
    )
    expected_recipe_identity = {
        "raw_sha256": sha256_prefixed(final_recipe_bytes),
        "mechanical_status": gate_result.status,
        "recipe_value_fingerprint": gate_result.recipe_value_fingerprint,
        "ratified_recipe_fingerprint": gate_result.ratified_recipe_fingerprint,
        "historical_recipe_fingerprint": gate_result.historical_recipe_fingerprint,
    }
    if archived_recipe != final_recipe_bytes or recipe_identity != expected_recipe_identity:
        raise ValueError("accepted recipe authority is not bound to the retained seal")

    ordered_records = tuple(records[role] for role, _, _ in _PLANNER_INPUT_FILES)
    return VerifiedPlannerCheckpointJoin(
        checkpoint_archive=verified_archive,
        planner_inputs=planner_inputs,
        gate_result=gate_result,
        final_recipe_bytes=final_recipe_bytes,
        final_recipe_raw_sha256=expected_recipe_identity["raw_sha256"],
        recipe_value_fingerprint=gate_result.recipe_value_fingerprint,
        ratified_recipe_fingerprint=gate_result.ratified_recipe_fingerprint,
        historical_recipe_fingerprint=gate_result.historical_recipe_fingerprint,
        planner_records=ordered_records,
        record_identities=tuple(
            (
                record.role,
                record.relative_path,
                record.raw_sha256,
                record.canonical_fingerprint,
            )
            for record in ordered_records
        ),
        _verified_checkpoint_archive=verified_archive,
        _verified_planner_inputs=planner_inputs,
        _verified_gate_result=gate_result,
        _verified_final_recipe_bytes=final_recipe_bytes,
        _verification_token=_JOIN_PROOF_TOKEN,
    )


def _checked_join_proof(
    proof: VerifiedPlannerCheckpointJoin,
) -> tuple[MechanicalGateResult, Mapping[str, PlannerInputRecord]]:
    if (
        type(proof) is not VerifiedPlannerCheckpointJoin
        or proof._verification_token is not _JOIN_PROOF_TOKEN
    ):
        raise ValueError("verified ready Checkpoint 1 join proof is required")
    if type(proof.checkpoint_archive) is not SealedPlannerCheckpointArchive:
        raise ValueError("verified ready Checkpoint 1 join proof is invalid")
    if proof.checkpoint_archive is not proof._verified_checkpoint_archive:
        raise ValueError("verified ready Checkpoint 1 join proof is invalid")
    gate = proof.gate_result
    if (
        type(gate) is not MechanicalGateResult
        or gate.status != "mechanically_accepted"
        or gate.diagnostics != ()
        or proof.planner_inputs is not proof._verified_planner_inputs
        or gate is not proof._verified_gate_result
        or type(proof.final_recipe_bytes) is not bytes
        or proof.final_recipe_bytes is not proof._verified_final_recipe_bytes
        or gate.final_recipe_bytes is not proof.final_recipe_bytes
        or proof.final_recipe_raw_sha256
        != sha256_prefixed(proof.final_recipe_bytes)
        or gate.recipe_value_fingerprint != proof.recipe_value_fingerprint
        or gate.ratified_recipe_fingerprint
        != proof.ratified_recipe_fingerprint
        or gate.historical_recipe_fingerprint
        != proof.historical_recipe_fingerprint
    ):
        raise ValueError("verified ready Checkpoint 1 join proof is invalid")
    archived_recipe = (
        proof.checkpoint_archive.archive_dir / "planner/final_recipe.json"
    ).read_bytes()
    if archived_recipe != proof.final_recipe_bytes:
        raise ValueError("verified ready Checkpoint 1 recipe bytes changed")
    if len(proof.planner_records) != len(proof.planner_inputs.records) or any(
        proof_record is not input_record
        for proof_record, input_record in zip(
            proof.planner_records, proof.planner_inputs.records
        )
    ):
        raise ValueError("verified ready Checkpoint 1 record identity changed")
    identities = tuple(
        (
            record.role,
            record.relative_path,
            record.raw_sha256,
            record.canonical_fingerprint,
        )
        for record in proof.planner_records
    )
    if identities != proof.record_identities:
        raise ValueError("verified ready Checkpoint 1 record identity changed")
    records: dict[str, PlannerInputRecord] = {}
    for record in proof.planner_records:
        if (
            type(record) is not PlannerInputRecord
            or record.role in records
            or record.raw_sha256 != sha256_prefixed(record.raw_bytes)
            or (
                proof.checkpoint_archive.archive_dir
                / "inputs"
                / record.relative_path
            ).read_bytes()
            != record.raw_bytes
        ):
            raise ValueError("verified ready Checkpoint 1 record identity changed")
        records[record.role] = record
    if tuple(records) != tuple(role for role, _, _ in _PLANNER_INPUT_FILES):
        raise ValueError("verified ready Checkpoint 1 record identity changed")
    return gate, MappingProxyType(records)


def build_lm9bc_handoff(
    *,
    join_proof: VerifiedPlannerCheckpointJoin,
    compiler_fixture_dir: Path,
    destination: Path,
) -> Lm9bcHandoff:
    """Build the LM9B-C boundary without reading matched-control inputs."""

    compiler_fixture_dir = Path(compiler_fixture_dir).resolve()
    destination = Path(destination).resolve()

    accepted_result, planner_records = _checked_join_proof(join_proof)
    accepted_recipe_bytes = accepted_result.final_recipe_bytes
    assert accepted_recipe_bytes is not None
    planner_inputs = join_proof.planner_inputs

    task_record = planner_records["authority.task_envelope"]
    environment_record = planner_records["authority.environment_snapshot"]
    policy_record = planner_records["authority.planning_policy"]

    destination.mkdir(parents=True, exist_ok=False)

    rows = (
        (
            "recipe",
            "accepted_recipe.json",
            accepted_recipe_bytes,
            accepted_result.recipe_value_fingerprint,
        ),
        ("authority.task_envelope", "task_envelope.json", task_record.raw_bytes, None),
        ("authority.environment_snapshot", "environment_snapshot.json", environment_record.raw_bytes, None),
        ("authority.planning_policy", "planning_policy.json", policy_record.raw_bytes, None),
        ("implementation_context", "implementation_context.json", (compiler_fixture_dir / "implementation_context.json").read_bytes(), None),
        ("exclusion_policy", "exclusion_policy.json", (compiler_fixture_dir / "exclusion_policy.json").read_bytes(), None),
        ("evaluation_rubric", "evaluation_rubric.json", (compiler_fixture_dir / "evaluation_rubric.json").read_bytes(), None),
    )
    records: list[dict[str, object]] = []
    for role, filename, raw, known_canonical_fingerprint in rows:
        path = destination / filename
        _write_bytes(path, raw)
        persisted = path.read_bytes()
        if persisted != raw:
            raise ValueError(f"handoff write verification failed: {role}")
        canonical = known_canonical_fingerprint
        if canonical is None:
            value = parse_strict_json(persisted)
            if not isinstance(value, dict):
                raise ValueError(f"handoff record is not an object: {role}")
            canonical = canonical_fingerprint(own_trusted_json(value))
        records.append(
            {
                "role": role,
                "path": filename,
                "raw_sha256": sha256_prefixed(persisted),
                "canonical_fingerprint": canonical,
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


def derive_probe_explicit_blockers(final_recipe_bytes: bytes) -> tuple[str, ...]:
    """Deterministic explicit-blocker projection for this workerless probe.

    Authority limit: the only blocker this probe can deterministically
    establish is ``unresolved_intent_present``, read from the mechanically
    accepted recipe's explicit ``unresolved_intent`` collection. It does NOT
    establish that policy, capability, selection, or authorization blockers
    are absent - that requires LM9A-S. Accordingly ``probe_candidate_ready``
    means eligibility for the inert compiler experiment only, never product
    compile readiness. The output vocabulary is closed to this single value.
    """

    recipe = parse_strict_json(final_recipe_bytes)
    if not isinstance(recipe, dict):
        raise ValueError("accepted recipe bytes must decode to an object")
    unresolved = recipe.get("unresolved_intent")
    if not isinstance(unresolved, list):
        raise ValueError(
            "accepted recipe must carry an explicit unresolved_intent collection"
        )
    return ("unresolved_intent_present",) if unresolved else ()


def derive_checkpoint_classification(
    planner_session: object,
    evaluator: object | None,
    *,
    checkpoint_gate: object | None = None,
) -> str:
    """Derive the sole Checkpoint 1 classification from captured outcomes.

    Authority split: the evaluator model establishes semantic fidelity ONLY.
    Advancement (blocked vs ready) is derived deterministically from the
    mechanically accepted artifact - bound to ``checkpoint_gate``, the
    checkpoint's INDEPENDENT reevaluation of the final bytes under the frozen
    checkpoint inputs. This is the proof carrier: classification and sealing
    must consume it, proving the archived result was accepted under the exact
    frozen inputs being archived - never merely the session-loop result, and
    never the model's recommendation.
    """

    termination = getattr(planner_session, "termination", None)
    if termination == "mechanically_rejected":
        return "probe_mechanically_rejected"
    if termination != "mechanically_accepted" or evaluator is None:
        return "probe_inconclusive"
    if getattr(evaluator, "termination", None) != "valid_recommendation":
        return "probe_inconclusive"
    if type(checkpoint_gate) is not MechanicalGateResult:
        raise ValueError(
            "checkpoint gate result is required to classify an accepted session"
        )
    if checkpoint_gate.status != "mechanically_accepted":
        raise ValueError("checkpoint gate result did not accept the final recipe")
    gate_final_bytes = checkpoint_gate.final_recipe_bytes
    if not isinstance(gate_final_bytes, bytes) or gate_final_bytes != getattr(
        planner_session, "final_recipe_bytes", None
    ):
        # Integrity/control failure: the checkpoint gate's accepted bytes must
        # be the session's final bytes. Never resolved as a classification.
        raise ValueError(
            "checkpoint gate bytes do not match the session final recipe"
        )
    accepted_results = [
        gate_result
        for turn in getattr(planner_session, "turns", ())
        if (gate_result := getattr(turn, "gate_result", None)) is not None
        and getattr(gate_result, "status", None) == "mechanically_accepted"
    ]
    if len(accepted_results) != 1:
        raise ValueError(
            "accepted session must retain exactly one accepted gate result"
        )
    if checkpoint_gate != accepted_results[0]:
        # The independent checkpoint reevaluation must agree exactly with the
        # session's accepted gate result; divergence is a control failure.
        raise ValueError(
            "checkpoint gate result does not match the accepted turn gate result"
        )
    recommendation = getattr(evaluator, "recommendation", None)
    if recommendation == "semantically_unfaithful":
        return "probe_planner_failure"
    if recommendation == "evaluation_inconclusive":
        return "probe_inconclusive"
    if recommendation != "semantically_faithful":
        raise ValueError("invalid evaluator recommendation for checkpoint")
    blockers = derive_probe_explicit_blockers(gate_final_bytes)
    return "probe_candidate_blocked" if blockers else "probe_candidate_ready"


def derive_joined_aggregate_outcome(
    *,
    checkpoint_1_classification: str,
    checkpoint_2_outcome: str,
    compiler_session: object | None = None,
    evaluator_result: object | None = None,
) -> str:
    """Attribute the joined result without promoting compiler-stage failures."""

    if checkpoint_1_classification != "probe_candidate_ready":
        if checkpoint_2_outcome != "not_evaluated":
            raise ValueError("non-ready Checkpoint 1 must leave Checkpoint 2 unevaluated")
        return checkpoint_1_classification

    if checkpoint_2_outcome == "not_evaluated":
        raise ValueError("ready Checkpoint 1 requires a Checkpoint 2 outcome")
    terminal = getattr(compiler_session, "terminal_submission", None)
    validation = getattr(compiler_session, "terminal_validation", None)
    result_kind = terminal.get("result_kind") if isinstance(terminal, Mapping) else None

    if checkpoint_2_outcome == "bounded_lowering_demonstrated":
        if result_kind != "compiled_candidate":
            raise ValueError("bounded lowering requires an explicit compiled candidate")
        return "joined_transfer_demonstrated"
    if checkpoint_2_outcome == "contract_gap_demonstrated":
        report = getattr(evaluator_result, "report", None)
        explicit_gap = (
            result_kind == "contract_insufficient"
            and validation is not None
            and getattr(validation, "schema_valid", None) is True
            and getattr(validation, "trace_valid", None) is True
            and isinstance(report, Mapping)
            and report.get("evaluated_result_kind") == "contract_insufficient"
            and report.get("decision") == "accepted"
            and isinstance(report.get("contract_gap_assessment"), Mapping)
            and all(report["contract_gap_assessment"].values())
        )
        return "contract_gap_demonstrated" if explicit_gap else "candidate_failure"
    if checkpoint_2_outcome == "candidate_failure":
        return "candidate_failure"
    if checkpoint_2_outcome == "inconclusive":
        turns = getattr(compiler_session, "turns", ())
        if (
            getattr(compiler_session, "stop_reason", None) == "max_turns_exhausted"
            and turns
            and all(getattr(turn, "feedback_codes", ()) for turn in turns)
        ):
            return "candidate_failure"
        return "inconclusive"
    raise ValueError("invalid Checkpoint 2 outcome")


def _archive_json_bytes(value: object) -> bytes:
    # allow_nan=False so the archive writer refuses to persist non-finite
    # numbers; the archive readback (parse_archive_json) admits only finite
    # floats, keeping the write and read contracts symmetric.
    return (
        json.dumps(
            _thaw_json(value),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
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


def _content_addressed_tree(root: Path) -> Mapping[str, object]:
    root = Path(root).resolve()
    records = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        raw = path.read_bytes()
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "raw_sha256": sha256_prefixed(raw),
                "byte_length": len(raw),
            }
        )
    if not records:
        raise ValueError("LM9B-C evidence archive is empty")
    identity = canonical_fingerprint(
        own_trusted_json(
            {
                "schema": "rook.lm9b_p.external_archive_binding:v1",
                "records": records,
            }
        )
    )
    return MappingProxyType(
        {
            "schema": "rook.lm9b_p.external_archive_binding:v1",
            "aggregate_identity": identity,
            "records": tuple(MappingProxyType(record) for record in records),
        }
    )


def seal_joined_aggregate(
    *,
    destination: Path,
    checkpoint_1_archive: SealedPlannerCheckpointArchive,
    checkpoint_1_classification: str,
    checkpoint_2_outcome: str,
    checkpoint_2_reason_codes: Sequence[str],
    aggregate_outcome: str,
    handoff: Lm9bcHandoff | None,
    planner_recipe_bytes: bytes | None,
    lm9bc_loaded_recipe_bytes: bytes | None,
    lm9bc_run_dir: Path | None,
    pre_session_failure: Mapping[str, object] | None,
) -> SealedJoinedAggregate:
    """Atomically bind both checkpoint archives and the exact recipe bytes."""

    verified_checkpoint = verify_sealed_planner_checkpoint_archive(
        checkpoint_1_archive.archive_dir,
        expected_aggregate_identity=checkpoint_1_archive.aggregate_identity,
    )
    destination = Path(destination).resolve()
    temporary = destination.with_name(f".{destination.name}.tmp-{uuid4().hex}")
    temporary.mkdir(parents=True, exist_ok=False)
    try:
        evidence_recipe_bytes = None
        lm9bc_archive = None
        if lm9bc_run_dir is not None:
            run_dir = Path(lm9bc_run_dir).resolve()
            evidence_recipe_bytes = (run_dir / "inputs" / "recipe.json").read_bytes()
            lm9bc_archive = _content_addressed_tree(run_dir)

        recipe_values = (
            planner_recipe_bytes,
            handoff.archived_recipe_bytes if handoff is not None else None,
            lm9bc_loaded_recipe_bytes,
            evidence_recipe_bytes,
        )
        complete_recipe_proof = all(type(value) is bytes for value in recipe_values)
        all_equal = complete_recipe_proof and len(set(recipe_values)) == 1
        if lm9bc_run_dir is not None and not all_equal:
            raise ValueError("joined recipe byte equality failed")
        recipe_hashes = [
            sha256_prefixed(value) if type(value) is bytes else None
            for value in recipe_values
        ]
        aggregate = {
            "schema": "rook.lm9b_p.joined_aggregate:v1",
            "checkpoint_1": {
                "classification": checkpoint_1_classification,
                "aggregate_identity": verified_checkpoint.aggregate_identity,
            },
            "checkpoint_2": {
                "outcome": checkpoint_2_outcome,
                "reason_codes": list(checkpoint_2_reason_codes),
            },
            "aggregate_outcome": aggregate_outcome,
            "handoff": (
                {
                    "manifest_raw_sha256": handoff.manifest_raw_sha256,
                    "manifest_canonical_fingerprint": handoff.manifest_canonical_fingerprint,
                    "compiler_renderer_id": handoff.compiler_renderer_id,
                    "attempt_context_fingerprint": handoff.attempt_context_fingerprint,
                }
                if handoff is not None
                else None
            ),
            "recipe_byte_equality": {
                "planner_final_raw_sha256": recipe_hashes[0],
                "handoff_archive_raw_sha256": recipe_hashes[1],
                "lm9b_c_loaded_raw_sha256": recipe_hashes[2],
                "lm9b_c_evidence_raw_sha256": recipe_hashes[3],
                "all_equal": all_equal,
            },
            "compiler_visible_input": {
                "renderer_id": (
                    handoff.compiler_renderer_id if handoff is not None else None
                ),
                "raw_recipe_bytes_consumed_by_model": False,
                "projection": [
                    "parsed_rendered_recipe_projection",
                    "legal_trace_reference_catalog",
                    "terminal_result_schema",
                ],
            },
            "pre_session_failure": (
                dict(pre_session_failure) if pre_session_failure is not None else None
            ),
            "lm9b_c_archive": _thaw_json(lm9bc_archive),
            "execution_permitted": False,
        }
        aggregate_raw = _archive_json_bytes(aggregate)
        aggregate_path = temporary / "aggregate.json"
        aggregate_path.write_bytes(aggregate_raw)
        if aggregate_path.read_bytes() != aggregate_raw:
            raise ValueError("joined aggregate write verification failed")
        records = [
            {
                "path": "aggregate.json",
                "raw_sha256": sha256_prefixed(aggregate_raw),
                "byte_length": len(aggregate_raw),
            }
        ]
        aggregate_identity = canonical_fingerprint(
            own_trusted_json(
                {
                    "schema": "rook.lm9b_p.joined_aggregate_checksums:v1",
                    "records": records,
                }
            )
        )
        checksums = {
            "schema": "rook.lm9b_p.joined_aggregate_checksums:v1",
            "records": records,
            "aggregate_identity": aggregate_identity,
        }
        checksums_raw = _archive_json_bytes(checksums)
        checksums_path = temporary / "checksums.json"
        checksums_path.write_bytes(checksums_raw)
        if checksums_path.read_bytes() != checksums_raw:
            raise ValueError("joined aggregate checksums write verification failed")
        if destination.exists():
            raise FileExistsError(f"sealed joined aggregate already exists: {destination}")
        temporary.rename(destination)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return SealedJoinedAggregate(
        archive_dir=destination,
        aggregate_identity=aggregate_identity,
        checksums_raw_sha256=sha256_prefixed(checksums_raw),
    )


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


def _checked_out_git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parent,
        check=True,
        capture_output=True,
        text=True,
    )
    head = completed.stdout.strip()
    if len(head) != 40 or any(character not in "0123456789abcdef" for character in head):
        raise ValueError("checked-out HEAD is not a commit SHA")
    return head


def _attempt_snapshot(attempt: ProviderAttemptEvidence) -> Mapping[str, object]:
    outcome = attempt.outcome
    if outcome not in {"pending", "raised", "returned"}:
        raise ValueError("provider attempt outcome is invalid")
    turn = attempt.provider_turn if outcome == "returned" else None
    raw_request = (
        attempt.raw_request if outcome == "raised" else getattr(turn, "raw_request", None)
    )
    raw_response = getattr(turn, "raw_response", None)
    raw_error = attempt.raw_error if outcome == "raised" else None
    usage = getattr(turn, "usage", None)
    provider_metadata = getattr(turn, "provider_metadata", None)
    message = getattr(turn, "assistant_message", None)
    arguments: list[tuple[int, bytes]] = []
    if isinstance(message, Mapping):
        calls = message.get("tool_calls")
        if isinstance(calls, list):
            for index, call in enumerate(calls):
                if not isinstance(call, Mapping):
                    continue
                function = call.get("function")
                if not isinstance(function, Mapping):
                    continue
                value = function.get("arguments")
                if isinstance(value, str):
                    try:
                        arguments.append((index, value.encode("utf-8", errors="strict")))
                    except UnicodeError as exc:
                        raise ValueError("provider tool arguments are not UTF-8") from exc
    return MappingProxyType(
        {
            "outcome": outcome,
            "provider_request_bytes": attempt.provider_request_bytes,
            "raw_request": raw_request if isinstance(raw_request, bytes) else None,
            "raw_response": raw_response if isinstance(raw_response, bytes) else None,
            "raw_error": raw_error if isinstance(raw_error, bytes) else None,
            "usage": dict(usage) if isinstance(usage, Mapping) else None,
            "provider_metadata": (
                _freeze_json(dict(provider_metadata))
                if isinstance(provider_metadata, Mapping)
                else None
            ),
            "tool_arguments": tuple(arguments),
            "exception_type": attempt.exception_type,
            "exception_message": attempt.exception_message,
            "failure_type": attempt.failure_type,
            "elapsed_ms": attempt.elapsed_ms,
            "provider_turn": turn,
        }
    )


def _write_attempt(
    root: Path,
    records: list[dict[str, object]],
    *,
    phase: str,
    index: int,
    snapshot: Mapping[str, object],
) -> None:
    prefix = f"{phase}/attempts/{index:03d}"
    arguments = snapshot["tool_arguments"]
    assert isinstance(arguments, tuple)
    argument_indexes = [item[0] for item in arguments]
    capture = {
        "schema": "rook.lm9b_p.provider_attempt:v1",
        "outcome": snapshot["outcome"],
        "elapsed_ms": snapshot["elapsed_ms"],
        "exception_type": snapshot["exception_type"],
        "exception_message": snapshot["exception_message"],
        "failure_type": snapshot["failure_type"],
        "has_raw_request": snapshot["raw_request"] is not None,
        "has_raw_response": snapshot["raw_response"] is not None,
        "has_raw_error": snapshot["raw_error"] is not None,
        "has_usage": snapshot["usage"] is not None,
        "provider_metadata": snapshot["provider_metadata"],
        "tool_argument_indexes": argument_indexes,
    }
    _archive_write(
        root, records, role=f"{phase}_attempt:{index}:capture",
        relative_path=f"{prefix}/capture.json", raw=_archive_json_bytes(capture)
    )
    _archive_write(
        root, records, role=f"{phase}_attempt:{index}:provider_request",
        relative_path=f"{prefix}/provider_request.json",
        raw=snapshot["provider_request_bytes"],
    )
    for field, filename in (
        ("raw_request", "raw_request.bin"),
        ("raw_response", "raw_response.bin"),
        ("raw_error", "raw_error.bin"),
    ):
        raw = snapshot[field]
        if raw is not None:
            assert isinstance(raw, bytes)
            _archive_write(
                root, records, role=f"{phase}_attempt:{index}:{field}",
                relative_path=f"{prefix}/{filename}", raw=raw
            )
    usage = snapshot["usage"]
    if usage is not None:
        _archive_write(
            root, records, role=f"{phase}_attempt:{index}:usage",
            relative_path=f"{prefix}/usage.json", raw=_archive_json_bytes(usage)
        )
    for tool_index, raw in arguments:
        _archive_write(
            root, records, role=f"{phase}_attempt:{index}:tool_arguments:{tool_index}",
            relative_path=f"{prefix}/tool_arguments/{tool_index:03d}.bin", raw=raw
        )


def _archive_object(path: Path, label: str) -> Mapping[str, object]:
    try:
        value = parse_archive_json(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise ValueError(f"sealed checkpoint archive {label} is unavailable") from exc
    if not isinstance(value, dict):
        raise ValueError(f"sealed checkpoint archive {label} is invalid")
    return value


def _expected_attempt_records(
    archive_dir: Path, phase: str, index: int
) -> Mapping[str, str]:
    prefix = f"{phase}/attempts/{index:03d}"
    capture = _archive_object(archive_dir / f"{prefix}/capture.json", "attempt capture")
    required = {
        "schema", "outcome", "elapsed_ms", "exception_type", "exception_message",
        "failure_type", "has_raw_request", "has_raw_response", "has_raw_error",
        "has_usage", "provider_metadata", "tool_argument_indexes",
    }
    if set(capture) != required or capture["schema"] != "rook.lm9b_p.provider_attempt:v1":
        raise ValueError("sealed checkpoint archive attempt capture shape is invalid")
    outcome = capture["outcome"]
    if outcome not in {"pending", "raised", "returned"} or not isinstance(capture["tool_argument_indexes"], list):
        raise ValueError("sealed checkpoint archive attempt capture values are invalid")
    indexes = capture["tool_argument_indexes"]
    if (
        any(type(item) is not int or item < 0 for item in indexes)
        or indexes != sorted(set(indexes))
    ):
        raise ValueError("sealed checkpoint archive tool argument order is invalid")
    elapsed_ms = capture["elapsed_ms"]
    if outcome == "pending":
        if elapsed_ms is not None:
            raise ValueError("sealed checkpoint archive pending attempt has timing evidence")
    elif type(elapsed_ms) is not int or elapsed_ms < 0:
        raise ValueError("sealed checkpoint archive completed attempt timing is invalid")
    expected = {
        f"{prefix}/capture.json": f"{phase}_attempt:{index}:capture",
        f"{prefix}/provider_request.json": f"{phase}_attempt:{index}:provider_request",
    }
    for field, filename in (
        ("has_raw_request", "raw_request.bin"),
        ("has_raw_response", "raw_response.bin"),
        ("has_raw_error", "raw_error.bin"),
    ):
        if type(capture[field]) is not bool:
            raise ValueError("sealed checkpoint archive attempt flag is invalid")
        if capture[field]:
            expected[f"{prefix}/{filename}"] = f"{phase}_attempt:{index}:{field[4:]}"
    if type(capture["has_usage"]) is not bool:
        raise ValueError("sealed checkpoint archive attempt usage flag is invalid")
    if capture["has_usage"]:
        expected[f"{prefix}/usage.json"] = f"{phase}_attempt:{index}:usage"
    for tool_index in indexes:
        expected[f"{prefix}/tool_arguments/{tool_index:03d}.bin"] = (
            f"{phase}_attempt:{index}:tool_arguments:{tool_index}"
        )
    if outcome == "raised" and (
        not isinstance(capture["exception_type"], str)
        or not isinstance(capture["exception_message"], str)
    ):
        raise ValueError("sealed checkpoint archive raised attempt lacks exception evidence")
    if outcome != "raised" and (
        capture["exception_type"] is not None
        or capture["exception_message"] is not None
    ):
        raise ValueError("sealed checkpoint archive non-failure has exception evidence")
    if outcome == "returned" and not isinstance(capture["provider_metadata"], dict):
        raise ValueError("sealed checkpoint archive returned attempt lacks provider metadata")
    if outcome == "raised":
        has_transport_failure = capture["failure_type"] is not None
        if has_transport_failure and (
            not isinstance(capture["failure_type"], str)
            or capture["exception_type"] != "ProviderCallFailure"
            or not capture["has_raw_request"]
            or not capture["has_raw_error"]
        ):
            raise ValueError("sealed checkpoint archive transport failure evidence is invalid")
        if not has_transport_failure and (
            capture["has_raw_request"] or capture["has_raw_error"]
        ):
            raise ValueError("sealed checkpoint archive generic failure has transport evidence")
        if capture["has_raw_response"] or capture["has_usage"]:
            raise ValueError("sealed checkpoint archive failed attempt has returned evidence")
    elif capture["failure_type"] is not None or capture["has_raw_error"]:
        raise ValueError("sealed checkpoint archive non-failure has transport failure evidence")
    if outcome == "pending" and any(
        capture[field] for field in ("has_raw_request", "has_raw_response", "has_raw_error", "has_usage")
    ):
        raise ValueError("sealed checkpoint archive pending attempt has provider evidence")
    if outcome != "returned" and capture["provider_metadata"] is not None:
        raise ValueError("sealed checkpoint archive failed attempt has returned metadata")
    return MappingProxyType(expected)


def _trusted_attempt_records(
    phase: str, index: int, snapshot: Mapping[str, object]
) -> Mapping[str, str]:
    prefix = f"{phase}/attempts/{index:03d}"
    expected = {
        f"{prefix}/capture.json": f"{phase}_attempt:{index}:capture",
        f"{prefix}/provider_request.json": f"{phase}_attempt:{index}:provider_request",
    }
    for field, filename in (
        ("raw_request", "raw_request.bin"),
        ("raw_response", "raw_response.bin"),
        ("raw_error", "raw_error.bin"),
    ):
        if snapshot[field] is not None:
            expected[f"{prefix}/{filename}"] = f"{phase}_attempt:{index}:{field}"
    if snapshot["usage"] is not None:
        expected[f"{prefix}/usage.json"] = f"{phase}_attempt:{index}:usage"
    for tool_index, _ in snapshot["tool_arguments"]:
        expected[f"{prefix}/tool_arguments/{tool_index:03d}.bin"] = (
            f"{phase}_attempt:{index}:tool_arguments:{tool_index}"
        )
    return MappingProxyType(expected)


def _provider_identity(
    snapshots: Sequence[Mapping[str, object]],
    *,
    label: str,
    declared_model: str,
    declared_profile: str,
) -> None:
    for snapshot in snapshots:
        turn = snapshot["provider_turn"]
        if not isinstance(turn, ProviderTurn):
            continue
        metadata = snapshot["provider_metadata"]
        if not isinstance(metadata, Mapping):
            raise ValueError(f"{label} provider identity is unavailable")
        if (
            metadata.get("model_identity") != declared_model
            or metadata.get("profile_identity") != declared_profile
        ):
            raise ValueError(f"{label} provider identity does not match declared identity")


def _trusted_archive_records(
    *,
    inputs: FrozenPlannerInputs,
    planner_session: object,
    evaluator: object | None,
    classification: str,
    planner_attempts: Sequence[Mapping[str, object]],
    evaluator_attempts: Sequence[Mapping[str, object]],
    checkpoint_gate: object | None = None,
) -> Mapping[str, str]:
    planner_termination = getattr(planner_session, "termination", None)
    session_turns = tuple(getattr(planner_session, "turns", ()))
    final_recipe = getattr(planner_session, "final_recipe_bytes", None)
    evaluator_termination = getattr(evaluator, "termination", "not_run")
    if classification != derive_checkpoint_classification(
        planner_session, evaluator, checkpoint_gate=checkpoint_gate
    ):
        raise ValueError("checkpoint classification is not mechanically derived")
    if len(session_turns) > len(planner_attempts):
        raise ValueError("Planner turn archive is incomplete")
    if planner_termination == "mechanically_accepted":
        if not isinstance(final_recipe, bytes) or evaluator is None or len(evaluator_attempts) != 1:
            raise ValueError("accepted checkpoint archive shape is invalid")
    elif final_recipe is not None or evaluator is not None or evaluator_attempts:
        raise ValueError("non-accepted checkpoint archive shape is invalid")
    if classification in {"probe_candidate_ready", "probe_candidate_blocked"} and (
        not session_turns or planner_termination != "mechanically_accepted" or not isinstance(final_recipe, bytes) or evaluator_termination != "valid_recommendation"
    ):
        raise ValueError("candidate checkpoint archive evidence is incomplete")
    if evaluator is not None and evaluator_termination != "valid_recommendation" and classification != "probe_inconclusive":
        raise ValueError("evaluator failure classification is invalid")
    expected: dict[str, str] = {
        **{f"inputs/{filename}": f"input:{role}" for role, filename, _ in _PLANNER_INPUT_FILES},
        "inputs/manifest.json": "inputs_manifest",
        "planner/request.json": "planner_request",
        "checkpoint/classification.json": "checkpoint_classification",
        "checkpoint/session.json": "checkpoint_session",
        "identity.json": "identity",
    }
    for index in range(len(session_turns)):
        prefix = f"planner/turns/{index:03d}"
        expected.update({
            f"{prefix}/raw_response.bin": f"planner_turn:{index}:raw_response",
            f"{prefix}/feedback.json": f"planner_turn:{index}:feedback",
            f"{prefix}/usage.json": f"planner_turn:{index}:usage",
            f"{prefix}/timing.json": f"planner_turn:{index}:timing",
        })
    for index, snapshot in enumerate(planner_attempts):
        expected.update(_trusted_attempt_records("planner", index, snapshot))
    if planner_termination == "mechanically_accepted":
        expected.update({
            "planner/final_recipe.json": "planner_final_recipe",
            "planner/final_recipe_identity.json": "planner_final_recipe_identity",
            "evaluator/request.json": "evaluator_request",
            "evaluator/report.json": "evaluator_report",
            "evaluator/usage.json": "evaluator_usage",
            "evaluator/timing.json": "evaluator_timing",
        })
        for index, snapshot in enumerate(evaluator_attempts):
            expected.update(_trusted_attempt_records("evaluator", index, snapshot))
        if evaluator_attempts[0]["raw_response"] is not None:
            expected["evaluator/raw_response.bin"] = "evaluator_raw_response"
    else:
        expected["evaluator/not_run.json"] = "evaluator_not_run"
    return MappingProxyType(expected)


def _closed_archive_records(archive_dir: Path) -> Mapping[str, str]:
    session = _archive_object(archive_dir / "checkpoint/session.json", "session")
    if set(session) != {"schema", "planner", "evaluator"} or session["schema"] != "rook.lm9b_p.checkpoint_session:v1":
        raise ValueError("sealed checkpoint archive session shape is invalid")
    planner = session["planner"]
    evaluator = session["evaluator"]
    if not isinstance(planner, dict) or not isinstance(evaluator, dict):
        raise ValueError("sealed checkpoint archive session values are invalid")
    if set(planner) != {"termination", "turn_count", "attempt_count"} or set(evaluator) != {"termination", "attempt_count"}:
        raise ValueError("sealed checkpoint archive session cardinality is invalid")
    planner_termination = planner["termination"]
    evaluator_termination = evaluator["termination"]
    turn_count = planner["turn_count"]
    planner_attempt_count = planner["attempt_count"]
    evaluator_attempt_count = evaluator["attempt_count"]
    if (
        planner_termination not in {"mechanically_accepted", "mechanically_rejected", "provider_failure", "timeout"}
        or evaluator_termination not in {"not_run", "valid_recommendation", "provider_failure", "timeout", "malformed"}
        or any(type(value) is not int or value < 0 for value in (turn_count, planner_attempt_count, evaluator_attempt_count))
        or turn_count > planner_attempt_count
    ):
        raise ValueError("sealed checkpoint archive session values are invalid")
    expected: dict[str, str] = {
        **{f"inputs/{filename}": f"input:{role}" for role, filename, _ in _PLANNER_INPUT_FILES},
        "inputs/manifest.json": "inputs_manifest",
        "planner/request.json": "planner_request",
        "checkpoint/classification.json": "checkpoint_classification",
        "checkpoint/session.json": "checkpoint_session",
        "identity.json": "identity",
    }
    for index in range(turn_count):
        prefix = f"planner/turns/{index:03d}"
        expected.update({
            f"{prefix}/raw_response.bin": f"planner_turn:{index}:raw_response",
            f"{prefix}/feedback.json": f"planner_turn:{index}:feedback",
            f"{prefix}/usage.json": f"planner_turn:{index}:usage",
            f"{prefix}/timing.json": f"planner_turn:{index}:timing",
        })
    for index in range(planner_attempt_count):
        expected.update(_expected_attempt_records(archive_dir, "planner", index))
    if planner_termination == "mechanically_accepted":
        if evaluator_termination == "not_run" or evaluator_attempt_count != 1:
            raise ValueError("sealed checkpoint archive accepted evaluator shape is invalid")
        expected.update({
            "planner/final_recipe.json": "planner_final_recipe",
            "planner/final_recipe_identity.json": "planner_final_recipe_identity",
            "evaluator/request.json": "evaluator_request",
            "evaluator/report.json": "evaluator_report",
            "evaluator/usage.json": "evaluator_usage",
            "evaluator/timing.json": "evaluator_timing",
        })
        capture = _archive_object(archive_dir / "evaluator/attempts/000/capture.json", "evaluator attempt capture")
        if capture.get("has_raw_response"):
            expected["evaluator/raw_response.bin"] = "evaluator_raw_response"
        for index in range(evaluator_attempt_count):
            expected.update(_expected_attempt_records(archive_dir, "evaluator", index))
    else:
        if evaluator_termination != "not_run" or evaluator_attempt_count != 0:
            raise ValueError("sealed checkpoint archive no-evaluator shape is invalid")
        expected["evaluator/not_run.json"] = "evaluator_not_run"
    classification = _archive_object(archive_dir / "checkpoint/classification.json", "classification")
    if set(classification) != {"schema", "classification", "checkpoint_2"} or classification["schema"] != _CHECKPOINT_CLASSIFICATION_SCHEMA or classification["checkpoint_2"] != "not_evaluated":
        raise ValueError("sealed checkpoint archive classification shape is invalid")
    expected_classification = (
        "probe_mechanically_rejected" if planner_termination == "mechanically_rejected"
        else "probe_inconclusive" if planner_termination != "mechanically_accepted" or evaluator_termination != "valid_recommendation"
        else None
    )
    if expected_classification is not None:
        if classification["classification"] != expected_classification:
            raise ValueError("sealed checkpoint archive classification is invalid")
    elif classification["classification"] not in {"probe_candidate_blocked", "probe_planner_failure", "probe_candidate_ready"}:
        raise ValueError("sealed checkpoint archive evaluator classification is invalid")
    return MappingProxyType(expected)


def _verify_archive_checksums(
    archive_dir: Path,
    *,
    expected_aggregate_identity: str | None = None,
    trusted_records: Mapping[str, str] | None = None,
) -> SealedPlannerCheckpointArchive:
    checksums_path = archive_dir / "checksums.json"
    checksums = _archive_object(checksums_path, "checksums")
    if set(checksums) != {"schema", "records", "aggregate_identity"} or checksums["schema"] != _CHECKPOINT_CHECKSUMS_SCHEMA:
        raise ValueError("sealed checkpoint archive checksum shape is invalid")
    records = checksums["records"]
    if not isinstance(records, list) or not isinstance(checksums["aggregate_identity"], str):
        raise ValueError("sealed checkpoint archive checksum values are invalid")
    expected = trusted_records or _closed_archive_records(archive_dir)
    by_path: dict[str, Mapping[str, object]] = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != {"role", "path", "raw_sha256", "byte_length"}:
            raise ValueError("sealed checkpoint archive checksum record is invalid")
        path = record["path"]
        if not isinstance(path, str) or path in by_path:
            raise ValueError("sealed checkpoint archive checksum path is invalid")
        by_path[path] = record
    if list(by_path) != sorted(by_path) or set(by_path) != set(expected):
        raise ValueError("sealed checkpoint archive required record closure is invalid")
    actual_files = {path.relative_to(archive_dir).as_posix() for path in archive_dir.rglob("*") if path.is_file()}
    if actual_files != set(expected) | {"checksums.json"}:
        raise ValueError("sealed checkpoint archive file set is invalid")
    for path, role in expected.items():
        record = by_path[path]
        persisted = (archive_dir / path).read_bytes()
        if record["role"] != role or record["raw_sha256"] != sha256_prefixed(persisted) or record["byte_length"] != len(persisted):
            raise ValueError(f"sealed checkpoint archive checksum mismatch: {path}")
    expected_aggregate = canonical_fingerprint(own_trusted_json({"schema": _CHECKPOINT_CHECKSUMS_SCHEMA, "records": records}))
    if checksums["aggregate_identity"] != expected_aggregate:
        raise ValueError("sealed checkpoint archive aggregate identity is invalid")
    if (
        expected_aggregate_identity is not None
        and checksums["aggregate_identity"] != expected_aggregate_identity
    ):
        raise ValueError("sealed checkpoint archive aggregate identity does not match retained seal")
    return SealedPlannerCheckpointArchive(archive_dir, checksums["aggregate_identity"], sha256_prefixed(checksums_path.read_bytes()))


def verify_sealed_planner_checkpoint_archive(
    archive_dir: Path,
    *,
    expected_aggregate_identity: str,
) -> SealedPlannerCheckpointArchive:
    archive_dir = Path(archive_dir).resolve()
    if not archive_dir.is_dir():
        raise ValueError("sealed checkpoint archive directory is unavailable")
    if not isinstance(expected_aggregate_identity, str):
        raise ValueError("retained sealed aggregate identity is required")
    return _verify_archive_checksums(
        archive_dir,
        expected_aggregate_identity=expected_aggregate_identity,
    )


def seal_planner_checkpoint_archive(
    *, destination: Path, inputs: FrozenPlannerInputs, planner_request: RenderedRequest,
    planner_session: object, evaluator: object | None, evaluator_request: RenderedRequest | None,
    planner_provider_attempts: Sequence[ProviderAttemptEvidence], evaluator_provider_attempts: Sequence[ProviderAttemptEvidence],
    evaluator_elapsed_ms: int | None, classification: str, archive_identity: Mapping[str, object],
    checkpoint_gate: object | None = None,
) -> SealedPlannerCheckpointArchive:
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(f"sealed checkpoint archive already exists: {destination}")
    _verify_frozen_planner_inputs(inputs)
    if classification != derive_checkpoint_classification(
        planner_session, evaluator, checkpoint_gate=checkpoint_gate
    ):
        raise ValueError("checkpoint classification is not mechanically derived")
    head = _checked_out_git_head()
    if archive_identity.get("git_commit_sha") != head:
        raise ValueError("archive git SHA does not match checked-out HEAD")
    planner_model = archive_identity.get("planner_model_identity")
    evaluator_model = archive_identity.get("evaluator_model_identity")
    profile = archive_identity.get("provider_profile_identity")
    if not all(isinstance(value, str) and value for value in (planner_model, evaluator_model, profile)):
        raise ValueError("exact model and profile identities are required")
    assert isinstance(planner_model, str) and isinstance(evaluator_model, str) and isinstance(profile, str)
    planner_attempts = tuple(_attempt_snapshot(item) for item in planner_provider_attempts)
    evaluator_attempts = tuple(_attempt_snapshot(item) for item in evaluator_provider_attempts)
    _provider_identity(
        planner_attempts,
        label="Planner",
        declared_model=planner_model,
        declared_profile=profile,
    )
    _provider_identity(
        evaluator_attempts,
        label="evaluator",
        declared_model=evaluator_model,
        declared_profile=profile,
    )
    trusted_records = _trusted_archive_records(
        inputs=inputs,
        planner_session=planner_session,
        evaluator=evaluator,
        classification=classification,
        planner_attempts=planner_attempts,
        evaluator_attempts=evaluator_attempts,
        checkpoint_gate=checkpoint_gate,
    )
    session_turns = tuple(getattr(planner_session, "turns", ()))
    returned_planner = tuple(item for item in planner_attempts if item["raw_response"] is not None)
    if len(session_turns) > len(returned_planner):
        raise ValueError("Planner turn archive is incomplete")
    for turn, attempt in zip(session_turns, returned_planner):
        if getattr(turn, "raw_response", None) != attempt["raw_response"] or getattr(turn, "usage", None) != attempt["usage"]:
            raise ValueError("Planner turn archive does not match execution")
    if evaluator is not None and len(evaluator_attempts) != 1:
        raise ValueError("evaluator attempt archive is incomplete")
    if evaluator is None and evaluator_attempts:
        raise ValueError("unexpected evaluator attempt archive")
    temporary = destination.parent / f".{destination.name}.tmp-{uuid4().hex}"
    temporary.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, object]] = []
    try:
        input_records = []
        for record in inputs.records:
            persisted = _archive_write(temporary, records, role=f"input:{record.role}", relative_path=f"inputs/{record.relative_path}", raw=record.raw_bytes)
            input_records.append({"role": record.role, "path": record.relative_path, "raw_sha256": sha256_prefixed(persisted), "canonical_fingerprint": record.canonical_fingerprint})
        _archive_write(temporary, records, role="inputs_manifest", relative_path="inputs/manifest.json", raw=_archive_json_bytes({"schema": "rook.lm9b_p.planner_input_manifest:v1", "records": input_records}))
        _archive_write(temporary, records, role="planner_request", relative_path="planner/request.json", raw=planner_request.raw_bytes)
        for index, turn in enumerate(session_turns):
            prefix = f"planner/turns/{index:03d}"
            for role, path, raw in (
                ("raw_response", f"{prefix}/raw_response.bin", getattr(turn, "raw_response")),
                ("feedback", f"{prefix}/feedback.json", _archive_json_bytes(_gate_feedback(getattr(turn, "gate_result")))),
                ("usage", f"{prefix}/usage.json", _archive_json_bytes(getattr(turn, "usage"))),
                ("timing", f"{prefix}/timing.json", _archive_json_bytes({"elapsed_ms": getattr(turn, "elapsed_ms")})),
            ):
                _archive_write(temporary, records, role=f"planner_turn:{index}:{role}", relative_path=path, raw=raw)
        for index, attempt in enumerate(planner_attempts):
            _write_attempt(temporary, records, phase="planner", index=index, snapshot=attempt)
        final_recipe = getattr(planner_session, "final_recipe_bytes", None)
        if final_recipe is not None:
            persisted = _archive_write(temporary, records, role="planner_final_recipe", relative_path="planner/final_recipe.json", raw=final_recipe)
            gate = evaluate_mechanical_gate(recipe_bytes=persisted, authority=inputs.authority, recipe_schema=inputs.recipe_schema, normalization_profile=inputs.authority.normalization_profile, exclusion_policy=inputs.exclusion_policy)
            _archive_write(temporary, records, role="planner_final_recipe_identity", relative_path="planner/final_recipe_identity.json", raw=_archive_json_bytes({"raw_sha256": sha256_prefixed(persisted), "mechanical_status": gate.status, "recipe_value_fingerprint": gate.recipe_value_fingerprint, "ratified_recipe_fingerprint": gate.ratified_recipe_fingerprint, "historical_recipe_fingerprint": gate.historical_recipe_fingerprint}))
        if evaluator is None:
            _archive_write(temporary, records, role="evaluator_not_run", relative_path="evaluator/not_run.json", raw=_archive_json_bytes({"status": "not_run"}))
        else:
            if evaluator_request is None:
                raise ValueError("evaluator request archive is incomplete")
            _archive_write(temporary, records, role="evaluator_request", relative_path="evaluator/request.json", raw=evaluator_request.raw_bytes)
            raw_response = getattr(evaluator, "raw_response", None)
            if raw_response is not None:
                _archive_write(temporary, records, role="evaluator_raw_response", relative_path="evaluator/raw_response.bin", raw=raw_response)
            _archive_write(temporary, records, role="evaluator_report", relative_path="evaluator/report.json", raw=_archive_json_bytes({"termination": getattr(evaluator, "termination"), "recommendation": getattr(evaluator, "recommendation"), "evidence": getattr(evaluator, "evidence"), "raw_response_sha256": sha256_prefixed(raw_response) if raw_response is not None else None}))
            _archive_write(temporary, records, role="evaluator_usage", relative_path="evaluator/usage.json", raw=_archive_json_bytes(getattr(evaluator, "usage", None) or {"available": False}))
            _archive_write(temporary, records, role="evaluator_timing", relative_path="evaluator/timing.json", raw=_archive_json_bytes({"elapsed_ms": evaluator_elapsed_ms, "attempts": len(evaluator_attempts)}))
            for index, attempt in enumerate(evaluator_attempts):
                _write_attempt(temporary, records, phase="evaluator", index=index, snapshot=attempt)
        _archive_write(temporary, records, role="checkpoint_classification", relative_path="checkpoint/classification.json", raw=_archive_json_bytes({"schema": _CHECKPOINT_CLASSIFICATION_SCHEMA, "classification": classification, "checkpoint_2": "not_evaluated"}))
        _archive_write(temporary, records, role="checkpoint_session", relative_path="checkpoint/session.json", raw=_archive_json_bytes({"schema": "rook.lm9b_p.checkpoint_session:v1", "planner": {"termination": getattr(planner_session, "termination"), "turn_count": len(session_turns), "attempt_count": len(planner_attempts)}, "evaluator": {"termination": getattr(evaluator, "termination", "not_run") if evaluator is not None else "not_run", "attempt_count": len(evaluator_attempts)}}))
        _archive_write(temporary, records, role="identity", relative_path="identity.json", raw=_archive_json_bytes({"schema": _CHECKPOINT_IDENTITY_SCHEMA, "git_commit_sha": head, "planner_model_identity": planner_model, "evaluator_model_identity": evaluator_model, "provider_profile_identity": profile, "normalization_profile_identity": {"profile_id": inputs.authority.normalization_profile.profile_id, "profile_fingerprint": inputs.authority.normalization_profile.profile_fingerprint}, "bounds": {"planner_max_turns": PLANNER_MAX_TURNS, "evaluator_max_attempts": 1}, "execution_permitted": False}))
        ordered = sorted(records, key=lambda record: record["path"])
        checksums = {"schema": _CHECKPOINT_CHECKSUMS_SCHEMA, "records": ordered, "aggregate_identity": canonical_fingerprint(own_trusted_json({"schema": _CHECKPOINT_CHECKSUMS_SCHEMA, "records": ordered}))}
        (temporary / "checksums.json").write_bytes(_archive_json_bytes(checksums))
        _verify_archive_checksums(temporary, trusted_records=trusted_records)
        if destination.exists():
            raise FileExistsError(f"sealed checkpoint archive already exists: {destination}")
        temporary.rename(destination)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return verify_sealed_planner_checkpoint_archive(
        destination,
        expected_aggregate_identity=checksums["aggregate_identity"],
    )


def compare_sealed_checkpoint_with_r01(
    *,
    archive_dir: Path,
    sealed_aggregate_identity: str,
    r01_recipe_path: Path,
) -> Mapping[str, object]:
    """Compare R01 only after binding the archive to its retained sealed aggregate."""

    sealed = verify_sealed_planner_checkpoint_archive(
        archive_dir,
        expected_aggregate_identity=sealed_aggregate_identity,
    )
    try:
        persisted_recipe = (sealed.archive_dir / "planner" / "final_recipe.json").read_bytes()
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
    "ProviderAttemptEvidence",
    "RenderedRequest",
    "SealedJoinedAggregate",
    "SealedPlannerCheckpointArchive",
    "VerifiedPlannerCheckpointJoin",
    "build_lm9bc_handoff",
    "compare_sealed_checkpoint_with_r01",
    "derive_checkpoint_classification",
    "derive_probe_explicit_blockers",
    "derive_joined_aggregate_outcome",
    "load_planner_authority_context",
    "load_planner_inputs",
    "render_planner_evaluator_request",
    "render_planner_request",
    "seal_joined_aggregate",
    "seal_planner_checkpoint_archive",
    "verify_sealed_planner_checkpoint_archive",
    "verify_ready_checkpoint_for_join",
)
