"""Versioned Prime compaction-lifecycle admission tests."""

from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.util
from pathlib import Path

import pytest

from rook import gh_behavioral_acceptance as acceptance_v1


V1_SHA256 = "8A68408AD6216A7DEF638EAC962B28CA7A32735312DCD00C57D038EAD8DEBAF5"
GOAL_ID = "27896eb1-b067-4135-9d91-43895f7bc09f"
OBJECTIVE = "Build the retained Vessel massing."


def _acceptance_v2():
    spec = importlib.util.find_spec("rook.gh_behavioral_acceptance_v2")
    assert spec is not None, "versioned compaction admission owner is missing"
    return importlib.import_module("rook.gh_behavioral_acceptance_v2")


def _goal_context(continuations_used: int, *, goal_id: str = GOAL_ID) -> dict:
    return {
        "role": "custom",
        "customType": "goal_context",
        "content": "<goal_context>\nretained objective\n</goal_context>",
        "display": True,
        "details": {
            "kind": "continuation",
            "goalId": goal_id,
            "objective": OBJECTIVE,
            "status": "active",
            "continuationsUsed": continuations_used,
        },
    }


def _agent_end(continuations_used: int, *, goal_id: str = GOAL_ID) -> dict:
    return {
        "type": "agent_end",
        "messages": [_goal_context(continuations_used, goal_id=goal_id)],
    }


def _ipython_state() -> dict:
    return {
        "role": "custom",
        "customType": "ipython_state",
        "content": "<ipython_state>\nretained kernel state\n</ipython_state>",
        "display": False,
        "timestamp": 1787232996890,
    }


def _compaction_end(*, will_retry: bool = False) -> dict:
    return {
        "type": "compaction_end",
        "reason": "threshold",
        "result": {
            "summary": "retained summary",
            "firstKeptEntryId": "7429c411",
            "tokensBefore": 112121,
            "details": {"readFiles": [], "modifiedFiles": []},
        },
        "aborted": False,
        "willRetry": will_retry,
    }


def _action(phase: str | None = None) -> dict:
    actions: dict = {"queuedCount": 0, "steering": [], "followUps": []}
    if phase is not None:
        actions["active"] = {
            "kind": "turn",
            "phase": phase,
            "label": "<goal_context>continue</goal_context>",
        }
    return {"type": "session_action_update", "actions": actions}


def _compacted_runtime() -> list[dict]:
    state = _ipython_state()
    return [
        {"type": "session", "id": "same-session"},
        {"type": "agent_start"},
        {"type": "message"},
        _agent_end(0),
        {"type": "compaction_start", "reason": "threshold"},
        {"type": "message_start", "message": state},
        {"type": "message_end", "message": state},
        _compaction_end(),
        _action("preparing"),
        _action("committing"),
        {"type": "agent_start"},
        _action("running"),
        {"type": "message"},
        _agent_end(1),
        _action(),
    ]


def _write_prime_fixture(tmp_path: Path, runtime_rows: list[dict]) -> tuple[Path, Path]:
    source = tmp_path / "source.jsonl"
    runtime = tmp_path / "prime.jsonl"
    source.write_bytes(
        acceptance_v1.canonical_json_bytes(
            {
                "schema": "rook.gh_authoring_source_log:v1",
                "row_emitter": "prime_rook_adapter",
            }
        )
    )
    runtime.write_bytes(
        b"".join(acceptance_v1.canonical_json_bytes(row) for row in runtime_rows)
    )
    return source, runtime


def _terminal_process_state() -> dict:
    return {
        "terminated": True,
        "stdout_eof": True,
        "owned_child_pids": [],
        "exit_code": 0,
    }


def test_v2_accepts_same_goal_compaction_continuation_and_normalizes_trace(tmp_path):
    acceptance_v2 = _acceptance_v2()
    source, runtime = _write_prime_fixture(tmp_path, _compacted_runtime())

    with pytest.raises(ValueError, match="invalid_prime_terminal_marker"):
        acceptance_v1.seal_prime_source_log(
            source, runtime, _terminal_process_state()
        )

    closure = acceptance_v2.seal_prime_source_log(
        source, runtime, _terminal_process_state()
    )
    trace = acceptance_v2.normalize_authoring_trace(source, runtime)

    assert closure["terminal_marker"] == "agent_end"
    assert trace["events"] == []
    assert trace["source_closure"] == closure


def test_v2_preserves_v1_single_segment_admission(tmp_path):
    acceptance_v2 = _acceptance_v2()
    source, runtime = _write_prime_fixture(tmp_path, [{"type": "agent_end"}])

    closure = acceptance_v2.seal_prime_source_log(
        source, runtime, _terminal_process_state()
    )

    assert closure["terminal_marker"] == "agent_end"


@pytest.mark.parametrize(
    "case",
    [
        "orphan_agent_end",
        "missing_compaction_start",
        "orphan_compaction",
        "failed_compaction",
        "retrying_compaction",
        "changed_goal",
        "changed_objective",
        "multiple_sessions",
        "post_terminal_message",
        "post_terminal_tool_activity",
    ],
)
def test_v2_refuses_unlinked_or_nonterminal_actor_segments(tmp_path, case):
    acceptance_v2 = _acceptance_v2()
    rows = _compacted_runtime()
    if case == "orphan_agent_end":
        rows.insert(-1, _agent_end(1))
    elif case == "missing_compaction_start":
        rows.pop(4)
    elif case == "orphan_compaction":
        rows.insert(2, {"type": "compaction_start", "reason": "threshold"})
    elif case == "failed_compaction":
        rows[7]["result"] = None
        rows[7]["errorMessage"] = "compaction failed"
        rows[7]["errorSeverity"] = "error"
    elif case == "retrying_compaction":
        rows[7] = _compaction_end(will_retry=True)
    elif case == "changed_goal":
        rows[13] = _agent_end(1, goal_id="replacement-goal")
    elif case == "changed_objective":
        rows[13] = copy.deepcopy(rows[13])
        rows[13]["messages"][0]["details"]["objective"] = "Different objective"
    elif case == "multiple_sessions":
        rows.insert(1, {"type": "session", "id": "replacement-session"})
    elif case == "post_terminal_message":
        rows.append({"type": "message"})
    elif case == "post_terminal_tool_activity":
        rows.append({"type": "tool_execution_start", "toolName": "ipython"})
    source, runtime = _write_prime_fixture(tmp_path, rows)

    with pytest.raises(ValueError, match="invalid_prime_terminal_marker"):
        acceptance_v2.seal_prime_source_log(
            source, runtime, _terminal_process_state()
        )
    assert b'"type":"closure"' not in source.read_bytes()


def test_v1_owner_bytes_remain_frozen():
    assert (
        hashlib.sha256(Path(acceptance_v1.__file__).read_bytes()).hexdigest().upper()
        == V1_SHA256
    )


def _viewport_event() -> dict:
    return {
        "sequence": 0,
        "ingress": "canonical_gateway",
        "target": "rhino_viewport",
        "arguments": {
            "width": 900,
            "height": 1100,
            "view": "Perspective",
            "displayMode": "Arctic",
            "zoomExtents": True,
        },
        "result": {
            "success": True,
            "data": {
                "displayMode": "Arctic",
                "filePath": "C:/Temp/viewport.png",
                "format": "png",
                "height": 1100,
                "message": "Image saved to file.",
                "savedToFile": True,
                "viewName": "Perspective",
                "width": 900,
            },
        },
        "exception": None,
        "dispatch": {"status": "dispatched", "target_call_count": 1},
        "mutation": {
            "classification": "unknown",
            "commit_status": "unknown",
            "commit_evidence": None,
            "solve_readiness_receipt": None,
        },
    }


def test_v2_projects_exact_successful_viewport_capture_as_gh_observation():
    acceptance_v2 = _acceptance_v2()

    event = acceptance_v2._normalize_v2_event(_viewport_event())

    assert event["mutation"] == {
        "classification": "observational",
        "commit_status": "none",
        "commit_evidence": None,
        "solve_readiness_receipt": None,
    }


@pytest.mark.parametrize("change", ["not_saved", "open_result", "failed_result"])
def test_v2_keeps_unproven_viewport_capture_shapes_unknown(change):
    acceptance_v2 = _acceptance_v2()
    event = _viewport_event()
    if change == "not_saved":
        event["result"]["data"]["savedToFile"] = False
    elif change == "open_result":
        event["result"]["data"]["extra"] = "unexpected"
    elif change == "failed_result":
        event["result"]["success"] = False

    normalized = acceptance_v2._normalize_v2_event(event)

    assert normalized["mutation"]["classification"] == "unknown"
    assert normalized["mutation"]["commit_status"] == "unknown"
