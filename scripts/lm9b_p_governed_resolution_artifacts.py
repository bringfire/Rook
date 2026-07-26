"""Evidence and preflight contracts for the governed-resolution checkpoint."""

from __future__ import annotations

import hashlib
import base64
import inspect
import json
import re
import stat
import subprocess
import sys
import weakref
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _import_path in (_SCRIPTS_DIR, _MCP_SRC):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

import lm9b_p_governed_resolution_support as SUPPORT
import lm9b_p_planner_recipe_transfer_artifacts as PLANNER_ARTIFACTS
import lm9b_p_planner_recipe_transfer_support as PLANNER_SUPPORT
import lm9b_p_evaluator_only_continuation_artifacts as CONT_ARTIFACTS
import lm9b_p_readiness_contract as READINESS
import lm9_semantic_typed_values as TYPED_VALUES
import lm9_typed_fact_carrier_artifacts as CARRIER
import lm9_typed_fact_carrier_qualification as QUALIFICATION


HISTORICAL_CARRIER_COMMIT = "d6330a61a21d56abf16af6ba3b8f1678ede2c3ec"
HISTORICAL_CARRIER_QUALIFICATION = Path(
    r"C:\Users\bring\rook-lm9b-p-attempts"
    r"\2026-07-23-typed-fact-carrier-post-merge"
    r"\d6330a61a21d56abf16af6ba3b8f1678ede2c3ec"
)
HISTORICAL_CARRIER_QUALIFICATION_IDENTITY = (
    "sha256:ad12f0cec491b64f51982b7069acfa1301c1d577071cff9498cf7fba260446e1"
)
OFFICIAL_DERIVATIVE = CARRIER.OFFICIAL_DERIVATIVE
OFFICIAL_DERIVATIVE_IDENTITY = CARRIER.OFFICIAL_DERIVATIVE_IDENTITY
SUCCESSOR_ENVELOPE_PATH = CARRIER.RADIAL_FIXTURE_PATH
ISOLATION_POLICY_PATH = (
    _SCRIPTS_DIR
    / "lm9b_p_governed_resolution_contracts"
    / "isolation_policy.json"
)
EVALUATION_RUBRIC_PATH = (
    _SCRIPTS_DIR
    / "lm9b_p_governed_resolution_contracts"
    / "planner_revision_evaluation_rubric.json"
)
PREFLIGHT_SCHEMA_ID = "rook.lm9b_p.governed_resolution_preflight:v1"
CHECKPOINT_SCHEMA_ID = "rook.lm9b_p.governed_resolution_checkpoint:v1"
ATTEMPT_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
ATTEMPT_ID_MAX_LENGTH = 64
INVOCATION_SCHEMA_ID = "rook.lm9b_p.governed_resolution_invocation_binding:v1"
_READY_PROOF_VALUE = {
    "contract_id": "lm9b_p.governed_resolution_ready_proof:v1",
    "closed_fields": [
        "checkpoint_identity",
        "exact_recipe_bytes",
        "recipe_fingerprint",
        "successor_authority_records",
        "mechanical_gate_fingerprint",
        "isolation_result_fingerprint",
    ],
    "issuance_predicate": (
        "publicly reconstructed probe_candidate_ready checkpoint only"
    ),
    "reconstruction": "rerun public checkpoint verifier at bound destination",
}
_READY_PROOF_VALUE["contract_fingerprint"] = PLANNER_SUPPORT.fingerprint(
    _READY_PROOF_VALUE
)
READY_PROOF_CONTRACT = MappingProxyType(_READY_PROOF_VALUE)
CONTRACT_IDS = MappingProxyType(
    {
        "blocker_projection": "lm9b_p.explicit_blocker_projection:v1",
        "classifier": "lm9b_p.evaluated_recipe_classification:v1",
        "outcome_equations": "lm9b_p.governed_resolution_outcome_equations:v1",
        "archive_seal": "lm9b_p.governed_resolution_archive_seal:v1",
        "public_verifier": "lm9b_p.governed_resolution_public_verifier:v1",
        "ready_proof": "lm9b_p.governed_resolution_ready_proof:v1",
        "readiness_schema": READINESS.SCHEMA_ID,
        "readiness_verifier": "lm9b_p.readiness_launch_verifier:v1",
    }
)
_PREFLIGHT_MEMBERS = frozenset(
    {"record.json", "initial-request.json", "checksums.json"}
)
_CHECKPOINT_MEMBERS = frozenset(
    {
        "record.json",
        "preflight.json",
        "readiness.json",
        "planner-session.json",
        "candidate-recipe.json",
        "checkpoint-gate.json",
        "isolation.json",
        "evaluator.json",
        "classification.json",
        "checksums.json",
    }
)


@dataclass(frozen=True)
class ResolutionInstrument:
    inputs: SUPPORT.VerifiedResolutionInputs
    initial_request: SUPPORT.RenderedRevisionRequest
    contract_manifest: Mapping[str, object]
    instrument_fingerprint: str


@dataclass(frozen=True, eq=False)
class VerifiedResolutionSources:
    historical_source: CONT_ARTIFACTS.VerifiedHistoricalSource
    parent_derivative: CONT_ARTIFACTS.SealedDerivative
    carrier_qualification: VerifiedCarrierQualificationCompatibility
    exact_successor_bytes: bytes
    exact_contract_bytes: Mapping[str, bytes]
    reviewed_commit_sha: str


@dataclass(frozen=True, eq=False)
class VerifiedCarrierQualificationCompatibility:
    archive_dir: Path
    historical_qualification_identity: str
    historical_commit_sha: str
    consuming_commit_sha: str
    comparison_rows: tuple[Mapping[str, object], ...]
    compatibility_fingerprint: str


@dataclass(frozen=True)
class AttemptBinding:
    attempt_id: str
    resolution_root: Path
    destination: Path
    staging_path: Path
    attempt_fingerprint: str


@dataclass(frozen=True)
class VerifiedResolutionPreflight:
    archive_dir: Path
    record: Mapping[str, object]
    preflight_fingerprint: str
    instrument_fingerprint: str
    attempt: AttemptBinding
    instrument: ResolutionInstrument


@dataclass(frozen=True)
class SealedResolutionCheckpoint:
    archive_dir: Path
    checkpoint_identity: str
    classification: str
    exact_recipe_bytes: bytes | None
    state: str = "sealed"


def _load_verified_resolution_sources_unsealed(
    **_kwargs: object,
) -> tuple[VerifiedResolutionSources, Mapping[str, object]]:
    required = {
        "historical_source_dir",
        "derivative_archive",
        "derivative_identity",
        "carrier_qualification_archive",
        "carrier_qualification_identity",
        "repo_root",
        "successor_envelope_path",
    }
    if set(_kwargs) != required:
        raise ValueError("resolution source set is incomplete or contains extras")
    historical_dir = Path(_kwargs["historical_source_dir"]).resolve()
    derivative_archive = Path(_kwargs["derivative_archive"]).resolve()
    qualification_archive = Path(
        _kwargs["carrier_qualification_archive"]
    ).resolve()
    repo_root = Path(_kwargs["repo_root"]).resolve()
    successor_path = Path(_kwargs["successor_envelope_path"]).resolve()
    if historical_dir != CONT_ARTIFACTS.PRODUCTION_SOURCE_PINS.source_root.resolve():
        raise ValueError("historical source location differs from production pin")
    if (
        derivative_archive != OFFICIAL_DERIVATIVE.resolve()
        or _kwargs["derivative_identity"] != OFFICIAL_DERIVATIVE_IDENTITY
    ):
        raise ValueError("official derivative path or identity differs from pin")
    if successor_path != SUCCESSOR_ENVELOPE_PATH.resolve():
        raise ValueError("successor envelope location differs from reviewed fixture")
    reviewed_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _require_reviewed_file(
        repo_root, successor_path, reviewed_commit, label="successor envelope"
    )
    _require_reviewed_file(
        repo_root,
        CARRIER.PAYLOAD_SCHEMA_PATH.resolve(),
        reviewed_commit,
        label="forward payload schema",
    )
    _require_reviewed_file(
        repo_root,
        CARRIER.REGISTRY_PATH.resolve(),
        reviewed_commit,
        label="semantic value registry",
    )
    source = CONT_ARTIFACTS.verify_historical_source()
    if source.source_root.resolve() != historical_dir:
        raise ValueError("historical verifier returned a different source")
    derivative = CONT_ARTIFACTS.verify_sealed_derivative_archive(
        derivative_archive,
        expected_derivative_identity=_kwargs["derivative_identity"],
    )
    qualification = verify_historical_carrier_qualification_compatibility(
        archive_dir=qualification_archive,
        expected_identity=_kwargs["carrier_qualification_identity"],
        repo_root=repo_root,
        consuming_commit_sha=reviewed_commit,
    )
    successor_raw = successor_path.read_bytes()
    contract_bytes = MappingProxyType(
        {
            "forward_payload_schema": CARRIER.PAYLOAD_SCHEMA_PATH.read_bytes(),
            "semantic_value_registry": CARRIER.REGISTRY_PATH.read_bytes(),
        }
    )
    runtime = TYPED_VALUES.current_runtime_identity()
    registry = CARRIER._verified_registry(
        contract_bytes["semantic_value_registry"], runtime
    )
    records = {record.role: record for record in source.input_records}
    attempt_context = records["attempt_context"].value
    environment = records["authority.environment_snapshot"].value
    if not isinstance(attempt_context, Mapping) or not isinstance(
        environment, Mapping
    ):
        raise ValueError("historical authority records are invalid")
    issuer = environment.get("issuer")
    if not isinstance(issuer, Mapping):
        raise ValueError("historical environment issuer is invalid")
    unit_context_index = TYPED_VALUES.derive_verified_unit_context_index(
        environment_artifact_bytes=records[
            "authority.environment_snapshot"
        ].raw_bytes,
        environment_payload_schema_bytes=CARRIER._environment_payload_schema_bytes(
            records
        ),
        attempt_context_bytes=records["attempt_context"].raw_bytes,
        expected_artifact_fingerprint=environment["artifact_fingerprint"],
        expected_issuer_id=issuer["authority_id"],
        expected_environment_session_id=attempt_context["environment_session_id"],
        expected_task_session_id=attempt_context["task_session_id"],
        evaluated_at=attempt_context["evaluated_at"],
    )
    successor = CARRIER.validate_forward_task_envelope(
        successor_raw,
        payload_schema_raw_bytes=contract_bytes["forward_payload_schema"],
        registry_raw_bytes=contract_bytes["semantic_value_registry"],
        unit_context_index=unit_context_index,
        runtime=runtime,
    )
    parent_recipe = TYPED_VALUES.parse_strict_json(
        source.final_recipe_bytes, label="blocked parent recipe"
    )
    if type(parent_recipe) is not dict:
        raise ValueError("blocked parent recipe must be an object")
    parent_values = CARRIER.reconstruct_observed_historical_task_values(
        source,
        registry=registry,
        unit_context_index=unit_context_index,
    )
    parent_bindings = CARRIER.historical_task_bindings(source)
    partition = CARRIER.derive_authority_partition(
        parent_values=parent_values,
        parent_bindings=parent_bindings,
        successor=successor,
        parent_recipe=parent_recipe,
    )
    migration = CARRIER.verify_exact_migration(
        parent_values=parent_values,
        parent_bindings=parent_bindings,
        successor=successor,
        partition=partition,
    )
    carrier = VerifiedResolutionSources(
        historical_source=source,
        parent_derivative=derivative,
        carrier_qualification=qualification,
        exact_successor_bytes=successor_raw,
        exact_contract_bytes=contract_bytes,
        reviewed_commit_sha=reviewed_commit,
    )
    projection = MappingProxyType(
        {
            "historical_source": source,
            "parent_derivative": derivative,
            "carrier_qualification": qualification,
            "runtime": runtime,
            "registry": registry,
            "unit_context_index": unit_context_index,
            "successor": successor,
            "parent_recipe": MappingProxyType(parent_recipe),
            "parent_values": parent_values,
            "parent_bindings": parent_bindings,
            "partition": partition,
            "migration": tuple(migration),
        }
    )
    return carrier, projection


def _seal_resolution_source_loader(loader):
    issued: weakref.WeakKeyDictionary[
        VerifiedResolutionSources, Mapping[str, object]
    ] = weakref.WeakKeyDictionary()

    def load_and_issue(**kwargs: object) -> VerifiedResolutionSources:
        result, projection = loader(**kwargs)
        if type(result) is not VerifiedResolutionSources:
            raise TypeError("resolution source loader returned the wrong carrier")
        issued[result] = MappingProxyType(
            {
                "snapshot": _resolution_sources_snapshot(result),
                "projection": projection,
            }
        )
        return result

    def consume(value: object) -> Mapping[str, object]:
        if type(value) is not VerifiedResolutionSources:
            raise TypeError("closure-issued resolution sources are required")
        retained = issued.get(value)
        if (
            retained is None
            or retained["snapshot"] != _resolution_sources_snapshot(value)
        ):
            raise ValueError("resolution sources are not closure-issued")
        return retained["projection"]

    return load_and_issue, consume


def _resolution_sources_snapshot(value: VerifiedResolutionSources) -> dict[str, object]:
    return {
        "historical_source_identity": dict(value.historical_source.identity_value),
        "parent_derivative_identity": value.parent_derivative.derivative_archive_identity,
        "carrier_compatibility_fingerprint": (
            value.carrier_qualification.compatibility_fingerprint
        ),
        "successor_raw_sha256": _sha256(value.exact_successor_bytes),
        "contract_raw_sha256": {
            key: _sha256(raw) for key, raw in value.exact_contract_bytes.items()
        },
        "reviewed_commit_sha": value.reviewed_commit_sha,
    }


load_verified_resolution_sources, consume_verified_resolution_sources = (
    _seal_resolution_source_loader(_load_verified_resolution_sources_unsealed)
)


def assemble_resolution_instrument(**_kwargs: object) -> ResolutionInstrument:
    if set(_kwargs) != {
        "sources",
        "isolation_policy_path",
        "evaluation_rubric_path",
    }:
        raise ValueError("resolution instrument inputs are incomplete or contain extras")
    sources = _kwargs["sources"]
    consume_verified_resolution_sources(sources)
    policy_path = Path(_kwargs["isolation_policy_path"]).resolve()
    rubric_path = Path(_kwargs["evaluation_rubric_path"]).resolve()
    if (
        policy_path != ISOLATION_POLICY_PATH.resolve()
        or rubric_path != EVALUATION_RUBRIC_PATH.resolve()
    ):
        raise ValueError("resolution contract path differs from reviewed source")
    inputs = SUPPORT.assemble_verified_resolution_inputs(
        sources=sources,
        isolation_policy_bytes=policy_path.read_bytes(),
        evaluation_rubric_bytes=rubric_path.read_bytes(),
    )
    return assemble_task1_resolution_instrument(inputs)


def assemble_task1_resolution_instrument(
    inputs: SUPPORT.VerifiedResolutionInputs,
) -> ResolutionInstrument:
    if type(inputs) is not SUPPORT.VerifiedResolutionInputs:
        raise TypeError("verified resolution inputs are required")
    initial = SUPPORT.render_planner_revision_request(inputs)
    readiness_manifest = READINESS.derive_routes(
        READINESS.role_routes_from_models(
            {"planner": "gpt-5.4", "planner_evaluator": "gpt-5.4"}
        ),
        lambda _model: "OPENAI_API_KEY",
    )
    readiness_route_roles = readiness_route_role_projection(readiness_manifest)
    outcome_table = {
        "mechanically_rejected": "probe_mechanically_rejected",
        "isolation_rejected": "probe_resolution_isolation_failure",
        "semantically_unfaithful": "probe_planner_failure",
        "semantically_faithful_without_blockers": "probe_candidate_ready",
        "provider_or_malformed_complete_evidence": "probe_inconclusive",
        "blocked_after_isolation": "integrity_failure_no_scientific_outcome",
    }
    manifest = {
        "schema": "rook.lm9b_p.governed_resolution_instrument_contracts:v1",
        "historical_qualification": {
            "identity": inputs.historical_qualification_identity,
            "commit_sha": HISTORICAL_CARRIER_COMMIT,
        },
        "carrier_forward_compatibility": {
            "fingerprint": inputs.carrier_compatibility_fingerprint,
            "consuming_commit_sha": inputs.reviewed_commit_sha,
        },
        "verified_inputs": {
            "inputs_fingerprint": inputs.inputs_fingerprint,
            "physical_source_loader_source_fingerprint": (
                _callable_source_fingerprint(
                    _load_verified_resolution_sources_unsealed
                )
            ),
            "carrier_compatibility_verifier_source_fingerprint": (
                _callable_source_fingerprint(
                    _verify_historical_carrier_qualification_compatibility_unsealed
                )
            ),
            "pure_input_assembler_source_fingerprint": (
                _callable_source_fingerprint(
                    SUPPORT.assemble_verified_resolution_inputs
                )
            ),
            "parent_recipe_raw_sha256": _sha256(inputs.parent_recipe_bytes),
            "successor_envelope_raw_sha256": _sha256(
                inputs.successor_envelope_bytes
            ),
            "successor_envelope_fingerprint": inputs.successor_envelope[
                "artifact_fingerprint"
            ],
            "carrier_support_fingerprint": inputs.carrier_support_instrument[
                "carrier_support_fingerprint"
            ],
            "normalization_profile_fingerprint": (
                inputs.normalization_profile.profile_fingerprint
            ),
        },
        "planner": {
            "revision_renderer_id": initial.renderer_id,
            "revision_renderer_source_fingerprint": _callable_source_fingerprint(
                SUPPORT.render_planner_revision_request
            ),
            "initial_request_raw_sha256": initial.raw_sha256,
            "controller_source_fingerprint": _callable_source_fingerprint(
                PLANNER_SUPPORT.run_planner_session
            ),
            "provider_request_builder_source_fingerprint": (
                _callable_source_fingerprint(
                    PLANNER_SUPPORT.build_planner_provider_call_request
                )
            ),
            "feedback_renderer_source_fingerprint": _callable_source_fingerprint(
                PLANNER_SUPPORT.build_planner_mechanical_feedback_message
            ),
            "system_prompt_fingerprint": _sha256(
                SUPPORT.REVISION_SYSTEM_PROMPT.encode("utf-8")
            ),
            "tool_schema_fingerprint": PLANNER_SUPPORT.fingerprint(
                PLANNER_SUPPORT.planner_tool_definition()
            ),
            "mechanical_gate_source_fingerprint": _callable_source_fingerprint(
                PLANNER_SUPPORT.evaluate_mechanical_gate
            ),
            "diagnostic_vocabulary_fingerprint": PLANNER_SUPPORT.fingerprint(
                {
                    "contract": "source_defined_planner_diagnostics:v1",
                    "submission_parser_source": _callable_source_fingerprint(
                        PLANNER_SUPPORT.derive_planner_submission_from_message
                    ),
                    "mechanical_gate_source": _callable_source_fingerprint(
                        PLANNER_SUPPORT.evaluate_mechanical_gate
                    ),
                    "feedback_renderer_source": _callable_source_fingerprint(
                        PLANNER_SUPPORT.build_planner_mechanical_feedback_message
                    ),
                }
            ),
            "model": "gpt-5.4",
            "provider_profile": "litellm.completion.tool_calling.no_parallel:v1",
            "temperature": None,
            "temperature_field_present": False,
            "max_calls": PLANNER_SUPPORT.PLANNER_MAX_TURNS,
            "max_completion_tokens": PLANNER_SUPPORT.PLANNER_MAX_COMPLETION_TOKENS,
            "provider_timeout_s": PLANNER_SUPPORT.PLANNER_PROVIDER_TIMEOUT_S,
            "overall_deadline_s": PLANNER_SUPPORT.PLANNER_OVERALL_DEADLINE_S,
            "token_stop_threshold": PLANNER_SUPPORT.PLANNER_TOKEN_STOP_THRESHOLD,
            "cost_stop_threshold_usd": (
                PLANNER_SUPPORT.PLANNER_COST_STOP_THRESHOLD_USD
            ),
        },
        "isolation": {
            "definition_id": inputs.policy_instance.definition_id,
            "definition_fingerprint": inputs.policy_instance.definition_fingerprint,
            "instance_fingerprint": inputs.policy_instance.instance_fingerprint,
            "gate_source_fingerprint": _callable_source_fingerprint(
                SUPPORT.evaluate_resolution_isolation
            ),
        },
        "evaluator": {
            "renderer_id": SUPPORT.REVISION_EVALUATION_RENDERER_ID,
            "renderer_source_fingerprint": _callable_source_fingerprint(
                SUPPORT.render_planner_revision_evaluation_request
            ),
            "rubric_fingerprint": inputs.evaluation_rubric["rubric_fingerprint"],
            "report_schema_fingerprint": PLANNER_SUPPORT.fingerprint(
                PLANNER_SUPPORT.PLANNER_EVALUATION_REPORT_SCHEMA
            ),
            "recommendation_meanings_fingerprint": PLANNER_SUPPORT.fingerprint(
                PLANNER_SUPPORT.PLANNER_EVALUATION_RECOMMENDATION_MEANINGS
            ),
            "parser_source_fingerprint": _callable_source_fingerprint(
                PLANNER_SUPPORT.derive_planner_evaluation_result
            ),
            "provider_request_builder_source_fingerprint": (
                _callable_source_fingerprint(
                    PLANNER_SUPPORT.build_planner_evaluator_provider_call_request
                )
            ),
            "system_prompt_fingerprint": _sha256(
                PLANNER_SUPPORT.PLANNER_EVALUATOR_SYSTEM_PROMPT.encode("utf-8")
            ),
            "tool_schema_fingerprint": PLANNER_SUPPORT.fingerprint(
                PLANNER_SUPPORT.planner_evaluator_tool_definition()
            ),
            "model": "gpt-5.4",
            "provider_profile": "litellm.completion.tool_calling.no_parallel:v1",
            "temperature": None,
            "temperature_field_present": False,
            "max_calls": 1,
            "max_completion_tokens": (
                PLANNER_SUPPORT.PLANNER_EVALUATOR_MAX_COMPLETION_TOKENS
            ),
            "provider_timeout_s": (
                PLANNER_SUPPORT.PLANNER_EVALUATOR_PROVIDER_TIMEOUT_S
            ),
        },
        "decision": {
            "blocker_projection_contract_id": CONTRACT_IDS["blocker_projection"],
            "blocker_projection_source_fingerprint": _callable_source_fingerprint(
                PLANNER_ARTIFACTS.derive_probe_explicit_blockers
            ),
            "classifier_contract_id": CONTRACT_IDS["classifier"],
            "classifier_source_fingerprint": _callable_source_fingerprint(
                PLANNER_ARTIFACTS.derive_evaluated_recipe_classification
            ),
            "outcome_equations_contract_id": CONTRACT_IDS["outcome_equations"],
            "outcome_table": outcome_table,
            "outcome_table_fingerprint": PLANNER_SUPPORT.fingerprint(outcome_table),
        },
        "readiness": {
            "schema_id": CONTRACT_IDS["readiness_schema"],
            "verifier_contract_id": CONTRACT_IDS["readiness_verifier"],
            "verifier_source_fingerprint": _callable_source_fingerprint(
                READINESS.verify_launch_readiness
            ),
            "canary_protocol_fingerprint": READINESS.canary_protocol_fingerprint(),
            "route_manifest_fingerprint": readiness_manifest.manifest_fingerprint,
            "route_role_projection": readiness_route_roles,
            "route_role_projection_fingerprint": PLANNER_SUPPORT.fingerprint(
                readiness_route_roles
            ),
            "route_role_projection_source_fingerprint": (
                _callable_source_fingerprint(readiness_route_role_projection)
            ),
            "freshness_window_s": READINESS.FROZEN_MAX_AGE_S,
        },
        "preflight": {
            "schema_id": PREFLIGHT_SCHEMA_ID,
            "closed_members": sorted(_PREFLIGHT_MEMBERS),
            "writer_source_fingerprint": _callable_source_fingerprint(
                write_resolution_preflight
            ),
            "public_verifier_source_fingerprint": _callable_source_fingerprint(
                verify_resolution_preflight
            ),
            "reservation_source_fingerprint": _callable_source_fingerprint(
                reserve_resolution_staging
            ),
        },
        "archive": {
            "seal_contract_id": CONTRACT_IDS["archive_seal"],
            "seal_source_fingerprint": _callable_source_fingerprint(
                seal_task1_resolution_checkpoint
            ),
            "public_verifier_contract_id": CONTRACT_IDS["public_verifier"],
            "public_verifier_source_fingerprint": _callable_source_fingerprint(
                verify_sealed_resolution_checkpoint
            ),
            "closed_members": sorted(_CHECKPOINT_MEMBERS),
            "finalization_equation": "same_filesystem_no_clobber_path_rename:v1",
        },
        "launch_invocation": _launch_invocation_contract(),
        "ready_proof": dict(READY_PROOF_CONTRACT),
        "role_call_budgets": {
            "planner": PLANNER_SUPPORT.PLANNER_MAX_TURNS,
            "planner_evaluator": 1,
            "compiler": 0,
        },
        "reviewed_commit_sha": inputs.reviewed_commit_sha,
        "task1_stage": "task1_vertical_unhardened",
    }
    return ResolutionInstrument(
        inputs=inputs,
        initial_request=initial,
        contract_manifest=MappingProxyType(manifest),
        instrument_fingerprint=PLANNER_SUPPORT.fingerprint(manifest),
    )


def _verify_historical_carrier_qualification_compatibility_unsealed(
    *,
    archive_dir: Path,
    expected_identity: str,
    repo_root: Path,
    consuming_commit_sha: str,
) -> VerifiedCarrierQualificationCompatibility:
    archive = Path(archive_dir).resolve()
    repo = Path(repo_root).resolve()
    if archive != HISTORICAL_CARRIER_QUALIFICATION.resolve():
        raise ValueError("carrier qualification location differs from pinned evidence")
    if expected_identity != HISTORICAL_CARRIER_QUALIFICATION_IDENTITY:
        raise ValueError("carrier qualification expected identity differs from pin")
    members = {
        path.relative_to(archive).as_posix()
        for path in archive.rglob("*")
        if path.is_file()
    }
    if members != QUALIFICATION.FINAL_MEMBERS:
        raise ValueError("carrier qualification membership is not closed")
    checksums = _object_bytes((archive / "checksums.json").read_bytes(), "checksums")
    if (
        set(checksums)
        != {"schema", "canonical_destination", "members", "qualification_identity"}
        or checksums["schema"] != QUALIFICATION.CHECKSUMS_SCHEMA_ID
        or Path(checksums["canonical_destination"]).resolve() != archive
    ):
        raise ValueError("carrier qualification checksum identity is invalid")
    rows = checksums["members"]
    expected_paths = sorted(QUALIFICATION.FINAL_MEMBERS - {"checksums.json"})
    if type(rows) is not list or [row.get("path") for row in rows] != expected_paths:
        raise ValueError("carrier qualification checksum rows are invalid")
    rebuilt_rows: list[dict[str, object]] = []
    for row in rows:
        raw = (archive / row["path"]).read_bytes()
        raw_sha = _sha256(raw)
        if set(row) != {"path", "raw_sha256"} or row["raw_sha256"] != raw_sha:
            raise ValueError("carrier qualification member checksum mismatch")
        rebuilt_rows.append({"path": row["path"], "raw_sha256": raw_sha})
    identity_source = {
        "schema": QUALIFICATION.QUALIFICATION_SCHEMA_ID,
        "canonical_destination": str(archive),
        "members": rebuilt_rows,
    }
    identity = TYPED_VALUES.fingerprint(identity_source)
    if checksums["qualification_identity"] != identity or identity != expected_identity:
        raise ValueError("carrier qualification aggregate identity mismatch")
    snapshot = _object_bytes((archive / "snapshot.json").read_bytes(), "snapshot")
    record = _object_bytes((archive / "record.json").read_bytes(), "record")
    if (
        snapshot.get("commit_sha") != HISTORICAL_CARRIER_COMMIT
        or record.get("reviewed_commit") != HISTORICAL_CARRIER_COMMIT
        or record.get("snapshot_fingerprint") != snapshot.get("snapshot_fingerprint")
    ):
        raise ValueError("carrier qualification historical commit binding is invalid")
    snapshot_projection = {
        key: value for key, value in snapshot.items() if key != "snapshot_fingerprint"
    }
    if snapshot.get("snapshot_fingerprint") != TYPED_VALUES.fingerprint(
        snapshot_projection
    ):
        raise ValueError("carrier qualification snapshot fingerprint mismatch")
    runtime = TYPED_VALUES.current_runtime_identity()
    if snapshot.get("runtime") != TYPED_VALUES.runtime_identity_value(runtime):
        raise ValueError("carrier qualification runtime differs from current runtime")
    actual_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if consuming_commit_sha != actual_head:
        raise ValueError("resolution consuming commit differs from checkout")

    comparison_rows: list[Mapping[str, object]] = []

    def compare_raw(component: str, current_raw: bytes, qualified_raw: bytes) -> None:
        current_sha = _sha256(current_raw)
        qualified_sha = _sha256(qualified_raw)
        if current_raw != qualified_raw:
            raise ValueError(f"carrier compatibility drift: {component}")
        comparison_rows.append(
            MappingProxyType(
                {
                    "component": component,
                    "qualified_raw_sha256": qualified_sha,
                    "current_raw_sha256": current_sha,
                    "comparison": "exact_bytes_equal",
                }
            )
        )

    typed_path = "scripts/lm9_semantic_typed_values.py"
    carrier_path = "scripts/lm9_typed_fact_carrier_artifacts.py"
    typed_current = _git_object(repo, consuming_commit_sha, typed_path)
    typed_qualified = _git_object(repo, HISTORICAL_CARRIER_COMMIT, typed_path)
    _require_worktree_blob(repo, typed_path, HISTORICAL_CARRIER_COMMIT)
    compare_raw("lm9_semantic_typed_values.py", typed_current, typed_qualified)
    if _sha256(typed_current) != snapshot.get("helper_source_sha256"):
        raise ValueError("typed-value helper differs from qualified source hash")
    compare_raw(
        "lm9_typed_fact_carrier_artifacts.py",
        _git_object(repo, consuming_commit_sha, carrier_path),
        _git_object(repo, HISTORICAL_CARRIER_COMMIT, carrier_path),
    )
    _require_worktree_blob(repo, carrier_path, HISTORICAL_CARRIER_COMMIT)
    compare_raw(
        "semantic_value_schema_registry.json",
        CARRIER.REGISTRY_PATH.read_bytes(),
        (archive / "contracts/semantic-value-registry.json").read_bytes(),
    )
    compare_raw(
        "planner_task_typed_facts_payload_schema.json",
        CARRIER.PAYLOAD_SCHEMA_PATH.read_bytes(),
        (archive / "contracts/task-payload-schema.json").read_bytes(),
    )
    profile_value = TYPED_VALUES.build_profile_identity(runtime)
    archived_profile = _object_bytes(
        (archive / "contracts/profile.json").read_bytes(), "profile"
    )
    current_profile = CARRIER.value_for_evidence(profile_value.value)
    if archived_profile != current_profile:
        raise ValueError("carrier JSON-Schema profile differs from qualification")
    component_identities = {
        "helper_contract_id": TYPED_VALUES.HELPER_CONTRACT_ID,
        "profile_id": TYPED_VALUES.PROFILE_ID,
        "profile_fingerprint": profile_value.fingerprint,
        "registry_schema_id": TYPED_VALUES.REGISTRY_SCHEMA_ID,
        "registry_version": TYPED_VALUES.REGISTRY_VERSION,
        "registry_fingerprint": TYPED_VALUES.SEMANTIC_VALUE_REGISTRY_FINGERPRINT,
        "payload_schema_id": TYPED_VALUES.FORWARD_PAYLOAD_SCHEMA_ID,
        "payload_schema_fingerprint": (
            TYPED_VALUES.FORWARD_PAYLOAD_SCHEMA_FINGERPRINT
        ),
    }
    if (
        component_identities["profile_fingerprint"]
        != snapshot.get("profile_fingerprint")
        or component_identities["registry_fingerprint"]
        != snapshot.get("registry_fingerprint")
        or component_identities["payload_schema_fingerprint"]
        != snapshot.get("payload_schema_fingerprint")
    ):
        raise ValueError("carrier contract identity differs from qualification")
    comparison_rows.append(
        MappingProxyType(
            {
                "component": "runtime_and_contract_identities",
                "qualified_fingerprint": TYPED_VALUES.fingerprint(
                    {
                        "runtime": snapshot["runtime"],
                        **component_identities,
                    }
                ),
                "current_fingerprint": TYPED_VALUES.fingerprint(
                    {
                        "runtime": TYPED_VALUES.runtime_identity_value(runtime),
                        **component_identities,
                    }
                ),
                "comparison": "exact_identity_equal",
            }
        )
    )
    compatibility_value = {
        "schema": "rook.lm9b_p.carrier_forward_compatibility:v1",
        "historical_qualification_identity": identity,
        "historical_commit_sha": HISTORICAL_CARRIER_COMMIT,
        "consuming_commit_sha": consuming_commit_sha,
        "comparison_rows": [dict(row) for row in comparison_rows],
    }
    return VerifiedCarrierQualificationCompatibility(
        archive_dir=archive,
        historical_qualification_identity=identity,
        historical_commit_sha=HISTORICAL_CARRIER_COMMIT,
        consuming_commit_sha=consuming_commit_sha,
        comparison_rows=tuple(comparison_rows),
        compatibility_fingerprint=TYPED_VALUES.fingerprint(compatibility_value),
    )


def _seal_compatibility_verifier(verifier):
    issued: weakref.WeakKeyDictionary[
        VerifiedCarrierQualificationCompatibility, Mapping[str, object]
    ] = weakref.WeakKeyDictionary()

    def verify_and_issue(**kwargs: object) -> VerifiedCarrierQualificationCompatibility:
        result = verifier(**kwargs)
        if type(result) is not VerifiedCarrierQualificationCompatibility:
            raise TypeError("compatibility verifier returned the wrong carrier type")
        snapshot = _compatibility_snapshot(result)
        issued[result] = snapshot
        return result

    def consume(
        value: object,
    ) -> Mapping[str, object]:
        if type(value) is not VerifiedCarrierQualificationCompatibility:
            raise TypeError("closure-issued carrier compatibility is required")
        snapshot = issued.get(value)
        if snapshot is None or snapshot != _compatibility_snapshot(value):
            raise ValueError("carrier compatibility proof is not closure-issued")
        return MappingProxyType(dict(snapshot))

    return verify_and_issue, consume


def _compatibility_snapshot(
    value: VerifiedCarrierQualificationCompatibility,
) -> dict[str, object]:
    return {
        "archive_dir": str(value.archive_dir),
        "historical_qualification_identity": value.historical_qualification_identity,
        "historical_commit_sha": value.historical_commit_sha,
        "consuming_commit_sha": value.consuming_commit_sha,
        "comparison_rows": [dict(row) for row in value.comparison_rows],
        "compatibility_fingerprint": value.compatibility_fingerprint,
    }


(
    verify_historical_carrier_qualification_compatibility,
    consume_verified_carrier_qualification,
) = _seal_compatibility_verifier(
    _verify_historical_carrier_qualification_compatibility_unsealed
)


def bind_resolution_attempt(
    *,
    instrument: ResolutionInstrument,
    attempt_id: str,
    resolution_root: Path,
    destination: Path,
) -> AttemptBinding:
    if type(instrument) is not ResolutionInstrument:
        raise TypeError("resolution instrument is required")
    if (
        type(attempt_id) is not str
        or len(attempt_id) > ATTEMPT_ID_MAX_LENGTH
        or ATTEMPT_ID_PATTERN.fullmatch(attempt_id) is None
    ):
        raise ValueError("resolution attempt ID is invalid")
    supplied_root = Path(resolution_root)
    supplied_final = Path(destination)
    if not supplied_root.is_absolute() or not supplied_final.is_absolute():
        raise ValueError("resolution root and destination must be absolute")
    root = supplied_root.resolve()
    final = supplied_final.resolve()
    if (
        supplied_root != root
        or supplied_final != final
        or not root.is_dir()
        or final.parent != root
    ):
        raise ValueError("resolution destination must be a direct child")
    if _path_has_reparse_ambiguity(root):
        raise ValueError("resolution root has reparse-point ambiguity")
    if not _paths_share_filesystem(root, final.parent):
        raise ValueError("resolution staging and destination filesystem differ")
    staging = root / f".{attempt_id}.staging"
    if final == staging:
        raise ValueError("resolution destination must differ from staging")
    if final.exists() or staging.exists():
        raise FileExistsError("resolution destination or staging already exists")
    value = {
        "instrument_fingerprint": instrument.instrument_fingerprint,
        "attempt_id": attempt_id,
        "canonical_destination": str(final),
    }
    return AttemptBinding(
        attempt_id=attempt_id,
        resolution_root=root,
        destination=final,
        staging_path=staging,
        attempt_fingerprint=PLANNER_SUPPORT.fingerprint(value),
    )


def build_resolution_invocation_binding(
    *,
    supplied_preflight_fingerprint: str,
    transmit: bool,
    reviewed_commit_sha: str,
    readiness_identity: str,
    attempt_id: str,
    attempt_fingerprint: str,
) -> Mapping[str, object]:
    value: dict[str, object] = {
        "schema": INVOCATION_SCHEMA_ID,
        "supplied_preflight_fingerprint": supplied_preflight_fingerprint,
        "transmit": transmit,
        "reviewed_commit_sha": reviewed_commit_sha,
        "readiness_identity": readiness_identity,
        "attempt_id": attempt_id,
        "attempt_fingerprint": attempt_fingerprint,
    }
    if (
        type(supplied_preflight_fingerprint) is not str
        or type(transmit) is not bool
        or type(reviewed_commit_sha) is not str
        or type(readiness_identity) is not str
        or type(attempt_id) is not str
        or type(attempt_fingerprint) is not str
    ):
        raise TypeError("resolution invocation fields have invalid types")
    value["invocation_fingerprint"] = PLANNER_SUPPORT.fingerprint(value)
    return MappingProxyType(value)


def readiness_route_role_projection(
    manifest: READINESS.RouteManifest,
) -> list[dict[str, object]]:
    if type(manifest) is not READINESS.RouteManifest:
        raise TypeError("readiness route manifest is required")
    return [
        {
            "route_fingerprint": route.route_fingerprint,
            "member_roles": list(route.member_roles),
        }
        for route in manifest.routes
    ]


def _launch_invocation_contract() -> dict[str, object]:
    value: dict[str, object] = {
        "schema_id": INVOCATION_SCHEMA_ID,
        "closed_fields": [
            "schema",
            "supplied_preflight_fingerprint",
            "transmit",
            "reviewed_commit_sha",
            "readiness_identity",
            "attempt_id",
            "attempt_fingerprint",
            "invocation_fingerprint",
        ],
        "claim": "execution was invoked with these bindings only",
        "non_claim": "does not authenticate human authorization",
        "builder_source_fingerprint": _callable_source_fingerprint(
            build_resolution_invocation_binding
        ),
        "verifier_source_fingerprint": _callable_source_fingerprint(
            verify_resolution_invocation_binding
        ),
    }
    value["contract_fingerprint"] = PLANNER_SUPPORT.fingerprint(value)
    return value


def verify_resolution_invocation_binding(
    value: object, *, expected: Mapping[str, object]
) -> Mapping[str, object]:
    if type(value) not in {dict, MappingProxyType} or set(value) != set(expected):
        raise ValueError("resolution invocation binding is not closed")
    if (
        value.get("schema") != INVOCATION_SCHEMA_ID
        or value.get("invocation_fingerprint")
        != PLANNER_SUPPORT.fingerprint_without(value, "invocation_fingerprint")
        or dict(value) != dict(expected)
    ):
        raise ValueError("resolution invocation binding differs")
    return MappingProxyType(dict(value))


def _path_has_reparse_ambiguity(path: Path) -> bool:
    try:
        attributes = path.lstat().st_file_attributes
    except AttributeError:
        return path.is_symlink()
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _paths_share_filesystem(left: Path, right: Path) -> bool:
    return left.stat().st_dev == right.stat().st_dev


def write_resolution_preflight(
    *,
    destination: Path,
    instrument: ResolutionInstrument,
    attempt_binding: AttemptBinding,
) -> VerifiedResolutionPreflight:
    archive = Path(destination).resolve()
    if archive.exists():
        raise FileExistsError("resolution preflight destination already exists")
    archive.mkdir(parents=False, exist_ok=False)
    record = _preflight_record(instrument, attempt_binding, archive)
    record_raw = _json_bytes(record)
    initial_raw = instrument.initial_request.raw_bytes
    members = {
        "record.json": record_raw,
        "initial-request.json": initial_raw,
    }
    checksums = _checksums("rook.lm9b_p.governed_resolution_preflight_checksums:v1", members)
    members["checksums.json"] = _json_bytes(checksums)
    for relative, raw in members.items():
        (archive / relative).write_bytes(raw)
        if (archive / relative).read_bytes() != raw:
            raise ValueError("resolution preflight write verification failed")
    return verify_resolution_preflight(
        archive,
        expected_fingerprint=record["preflight_fingerprint"],
    )


def verify_resolution_preflight(
    archive_dir: Path,
    *,
    expected_fingerprint: str,
) -> VerifiedResolutionPreflight:
    archive = Path(archive_dir).resolve()
    members = {
        path.relative_to(archive).as_posix()
        for path in archive.rglob("*")
        if path.is_file()
    }
    if members != _PREFLIGHT_MEMBERS:
        raise ValueError("resolution preflight membership is not closed")
    record = _object_bytes((archive / "record.json").read_bytes(), "preflight")
    if (
        record.get("schema") != PREFLIGHT_SCHEMA_ID
        or record.get("preflight_fingerprint")
        != PLANNER_SUPPORT.fingerprint_without(record, "preflight_fingerprint")
        or record.get("preflight_fingerprint") != expected_fingerprint
    ):
        raise ValueError("resolution preflight fingerprint mismatch")
    raw_members = {
        "record.json": (archive / "record.json").read_bytes(),
        "initial-request.json": (archive / "initial-request.json").read_bytes(),
    }
    checksums = _object_bytes((archive / "checksums.json").read_bytes(), "checksums")
    if checksums != _checksums(checksums.get("schema"), raw_members):
        raise ValueError("resolution preflight checksums mismatch")
    attempt_value = record.get("attempt")
    if type(attempt_value) is not dict:
        raise ValueError("resolution preflight attempt is invalid")
    sources = _load_current_resolution_sources(record["reviewed_commit_sha"])
    instrument = assemble_resolution_instrument(
        sources=sources,
        isolation_policy_path=ISOLATION_POLICY_PATH,
        evaluation_rubric_path=EVALUATION_RUBRIC_PATH,
    )
    attempt = bind_resolution_attempt(
        instrument=instrument,
        attempt_id=attempt_value["attempt_id"],
        resolution_root=Path(attempt_value["resolution_root"]),
        destination=Path(attempt_value["canonical_destination"]),
    )
    expected_record = _preflight_record(instrument, attempt, archive)
    if expected_record != record:
        raise ValueError("resolution preflight differs from reconstructed instrument")
    if instrument.initial_request.raw_bytes != raw_members["initial-request.json"]:
        raise ValueError("resolution preflight initial request bytes differ")
    return VerifiedResolutionPreflight(
        archive_dir=archive,
        record=MappingProxyType(record),
        preflight_fingerprint=record["preflight_fingerprint"],
        instrument_fingerprint=instrument.instrument_fingerprint,
        attempt=attempt,
        instrument=instrument,
    )


def reserve_resolution_staging(preflight: VerifiedResolutionPreflight) -> Path:
    if type(preflight) is not VerifiedResolutionPreflight:
        raise TypeError("verified resolution preflight is required")
    if preflight.attempt.destination == preflight.attempt.staging_path:
        raise ValueError("resolution staging must differ from destination")
    if preflight.attempt.destination.exists():
        raise FileExistsError("resolution destination already exists")
    preflight.attempt.staging_path.mkdir(parents=False, exist_ok=False)
    return preflight.attempt.staging_path


def require_clean_reviewed_checkout(repo_root: Path, reviewed_commit_sha: str) -> None:
    repo = Path(repo_root).resolve()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != reviewed_commit_sha:
        raise ValueError("reviewed checkout HEAD differs from preflight")
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if dirty:
        raise ValueError("reviewed checkout is dirty")


def verify_sealed_resolution_checkpoint(
    archive_dir: Path,
    *,
    expected_identity: str,
) -> SealedResolutionCheckpoint:
    archive = Path(archive_dir).resolve()
    members = {
        path.relative_to(archive).as_posix()
        for path in archive.rglob("*")
        if path.is_file()
    }
    if members != _CHECKPOINT_MEMBERS:
        raise ValueError("resolution checkpoint membership is not closed")
    raw_members = {
        relative: (archive / relative).read_bytes()
        for relative in sorted(_CHECKPOINT_MEMBERS - {"checksums.json"})
    }
    checksums = _object_bytes(
        (archive / "checksums.json").read_bytes(), "checkpoint checksums"
    )
    expected_checksums = _checksums(
        "rook.lm9b_p.governed_resolution_checkpoint_checksums:v1",
        raw_members,
    )
    if checksums != expected_checksums:
        raise ValueError("resolution checkpoint checksum closure differs")
    record = _object_bytes(raw_members["record.json"], "checkpoint record")
    if (
        record.get("schema") != CHECKPOINT_SCHEMA_ID
        or Path(record.get("canonical_destination", "")).resolve() != archive
        or record.get("implementation_stage") != "task1_vertical_unhardened"
        or record.get("compiler_dispatch_activity") is not False
    ):
        raise ValueError("resolution checkpoint boundary record is invalid")
    identity_source = {
        "schema": CHECKPOINT_SCHEMA_ID,
        "canonical_destination": str(archive),
        "members": [
            row
            for row in expected_checksums["members"]
            if row["path"] != "record.json"
        ],
    }
    identity = PLANNER_SUPPORT.fingerprint(identity_source)
    if identity != expected_identity or record.get("checkpoint_identity") != identity:
        raise ValueError("resolution checkpoint identity mismatch")

    preflight = _object_bytes(raw_members["preflight.json"], "preflight binding")
    if (
        preflight.get("preflight_fingerprint")
        != record.get("preflight_fingerprint")
        or preflight.get("attempt_fingerprint")
        != record.get("attempt_fingerprint")
        or preflight.get("instrument_fingerprint")
        != record.get("instrument_fingerprint")
    ):
        raise ValueError("checkpoint preflight binding differs")
    readiness = _object_bytes(raw_members["readiness.json"], "readiness")
    manifest = READINESS.derive_routes(
        READINESS.role_routes_from_models(
            {"planner": "gpt-5.4", "planner_evaluator": "gpt-5.4"}
        ),
        lambda _model: "OPENAI_API_KEY",
    )
    readiness_decision = READINESS.verify_launch_readiness(
        record=readiness["record"],
        manifest=manifest,
        head_sha=record["reviewed_commit_sha"],
        now_iso=readiness["verified_at"],
        credential_present={route.route_fingerprint: True for route in manifest.routes},
    )
    if not readiness_decision.ok:
        raise ValueError("archived readiness does not verify")

    sources = _load_current_resolution_sources(record["reviewed_commit_sha"])
    instrument = assemble_resolution_instrument(
        sources=sources,
        isolation_policy_path=ISOLATION_POLICY_PATH,
        evaluation_rubric_path=EVALUATION_RUBRIC_PATH,
    )
    inputs = instrument.inputs
    if instrument.instrument_fingerprint != record.get("instrument_fingerprint"):
        raise ValueError("checkpoint instrument differs from reconstruction")

    candidate_raw = raw_members["candidate-recipe.json"]
    planner = _object_bytes(raw_members["planner-session.json"], "planner session")
    _verify_task1_planner_evidence(
        planner,
        inputs=inputs,
        initial_request=instrument.initial_request,
        candidate_raw=candidate_raw,
    )
    gate = PLANNER_SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=candidate_raw,
        authority=inputs.current_authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )
    archived_gate = _object_bytes(raw_members["checkpoint-gate.json"], "gate")
    if archived_gate != _gate_record(gate):
        raise ValueError("checkpoint mechanical gate differs")
    isolation = SUPPORT.evaluate_resolution_isolation(
        inputs=inputs,
        candidate_recipe_bytes=candidate_raw,
    )
    if _object_bytes(raw_members["isolation.json"], "isolation") != _isolation_record(
        isolation
    ):
        raise ValueError("checkpoint isolation differs")
    if isolation.status != "isolated":
        raise ValueError("sealed ready checkpoint did not pass isolation")

    evaluator_row = _object_bytes(raw_members["evaluator.json"], "evaluator")
    if (
        set(evaluator_row)
        != {
            "schema",
            "dispatched_request_b64",
            "provider_claimed_raw_request_b64",
            "raw_response_b64",
            "assistant_message",
            "usage",
            "provider_metadata",
            "termination",
        }
        or evaluator_row.get("schema")
        != "rook.lm9b_p.governed_resolution_evaluator:v1"
    ):
        raise ValueError("checkpoint evaluator evidence shape differs")
    rendered_evaluator = SUPPORT.render_planner_revision_evaluation_request(
        inputs,
        candidate_recipe_bytes=candidate_raw,
    )
    expected_evaluator_request = (
        PLANNER_SUPPORT.build_planner_evaluator_provider_call_request(
            system_prompt=PLANNER_SUPPORT.PLANNER_EVALUATOR_SYSTEM_PROMPT,
            user_prompt=rendered_evaluator.raw_bytes.decode("utf-8"),
        )
    )
    dispatched_evaluator_request = base64.b64decode(
        evaluator_row["dispatched_request_b64"], validate=True
    )
    if dispatched_evaluator_request != expected_evaluator_request:
        raise ValueError("evaluator dispatch differs from reconstructed request")
    provider_turn = _provider_turn_from_record(evaluator_row)
    evaluator = PLANNER_SUPPORT.derive_planner_evaluation_result(
        outcome="returned", response=provider_turn
    )
    if evaluator_row.get("termination") != evaluator.termination:
        raise ValueError("checkpoint evaluator evidence termination differs")
    classification = PLANNER_ARTIFACTS.derive_evaluated_recipe_classification(
        evaluator,
        final_recipe_bytes=candidate_raw,
    )
    if classification == "probe_candidate_blocked":
        raise ValueError("isolation-passing recipe retained an explicit blocker")
    archived_classification = _object_bytes(
        raw_members["classification.json"], "classification"
    )
    if (
        classification != "probe_candidate_ready"
        or archived_classification
        != {
            "schema": "rook.lm9b_p.governed_resolution_classification:v1",
            "classification": classification,
            "checkpoint_2": "not_evaluated",
        }
        or record.get("classification") != classification
    ):
        raise ValueError("checkpoint classification differs")
    return SealedResolutionCheckpoint(
        archive_dir=archive,
        checkpoint_identity=identity,
        classification=classification,
        exact_recipe_bytes=candidate_raw,
    )


def seal_task1_resolution_checkpoint(
    *,
    preflight: VerifiedResolutionPreflight,
    readiness_record: Mapping[str, object],
    readiness_verified_at: str,
    planner_session: PLANNER_SUPPORT.PlannerSessionResult,
    planner_call_records: list[Mapping[str, object]],
    checkpoint_gate: PLANNER_SUPPORT.MechanicalGateResult,
    isolation_result: SUPPORT.IsolationGateResult,
    evaluator_turn: PLANNER_SUPPORT.ProviderTurn,
    evaluator_request_bytes: bytes,
    evaluator_result: PLANNER_SUPPORT.PlannerEvaluationResult,
    classification: str,
) -> SealedResolutionCheckpoint:
    staging = preflight.attempt.staging_path
    if not staging.is_dir() or preflight.attempt.destination.exists():
        raise ValueError("reserved staging and absent destination are required")
    candidate_raw = planner_session.final_recipe_bytes
    if type(candidate_raw) is not bytes:
        raise ValueError("accepted candidate bytes are required")
    planner_record = {
        "schema": "rook.lm9b_p.governed_resolution_planner_session:v1",
        "termination": planner_session.termination,
        "call_count": len(planner_call_records),
        "final_recipe_raw_sha256": _sha256(candidate_raw),
        "calls": planner_call_records,
        "turns": [
            {
                "turn_index": turn.turn_index,
                "raw_response_sha256": _sha256(turn.raw_response),
                "tool_arguments_sha256": (
                    None if turn.tool_arguments is None else _sha256(turn.tool_arguments)
                ),
                "gate_status": (
                    None if turn.gate_result is None else turn.gate_result.status
                ),
                "usage": dict(turn.usage),
                "elapsed_ms": turn.elapsed_ms,
            }
            for turn in planner_session.turns
        ],
    }
    evaluator_record = _provider_turn_record(
        evaluator_turn,
        evaluator_result,
        dispatched_request_bytes=evaluator_request_bytes,
    )
    classification_record = {
        "schema": "rook.lm9b_p.governed_resolution_classification:v1",
        "classification": classification,
        "checkpoint_2": "not_evaluated",
    }
    preflight_binding = {
        "preflight_fingerprint": preflight.preflight_fingerprint,
        "instrument_fingerprint": preflight.instrument_fingerprint,
        "attempt_fingerprint": preflight.attempt.attempt_fingerprint,
        "attempt_id": preflight.attempt.attempt_id,
    }
    raw_members = {
        "preflight.json": _json_bytes(preflight_binding),
        "readiness.json": _json_bytes(
            {"record": dict(readiness_record), "verified_at": readiness_verified_at}
        ),
        "planner-session.json": _json_bytes(planner_record),
        "candidate-recipe.json": candidate_raw,
        "checkpoint-gate.json": _json_bytes(_gate_record(checkpoint_gate)),
        "isolation.json": _json_bytes(_isolation_record(isolation_result)),
        "evaluator.json": _json_bytes(evaluator_record),
        "classification.json": _json_bytes(classification_record),
    }
    provisional_checksums = _checksums(
        "rook.lm9b_p.governed_resolution_checkpoint_checksums:v1",
        {"record.json": b"", **raw_members},
    )
    identity_source = {
        "schema": CHECKPOINT_SCHEMA_ID,
        "canonical_destination": str(preflight.attempt.destination),
        "members": [
            row
            for row in provisional_checksums["members"]
            if row["path"] != "record.json"
        ],
    }
    # The record cannot hash itself. The checkpoint identity covers every root
    # evidence member except the record, whose exact bytes are checksum-closed.
    checkpoint_identity = PLANNER_SUPPORT.fingerprint(identity_source)
    record = {
        "schema": CHECKPOINT_SCHEMA_ID,
        "canonical_destination": str(preflight.attempt.destination),
        "checkpoint_identity": checkpoint_identity,
        "classification": classification,
        "implementation_stage": "task1_vertical_unhardened",
        "compiler_dispatch_activity": False,
        "reviewed_commit_sha": preflight.record["reviewed_commit_sha"],
        **preflight_binding,
    }
    raw_members["record.json"] = _json_bytes(record)
    checksums = _checksums(
        "rook.lm9b_p.governed_resolution_checkpoint_checksums:v1", raw_members
    )
    raw_members["checksums.json"] = _json_bytes(checksums)
    for relative, raw in raw_members.items():
        path = staging / relative
        path.write_bytes(raw)
        if path.read_bytes() != raw:
            raise ValueError("resolution checkpoint write verification failed")
    # Verify staging with the same derivations except physical destination, then
    # finalize no-clobber. Task 2 replaces this thin staging check with the full
    # private verifier and reconciliation matrix.
    if set(raw_members) != _CHECKPOINT_MEMBERS:
        raise ValueError("resolution checkpoint staging membership differs")
    staging.rename(preflight.attempt.destination)
    return verify_sealed_resolution_checkpoint(
        preflight.attempt.destination,
        expected_identity=checkpoint_identity,
    )


def _gate_record(gate: PLANNER_SUPPORT.MechanicalGateResult) -> dict[str, object]:
    return {
        "schema": "rook.lm9b_p.governed_resolution_mechanical_gate:v1",
        "status": gate.status,
        "diagnostics": [
            {"code": row.code, "path": row.path, "message": row.message}
            for row in gate.diagnostics
        ],
        "final_recipe_raw_sha256": (
            None if gate.final_recipe_bytes is None else _sha256(gate.final_recipe_bytes)
        ),
        "recipe_value_fingerprint": gate.recipe_value_fingerprint,
        "ratified_recipe_fingerprint": gate.ratified_recipe_fingerprint,
        "historical_recipe_fingerprint": gate.historical_recipe_fingerprint,
    }


def _isolation_record(result: SUPPORT.IsolationGateResult) -> dict[str, object]:
    return {
        "schema": "rook.lm9b_p.governed_resolution_isolation_result:v1",
        "status": result.status,
        "equations": [dict(row) for row in result.equations],
        "bounded_differences": [dict(row) for row in result.bounded_differences],
        "parent_residual_raw_sha256": _sha256(result.parent_residual_bytes),
        "candidate_residual_raw_sha256": _sha256(result.candidate_residual_bytes),
        "result_fingerprint": result.result_fingerprint,
    }


def _provider_turn_record(
    turn: PLANNER_SUPPORT.ProviderTurn,
    result: PLANNER_SUPPORT.PlannerEvaluationResult,
    *,
    dispatched_request_bytes: bytes,
) -> dict[str, object]:
    return {
        "schema": "rook.lm9b_p.governed_resolution_evaluator:v1",
        "dispatched_request_b64": base64.b64encode(
            dispatched_request_bytes
        ).decode("ascii"),
        "provider_claimed_raw_request_b64": base64.b64encode(
            turn.raw_request
        ).decode("ascii"),
        "raw_response_b64": base64.b64encode(turn.raw_response).decode("ascii"),
        "assistant_message": PLANNER_SUPPORT._json_builtins(turn.assistant_message),
        "usage": PLANNER_SUPPORT._json_builtins(turn.usage),
        "provider_metadata": PLANNER_SUPPORT._json_builtins(turn.provider_metadata),
        "termination": result.termination,
    }


def _provider_turn_from_record(
    record: Mapping[str, object],
) -> PLANNER_SUPPORT.ProviderTurn:
    return PLANNER_SUPPORT.ProviderTurn(
        raw_request=base64.b64decode(
            record["provider_claimed_raw_request_b64"], validate=True
        ),
        raw_response=base64.b64decode(record["raw_response_b64"], validate=True),
        assistant_message=record["assistant_message"],
        usage=record["usage"],
        provider_metadata=record["provider_metadata"],
    )


def _verify_task1_planner_evidence(
    planner: Mapping[str, object],
    *,
    inputs: SUPPORT.VerifiedResolutionInputs,
    initial_request: SUPPORT.RenderedRevisionRequest,
    candidate_raw: bytes,
) -> None:
    calls = planner.get("calls")
    turns = planner.get("turns")
    if (
        set(planner)
        != {
            "schema",
            "termination",
            "call_count",
            "final_recipe_raw_sha256",
            "calls",
            "turns",
        }
        or planner.get("schema")
        != "rook.lm9b_p.governed_resolution_planner_session:v1"
        or planner.get("termination") != "mechanically_accepted"
        or planner.get("final_recipe_raw_sha256") != _sha256(candidate_raw)
        or planner.get("call_count") != 2
        or type(calls) is not list
        or type(turns) is not list
        or len(calls) != 2
        or len(turns) != 2
        or [row.get("call_index") for row in calls] != [1, 2]
        or [row.get("role") for row in calls] != ["planner", "planner"]
        or [row.get("turn_index") for row in turns] != [1, 2]
    ):
        raise ValueError("checkpoint Planner ledger is invalid")
    messages: list[dict[str, object]] = [
        {"role": "system", "content": SUPPORT.REVISION_SYSTEM_PROMPT},
        {"role": "user", "content": initial_request.raw_bytes.decode("utf-8")},
    ]
    accepted_recipe: bytes | None = None
    for index, (call, turn_row) in enumerate(zip(calls, turns, strict=True), 1):
        if type(call) is not dict or type(turn_row) is not dict:
            raise ValueError("Planner call evidence row is malformed")
        request_text = call.get("canonical_request_json")
        if type(request_text) is not str:
            raise ValueError("Planner canonical request evidence is absent")
        request_raw = request_text.encode("utf-8")
        request_value = PLANNER_SUPPORT.materialize_planner_provider_call_request(
            request_raw
        )
        rebuilt_request = PLANNER_SUPPORT.build_planner_provider_call_request(
            messages=messages,
            provider_timeout_s=request_value["provider_timeout_s"],
        )
        if (
            rebuilt_request != request_raw
            or call.get("request_raw_sha256") != _sha256(request_raw)
        ):
            raise ValueError("Planner request does not follow the transcript")
        response = PLANNER_SUPPORT.ProviderTurn(
            raw_request=base64.b64decode(
                call["provider_raw_request_b64"], validate=True
            ),
            raw_response=base64.b64decode(call["raw_response_b64"], validate=True),
            assistant_message=call["assistant_message"],
            usage=call["usage"],
            provider_metadata=call["provider_metadata"],
        )
        if call.get("raw_response_sha256") != _sha256(response.raw_response):
            raise ValueError("Planner response hash differs from captured bytes")
        tool_arguments, recipe_bytes, protocol_rejection, tool_call_id = (
            PLANNER_SUPPORT.derive_planner_submission_from_message(
                response.assistant_message
            )
        )
        gate = protocol_rejection
        if recipe_bytes is not None:
            gate = PLANNER_SUPPORT.evaluate_mechanical_gate(
                recipe_bytes=recipe_bytes,
                authority=inputs.current_authority,
                recipe_schema=inputs.recipe_schema,
                normalization_profile=inputs.normalization_profile,
                exclusion_policy=inputs.exclusion_policy,
            )
        if gate is None:
            raise ValueError("Planner submission produced no gate result")
        expected_turn = {
            "turn_index": index,
            "raw_response_sha256": _sha256(response.raw_response),
            "tool_arguments_sha256": (
                None if tool_arguments is None else _sha256(tool_arguments)
            ),
            "gate_status": gate.status,
            "usage": PLANNER_SUPPORT._json_builtins(response.usage),
            "elapsed_ms": turn_row.get("elapsed_ms"),
        }
        if (
            type(turn_row.get("elapsed_ms")) is not int
            or turn_row["elapsed_ms"] < 0
            or turn_row != expected_turn
        ):
            raise ValueError("Planner turn row differs from captured response")
        if gate.status == "mechanically_accepted":
            if index != len(calls) or recipe_bytes != candidate_raw:
                raise ValueError("accepted Planner tool bytes differ from candidate")
            accepted_recipe = recipe_bytes
            continue
        messages.append(dict(response.assistant_message))
        messages.append(
            PLANNER_SUPPORT.build_planner_mechanical_feedback_message(
                gate, tool_call_id
            )
        )
    if accepted_recipe != candidate_raw:
        raise ValueError("Planner evidence does not derive the sealed candidate")


def _object_bytes(raw: bytes, label: str) -> dict[str, object]:
    value = PLANNER_SUPPORT.parse_archive_json(raw)
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def _load_current_resolution_sources(
    expected_reviewed_commit: object,
) -> VerifiedResolutionSources:
    if type(expected_reviewed_commit) is not str:
        raise ValueError("reviewed commit identity is invalid")
    sources = load_verified_resolution_sources(
        historical_source_dir=CONT_ARTIFACTS.PRODUCTION_SOURCE_PINS.source_root,
        derivative_archive=OFFICIAL_DERIVATIVE,
        derivative_identity=OFFICIAL_DERIVATIVE_IDENTITY,
        carrier_qualification_archive=HISTORICAL_CARRIER_QUALIFICATION,
        carrier_qualification_identity=HISTORICAL_CARRIER_QUALIFICATION_IDENTITY,
        repo_root=_REPO_ROOT,
        successor_envelope_path=SUCCESSOR_ENVELOPE_PATH,
    )
    if sources.reviewed_commit_sha != expected_reviewed_commit:
        raise ValueError("reviewed commit differs from current source carrier")
    return sources


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _callable_source_fingerprint(value: object) -> str:
    return _sha256(inspect.getsource(value).encode("utf-8"))


def _git_object(repo: Path, commit: str, relative_path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout


def _require_reviewed_file(
    repo: Path, path: Path, commit: str, *, label: str
) -> None:
    try:
        relative = path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} is outside the reviewed checkout") from exc
    try:
        _require_worktree_blob(repo, relative, commit)
    except ValueError as exc:
        raise ValueError(f"{label} differs from its reviewed Git object") from exc


def _require_worktree_blob(repo: Path, relative_path: str, commit: str) -> None:
    expected = subprocess.run(
        ["git", "rev-parse", f"{commit}:{relative_path}"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    actual = subprocess.run(
        ["git", "hash-object", relative_path],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual != expected:
        raise ValueError(f"carrier worktree drift: {relative_path}")


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        PLANNER_SUPPORT._json_builtins(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _checksums(schema: object, members: Mapping[str, bytes]) -> dict[str, object]:
    return {
        "schema": schema,
        "members": [
            {"path": path, "raw_sha256": _sha256(raw)}
            for path, raw in sorted(members.items())
        ],
    }


def _preflight_record(
    instrument: ResolutionInstrument,
    attempt: AttemptBinding,
    archive: Path,
) -> dict[str, object]:
    value = {
        "schema": PREFLIGHT_SCHEMA_ID,
        "canonical_preflight_destination": str(archive),
        "reviewed_commit_sha": instrument.inputs.reviewed_commit_sha,
        "historical_qualification_identity": (
            instrument.inputs.historical_qualification_identity
        ),
        "carrier_compatibility_fingerprint": (
            instrument.inputs.carrier_compatibility_fingerprint
        ),
        "instrument_fingerprint": instrument.instrument_fingerprint,
        "instrument_contracts": dict(instrument.contract_manifest),
        "initial_request_raw_sha256": instrument.initial_request.raw_sha256,
        "attempt": {
            "attempt_id": attempt.attempt_id,
            "resolution_root": str(attempt.resolution_root),
            "canonical_destination": str(attempt.destination),
            "staging_path": str(attempt.staging_path),
            "attempt_fingerprint": attempt.attempt_fingerprint,
        },
    }
    value["preflight_fingerprint"] = PLANNER_SUPPORT.fingerprint(value)
    return value


__all__ = (
    "AttemptBinding",
    "ResolutionInstrument",
    "SealedResolutionCheckpoint",
    "VerifiedCarrierQualificationCompatibility",
    "VerifiedResolutionPreflight",
    "VerifiedResolutionSources",
    "assemble_resolution_instrument",
    "assemble_task1_resolution_instrument",
    "bind_resolution_attempt",
    "build_resolution_invocation_binding",
    "consume_verified_carrier_qualification",
    "consume_verified_resolution_sources",
    "load_verified_resolution_sources",
    "reserve_resolution_staging",
    "require_clean_reviewed_checkout",
    "readiness_route_role_projection",
    "seal_task1_resolution_checkpoint",
    "verify_historical_carrier_qualification_compatibility",
    "verify_resolution_preflight",
    "verify_resolution_invocation_binding",
    "verify_sealed_resolution_checkpoint",
    "write_resolution_preflight",
)
