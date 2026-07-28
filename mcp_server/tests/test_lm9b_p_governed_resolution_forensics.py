from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from dataclasses import fields
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
FORENSICS_PATH = SCRIPTS / "lm9b_p_governed_resolution_forensics.py"


def _load_forensics():
    if not FORENSICS_PATH.is_file():
        pytest.fail("governed-resolution forensics module is not implemented")
    name = "lm9b_p_governed_resolution_forensics"
    spec = importlib.util.spec_from_file_location(name, FORENSICS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_task4_forensic_types_import_without_operational_dependencies() -> None:
    """Catches read-only forensics importing execution or issuing active types."""

    module = _load_forensics()
    source = FORENSICS_PATH.read_text(encoding="utf-8")
    imported = {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not {
        "lm9b_p_governed_resolution_probe",
        "lm9b_p_planner_recipe_transfer_probe",
        "lm9b_c_compiler_sufficiency_probe",
    } & imported
    assert [field.name for field in fields(module.ResolutionForensicReconstruction)] == [
        "observed_commit_sha",
        "forensic_commit_sha",
        "planner_call_count",
        "evaluator_call_count",
        "mechanical_status",
        "isolation_status",
        "reconstructed_classification",
        "candidate_recipe_raw_sha256",
        "call_ledger_fingerprint",
        "gate_fingerprint",
        "isolation_fingerprint",
        "reconstruction_fingerprint",
    ]
    assert [field.name for field in fields(module.ForensicSourceSnapshot)] == [
        "staging_path",
        "destination_path",
        "preflight_members",
        "marker_bytes",
        "candidate_members",
        "before_identity",
    ]
    with pytest.raises(TypeError, match="closure-issued"):
        module.VerifiedHistoricalResolutionPreflightForensics()
    with pytest.raises(TypeError, match="closure-issued"):
        module.VerifiedResolutionForensicSource()


def test_task4_verifies_only_the_pinned_physical_historical_preflight(
    tmp_path: Path,
) -> None:
    """Catches a checkpoint authorizing a relocated or self-authored preflight."""

    module = _load_forensics()
    carrier = module.verify_historical_resolution_preflight_forensics(
        repo_root=ROOT,
        preflight_archive=module.OBSERVED_PREFLIGHT_ARCHIVE,
        expected_preflight_fingerprint=module.OBSERVED_PREFLIGHT_FINGERPRINT,
    )
    assert type(carrier) is module.VerifiedHistoricalResolutionPreflightForensics

    copied = tmp_path / "copied-preflight"
    shutil.copytree(module.OBSERVED_PREFLIGHT_ARCHIVE, copied)
    with pytest.raises(ValueError, match="pin differs"):
        module.verify_historical_resolution_preflight_forensics(
            repo_root=ROOT,
            preflight_archive=copied,
            expected_preflight_fingerprint=module.OBSERVED_PREFLIGHT_FINGERPRINT,
        )
    with pytest.raises(ValueError, match="pin differs"):
        module.verify_historical_resolution_preflight_forensics(
            repo_root=ROOT,
            preflight_archive=module.OBSERVED_PREFLIGHT_ARCHIVE,
            expected_preflight_fingerprint="sha256:" + "0" * 64,
        )


def _historical_carrier(module):
    return module.verify_historical_resolution_preflight_forensics(
        repo_root=ROOT,
        preflight_archive=module.OBSERVED_PREFLIGHT_ARCHIVE,
        expected_preflight_fingerprint=module.OBSERVED_PREFLIGHT_FINGERPRINT,
    )


def test_task4_historical_reconstruction_rejects_fully_reclosed_source_drift() -> None:
    """Catches authored downstream hashes replacing the pinned Git authority."""

    module = _load_forensics()
    _archive, members, _identity = module._flat_snapshot(
        module.OBSERVED_PREFLIGHT_ARCHIVE,
        expected=module._PREFLIGHT_MEMBERS,
    )
    git_blobs, _manifest = module._git_blob_map(ROOT)
    changed_blobs = dict(git_blobs)
    target = "scripts/lm9b_p_governed_resolution_support.py"
    changed_blobs[target] = changed_blobs[target].replace(
        b"    payload = {\n", b"    payload  = {\n", 1
    )
    record = json.loads(members["record.json"])
    source = module._source_bytes(
        changed_blobs[target], "render_planner_revision_request"
    )
    record["instrument_contracts"]["planner"][
        "revision_renderer_source_fingerprint"
    ] = "sha256:" + hashlib.sha256(source).hexdigest()
    record["instrument_fingerprint"] = module.PLANNER_SUPPORT.fingerprint(
        record["instrument_contracts"]
    )
    record["attempt"]["attempt_fingerprint"] = module.PLANNER_SUPPORT.fingerprint(
        {
            "instrument_fingerprint": record["instrument_fingerprint"],
            "attempt_id": record["attempt"]["attempt_id"],
            "canonical_destination": record["attempt"]["canonical_destination"],
        }
    )
    record["preflight_fingerprint"] = module.PLANNER_SUPPORT.fingerprint_without(
        record, "preflight_fingerprint"
    )
    changed_members = dict(members)
    changed_members["record.json"] = module._canonical_bytes(record)
    checksums = json.loads(changed_members["checksums.json"])
    checksums["members"] = [
        {
            "path": name,
            "raw_sha256": "sha256:"
            + hashlib.sha256(changed_members[name]).hexdigest(),
        }
        for name in ("initial-request.json", "record.json")
    ]
    changed_members["checksums.json"] = module._canonical_bytes(checksums)
    with pytest.raises(ValueError, match="historical (preflight|instrument)"):
        module._verify_historical_preflight_projection(
            archive=module.OBSERVED_PREFLIGHT_ARCHIVE,
            members=changed_members,
            git_blobs=changed_blobs,
        )


def test_task4_loads_a_closed_read_only_copy_of_retained_staging(
    tmp_path: Path,
) -> None:
    """Catches checksum-only acceptance or source mutation during custody."""

    module = _load_forensics()
    historical = _historical_carrier(module)
    copied = tmp_path / module.OBSERVED_STAGING.name
    shutil.copytree(module.OBSERVED_STAGING, copied)
    before = module._recursive_snapshot(copied)
    source = module.load_verified_resolution_forensic_source(
        historical_preflight=historical,
        staging_dir=copied,
        expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
        expected_candidate_checksums_sha256=(
            module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
        ),
    )
    assert type(source) is module.VerifiedResolutionForensicSource
    assert module._recursive_snapshot(copied) == before

    (copied / "unexpected").mkdir()
    with pytest.raises(ValueError, match="membership"):
        module.load_verified_resolution_forensic_source(
            historical_preflight=historical,
            staging_dir=copied,
            expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
            expected_candidate_checksums_sha256=(
                module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
            ),
        )


def test_task4_reconstructs_the_six_turn_candidate_without_writes(
    tmp_path: Path,
) -> None:
    """Catches trusting authored outcome files instead of model root evidence."""

    module = _load_forensics()
    historical = _historical_carrier(module)
    copied = tmp_path / module.OBSERVED_STAGING.name
    shutil.copytree(module.OBSERVED_STAGING, copied)
    source = module.load_verified_resolution_forensic_source(
        historical_preflight=historical,
        staging_dir=copied,
        expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
        expected_candidate_checksums_sha256=(
            module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
        ),
    )
    before = module._recursive_snapshot(copied)
    commit = module._current_commit(ROOT)
    result = module.reconstruct_resolution_forensic_candidate(
        source=source,
        repo_root=ROOT,
        forensic_commit_sha=commit,
    )
    assert result.planner_call_count == 6
    assert result.evaluator_call_count == 0
    assert result.mechanical_status == "accepted"
    assert result.isolation_status == "isolation_rejected"
    assert (
        result.reconstructed_classification
        == "probe_resolution_isolation_failure"
    )
    assert module._recursive_snapshot(copied) == before


def test_task4_forensic_capabilities_are_unforgeable_and_inert(
    tmp_path: Path,
) -> None:
    """Catches forensic evidence becoming an execution or ready-proof carrier."""

    module = _load_forensics()
    historical = _historical_carrier(module)
    copied = tmp_path / module.OBSERVED_STAGING.name
    shutil.copytree(module.OBSERVED_STAGING, copied)
    source = module.load_verified_resolution_forensic_source(
        historical_preflight=historical,
        staging_dir=copied,
        expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
        expected_candidate_checksums_sha256=(
            module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
        ),
    )
    forged_historical = object.__new__(
        module.VerifiedHistoricalResolutionPreflightForensics
    )
    forged_source = object.__new__(module.VerifiedResolutionForensicSource)
    with pytest.raises(ValueError, match="was not issued"):
        module.load_verified_resolution_forensic_source(
            historical_preflight=forged_historical,
            staging_dir=copied,
            expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
            expected_candidate_checksums_sha256=(
                module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
            ),
        )
    with pytest.raises(ValueError, match="was not issued"):
        module.reconstruct_resolution_forensic_candidate(
            source=forged_source,
            repo_root=ROOT,
            forensic_commit_sha=module._current_commit(ROOT),
        )

    for carrier in (historical, source):
        with pytest.raises(TypeError, match="verified resolution preflight"):
            module.ARTIFACTS.reserve_resolution_staging(carrier)
        with pytest.raises(TypeError, match="sealed resolution checkpoint"):
            module.ARTIFACTS.issue_resolution_ready_proof(
                carrier,
                preflight_archive=module.OBSERVED_PREFLIGHT_ARCHIVE,
                expected_preflight_fingerprint=module.OBSERVED_PREFLIGHT_FINGERPRINT,
            )
        with pytest.raises(TypeError, match="wrong type"):
            module.ARTIFACTS.consume_resolution_ready_proof(
                carrier,
                preflight_archive=module.OBSERVED_PREFLIGHT_ARCHIVE,
                expected_preflight_fingerprint=module.OBSERVED_PREFLIGHT_FINGERPRINT,
            )
        with pytest.raises(TypeError, match="verified resolution preflight"):
            module.ARTIFACTS.seal_resolution_checkpoint(
                preflight=carrier,
                invocation_binding={},
                readiness_record={},
                readiness_verified_at="",
                planner_session=None,
                evaluator_result=None,
                isolation_result=None,
                checkpoint_gate=None,
                candidate_recipe_bytes=None,
                call_ledger=(),
                derived_stop_cause="mechanically_rejected",
                classification="probe_mechanically_rejected",
            )

    assert not any(
        name.startswith("_issue_")
        for name, value in vars(module).items()
        if callable(value)
    )


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("marker", "marker fingerprint"),
        ("candidate_checksum", "retained bytes differ"),
        ("missing_marker", "marker is absent"),
        ("missing_candidate", "retained bytes differ"),
        ("missing_runtime", "retained bytes differ"),
        ("extra_file", "file membership"),
    ],
)
def test_task4_forensic_source_mutations_refuse_before_issuance(
    tmp_path: Path,
    mutation: str,
    match: str,
) -> None:
    """Catches a nearby checksum or directory being mistaken for root custody."""

    module = _load_forensics()
    historical = _historical_carrier(module)
    copied = tmp_path / module.OBSERVED_STAGING.name
    shutil.copytree(module.OBSERVED_STAGING, copied)
    if mutation == "marker":
        (copied / "post_dispatch_unsealed.json").write_bytes(b"{}")
    elif mutation == "candidate_checksum":
        (copied / ".archive-candidate" / "checksums.json").write_bytes(b"{}")
    elif mutation == "missing_marker":
        (copied / "post_dispatch_unsealed.json").unlink()
    elif mutation == "missing_candidate":
        (copied / ".archive-candidate" / "source.json").unlink()
    elif mutation == "missing_runtime":
        (copied / ".resolution-runtime" / "readiness.json").unlink()
    else:
        (copied / "unexpected.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match=match):
        module.load_verified_resolution_forensic_source(
            historical_preflight=historical,
            staging_dir=copied,
            expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
            expected_candidate_checksums_sha256=(
                module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
            ),
        )


def test_task4_forensic_source_rejects_destination_presence_and_reparse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches following aliases or loading evidence after publication appeared."""

    module = _load_forensics()
    historical = _historical_carrier(module)
    copied = tmp_path / module.OBSERVED_STAGING.name
    shutil.copytree(module.OBSERVED_STAGING, copied)
    destination = tmp_path / "destination"
    destination.mkdir()
    monkeypatch.setattr(module, "OBSERVED_DESTINATION", destination)
    with pytest.raises(ValueError, match="destination is present"):
        module.load_verified_resolution_forensic_source(
            historical_preflight=historical,
            staging_dir=copied,
            expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
            expected_candidate_checksums_sha256=(
                module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
            ),
        )
    monkeypatch.setattr(
        module,
        "OBSERVED_DESTINATION",
        module.OBSERVED_RESOLUTION_ROOT / module.OBSERVED_ATTEMPT_ID,
    )
    alias = copied / "alias"
    try:
        os.symlink(copied / ".archive-candidate", alias, target_is_directory=True)
    except OSError:
        pytest.skip("Windows symlink creation is unavailable")
    with pytest.raises(ValueError, match="reparse entry"):
        module.load_verified_resolution_forensic_source(
            historical_preflight=historical,
            staging_dir=copied,
            expected_marker_sha256=module.OBSERVED_MARKER_SHA256,
            expected_candidate_checksums_sha256=(
                module.OBSERVED_CANDIDATE_CHECKSUMS_SHA256
            ),
        )
