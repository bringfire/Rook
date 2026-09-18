from __future__ import annotations

import asyncio

import pytest
from acp import update_agent_message_text
from acp.schema import PermissionOption, ToolCallStart

from rook.agent.chat.acp_client import RookChatAcpClient
from rook.agent.chat.acp_presentation import (
    BoundedPromptProjection,
    PresentationQueue,
    PromptGeneration,
)


def _generation(prompt_id: str = "prompt-1") -> PromptGeneration:
    return PromptGeneration(launch_generation=3, acp_session_id="acp-session", prompt_id=prompt_id)


def _projection(generation: PromptGeneration, *, callback_deadline: float = 1.0):
    return BoundedPromptProjection(
        generation=generation,
        queue=PresentationQueue(),
        user_text="hello",
        callback_deadline_seconds=callback_deadline,
    )


@pytest.mark.asyncio
async def test_permission_prefers_allow_once_then_allow_always():
    client = RookChatAcpClient()
    generation = _generation()
    cancellation = asyncio.Event()
    client.activate_prompt(generation, _projection(generation), cancellation)
    tool = ToolCallStart(session_update="tool_call", tool_call_id="tool-1", title="test", status="pending")
    options = [
        PermissionOption(option_id="always", name="Always", kind="allow_always"),
        PermissionOption(option_id="once", name="Once", kind="allow_once"),
    ]

    response = await client.request_permission("acp-session", tool, options)

    assert response.model_dump(by_alias=True, exclude_none=True)["outcome"] == {
        "outcome": "selected",
        "optionId": "once",
    }
    assert not cancellation.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "options",
    [
        [PermissionOption(option_id="", name="Empty", kind="allow_once")],
        [
            PermissionOption(option_id="same", name="One", kind="allow_once"),
            PermissionOption(option_id="same", name="Two", kind="allow_always"),
        ],
        [PermissionOption(option_id="reject", name="Reject", kind="reject_once")],
    ],
)
async def test_invalid_or_nonallow_permission_options_cancel_absorbingly(options):
    client = RookChatAcpClient()
    generation = _generation()
    cancellation = asyncio.Event()
    client.activate_prompt(generation, _projection(generation), cancellation)
    tool = ToolCallStart(session_update="tool_call", tool_call_id="tool-1", title="test", status="pending")

    first = await client.request_permission("acp-session", tool, options)
    second = await client.request_permission(
        "acp-session",
        tool,
        [PermissionOption(option_id="later", name="Later", kind="allow_once")],
    )

    assert first.model_dump()["outcome"] == {"outcome": "cancelled"}
    assert second.model_dump()["outcome"] == {"outcome": "cancelled"}
    assert cancellation.is_set()


@pytest.mark.asyncio
async def test_callbacks_are_fenced_by_prompt_and_session_generation():
    client = RookChatAcpClient()
    first = _generation("first")
    first_projection = _projection(first)
    client.activate_prompt(first, first_projection, asyncio.Event())
    client.clear_prompt(first)
    second = _generation("second")
    second_projection = _projection(second)
    client.activate_prompt(second, second_projection, asyncio.Event())

    await client.session_update("wrong-session", update_agent_message_text("stale"))
    client.clear_prompt(first)
    await client.session_update("acp-session", update_agent_message_text("current"))

    assert [row.text for row in second_projection.queue.snapshot()] == ["current"]


@pytest.mark.asyncio
async def test_concurrent_callbacks_preserve_source_assignment_order():
    client = RookChatAcpClient()
    generation = _generation()
    projection = _projection(generation)
    client.activate_prompt(generation, projection, asyncio.Event())

    tasks = [
        asyncio.create_task(client.session_update("acp-session", update_agent_message_text(str(index))))
        for index in range(64)
    ]
    await asyncio.gather(*tasks)

    rows = projection.queue.snapshot()
    assert [row.source_ordinal for row in rows] == list(range(64))
    assert "".join(row.text or "" for row in rows) == "".join(str(index) for index in range(64))


def test_new_session_resets_optional_prime_metadata_to_unknown():
    client = RookChatAcpClient()
    client.observe_prime_meta({"goal": {"status": "active"}, "compaction": {"count": 2}})
    assert client.prime_meta.goal == {"status": "active"}
    client.reset_for_session(launch_generation=4, acp_session_id="replacement")
    assert client.prime_meta.goal is None
    assert client.prime_meta.compaction is None


def test_unknown_prime_metadata_is_bounded_and_redacted():
    client = RookChatAcpClient()
    client.observe_prime_meta({"api_token": "secret", **{f"key-{i}": i for i in range(40)}})
    payload = client.prime_meta.unknown.encoded_payload
    assert len(payload) <= 8 * 1024
    assert b"secret" not in payload
