from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from rook.agent.chat.acp_presentation import (
    BoundedPromptProjection,
    PresentationCache,
    PresentationQueue,
    ProjectedEvent,
    PromptGeneration,
    TurnProjection,
    map_stop_reason,
    project_unknown_meta,
)


def _event(
    ordinal: int,
    kind: str,
    text: str,
    *,
    message_id: str | None = None,
) -> ProjectedEvent:
    return ProjectedEvent(
        source_ordinal=ordinal,
        kind=kind,
        message_id=message_id,
        text=text,
        payload=None,
    )


def test_stop_reason_mapping_is_closed() -> None:
    assert map_stop_reason("end_turn") == "settled"
    assert map_stop_reason("cancelled") == "cancelled"
    assert map_stop_reason("max_tokens") == "incomplete"
    assert map_stop_reason("max_turn_requests") == "incomplete"
    assert map_stop_reason("refusal") == "refused"
    assert map_stop_reason("unknown") == "error"


@pytest.mark.asyncio
async def test_projection_orders_concurrent_callbacks_and_coalesces_only_message_chunks() -> None:
    queue = PresentationQueue(max_events=8, max_utf8_bytes=4096)
    projection = BoundedPromptProjection(
        generation=PromptGeneration(3, "acp-1", "prompt-9"),
        queue=queue,
        user_text="hello",
        callback_deadline_seconds=0.5,
    )

    later = asyncio.create_task(
        projection.accept_source_update(1, _event(1, "agent_message_chunk", "B", message_id="m"))
    )
    await asyncio.sleep(0)
    earlier = asyncio.create_task(
        projection.accept_source_update(0, _event(0, "agent_message_chunk", "A", message_id="m"))
    )
    assert await earlier is True
    assert await later is True

    await projection.accept_source_update(2, _event(2, "tool_call", "started", message_id="tool"))
    await projection.accept_source_update(3, _event(3, "tool_call", "completed", message_id="tool"))
    rows = queue.snapshot()
    assert [(row.kind, row.text) for row in rows] == [
        ("agent_message_chunk", "AB"),
        ("tool_call", "started"),
        ("tool_call", "completed"),
    ]


@pytest.mark.asyncio
async def test_whole_callback_deadline_signals_absorbing_overflow_without_unbounded_wait() -> None:
    queue = PresentationQueue(max_events=1, max_utf8_bytes=128)
    projection = BoundedPromptProjection(
        generation=PromptGeneration(1, "acp", "prompt"),
        queue=queue,
        user_text="",
        callback_deadline_seconds=0.02,
    )
    assert await projection.accept_source_update(0, _event(0, "tool_call", "first")) is True

    assert await projection.accept_source_update(1, _event(1, "tool_call", "second")) is False
    assert projection.overflowed is True
    assert await projection.accept_source_update(2, _event(2, "tool_call", "third")) is False


@pytest.mark.asyncio
async def test_closed_or_wrong_generation_callbacks_publish_nothing() -> None:
    queue = PresentationQueue(max_events=8, max_utf8_bytes=4096)
    generation = PromptGeneration(1, "acp", "prompt")
    projection = BoundedPromptProjection(generation=generation, queue=queue, user_text="")

    wrong = ProjectedEvent(0, "agent_message_chunk", None, "wrong", None)
    assert await projection.accept_source_update(0, wrong, generation=PromptGeneration(2, "acp", "prompt")) is False
    projection.close_producer()
    assert await projection.accept_source_update(0, _event(0, "agent_message_chunk", "late")) is False
    assert queue.snapshot() == ()


def test_turn_accumulators_are_bounded_with_visible_original_byte_counts() -> None:
    projection = BoundedPromptProjection(
        generation=PromptGeneration(1, "acp", "prompt"),
        queue=PresentationQueue(max_events=8, max_utf8_bytes=4096),
        user_text="u" * (256 * 1024 + 100),
    )
    projection.accumulate_assistant_text("a" * (1024 * 1024 + 200))

    turn = projection.finalize("cancelled")

    assert len(turn.user_text.encode("utf-8")) <= 256 * 1024
    assert len(turn.assistant_text.encode("utf-8")) <= 1024 * 1024
    assert "truncated" in turn.user_text
    assert str(256 * 1024 + 100) in turn.user_text
    assert "truncated" in turn.assistant_text
    assert str(1024 * 1024 + 200) in turn.assistant_text
    assert turn.stop_reason == "cancelled"


@pytest.mark.asyncio
async def test_tool_card_truncation_includes_marker_inside_utf8_byte_limit() -> None:
    projection = BoundedPromptProjection(
        generation=PromptGeneration(1, "acp", "prompt"),
        queue=PresentationQueue(max_events=8, max_utf8_bytes=1024 * 1024),
        user_text="",
    )
    event = ProjectedEvent(0, "tool_call_update", "tool", "界" * 20_000, None)

    assert await projection.accept_source_update(0, event)
    card = projection.finalize("end_turn").tool_cards[0]

    assert len(card["content"].encode("utf-8")) <= 16 * 1024
    assert "truncated" in card["content"]
    assert card["originalBytes"] == len(event.panel_bytes())


def test_unknown_meta_has_closed_record_key_and_total_limits() -> None:
    records = [
        {f"key-{index}-{sub}": "secret-value" if sub == 0 else "x" * 10_000 for sub in range(20)}
        for index in range(40)
    ]

    projected = project_unknown_meta(records)

    assert len(projected.records) == 32
    assert all(len(record) <= 16 for record in projected.records)
    assert all(len(key.encode("utf-8")) <= 64 for record in projected.records for key in record)
    assert len(projected.encoded_payload) <= 8 * 1024
    assert projected.omitted_records == 8
    assert projected.omitted_keys > 0
    assert b"secret-value" not in projected.encoded_payload


def test_cache_publishes_immutable_turns_and_evicts_complete_oldest_files(tmp_path: Path) -> None:
    cache = PresentationCache(tmp_path / "presentation", max_turns=3, max_bytes=10_000)
    for value in ("one", "two", "three", "four"):
        projection = BoundedPromptProjection(
            generation=PromptGeneration(1, "acp", value),
            queue=PresentationQueue(max_events=8, max_utf8_bytes=4096),
            user_text=value,
        )
        projection.accumulate_assistant_text(value.upper())
        cache.publish(projection.finalize("end_turn"))

    history = cache.load()
    assert history.available is True
    assert [turn["sequence"] for turn in history.turns] == [2, 3, 4]
    assert history.earlier_history_omitted is True
    assert len(list((tmp_path / "presentation").glob("*.json"))) == 3


def test_cache_corruption_is_disposable_and_fallback_is_create_only(tmp_path: Path) -> None:
    root = tmp_path / "presentation"
    root.mkdir()
    (root / "00000001.json").write_text("not-json", encoding="utf-8")
    cache = PresentationCache(root)

    history = cache.load()
    assert history.available is False
    assert history.message == "presentation history unavailable"

    (root / "00000001.json").unlink()
    sequence = cache.publish_fallback(
        stop_reason="max_tokens",
        original_byte_counts={"user": 9000, "assistant": 12000},
    )
    payload = (root / f"{sequence:08d}.json").read_bytes()
    assert len(payload) <= 8 * 1024
    assert b"Turn presentation was unavailable. Prime retains the authoritative conversation state." in payload


def test_empty_cache_is_unavailable_history(tmp_path: Path) -> None:
    history = PresentationCache(tmp_path / "presentation").load()

    assert history.available is False
    assert history.turns == ()
    assert history.message == "presentation history unavailable"


@pytest.mark.parametrize(
    "corrupt_field,corrupt_value",
    [
        ("images", None),
        ("toolCards", None),
        ("userText", None),
        ("assistantText", 3),
        ("userOriginalBytes", -1),
        ("stopReason", None),
        ("stopReason", "provider_error"),
        ("sequence", True),
        (
            "images",
            [
                {
                    "fileName": "too-large.png",
                    "mimeType": "image/png",
                    "binaryBytes": 16 * 1024 * 1024 + 1,
                    "width": 1,
                    "height": 1,
                    "sha256": "a" * 64,
                    "previewAvailable": False,
                }
            ],
        ),
        ("toolCards", [{"kind": "tool_call", "content": "kept", "originalBytes": 1}]),
    ],
)
def test_cache_rejects_incomplete_or_wrongly_typed_turn_schema(
    tmp_path: Path,
    corrupt_field: str,
    corrupt_value: object,
) -> None:
    root = tmp_path / "presentation"
    root.mkdir()
    payload = {
        "sequence": 1,
        "userText": "inspect",
        "assistantText": "done",
        "userOriginalBytes": 7,
        "assistantOriginalBytes": 4,
        "stopReason": "end_turn",
        "toolCards": [],
        "images": [],
    }
    payload[corrupt_field] = corrupt_value
    (root / "00000001.json").write_text(json.dumps(payload), encoding="utf-8")

    history = PresentationCache(root).load()

    assert history.available is False
    assert history.message == "presentation history unavailable"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "sequence": 1,
            "stopReason": "max_tokens",
            "originalByteCounts": {"user": 9},
            "message": "Turn presentation was unavailable. Prime retains the authoritative conversation state.",
            "fallback": True,
        },
        {
            "sequence": 1,
            "stopReason": "max_tokens",
            "originalByteCounts": {"user": 9, "assistant": 12},
            "message": "wrong",
            "fallback": True,
        },
    ],
)
def test_cache_rejects_fallback_rows_outside_the_closed_schema(tmp_path: Path, payload: dict) -> None:
    root = tmp_path / "presentation"
    root.mkdir()
    (root / "00000001.json").write_text(json.dumps(payload), encoding="utf-8")

    history = PresentationCache(root).load()

    assert history.available is False
    assert history.message == "presentation history unavailable"


def test_cache_rejects_fallback_file_above_its_byte_limit(tmp_path: Path) -> None:
    root = tmp_path / "presentation"
    root.mkdir()
    payload = {
        "sequence": 1,
        "stopReason": "error",
        "originalByteCounts": {"user": 9, "assistant": 12},
        "message": "Turn presentation was unavailable. Prime retains the authoritative conversation state.",
        "fallback": True,
    }
    encoded = json.dumps(payload) + (" " * (8 * 1024))
    (root / "00000001.json").write_text(encoded, encoding="utf-8")

    history = PresentationCache(root).load()

    assert history.available is False
    assert history.message == "presentation history unavailable"


def test_cache_loader_accepts_writer_output_with_many_bounded_tool_cards(tmp_path: Path) -> None:
    cache = PresentationCache(tmp_path / "presentation")
    cards = tuple({"kind": "tool_update", "content": "x", "originalBytes": 1} for _ in range(300))

    cache.publish(TurnProjection("inspect", "done", 7, 4, "end_turn", cards, ()))

    history = cache.load()
    assert history.available is True
    assert len(history.turns[0]["toolCards"]) == 300


def test_cache_rejects_internal_sequence_gaps(tmp_path: Path) -> None:
    root = tmp_path / "presentation"
    root.mkdir()
    turn = TurnProjection("inspect", "done", 7, 4, "end_turn", (), ())
    for sequence in (1, 3):
        (root / f"{sequence:08d}.json").write_text(
            json.dumps(turn.payload(sequence)),
            encoding="utf-8",
        )

    history = PresentationCache(root).load()

    assert history.available is False
    assert history.message == "presentation history unavailable"


def test_cache_rejects_non_ascii_sequence_filename_as_unavailable_history(tmp_path: Path) -> None:
    root = tmp_path / "presentation"
    root.mkdir()
    non_ascii_sequence = "\N{SUPERSCRIPT TWO}" * 8
    (root / f"{non_ascii_sequence}.json").write_text("{}", encoding="utf-8")

    history = PresentationCache(root).load()

    assert history.available is False
    assert history.message == "presentation history unavailable"


def test_cache_rejects_escaped_lone_surrogate_as_unavailable_history(tmp_path: Path) -> None:
    root = tmp_path / "presentation"
    root.mkdir()
    payload = TurnProjection("inspect", "done", 7, 4, "end_turn", (), ()).payload(1)
    payload["userText"] = "\ud800"
    (root / "00000001.json").write_text(json.dumps(payload), encoding="utf-8")

    history = PresentationCache(root).load()

    assert history.available is False
    assert history.message == "presentation history unavailable"


def test_cache_rejects_lone_surrogate_tool_kind_as_unavailable_history(tmp_path: Path) -> None:
    root = tmp_path / "presentation"
    root.mkdir()
    payload = TurnProjection(
        "inspect",
        "done",
        7,
        4,
        "end_turn",
        ({"kind": "\ud800", "content": "kept", "originalBytes": 4},),
        (),
    ).payload(1)
    (root / "00000001.json").write_text(json.dumps(payload), encoding="utf-8")

    history = PresentationCache(root).load()

    assert history.available is False
    assert history.message == "presentation history unavailable"


def test_cache_evicts_before_create_only_publication(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "presentation"
    cache = PresentationCache(root, max_turns=1, max_bytes=10_000)
    first = BoundedPromptProjection(
        generation=PromptGeneration(1, "acp", "first"),
        queue=PresentationQueue(max_events=8, max_utf8_bytes=4096),
        user_text="first",
    )
    second = BoundedPromptProjection(
        generation=PromptGeneration(1, "acp", "second"),
        queue=PresentationQueue(max_events=8, max_utf8_bytes=4096),
        user_text="second",
    )
    cache.publish(first.finalize("end_turn"))
    first_path = root / "00000001.json"
    real_unlink = Path.unlink

    def fail_oldest_unlink(path: Path, *args, **kwargs):
        if path == first_path:
            raise PermissionError("injected eviction failure")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_oldest_unlink)

    with pytest.raises(PermissionError, match="injected eviction failure"):
        cache.publish(second.finalize("end_turn"))
    assert [path.name for path in root.glob("*.json")] == ["00000001.json"]


def test_cache_bounds_existing_files_before_reading_retained_payloads(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "presentation"
    writer = PresentationCache(root, max_turns=3, max_bytes=10_000)
    for value in ("one", "two", "three"):
        projection = BoundedPromptProjection(
            generation=PromptGeneration(1, "acp", value),
            queue=PresentationQueue(max_events=8, max_utf8_bytes=4096),
            user_text=value,
        )
        writer.publish(projection.finalize("end_turn"))

    real_read_bytes = Path.read_bytes

    def refuse_evicted_reads(path: Path):
        if path.name in {"00000001.json", "00000002.json"}:
            raise AssertionError("evicted payload was read before cache bounding")
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", refuse_evicted_reads)
    history = PresentationCache(root, max_turns=1, max_bytes=10_000).load()

    assert history.available
    assert [turn["sequence"] for turn in history.turns] == [3]
    assert [path.name for path in root.glob("*.json")] == ["00000003.json"]
