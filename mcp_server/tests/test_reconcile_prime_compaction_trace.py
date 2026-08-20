"""Offline reconciliation tests for versioned Prime compaction admission."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from rook import gh_behavioral_acceptance as acceptance_v1


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "reconcile_prime_compaction_trace.py"
)


def _script():
    spec = importlib.util.spec_from_file_location(
        "reconcile_prime_compaction_trace_for_tests", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(acceptance_v1.canonical_json_bytes(value))


def _write_manifest(root: Path, path: Path) -> dict:
    entries = {}
    for candidate in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = candidate.relative_to(root).as_posix()
        if relative in {"evidence-manifest.json", "manifest-verification.json"}:
            continue
        entries[relative] = {"bytes": candidate.stat().st_size, "sha256": _sha(candidate)}
    manifest = {
        "schema": "rook.evidence_manifest:v1",
        "root": root.as_posix(),
        "entryCount": len(entries),
        "entries": entries,
    }
    _write_json(path, manifest)
    return manifest


def _receipt() -> dict:
    return {
        "schema": "rook.gh_solve_readiness_receipt:v1",
        "receipt_id": "receipt-final",
        "document_session_id": "document-session",
        "mutation_epoch": 4,
        "solution_run_epoch": 8,
        "completed_solution_run_epoch": 8,
        "status": "ready",
        "reason": None,
        "completion_signal": "solution_end",
        "issued_at": "2026-08-20T12:00:00.0000000Z",
        "completed_at": "2026-08-20T12:00:01.0000000Z",
    }


def _write_source(path: Path) -> None:
    path.write_bytes(
        acceptance_v1.canonical_json_bytes(
            {
                "schema": "rook.gh_authoring_source_log:v1",
                "row_emitter": "prime_rook_adapter",
            }
        )
    )
    receipt = _receipt()
    acceptance_v1.append_canonical_gateway_source_event(
        path,
        "gh_edit",
        {"epoch": 3, "set_values": [{"id": "C1", "value": 8}]},
        result={
            "success": True,
            "data": {
                "edit_summary": {
                    "created": 0,
                    "deleted": 0,
                    "values_set": 1,
                    "connected": 0,
                    "disconnected": 0,
                },
                "solve_readiness_receipt": receipt,
            },
        },
    )
    acceptance_v1.append_canonical_gateway_source_event(
        path,
        "gh_snapshot",
        {"readiness_receipt_id": receipt["receipt_id"]},
        result={
            "success": True,
            "data": {
                "components": [{"id": "C1"}],
                "flows": [],
                "diagnostics": {"errors": 0, "warnings": 0},
                "readiness_fence": {
                    "readiness_receipt_id": receipt["receipt_id"],
                    "document_session_id": receipt["document_session_id"],
                    "mutation_epoch": receipt["mutation_epoch"],
                    "solution_run_epoch": receipt["solution_run_epoch"],
                    "completed_solution_run_epoch": receipt[
                        "completed_solution_run_epoch"
                    ],
                },
            },
        },
    )


def _goal_context(continuations_used: int) -> dict:
    return {
        "role": "custom",
        "customType": "goal_context",
        "content": "<goal_context>fixture</goal_context>",
        "display": True,
        "details": {
            "kind": "continuation",
            "goalId": "goal-one",
            "objective": "Fixture objective",
            "status": "active",
            "continuationsUsed": continuations_used,
        },
    }


def _write_runtime(path: Path) -> None:
    state = {
        "role": "custom",
        "customType": "ipython_state",
        "content": "<ipython_state>\nfixture\n</ipython_state>",
        "display": False,
        "timestamp": 1,
    }
    rows = [
        {"type": "session", "id": "session-one"},
        {"type": "agent_start"},
        {"type": "message_update", "assistantMessageEvent": {"partial": "a"}},
        {"type": "agent_end", "messages": [_goal_context(0)]},
        {"type": "compaction_start", "reason": "threshold"},
        {"type": "message_start", "message": state},
        {"type": "message_end", "message": state},
        {
            "type": "compaction_end",
            "reason": "threshold",
            "result": {
                "summary": "fixture",
                "firstKeptEntryId": "entry-one",
                "tokensBefore": 10,
                "details": {"readFiles": [], "modifiedFiles": []},
            },
            "aborted": False,
            "willRetry": False,
        },
        {
            "type": "session_action_update",
            "actions": {
                "queuedCount": 0,
                "steering": [],
                "followUps": [],
                "active": {"kind": "turn", "phase": "preparing", "label": "continue"},
            },
        },
        {
            "type": "session_action_update",
            "actions": {
                "queuedCount": 0,
                "steering": [],
                "followUps": [],
                "active": {"kind": "turn", "phase": "committing", "label": "continue"},
            },
        },
        {"type": "agent_start"},
        {"type": "agent_end", "messages": [_goal_context(1)]},
        {
            "type": "session_action_update",
            "actions": {"queuedCount": 0, "steering": [], "followUps": []},
        },
    ]
    path.write_bytes(b"".join(acceptance_v1.canonical_json_bytes(row) for row in rows))


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    script = _script()
    source_root = tmp_path / "sealed"
    row_root = source_root / "MV1"
    operator = row_root / "operator"
    operator.mkdir(parents=True)
    source = operator / "source.jsonl"
    runtime = operator / "prime.jsonl"
    process = operator / "process-result.json"
    historical = operator / "hidden-evaluation.json"
    _write_source(source)
    _write_runtime(runtime)
    _write_json(process, {"exitCode": 0, "stdoutEof": True, "ownedChildPids": []})
    _write_json(historical, {"status": "incomplete", "reason": "invalid_prime_terminal_marker"})
    row_manifest_path = row_root / "evidence-manifest.json"
    _write_manifest(row_root, row_manifest_path)
    global_manifest_path = source_root / "evidence-manifest.json"
    _write_manifest(source_root, global_manifest_path)

    output_root = tmp_path / "reconciled"
    v2_path = Path(script.acceptance_v2.__file__).resolve()
    protocol = {
        "schema": "rook.experiment.prime_compaction_trace_reconciliation:v1",
        "mode": "offline_only",
        "outputRoot": output_root.as_posix(),
        "sourceEvidence": {
            "root": source_root.as_posix(),
            "globalManifest": {
                "path": global_manifest_path.as_posix(),
                "sha256": _sha(global_manifest_path),
            },
            "rowRoot": row_root.as_posix(),
            "rowManifest": {
                "path": row_manifest_path.as_posix(),
                "sha256": _sha(row_manifest_path),
            },
            "sourceLog": {"path": source.as_posix(), "sha256": _sha(source)},
            "runtimeLog": {"path": runtime.as_posix(), "sha256": _sha(runtime)},
            "processResult": {"path": process.as_posix(), "sha256": _sha(process)},
            "historicalEvaluation": {"path": historical.as_posix(), "sha256": _sha(historical)},
        },
        "owners": {
            "v1": {
                "path": Path(acceptance_v1.__file__).resolve().as_posix(),
                "sha256": _sha(Path(acceptance_v1.__file__).resolve()),
            },
            "v2": {"path": v2_path.as_posix(), "sha256": _sha(v2_path)},
        },
        "runner": {"path": SCRIPT_PATH.as_posix(), "sha256": _sha(SCRIPT_PATH)},
    }
    protocol_path = tmp_path / "protocol.json"
    _write_json(protocol_path, protocol)
    return protocol_path, output_root


def test_offline_reconciliation_seals_compacted_trace_and_selects_fenced_receipt(tmp_path):
    script = _script()
    protocol_path, output_root = _fixture(tmp_path)

    result = script.run_reconciliation(protocol_path)

    assert result["status"] == "unproven"
    assert result["reason"] == "independent_judgment_required"
    assert result["traceAdmission"] == "pass"
    assert result["latestReceiptId"] == "receipt-final"
    assert result["finalObservation"]["sourceSequence"] == 1
    assert (output_root / "authoring-trace-v2.json").is_file()
    assert script.verify_evidence_manifest(
        output_root, output_root / "evidence-manifest.json"
    )["mismatches"] == []


def test_runtime_efficiency_attribution_is_byte_accounted(tmp_path):
    script = _script()
    runtime = tmp_path / "prime.jsonl"
    duplicate = acceptance_v1.canonical_json_bytes(
        {"type": "message_update", "assistantMessageEvent": {"partial": "abc"}}
    )
    image = acceptance_v1.canonical_json_bytes(
        {
            "type": "message_end",
            "message": {
                "content": [
                    {"type": "image", "data": "AAAA", "mimeType": "image/png"}
                ]
            },
        }
    )
    runtime.write_bytes(duplicate + duplicate + image)

    analysis = script.analyze_prime_runtime(runtime)

    assert analysis["totalRows"] == 3
    assert analysis["totalBytes"] == runtime.stat().st_size
    assert analysis["rowsByType"]["message_update"]["rows"] == 2
    assert analysis["messageUpdateSubtypes"] == {
        "unknown": {"rows": 2, "bytes": len(duplicate) * 2}
    }
    assert analysis["messageUpdateDeltaBytes"] == 0
    assert analysis["messageUpdatesWithPartial"] == 2
    assert analysis["exactDuplicateRows"] == 1
    assert analysis["imageBearingRows"] == 1


def test_source_manifest_drift_refuses_before_output_creation(tmp_path):
    script = _script()
    protocol_path, output_root = _fixture(tmp_path)
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    Path(protocol["sourceEvidence"]["sourceLog"]["path"]).write_bytes(b"changed\n")

    try:
        script.run_reconciliation(protocol_path)
    except ValueError as exc:
        assert str(exc) == "source_evidence_mismatch"
    else:
        raise AssertionError("tampered source evidence was admitted")
    assert not output_root.exists()
