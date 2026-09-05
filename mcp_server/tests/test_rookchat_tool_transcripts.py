from __future__ import annotations

import json

import pytest

from rook.agent.chat.acp_presentation import (
    BoundedPromptProjection,
    PresentationQueue,
    ProjectedEvent,
    PromptGeneration,
)
from rook.agent.chat.acp_rook_results import parse_rook_envelope


def _event(ordinal: int, kind: str, text: str, message_id: str) -> ProjectedEvent:
    return ProjectedEvent(
        source_ordinal=ordinal,
        kind=kind,
        message_id=message_id,
        text=text,
        payload=None,
    )


@pytest.mark.asyncio
async def test_fake_acp_updates_preserve_message_order_and_structured_rook_result() -> None:
    projection = BoundedPromptProjection(
        generation=PromptGeneration(1, "session", "prompt"),
        queue=PresentationQueue(max_events=8, max_utf8_bytes=4096),
        user_text="make a box",
    )
    rook_result = json.dumps(
        {"success": True, "data": {"receipt": "receipt-1", "componentGuid": "component-1"}}
    )

    assert await projection.accept_source_update(0, _event(0, "agent_message_chunk", "Created ", "m-1"))
    assert await projection.accept_source_update(1, _event(1, "agent_message_chunk", "the box.", "m-1"))
    assert await projection.accept_source_update(2, _event(2, "tool_call_update", rook_result, "tool-1"))

    turn = projection.finalize("end_turn")
    parsed = parse_rook_envelope(rook_result)

    assert turn.assistant_text == "Created the box."
    assert [row.kind for row in projection.queue.snapshot()] == [
        "agent_message_chunk",
        "tool_call_update",
    ]
    assert len(turn.tool_cards) == 1
    assert parsed is not None
    assert parsed.success is True
    assert parsed.data == {"receipt": "receipt-1", "componentGuid": "component-1"}


@pytest.mark.asyncio
async def test_thought_updates_are_live_only_and_never_enter_turn_cache() -> None:
    projection = BoundedPromptProjection(
        generation=PromptGeneration(1, "session", "prompt"),
        queue=PresentationQueue(max_events=8, max_utf8_bytes=4096),
        user_text="inspect",
    )

    assert await projection.accept_source_update(0, _event(0, "agent_thought_chunk", "private thought", "t-1"))
    turn = projection.finalize("end_turn")

    assert projection.queue.snapshot()[0].text == "private thought"
    assert "private thought" not in json.dumps(turn.payload(1), sort_keys=True)


@pytest.mark.asyncio
async def test_cancelled_turn_keeps_partial_assistant_text_with_exact_outcome() -> None:
    projection = BoundedPromptProjection(
        generation=PromptGeneration(1, "session", "prompt"),
        queue=PresentationQueue(max_events=8, max_utf8_bytes=4096),
        user_text="start",
    )
    assert await projection.accept_source_update(0, _event(0, "agent_message_chunk", "partial", "m-1"))

    turn = projection.finalize("cancelled")

    assert turn.assistant_text == "partial"
    assert turn.stop_reason == "cancelled"


def test_rook_failure_envelope_is_not_promoted_by_transport_success() -> None:
    parsed = parse_rook_envelope('{"success":false,"data":"target_unavailable"}')

    assert parsed is not None
    assert parsed.success is False
    assert parsed.data == "target_unavailable"
