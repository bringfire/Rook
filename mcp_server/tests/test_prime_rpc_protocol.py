from __future__ import annotations

import pytest

from rook.agent.chat.prime_rpc_protocol import (
    PrimeProtocolError,
    parse_ipython_runtime_preparation,
    parse_prompt_settlement,
    parse_rlm_max_depth_status,
    project_prime_event,
)


def test_recursion_status_accepts_only_the_closed_prime_shape() -> None:
    status = parse_rlm_max_depth_status(
        {
            "id": "depth-1",
            "type": "response",
            "command": "get_rlm_max_depth_status",
            "success": True,
            "data": {"maxDepth": 0, "source": "chat"},
        },
        expected_command="get_rlm_max_depth_status",
    )

    assert status.max_depth == 0
    assert status.source == "chat"


@pytest.mark.parametrize(
    "response",
    [
        {
            "id": "depth-1",
            "type": "response",
            "command": "get_rlm_max_depth_status",
            "success": True,
            "data": {"maxDepth": 0, "source": "chat", "extra": True},
        },
        {
            "id": "depth-1",
            "type": "response",
            "command": "set_rlm_max_depth",
            "success": True,
            "data": {"maxDepth": 0, "source": "chat"},
        },
        {
            "id": "depth-1",
            "type": "response",
            "command": "get_rlm_max_depth_status",
            "success": True,
            "data": {"maxDepth": -1, "source": "chat"},
        },
        {
            "id": "depth-1",
            "type": "response",
            "command": "get_rlm_max_depth_status",
            "success": True,
            "data": {"maxDepth": 0, "source": "other"},
        },
    ],
)
def test_recursion_status_rejects_open_wrong_or_invalid_shapes(response: dict) -> None:
    with pytest.raises(PrimeProtocolError):
        parse_rlm_max_depth_status(
            response,
            expected_command="get_rlm_max_depth_status",
        )


def test_runtime_preparation_accepts_only_absolute_closed_import_custody() -> None:
    prepared = parse_ipython_runtime_preparation(
        {
            "id": "prepare-1",
            "type": "response",
            "command": "prepare_ipython_runtime",
            "success": True,
            "data": {
                "interpreterPath": "C:/kernels/contract/Scripts/python.exe",
                "rookFullFile": "C:/product/rook-full/src/rook_full/__init__.py",
                "goalFile": "D:/prime/skills/goal/src/goal/__init__.py",
                "callables": {"search": True, "read": True, "call": True},
            },
        }
    )

    assert prepared.interpreter_path == "C:/kernels/contract/Scripts/python.exe"
    assert prepared.rook_full_file.endswith("rook_full/__init__.py")
    assert prepared.goal_file.endswith("goal/__init__.py")


@pytest.mark.parametrize(
    "change",
    [
        {"interpreterPath": "relative/python.exe"},
        {"rookFullFile": "relative/rook_full.py"},
        {"goalFile": "relative/goal.py"},
        {"callables": {"search": True, "read": True, "call": False}},
        {"extra": True},
    ],
)
def test_runtime_preparation_rejects_nonclosed_or_unqualified_shapes(
    change: dict,
) -> None:
    data = {
        "interpreterPath": "C:/kernels/contract/Scripts/python.exe",
        "rookFullFile": "C:/product/rook-full/src/rook_full/__init__.py",
        "goalFile": "D:/prime/skills/goal/src/goal/__init__.py",
        "callables": {"search": True, "read": True, "call": True},
    }
    data.update(change)
    with pytest.raises(PrimeProtocolError):
        parse_ipython_runtime_preparation(
            {
                "id": "prepare-1",
                "type": "response",
                "command": "prepare_ipython_runtime",
                "success": True,
                "data": data,
            }
        )


def test_prompt_settlement_accepts_only_closed_success_shape() -> None:
    settlement = parse_prompt_settlement(
        {
            "id": "turn-1",
            "type": "response",
            "command": "prompt_and_wait",
            "success": True,
            "data": {"outcome": "completed"},
        }
    )

    assert settlement.request_id == "turn-1"
    assert settlement.outcome == "completed"
    assert settlement.error_code is None
    assert settlement.error_message is None


@pytest.mark.parametrize(
    "code",
    [
        "admission_failed",
        "execution_failed",
        "inspection_failed",
        "settlement_unknown",
        "protocol_failed",
    ],
)
def test_prompt_settlement_preserves_closed_failure_codes(code: str) -> None:
    settlement = parse_prompt_settlement(
        {
            "id": "turn-1",
            "type": "response",
            "command": "prompt_and_wait",
            "success": False,
            "error": {"code": code, "message": "failed"},
        }
    )

    assert settlement.outcome is None
    assert settlement.error_code == code
    assert settlement.error_message == "failed"


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"id": "x", "type": "response", "command": "abort", "success": True},
        {
            "id": "x",
            "type": "response",
            "command": "prompt_and_wait",
            "success": True,
            "data": {"outcome": "unknown"},
        },
        {
            "id": "x",
            "type": "response",
            "command": "prompt_and_wait",
            "success": False,
            "error": {"code": "other", "message": "failed"},
        },
        {
            "id": "x",
            "type": "response",
            "command": "prompt_and_wait",
            "success": True,
            "data": {"outcome": "completed"},
            "extra": True,
        },
    ],
)
def test_prompt_settlement_rejects_malformed_or_open_shapes(response: dict) -> None:
    with pytest.raises(PrimeProtocolError):
        parse_prompt_settlement(response)


def test_project_prime_event_keeps_only_slice_two_vocabulary() -> None:
    text = project_prime_event(
        {
            "type": "message_update",
            "assistantMessageEvent": {"type": "text_delta", "delta": "hello"},
        }
    )
    model = project_prime_event(
        {
            "type": "model_change",
            "model": {"provider": "openai-codex", "id": "gpt-5.6-sol"},
            "thinkingLevel": "xhigh",
        }
    )
    segment = project_prime_event({"type": "agent_end", "messages": []})

    assert text == {"type": "text_delta", "content": "hello"}
    assert model == {
        "type": "model_update",
        "provider": "openai-codex",
        "model": "gpt-5.6-sol",
        "thinking": "xhigh",
    }
    assert segment == {"type": "status", "status": "segment_end"}
    assert project_prime_event({"type": "tool_execution_start"}) is None
    assert project_prime_event({"type": "message_update", "assistantMessageEvent": {"type": "thinking_delta"}}) is None
