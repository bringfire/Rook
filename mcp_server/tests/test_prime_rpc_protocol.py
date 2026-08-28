from __future__ import annotations

import pytest

from rook.agent.chat.prime_rpc_protocol import (
    PrimeProtocolError,
    parse_prompt_settlement,
    project_prime_event,
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
