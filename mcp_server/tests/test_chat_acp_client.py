from __future__ import annotations

import asyncio
import json

import pytest
from acp import update_agent_message_text
from acp.schema import PermissionOption, SessionNotification, ToolCallStart

from rook.agent.chat.acp_client import RookChatAcpClient
from rook.agent.chat.acp_presentation import (
    BoundedPromptProjection,
    PresentationCache,
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


def _settings_update(value, sequence=1):
    from acp.schema import SessionNotification
    return SessionNotification.model_validate({"sessionId": "acp-session", "update": {
        "sessionUpdate": "session_info_update", "_meta": {"ai.primeintellect.prime-agent": {
            "effectiveSettings": value, "eventSequence": sequence, "promptTurnId": 0}}}}).update


@pytest.mark.asyncio
async def test_task7_idle_effective_settings_are_session_scoped():
    client = RookChatAcpClient()
    client.reset_for_session(launch_generation=3, acp_session_id="acp-session")
    expected = {"provider": "actual", "model": "clamped", "reasoning": "off"}
    await client.session_update("acp-session", _settings_update(expected))
    assert getattr(client, "effective_settings", None) == expected
    await client.session_update("wrong", _settings_update({**expected, "model": "wrong"}, 2))
    assert client.effective_settings == expected
    await client.session_update("acp-session", _settings_update({**expected, "model": "older"}, 1))
    assert client.effective_settings == expected
    client.reset_for_session(launch_generation=4, acp_session_id="replacement")
    assert client.effective_settings == dict.fromkeys(expected)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, {}, {"provider": 1}, {"model": "x" * 257}, {"model": "\ud800"}])
async def test_task7_unavailable_metadata_is_unknown(value):
    client = RookChatAcpClient()
    client.reset_for_session(launch_generation=3, acp_session_id="acp-session")
    await client.session_update("acp-session", _settings_update(value))
    assert getattr(client, "effective_settings", None) == {"provider": None, "model": None, "reasoning": None}


@pytest.mark.asyncio
async def test_task7_retired_initialization_cannot_revive_settings():
    client = RookChatAcpClient()
    client.begin_session(3)
    value = {"provider": "p", "model": "stale", "reasoning": "high"}
    await client.session_update("acp-session", _settings_update(value))
    client.retire_session_settings()
    client.complete_session("acp-session", {"ai.primeintellect.prime-agent": {"effectiveSettings": value}})
    await client.session_update("acp-session", _settings_update(value, 2))
    assert client.effective_settings == dict.fromkeys(value)


@pytest.mark.asyncio
async def test_task7_initialization_matches_returned_identity_and_bounds_pending_updates():
    client = RookChatAcpClient()
    value = {"provider": "p", "model": "latest", "reasoning": "high"}
    client.begin_session(3)
    await client.session_update("acp-session", _settings_update(value))
    await client.session_update("wrong", _settings_update({**value, "model": "wrong"}, 2))
    client.complete_session("acp-session", {})
    assert client.effective_settings == value
    client.begin_session(4)
    for index in range(40):
        await client.session_update("acp-session", _settings_update(value, index + 1))
    assert len(client._pending_settings) <= 32
    client.complete_session("acp-session", {})
    assert client.effective_settings == dict.fromkeys(value)
    await client.session_update("acp-session", _settings_update(value, 41))
    await client.session_update("acp-session", update_agent_message_text("unrelated idle text"))
    assert client.effective_settings == value


@pytest.mark.asyncio
async def test_task7_unknown_update_clears_report_without_resetting_prompt():
    client = RookChatAcpClient()
    generation = _generation()
    projection = _projection(generation)
    client.activate_prompt(generation, projection, asyncio.Event())
    await client.session_update("acp-session", _settings_update({"provider": "p", "model": "c", "reasoning": "low"}))
    await client.session_update("acp-session", _settings_update(None, 2))
    assert client.effective_settings == {"provider": None, "model": None, "reasoning": None}
    assert [row.source_ordinal for row in projection.queue.snapshot()] == [0, 1]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["session_info_update", "tool_call"])
@pytest.mark.parametrize("value", [
    pytest.param({"model": "\ud800"}, id="surrogate-value"),
    pytest.param({"\ud800": "invalid"}, id="surrogate-key"),
    pytest.param({"model": "x" * 257}, id="oversized"),
    pytest.param({"model": 42}, id="wrong-type"),
    pytest.param(None, id="unavailable"),
    pytest.param({"provider": "p", "model": "valid-\U0001f600", "reasoning": "off"}, id="valid"),
])
async def test_task7_active_settings_cannot_corrupt_delivery_or_history(tmp_path, kind, value):
    namespace = "ai.primeintellect.prime-agent"
    client = RookChatAcpClient()
    generation = _generation()
    projection = _projection(generation, callback_deadline=0.2)
    cancellation = asyncio.Event()
    client.activate_prompt(generation, projection, cancellation)
    metadata = {namespace: {"effectiveSettings": value, "eventSequence": 1, "promptTurnId": 0,
                            "quiescence": {"outstandingSubagents": 0}},
                "other.namespace": {"marker": "keep"}}
    update = {"sessionUpdate": kind, "_meta": metadata}
    if kind == "tool_call":
        update.update(toolCallId="metadata-tool", title="Metadata tool", status="completed")
    notification = SessionNotification.model_validate({"sessionId": "acp-session", "update": update})
    expected = value if isinstance(value, dict) and value.get("provider") == "p" else {
        "provider": None, "model": None, "reasoning": None}
    try:
        async with asyncio.timeout(2):
            await client.session_update(notification.session_id, notification.update)
            await client.session_update("acp-session", update_agent_message_text("healthy before"))
            await client.session_update("acp-session", ToolCallStart(
                session_update="tool_call", tool_call_id="healthy-tool", title="Healthy tool", status="completed"))
            await client.session_update("acp-session", update_agent_message_text(" healthy after"))
            projection.close_producer()
            delivered = []
            while (event := await projection.queue.get()) is not None:
                delivered.append(json.loads(event.panel_bytes()))
        assert client.effective_settings == expected
        assert delivered[0]["effectiveSettings"] == expected
        assert [event["sourceOrdinal"] for event in delivered] == [0, 1, 2, 3]
        assert [event["kind"] for event in delivered] == [kind, "agent_message_chunk", "tool_call", "agent_message_chunk"]
        retained_meta = delivered[0]["payload"]["_meta"]
        assert retained_meta == {**metadata, namespace: {
            key: item for key, item in metadata[namespace].items() if key != "effectiveSettings"}}
        assert notification.update.field_meta == metadata  # The SDK-owned source was not mutated.
        assert not projection.overflowed
        assert not projection.overflow_signal.is_set()
        assert not cancellation.is_set()
        turn = projection.finalize("end_turn")
        assert turn.stop_reason == "end_turn"
        assert turn.assistant_text == "healthy before healthy after"
        assert len(turn.tool_cards) == (2 if kind == "tool_call" else 1)
        cache = PresentationCache(tmp_path / "history")
        cache.publish(turn)
        history = cache.load()
        assert history.available
        assert history.turns[0]["assistantText"] == turn.assistant_text
        live_tools = [event for event in delivered if event["kind"].startswith("tool_")]
        for card, live in zip(history.turns[0]["toolCards"], live_tools, strict=True):
            stored = json.loads(card["content"])
            assert "effectiveSettings" not in stored
            assert stored == {key: item for key, item in live.items() if key != "effectiveSettings"}
            assert card["originalBytes"] == len(card["content"].encode("utf-8"))
            raw_meta = stored["payload"].get("_meta", {})
            assert "effectiveSettings" not in raw_meta.get(namespace, {})
        assert projection._tool_bytes == sum(card["originalBytes"] for card in turn.tool_cards)
    finally:
        client.clear_prompt(generation)
        projection.close_producer()


@pytest.mark.asyncio
@pytest.mark.parametrize("location", ["content", "unrelated-metadata"])
async def test_task7_settings_filter_does_not_swallow_unrelated_serialization_errors(location):
    client = RookChatAcpClient()
    generation = _generation()
    projection = _projection(generation)
    client.activate_prompt(generation, projection, asyncio.Event())
    update = {"sessionUpdate": "tool_call", "toolCallId": "t", "title": "Tool", "status": "completed"}
    if location == "content":
        update["title"] = "\ud800"
    else:
        update["_meta"] = {"unrelated": "\ud800"}
    notification = SessionNotification.model_validate({"sessionId": "acp-session", "update": update})
    try:
        with pytest.raises(UnicodeEncodeError):
            await client.session_update(notification.session_id, notification.update)
        assert projection.queue.snapshot() == ()
        assert projection._next_source_ordinal == 0
        assert projection.finalize("error").tool_cards == ()
    finally:
        client.clear_prompt(generation)
        projection.close_producer()
