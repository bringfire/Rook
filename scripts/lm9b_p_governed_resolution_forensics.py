from __future__ import annotations

import ast
import hashlib
import json
import os
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

import lm9b_p_governed_resolution_archive_evidence as ARCHIVE_EVIDENCE
import lm9b_p_governed_resolution_artifacts as ARTIFACTS
import lm9b_p_governed_resolution_support as SUPPORT
import lm9b_p_planner_recipe_transfer_artifacts as PLANNER_ARTIFACTS
import lm9b_p_planner_recipe_transfer_support as PLANNER_SUPPORT


OBSERVED_COMMIT_SHA = "e81b12cca0eb750a7f3e730d2376085a915d43dd"
OBSERVED_PREFLIGHT_FINGERPRINT = (
    "sha256:897337de3d20e126a143576de707ec3b1377033eab49465ac38d793afd97a856"
)
OBSERVED_INSTRUMENT_FINGERPRINT = (
    "sha256:0b57f30954c375df34b28ba394f2ef281c09388c209e688586187d8759f26d11"
)
OBSERVED_ATTEMPT_FINGERPRINT = (
    "sha256:bd350d895f0e34a67aa7ebe59e1e8c4b3b5b3f4e715aa6d81d5874561af10e42"
)
OBSERVED_ATTEMPT_ID = "governed-resolution-e81b12cca0eb-replacement-01"
OBSERVED_RESOLUTION_ROOT = Path(
    r"C:\Users\bring\rook-lm9b-p-attempts"
    r"\2026-07-27-governed-resolution-operational"
)
OBSERVED_PREFLIGHT_ARCHIVE = (
    OBSERVED_RESOLUTION_ROOT / f"{OBSERVED_ATTEMPT_ID}-preflight"
)
OBSERVED_DESTINATION = OBSERVED_RESOLUTION_ROOT / OBSERVED_ATTEMPT_ID
OBSERVED_STAGING = OBSERVED_RESOLUTION_ROOT / f".{OBSERVED_ATTEMPT_ID}.staging"
OBSERVED_MARKER_SHA256 = (
    "sha256:c307db9cf7220df203086c2ce348cdad4bf2def1029653d2125ba6341632a501"
)
OBSERVED_CANDIDATE_CHECKSUMS_SHA256 = (
    "sha256:ee01977cce93887f48cc6a2f13cc33a8e24d00a38ab002f59519c67b03a97999"
)
_OBSERVED_INITIAL_REQUEST_SHA256 = (
    "sha256:c1af3a9bc8b7e9f93fc137140a91155e2fe8297ff2ceb5da8b2e882982563f98"
)
_OBSERVED_INSTRUMENT_MANIFEST_FINGERPRINT = (
    "sha256:06b09362a60af25f4d2f3a445d0555f21794a77f0a7ceecd3aa669d720ad17e0"
)
_PREFLIGHT_MEMBERS = frozenset(
    {"record.json", "initial-request.json", "checksums.json"}
)


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _strict_object(raw: bytes, label: str) -> dict[str, object]:
    value = PLANNER_SUPPORT.parse_archive_json(raw)
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def _path_has_reparse_ambiguity(path: Path) -> bool:
    current = path
    while True:
        try:
            info = os.lstat(current)
        except OSError:
            return True
        attributes = getattr(info, "st_file_attributes", 0)
        if stat.S_ISLNK(info.st_mode) or bool(
            attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            return True
        if current.parent == current:
            return False
        current = current.parent


def _flat_snapshot(path: Path, *, expected: frozenset[str]) -> tuple[Path, dict[str, bytes], tuple[object, ...]]:
    archive = Path(path)
    if not archive.is_absolute() or _path_has_reparse_ambiguity(archive):
        raise ValueError("forensic evidence path is not a physical absolute path")
    archive = archive.resolve()
    rows: list[tuple[object, ...]] = []
    members: dict[str, bytes] = {}
    names: set[str] = set()
    with os.scandir(archive) as stream:
        for entry in stream:
            names.add(entry.name)
            if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                raise ValueError("forensic evidence membership is not file-only")
            raw = Path(entry.path).read_bytes()
            info = entry.stat(follow_symlinks=False)
            members[entry.name] = raw
            rows.append(
                (
                    entry.name,
                    "file",
                    len(raw),
                    getattr(info, "st_dev", None),
                    getattr(info, "st_ino", None),
                    _sha256(raw),
                )
            )
    if names != set(expected):
        raise ValueError("forensic evidence membership is not closed")
    root_info = os.lstat(archive)
    identity: tuple[object, ...] = (
        str(archive),
        getattr(root_info, "st_dev", None),
        getattr(root_info, "st_ino", None),
        tuple(sorted(rows)),
    )
    return archive, members, identity


def _recursive_snapshot(path: Path) -> tuple[dict[str, bytes], tuple[object, ...]]:
    root = Path(path)
    if not root.is_absolute() or _path_has_reparse_ambiguity(root):
        raise ValueError("forensic staging path is not a physical absolute path")
    root = root.resolve()
    files: dict[str, bytes] = {}
    rows: list[tuple[object, ...]] = []

    def visit(directory: Path) -> None:
        with os.scandir(directory) as stream:
            entries = sorted(stream, key=lambda item: item.name)
        for entry in entries:
            relative = Path(entry.path).relative_to(root).as_posix()
            info = entry.stat(follow_symlinks=False)
            attributes = getattr(info, "st_file_attributes", 0)
            if entry.is_symlink() or bool(
                attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            ):
                raise ValueError("forensic staging contains a reparse entry")
            if entry.is_dir(follow_symlinks=False):
                rows.append(
                    (
                        relative,
                        "directory",
                        getattr(info, "st_dev", None),
                        getattr(info, "st_ino", None),
                    )
                )
                visit(Path(entry.path))
            elif entry.is_file(follow_symlinks=False):
                raw = Path(entry.path).read_bytes()
                files[relative] = raw
                rows.append(
                    (
                        relative,
                        "file",
                        len(raw),
                        getattr(info, "st_dev", None),
                        getattr(info, "st_ino", None),
                        _sha256(raw),
                    )
                )
            else:
                raise ValueError("forensic staging contains a non-file entry")

    visit(root)
    root_info = os.lstat(root)
    identity: tuple[object, ...] = (
        str(root),
        getattr(root_info, "st_dev", None),
        getattr(root_info, "st_ino", None),
        tuple(rows),
    )
    return files, identity


_GIT_PATHS = (
    "scripts/lm9_semantic_typed_values.py",
    "scripts/lm9_typed_fact_carrier_artifacts.py",
    "scripts/lm9_typed_fact_carrier_qualification.py",
    "scripts/lm9_typed_fact_carrier_contracts/semantic_value_schema_registry.json",
    "scripts/lm9_typed_fact_carrier_contracts/planner_task_typed_facts_payload_schema.json",
    "scripts/lm9_typed_fact_carrier_fixtures/radial_successor_task_envelope.json",
    "scripts/lm9b_c_compiler_sufficiency_probe.py",
    "scripts/lm9b_p_governed_resolution_artifacts.py",
    "scripts/lm9b_p_governed_resolution_contracts/isolation_policy.json",
    "scripts/lm9b_p_governed_resolution_contracts/planner_revision_evaluation_rubric.json",
    "scripts/lm9b_p_governed_resolution_probe.py",
    "scripts/lm9b_p_governed_resolution_support.py",
    "scripts/lm9b_p_planner_recipe_transfer_artifacts.py",
    "scripts/lm9b_p_planner_recipe_transfer_support.py",
    "scripts/lm9b_p_readiness_contract.py",
)


_SOURCE_BINDINGS = (
    ("archive.public_verifier_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "verify_sealed_resolution_checkpoint"),
    ("archive.seal_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "seal_resolution_checkpoint"),
    ("decision.blocker_projection_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_artifacts.py", "derive_probe_explicit_blockers"),
    ("decision.call_ledger_verifier_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "verify_resolution_call_ledger"),
    ("decision.classifier_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_artifacts.py", "derive_evaluated_recipe_classification"),
    ("evaluator.parser_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_support.py", "derive_planner_evaluation_result"),
    ("evaluator.provider_request_builder_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_support.py", "build_planner_evaluator_provider_call_request"),
    ("evaluator.renderer_source_fingerprint", "scripts/lm9b_p_governed_resolution_support.py", "render_planner_revision_evaluation_request"),
    ("isolation.gate_source_fingerprint", "scripts/lm9b_p_governed_resolution_support.py", "evaluate_resolution_isolation"),
    ("launch_invocation.builder_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "build_resolution_invocation_binding"),
    ("launch_invocation.verifier_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "verify_resolution_invocation_binding"),
    ("planner.call_plan_builder_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_support.py", "build_planner_provider_call_plan"),
    ("planner.controller_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_support.py", "run_planner_session"),
    ("planner.feedback_renderer_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_support.py", "build_planner_mechanical_feedback_message"),
    ("planner.mechanical_gate_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_support.py", "evaluate_mechanical_gate"),
    ("planner.provider_request_builder_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_support.py", "build_planner_provider_call_request"),
    ("planner.revision_renderer_source_fingerprint", "scripts/lm9b_p_governed_resolution_support.py", "render_planner_revision_request"),
    ("preflight.public_verifier_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "verify_resolution_preflight"),
    ("preflight.reservation_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "reserve_resolution_staging"),
    ("preflight.writer_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "write_resolution_preflight"),
    ("readiness.role_adapter_binding.litellm_adapter_call_source_fingerprint", "scripts/lm9b_c_compiler_sufficiency_probe.py", "LiteLLMProvider.__call__"),
    ("readiness.role_adapter_binding.litellm_request_projection_source_fingerprint", "scripts/lm9b_c_compiler_sufficiency_probe.py", "build_litellm_completion_request_bytes"),
    ("readiness.route_identity_projection_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "readiness_route_identity_projection"),
    ("readiness.verifier_source_fingerprint", "scripts/lm9b_p_readiness_contract.py", "verify_launch_readiness"),
    ("ready_proof.consumer_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "consume_resolution_ready_proof"),
    ("ready_proof.issuer_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "issue_resolution_ready_proof"),
    ("ready_proof.snapshot_verifier_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "verify_sealed_resolution_checkpoint"),
    ("verified_inputs.carrier_compatibility_verifier_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "_verify_historical_carrier_qualification_compatibility_unsealed"),
    ("verified_inputs.physical_source_loader_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "_load_verified_resolution_sources_unsealed"),
    ("verified_inputs.pure_input_assembler_source_fingerprint", "scripts/lm9b_p_governed_resolution_support.py", "_build_resolution_inputs_capability.derive"),
)


def _mapping_path(value: Mapping[str, object], dotted: str) -> object:
    current: object = value
    for part in dotted.split("."):
        if type(current) is not dict:
            raise ValueError(f"historical instrument path is absent: {dotted}")
        current = current.get(part)
    return current


def _git_blob(repo: Path, relative: str) -> tuple[bytes, str]:
    raw = subprocess.run(
        ["git", "show", f"{OBSERVED_COMMIT_SHA}:{relative}"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    blob = subprocess.run(
        ["git", "rev-parse", f"{OBSERVED_COMMIT_SHA}:{relative}"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return raw, blob


def _git_blob_map(repo: Path) -> tuple[dict[str, bytes], tuple[Mapping[str, object], ...]]:
    blobs: dict[str, bytes] = {}
    rows: list[Mapping[str, object]] = []
    for relative in _GIT_PATHS:
        raw, blob_id = _git_blob(repo, relative)
        blobs[relative] = raw
        rows.append(
            MappingProxyType(
                {
                    "path": relative,
                    "git_blob_id": blob_id,
                    "byte_length": len(raw),
                    "raw_sha256": _sha256(raw),
                }
            )
        )
    return blobs, tuple(rows)


def _source_bytes(raw: bytes, qualified_name: str) -> bytes:
    text = raw.decode("utf-8")
    tree = ast.parse(text)
    parts = qualified_name.split(".")
    nodes: list[ast.AST] = list(tree.body)
    selected: ast.AST | None = None
    for part in parts:
        selected = next(
            (
                node
                for node in nodes
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.name == part
            ),
            None,
        )
        if selected is None:
            raise ValueError(f"historical callable is absent: {qualified_name}")
        nodes = list(getattr(selected, "body", ()))
    assert selected is not None and selected.end_lineno is not None
    decorators = getattr(selected, "decorator_list", ())
    start = min(
        [selected.lineno, *(item.lineno for item in decorators)]
    )
    lines = text.splitlines(keepends=True)
    return "".join(lines[start - 1 : selected.end_lineno]).encode("utf-8")


def _verify_historical_preflight_projection(
    *,
    archive: Path,
    members: Mapping[str, bytes],
    git_blobs: Mapping[str, bytes],
) -> tuple[dict[str, object], tuple[Mapping[str, object], ...]]:
    record = _strict_object(members["record.json"], "historical preflight")
    checksums = _strict_object(members["checksums.json"], "historical checksums")
    expected_checksums = {
        "schema": checksums.get("schema"),
        "members": [
            {"path": name, "raw_sha256": _sha256(members[name])}
            for name in ("initial-request.json", "record.json")
        ],
    }
    if checksums != expected_checksums:
        raise ValueError("historical preflight checksum closure differs")
    if (
        set(record)
        != {
            "schema",
            "canonical_preflight_destination",
            "reviewed_commit_sha",
            "historical_qualification_identity",
            "carrier_compatibility_fingerprint",
            "instrument_fingerprint",
            "instrument_contracts",
            "initial_request_raw_sha256",
            "attempt",
            "preflight_fingerprint",
        }
        or record.get("schema") != ARTIFACTS.PREFLIGHT_SCHEMA_ID
        or record.get("canonical_preflight_destination") != str(archive)
        or record.get("reviewed_commit_sha") != OBSERVED_COMMIT_SHA
        or record.get("instrument_fingerprint") != OBSERVED_INSTRUMENT_FINGERPRINT
        or record.get("initial_request_raw_sha256") != _OBSERVED_INITIAL_REQUEST_SHA256
        or _sha256(members["initial-request.json"]) != _OBSERVED_INITIAL_REQUEST_SHA256
        or record.get("preflight_fingerprint") != OBSERVED_PREFLIGHT_FINGERPRINT
        or PLANNER_SUPPORT.fingerprint_without(record, "preflight_fingerprint")
        != OBSERVED_PREFLIGHT_FINGERPRINT
    ):
        raise ValueError("historical preflight root reconstruction differs")
    manifest = record["instrument_contracts"]
    if (
        type(manifest) is not dict
        or PLANNER_SUPPORT.fingerprint(manifest) != OBSERVED_INSTRUMENT_FINGERPRINT
        or _sha256(_canonical_bytes(manifest))
        != _OBSERVED_INSTRUMENT_MANIFEST_FINGERPRINT
        or manifest.get("reviewed_commit_sha") != OBSERVED_COMMIT_SHA
    ):
        raise ValueError("historical instrument reconstruction differs")
    attempt = record["attempt"]
    expected_attempt = {
        "attempt_id": OBSERVED_ATTEMPT_ID,
        "resolution_root": str(OBSERVED_RESOLUTION_ROOT),
        "canonical_destination": str(OBSERVED_DESTINATION),
        "staging_path": str(OBSERVED_STAGING),
        "attempt_fingerprint": OBSERVED_ATTEMPT_FINGERPRINT,
    }
    if type(attempt) is not dict or attempt != expected_attempt:
        raise ValueError("historical attempt binding differs")
    if PLANNER_SUPPORT.fingerprint(
        {
            "instrument_fingerprint": OBSERVED_INSTRUMENT_FINGERPRINT,
            "attempt_id": OBSERVED_ATTEMPT_ID,
            "canonical_destination": str(OBSERVED_DESTINATION),
        }
    ) != OBSERVED_ATTEMPT_FINGERPRINT:
        raise ValueError("historical attempt equation differs")
    for dotted, relative, symbol in _SOURCE_BINDINGS:
        observed = _mapping_path(manifest, dotted)
        derived = _sha256(_source_bytes(git_blobs[relative], symbol))
        if observed != derived:
            raise ValueError(f"historical source fingerprint differs: {dotted}")
    raw_bindings = {
        "readiness.role_adapter_binding.execution_module_raw_sha256": (
            "scripts/lm9b_p_governed_resolution_probe.py"
        ),
        "readiness.role_adapter_binding.litellm_provider_module_raw_sha256": (
            "scripts/lm9b_c_compiler_sufficiency_probe.py"
        ),
    }
    for dotted, relative in raw_bindings.items():
        if _mapping_path(manifest, dotted) != _sha256(git_blobs[relative]):
            raise ValueError(f"historical raw source differs: {dotted}")
    diagnostic = {
        "contract": "source_defined_planner_diagnostics:v1",
        "submission_parser_source": _sha256(
            _source_bytes(
                git_blobs["scripts/lm9b_p_planner_recipe_transfer_support.py"],
                "derive_planner_submission_from_message",
            )
        ),
        "mechanical_gate_source": _mapping_path(
            manifest, "planner.mechanical_gate_source_fingerprint"
        ),
        "feedback_renderer_source": _mapping_path(
            manifest, "planner.feedback_renderer_source_fingerprint"
        ),
    }
    if _mapping_path(manifest, "planner.diagnostic_vocabulary_fingerprint") != PLANNER_SUPPORT.fingerprint(diagnostic):
        raise ValueError("historical diagnostic vocabulary differs")
    return record, tuple()


@dataclass(frozen=True)
class _HistoricalPreflightSnapshot:
    archive_dir: Path
    record: Mapping[str, object]
    members: Mapping[str, bytes]
    git_manifest: tuple[Mapping[str, object], ...]
    physical_identity: tuple[object, ...]


@dataclass(frozen=True)
class _ForensicSourceCapabilitySnapshot:
    source: ForensicSourceSnapshot
    historical: _HistoricalPreflightSnapshot


@dataclass(frozen=True)
class ResolutionForensicReconstruction:
    observed_commit_sha: str
    forensic_commit_sha: str
    planner_call_count: int
    evaluator_call_count: int
    mechanical_status: str
    isolation_status: str
    reconstructed_classification: str
    candidate_recipe_raw_sha256: str
    call_ledger_fingerprint: str
    gate_fingerprint: str
    isolation_fingerprint: str
    reconstruction_fingerprint: str


@dataclass(frozen=True)
class ForensicSourceSnapshot:
    staging_path: Path
    destination_path: Path
    preflight_members: Mapping[str, bytes]
    marker_bytes: bytes
    candidate_members: Mapping[str, bytes]
    before_identity: tuple[object, ...]


class VerifiedHistoricalResolutionPreflightForensics:
    __slots__ = ("__weakref__",)

    def __new__(cls) -> "VerifiedHistoricalResolutionPreflightForensics":
        raise TypeError("historical forensic preflight carriers are closure-issued")


class VerifiedResolutionForensicSource:
    __slots__ = ("__weakref__",)

    def __new__(cls) -> "VerifiedResolutionForensicSource":
        raise TypeError("resolution forensic source carriers are closure-issued")


def _build_forensic_capabilities():
    historical_issued: weakref.WeakKeyDictionary[
        VerifiedHistoricalResolutionPreflightForensics,
        _HistoricalPreflightSnapshot,
    ] = weakref.WeakKeyDictionary()
    source_issued: weakref.WeakKeyDictionary[
        VerifiedResolutionForensicSource,
        _ForensicSourceCapabilitySnapshot,
    ] = weakref.WeakKeyDictionary()

    def verify_historical(
        *,
        repo_root: Path,
        preflight_archive: Path,
        expected_preflight_fingerprint: str,
    ) -> VerifiedHistoricalResolutionPreflightForensics:
        snapshot = _verify_historical_resolution_preflight_forensics_unsealed(
            repo_root=repo_root,
            preflight_archive=preflight_archive,
            expected_preflight_fingerprint=expected_preflight_fingerprint,
        )
        issued = object.__new__(VerifiedHistoricalResolutionPreflightForensics)
        historical_issued[issued] = snapshot
        return issued

    def consume_historical(
        value: object,
    ) -> _HistoricalPreflightSnapshot:
        if type(value) is not VerifiedHistoricalResolutionPreflightForensics:
            raise TypeError("closure-issued historical forensic preflight required")
        snapshot = historical_issued.get(value)
        if snapshot is None:
            raise ValueError("historical forensic preflight was not issued")
        return snapshot

    def load_source(
        *,
        historical_preflight: object,
        staging_dir: Path,
        expected_marker_sha256: str,
        expected_candidate_checksums_sha256: str,
    ) -> VerifiedResolutionForensicSource:
        historical = consume_historical(historical_preflight)
        snapshot = _load_verified_resolution_forensic_source_unsealed(
            historical=historical,
            staging_dir=staging_dir,
            expected_marker_sha256=expected_marker_sha256,
            expected_candidate_checksums_sha256=(
                expected_candidate_checksums_sha256
            ),
        )
        issued = object.__new__(VerifiedResolutionForensicSource)
        source_issued[issued] = snapshot
        return issued

    def consume_source(value: object) -> _ForensicSourceCapabilitySnapshot:
        if type(value) is not VerifiedResolutionForensicSource:
            raise TypeError("closure-issued resolution forensic source required")
        snapshot = source_issued.get(value)
        if snapshot is None:
            raise ValueError("resolution forensic source was not issued")
        return snapshot

    return verify_historical, consume_historical, load_source, consume_source


def _verify_historical_resolution_preflight_forensics_unsealed(
    *,
    repo_root: Path,
    preflight_archive: Path,
    expected_preflight_fingerprint: str,
) -> _HistoricalPreflightSnapshot:
    """Verify the one consumed e81 preflight without executing historical code."""

    repo = Path(repo_root).resolve()
    archive_argument = Path(preflight_archive)
    if (
        expected_preflight_fingerprint != OBSERVED_PREFLIGHT_FINGERPRINT
        or not archive_argument.is_absolute()
        or archive_argument != OBSERVED_PREFLIGHT_ARCHIVE
    ):
        raise ValueError("historical forensic preflight pin differs")
    archive, members, before = _flat_snapshot(
        archive_argument, expected=_PREFLIGHT_MEMBERS
    )
    if archive != OBSERVED_PREFLIGHT_ARCHIVE:
        raise ValueError("historical forensic preflight location differs")
    git_blobs, git_manifest = _git_blob_map(repo)
    record, _rows = _verify_historical_preflight_projection(
        archive=archive,
        members=members,
        git_blobs=git_blobs,
    )
    _archive_after, members_after, after = _flat_snapshot(
        archive_argument, expected=_PREFLIGHT_MEMBERS
    )
    if after != before or members_after != members:
        raise ValueError("historical forensic preflight moved during verification")
    return _HistoricalPreflightSnapshot(
        archive_dir=archive,
        record=MappingProxyType(record),
        members=MappingProxyType(dict(members)),
        git_manifest=git_manifest,
        physical_identity=before,
    )


def _load_verified_resolution_forensic_source_unsealed(
    *,
    historical: _HistoricalPreflightSnapshot,
    staging_dir: Path,
    expected_marker_sha256: str,
    expected_candidate_checksums_sha256: str,
) -> _ForensicSourceCapabilitySnapshot:
    """Freeze one immutable copy of the consumed attempt's retained evidence."""

    if (
        expected_marker_sha256 != OBSERVED_MARKER_SHA256
        or expected_candidate_checksums_sha256
        != OBSERVED_CANDIDATE_CHECKSUMS_SHA256
    ):
        raise ValueError("forensic retained-source identity differs from pin")
    if os.path.lexists(OBSERVED_DESTINATION):
        raise ValueError("reserved governed-resolution destination is present")
    staging = Path(staging_dir)
    files, before = _recursive_snapshot(staging)
    directory_paths = {
        row[0]
        for row in before[-1]
        if isinstance(row, tuple) and len(row) >= 2 and row[1] == "directory"
    }
    if directory_paths != {
        ".archive-candidate",
        ".resolution-runtime",
        ".resolution-runtime/calls",
    }:
        raise ValueError("forensic staging directory membership is not closed")
    marker_relative = "post_dispatch_unsealed.json"
    candidate_prefix = ".archive-candidate/"
    runtime_prefix = ".resolution-runtime/"
    if marker_relative not in files:
        raise ValueError("forensic post-dispatch marker is absent")
    marker_raw = files[marker_relative]
    if _sha256(marker_raw) != expected_marker_sha256:
        raise ValueError("forensic post-dispatch marker fingerprint differs")
    marker = _strict_object(marker_raw, "post-dispatch marker")
    if (
        set(marker)
        != {
            "schema",
            "attempt_fingerprint",
            "attempt_id",
            "failure_locus",
            "forensic_hashes",
            "instrument_fingerprint",
            "preflight_fingerprint",
        }
        or marker.get("attempt_id") != OBSERVED_ATTEMPT_ID
        or marker.get("attempt_fingerprint") != OBSERVED_ATTEMPT_FINGERPRINT
        or marker.get("instrument_fingerprint") != OBSERVED_INSTRUMENT_FINGERPRINT
        or marker.get("preflight_fingerprint") != OBSERVED_PREFLIGHT_FINGERPRINT
        or marker.get("failure_locus")
        != "checkpoint_seal_failure:StrictJsonError"
    ):
        raise ValueError("forensic post-dispatch marker binding differs")
    forensic_rows = marker.get("forensic_hashes")
    if type(forensic_rows) is not list:
        raise ValueError("forensic post-dispatch hash rows are invalid")
    expected_files = {marker_relative}
    for row in forensic_rows:
        if (
            type(row) is not dict
            or set(row) != {"path", "sha256", "size"}
            or type(row.get("path")) is not str
            or row["path"] in expected_files
            or row["path"].startswith("/")
            or ".." in Path(row["path"]).parts
        ):
            raise ValueError("forensic post-dispatch hash row is invalid")
        relative = row["path"]
        expected_files.add(relative)
        raw = files.get(relative)
        if (
            raw is None
            or row.get("size") != len(raw)
            or row.get("sha256") != _sha256(raw)
        ):
            raise ValueError("forensic post-dispatch retained bytes differ")
    if set(files) != expected_files:
        raise ValueError("forensic staging file membership is not closed")
    candidate_members = {
        relative.removeprefix(candidate_prefix): raw
        for relative, raw in files.items()
        if relative.startswith(candidate_prefix)
    }
    expected_candidate_members = ARTIFACTS.resolution_archive_member_paths(
        candidate_present=True,
        isolation_evaluated=True,
        evaluator_dispatched=False,
    )
    if set(candidate_members) != set(expected_candidate_members):
        raise ValueError("forensic archive-candidate membership differs")
    checksum_raw = candidate_members.get("checksums.json")
    if (
        checksum_raw is None
        or _sha256(checksum_raw) != expected_candidate_checksums_sha256
    ):
        raise ValueError("forensic archive-candidate checksum identity differs")
    checksums = _strict_object(checksum_raw, "candidate checksums")
    checksum_rows = checksums.get("members")
    expected_checksum_rows = [
        {"path": name, "raw_sha256": _sha256(raw)}
        for name, raw in sorted(candidate_members.items())
        if name != "checksums.json"
    ]
    if (
        set(checksums) != {"schema", "members"}
        or checksum_rows != expected_checksum_rows
    ):
        raise ValueError("forensic archive-candidate checksum closure differs")
    runtime_members = {
        relative.removeprefix(runtime_prefix): raw
        for relative, raw in files.items()
        if relative.startswith(runtime_prefix)
    }
    if (
        runtime_members.get("preflight.json")
        != historical.members["record.json"]
        or runtime_members.get("initial-request.json")
        != historical.members["initial-request.json"]
        or not any(name.startswith("calls/") for name in runtime_members)
    ):
        raise ValueError("forensic runtime root evidence differs")
    instrument = _strict_object(
        candidate_members["instrument.json"], "candidate instrument"
    )
    if (
        instrument.get("preflight_record") != dict(historical.record)
        or instrument.get("instrument_fingerprint")
        != OBSERVED_INSTRUMENT_FINGERPRINT
        or instrument.get("contract_manifest")
        != historical.record["instrument_contracts"]
    ):
        raise ValueError("forensic candidate instrument differs from preflight")
    record = _strict_object(candidate_members["record.json"], "candidate record")
    if (
        record.get("attempt_id") != OBSERVED_ATTEMPT_ID
        or record.get("attempt_fingerprint") != OBSERVED_ATTEMPT_FINGERPRINT
        or record.get("preflight_fingerprint") != OBSERVED_PREFLIGHT_FINGERPRINT
        or record.get("instrument_fingerprint") != OBSERVED_INSTRUMENT_FINGERPRINT
        or record.get("canonical_destination") != str(OBSERVED_DESTINATION)
    ):
        raise ValueError("forensic candidate root binding differs")
    files_after, after = _recursive_snapshot(staging)
    if after != before or files_after != files:
        raise ValueError("forensic staging moved during source verification")
    public = ForensicSourceSnapshot(
        staging_path=staging.resolve(),
        destination_path=OBSERVED_DESTINATION,
        preflight_members=MappingProxyType(dict(historical.members)),
        marker_bytes=marker_raw,
        candidate_members=MappingProxyType(dict(candidate_members)),
        before_identity=before,
    )
    return _ForensicSourceCapabilitySnapshot(
        source=public, historical=historical
    )


(
    verify_historical_resolution_preflight_forensics,
    _consume_historical_preflight,
    load_verified_resolution_forensic_source,
    _consume_forensic_source,
) = _build_forensic_capabilities()


def _current_commit(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def reconstruct_resolution_forensic_candidate(
    *,
    source: object,
    repo_root: Path,
    forensic_commit_sha: str,
) -> ResolutionForensicReconstruction:
    """Reconstruct one retained outcome without publishing or repairing it."""

    capability = _consume_forensic_source(source)
    frozen = capability.source
    historical = capability.historical
    repo = Path(repo_root).resolve()
    if (
        type(forensic_commit_sha) is not str
        or _current_commit(repo) != forensic_commit_sha
    ):
        raise ValueError("forensic reconstruction commit differs")
    if os.path.lexists(frozen.destination_path):
        raise ValueError("reserved governed-resolution destination appeared")
    _archive, preflight_members, preflight_identity = _flat_snapshot(
        historical.archive_dir, expected=_PREFLIGHT_MEMBERS
    )
    if (
        preflight_identity != historical.physical_identity
        or preflight_members != dict(historical.members)
    ):
        raise ValueError("historical preflight moved before reconstruction")
    staging_files, staging_identity = _recursive_snapshot(frozen.staging_path)
    if staging_identity != frozen.before_identity:
        raise ValueError("forensic staging moved before reconstruction")
    observed_candidate = {
        relative.removeprefix(".archive-candidate/"): raw
        for relative, raw in staging_files.items()
        if relative.startswith(".archive-candidate/")
    }
    if observed_candidate != dict(frozen.candidate_members):
        raise ValueError("forensic candidate bytes moved before reconstruction")

    profile, _profile_contract = ARTIFACTS._resolution_archive_resource_contract(
        forensic_commit_sha
    )
    call_ledger_value, call_shape = ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
        frozen.candidate_members["call-ledger.json"],
        profile=profile,
    )
    shape = ARCHIVE_EVIDENCE.consume_resolution_call_shape(
        call_shape, profile=profile
    )
    if shape["planner_count"] != 6 or shape["evaluator_count"] != 0:
        raise ValueError("retained forensic call cardinality differs")
    parsed_members: dict[str, object] = {"call-ledger.json": call_ledger_value}
    for relative, raw in frozen.candidate_members.items():
        if relative == "call-ledger.json":
            continue
        parsed_members[relative] = ARCHIVE_EVIDENCE.parse_resolution_archive_member(
            raw,
            path=relative,
            profile=profile,
            call_shape=(
                call_shape
                if relative in {"planner-session.json", "evaluator.json"}
                else None
            ),
        )
    sources = ARTIFACTS._load_current_resolution_sources(forensic_commit_sha)
    current_instrument = ARTIFACTS.assemble_resolution_instrument(
        sources=sources,
        isolation_policy_path=ARTIFACTS.ISOLATION_POLICY_PATH,
        evaluation_rubric_path=ARTIFACTS.EVALUATION_RUBRIC_PATH,
    )
    inputs = current_instrument.inputs
    authored_authority = parsed_members["authority.json"]
    current_authority = ARTIFACTS._resolution_authority_record(inputs)
    if (
        type(authored_authority) is not dict
        or {
            key: value
            for key, value in authored_authority.items()
            if key != "inputs_fingerprint"
        }
        != {
            key: value
            for key, value in current_authority.items()
            if key != "inputs_fingerprint"
        }
        or parsed_members["migration.json"]
        != ARTIFACTS._resolution_migration_record(inputs)
        or parsed_members["correspondence.json"]
        != ARTIFACTS._resolution_correspondence_record(inputs)
    ):
        raise ValueError("forensic carrier compatibility projection differs")
    authored_source = parsed_members["source.json"]
    current_source = ARTIFACTS._resolution_source_record(inputs)
    source_exclusions = {
        "reviewed_commit_sha",
        "carrier_compatibility_fingerprint",
    }
    if (
        type(authored_source) is not dict
        or {
            key: value
            for key, value in authored_source.items()
            if key not in source_exclusions
        }
        != {
            key: value
            for key, value in current_source.items()
            if key not in source_exclusions
        }
    ):
        raise ValueError("forensic historical source projection differs")
    contracts = historical.record["instrument_contracts"]
    calls_value = call_ledger_value.get("calls")
    if type(calls_value) is not list:
        raise ValueError("retained forensic call ledger is malformed")
    call_ledger = tuple(
        MappingProxyType(dict(row))
        for row in calls_value
        if type(row) is dict
    )
    if len(call_ledger) != len(calls_value):
        raise ValueError("retained forensic call row is malformed")
    candidate_bytes = frozen.candidate_members["candidate-recipe.json"]
    reconstructed = ARTIFACTS._reconstruct_resolution_attempt_from_verified_components(
        inputs=inputs,
        instrument_contracts=contracts,
        archive_resource_profile=profile,
        call_ledger=call_ledger,
        candidate_recipe_bytes=candidate_bytes,
    )
    ARTIFACTS._verify_resolution_call_ledger_from_verified_components(
        inputs=inputs,
        initial_request_bytes=historical.members["initial-request.json"],
        instrument_contracts=contracts,
        archive_resource_profile=profile,
        planner_session=reconstructed.planner_session,
        evaluator_result=reconstructed.evaluator_result,
        isolation_result=reconstructed.isolation_result,
        classification=reconstructed.classification,
        candidate_recipe_bytes=candidate_bytes,
        call_ledger=call_ledger,
        derived_stop_cause=reconstructed.derived_stop_cause,
    )
    if (
        reconstructed.checkpoint_gate is None
        or reconstructed.checkpoint_gate.status != "mechanically_accepted"
        or reconstructed.isolation_result is None
        or reconstructed.isolation_result.status != "isolation_rejected"
        or reconstructed.classification
        != "probe_resolution_isolation_failure"
        or reconstructed.evaluator_result is not None
    ):
        raise ValueError("retained forensic outcome reconstruction differs")
    expected_planner = ARTIFACTS._planner_session_record(
        reconstructed.planner_session, [dict(row) for row in call_ledger]
    )
    expected_gate = ARTIFACTS._gate_record(reconstructed.checkpoint_gate)
    expected_isolation = ARTIFACTS._isolation_record(
        reconstructed.isolation_result
    )
    expected_classification = ARTIFACTS._classification_record(
        classification=reconstructed.classification,
        derived_stop_cause=reconstructed.derived_stop_cause,
        candidate_recipe_bytes=candidate_bytes,
    )
    authored_pairs = (
        ("planner-session.json", expected_planner),
        ("checkpoint-gate.json", expected_gate),
        ("isolation.json", expected_isolation),
        ("classification.json", expected_classification),
    )
    for relative, expected in authored_pairs:
        if parsed_members[relative] != expected:
            raise ValueError(f"retained authored claim differs: {relative}")
    value = {
        "observed_commit_sha": OBSERVED_COMMIT_SHA,
        "forensic_commit_sha": forensic_commit_sha,
        "planner_call_count": shape["planner_count"],
        "evaluator_call_count": shape["evaluator_count"],
        "mechanical_status": "accepted",
        "isolation_status": reconstructed.isolation_result.status,
        "reconstructed_classification": reconstructed.classification,
        "candidate_recipe_raw_sha256": _sha256(candidate_bytes),
        "call_ledger_fingerprint": PLANNER_SUPPORT.fingerprint(
            call_ledger_value
        ),
        "gate_fingerprint": PLANNER_SUPPORT.fingerprint(expected_gate),
        "isolation_fingerprint": reconstructed.isolation_result.result_fingerprint,
    }
    value["reconstruction_fingerprint"] = PLANNER_SUPPORT.fingerprint(value)
    result = ResolutionForensicReconstruction(**value)
    staging_after, after_identity = _recursive_snapshot(frozen.staging_path)
    if (
        after_identity != frozen.before_identity
        or staging_after != staging_files
        or os.path.lexists(frozen.destination_path)
    ):
        raise ValueError("forensic source moved during reconstruction")
    _archive_after, preflight_after, preflight_after_identity = _flat_snapshot(
        historical.archive_dir, expected=_PREFLIGHT_MEMBERS
    )
    if (
        preflight_after_identity != historical.physical_identity
        or preflight_after != preflight_members
    ):
        raise ValueError("historical preflight moved during reconstruction")
    return result


__all__ = (
    "ForensicSourceSnapshot",
    "OBSERVED_ATTEMPT_FINGERPRINT",
    "OBSERVED_ATTEMPT_ID",
    "OBSERVED_CANDIDATE_CHECKSUMS_SHA256",
    "OBSERVED_COMMIT_SHA",
    "OBSERVED_DESTINATION",
    "OBSERVED_INSTRUMENT_FINGERPRINT",
    "OBSERVED_MARKER_SHA256",
    "OBSERVED_PREFLIGHT_ARCHIVE",
    "OBSERVED_PREFLIGHT_FINGERPRINT",
    "OBSERVED_STAGING",
    "ResolutionForensicReconstruction",
    "VerifiedHistoricalResolutionPreflightForensics",
    "VerifiedResolutionForensicSource",
    "load_verified_resolution_forensic_source",
    "reconstruct_resolution_forensic_candidate",
    "verify_historical_resolution_preflight_forensics",
)
