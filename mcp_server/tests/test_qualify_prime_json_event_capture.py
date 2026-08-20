"""Offline qualification tests for compact Prime JSON event capture."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
from typing import Any

import pytest

from rook import gh_behavioral_acceptance as acceptance_v1
from rook import gh_behavioral_acceptance_v2 as acceptance_v2


ROOT = Path(__file__).resolve().parents[2]
QUALIFICATION_PATH = ROOT / "scripts" / "qualify_prime_json_event_capture.py"
CAPTURE_PATH = ROOT / "scripts" / "prime_json_event_capture.py"
RUNNER_PATH = ROOT / "scripts" / "qwen38_self_termination_campaign_runner.py"
SPEC_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-20-prime-json-event-stream-storage-efficiency-design.md"
)
FROZEN_PROTOCOL_V1_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-20-prime-json-event-capture-offline-qualification-v1.json"
)
FROZEN_PROTOCOL_V2_PATH = FROZEN_PROTOCOL_V1_PATH.with_name(
    "2026-08-20-prime-json-event-capture-offline-qualification-v2.json"
)
FROZEN_PROTOCOL_V3_PATH = FROZEN_PROTOCOL_V1_PATH.with_name(
    "2026-08-20-prime-json-event-capture-offline-qualification-v3.json"
)


@pytest.fixture
def qualification():
    spec = importlib.util.spec_from_file_location(
        "qualify_prime_json_event_capture_for_tests", QUALIFICATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def line(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def write_manifest(root: Path, path: Path) -> None:
    entries = {}
    for item in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        if item == path:
            continue
        entries[item.relative_to(root).as_posix()] = {
            "bytes": item.stat().st_size,
            "sha256": sha256(item),
        }
    path.write_bytes(
        line(
            {
                "schema": "rook.evidence_manifest:v1",
                "root": root.as_posix(),
                "entryCount": len(entries),
                "entries": entries,
            }
        )
    )


def capture_config() -> dict[str, Any]:
    return {
        "schema": "rook.prime_event_capture_config:v1",
        "mode": "compact",
        "retainedPath": "operator/prime-events.compact.jsonl",
        "custodyPath": "operator/prime-event-capture-custody.json",
        "rawDebugPath": None,
    }


def assistant_message(content: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": copy.deepcopy(content),
        "api": "openai-completions",
        "provider": "ollama",
        "model": "qwen3.8:27b",
        "usage": {"input": 10, "output": 2, "totalTokens": 12},
        "stopReason": "toolUse",
        "timestamp": 1,
    }


def update(
    subtype: str,
    content_index: int,
    payload: dict[str, Any],
    message: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "message_update",
        "message": copy.deepcopy(message),
        "assistantMessageEvent": {
            "type": subtype,
            "contentIndex": content_index,
            **copy.deepcopy(payload),
            "partial": copy.deepcopy(message),
        },
    }


def rich_runtime_rows() -> list[dict[str, Any]]:
    text_empty = {"type": "text", "text": ""}
    text_a = {"type": "text", "text": "A"}
    thinking_empty = {"type": "thinking", "thinking": ""}
    thinking_b = {"type": "thinking", "thinking": "B"}
    tool_streaming = {
        "type": "toolCall",
        "id": "call-1",
        "name": "ipython",
        "arguments": {},
        "partialArgs": '{"code":',
        "streamIndex": 0,
    }
    tool_final = {
        "type": "toolCall",
        "id": "call-1",
        "name": "ipython",
        "arguments": {"code": "print(1)"},
    }
    empty = assistant_message([])
    text_started = assistant_message([text_empty])
    text_complete = assistant_message([text_a])
    thinking_started = assistant_message([text_a, thinking_empty])
    thinking_complete = assistant_message([text_a, thinking_b])
    tool_started = assistant_message([text_a, thinking_b, tool_streaming])
    final = assistant_message([text_a, thinking_b, tool_final])
    return [
        {"type": "session", "id": "session-1"},
        {"type": "goal_update", "goal": {"status": "active"}},
        {"type": "agent_start"},
        {"type": "message_start", "message": empty},
        update("text_start", 0, {}, text_started),
        update("text_delta", 0, {"delta": "A"}, text_complete),
        update("thinking_start", 1, {}, thinking_started),
        update("thinking_delta", 1, {"delta": "B"}, thinking_complete),
        update("toolcall_start", 2, {}, tool_started),
        update("toolcall_delta", 2, {"delta": '{"code":'}, tool_started),
        update("toolcall_end", 2, {"toolCall": tool_final}, final),
        update("text_end", 0, {"content": "A"}, final),
        update("thinking_end", 1, {"content": "B"}, final),
        {"type": "message_end", "message": final},
        {
            "type": "tool_execution_start",
            "toolCallId": "call-1",
            "toolName": "ipython",
        },
        {
            "type": "message_start",
            "message": {
                "role": "toolResult",
                "toolCallId": "call-1",
                "toolName": "ipython",
                "content": [
                    {"type": "text", "text": "ok"},
                    {
                        "type": "image",
                        "mimeType": "image/png",
                        "data": "aW1hZ2U=",
                    },
                ],
            },
        },
        {"type": "tool_execution_end", "toolCallId": "call-1"},
        {"type": "tool_execution_error", "toolCallId": "recovered"},
        {
            "type": "message_start",
            "message": {
                "role": "custom",
                "customType": "ipython_state",
                "content": "<ipython_state>state</ipython_state>",
                "display": False,
                "timestamp": 2,
            },
        },
        {
            "type": "message_end",
            "message": {
                "role": "custom",
                "customType": "ipython_state",
                "content": "<ipython_state>state</ipython_state>",
                "display": False,
                "timestamp": 2,
            },
        },
        {"type": "agent_end"},
    ]


def make_protocol(tmp_path: Path) -> Path:
    source_root = tmp_path / "source"
    row_root = source_root / "MV1"
    operator = row_root / "operator"
    operator.mkdir(parents=True)
    runtime = operator / "prime.jsonl"
    runtime.write_bytes(b"".join(line(row) for row in rich_runtime_rows()))
    source_log = operator / "source.jsonl"
    source_log.write_bytes(
        line(
            {
                "schema": "rook.gh_authoring_source_log:v1",
                "row_emitter": "prime_rook_adapter",
            }
        )
    )
    process = operator / "process-result.json"
    process.write_bytes(line({"exitCode": 0, "stdoutEof": True}))
    row_manifest = row_root / "evidence-manifest.json"
    write_manifest(row_root, row_manifest)
    global_manifest = source_root / "evidence-manifest.json"
    write_manifest(source_root, global_manifest)

    def reference(path: Path) -> dict[str, Any]:
        return {"path": path.as_posix(), "sha256": sha256(path)}

    protocol = {
        "schema": "rook.experiment.prime_json_event_capture_offline_qualification:v1",
        "mode": "offline_only",
        "outputRoot": (tmp_path / "output").as_posix(),
        "captureConfig": capture_config(),
        "sourceEvidence": {
            "root": source_root.as_posix(),
            "rowRoot": row_root.as_posix(),
            "globalManifest": reference(global_manifest),
            "rowManifest": reference(row_manifest),
            "runtimeLog": {
                **reference(runtime),
                "bytes": runtime.stat().st_size,
                "rows": len(rich_runtime_rows()),
            },
            "sourceLog": reference(source_log),
            "processResult": reference(process),
        },
        "owners": {
            "captureModule": reference(CAPTURE_PATH),
            "campaignRunner": reference(RUNNER_PATH),
            "v2": reference(Path(acceptance_v2.__file__).resolve()),
            "spec": reference(SPEC_PATH),
        },
        "precontactVerification": {
            "pythonPath": Path(sys.executable).as_posix(),
            "arguments": ["-c", "print('offline preflight')"],
        },
        "expected": {
            "sourceRows": len(rich_runtime_rows()),
            "sourceBytes": runtime.stat().st_size,
            "sourceSha256": sha256(runtime),
            "compactedMessageUpdates": 9,
            "rawFallbackMessageUpdates": 0,
            "maxRetainedRatio": 1.0,
            "liveContact": False,
        },
    }
    path = tmp_path / "protocol.json"
    path.write_bytes(line(protocol))
    return path


def test_protocol_is_closed_and_offline_only(qualification, tmp_path: Path):
    path = make_protocol(tmp_path)
    protocol = qualification.validate_qualification_protocol(
        json.loads(path.read_text())
    )
    assert protocol["mode"] == "offline_only"
    assert protocol["expected"]["liveContact"] is False

    for changed in (
        json.loads(path.read_text()) | {"extra": True},
        json.loads(path.read_text()) | {"mode": "live"},
        json.loads(path.read_text()) | {"outputRoot": "relative"},
    ):
        with pytest.raises(ValueError, match="qualification_protocol_invalid"):
            qualification.validate_qualification_protocol(changed)


@pytest.mark.parametrize(
    "reference",
    [
        ("sourceEvidence", "globalManifest"),
        ("sourceEvidence", "rowManifest"),
        ("sourceEvidence", "runtimeLog"),
        ("sourceEvidence", "sourceLog"),
        ("sourceEvidence", "processResult"),
        ("owners", "captureModule"),
        ("owners", "campaignRunner"),
        ("owners", "v2"),
        ("owners", "spec"),
    ],
)
def test_source_mismatch_refuses_before_output(
    qualification, tmp_path: Path, reference
):
    path = make_protocol(tmp_path)
    protocol = json.loads(path.read_text())
    protocol[reference[0]][reference[1]]["sha256"] = "0" * 64
    path.write_bytes(line(protocol))

    with pytest.raises(ValueError, match="source_evidence_mismatch"):
        qualification.run_qualification(path)
    assert not Path(protocol["outputRoot"]).exists()


def test_small_fixture_dual_replay_is_deterministic_and_offline(
    qualification, tmp_path: Path
):
    path = make_protocol(tmp_path)
    result = qualification.run_qualification(path)
    output = Path(json.loads(path.read_text())["outputRoot"])

    assert result["status"] == "qualified"
    assert result["liveContact"] is False
    assert result["determinism"] == "pass"
    assert result["terminalReconstruction"] == "pass"
    assert result["passthroughParity"] == "pass"
    assert result["rowParity"] == {
        "status": "pass",
        "sourceRows": len(rich_runtime_rows()),
        "retainedRows": len(rich_runtime_rows()),
        "compactedMessageUpdates": 9,
        "rawFallbackMessageUpdates": 0,
        "passthroughRows": len(rich_runtime_rows()) - 9,
        "firstMismatch": None,
    }
    custody_path = output / "replay-a" / "operator" / (
        "prime-event-capture-custody.json"
    )
    assert result["custodyBytes"] == custody_path.stat().st_size
    assert result["persistedBytes"] == (
        result["retained"]["bytes"] + custody_path.stat().st_size
    )
    assert result["retainedRatio"] == (
        result["persistedBytes"] / result["source"]["bytes"]
    )
    assert result["v2Parity"]["status"] == "pass"
    assert not list(output.rglob("prime.jsonl"))
    assert (output / "replay-a" / "operator" / "prime-events.compact.jsonl").is_file()
    assert qualification.verify_evidence_manifest(
        output, output / "evidence-manifest.json"
    )["mismatches"] == []


def test_independent_row_oracle_rejects_faulty_compact_delta(
    qualification, tmp_path: Path
):
    protocol_path = make_protocol(tmp_path)
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    replay = tmp_path / "oracle-replay"
    qualification._run_replay(protocol, replay)
    retained = replay / "operator" / "prime-events.compact.jsonl"
    rows = retained.read_bytes().splitlines(keepends=True)
    for index, raw in enumerate(rows):
        value = json.loads(raw)
        event = value.get("assistantMessageEvent")
        if value.get("type") == "assistant_stream_delta" and (
            type(event) is dict and event.get("type") == "text_delta"
        ):
            event["delta"] = "wrong"
            rows[index] = line(value)
            break
    else:
        pytest.fail("fixture did not contain a compact text delta")
    retained.write_bytes(b"".join(rows))

    parity = qualification._independent_row_parity(
        Path(protocol["sourceEvidence"]["runtimeLog"]["path"]), retained
    )

    assert parity["status"] == "fail"
    assert parity["firstMismatch"] == {
        "row": 6,
        "reason": "compact_projection_mismatch",
    }


def test_output_root_is_never_reused(qualification, tmp_path: Path):
    path = make_protocol(tmp_path)
    protocol = json.loads(path.read_text())
    Path(protocol["outputRoot"]).mkdir()
    with pytest.raises(ValueError, match="output_root_exists"):
        qualification.run_qualification(path)


def test_qualification_source_has_no_live_system_dependencies():
    source = QUALIFICATION_PATH.read_text(encoding="utf-8")
    for forbidden in ("ollama", "rhino", "grasshopper", "rook.server", "httpx", "requests"):
        assert forbidden not in source.lower()
    assert "subprocess.run" in source
    assert "transform_prime_row" not in source
    assert math.isfinite(1.0)


def test_frozen_protocol_binds_exact_offline_qualification_inputs(qualification):
    protocol = json.loads(FROZEN_PROTOCOL_V1_PATH.read_text(encoding="utf-8"))
    assert qualification.validate_qualification_protocol(protocol) == protocol
    assert protocol["mode"] == "offline_only"
    assert protocol["outputRoot"] == (
        "C:/UDEV/RookEvidence/"
        "2026-08-20-prime-json-event-capture-offline-qualification-v1"
    )
    assert protocol["captureConfig"] == capture_config()
    assert protocol["sourceEvidence"] == {
        "root": (
            "C:/UDEV/RookEvidence/"
            "2026-08-20-qwen38-multimodal-vessel-massing-v5"
        ),
        "rowRoot": (
            "C:/UDEV/RookEvidence/"
            "2026-08-20-qwen38-multimodal-vessel-massing-v5/MV1"
        ),
        "globalManifest": {
            "path": (
                "C:/UDEV/RookEvidence/"
                "2026-08-20-qwen38-multimodal-vessel-massing-v5/"
                "evidence-manifest.json"
            ),
            "sha256": (
                "7BDD42FE284CDCF34AE101CE5550E9A1B"
                "5B7742A90F0437B5735C3FB5F67259D"
            ),
        },
        "rowManifest": {
            "path": (
                "C:/UDEV/RookEvidence/"
                "2026-08-20-qwen38-multimodal-vessel-massing-v5/MV1/"
                "evidence-manifest.json"
            ),
            "sha256": (
                "FCD5205D361C1772ADB8C266CB33A949"
                "0F4679697CE28DE3B7D75636065B13A4"
            ),
        },
        "runtimeLog": {
            "path": (
                "C:/UDEV/RookEvidence/"
                "2026-08-20-qwen38-multimodal-vessel-massing-v5/MV1/"
                "operator/prime.jsonl"
            ),
            "sha256": (
                "F79FF8A329993C9770B7E103B3F10620"
                "A6E118C5AD58E6184E9777EDFBFCAA3B"
            ),
            "bytes": 3_543_087_572,
            "rows": 74_473,
        },
        "sourceLog": {
            "path": (
                "C:/UDEV/RookEvidence/"
                "2026-08-20-qwen38-multimodal-vessel-massing-v5/MV1/"
                "operator/source.jsonl"
            ),
            "sha256": (
                "E86FDB1F88B1357F8811F3FC8F3DDBEC"
                "078C4949B873615E0CE1D98A98B966C8"
            ),
        },
        "processResult": {
            "path": (
                "C:/UDEV/RookEvidence/"
                "2026-08-20-qwen38-multimodal-vessel-massing-v5/MV1/"
                "operator/process-result.json"
            ),
            "sha256": (
                "4920BA546D4FFF73C1C8DDEB8887E5C1"
                "CABA3762A5775C75C516683D54342F70"
            ),
        },
    }
    assert protocol["owners"] == {
        "captureModule": {
            "path": CAPTURE_PATH.as_posix(),
            "sha256": (
                "BBB03F9DF0C4A0CA85F6D0FFCBDDE3E3"
                "F9BC61BB18D92EF6F4BF39675AD08C6E"
            ),
        },
        "campaignRunner": {
            "path": RUNNER_PATH.as_posix(),
            "sha256": (
                "CB0F4076A6812ABF6C8356DB874F1A04"
                "E90B37EA029B1C9E5262780E5C9A221F"
            ),
        },
        "v2": {
            "path": Path(acceptance_v2.__file__).resolve().as_posix(),
            "sha256": (
                "55211B778B44C96729A21D9DAE430B28"
                "83F4636520C030E1EBFD3B8F896508FF"
            ),
        },
        "spec": {
            "path": SPEC_PATH.as_posix(),
            "sha256": (
                "E5FAAE11FDCB40C184F0478E611D77F7"
                "77B2C8E552B99A6736555592BC0FDC63"
            ),
        },
    }
    assert protocol["precontactVerification"] == {
        "pythonPath": "C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe",
        "arguments": [
            "-m",
            "pytest",
            "mcp_server/tests/test_prime_json_event_capture.py",
            "mcp_server/tests/test_qwen38_self_termination_campaign_runner.py",
            "mcp_server/tests/test_qualify_prime_json_event_capture.py",
            "mcp_server/tests/test_gh_behavioral_acceptance_v2.py",
            "mcp_server/tests/test_reconcile_prime_compaction_trace.py",
            "-q",
        ],
    }
    assert protocol["expected"] == {
        "sourceRows": 74_473,
        "sourceBytes": 3_543_087_572,
        "sourceSha256": (
            "F79FF8A329993C9770B7E103B3F10620"
            "A6E118C5AD58E6184E9777EDFBFCAA3B"
        ),
        "compactedMessageUpdates": 74_143,
        "rawFallbackMessageUpdates": 0,
        "maxRetainedRatio": 0.05,
        "liveContact": False,
    }


def test_v2_protocol_changes_only_capture_owner_and_evidence_root(qualification):
    assert sha256(FROZEN_PROTOCOL_V1_PATH) == (
        "8082BA9D7133423FC2AC803097D373CC"
        "B10E7883FA120519926231AF375126BF"
    )
    v1 = json.loads(FROZEN_PROTOCOL_V1_PATH.read_text(encoding="utf-8"))
    v2 = json.loads(FROZEN_PROTOCOL_V2_PATH.read_text(encoding="utf-8"))
    expected = copy.deepcopy(v1)
    expected["outputRoot"] = (
        "C:/UDEV/RookEvidence/"
        "2026-08-20-prime-json-event-capture-offline-qualification-v2"
    )
    expected["owners"]["captureModule"]["sha256"] = (
        "2B9E86BD544092E74D34C19AC9F33183"
        "A1CA56A2D97E574973DEAB8E7D4EFAFF"
    )

    assert v2 == expected
    assert qualification.validate_qualification_protocol(v2) == v2


def test_v3_protocol_preserves_v2_and_changes_only_reviewed_capture_owner(
    qualification,
):
    assert sha256(FROZEN_PROTOCOL_V2_PATH) == (
        "76B30EF754A383FC4327A9C18F5FCCB0"
        "E74823BAD6F02050AB857799F0842E14"
    )
    v2 = json.loads(FROZEN_PROTOCOL_V2_PATH.read_text(encoding="utf-8"))
    v3 = json.loads(FROZEN_PROTOCOL_V3_PATH.read_text(encoding="utf-8"))
    expected = copy.deepcopy(v2)
    expected["outputRoot"] = (
        "C:/UDEV/RookEvidence/"
        "2026-08-20-prime-json-event-capture-offline-qualification-v3"
    )
    expected["owners"]["captureModule"]["sha256"] = (
        "6D5537386F391578650B276A4A25FC224"
        "F7ECBE14B7767BE5AB886B780439F94"
    )

    assert v3 == expected
    assert qualification.validate_qualification_protocol(v3) == v3
