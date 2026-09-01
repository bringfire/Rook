"""Bounded live ACP projection and disposable panel presentation history."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, Protocol

from acp.schema import AgentMessageChunk, AgentThoughtChunk, TextContentBlock

from .acp_storage import PublicationAlreadyExists, atomic_publish_noreplace


MAX_QUEUE_EVENTS = 256
MAX_QUEUE_UTF8_BYTES = 4 * 1024 * 1024
CALLBACK_DEADLINE_SECONDS = 1.0
MAX_USER_TEXT_BYTES = 256 * 1024
MAX_ASSISTANT_TEXT_BYTES = 1024 * 1024
MAX_TOOL_CONTENT_BYTES_PER_CARD = 16 * 1024
MAX_TOOL_CONTENT_BYTES_PER_TURN = 1024 * 1024
MAX_CACHED_TURN_BYTES = 4 * 1024 * 1024
MAX_CONVERSATION_CACHE_BYTES = 64 * 1024 * 1024
MAX_CACHED_TURNS = 256
MAX_FALLBACK_PROJECTION_BYTES = 8 * 1024
MAX_UNKNOWN_META_RECORDS = 32
MAX_UNKNOWN_META_KEYS_PER_RECORD = 16
MAX_UNKNOWN_META_KEY_BYTES = 64
MAX_UNKNOWN_META_TOTAL_BYTES = 8 * 1024

TRUNCATION_TEMPLATE = "\n[truncated; original UTF-8 bytes: {original_bytes}]"
FALLBACK_SENTENCE = "Turn presentation was unavailable. Prime retains the authoritative conversation state."
OMITTED_HISTORY_SENTENCE = "Earlier presentation history was omitted. Prime retains the authoritative conversation state."


@dataclass(frozen=True)
class PromptGeneration:
    launch_generation: int
    acp_session_id: str
    prompt_id: str


@dataclass(frozen=True)
class ProjectedEvent:
    source_ordinal: int
    kind: str
    message_id: str | None
    text: str | None
    payload: dict[str, Any] | None

    def panel_bytes(self) -> bytes:
        return json.dumps(
            {
                "sourceOrdinal": self.source_ordinal,
                "kind": self.kind,
                "messageId": self.message_id,
                "text": self.text,
                "payload": self.payload,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")


class PresentationSink(Protocol):
    async def write(self, event: ProjectedEvent) -> None: ...

    async def drain(self, deadline_seconds: float) -> bool: ...


class PresentationQueue:
    def __init__(self, *, max_events: int = MAX_QUEUE_EVENTS, max_utf8_bytes: int = MAX_QUEUE_UTF8_BYTES) -> None:
        self._max_events = max_events
        self._max_utf8_bytes = max_utf8_bytes
        self._rows: deque[ProjectedEvent] = deque()
        self._bytes = 0
        self._closed = False
        self._condition = asyncio.Condition()

    async def admit(self, event: ProjectedEvent) -> bool:
        event_bytes = len(event.panel_bytes())
        if event_bytes > self._max_utf8_bytes:
            return False
        async with self._condition:
            while True:
                if self._closed:
                    return False
                replacement = self._coalesced(event)
                if replacement is not None:
                    old_size = len(self._rows[-1].panel_bytes())
                    new_size = len(replacement.panel_bytes())
                    if self._bytes - old_size + new_size <= self._max_utf8_bytes:
                        self._rows[-1] = replacement
                        self._bytes = self._bytes - old_size + new_size
                        self._condition.notify_all()
                        return True
                if len(self._rows) < self._max_events and self._bytes + event_bytes <= self._max_utf8_bytes:
                    self._rows.append(event)
                    self._bytes += event_bytes
                    self._condition.notify_all()
                    return True
                await self._condition.wait()

    def _coalesced(self, event: ProjectedEvent) -> ProjectedEvent | None:
        if not self._rows or event.kind not in {"agent_message_chunk", "agent_thought_chunk"}:
            return None
        previous = self._rows[-1]
        if (
            not event.message_id
            or previous.kind != event.kind
            or previous.message_id != event.message_id
            or previous.text is None
            or event.text is None
        ):
            return None
        return replace(previous, text=previous.text + event.text)

    async def get(self) -> ProjectedEvent | None:
        async with self._condition:
            while not self._rows and not self._closed:
                await self._condition.wait()
            if not self._rows:
                return None
            row = self._rows.popleft()
            self._bytes -= len(row.panel_bytes())
            self._condition.notify_all()
            return row

    def snapshot(self) -> tuple[ProjectedEvent, ...]:
        return tuple(self._rows)

    def close_producer(self) -> None:
        self._closed = True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._notify_waiters())

    async def _notify_waiters(self) -> None:
        async with self._condition:
            self._condition.notify_all()

    async def wait_empty(self, deadline_seconds: float) -> bool:
        async def _wait() -> None:
            async with self._condition:
                await self._condition.wait_for(lambda: not self._rows)

        try:
            await asyncio.wait_for(_wait(), timeout=deadline_seconds)
        except asyncio.TimeoutError:
            return False
        return True


class _BoundedText:
    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._retained = bytearray()
        self.original_bytes = 0

    def append(self, value: str) -> None:
        encoded = value.encode("utf-8")
        self.original_bytes += len(encoded)
        remaining = self._limit - len(self._retained)
        if remaining > 0:
            self._retained.extend(encoded[:remaining])

    @property
    def value(self) -> str:
        if self.original_bytes <= self._limit:
            return bytes(self._retained).decode("utf-8", errors="ignore")
        marker = TRUNCATION_TEMPLATE.format(original_bytes=self.original_bytes).encode("utf-8")
        content_limit = max(0, self._limit - len(marker))
        content = bytes(self._retained[:content_limit]).decode("utf-8", errors="ignore")
        return content + marker.decode("utf-8")


@dataclass(frozen=True)
class TurnProjection:
    user_text: str
    assistant_text: str
    user_original_bytes: int
    assistant_original_bytes: int
    stop_reason: str
    tool_cards: tuple[dict[str, Any], ...]
    image_metadata: tuple[dict[str, Any], ...]

    def payload(self, sequence: int) -> dict[str, Any]:
        return {
            "sequence": sequence,
            "userText": self.user_text,
            "assistantText": self.assistant_text,
            "userOriginalBytes": self.user_original_bytes,
            "assistantOriginalBytes": self.assistant_original_bytes,
            "stopReason": self.stop_reason,
            "toolCards": list(self.tool_cards),
            "images": list(self.image_metadata),
        }


class BoundedPromptProjection:
    def __init__(
        self,
        *,
        generation: PromptGeneration,
        queue: PresentationQueue,
        user_text: str,
        callback_deadline_seconds: float = CALLBACK_DEADLINE_SECONDS,
    ) -> None:
        self.generation = generation
        self.queue = queue
        self._callback_deadline = callback_deadline_seconds
        self._condition = asyncio.Condition()
        self._next_source_ordinal = 0
        self._closed = False
        self._overflowed = False
        self.overflow_signal = asyncio.Event()
        self._user = _BoundedText(MAX_USER_TEXT_BYTES)
        self._assistant = _BoundedText(MAX_ASSISTANT_TEXT_BYTES)
        self._user.append(user_text)
        self._tool_cards: list[dict[str, Any]] = []
        self._tool_bytes = 0

    @property
    def overflowed(self) -> bool:
        return self._overflowed

    async def accept_source_update(
        self,
        source_ordinal: int,
        update: ProjectedEvent | Any,
        *,
        generation: PromptGeneration | None = None,
    ) -> bool:
        if self._closed or self._overflowed or (generation is not None and generation != self.generation):
            return False
        try:
            async with asyncio.timeout(self._callback_deadline):
                async with self._condition:
                    await self._condition.wait_for(
                        lambda: self._closed or self._overflowed or source_ordinal == self._next_source_ordinal
                    )
                    if self._closed or self._overflowed or (generation is not None and generation != self.generation):
                        return False
                    event = _project_event(source_ordinal, update)
                    admitted = await self.queue.admit(event)
                    if not admitted:
                        self._set_overflow()
                        return False
                    self._accumulate(event)
                    self._next_source_ordinal += 1
                    self._condition.notify_all()
                    return True
        except TimeoutError:
            self._set_overflow()
            async with self._condition:
                self._condition.notify_all()
            return False

    def _set_overflow(self) -> None:
        self._overflowed = True
        self.overflow_signal.set()

    def _accumulate(self, event: ProjectedEvent) -> None:
        if event.kind == "agent_message_chunk" and event.text:
            self._assistant.append(event.text)
        if event.kind.startswith("tool_"):
            raw = event.panel_bytes()
            original = len(raw)
            retained = raw[:MAX_TOOL_CONTENT_BYTES_PER_CARD]
            if self._tool_bytes + len(retained) > MAX_TOOL_CONTENT_BYTES_PER_TURN:
                return
            self._tool_bytes += len(retained)
            text = retained.decode("utf-8", errors="ignore")
            if original > len(retained):
                marker = TRUNCATION_TEMPLATE.format(original_bytes=original)
                text = text[: max(0, MAX_TOOL_CONTENT_BYTES_PER_CARD - len(marker.encode("utf-8")))] + marker
            self._tool_cards.append({"kind": event.kind, "content": text, "originalBytes": original})

    def accumulate_assistant_text(self, value: str) -> None:
        self._assistant.append(value)

    def close_producer(self) -> None:
        self._closed = True
        self.queue.close_producer()

    def finalize(
        self,
        stop_reason: str,
        *,
        image_metadata: Iterable[dict[str, Any]] = (),
    ) -> TurnProjection:
        return TurnProjection(
            user_text=self._user.value,
            assistant_text=self._assistant.value,
            user_original_bytes=self._user.original_bytes,
            assistant_original_bytes=self._assistant.original_bytes,
            stop_reason=stop_reason,
            tool_cards=tuple(self._tool_cards),
            image_metadata=tuple(image_metadata),
        )


def _project_event(source_ordinal: int, update: ProjectedEvent | Any) -> ProjectedEvent:
    if isinstance(update, ProjectedEvent):
        return replace(update, source_ordinal=source_ordinal)
    field_meta = getattr(update, "field_meta", None) or {}
    message_id = field_meta.get("messageId") if isinstance(field_meta, dict) else None
    content = getattr(update, "content", None)
    text = content.text if isinstance(content, TextContentBlock) else None
    if isinstance(update, AgentMessageChunk):
        kind = "agent_message_chunk"
    elif isinstance(update, AgentThoughtChunk):
        kind = "agent_thought_chunk"
    else:
        kind = str(getattr(update, "session_update", "unknown"))
    payload = None if text is not None else update.model_dump(by_alias=True, exclude_none=True)
    return ProjectedEvent(source_ordinal, kind, message_id, text, payload)


def map_stop_reason(stop_reason: str) -> Literal["settled", "cancelled", "incomplete", "refused", "error"]:
    return {
        "end_turn": "settled",
        "cancelled": "cancelled",
        "max_tokens": "incomplete",
        "max_turn_requests": "incomplete",
        "refusal": "refused",
    }.get(stop_reason, "error")


@dataclass(frozen=True)
class UnknownMetaProjection:
    records: tuple[dict[str, str], ...]
    encoded_payload: bytes
    omitted_records: int
    omitted_keys: int
    omitted_values: int


def _bounded_meta_key(value: object) -> tuple[str, bool]:
    text = str(value)
    encoded = text.encode("utf-8")
    if len(encoded) <= MAX_UNKNOWN_META_KEY_BYTES:
        return text, False
    marker = "...[truncated]"
    keep = MAX_UNKNOWN_META_KEY_BYTES - len(marker.encode("utf-8"))
    return encoded[:keep].decode("utf-8", errors="ignore") + marker, True


def project_unknown_meta(records: Iterable[Mapping[str, Any]]) -> UnknownMetaProjection:
    selected: list[dict[str, str]] = []
    omitted_records = 0
    omitted_keys = 0
    omitted_values = 0
    for record_index, record in enumerate(records):
        if record_index >= MAX_UNKNOWN_META_RECORDS:
            omitted_records += 1
            continue
        projected: dict[str, str] = {}
        for key_index, key in enumerate(record):
            if key_index >= MAX_UNKNOWN_META_KEYS_PER_RECORD:
                omitted_keys += 1
                continue
            bounded_key, key_truncated = _bounded_meta_key(key)
            if key_truncated:
                omitted_keys += 1
            lowered = bounded_key.casefold()
            value = "[redacted]" if any(word in lowered for word in ("secret", "token", "password", "api_key")) else f"<{type(record[key]).__name__}>"
            candidate = selected + [projected | {bounded_key: value}]
            encoded = json.dumps(candidate, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            if len(encoded) > MAX_UNKNOWN_META_TOTAL_BYTES:
                omitted_values += 1
                continue
            projected[bounded_key] = value
        selected.append(projected)
    encoded_payload = json.dumps(selected, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    while len(encoded_payload) > MAX_UNKNOWN_META_TOTAL_BYTES:
        last_nonempty = next((record for record in reversed(selected) if record), None)
        if last_nonempty is None:
            break
        last_nonempty.pop(next(reversed(last_nonempty)))
        omitted_values += 1
        encoded_payload = json.dumps(selected, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return UnknownMetaProjection(tuple(selected), encoded_payload, omitted_records, omitted_keys, omitted_values)


@dataclass(frozen=True)
class PresentationHistory:
    available: bool
    turns: tuple[dict[str, Any], ...]
    earlier_history_omitted: bool
    message: str | None = None


class PresentationCacheError(RuntimeError):
    pass


class PresentationCache:
    def __init__(
        self,
        root: Path,
        *,
        max_turns: int = MAX_CACHED_TURNS,
        max_bytes: int = MAX_CONVERSATION_CACHE_BYTES,
    ) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._max_turns = max_turns
        self._max_bytes = max_bytes

    def publish(self, turn: TurnProjection) -> int:
        entries = self._load_entries_or_raise()
        sequence = max((value[0] for value in entries), default=0) + 1
        payload = _canonical_json_bytes(turn.payload(sequence))
        if len(payload) > MAX_CACHED_TURN_BYTES:
            raise PresentationCacheError("projected turn is oversized")
        try:
            atomic_publish_noreplace(self._turn_path(sequence), payload)
        except PublicationAlreadyExists as exc:
            raise PresentationCacheError("presentation sequence already exists") from exc
        self._evict()
        return sequence

    def publish_fallback(self, *, stop_reason: str, original_byte_counts: Mapping[str, int]) -> int:
        entries = self._load_entries_or_raise()
        sequence = max((value[0] for value in entries), default=0) + 1
        payload = _canonical_json_bytes(
            {
                "sequence": sequence,
                "stopReason": stop_reason,
                "originalByteCounts": dict(original_byte_counts),
                "message": FALLBACK_SENTENCE,
                "fallback": True,
            }
        )
        if len(payload) > MAX_FALLBACK_PROJECTION_BYTES:
            raise PresentationCacheError("fallback projection is oversized")
        atomic_publish_noreplace(self._turn_path(sequence), payload)
        self._evict()
        return sequence

    def load(self) -> PresentationHistory:
        try:
            entries = self._load_entries_or_raise()
        except PresentationCacheError:
            return PresentationHistory(False, (), False, "presentation history unavailable")
        turns = tuple(payload for _, _, payload in entries)
        omitted = bool(entries and entries[0][0] > 1)
        return PresentationHistory(True, turns, omitted, OMITTED_HISTORY_SENTENCE if omitted else None)

    def _load_entries_or_raise(self) -> list[tuple[int, Path, dict[str, Any]]]:
        entries: list[tuple[int, Path, dict[str, Any]]] = []
        for path in sorted(self.root.glob("*.json")):
            if len(path.stem) != 8 or not path.stem.isdigit() or path.is_symlink():
                raise PresentationCacheError("presentation cache entry is invalid")
            try:
                raw = path.read_bytes()
                payload = json.loads(raw.decode("utf-8", errors="strict"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise PresentationCacheError("presentation cache entry is corrupt") from exc
            sequence = int(path.stem)
            if not isinstance(payload, dict) or payload.get("sequence") != sequence or len(raw) > MAX_CACHED_TURN_BYTES:
                raise PresentationCacheError("presentation cache entry is invalid")
            entries.append((sequence, path, payload))
        return entries

    def _evict(self) -> None:
        entries = self._load_entries_or_raise()
        total = sum(path.stat().st_size for _, path, _ in entries)
        while entries and (len(entries) > self._max_turns or total > self._max_bytes):
            _, path, _ = entries.pop(0)
            size = path.stat().st_size
            path.unlink()
            total -= size

    def _turn_path(self, sequence: int) -> Path:
        return self.root / f"{sequence:08d}.json"


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
