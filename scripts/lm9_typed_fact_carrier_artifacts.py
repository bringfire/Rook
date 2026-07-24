"""Probe-owned composition for LM9 task-local typed-fact evidence."""

from __future__ import annotations

import copy
import json
import pickle
import re
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _import_path in (_SCRIPTS_DIR, _MCP_SRC):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

import lm9_semantic_typed_values as TYPED_VALUES
import lm9b_p_evaluator_only_continuation_artifacts as CONT_ARTIFACTS
import lm9b_p_planner_recipe_transfer_artifacts as PLANNER_ARTIFACTS
import lm9b_p_planner_recipe_transfer_support as SUPPORT


CONTRACTS_DIR = _SCRIPTS_DIR / "lm9_typed_fact_carrier_contracts"
FIXTURES_DIR = _SCRIPTS_DIR / "lm9_typed_fact_carrier_fixtures"
REGISTRY_PATH = CONTRACTS_DIR / "semantic_value_schema_registry.json"
PAYLOAD_SCHEMA_PATH = (
    CONTRACTS_DIR / "planner_task_typed_facts_payload_schema.json"
)
RADIAL_FIXTURE_PATH = FIXTURES_DIR / "radial_successor_task_envelope.json"
ANNOTATION_FIXTURE_PATH = FIXTURES_DIR / "annotation_task_envelope.json"
HISTORICAL_TASK_PAYLOAD_SCHEMA_ID = "rook.lm9b_c.r01_task_payload:v1"
HISTORICAL_TASK_PAYLOAD_SCHEMA_FINGERPRINT = (
    "sha256:a644b6f928ae82fa206e5ad6f303abc0787409457ebd16add636024472a09507"
)
OFFICIAL_DERIVATIVE = Path(
    r"C:\Users\bring\rook-lm9b-p-attempts"
    r"\2026-07-22-evaluator-only-continuation"
    r"\derivatives\visibility-evaluator-01"
)
OFFICIAL_DERIVATIVE_IDENTITY = (
    "sha256:48bcdcb36fb3ccee49fe358335f577ffabcb83b0f74e9f84d96951d6b3950b94"
)
_ENVELOPE_FIELDS = {
    "schema",
    "artifact_id",
    "task_session_id",
    "payload_schema",
    "payload_schema_fingerprint",
    "payload",
    "value_bindings",
    "issued_at",
    "artifact_fingerprint",
}
_BINDING_FIELDS = {
    "binding_id",
    "json_pointer",
    "semantic_key",
    "value_schema",
    "typed_value_fingerprint",
    "authority_kind",
    "provenance",
}
_PROVENANCE_FIELDS = {"issuer_kind", "issuer_id"}
_MACHINE_KEY = re.compile(TYPED_VALUES.MACHINE_KEY_PATTERN)


def _freeze(value: object) -> object:
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _json_bytes(value: object) -> bytes:
    return TYPED_VALUES.canonical_json_bytes(value) + b"\n"


def _record_by_role(
    source: CONT_ARTIFACTS.VerifiedHistoricalSource,
) -> dict[str, PLANNER_ARTIFACTS.PlannerInputRecord]:
    return {record.role: record for record in source.input_records}


def _require_exact_historical_source(
    source: CONT_ARTIFACTS.VerifiedHistoricalSource,
) -> CONT_ARTIFACTS.VerifiedHistoricalSource:
    if type(source) is not CONT_ARTIFACTS.VerifiedHistoricalSource:
        raise TypeError("exact verified historical source is required")
    expected = CONT_ARTIFACTS.verify_historical_source()
    if source != expected:
        raise ValueError("historical source differs from production-pinned evidence")
    return expected


def frozen_gate_inputs(
    source: CONT_ARTIFACTS.VerifiedHistoricalSource,
) -> PLANNER_ARTIFACTS.FrozenPlannerInputs:
    """Rebuild gate inputs with the sole already-ratified rubric migration."""

    replacement = PLANNER_ARTIFACTS.planner_input_record_from_bytes(
        role="evaluation_rubric",
        relative_path="planner_evaluation_rubric.json",
        raw_bytes=CONT_ARTIFACTS.CORRECTED_RUBRIC_PATH.read_bytes(),
    )
    records: list[PLANNER_ARTIFACTS.PlannerInputRecord] = []
    replaced = 0
    for archived in source.input_records:
        if archived.role == "evaluation_rubric":
            if archived.raw_bytes == replacement.raw_bytes:
                raise ValueError("historical and corrected evaluator rubrics are identical")
            records.append(replacement)
            replaced += 1
        else:
            records.append(archived)
    if replaced != 1:
        raise ValueError("gate input migration did not replace exactly one rubric")
    return PLANNER_ARTIFACTS.frozen_planner_inputs_from_records(
        records,
        source_dir=source.source_root / "checkpoint-1" / "inputs",
    )


def _verified_registry(
    raw_bytes: bytes, runtime: TYPED_VALUES.RuntimeIdentity
) -> TYPED_VALUES.VerifiedSemanticValueRegistry:
    if (
        type(raw_bytes) is not bytes
        or len(raw_bytes) > TYPED_VALUES.MAX_REGISTRY_BYTES
    ):
        raise ValueError("semantic-value registry byte limit exceeded")
    value = TYPED_VALUES.parse_strict_json(raw_bytes, label="semantic-value registry")
    if type(value) is not dict:
        raise ValueError("semantic-value registry must be an object")
    return TYPED_VALUES.verify_semantic_value_registry(
        value, raw_registry_byte_count=len(raw_bytes), runtime=runtime
    )


def _admitted_payload_schema(
    raw_bytes: bytes, runtime: TYPED_VALUES.RuntimeIdentity
) -> TYPED_VALUES.AdmittedSchema:
    value = TYPED_VALUES.parse_strict_json(raw_bytes, label="task payload schema")
    if type(value) is not dict:
        raise ValueError("task payload schema must be an object")
    admitted = TYPED_VALUES.admit_schema_document(
        value, profile=TYPED_VALUES.build_profile_identity(runtime)
    )
    if admitted.schema_id != TYPED_VALUES.FORWARD_PAYLOAD_SCHEMA_ID:
        raise ValueError("forward task-payload schema identity mismatch")
    return admitted


@dataclass(frozen=True)
class VerifiedForwardTaskEnvelope:
    envelope: Mapping[str, object]
    facts: Mapping[str, TYPED_VALUES.VerifiedTypedValue]
    bindings: Mapping[str, Mapping[str, object]]
    artifact_fingerprint: str


@dataclass(frozen=True)
class AuthorityPartition:
    parent_keys: tuple[str, ...]
    successor_keys: tuple[str, ...]
    migration_keys: tuple[str, ...]
    authority_delta_keys: tuple[str, ...]
    required_delta_keys: tuple[str, ...]
    partition_fingerprint: str


@dataclass(frozen=True)
class OutcomeNeutralParentWitness:
    source_manifest_raw_sha256: str
    recipe_raw_sha256: str
    recipe_fingerprint: str
    typed_value_validation_fingerprint: str
    mechanical_gate_status: str
    unresolved_keys: tuple[str, ...]
    derivative_archive_identity: str
    evaluator_recommendation: str
    classification: str
    witness_fingerprint: str


@dataclass(frozen=True)
class ControlCompatibilityWitness:
    fixture_path: str
    recipe_raw_sha256: str
    assumption_count: int
    derived_fact_count: int
    gate_status: str
    typed_value_validation_fingerprint: str


@dataclass(frozen=True)
class NegativeCaseResult:
    case_id: str
    status: str
    evidence_fingerprint: str


def validate_forward_task_envelope(
    raw_bytes: bytes,
    *,
    payload_schema_raw_bytes: bytes,
    registry_raw_bytes: bytes,
    unit_context_index: TYPED_VALUES.VerifiedUnitContextIndex,
    runtime: TYPED_VALUES.RuntimeIdentity,
) -> VerifiedForwardTaskEnvelope:
    if type(raw_bytes) is not bytes or len(raw_bytes) > TYPED_VALUES.MAX_ENVELOPE_BYTES:
        raise ValueError("forward task-envelope byte limit exceeded")
    envelope = TYPED_VALUES.parse_strict_json(raw_bytes, label="forward task envelope")
    if type(envelope) is not dict or set(envelope) != _ENVELOPE_FIELDS:
        raise ValueError("forward task-envelope shape is invalid")
    if (
        envelope["schema"] != "rook.planner_task_envelope:v1"
        or envelope["artifact_id"] != "task_envelope"
        or type(envelope["task_session_id"]) is not str
        or not envelope["task_session_id"]
        or envelope["payload_schema"] != TYPED_VALUES.FORWARD_PAYLOAD_SCHEMA_ID
    ):
        raise ValueError("forward task-envelope identity is invalid")
    verified_context = TYPED_VALUES._consume_unit_context_index(
        unit_context_index
    )
    bound_task_sessions = {
        entry.task_session_id for entry in verified_context.entries.values()
    }
    if bound_task_sessions != {envelope["task_session_id"]}:
        raise ValueError("forward task session differs from verified authority")
    registry = _verified_registry(registry_raw_bytes, runtime)
    payload_schema = _admitted_payload_schema(payload_schema_raw_bytes, runtime)
    if envelope["payload_schema_fingerprint"] != payload_schema.schema_fingerprint:
        raise ValueError("forward task-payload fingerprint mismatch")
    budget = TYPED_VALUES.EvaluationBudget()
    issues = TYPED_VALUES.validate_schema_instance(
        envelope["payload"],
        schema=payload_schema,
        aggregate_budget=budget,
        instance_path="/payload",
    )
    if issues:
        raise ValueError("forward task payload failed its code-owned schema")
    payload = envelope["payload"]
    assert type(payload) is dict and type(payload["facts"]) is dict
    raw_facts = payload["facts"]
    facts: dict[str, TYPED_VALUES.VerifiedTypedValue] = {}
    for key, value in raw_facts.items():
        if (
            type(key) is not str
            or len(key) > 245
            or _MACHINE_KEY.fullmatch(key) is None
            or type(value) is not dict
        ):
            raise ValueError("forward fact key or value shell is invalid")
        facts[key] = TYPED_VALUES.validate_typed_value(
            value,
            registry=registry,
            unit_context_index=unit_context_index,
            required_presence="forward_fact",
            aggregate_budget=budget,
            instance_path=f"/payload/facts/{key}",
        )
    rows = envelope["value_bindings"]
    if type(rows) is not list or len(rows) != len(facts):
        raise ValueError("forward fact binding coverage is invalid")
    keys = [row.get("semantic_key") if type(row) is dict else None for row in rows]
    if keys != sorted(facts, key=lambda item: item.encode("utf-16-be")):
        raise ValueError("forward fact bindings are not deterministically ordered")
    bindings: dict[str, Mapping[str, object]] = {}
    seen_ids: set[str] = set()
    seen_pointers: set[str] = set()
    for row in rows:
        if type(row) is not dict or set(row) != _BINDING_FIELDS:
            raise ValueError("forward fact binding shape is invalid")
        key = row["semantic_key"]
        fact = facts.get(key)
        provenance = row["provenance"]
        if (
            fact is None
            or row["binding_id"] != f"task-value.{key}"
            or row["json_pointer"] != f"/facts/{key}"
            or row["value_schema"] != fact.schema.schema_id
            or row["typed_value_fingerprint"] != fact.fingerprint
            or row["authority_kind"] not in {"user_fact", "task_fact"}
            or type(provenance) is not dict
            or set(provenance) != _PROVENANCE_FIELDS
            or provenance["issuer_kind"] not in {
                "trusted_ingress",
                "deterministic_fixture",
            }
            or type(provenance["issuer_id"]) is not str
            or not provenance["issuer_id"]
        ):
            raise ValueError("forward fact binding authority is invalid")
        if row["binding_id"] in seen_ids or row["json_pointer"] in seen_pointers:
            raise ValueError("forward fact binding identity is duplicate")
        seen_ids.add(row["binding_id"])
        seen_pointers.add(row["json_pointer"])
        bindings[key] = _freeze(row)
    if set(bindings) != set(facts):
        raise ValueError("forward fact binding is not bijective")
    expected_fingerprint = TYPED_VALUES.fingerprint_without(
        envelope, "artifact_fingerprint"
    )
    if envelope["artifact_fingerprint"] != expected_fingerprint:
        raise ValueError("forward task-envelope fingerprint mismatch")
    return VerifiedForwardTaskEnvelope(
        envelope=_freeze(envelope),
        facts=MappingProxyType(facts),
        bindings=MappingProxyType(bindings),
        artifact_fingerprint=expected_fingerprint,
    )


def issue_fixture_task_envelope(
    *,
    task_session_id: str,
    facts: Mapping[str, Mapping[str, object]],
    authority_by_key: Mapping[str, Mapping[str, object]],
    payload_schema: Mapping[str, object],
) -> bytes:
    if set(facts) != set(authority_by_key):
        raise ValueError("fixture facts and authority rows differ")
    ordered = sorted(facts, key=lambda item: item.encode("utf-16-be"))
    bindings: list[dict[str, object]] = []
    for key in ordered:
        authority = _plain(authority_by_key[key])
        if type(authority) is not dict or set(authority) != {
            "authority_kind",
            "provenance",
        }:
            raise ValueError("fixture authority row is invalid")
        provenance = authority["provenance"]
        if (
            type(provenance) is not dict
            or provenance.get("issuer_kind") != "deterministic_fixture"
        ):
            raise ValueError("fixture issuance requires deterministic provenance")
        typed = _plain(facts[key])
        assert type(typed) is dict
        bindings.append(
            {
                "authority_kind": authority["authority_kind"],
                "binding_id": f"task-value.{key}",
                "json_pointer": f"/facts/{key}",
                "provenance": provenance,
                "semantic_key": key,
                "typed_value_fingerprint": TYPED_VALUES.fingerprint(typed),
                "value_schema": typed["schema"],
            }
        )
    envelope: dict[str, object] = {
        "schema": "rook.planner_task_envelope:v1",
        "artifact_id": "task_envelope",
        "task_session_id": task_session_id,
        "payload_schema": TYPED_VALUES.FORWARD_PAYLOAD_SCHEMA_ID,
        "payload_schema_fingerprint": TYPED_VALUES.fingerprint(payload_schema),
        "payload": {"facts": {key: _plain(facts[key]) for key in ordered}},
        "value_bindings": bindings,
        "issued_at": "2026-07-23T12:00:00Z",
    }
    envelope["artifact_fingerprint"] = TYPED_VALUES.fingerprint(envelope)
    return _json_bytes(envelope)


def reconstruct_observed_historical_task_values(
    source: CONT_ARTIFACTS.VerifiedHistoricalSource,
    *,
    registry: TYPED_VALUES.VerifiedSemanticValueRegistry,
    unit_context_index: TYPED_VALUES.VerifiedUnitContextIndex,
) -> Mapping[str, TYPED_VALUES.VerifiedTypedValue]:
    source = _require_exact_historical_source(source)
    records = _record_by_role(source)
    task = _plain(records["authority.task_envelope"].value)
    if type(task) is not dict or (
        task.get("payload_schema") != HISTORICAL_TASK_PAYLOAD_SCHEMA_ID
        or task.get("payload_schema_fingerprint")
        != HISTORICAL_TASK_PAYLOAD_SCHEMA_FINGERPRINT
    ):
        raise ValueError("historical task-payload identity is not observed")
    facts = task.get("payload", {}).get("facts")
    rows = task.get("value_bindings")
    if type(facts) is not dict or type(rows) is not list or len(facts) != len(rows):
        raise ValueError("historical task authority is malformed")
    bindings = {row["semantic_key"]: row for row in rows if type(row) is dict}
    if set(bindings) != set(facts):
        raise ValueError("historical task binding is not bijective")
    budget = TYPED_VALUES.EvaluationBudget()
    values: dict[str, TYPED_VALUES.VerifiedTypedValue] = {}
    for key in sorted(facts, key=lambda item: item.encode("utf-16-be")):
        raw = facts[key]
        if type(raw) not in {str, int}:
            raise ValueError("historical task fact shape was not observed")
        binding = bindings[key]
        expected_schema = (
            "rook.semantic_string:v1" if type(raw) is str else "rook.semantic_integer:v1"
        )
        if (
            binding.get("binding_id") != f"task-value.{key}"
            or binding.get("json_pointer") != f"/facts/{key}"
            or binding.get("value_schema") != expected_schema
            or binding.get("typed_value_fingerprint")
            != TYPED_VALUES.fingerprint({"schema": expected_schema, "value": raw})
        ):
            raise ValueError("historical task binding differs from sealed equation")
        typed = {
            "schema": expected_schema,
            "value": raw,
            "unit": None,
            "unit_context_ref": None,
        }
        values[key] = TYPED_VALUES.validate_typed_value(
            typed,
            registry=registry,
            unit_context_index=unit_context_index,
            required_presence="forward_fact",
            aggregate_budget=budget,
            instance_path=f"/historical/facts/{key}",
        )
    return MappingProxyType(values)


def historical_task_bindings(
    source: CONT_ARTIFACTS.VerifiedHistoricalSource,
) -> Mapping[str, Mapping[str, object]]:
    source = _require_exact_historical_source(source)
    task = _plain(_record_by_role(source)["authority.task_envelope"].value)
    assert type(task) is dict and type(task["value_bindings"]) is list
    return MappingProxyType(
        {
            row["semantic_key"]: _freeze(row)
            for row in task["value_bindings"]
        }
    )


def derive_authority_partition(
    *,
    parent_values: Mapping[str, TYPED_VALUES.VerifiedTypedValue],
    parent_bindings: Mapping[str, Mapping[str, object]],
    successor: VerifiedForwardTaskEnvelope,
    parent_recipe: Mapping[str, object],
) -> AuthorityPartition:
    if set(parent_values) != set(parent_bindings):
        raise ValueError("parent value/binding coverage is invalid")
    parent_keys = tuple(sorted(parent_values, key=lambda item: item.encode("utf-16-be")))
    successor_keys = tuple(
        sorted(successor.facts, key=lambda item: item.encode("utf-16-be"))
    )
    migration_keys = tuple(key for key in successor_keys if key in parent_values)
    delta_keys = tuple(key for key in successor_keys if key not in parent_values)
    unresolved = parent_recipe.get("unresolved_intent")
    if type(unresolved) is not list:
        raise ValueError("parent recipe unresolved intent is invalid")
    unresolved_by_key = {
        row.get("semantic_key"): row
        for row in unresolved
        if type(row) is dict and type(row.get("semantic_key")) is str
    }
    if len(unresolved_by_key) != len(unresolved):
        raise ValueError("parent unresolved contract identities are invalid")
    required = tuple(
        sorted(
            unresolved_by_key,
            key=lambda item: item.encode("utf-16-be"),
        )
    )
    if migration_keys != parent_keys or delta_keys != required:
        raise ValueError("successor authority partition is not isolated")
    for key in delta_keys:
        fact = successor.facts[key]
        binding = successor.bindings[key]
        unresolved_row = unresolved_by_key[key]
        expected_location = unresolved_row.get("expected_source_location")
        resolution_authority = unresolved_row.get("resolution_authority")
        permitted_kinds = (
            resolution_authority.get("permitted_kinds")
            if type(resolution_authority) is dict
            else None
        )
        expected_unit_context = unresolved_row.get("unit_context_ref")
        if (
            unresolved_row.get("semantic_key") != key
            or fact.schema.schema_id != unresolved_row.get("value_schema")
            or binding["value_schema"] != unresolved_row.get("value_schema")
            or binding["authority_kind"] != "user_fact"
            or type(resolution_authority) is not dict
            or type(permitted_kinds) is not list
            or "user_fact" not in permitted_kinds
            or type(expected_location) is not dict
            or expected_location.get("artifact_id") != "task_envelope"
            or expected_location.get("json_pointer") != binding["json_pointer"]
            or _plain(fact.value.get("unit_context_ref"))
            != _plain(expected_unit_context)
        ):
            raise ValueError(
                "successor delta differs from parent unresolved contract"
            )
    value = {
        "parent_keys": list(parent_keys),
        "successor_keys": list(successor_keys),
        "migration_keys": list(migration_keys),
        "authority_delta_keys": list(delta_keys),
        "required_delta_keys": list(required),
    }
    return AuthorityPartition(
        parent_keys,
        successor_keys,
        migration_keys,
        delta_keys,
        required,
        TYPED_VALUES.fingerprint(value),
    )


def verify_exact_migration(
    *,
    parent_values: Mapping[str, TYPED_VALUES.VerifiedTypedValue],
    parent_bindings: Mapping[str, Mapping[str, object]],
    successor: VerifiedForwardTaskEnvelope,
    partition: AuthorityPartition,
) -> tuple[Mapping[str, object], ...]:
    ledger: list[Mapping[str, object]] = []
    for key in partition.migration_keys:
        parent = parent_values[key]
        current = successor.facts[key]
        parent_binding = parent_bindings[key]
        current_binding = successor.bindings[key]
        if parent.canonical_bytes != current.canonical_bytes:
            raise ValueError("retained typed value changed during representation migration")
        for field in ("semantic_key", "value_schema", "authority_kind", "provenance"):
            if _plain(parent_binding[field]) != _plain(current_binding[field]):
                raise ValueError("retained authority changed during representation migration")
        ledger.append(
            MappingProxyType(
                {
                    "semantic_key": key,
                    "canonical_typed_value_raw_sha256": TYPED_VALUES.sha256_prefixed(
                        parent.canonical_bytes
                    ),
                    "comparison": "exact_canonical_bytes_equal",
                }
            )
        )
    return tuple(ledger)


_NEGATIVE_CASE_IDS = (
    "registry.duplicate_or_unknown_schema",
    "registry.closed_shape_or_order",
    "registry.fingerprint_mismatch",
    "registry.dialect_or_id",
    "registry.unlisted_keyword",
    "registry.forbidden_reference",
    "registry.non_allowlisted_pattern",
    "registry.retrieval_or_format",
    "registry.budget_exhaustion",
    "registry.runtime_identity",
    "typed.wrong_type",
    "typed.boolean_as_integer",
    "typed.unsafe_integer",
    "typed.noncanonical_scalar",
    "typed.scalar_length",
    "typed.missing_scalar_field",
    "typed.inappropriate_unit",
    "typed.invalid_unit_context",
    "typed.extra_field",
    "typed.unknown_discriminator",
    "typed.fingerprint_mismatch",
    "binding.duplicate_fact_property",
    "binding.invalid_semantic_key",
    "binding.coverage",
    "binding.duplicate_identity",
    "binding.order",
    "binding.id_formula",
    "binding.pointer",
    "binding.value_schema",
    "binding.authority_or_provenance",
    "binding.unbound",
    "binding.artifact_fingerprint",
    "binding.task_session",
    "unit_context.unverified_mapping",
    "unit_context.exported_minter",
    "unit_context.caller_seal",
    "unit_context.construction_or_subclass",
    "unit_context.manual_allocation",
    "unit_context.copy_replace_serialize",
    "unit_context.altered_projection",
    "unit_context.reclosed_issued_object",
    "unit_context.environment_identity",
    "unit_context.freshness_session_issuer",
    "unit_context.binding_shape",
    "unit_context.pointer_or_fingerprint",
    "migration.payload_schema_identity",
    "migration.unobserved_historical_shape",
    "migration.retained_value",
    "migration.retained_unit_context",
    "migration.retained_authority",
    "migration.removed_parent_fact",
    "migration.extra_authority_key",
    "migration.omitted_required_key",
    "migration.non_user_fact_delta",
    "migration.unresolved_value_schema",
    "migration.unresolved_source_location",
    "migration.unresolved_authority_permission",
    "migration.unresolved_unit_context",
    "genericity.fixture_key_in_neutral_source",
    "genericity.annotation_key_branch",
)


def required_negative_case_ids() -> tuple[str, ...]:
    return _NEGATIVE_CASE_IDS


def run_required_negative_cases(**_inputs: object) -> tuple[NegativeCaseResult, ...]:
    """Execute the closed refusal manifest and retain one result per mutation."""

    required = {
        "runtime",
        "registry_raw_bytes",
        "payload_schema_raw_bytes",
        "unit_context_index",
        "parent_task_envelope",
        "parent_recipe",
        "radial_envelope_bytes",
        "annotation_envelope_bytes",
    }
    if set(_inputs) != required:
        raise ValueError("negative-case inputs are not closed")
    runtime = _inputs["runtime"]
    registry_raw = _inputs["registry_raw_bytes"]
    payload_schema_raw = _inputs["payload_schema_raw_bytes"]
    unit_index = _inputs["unit_context_index"]
    if type(runtime) is not TYPED_VALUES.RuntimeIdentity:
        raise TypeError("negative-case runtime is invalid")
    if type(registry_raw) is not bytes or type(payload_schema_raw) is not bytes:
        raise TypeError("negative-case contract bytes are invalid")
    registry = _verified_registry(registry_raw, runtime)

    def envelope(raw: bytes) -> VerifiedForwardTaskEnvelope:
        return validate_forward_task_envelope(
            raw,
            payload_schema_raw_bytes=payload_schema_raw,
            registry_raw_bytes=registry_raw,
            unit_context_index=unit_index,
            runtime=runtime,
        )

    radial = TYPED_VALUES.parse_strict_json(
        _inputs["radial_envelope_bytes"], label="radial negative fixture"
    )
    annotation = TYPED_VALUES.parse_strict_json(
        _inputs["annotation_envelope_bytes"], label="annotation negative fixture"
    )
    parent_task = _plain(_inputs["parent_task_envelope"])
    parent_recipe = _plain(_inputs["parent_recipe"])
    if not all(type(value) is dict for value in (radial, annotation, parent_task, parent_recipe)):
        raise ValueError("negative-case fixture inputs are invalid")

    class ObservedRefusal(ValueError):
        pass

    def reclose_envelope(value: dict[str, object]) -> bytes:
        value["artifact_fingerprint"] = TYPED_VALUES.fingerprint_without(
            value, "artifact_fingerprint"
        )
        return _json_bytes(value)

    def reclose_registry(value: dict[str, object]) -> bytes:
        entries = value.get("entries")
        if type(entries) is list:
            for row in entries:
                if type(row) is dict and type(row.get("schema_document")) is dict:
                    row["schema_fingerprint"] = TYPED_VALUES.fingerprint(
                        row["schema_document"]
                    )
        value["registry_fingerprint"] = TYPED_VALUES.fingerprint_without(
            value, "registry_fingerprint"
        )
        return _json_bytes(value)

    def schema_row(value: dict[str, object], schema_id: str) -> dict[str, object]:
        return next(row for row in value["entries"] if row["schema_id"] == schema_id)

    def verified_typed(value: dict[str, object], *, index: object = unit_index) -> object:
        return TYPED_VALUES.validate_typed_value(
            value,
            registry=registry,
            unit_context_index=index,
            required_presence="forward_fact",
            aggregate_budget=TYPED_VALUES.EvaluationBudget(),
            instance_path="/negative/value",
        )

    def first_binding(value: dict[str, object]) -> dict[str, object]:
        return value["value_bindings"][0]

    def reclose_fact_binding(value: dict[str, object], key: str) -> None:
        fact = value["payload"]["facts"][key]
        row = next(item for item in value["value_bindings"] if item["semantic_key"] == key)
        row["value_schema"] = fact["schema"]
        row["typed_value_fingerprint"] = TYPED_VALUES.fingerprint(fact)

    def registry_action(case_id: str) -> None:
        value = TYPED_VALUES.parse_strict_json(registry_raw, label="negative registry")
        assert type(value) is dict
        if case_id == "registry.duplicate_or_unknown_schema":
            value["entries"].append(copy.deepcopy(value["entries"][0]))
            raw = reclose_registry(value)
        elif case_id == "registry.closed_shape_or_order":
            value["entries"].reverse()
            raw = reclose_registry(value)
        elif case_id == "registry.fingerprint_mismatch":
            value["registry_fingerprint"] = "sha256:" + "0" * 64
            raw = _json_bytes(value)
        elif case_id == "registry.dialect_or_id":
            value["json_schema_dialect"] = "https://json-schema.org/draft/2019-09/schema"
            raw = reclose_registry(value)
        elif case_id == "registry.unlisted_keyword":
            schema_row(value, "rook.semantic_string:v1")["schema_document"]["default"] = ""
            raw = reclose_registry(value)
        elif case_id == "registry.forbidden_reference":
            schema_row(value, "rook.semantic_string:v1")["schema_document"]["$ref"] = "#"
            raw = reclose_registry(value)
        elif case_id == "registry.non_allowlisted_pattern":
            schema_row(value, "rook.semantic_scalar:v1")["schema_document"]["properties"]["value"]["pattern"] = ".*"
            raw = reclose_registry(value)
        elif case_id == "registry.retrieval_or_format":
            schema_row(value, "rook.semantic_string:v1")["schema_document"]["properties"]["value"]["format"] = "uri"
            raw = reclose_registry(value)
        elif case_id == "registry.budget_exhaustion":
            TYPED_VALUES.verify_semantic_value_registry(
                value,
                raw_registry_byte_count=TYPED_VALUES.MAX_REGISTRY_BYTES + 1,
                runtime=runtime,
            )
            return
        else:
            altered = dataclass_replace_runtime(runtime)
            _verified_registry(registry_raw, altered)
            return
        _verified_registry(raw, runtime)

    def dataclass_replace_runtime(value: TYPED_VALUES.RuntimeIdentity) -> TYPED_VALUES.RuntimeIdentity:
        return replace(value, version=value.version + "-different")

    scalar = {
        "schema": "rook.semantic_scalar:v1",
        "value": "2",
        "unit": "model_unit",
        "unit_context_ref": {
            "kind": "artifact_value",
            "artifact_id": "environment_snapshot",
            "json_pointer": "/document/unit_context",
        },
    }

    def typed_action(case_id: str) -> None:
        if case_id == "typed.wrong_type":
            value = {"schema": "rook.semantic_integer:v1", "value": "3", "unit": None, "unit_context_ref": None}
        elif case_id == "typed.boolean_as_integer":
            value = {"schema": "rook.semantic_integer:v1", "value": True, "unit": None, "unit_context_ref": None}
        elif case_id == "typed.unsafe_integer":
            value = {"schema": "rook.semantic_integer:v1", "value": 9007199254740992, "unit": None, "unit_context_ref": None}
        elif case_id == "typed.noncanonical_scalar":
            value = {**scalar, "value": "2.0"}
        elif case_id == "typed.scalar_length":
            value = {**scalar, "value": "1" * 1025}
        elif case_id == "typed.missing_scalar_field":
            value = dict(scalar)
            del value["unit"]
        elif case_id == "typed.inappropriate_unit":
            value = {"schema": "rook.semantic_string:v1", "value": "x", "unit": "model_unit", "unit_context_ref": scalar["unit_context_ref"]}
        elif case_id == "typed.invalid_unit_context":
            value = {**scalar, "unit_context_ref": None}
        elif case_id == "typed.extra_field":
            value = {**scalar, "extra": True}
        elif case_id == "typed.unknown_discriminator":
            value = {"schema": "rook.semantic_unknown:v1", "value": "x", "unit": None, "unit_context_ref": None}
        else:
            changed = copy.deepcopy(annotation)
            first_binding(changed)["typed_value_fingerprint"] = "sha256:" + "0" * 64
            envelope(reclose_envelope(changed))
            return
        verified_typed(value)

    def binding_action(case_id: str) -> None:
        value = copy.deepcopy(annotation)
        rows = value["value_bindings"]
        if case_id == "binding.duplicate_fact_property":
            envelope(b'{"payload":{"facts":{"x":1,"x":2}}}')
            return
        if case_id == "binding.invalid_semantic_key":
            key = "BadKey"
            payload_schema = TYPED_VALUES.parse_strict_json(payload_schema_raw, label="payload schema")
            raw = issue_fixture_task_envelope(
                task_session_id=value["task_session_id"],
                facts={key: {"schema": "rook.semantic_string:v1", "value": "x", "unit": None, "unit_context_ref": None}},
                authority_by_key={key: {"authority_kind": "user_fact", "provenance": {"issuer_kind": "deterministic_fixture", "issuer_id": "negative"}}},
                payload_schema=payload_schema,
            )
            envelope(raw)
            return
        if case_id == "binding.coverage":
            rows.pop()
        elif case_id == "binding.duplicate_identity":
            rows[1]["binding_id"] = rows[0]["binding_id"]
        elif case_id == "binding.order":
            rows.reverse()
        elif case_id == "binding.id_formula":
            rows[0]["binding_id"] = "task-value.other"
        elif case_id == "binding.pointer":
            rows[0]["json_pointer"] = "/facts/other"
        elif case_id == "binding.value_schema":
            rows[0]["value_schema"] = "rook.semantic_string:v1"
        elif case_id == "binding.authority_or_provenance":
            rows[0]["provenance"]["issuer_kind"] = "unknown"
        elif case_id == "binding.unbound":
            key = rows[-1]["semantic_key"]
            del value["payload"]["facts"][key]
        elif case_id == "binding.artifact_fingerprint":
            value["artifact_fingerprint"] = "sha256:" + "0" * 64
            envelope(_json_bytes(value))
            return
        else:
            value["task_session_id"] = "different-task-session"
        envelope(reclose_envelope(value))

    def unit_context_inputs() -> dict[str, object]:
        source = CONT_ARTIFACTS.verify_historical_source()
        records = _record_by_role(source)
        environment = _plain(records["authority.environment_snapshot"].value)
        attempt = _plain(records["attempt_context"].value)
        payload_registry = _plain(records["registry.payload_schemas"].value)
        row = next(item for item in payload_registry["entries"] if item["schema_id"] == TYPED_VALUES.HISTORICAL_ENVIRONMENT_PAYLOAD_SCHEMA_ID)
        return {
            "environment_artifact_bytes": records["authority.environment_snapshot"].raw_bytes,
            "environment_payload_schema_bytes": TYPED_VALUES.canonical_json_bytes(row["schema_document"]),
            "attempt_context_bytes": records["attempt_context"].raw_bytes,
            "expected_artifact_fingerprint": environment["artifact_fingerprint"],
            "expected_issuer_id": environment["issuer"]["authority_id"],
            "expected_environment_session_id": attempt["environment_session_id"],
            "expected_task_session_id": attempt["task_session_id"],
            "evaluated_at": attempt["evaluated_at"],
        }

    def fresh_unit_index() -> TYPED_VALUES.VerifiedUnitContextIndex:
        return TYPED_VALUES.derive_verified_unit_context_index(**unit_context_inputs())

    def mutate_unit_source(case_id: str) -> None:
        inputs = unit_context_inputs()
        environment = TYPED_VALUES.parse_strict_json(inputs["environment_artifact_bytes"], label="environment")
        assert type(environment) is dict
        if case_id == "unit_context.environment_identity":
            environment["artifact_id"] = "other"
        elif case_id == "unit_context.freshness_session_issuer":
            environment["issuer"]["authority_id"] = "other"
        elif case_id == "unit_context.binding_shape":
            environment["value_bindings"] = []
        else:
            environment["value_bindings"][0]["typed_value_fingerprint"] = "sha256:" + "0" * 64
        environment["artifact_fingerprint"] = TYPED_VALUES.fingerprint_without(environment, "artifact_fingerprint")
        inputs["environment_artifact_bytes"] = _json_bytes(environment)
        inputs["expected_artifact_fingerprint"] = environment["artifact_fingerprint"]
        TYPED_VALUES.derive_verified_unit_context_index(**inputs)

    def unit_action(case_id: str) -> None:
        if case_id == "unit_context.unverified_mapping":
            verified_typed(dict(scalar), index={})
        elif case_id == "unit_context.exported_minter":
            forbidden = ("_issue_unit_context_index", "AuthoritySeal", "_UnitContextAuthoritySeal", "_build_unit_context_authority_gate")
            if any(hasattr(TYPED_VALUES, name) for name in forbidden):
                return
            raise ObservedRefusal("minting capability is structurally absent")
        elif case_id == "unit_context.caller_seal":
            TYPED_VALUES.derive_verified_unit_context_index(seal=object())
        elif case_id == "unit_context.construction_or_subclass":
            TYPED_VALUES.VerifiedUnitContextIndex()
        elif case_id == "unit_context.manual_allocation":
            verified_typed(dict(scalar), index=object.__new__(TYPED_VALUES.VerifiedUnitContextIndex))
        elif case_id == "unit_context.copy_replace_serialize":
            issued = fresh_unit_index()
            if copy.copy(issued) is not issued or copy.deepcopy(issued) is not issued:
                return
            try:
                replace(issued)
            except TypeError:
                pass
            else:
                return
            try:
                pickle.dumps(issued)
            except TypeError:
                raise ObservedRefusal(
                    "copy, replacement, and serialization cannot create a proof carrier"
                )
        elif case_id == "unit_context.altered_projection":
            issued = fresh_unit_index()
            object.__setattr__(issued, "_VerifiedUnitContextIndex__snapshot", b"{}")
            verified_typed(dict(scalar), index=issued)
        elif case_id == "unit_context.reclosed_issued_object":
            issued = fresh_unit_index()
            alternate_inputs = unit_context_inputs()
            attempt = TYPED_VALUES.parse_strict_json(alternate_inputs["attempt_context_bytes"], label="attempt")
            attempt["attempt_id"] = "alternate-negative-attempt"
            attempt["context_fingerprint"] = TYPED_VALUES.fingerprint_without(attempt, "context_fingerprint")
            alternate_inputs["attempt_context_bytes"] = _json_bytes(attempt)
            alternate = TYPED_VALUES.derive_verified_unit_context_index(**alternate_inputs)
            for slot in ("__snapshot", "__entries", "__proof_fingerprint"):
                object.__setattr__(issued, f"_VerifiedUnitContextIndex{slot}", object.__getattribute__(alternate, f"_VerifiedUnitContextIndex{slot}"))
            verified_typed(dict(scalar), index=issued)
        else:
            mutate_unit_source(case_id)

    def verified_successor(value: dict[str, object]) -> VerifiedForwardTaskEnvelope:
        return envelope(reclose_envelope(value))

    def migration_context(
        successor: VerifiedForwardTaskEnvelope,
        recipe: Mapping[str, object],
    ):
        source = CONT_ARTIFACTS.verify_historical_source()
        parent_values = reconstruct_observed_historical_task_values(source, registry=registry, unit_context_index=unit_index)
        bindings = historical_task_bindings(source)
        partition = derive_authority_partition(parent_values=parent_values, parent_bindings=bindings, successor=successor, parent_recipe=recipe)
        return parent_values, bindings, partition

    def migration_action(case_id: str) -> None:
        value = copy.deepcopy(radial)
        recipe = copy.deepcopy(parent_recipe)
        parent_keys = set(parent_task["payload"]["facts"])
        successor_keys = set(value["payload"]["facts"])
        retained_key = sorted(parent_keys, key=lambda item: item.encode("utf-16-be"))[0]
        delta_key = sorted(successor_keys - parent_keys, key=lambda item: item.encode("utf-16-be"))[0]
        if case_id == "migration.payload_schema_identity":
            mutated = copy.deepcopy(parent_task)
            mutated["payload_schema"] = "other"
            source = CONT_ARTIFACTS.verify_historical_source()
            records = list(source.input_records)
            index = next(i for i, row in enumerate(records) if row.role == "authority.task_envelope")
            records[index] = PLANNER_ARTIFACTS.planner_input_record_from_bytes(role=records[index].role, relative_path=records[index].relative_path, raw_bytes=_json_bytes(mutated))
            reconstruct_observed_historical_task_values(replace(source, input_records=tuple(records)), registry=registry, unit_context_index=unit_index)
            return
        if case_id == "migration.unobserved_historical_shape":
            mutated = copy.deepcopy(parent_task)
            mutated["payload"]["facts"][retained_key] = True
            source = CONT_ARTIFACTS.verify_historical_source()
            records = list(source.input_records)
            index = next(i for i, row in enumerate(records) if row.role == "authority.task_envelope")
            records[index] = PLANNER_ARTIFACTS.planner_input_record_from_bytes(role=records[index].role, relative_path=records[index].relative_path, raw_bytes=_json_bytes(mutated))
            reconstruct_observed_historical_task_values(replace(source, input_records=tuple(records)), registry=registry, unit_context_index=unit_index)
            return
        if case_id == "migration.retained_value":
            value["payload"]["facts"][retained_key]["value"] = "changed" if type(value["payload"]["facts"][retained_key]["value"]) is str else 11
            reclose_fact_binding(value, retained_key)
        elif case_id == "migration.retained_unit_context":
            value["payload"]["facts"][retained_key]["unit"] = "model_unit"
        elif case_id == "migration.retained_authority":
            next(row for row in value["value_bindings"] if row["semantic_key"] == retained_key)["provenance"]["issuer_id"] = "changed"
        elif case_id == "migration.removed_parent_fact":
            del value["payload"]["facts"][retained_key]
            value["value_bindings"] = [row for row in value["value_bindings"] if row["semantic_key"] != retained_key]
        elif case_id == "migration.extra_authority_key":
            extra = "unrequested_negative_fact"
            value["payload"]["facts"][extra] = {"schema": "rook.semantic_string:v1", "value": "x", "unit": None, "unit_context_ref": None}
            value["value_bindings"].append({"binding_id": f"task-value.{extra}", "json_pointer": f"/facts/{extra}", "semantic_key": extra, "value_schema": "rook.semantic_string:v1", "typed_value_fingerprint": TYPED_VALUES.fingerprint(value["payload"]["facts"][extra]), "authority_kind": "user_fact", "provenance": {"issuer_kind": "deterministic_fixture", "issuer_id": "negative"}})
            value["value_bindings"].sort(key=lambda row: row["semantic_key"].encode("utf-16-be"))
        elif case_id == "migration.omitted_required_key":
            del value["payload"]["facts"][delta_key]
            value["value_bindings"] = [row for row in value["value_bindings"] if row["semantic_key"] != delta_key]
        elif case_id == "migration.non_user_fact_delta":
            next(row for row in value["value_bindings"] if row["semantic_key"] == delta_key)["authority_kind"] = "task_fact"
        elif case_id.startswith("migration.unresolved_"):
            unresolved = next(row for row in recipe["unresolved_intent"] if row["semantic_key"] == delta_key)
            if case_id == "migration.unresolved_value_schema":
                unresolved["value_schema"] = "rook.semantic_string:v1"
            elif case_id == "migration.unresolved_source_location":
                unresolved["expected_source_location"]["json_pointer"] = "/facts/other"
            elif case_id == "migration.unresolved_authority_permission":
                unresolved["resolution_authority"]["permitted_kinds"] = ["planner_assumption"]
            else:
                unresolved["unit_context_ref"] = None
        elif case_id == "genericity.fixture_key_in_neutral_source":
            fixture_keys = set(radial["payload"]["facts"]) | set(annotation["payload"]["facts"])
            parent_names = set(parent_task["payload"]["facts"])
            searched = fixture_keys - parent_names
            sources = [Path(__file__), _SCRIPTS_DIR / "lm9_semantic_typed_values.py", *CONTRACTS_DIR.glob("*.json")]
            if not any(key in path.read_text(encoding="utf-8") for path in sources for key in searched):
                raise ObservedRefusal("fixture semantic keys are absent from neutral sources")
            return
        elif case_id == "genericity.annotation_key_branch":
            envelope(_inputs["annotation_envelope_bytes"])
            annotation_only = set(annotation["payload"]["facts"])
            sources = [Path(__file__), _SCRIPTS_DIR / "lm9_semantic_typed_values.py", *CONTRACTS_DIR.glob("*.json")]
            if not any(key in path.read_text(encoding="utf-8") for path in sources for key in annotation_only):
                raise ObservedRefusal("annotation witness uses no key-specific branch")
            return
        successor = verified_successor(value)
        parent_values, bindings, partition = migration_context(successor, recipe)
        verify_exact_migration(parent_values=parent_values, parent_bindings=bindings, successor=successor, partition=partition)

    def execute(case_id: str) -> NegativeCaseResult:
        try:
            if case_id.startswith("registry."):
                registry_action(case_id)
            elif case_id.startswith("typed."):
                typed_action(case_id)
            elif case_id.startswith("binding."):
                binding_action(case_id)
            elif case_id.startswith("unit_context."):
                unit_action(case_id)
            else:
                migration_action(case_id)
        except (ValueError, TypeError, ObservedRefusal) as exc:
            expected_tokens = {
                "registry.": ("registry", "schema", "profile", "runtime", "byte limit"),
                "typed.": (
                    "typed value",
                    "schema",
                    "unit context",
                    "discriminator",
                    "forward fact binding",
                ),
                "binding.": ("forward", "duplicate"),
                "unit_context.": (
                    "unit context",
                    "VerifiedUnitContextIndex",
                    "seal",
                    "minting capability",
                    "proof carrier",
                    "module-issued",
                    "environment",
                    "attempt context",
                ),
                "migration.": (
                    "historical source",
                    "typed value",
                    "retained",
                    "partition",
                    "unresolved contract",
                ),
                "genericity.": ("fixture semantic keys", "annotation witness"),
            }
            prefix = next(
                key for key in expected_tokens if case_id.startswith(key)
            )
            failure = str(exc).replace("-", " ")
            if not any(token in failure for token in expected_tokens[prefix]):
                raise RuntimeError(
                    f"negative case failed at an unexpected locus: {case_id}: {exc}"
                ) from exc
            evidence = {
                "case_id": case_id,
                "status": "deterministically_refused",
                "exception_type": type(exc).__name__,
                "failure": str(exc),
            }
            return NegativeCaseResult(
                case_id=case_id,
                status="deterministically_refused",
                evidence_fingerprint=TYPED_VALUES.fingerprint(evidence),
            )
        raise ValueError(f"negative case did not refuse: {case_id}")

    return tuple(execute(case_id) for case_id in _NEGATIVE_CASE_IDS)


def _validate_parent_recipe_occurrences(
    recipe: Mapping[str, object],
    *,
    registry: TYPED_VALUES.VerifiedSemanticValueRegistry,
    unit_context_index: TYPED_VALUES.VerifiedUnitContextIndex,
) -> str:
    rows: list[dict[str, object]] = []
    budget = TYPED_VALUES.EvaluationBudget()
    for field, occurrence in (("assumptions", "recipe_assumption"), ("derived_facts", "recipe_derived")):
        values = recipe.get(field)
        if type(values) is not list:
            raise ValueError(f"parent recipe {field} is invalid")
        for index, row in enumerate(values):
            if type(row) is not dict or type(row.get("typed_value")) is not dict:
                raise ValueError(f"parent recipe {field} occurrence is invalid")
            verified = TYPED_VALUES.validate_typed_value(
                row["typed_value"],
                registry=registry,
                unit_context_index=unit_context_index,
                required_presence=occurrence,
                aggregate_budget=budget,
                instance_path=f"/{field}/{index}/typed_value",
            )
            rows.append({"path": f"/{field}/{index}/typed_value", "raw_sha256": TYPED_VALUES.sha256_prefixed(verified.canonical_bytes)})
    unresolved = recipe.get("unresolved_intent")
    if type(unresolved) is not list:
        raise ValueError("parent unresolved-intent collection is invalid")
    for index, row in enumerate(unresolved):
        if type(row) is not dict or row.get("value_schema") not in registry.entries:
            raise ValueError("parent unresolved value schema is not registered")
        rows.append({"path": f"/unresolved_intent/{index}", "schema": row["value_schema"]})
    return TYPED_VALUES.fingerprint(rows)


def build_outcome_neutral_parent_witness(
    *,
    derivative_archive: Path,
    runtime: TYPED_VALUES.RuntimeIdentity,
    registry: TYPED_VALUES.VerifiedSemanticValueRegistry,
    unit_context_index: TYPED_VALUES.VerifiedUnitContextIndex,
) -> OutcomeNeutralParentWitness:
    source = CONT_ARTIFACTS.verify_historical_source()
    recipe = TYPED_VALUES.parse_strict_json(source.final_recipe_bytes, label="parent recipe")
    if type(recipe) is not dict:
        raise ValueError("parent recipe is not an object")
    typed_fingerprint = _validate_parent_recipe_occurrences(
        recipe, registry=registry, unit_context_index=unit_context_index
    )
    inputs = frozen_gate_inputs(source)
    gate = SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=source.final_recipe_bytes,
        authority=inputs.authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.authority.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )
    if gate.status != "mechanically_accepted" or gate.final_recipe_bytes != source.final_recipe_bytes:
        raise ValueError("registry migration changed parent mechanical outcome")
    sealed = CONT_ARTIFACTS.verify_sealed_derivative_archive(
        derivative_archive,
        expected_derivative_identity=OFFICIAL_DERIVATIVE_IDENTITY,
    )
    classification = PLANNER_ARTIFACTS.derive_evaluated_recipe_classification(
        sealed.evaluator_result,
        final_recipe_bytes=source.final_recipe_bytes,
    )
    unresolved = tuple(
        sorted(
            (row["semantic_key"] for row in recipe["unresolved_intent"]),
            key=lambda item: item.encode("utf-16-be"),
        )
    )
    value = {
        "source_manifest_raw_sha256": source.pins.root_manifest_raw_sha256,
        "recipe_raw_sha256": source.pins.recipe_raw_sha256,
        "recipe_fingerprint": source.pins.ratified_recipe_fingerprint,
        "typed_value_validation_fingerprint": typed_fingerprint,
        "mechanical_gate_status": gate.status,
        "unresolved_keys": list(unresolved),
        "derivative_archive_identity": sealed.derivative_archive_identity,
        "evaluator_recommendation": sealed.evaluator_result.recommendation,
        "classification": classification,
    }
    return OutcomeNeutralParentWitness(
        **value,
        witness_fingerprint=TYPED_VALUES.fingerprint(value),
    )


def build_control_compatibility_witness(
    recipe_path: Path,
    *,
    frozen_inputs: PLANNER_ARTIFACTS.FrozenPlannerInputs,
    registry: TYPED_VALUES.VerifiedSemanticValueRegistry,
    unit_context_index: TYPED_VALUES.VerifiedUnitContextIndex,
) -> ControlCompatibilityWitness:
    raw = Path(recipe_path).read_bytes()
    recipe = TYPED_VALUES.parse_strict_json(raw, label="control recipe")
    if type(recipe) is not dict:
        raise ValueError("control recipe must be an object")
    typed_fingerprint = _validate_parent_recipe_occurrences(
        recipe, registry=registry, unit_context_index=unit_context_index
    )
    gate = SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=raw,
        authority=frozen_inputs.authority,
        recipe_schema=frozen_inputs.recipe_schema,
        normalization_profile=frozen_inputs.authority.normalization_profile,
        exclusion_policy=frozen_inputs.exclusion_policy,
    )
    if gate.status != "mechanically_accepted" or gate.final_recipe_bytes != raw:
        raise ValueError("registry migration changed control recipe outcome")
    return ControlCompatibilityWitness(
        fixture_path=str(Path(recipe_path).resolve()),
        recipe_raw_sha256=TYPED_VALUES.sha256_prefixed(raw),
        assumption_count=len(recipe["assumptions"]),
        derived_fact_count=len(recipe["derived_facts"]),
        gate_status=gate.status,
        typed_value_validation_fingerprint=typed_fingerprint,
    )


def value_for_evidence(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return _plain(asdict(value))
    return _plain(value)


__all__ = [
    "ANNOTATION_FIXTURE_PATH",
    "AuthorityPartition",
    "ControlCompatibilityWitness",
    "NegativeCaseResult",
    "OFFICIAL_DERIVATIVE",
    "OFFICIAL_DERIVATIVE_IDENTITY",
    "OutcomeNeutralParentWitness",
    "PAYLOAD_SCHEMA_PATH",
    "RADIAL_FIXTURE_PATH",
    "REGISTRY_PATH",
    "VerifiedForwardTaskEnvelope",
    "build_outcome_neutral_parent_witness",
    "build_control_compatibility_witness",
    "derive_authority_partition",
    "frozen_gate_inputs",
    "historical_task_bindings",
    "issue_fixture_task_envelope",
    "reconstruct_observed_historical_task_values",
    "required_negative_case_ids",
    "run_required_negative_cases",
    "validate_forward_task_envelope",
    "value_for_evidence",
    "verify_exact_migration",
]
