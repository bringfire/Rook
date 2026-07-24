#!/usr/bin/env python3
"""No-contact qualification writer/verifier for the LM9 typed-fact carrier."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence


_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _import_path in (_SCRIPTS_DIR, _MCP_SRC):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

import lm9_semantic_typed_values as TYPED_VALUES
import lm9_typed_fact_carrier_artifacts as CARRIER
import lm9b_p_evaluator_only_continuation_artifacts as CONT_ARTIFACTS
import lm9b_p_planner_recipe_transfer_artifacts as PLANNER_ARTIFACTS


QUALIFICATION_SCHEMA_ID = "rook.lm9.typed_fact_carrier_qualification:v1"
SNAPSHOT_SCHEMA_ID = "rook.lm9.typed_fact_carrier_qualification_snapshot:v1"
CHECKSUMS_SCHEMA_ID = "rook.lm9.typed_fact_carrier_qualification_checksums:v1"
FINAL_MEMBERS = frozenset(
    {
        "record.json",
        "snapshot.json",
        "contracts/profile.json",
        "contracts/semantic-value-registry.json",
        "contracts/task-payload-schema.json",
        "source/historical-binding.json",
        "source/derivative-binding.json",
        "results/blocked-parent.json",
        "results/control-compatibility.json",
        "results/radial-witness.json",
        "results/annotation-witness.json",
        "results/negative-cases.json",
        "boundary.json",
        "checksums.json",
    }
)


@dataclass(frozen=True)
class QualificationSnapshot:
    commit_sha: str
    runtime: TYPED_VALUES.RuntimeIdentity
    helper_source_sha256: str
    profile_fingerprint: str
    registry_fingerprint: str
    payload_schema_fingerprint: str
    clean_checkout: bool
    snapshot_fingerprint: str


@dataclass(frozen=True)
class VerifiedQualification:
    archive_dir: Path
    qualification_identity: str
    snapshot: QualificationSnapshot
    record: Mapping[str, object]


def _json_bytes(value: object) -> bytes:
    return TYPED_VALUES.canonical_json_bytes(value) + b"\n"


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _checkout_state(repo_root: Path) -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return commit, not bool(status)


def _snapshot_projection(
    *,
    commit_sha: str,
    runtime: TYPED_VALUES.RuntimeIdentity,
    helper_source_sha256: str,
    profile_fingerprint: str,
    registry_fingerprint: str,
    payload_schema_fingerprint: str,
    clean_checkout: bool,
) -> dict[str, object]:
    return {
        "schema": SNAPSHOT_SCHEMA_ID,
        "commit_sha": commit_sha,
        "runtime": TYPED_VALUES.runtime_identity_value(runtime),
        "helper_source_sha256": helper_source_sha256,
        "profile_fingerprint": profile_fingerprint,
        "registry_fingerprint": registry_fingerprint,
        "payload_schema_fingerprint": payload_schema_fingerprint,
        "clean_checkout": clean_checkout,
    }


def _snapshot_value(snapshot: QualificationSnapshot) -> dict[str, object]:
    value = _snapshot_projection(
        commit_sha=snapshot.commit_sha,
        runtime=snapshot.runtime,
        helper_source_sha256=snapshot.helper_source_sha256,
        profile_fingerprint=snapshot.profile_fingerprint,
        registry_fingerprint=snapshot.registry_fingerprint,
        payload_schema_fingerprint=snapshot.payload_schema_fingerprint,
        clean_checkout=snapshot.clean_checkout,
    )
    value["snapshot_fingerprint"] = snapshot.snapshot_fingerprint
    return value


def build_qualification_snapshot(*, repo_root: Path) -> QualificationSnapshot:
    repo = Path(repo_root).resolve()
    if repo != _REPO_ROOT.resolve():
        raise ValueError("qualification must use the calling checkout")
    commit, clean = _checkout_state(repo)
    if type(commit) is not str or not commit:
        raise ValueError("qualification commit identity is invalid")
    if clean is not True:
        raise ValueError("qualification checkout is not clean")
    runtime = TYPED_VALUES.current_runtime_identity()
    profile = TYPED_VALUES.build_profile_identity(runtime)
    registry = CARRIER._verified_registry(CARRIER.REGISTRY_PATH.read_bytes(), runtime)
    payload_schema = CARRIER._admitted_payload_schema(
        CARRIER.PAYLOAD_SCHEMA_PATH.read_bytes(), runtime
    )
    projection = _snapshot_projection(
        commit_sha=commit,
        runtime=runtime,
        helper_source_sha256=_sha256(
            (_SCRIPTS_DIR / "lm9_semantic_typed_values.py").read_bytes()
        ),
        profile_fingerprint=profile.fingerprint,
        registry_fingerprint=registry.fingerprint,
        payload_schema_fingerprint=payload_schema.schema_fingerprint,
        clean_checkout=clean,
    )
    return QualificationSnapshot(
        commit_sha=commit,
        runtime=runtime,
        helper_source_sha256=projection["helper_source_sha256"],
        profile_fingerprint=profile.fingerprint,
        registry_fingerprint=registry.fingerprint,
        payload_schema_fingerprint=payload_schema.schema_fingerprint,
        clean_checkout=clean,
        snapshot_fingerprint=TYPED_VALUES.fingerprint(projection),
    )


def _snapshot_from_bytes(raw: bytes) -> QualificationSnapshot:
    value = TYPED_VALUES.parse_strict_json(raw, label="qualification snapshot")
    expected_fields = {
        "schema",
        "commit_sha",
        "runtime",
        "helper_source_sha256",
        "profile_fingerprint",
        "registry_fingerprint",
        "payload_schema_fingerprint",
        "clean_checkout",
        "snapshot_fingerprint",
    }
    if type(value) is not dict or set(value) != expected_fields:
        raise ValueError("qualification snapshot shape is invalid")
    runtime = TYPED_VALUES.current_runtime_identity()
    if value["runtime"] != TYPED_VALUES.runtime_identity_value(runtime):
        raise ValueError("qualification runtime identity mismatch")
    projection = {key: item for key, item in value.items() if key != "snapshot_fingerprint"}
    if (
        value["schema"] != SNAPSHOT_SCHEMA_ID
        or type(value["commit_sha"]) is not str
        or not value["commit_sha"]
        or value["clean_checkout"] is not True
        or value["snapshot_fingerprint"] != TYPED_VALUES.fingerprint(projection)
    ):
        raise ValueError("qualification snapshot identity is invalid")
    return QualificationSnapshot(
        commit_sha=value["commit_sha"],
        runtime=runtime,
        helper_source_sha256=value["helper_source_sha256"],
        profile_fingerprint=value["profile_fingerprint"],
        registry_fingerprint=value["registry_fingerprint"],
        payload_schema_fingerprint=value["payload_schema_fingerprint"],
        clean_checkout=True,
        snapshot_fingerprint=value["snapshot_fingerprint"],
    )


def _require_snapshot_current(
    snapshot: QualificationSnapshot,
    *,
    repo_root: Path,
) -> None:
    if type(snapshot) is not QualificationSnapshot:
        raise TypeError("exact qualification snapshot is required")
    runtime = TYPED_VALUES.current_runtime_identity()
    if runtime != snapshot.runtime:
        raise ValueError("qualification runtime identity changed after snapshot")
    commit, clean = _checkout_state(Path(repo_root).resolve())
    if commit != snapshot.commit_sha or clean is not True:
        raise ValueError("qualification checkout changed after snapshot")
    profile = TYPED_VALUES.build_profile_identity(runtime)
    registry = CARRIER._verified_registry(CARRIER.REGISTRY_PATH.read_bytes(), runtime)
    payload_schema = CARRIER._admitted_payload_schema(
        CARRIER.PAYLOAD_SCHEMA_PATH.read_bytes(), runtime
    )
    projection = _snapshot_projection(
        commit_sha=commit,
        runtime=runtime,
        helper_source_sha256=_sha256(
            (_SCRIPTS_DIR / "lm9_semantic_typed_values.py").read_bytes()
        ),
        profile_fingerprint=profile.fingerprint,
        registry_fingerprint=registry.fingerprint,
        payload_schema_fingerprint=payload_schema.schema_fingerprint,
        clean_checkout=clean,
    )
    if TYPED_VALUES.fingerprint(projection) != snapshot.snapshot_fingerprint:
        raise ValueError("qualification instrument changed after snapshot")


def _verify_source_and_derivative_bindings() -> None:
    CONT_ARTIFACTS.verify_historical_source()
    CONT_ARTIFACTS.verify_sealed_derivative_archive(
        CARRIER.OFFICIAL_DERIVATIVE,
        expected_derivative_identity=CARRIER.OFFICIAL_DERIVATIVE_IDENTITY,
    )


def _record_map(
    source: CONT_ARTIFACTS.VerifiedHistoricalSource,
) -> dict[str, PLANNER_ARTIFACTS.PlannerInputRecord]:
    return {record.role: record for record in source.input_records}


def _environment_payload_schema_bytes(
    records: Mapping[str, PLANNER_ARTIFACTS.PlannerInputRecord],
) -> bytes:
    return CARRIER._environment_payload_schema_bytes(records)


def _derive_transition(repo_root: Path) -> dict[str, object]:
    runtime = TYPED_VALUES.current_runtime_identity()
    profile = TYPED_VALUES.build_profile_identity(runtime)
    registry_raw = CARRIER.REGISTRY_PATH.read_bytes()
    payload_schema_raw = CARRIER.PAYLOAD_SCHEMA_PATH.read_bytes()
    payload_value = TYPED_VALUES.parse_strict_json(
        payload_schema_raw, label="code-owned forward task-payload schema"
    )
    if type(payload_value) is not dict:
        raise ValueError("code-owned forward task-payload schema is invalid")
    payload_schema = TYPED_VALUES.admit_schema_document(
        payload_value, profile=profile
    )

    source = CONT_ARTIFACTS.verify_historical_source()
    records = _record_map(source)
    registry, unit_context_index = CARRIER._verified_parent_value_context(
        source,
        runtime=runtime,
    )
    parent_values = CARRIER.reconstruct_observed_historical_task_values(
        source,
        registry=registry,
        unit_context_index=unit_context_index,
    )
    parent_bindings = CARRIER.historical_task_bindings(source)
    radial = CARRIER.validate_forward_task_envelope(
        CARRIER.RADIAL_FIXTURE_PATH.read_bytes(),
        payload_schema_raw_bytes=payload_schema_raw,
        registry_raw_bytes=registry_raw,
        unit_context_index=unit_context_index,
        runtime=runtime,
    )
    annotation = CARRIER.validate_forward_task_envelope(
        CARRIER.ANNOTATION_FIXTURE_PATH.read_bytes(),
        payload_schema_raw_bytes=payload_schema_raw,
        registry_raw_bytes=registry_raw,
        unit_context_index=unit_context_index,
        runtime=runtime,
    )
    parent_recipe = TYPED_VALUES.parse_strict_json(
        source.final_recipe_bytes, label="historical accepted recipe"
    )
    if type(parent_recipe) is not dict:
        raise ValueError("historical accepted recipe is invalid")
    partition = CARRIER.derive_authority_partition(
        parent_values=parent_values,
        parent_bindings=parent_bindings,
        successor=radial,
        parent_recipe=parent_recipe,
    )
    migration = CARRIER.verify_exact_migration(
        parent_values=parent_values,
        parent_bindings=parent_bindings,
        successor=radial,
        partition=partition,
    )
    parent_witness = CARRIER.build_outcome_neutral_parent_witness(
        derivative_archive=CARRIER.OFFICIAL_DERIVATIVE,
        runtime=runtime,
    )
    frozen_inputs = CARRIER.frozen_gate_inputs(source)
    controls = (
        CARRIER.build_control_compatibility_witness(
            repo_root / "scripts" / "lm9b_c_fixtures" / "r01_recipe.json",
            acceptance_boundary="lm9b_c_frozen_input",
            frozen_inputs=None,
            registry=registry,
            unit_context_index=unit_context_index,
        ),
        CARRIER.build_control_compatibility_witness(
            repo_root
            / "mcp_server"
            / "tests"
            / "fixtures"
            / "lm9b_p"
            / "non_r01_ready_recipe.json",
            acceptance_boundary="planner_mechanical_gate",
            frozen_inputs=frozen_inputs,
            registry=registry,
            unit_context_index=unit_context_index,
        ),
    )
    negatives = CARRIER.run_required_negative_cases(
        runtime=runtime,
        registry_raw_bytes=registry_raw,
        payload_schema_raw_bytes=payload_schema_raw,
        unit_context_index=unit_context_index,
        parent_task_envelope=records["authority.task_envelope"].value,
        parent_recipe=parent_recipe,
        radial_envelope_bytes=CARRIER.RADIAL_FIXTURE_PATH.read_bytes(),
        annotation_envelope_bytes=CARRIER.ANNOTATION_FIXTURE_PATH.read_bytes(),
    )
    if tuple(row.case_id for row in negatives) != CARRIER.required_negative_case_ids():
        raise ValueError("negative-case manifest is incomplete or reordered")
    return {
        "runtime": runtime,
        "profile": profile,
        "registry": registry,
        "payload_schema": payload_schema,
        "registry_raw": registry_raw,
        "payload_schema_raw": payload_schema_raw,
        "source": source,
        "unit_context_index": unit_context_index,
        "radial": radial,
        "annotation": annotation,
        "partition": partition,
        "migration": migration,
        "parent_witness": parent_witness,
        "controls": controls,
        "negatives": negatives,
    }


def _build_members(
    *,
    repo_root: Path,
    destination: Path,
    snapshot: QualificationSnapshot | None = None,
    transition: Mapping[str, object] | None = None,
) -> tuple[
    dict[str, bytes], Mapping[str, object], QualificationSnapshot
]:
    destination = destination.resolve()
    if snapshot is None:
        snapshot = build_qualification_snapshot(repo_root=repo_root.resolve())
    if transition is None:
        transition = _derive_transition(repo_root.resolve())
    runtime = transition["runtime"]
    profile = transition["profile"]
    registry = transition["registry"]
    payload_schema = transition["payload_schema"]
    source = transition["source"]
    radial = transition["radial"]
    annotation = transition["annotation"]
    partition = transition["partition"]
    parent_witness = transition["parent_witness"]
    controls = transition["controls"]
    negatives = transition["negatives"]
    assert isinstance(runtime, TYPED_VALUES.RuntimeIdentity)
    assert isinstance(profile, TYPED_VALUES.ProfileIdentity)
    assert isinstance(registry, TYPED_VALUES.VerifiedSemanticValueRegistry)
    assert isinstance(payload_schema, TYPED_VALUES.AdmittedSchema)
    assert isinstance(source, CONT_ARTIFACTS.VerifiedHistoricalSource)
    assert isinstance(radial, CARRIER.VerifiedForwardTaskEnvelope)
    assert isinstance(annotation, CARRIER.VerifiedForwardTaskEnvelope)
    assert isinstance(partition, CARRIER.AuthorityPartition)
    assert isinstance(parent_witness, CARRIER.OutcomeNeutralParentWitness)
    assert isinstance(controls, tuple) and len(controls) == 2
    assert all(
        isinstance(control, CARRIER.ControlCompatibilityWitness)
        for control in controls
    )
    assert isinstance(negatives, tuple)
    if (
        runtime != snapshot.runtime
        or profile.fingerprint != snapshot.profile_fingerprint
        or registry.fingerprint != snapshot.registry_fingerprint
        or payload_schema.schema_fingerprint
        != snapshot.payload_schema_fingerprint
    ):
        raise ValueError("qualification snapshot differs from derived transition")

    record: dict[str, object] = {
        "schema": QUALIFICATION_SCHEMA_ID,
        "stage": "qualification_complete",
        "eligibility": "independent_review_candidate",
        "canonical_destination": str(destination),
        "reviewed_commit": snapshot.commit_sha,
        "checkout_clean": snapshot.clean_checkout,
        "snapshot_fingerprint": snapshot.snapshot_fingerprint,
        "source_manifest_raw_sha256": source.pins.root_manifest_raw_sha256,
        "recipe_raw_sha256": source.pins.recipe_raw_sha256,
        "recipe_fingerprint": source.pins.ratified_recipe_fingerprint,
        "derivative_archive_identity": parent_witness.derivative_archive_identity,
        "classification": parent_witness.classification,
        "unresolved_keys": list(parent_witness.unresolved_keys),
        "migration_keys": list(partition.migration_keys),
        "authority_delta_keys": list(partition.authority_delta_keys),
        "required_delta_keys": list(partition.required_delta_keys),
        "partition_fingerprint": partition.partition_fingerprint,
    }
    historical_binding = {
        "schema": "rook.lm9.typed_fact_carrier_historical_binding:v1",
        **dict(source.identity_value),
        "unit_context_proof_fingerprint": transition[
            "unit_context_index"
        ].proof_fingerprint,
    }
    derivative_binding = {
        "schema": "rook.lm9.typed_fact_carrier_derivative_binding:v1",
        "archive_dir": str(CARRIER.OFFICIAL_DERIVATIVE.resolve()),
        "derivative_archive_identity": parent_witness.derivative_archive_identity,
        "evaluator_recommendation": parent_witness.evaluator_recommendation,
    }
    radial_result = {
        "schema": "rook.lm9.typed_fact_carrier_radial_witness:v1",
        "validated": True,
        "artifact_fingerprint": radial.artifact_fingerprint,
        "fact_count": len(radial.facts),
        "migration": [CARRIER.value_for_evidence(row) for row in transition["migration"]],
        "partition_fingerprint": partition.partition_fingerprint,
    }
    annotation_result = {
        "schema": "rook.lm9.typed_fact_carrier_annotation_witness:v1",
        "validated": True,
        "artifact_fingerprint": annotation.artifact_fingerprint,
        "fact_count": len(annotation.facts),
        "schemas": sorted({row.schema.schema_id for row in annotation.facts.values()}),
    }
    negative_result = {
        "schema": "rook.lm9.typed_fact_carrier_negative_cases:v1",
        "required_case_set_fingerprint": TYPED_VALUES.fingerprint(
            list(CARRIER.required_negative_case_ids())
        ),
        "results": [asdict(row) for row in negatives],
    }
    parent_result = {
        "schema": "rook.lm9.typed_fact_carrier_blocked_parent:v1",
        **asdict(parent_witness),
    }
    control_result = {
        "schema": "rook.lm9.typed_fact_carrier_control_compatibility:v1",
        "controls": [asdict(control) for control in controls],
    }
    boundary = {
        "schema": "rook.lm9.typed_fact_carrier_boundary:v1",
        "archived_evaluator_evidence_verified": True,
        "lm9b_c_manifest_verification": True,
        "planner_mechanical_gate_evaluation": True,
        "model_activity": False,
        "provider_activity": False,
        "readiness_activity": False,
        "evaluator_dispatch_activity": False,
        "planner_dispatch_activity": False,
        "compiler_dispatch_activity": False,
        "rhino_activity": False,
        "grasshopper_activity": False,
        "product_authority_activity": False,
        "claims": [
            "scientific_instrument_qualification_only",
            "no_lm9a_validity_or_compile_readiness_claim",
            "no_model_or_provider_dispatch",
        ],
    }
    members = {
        "record.json": _json_bytes(record),
        "snapshot.json": _json_bytes(_snapshot_value(snapshot)),
        "contracts/profile.json": _json_bytes(profile.value),
        "contracts/semantic-value-registry.json": transition["registry_raw"],
        "contracts/task-payload-schema.json": transition["payload_schema_raw"],
        "source/historical-binding.json": _json_bytes(historical_binding),
        "source/derivative-binding.json": _json_bytes(derivative_binding),
        "results/blocked-parent.json": _json_bytes(parent_result),
        "results/control-compatibility.json": _json_bytes(control_result),
        "results/radial-witness.json": _json_bytes(radial_result),
        "results/annotation-witness.json": _json_bytes(annotation_result),
        "results/negative-cases.json": _json_bytes(negative_result),
        "boundary.json": _json_bytes(boundary),
    }
    return members, MappingProxyType(record), snapshot


def _checksum_value(
    members: Mapping[str, bytes], *, destination: Path
) -> dict[str, object]:
    rows = [
        {"path": path, "raw_sha256": _sha256(raw)}
        for path, raw in sorted(members.items())
    ]
    identity_source = {
        "schema": QUALIFICATION_SCHEMA_ID,
        "canonical_destination": str(destination.resolve()),
        "members": rows,
    }
    return {
        "schema": CHECKSUMS_SCHEMA_ID,
        "canonical_destination": str(destination.resolve()),
        "members": rows,
        "qualification_identity": TYPED_VALUES.fingerprint(identity_source),
    }


def _archive_members(archive: Path) -> set[str]:
    return {
        path.relative_to(archive).as_posix()
        for path in archive.rglob("*")
        if path.is_file()
    }


def _verify_archive(
    archive_dir: Path,
    *,
    expected_identity: str | None,
    enforce_location: bool,
) -> VerifiedQualification:
    archive = Path(archive_dir).resolve()
    if not archive.is_dir() or _archive_members(archive) != FINAL_MEMBERS:
        raise ValueError("qualification archive membership is not closed")
    checksum_value = TYPED_VALUES.parse_strict_json(
        (archive / "checksums.json").read_bytes(), label="qualification checksums"
    )
    if type(checksum_value) is not dict or set(checksum_value) != {
        "schema",
        "canonical_destination",
        "members",
        "qualification_identity",
    } or checksum_value["schema"] != CHECKSUMS_SCHEMA_ID:
        raise ValueError("qualification checksums shape is invalid")
    canonical_destination = Path(checksum_value["canonical_destination"]).resolve()
    if enforce_location and archive != canonical_destination:
        raise ValueError("qualification archive is not at its bound destination")
    rows = checksum_value["members"]
    if type(rows) is not list or [row.get("path") for row in rows] != sorted(
        FINAL_MEMBERS - {"checksums.json"}
    ):
        raise ValueError("qualification checksum rows are invalid")
    persisted: dict[str, bytes] = {}
    for row in rows:
        if type(row) is not dict or set(row) != {"path", "raw_sha256"}:
            raise ValueError("qualification checksum row shape is invalid")
        raw = (archive / row["path"]).read_bytes()
        if _sha256(raw) != row["raw_sha256"]:
            raise ValueError("qualification member checksum mismatch")
        persisted[row["path"]] = raw
    expected_checksums = _checksum_value(
        persisted, destination=canonical_destination
    )
    if checksum_value != expected_checksums:
        raise ValueError("qualification aggregate identity mismatch")
    identity = checksum_value["qualification_identity"]
    if expected_identity is not None and identity != expected_identity:
        raise ValueError("qualification identity differs from expectation")
    rebuilt, expected_record, expected_snapshot = _build_members(
        repo_root=_REPO_ROOT,
        destination=canonical_destination,
    )
    if persisted != rebuilt:
        raise ValueError("qualification claims differ from reconstructed transition")
    record = TYPED_VALUES.parse_strict_json(
        persisted["record.json"], label="qualification record"
    )
    if type(record) is not dict or record != dict(expected_record):
        raise ValueError("qualification record reconstruction mismatch")
    snapshot = _snapshot_from_bytes(persisted["snapshot.json"])
    if snapshot != expected_snapshot:
        raise ValueError("qualification snapshot reconstruction mismatch")
    return VerifiedQualification(
        archive_dir=canonical_destination if not enforce_location else archive,
        qualification_identity=identity,
        snapshot=snapshot,
        record=MappingProxyType(record),
    )


def write_qualification_archive(
    *, repo_root: Path, destination: Path
) -> VerifiedQualification:
    repo = Path(repo_root).resolve()
    destination = Path(destination).resolve()
    staging = destination.with_name(destination.name + ".staging")
    if destination.exists():
        raise FileExistsError(f"qualification destination already exists: {destination}")
    if staging.exists():
        raise FileExistsError(f"qualification staging already exists: {staging}")
    snapshot = build_qualification_snapshot(repo_root=repo)
    _require_snapshot_current(snapshot, repo_root=repo)
    _verify_source_and_derivative_bindings()
    staging.mkdir(parents=False, exist_ok=False)
    snapshot_bytes = _json_bytes(_snapshot_value(snapshot))
    (staging / "snapshot.json").write_bytes(snapshot_bytes)
    if (staging / "snapshot.json").read_bytes() != snapshot_bytes:
        raise ValueError("persisted qualification snapshot bytes changed")
    if _snapshot_from_bytes(snapshot_bytes) != snapshot:
        raise ValueError("persisted qualification snapshot identity changed")
    _require_snapshot_current(snapshot, repo_root=repo)
    transition = _derive_transition(repo)
    members, _record, _snapshot = _build_members(
        repo_root=repo,
        destination=destination,
        snapshot=snapshot,
        transition=transition,
    )
    if members["snapshot.json"] != snapshot_bytes:
        raise ValueError("derived members changed the persisted snapshot")
    checksums = _checksum_value(members, destination=destination)
    members["checksums.json"] = _json_bytes(checksums)
    for relative, raw in sorted(members.items()):
        if relative == "snapshot.json":
            continue
        path = staging / Path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    _verify_archive(
        staging,
        expected_identity=checksums["qualification_identity"],
        enforce_location=False,
    )
    staging.rename(destination)
    return verify_qualification_archive(
        destination,
        expected_identity=checksums["qualification_identity"],
    )


def verify_qualification_archive(
    archive_dir: Path, *, expected_identity: str | None = None
) -> VerifiedQualification:
    return _verify_archive(
        archive_dir,
        expected_identity=expected_identity,
        enforce_location=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    qualify = subparsers.add_parser("qualify")
    qualify.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    qualify.add_argument("--destination", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--archive", type=Path, required=True)
    verify.add_argument("--expected-identity")
    args = parser.parse_args(argv)
    if args.command == "qualify":
        result = write_qualification_archive(
            repo_root=args.repo_root, destination=args.destination
        )
    else:
        result = verify_qualification_archive(
            args.archive, expected_identity=args.expected_identity
        )
    print(
        json.dumps(
            {
                "archive_dir": str(result.archive_dir),
                "qualification_identity": result.qualification_identity,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
