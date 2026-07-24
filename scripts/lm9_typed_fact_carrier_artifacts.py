"""Probe-owned composition for LM9 task-local typed-fact evidence."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
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
    if type(source) is not CONT_ARTIFACTS.VerifiedHistoricalSource:
        raise TypeError("exact verified historical source is required")
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
    required = tuple(
        sorted(
            (row["semantic_key"] for row in unresolved if type(row) is dict),
            key=lambda item: item.encode("utf-16-be"),
        )
    )
    if migration_keys != parent_keys or delta_keys != required:
        raise ValueError("successor authority partition is not isolated")
    for key in delta_keys:
        if successor.bindings[key]["authority_kind"] != "user_fact":
            raise ValueError("successor authority delta is not user-fact-only")
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
    "genericity.fixture_key_in_neutral_source",
    "genericity.annotation_key_branch",
)


def required_negative_case_ids() -> tuple[str, ...]:
    return _NEGATIVE_CASE_IDS


def run_required_negative_cases(**_inputs: object) -> tuple[NegativeCaseResult, ...]:
    """Register the final refusal matrix; later tasks harden every mutation."""

    return tuple(
        NegativeCaseResult(
            case_id=case_id,
            status="task1_registered_not_hardened",
            evidence_fingerprint=TYPED_VALUES.fingerprint(
                {"case_id": case_id, "stage": "task1_registered_not_hardened"}
            ),
        )
        for case_id in _NEGATIVE_CASE_IDS
    )


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
