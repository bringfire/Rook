from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
MCP_SRC = ROOT / "mcp_server" / "src"
for entry in (SCRIPTS, MCP_SRC):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import lm9b_p_governed_resolution_artifacts as ARTIFACTS


HISTORICAL_SOURCE = Path(
    r"C:\Users\bring\rook-lm9b-p-attempts\2026-07-22-visibility-intervention"
)
DERIVATIVE_ARCHIVE = Path(
    r"C:\Users\bring\rook-lm9b-p-attempts"
    r"\2026-07-22-evaluator-only-continuation"
    r"\derivatives\visibility-evaluator-01"
)
CARRIER_QUALIFICATION = Path(
    r"C:\Users\bring\rook-lm9b-p-attempts"
    r"\2026-07-23-typed-fact-carrier-post-merge"
    r"\d6330a61a21d56abf16af6ba3b8f1678ede2c3ec"
)


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _instrument():
    sources = ARTIFACTS.load_verified_resolution_sources(
        historical_source_dir=HISTORICAL_SOURCE,
        derivative_archive=DERIVATIVE_ARCHIVE,
        derivative_identity=ARTIFACTS.OFFICIAL_DERIVATIVE_IDENTITY,
        carrier_qualification_archive=CARRIER_QUALIFICATION,
        carrier_qualification_identity=(
            ARTIFACTS.HISTORICAL_CARRIER_QUALIFICATION_IDENTITY
        ),
        repo_root=ROOT,
        successor_envelope_path=ARTIFACTS.SUCCESSOR_ENVELOPE_PATH,
    )
    return ARTIFACTS.assemble_resolution_instrument(
        sources=sources,
        isolation_policy_path=ARTIFACTS.ISOLATION_POLICY_PATH,
        evaluation_rubric_path=ARTIFACTS.EVALUATION_RUBRIC_PATH,
    )


def test_task2_physical_loader_issues_one_closed_source_carrier() -> None:
    sources = ARTIFACTS.load_verified_resolution_sources(
        historical_source_dir=HISTORICAL_SOURCE,
        derivative_archive=DERIVATIVE_ARCHIVE,
        derivative_identity=ARTIFACTS.OFFICIAL_DERIVATIVE_IDENTITY,
        carrier_qualification_archive=CARRIER_QUALIFICATION,
        carrier_qualification_identity=(
            ARTIFACTS.HISTORICAL_CARRIER_QUALIFICATION_IDENTITY
        ),
        repo_root=ROOT,
        successor_envelope_path=ARTIFACTS.SUCCESSOR_ENVELOPE_PATH,
    )
    assert sources.reviewed_commit_sha == _head()
    assert set(sources.exact_contract_bytes) == {
        "forward_payload_schema",
        "semantic_value_registry",
    }
    assert sources.exact_successor_bytes == (
        ARTIFACTS.SUCCESSOR_ENVELOPE_PATH.read_bytes()
    )


def test_task2_instrument_assembles_only_from_verified_sources() -> None:
    sources = ARTIFACTS.load_verified_resolution_sources(
        historical_source_dir=HISTORICAL_SOURCE,
        derivative_archive=DERIVATIVE_ARCHIVE,
        derivative_identity=ARTIFACTS.OFFICIAL_DERIVATIVE_IDENTITY,
        carrier_qualification_archive=CARRIER_QUALIFICATION,
        carrier_qualification_identity=(
            ARTIFACTS.HISTORICAL_CARRIER_QUALIFICATION_IDENTITY
        ),
        repo_root=ROOT,
        successor_envelope_path=ARTIFACTS.SUCCESSOR_ENVELOPE_PATH,
    )
    instrument = ARTIFACTS.assemble_resolution_instrument(
        sources=sources,
        isolation_policy_path=ARTIFACTS.ISOLATION_POLICY_PATH,
        evaluation_rubric_path=ARTIFACTS.EVALUATION_RUBRIC_PATH,
    )
    assert instrument.inputs.reviewed_commit_sha == _head()
    assert instrument.contract_manifest["historical_qualification"][
        "identity"
    ] == ARTIFACTS.HISTORICAL_CARRIER_QUALIFICATION_IDENTITY
    assert set(instrument.contract_manifest) == {
        "schema",
        "historical_qualification",
        "carrier_forward_compatibility",
        "verified_inputs",
        "planner",
        "isolation",
        "evaluator",
        "decision",
        "readiness",
        "preflight",
        "archive",
        "launch_invocation",
        "ready_proof",
        "role_call_budgets",
        "reviewed_commit_sha",
        "task1_stage",
    }
    planner = instrument.contract_manifest["planner"]
    evaluator = instrument.contract_manifest["evaluator"]
    assert {
        "system_prompt_fingerprint",
        "tool_schema_fingerprint",
        "diagnostic_vocabulary_fingerprint",
        "temperature",
    } <= set(planner)
    assert {
        "system_prompt_fingerprint",
        "tool_schema_fingerprint",
        "temperature",
    } <= set(evaluator)
    assert instrument.contract_manifest["ready_proof"]["contract_fingerprint"]
    assert instrument.contract_manifest["launch_invocation"]["contract_fingerprint"]


@pytest.mark.parametrize(
    "attempt_id",
    ("", "Upper", "space value", "a/child", ".leading", "a" * 65),
)
def test_task2_attempt_binding_rejects_invalid_id(
    attempt_id: str, tmp_path: Path
) -> None:
    dispatches = {"planner": 0, "planner_evaluator": 0}
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ValueError, match="attempt ID"):
        ARTIFACTS.bind_resolution_attempt(
            instrument=_instrument(),
            attempt_id=attempt_id,
            resolution_root=root,
            destination=root / "result",
        )
    assert dispatches == {"planner": 0, "planner_evaluator": 0}


@pytest.mark.parametrize("case", ("outside_root", "destination_exists", "staging_exists"))
def test_task2_attempt_binding_refuses_unsafe_or_reused_destination(
    case: str, tmp_path: Path
) -> None:
    dispatches = {"planner": 0, "planner_evaluator": 0}
    root = tmp_path / "root"
    root.mkdir()
    destination = root / "result"
    attempt_id = "attempt-01"
    if case == "outside_root":
        destination = tmp_path / "outside"
    elif case == "destination_exists":
        destination.mkdir()
    else:
        (root / f".{attempt_id}.staging").mkdir()
    with pytest.raises((ValueError, FileExistsError)):
        ARTIFACTS.bind_resolution_attempt(
            instrument=_instrument(),
            attempt_id=attempt_id,
            resolution_root=root,
            destination=destination,
        )
    assert dispatches == {"planner": 0, "planner_evaluator": 0}


@pytest.mark.parametrize("case", ("reparse_point", "filesystem_mismatch"))
def test_task2_attempt_binding_refuses_ambiguous_filesystem(
    case: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dispatches = {"planner": 0, "planner_evaluator": 0}
    root = tmp_path / "root"
    root.mkdir()
    if case == "reparse_point":
        monkeypatch.setattr(
            ARTIFACTS,
            "_path_has_reparse_ambiguity",
            lambda _p: True,
            raising=False,
        )
    else:
        monkeypatch.setattr(
            ARTIFACTS,
            "_paths_share_filesystem",
            lambda _a, _b: False,
            raising=False,
        )
    with pytest.raises(ValueError, match="reparse|filesystem"):
        ARTIFACTS.bind_resolution_attempt(
            instrument=_instrument(),
            attempt_id="attempt-01",
            resolution_root=root,
            destination=root / "result",
        )
    assert dispatches == {"planner": 0, "planner_evaluator": 0}


def test_task2_attempt_binding_rejects_destination_equal_to_staging(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ValueError, match="staging.*destination|destination.*staging"):
        ARTIFACTS.bind_resolution_attempt(
            instrument=_instrument(),
            attempt_id="attempt-01",
            resolution_root=root,
            destination=root / ".attempt-01.staging",
        )


def test_task2_reservation_rejects_dangling_destination_alias_to_staging(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    instrument = _instrument()
    attempt = ARTIFACTS.bind_resolution_attempt(
        instrument=instrument,
        attempt_id="attempt-01",
        resolution_root=root,
        destination=root / "result",
    )
    preflight = ARTIFACTS.write_resolution_preflight(
        destination=tmp_path / "preflight",
        instrument=instrument,
        attempt_binding=attempt,
    )
    preflight.attempt.destination.symlink_to(
        preflight.attempt.staging_path,
        target_is_directory=True,
    )
    assert os.path.lexists(preflight.attempt.destination)
    assert preflight.attempt.destination.exists() is False
    with pytest.raises(ValueError, match="alias|reparse|destination"):
        ARTIFACTS.reserve_resolution_staging(preflight)
    assert preflight.attempt.staging_path.exists() is False


def test_task2_reservation_checks_created_staging_filesystem(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    instrument = _instrument()
    attempt = ARTIFACTS.bind_resolution_attempt(
        instrument=instrument,
        attempt_id="attempt-01",
        resolution_root=root,
        destination=root / "result",
    )
    preflight = ARTIFACTS.write_resolution_preflight(
        destination=tmp_path / "preflight",
        instrument=instrument,
        attempt_binding=attempt,
    )
    real_same_filesystem = ARTIFACTS._paths_share_filesystem
    observed_pairs: list[tuple[Path, Path]] = []

    def refuse_created_staging(left: Path, right: Path) -> bool:
        observed_pairs.append((left, right))
        if right == preflight.attempt.staging_path:
            return False
        return real_same_filesystem(left, right)

    monkeypatch.setattr(
        ARTIFACTS,
        "_paths_share_filesystem",
        refuse_created_staging,
    )
    with pytest.raises(ValueError, match="filesystem"):
        ARTIFACTS.reserve_resolution_staging(preflight)
    assert (
        preflight.attempt.resolution_root,
        preflight.attempt.staging_path,
    ) in observed_pairs
    assert preflight.attempt.staging_path.exists() is False


@pytest.mark.parametrize("mutation", ("derivative_path", "derivative_identity"))
def test_task2_physical_loader_pins_official_derivative_before_verification(
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    called = False

    def unexpected_verifier(*_args: object, **_kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("derivative verifier reached before production pin")

    monkeypatch.setattr(
        ARTIFACTS.CONT_ARTIFACTS,
        "verify_sealed_derivative_archive",
        unexpected_verifier,
    )
    derivative = DERIVATIVE_ARCHIVE
    identity = ARTIFACTS.OFFICIAL_DERIVATIVE_IDENTITY
    if mutation == "derivative_path":
        derivative = tmp_path / "replacement-derivative"
    else:
        identity = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="official derivative"):
        ARTIFACTS.load_verified_resolution_sources(
            historical_source_dir=HISTORICAL_SOURCE,
            derivative_archive=derivative,
            derivative_identity=identity,
            carrier_qualification_archive=CARRIER_QUALIFICATION,
            carrier_qualification_identity=(
                ARTIFACTS.HISTORICAL_CARRIER_QUALIFICATION_IDENTITY
            ),
            repo_root=ROOT,
            successor_envelope_path=ARTIFACTS.SUCCESSOR_ENVELOPE_PATH,
        )
    assert called is False


def test_task2_preflight_reconstructs_every_contract_and_refuses_future_proof(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    instrument = _instrument()
    attempt = ARTIFACTS.bind_resolution_attempt(
        instrument=instrument,
        attempt_id="attempt-01",
        resolution_root=root,
        destination=root / "result",
    )
    preflight = ARTIFACTS.write_resolution_preflight(
        destination=tmp_path / "preflight",
        instrument=instrument,
        attempt_binding=attempt,
    )
    assert preflight.record["instrument_contracts"] == dict(
        instrument.contract_manifest
    )
    assert preflight.record["instrument_contracts"]["role_call_budgets"] == {
        "planner": ARTIFACTS.PLANNER_SUPPORT.PLANNER_MAX_TURNS,
        "planner_evaluator": 1,
        "compiler": 0,
    }
    assert not {
        "proof_instance_identity",
        "checkpoint_identity",
        "eligible_recipe_identity",
    } & set(preflight.record["instrument_contracts"]["ready_proof"])

    record_path = preflight.archive_dir / "record.json"
    record = json.loads(record_path.read_bytes())
    record["instrument_contracts"]["ready_proof"]["checkpoint_identity"] = (
        "sha256:" + "0" * 64
    )
    record["instrument_fingerprint"] = ARTIFACTS.PLANNER_SUPPORT.fingerprint(
        record["instrument_contracts"]
    )
    record["preflight_fingerprint"] = ARTIFACTS.PLANNER_SUPPORT.fingerprint_without(
        record, "preflight_fingerprint"
    )
    record_path.write_bytes(ARTIFACTS._json_bytes(record))
    raw_members = {
        "record.json": record_path.read_bytes(),
        "initial-request.json": (
            preflight.archive_dir / "initial-request.json"
        ).read_bytes(),
    }
    (preflight.archive_dir / "checksums.json").write_bytes(
        ARTIFACTS._json_bytes(
            ARTIFACTS._checksums(
                "rook.lm9b_p.governed_resolution_preflight_checksums:v1",
                raw_members,
            )
        )
    )
    with pytest.raises(ValueError, match="reconstructed instrument"):
        ARTIFACTS.verify_resolution_preflight(
            preflight.archive_dir,
            expected_fingerprint=record["preflight_fingerprint"],
        )


def test_task4_instrument_binds_call_ledger_and_outcome_contracts() -> None:
    instrument = _instrument()
    decision = instrument.contract_manifest["decision"]

    assert decision["outcome_equations_contract_id"] == (
        "lm9b_p.governed_resolution_outcome_equations:v1"
    )
    assert decision["call_ledger_contract_id"] == (
        "lm9b_p.governed_resolution_call_ledger:v1"
    )
    assert decision["call_ledger_verifier_source_fingerprint"] == (
        ARTIFACTS._callable_source_fingerprint(
            ARTIFACTS.verify_resolution_call_ledger
        )
    )


def test_task2_invocation_binding_is_closed_and_fingerprint_bound() -> None:
    value = ARTIFACTS.build_resolution_invocation_binding(
        supplied_preflight_fingerprint="sha256:" + "1" * 64,
        transmit=True,
        reviewed_commit_sha="a" * 40,
        readiness_identity="sha256:" + "2" * 64,
        attempt_id="attempt-01",
        attempt_fingerprint="sha256:" + "3" * 64,
    )
    assert set(value) == {
        "schema",
        "supplied_preflight_fingerprint",
        "transmit",
        "reviewed_commit_sha",
        "readiness_identity",
        "attempt_id",
        "attempt_fingerprint",
        "invocation_fingerprint",
    }
    changed = dict(value)
    changed["transmit"] = False
    with pytest.raises(ValueError, match="invocation"):
        ARTIFACTS.verify_resolution_invocation_binding(changed, expected=value)
