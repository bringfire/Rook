"""Evidence and preflight contracts for the governed-resolution checkpoint."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
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
READY_PROOF_CONTRACT = MappingProxyType(
    {
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


@dataclass(frozen=True)
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


def assemble_task1_resolution_instrument(
    inputs: SUPPORT.VerifiedResolutionInputs,
) -> ResolutionInstrument:
    if type(inputs) is not SUPPORT.VerifiedResolutionInputs:
        raise TypeError("verified resolution inputs are required")
    initial = SUPPORT.render_planner_revision_request(inputs)
    qualification = {
        "historical_qualification_identity": (
            inputs.historical_qualification_identity
        ),
        "carrier_compatibility_fingerprint": (
            inputs.carrier_compatibility_fingerprint
        ),
    }
    manifest = {
        "schema": "rook.lm9b_p.governed_resolution_instrument_contracts:v1",
        "inputs_fingerprint": inputs.inputs_fingerprint,
        "revision_renderer_id": initial.renderer_id,
        "initial_request_raw_sha256": initial.raw_sha256,
        "isolation_policy_definition_id": inputs.policy_instance.definition_id,
        "isolation_policy_definition_fingerprint": (
            inputs.policy_instance.definition_fingerprint
        ),
        "isolation_policy_instance_fingerprint": (
            inputs.policy_instance.instance_fingerprint
        ),
        "evaluation_rubric_fingerprint": inputs.evaluation_rubric[
            "rubric_fingerprint"
        ],
        "planner_model": "gpt-5.4",
        "evaluator_model": "gpt-5.4",
        "provider_profile": "litellm.completion.tool_calling.no_parallel:v1",
        "planner_max_calls": PLANNER_SUPPORT.PLANNER_MAX_TURNS,
        "evaluator_max_calls": 1,
        "compiler_max_calls": 0,
        "ready_proof": dict(READY_PROOF_CONTRACT),
        "task1_stage": "task1_vertical_unhardened",
        "qualification_binding": qualification,
    }
    return ResolutionInstrument(
        inputs=inputs,
        initial_request=initial,
        contract_manifest=MappingProxyType(manifest),
        instrument_fingerprint=PLANNER_SUPPORT.fingerprint(manifest),
    )


def verify_historical_carrier_qualification_compatibility(
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
        or len(attempt_id) > 64
        or ATTEMPT_ID_PATTERN.fullmatch(attempt_id) is None
    ):
        raise ValueError("resolution attempt ID is invalid")
    root = Path(resolution_root).resolve()
    final = Path(destination).resolve()
    if not root.is_dir() or final.parent != root:
        raise ValueError("resolution destination must be a direct child")
    staging = root / f".{attempt_id}.staging"
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
    source = CONT_ARTIFACTS.verify_historical_source()
    derivative = CONT_ARTIFACTS.verify_sealed_derivative_archive(
        OFFICIAL_DERIVATIVE,
        expected_derivative_identity=OFFICIAL_DERIVATIVE_IDENTITY,
    )
    compatibility = verify_historical_carrier_qualification_compatibility(
        archive_dir=HISTORICAL_CARRIER_QUALIFICATION,
        expected_identity=HISTORICAL_CARRIER_QUALIFICATION_IDENTITY,
        repo_root=_REPO_ROOT,
        consuming_commit_sha=record["reviewed_commit_sha"],
    )
    inputs = SUPPORT.assemble_verified_resolution_inputs(
        historical_source=source,
        parent_derivative=derivative,
        carrier_qualification=compatibility,
        successor_envelope_bytes=SUCCESSOR_ENVELOPE_PATH.read_bytes(),
        payload_schema_bytes=CARRIER.PAYLOAD_SCHEMA_PATH.read_bytes(),
        semantic_registry_bytes=CARRIER.REGISTRY_PATH.read_bytes(),
        isolation_policy_bytes=ISOLATION_POLICY_PATH.read_bytes(),
        evaluation_rubric_bytes=EVALUATION_RUBRIC_PATH.read_bytes(),
        reviewed_commit_sha=record["reviewed_commit_sha"],
    )
    instrument = assemble_task1_resolution_instrument(inputs)
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
    preflight.attempt.staging_path.mkdir(parents=False, exist_ok=False)
    return preflight.attempt.staging_path


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

    source = CONT_ARTIFACTS.verify_historical_source()
    derivative = CONT_ARTIFACTS.verify_sealed_derivative_archive(
        OFFICIAL_DERIVATIVE,
        expected_derivative_identity=OFFICIAL_DERIVATIVE_IDENTITY,
    )
    compatibility = verify_historical_carrier_qualification_compatibility(
        archive_dir=HISTORICAL_CARRIER_QUALIFICATION,
        expected_identity=HISTORICAL_CARRIER_QUALIFICATION_IDENTITY,
        repo_root=_REPO_ROOT,
        consuming_commit_sha=record["reviewed_commit_sha"],
    )
    inputs = SUPPORT.assemble_verified_resolution_inputs(
        historical_source=source,
        parent_derivative=derivative,
        carrier_qualification=compatibility,
        successor_envelope_bytes=SUCCESSOR_ENVELOPE_PATH.read_bytes(),
        payload_schema_bytes=CARRIER.PAYLOAD_SCHEMA_PATH.read_bytes(),
        semantic_registry_bytes=CARRIER.REGISTRY_PATH.read_bytes(),
        isolation_policy_bytes=ISOLATION_POLICY_PATH.read_bytes(),
        evaluation_rubric_bytes=EVALUATION_RUBRIC_PATH.read_bytes(),
        reviewed_commit_sha=record["reviewed_commit_sha"],
    )
    instrument = assemble_task1_resolution_instrument(inputs)
    if instrument.instrument_fingerprint != record.get("instrument_fingerprint"):
        raise ValueError("checkpoint instrument differs from reconstruction")

    candidate_raw = raw_members["candidate-recipe.json"]
    planner = _object_bytes(raw_members["planner-session.json"], "planner session")
    if (
        planner.get("termination") != "mechanically_accepted"
        or planner.get("final_recipe_raw_sha256") != _sha256(candidate_raw)
        or planner.get("call_count") != 2
        or [row.get("turn_index") for row in planner.get("turns", [])] != [1, 2]
    ):
        raise ValueError("checkpoint Planner ledger is invalid")
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
    provider_turn = _provider_turn_from_record(evaluator_row)
    evaluator = PLANNER_SUPPORT.derive_planner_evaluation_result(
        outcome="returned", response=provider_turn
    )
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
    evaluator_record = _provider_turn_record(evaluator_turn, evaluator_result)
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
) -> dict[str, object]:
    return {
        "schema": "rook.lm9b_p.governed_resolution_evaluator:v1",
        "raw_request": turn.raw_request.decode("utf-8"),
        "raw_response": turn.raw_response.decode("utf-8"),
        "assistant_message": PLANNER_SUPPORT._json_builtins(turn.assistant_message),
        "usage": PLANNER_SUPPORT._json_builtins(turn.usage),
        "provider_metadata": PLANNER_SUPPORT._json_builtins(turn.provider_metadata),
        "termination": result.termination,
    }


def _provider_turn_from_record(
    record: Mapping[str, object],
) -> PLANNER_SUPPORT.ProviderTurn:
    return PLANNER_SUPPORT.ProviderTurn(
        raw_request=record["raw_request"].encode("utf-8"),
        raw_response=record["raw_response"].encode("utf-8"),
        assistant_message=record["assistant_message"],
        usage=record["usage"],
        provider_metadata=record["provider_metadata"],
    )


def _object_bytes(raw: bytes, label: str) -> dict[str, object]:
    value = PLANNER_SUPPORT.parse_archive_json(raw)
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _git_object(repo: Path, commit: str, relative_path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout


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
    "assemble_task1_resolution_instrument",
    "bind_resolution_attempt",
    "reserve_resolution_staging",
    "seal_task1_resolution_checkpoint",
    "verify_historical_carrier_qualification_compatibility",
    "verify_resolution_preflight",
    "verify_sealed_resolution_checkpoint",
    "write_resolution_preflight",
)
