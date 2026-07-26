"""Pure governed-resolution request and isolation contracts."""

from __future__ import annotations

import copy
import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping


_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _import_path in (_SCRIPTS_DIR, _MCP_SRC):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

import lm9b_p_planner_recipe_transfer_support as PLANNER_SUPPORT
import lm9b_p_planner_recipe_transfer_artifacts as PLANNER_ARTIFACTS
import lm9b_p_evaluator_only_continuation_artifacts as CONT_ARTIFACTS
import lm9_semantic_typed_values as TYPED_VALUES
import lm9_typed_fact_carrier_artifacts as CARRIER


REVISION_RENDERER_ID = "lm9b_p.planner_revision_request_renderer:v1"
REVISION_EVALUATION_RENDERER_ID = (
    "lm9b_p.planner_revision_evaluation_renderer:v1"
)
REVISION_SYSTEM_PROMPT = (
    "Revise the exact parent Planner recipe under the visible successor authority "
    "and isolation obligations. Submit one complete recipe through "
    "submit_planner_recipe. Do not emit a patch, infer supplied values, or alter "
    "unrelated semantics."
)


@dataclass(frozen=True)
class RenderedRevisionRequest:
    renderer_id: str
    payload: Mapping[str, object]
    raw_bytes: bytes
    raw_sha256: str
    canonical_fingerprint: str


@dataclass(frozen=True)
class IsolationPolicyInstance:
    definition_id: str
    definition_fingerprint: str
    value: Mapping[str, object]
    instance_fingerprint: str


@dataclass(frozen=True)
class VerifiedResolutionInputs:
    parent_recipe_bytes: bytes
    parent_recipe: Mapping[str, object]
    successor_envelope_bytes: bytes
    successor_envelope: Mapping[str, object]
    current_authority: object
    carrier_support_instrument: Mapping[str, object]
    recipe_schema: Mapping[str, object]
    normalization_profile: object
    exclusion_policy: Mapping[str, object]
    brief: str
    authoring_contract: Mapping[str, object]
    evaluation_rubric: Mapping[str, object]
    correspondence: tuple[Mapping[str, object], ...]
    migration_ledger: tuple[Mapping[str, object], ...]
    policy_instance: IsolationPolicyInstance
    historical_qualification_identity: str
    carrier_compatibility_fingerprint: str
    reviewed_commit_sha: str
    inputs_fingerprint: str


@dataclass(frozen=True)
class IsolationGateResult:
    status: Literal["isolated", "isolation_rejected"]
    equations: tuple[Mapping[str, object], ...]
    bounded_differences: tuple[Mapping[str, object], ...]
    parent_residual_bytes: bytes
    candidate_residual_bytes: bytes
    result_fingerprint: str


def assemble_verified_resolution_inputs(**_kwargs: object) -> VerifiedResolutionInputs:
    required = {
        "sources",
        "isolation_policy_bytes",
        "evaluation_rubric_bytes",
    }
    if set(_kwargs) != required:
        raise ValueError("resolution input set is incomplete or contains extras")
    sources = _kwargs["sources"]
    policy_raw = _kwargs["isolation_policy_bytes"]
    rubric_raw = _kwargs["evaluation_rubric_bytes"]
    # Runtime import avoids a module-import cycle. The consumer requires the
    # exact closure-issued physical-source carrier and returns its retained,
    # immutable verification projection; this assembler performs no I/O.
    import lm9b_p_governed_resolution_artifacts as RESOLUTION_ARTIFACTS

    source_proof = RESOLUTION_ARTIFACTS.consume_verified_resolution_sources(
        sources
    )
    source = source_proof["historical_source"]
    derivative = source_proof["parent_derivative"]
    qualification = source_proof["carrier_qualification"]
    successor_raw = sources.exact_successor_bytes
    payload_schema_raw = sources.exact_contract_bytes["forward_payload_schema"]
    registry_raw = sources.exact_contract_bytes["semantic_value_registry"]
    reviewed_commit = sources.reviewed_commit_sha
    if (
        derivative.evaluator_result.recommendation != "semantically_faithful"
        or derivative.classification != "probe_candidate_blocked"
    ):
        raise ValueError("parent derivative is not the faithful blocked observation")
    qualification_proof = (
        RESOLUTION_ARTIFACTS.consume_verified_carrier_qualification(
            qualification
        )
    )
    if (
        type(reviewed_commit) is not str
        or not reviewed_commit
        or qualification_proof["consuming_commit_sha"] != reviewed_commit
    ):
        raise ValueError("carrier compatibility is not bound to the consuming commit")
    for raw, label in (
        (successor_raw, "successor envelope"),
        (payload_schema_raw, "payload schema"),
        (registry_raw, "semantic registry"),
        (policy_raw, "isolation policy"),
        (rubric_raw, "evaluation rubric"),
    ):
        if type(raw) is not bytes:
            raise TypeError(f"exact {label} bytes are required")

    successor = source_proof["successor"]
    parent_recipe = source_proof["parent_recipe"]
    partition = source_proof["partition"]
    migration = source_proof["migration"]
    parent_keys = set(partition.parent_keys)
    unresolved_keys = set(partition.required_delta_keys)
    successor_keys = set(partition.successor_keys)
    if parent_keys & unresolved_keys:
        raise ValueError("parent established and unresolved keys overlap")
    if successor_keys != parent_keys | unresolved_keys:
        raise ValueError("successor key set differs from P union U")

    rubric = PLANNER_SUPPORT.parse_strict_json(rubric_raw)
    policy = PLANNER_SUPPORT.parse_strict_json(policy_raw)
    if type(rubric) is not dict or rubric.get("rubric_fingerprint") != (
        PLANNER_SUPPORT.fingerprint_without(rubric, "rubric_fingerprint")
    ):
        raise ValueError("resolution evaluator rubric identity is invalid")
    if any("spacing choice absent" in item.casefold() for item in rubric.get("scenario_obligations", [])):
        raise ValueError("resolution evaluator rubric retains stale spacing authority")
    if type(policy) is not dict or policy.get("policy_fingerprint") != (
        PLANNER_SUPPORT.fingerprint_without(policy, "policy_fingerprint")
    ):
        raise ValueError("resolution isolation policy identity is invalid")

    replacement = PLANNER_ARTIFACTS.planner_input_record_from_bytes(
        role="evaluation_rubric",
        relative_path="planner_evaluation_rubric.json",
        raw_bytes=rubric_raw,
    )
    migrated_records = tuple(
        replacement if record.role == "evaluation_rubric" else record
        for record in source.input_records
    )
    frozen = PLANNER_ARTIFACTS.frozen_planner_inputs_from_records(
        migrated_records,
        source_dir=source.source_root / "checkpoint-1" / "inputs",
    )
    artifacts = dict(frozen.authority.artifacts)
    artifacts["task_envelope"] = successor.envelope
    historical_payload_registry = PLANNER_SUPPORT._json_builtins(
        frozen.authority.payload_schema_registry
    )
    environment_schema_id = artifacts["environment_snapshot"]["payload_schema"]
    environment_entries = [
        copy.deepcopy(row)
        for row in historical_payload_registry["entries"]
        if row["schema_id"] == environment_schema_id
    ]
    if len(environment_entries) != 1:
        raise ValueError("historical environment payload schema is not unique")
    forward_payload_schema = PLANNER_SUPPORT.parse_strict_json(payload_schema_raw)
    semantic_value_registry = PLANNER_SUPPORT.parse_strict_json(registry_raw)
    if type(forward_payload_schema) is not dict or type(
        semantic_value_registry
    ) is not dict:
        raise ValueError("carrier-support contract is not an object")
    successor_payload_registry = {
        "schema": "rook.payload_schema_registry:v1",
        "registry_id": "payload_schema_registry",
        "registry_version": "lm9b_p.governed_resolution_payload_schemas:v1",
        "json_schema_dialect": TYPED_VALUES.DIALECT,
        "schema_evaluator_profile": TYPED_VALUES.PROFILE_ID,
        "entries": [
            environment_entries[0],
            {
                "schema_id": TYPED_VALUES.FORWARD_PAYLOAD_SCHEMA_ID,
                "schema_fingerprint": TYPED_VALUES.fingerprint(
                    forward_payload_schema
                ),
                "schema_document": forward_payload_schema,
            },
        ],
    }
    successor_payload_registry["registry_fingerprint"] = (
        TYPED_VALUES.fingerprint(successor_payload_registry)
    )
    carrier_support = {
        "schema": "rook.lm9b_p.governed_resolution_carrier_support:v1",
        "payload_schema_registry": successor_payload_registry,
        "semantic_value_registry": semantic_value_registry,
        "profile": CARRIER.value_for_evidence(
            TYPED_VALUES.build_profile_identity(source_proof["runtime"]).value
        ),
        "typed_value_helper_contract_id": TYPED_VALUES.HELPER_CONTRACT_ID,
        "forward_payload_schema_raw_sha256": PLANNER_SUPPORT.sha256_prefixed(
            payload_schema_raw
        ),
        "semantic_value_registry_raw_sha256": PLANNER_SUPPORT.sha256_prefixed(
            registry_raw
        ),
    }
    carrier_support["carrier_support_fingerprint"] = PLANNER_SUPPORT.fingerprint(
        carrier_support
    )
    current_authority = replace(
        frozen.authority,
        artifacts=MappingProxyType(artifacts),
        payload_schema_registry=_freeze_json(successor_payload_registry),
    )

    unresolved_rows = {
        row["semantic_key"]: row for row in parent_recipe["unresolved_intent"]
    }
    correspondence: list[Mapping[str, object]] = []
    for key in partition.required_delta_keys:
        unresolved = unresolved_rows[key]
        binding = successor.bindings[key]
        correspondence.append(
            MappingProxyType(
                {
                    "parent_intent_id": unresolved["intent_id"],
                    "semantic_key": key,
                    "expected_schema": unresolved["value_schema"],
                    "expected_unit_context_ref": unresolved["unit_context_ref"],
                    "expected_source_artifact_id": "task_envelope",
                    "expected_source_pointer": unresolved[
                        "expected_source_location"
                    ]["json_pointer"],
                    "successor_envelope_fingerprint": successor.artifact_fingerprint,
                    "successor_binding_id": binding["binding_id"],
                    "successor_binding_pointer": binding["json_pointer"],
                }
            )
        )

    clause_occurrences = _clause_occurrences(parent_recipe)
    affected_ids = sorted(
        {
            clause_id
            for row in parent_recipe["unresolved_intent"]
            for clause_id in row["affected_clause_ids"]
        }
    )
    affected: list[dict[str, object]] = []
    for clause_id in affected_ids:
        matches = clause_occurrences.get(clause_id, [])
        if len(matches) != 1:
            raise ValueError("parent affected clause ownership is not unique")
        category, pointer, _clause = matches[0]
        affected.append(
            {"clause_id": clause_id, "category": category, "pointer": pointer}
        )
    parent_reference_occurrences = _external_reference_occurrences(parent_recipe)
    unresolved_prefixes = tuple(
        f"/unresolved_intent/{index}"
        for index, _row in enumerate(parent_recipe["unresolved_intent"])
    )
    descriptor_removal_eligible_ids: list[str] = []
    descriptor_reference_ledger: list[dict[str, object]] = []
    for descriptor in parent_recipe["authority_artifacts"]:
        artifact_id = descriptor["artifact_id"]
        occurrences = tuple(
            row
            for row in parent_reference_occurrences
            if row["artifact_id"] == artifact_id
        )
        if not occurrences:
            raise ValueError("parent authority descriptor has no reference")
        exclusively_removed = all(
            any(
                row["pointer"] == prefix
                or row["pointer"].startswith(prefix + "/")
                for prefix in unresolved_prefixes
            )
            for row in occurrences
        )
        if exclusively_removed:
            descriptor_removal_eligible_ids.append(artifact_id)
        descriptor_reference_ledger.append(
            {
                "artifact_id": artifact_id,
                "reference_occurrences": [dict(row) for row in occurrences],
                "references_exclusively_in_removed_unresolved_rows": (
                    exclusively_removed
                ),
            }
        )
    policy_instance_value = {
        "definition_id": policy["definition_id"],
        "definition_fingerprint": policy["policy_fingerprint"],
        "parent_recipe_fingerprint": parent_recipe["recipe_fingerprint"],
        "successor_envelope_fingerprint": successor.artifact_fingerprint,
        "correspondence_fingerprint": PLANNER_SUPPORT.fingerprint(correspondence),
        "affected_clauses": affected,
        "descriptor_removal_eligible_ids": descriptor_removal_eligible_ids,
        "descriptor_reference_ledger": descriptor_reference_ledger,
        "model_obligations": copy.deepcopy(policy["model_obligations"]),
    }
    policy_instance = IsolationPolicyInstance(
        definition_id=policy["definition_id"],
        definition_fingerprint=policy["policy_fingerprint"],
        value=MappingProxyType(policy_instance_value),
        instance_fingerprint=PLANNER_SUPPORT.fingerprint(policy_instance_value),
    )
    inputs_identity = {
        "parent_recipe_raw_sha256": PLANNER_SUPPORT.sha256_prefixed(
            source.final_recipe_bytes
        ),
        "successor_envelope_raw_sha256": PLANNER_SUPPORT.sha256_prefixed(
            successor_raw
        ),
        "successor_envelope_fingerprint": successor.artifact_fingerprint,
        "carrier_compatibility_fingerprint": qualification_proof[
            "compatibility_fingerprint"
        ],
        "migration_fingerprint": PLANNER_SUPPORT.fingerprint(migration),
        "correspondence_fingerprint": PLANNER_SUPPORT.fingerprint(correspondence),
        "policy_instance_fingerprint": policy_instance.instance_fingerprint,
        "evaluation_rubric_fingerprint": rubric["rubric_fingerprint"],
        "carrier_support_fingerprint": carrier_support[
            "carrier_support_fingerprint"
        ],
        "reviewed_commit_sha": reviewed_commit,
    }
    return VerifiedResolutionInputs(
        parent_recipe_bytes=source.final_recipe_bytes,
        parent_recipe=MappingProxyType(parent_recipe),
        successor_envelope_bytes=successor_raw,
        successor_envelope=successor.envelope,
        current_authority=current_authority,
        carrier_support_instrument=_freeze_json(carrier_support),
        recipe_schema=frozen.recipe_schema,
        normalization_profile=current_authority.normalization_profile,
        exclusion_policy=frozen.exclusion_policy,
        brief=frozen.brief,
        authoring_contract=frozen.authoring_contract,
        evaluation_rubric=MappingProxyType(rubric),
        correspondence=tuple(correspondence),
        migration_ledger=tuple(migration),
        policy_instance=policy_instance,
        historical_qualification_identity=(
            qualification_proof["historical_qualification_identity"]
        ),
        carrier_compatibility_fingerprint=(
            qualification_proof["compatibility_fingerprint"]
        ),
        reviewed_commit_sha=reviewed_commit,
        inputs_fingerprint=PLANNER_SUPPORT.fingerprint(inputs_identity),
    )


def render_planner_revision_request(
    inputs: VerifiedResolutionInputs,
) -> RenderedRevisionRequest:
    if type(inputs) is not VerifiedResolutionInputs:
        raise TypeError("verified resolution inputs are required")
    payload = {
        "schema": "rook.lm9b_p.planner_revision_request:v1",
        "renderer_id": REVISION_RENDERER_ID,
        "brief": inputs.brief,
        "parent_recipe_json": inputs.parent_recipe_bytes.decode("utf-8"),
        "successor_authority": {
            "artifacts": inputs.current_authority.artifacts,
        },
        "carrier_support_instrument": inputs.carrier_support_instrument,
        "clarification_correspondence": inputs.correspondence,
        "recipe_schema": inputs.recipe_schema,
        "authoring_contract": inputs.authoring_contract,
        "isolation_policy": {
            "definition_id": inputs.policy_instance.definition_id,
            "definition_fingerprint": inputs.policy_instance.definition_fingerprint,
            "instance_fingerprint": inputs.policy_instance.instance_fingerprint,
            "model_obligations": inputs.policy_instance.value["model_obligations"],
        },
        "terminal_submission_contract": PLANNER_SUPPORT.planner_tool_definition(),
    }
    raw = _canonical_bytes(payload)
    return RenderedRevisionRequest(
        renderer_id=REVISION_RENDERER_ID,
        payload=MappingProxyType(payload),
        raw_bytes=raw,
        raw_sha256=PLANNER_SUPPORT.sha256_prefixed(raw),
        canonical_fingerprint=PLANNER_SUPPORT.fingerprint(payload),
    )


def render_planner_revision_evaluation_request(
    inputs: VerifiedResolutionInputs,
    *,
    candidate_recipe_bytes: bytes,
) -> RenderedRevisionRequest:
    if type(inputs) is not VerifiedResolutionInputs:
        raise TypeError("verified resolution inputs are required")
    if type(candidate_recipe_bytes) is not bytes:
        raise TypeError("exact candidate recipe bytes are required")
    candidate = PLANNER_SUPPORT.parse_strict_json(candidate_recipe_bytes)
    if type(candidate) is not dict:
        raise ValueError("candidate recipe must be an object")
    payload = {
        "schema": "rook.lm9b_p.planner_revision_evaluation_request:v1",
        "renderer_id": REVISION_EVALUATION_RENDERER_ID,
        "brief": inputs.brief,
        "successor_authority": {
            "artifacts": inputs.current_authority.artifacts,
        },
        "final_recipe_json": candidate_recipe_bytes.decode("utf-8"),
        "final_recipe_raw_sha256": PLANNER_SUPPORT.sha256_prefixed(
            candidate_recipe_bytes
        ),
        "evaluation_rubric": inputs.evaluation_rubric,
        "evaluation_report_contract": {
            "argument": "evaluation_json",
            "report_schema": PLANNER_SUPPORT.PLANNER_EVALUATION_REPORT_SCHEMA,
            "recommendation_meanings": (
                PLANNER_SUPPORT.PLANNER_EVALUATION_RECOMMENDATION_MEANINGS
            ),
        },
    }
    raw = _canonical_bytes(payload)
    return RenderedRevisionRequest(
        renderer_id=REVISION_EVALUATION_RENDERER_ID,
        payload=MappingProxyType(payload),
        raw_bytes=raw,
        raw_sha256=PLANNER_SUPPORT.sha256_prefixed(raw),
        canonical_fingerprint=PLANNER_SUPPORT.fingerprint(payload),
    )


def evaluate_resolution_isolation(
    *,
    inputs: VerifiedResolutionInputs,
    candidate_recipe_bytes: bytes,
) -> IsolationGateResult:
    parent = copy.deepcopy(dict(inputs.parent_recipe))
    candidate = PLANNER_SUPPORT.parse_strict_json(candidate_recipe_bytes)
    if type(candidate) is not dict:
        raise ValueError("candidate recipe must be an object")
    equations: list[Mapping[str, object]] = []
    differences: list[Mapping[str, object]] = []
    successor_fingerprint = inputs.successor_envelope["artifact_fingerprint"]

    expected_source = copy.deepcopy(parent["source_task"])
    expected_source["fingerprint"] = successor_fingerprint
    source_ok = candidate.get("source_task") == expected_source
    equations.append(_equation("source_descriptor", source_ok))

    unresolved_ok = candidate.get("unresolved_intent") == []
    equations.append(_equation("resolved_unresolved_rows", unresolved_ok))
    candidate_reference_occurrences = _external_reference_occurrences(candidate)
    referenced_candidate_artifacts = {
        row["artifact_id"] for row in candidate_reference_occurrences
    }
    eligible_ids = tuple(
        inputs.policy_instance.value["descriptor_removal_eligible_ids"]
    )
    removable_ids = tuple(
        artifact_id
        for artifact_id in eligible_ids
        if artifact_id not in referenced_candidate_artifacts
    )
    expected_descriptors = [
        copy.deepcopy(descriptor)
        for descriptor in parent["authority_artifacts"]
        if descriptor["artifact_id"] not in removable_ids
    ]
    descriptor_ok = candidate.get("authority_artifacts") == expected_descriptors
    equations.append(
        _equation("authority_descriptor_reachability", descriptor_ok)
    )
    expected_goal = copy.deepcopy(parent["goal"])
    expected_goal["projected_into"]["unresolved_intent_ids"] = []
    goal_ok = candidate.get("goal") == expected_goal
    equations.append(_equation("goal_projection", goal_ok))

    parent_occurrences = _clause_occurrences(parent)
    candidate_occurrences = _clause_occurrences(candidate)
    required_refs_by_clause: dict[str, list[dict[str, object]]] = {}
    for row in inputs.correspondence:
        intent = next(
            item
            for item in parent["unresolved_intent"]
            if item["intent_id"] == row["parent_intent_id"]
        )
        reference = {
            "kind": "artifact_value",
            "artifact_id": "task_envelope",
            "json_pointer": row["successor_binding_pointer"],
        }
        for clause_id in intent["affected_clause_ids"]:
            required_refs_by_clause.setdefault(clause_id, []).append(reference)

    clause_ownership_ok = True
    affected_clause_residual_ok = True
    reference_ok = True
    for row in inputs.policy_instance.value["affected_clauses"]:
        clause_id = row["clause_id"]
        parent_matches = parent_occurrences.get(clause_id, [])
        candidate_matches = candidate_occurrences.get(clause_id, [])
        if (
            len(parent_matches) != 1
            or len(candidate_matches) != 1
            or candidate_matches[0][0] != row["category"]
            or candidate_matches[0][1] != row["pointer"]
        ):
            clause_ownership_ok = False
            continue
        parent_clause = parent_matches[0][2]
        candidate_clause = candidate_matches[0][2]
        expected_refs = _ordered_unique_references(
            [*parent_clause["source_refs"], *required_refs_by_clause[clause_id]]
        )
        candidate_refs = candidate_clause.get("source_refs")
        if (
            type(candidate_refs) is not list
            or candidate_refs != expected_refs
            or len(candidate_refs)
            != len({_canonical_bytes(item) for item in candidate_refs})
        ):
            reference_ok = False
        parent_rest = {
            key: value for key, value in parent_clause.items() if key != "source_refs"
        }
        candidate_rest = {
            key: value
            for key, value in candidate_clause.items()
            if key != "source_refs"
        }
        if parent_rest != candidate_rest:
            affected_clause_residual_ok = False
    equations.append(_equation("clause_ownership", clause_ownership_ok))
    equations.append(_equation("authority_reference_additions", reference_ok))
    equations.append(
        _equation("affected_clause_residual", affected_clause_residual_ok)
    )

    claimed = candidate.get("recipe_fingerprint")
    candidate_projection = {
        key: value for key, value in candidate.items() if key != "recipe_fingerprint"
    }
    normalized_candidate = PLANNER_SUPPORT.normalize_recipe(
        copy.deepcopy(candidate_projection), inputs.normalization_profile
    )
    fingerprint_ok = claimed == PLANNER_SUPPORT.fingerprint(normalized_candidate)
    equations.append(_equation("recipe_fingerprint", fingerprint_ok))

    parent_projection = {
        key: value for key, value in parent.items() if key != "recipe_fingerprint"
    }
    normalized_parent = PLANNER_SUPPORT.normalize_recipe(
        copy.deepcopy(parent_projection), inputs.normalization_profile
    )
    parent_residual = copy.deepcopy(normalized_parent)
    candidate_residual = copy.deepcopy(normalized_candidate)
    parent_residual["source_task"]["fingerprint"] = None
    candidate_residual["source_task"]["fingerprint"] = None
    parent_residual["unresolved_intent"] = []
    candidate_residual["unresolved_intent"] = []
    if descriptor_ok:
        parent_residual["authority_artifacts"] = []
        candidate_residual["authority_artifacts"] = []
    parent_residual["goal"]["projected_into"]["unresolved_intent_ids"] = []
    candidate_residual["goal"]["projected_into"]["unresolved_intent_ids"] = []
    for row in inputs.policy_instance.value["affected_clauses"]:
        _clause_at_pointer(parent_residual, row["pointer"])["source_refs"] = []
        _clause_at_pointer(candidate_residual, row["pointer"])["source_refs"] = []
    parent_residual_bytes = _canonical_bytes(parent_residual)
    candidate_residual_bytes = _canonical_bytes(candidate_residual)
    residual_ok = parent_residual_bytes == candidate_residual_bytes
    equations.append(_equation("residual_equality", residual_ok))
    for equation in equations:
        if not equation["passed"]:
            differences.append(
                MappingProxyType(
                    {
                        "equation_id": equation["equation_id"],
                        "difference": "candidate differs from permitted delta",
                    }
                )
            )
    status = "isolated" if not differences else "isolation_rejected"
    result_value = {
        "status": status,
        "equations": equations,
        "bounded_differences": differences,
        "parent_residual_raw_sha256": PLANNER_SUPPORT.sha256_prefixed(
            parent_residual_bytes
        ),
        "candidate_residual_raw_sha256": PLANNER_SUPPORT.sha256_prefixed(
            candidate_residual_bytes
        ),
    }
    return IsolationGateResult(
        status=status,
        equations=tuple(equations),
        bounded_differences=tuple(differences),
        parent_residual_bytes=parent_residual_bytes,
        candidate_residual_bytes=candidate_residual_bytes,
        result_fingerprint=PLANNER_SUPPORT.fingerprint(result_value),
    )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        PLANNER_SUPPORT._json_builtins(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _clause_occurrences(
    recipe: Mapping[str, object],
) -> dict[str, list[tuple[str, str, Mapping[str, object]]]]:
    rows: list[tuple[str, str, Mapping[str, object]]] = []
    goal = recipe.get("goal")
    if isinstance(goal, Mapping):
        rows.append(("goal", "/goal", goal))
    for category in ("requires", "invariants"):
        collection = recipe.get(category)
        if isinstance(collection, list):
            rows.extend(
                (category, f"/{category}/{index}", clause)
                for index, clause in enumerate(collection)
                if isinstance(clause, Mapping)
            )
    maintains = recipe.get("maintains")
    if isinstance(maintains, list):
        for index, clause in enumerate(maintains):
            if not isinstance(clause, Mapping):
                continue
            rows.append(("maintains", f"/maintains/{index}", clause))
            for nested_category in ("canonicalization", "postconditions"):
                nested = clause.get(nested_category)
                if isinstance(nested, list):
                    rows.extend(
                        (
                            nested_category,
                            f"/maintains/{index}/{nested_category}/{nested_index}",
                            item,
                        )
                        for nested_index, item in enumerate(nested)
                        if isinstance(item, Mapping)
                    )
    by_id: dict[str, list[tuple[str, str, Mapping[str, object]]]] = {}
    for category, pointer, clause in rows:
        clause_id = clause.get("clause_id")
        if isinstance(clause_id, str):
            by_id.setdefault(clause_id, []).append((category, pointer, clause))
    return by_id


def _clause_at_pointer(recipe: dict[str, object], pointer: object) -> dict[str, object]:
    if type(pointer) is not str:
        raise ValueError("clause pointer must be a string")
    value = PLANNER_SUPPORT.resolve_json_pointer(recipe, pointer)
    if type(value) is not dict:
        raise ValueError("clause pointer does not resolve to an object")
    return value


def _ordered_unique_references(
    references: list[Mapping[str, object]],
) -> list[dict[str, object]]:
    values = [copy.deepcopy(dict(item)) for item in references]
    values.sort(key=_canonical_bytes)
    if len(values) != len({_canonical_bytes(item) for item in values}):
        raise ValueError("reference collection contains a duplicate")
    return values


def _external_reference_occurrences(
    value: object,
    pointer: str = "",
) -> tuple[Mapping[str, object], ...]:
    rows: list[Mapping[str, object]] = []
    if isinstance(value, Mapping):
        kind = value.get("kind")
        artifact_id = value.get("artifact_id")
        if kind in ("artifact_value", "policy_rule") and type(artifact_id) is str:
            rows.append(
                MappingProxyType(
                    {
                        "artifact_id": artifact_id,
                        "kind": kind,
                        "pointer": pointer,
                    }
                )
            )
        for key, item in value.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            rows.extend(
                _external_reference_occurrences(item, f"{pointer}/{escaped}")
            )
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            rows.extend(
                _external_reference_occurrences(item, f"{pointer}/{index}")
            )
    return tuple(rows)


def _equation(equation_id: str, passed: bool) -> Mapping[str, object]:
    return MappingProxyType({"equation_id": equation_id, "passed": passed})


__all__ = (
    "IsolationGateResult",
    "IsolationPolicyInstance",
    "RenderedRevisionRequest",
    "VerifiedResolutionInputs",
    "assemble_verified_resolution_inputs",
    "evaluate_resolution_isolation",
    "render_planner_revision_request",
    "render_planner_revision_evaluation_request",
)
