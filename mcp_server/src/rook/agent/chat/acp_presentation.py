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

from .acp_images import (
    MAX_IMAGE_BYTES,
    MAX_IMAGE_BYTES_PER_TURN,
    MAX_IMAGE_DIMENSION,
    MAX_IMAGE_FILE_NAME_UTF8_BYTES,
    MAX_IMAGE_PIXELS,
    MAX_IMAGES_PER_TURN,
)
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
    effective_settings: dict[str, str | None] | None = None

    def panel_bytes(self) -> bytes:
        return json.dumps(
            {
                **({"effectiveSettings": self.effective_settings} if self.effective_settings is not None else {}),
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
        if previous.effective_settings is not None or event.effective_settings is not None:
            return None
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
        effective_settings: dict[str, str | None] | None = None,
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
                    if effective_settings is not None:
                        event = replace(event, effective_settings=effective_settings)
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
            text = _bounded_utf8_with_marker(raw, MAX_TOOL_CONTENT_BYTES_PER_CARD, original)
            retained_bytes = len(text.encode("utf-8"))
            if self._tool_bytes + retained_bytes > MAX_TOOL_CONTENT_BYTES_PER_TURN:
                return
            self._tool_bytes += retained_bytes
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


@dataclass(frozen=True)
class _CacheEntry:
    sequence: int
    path: Path
    byte_count: int


_TURN_KEYS = {
    "sequence",
    "userText",
    "assistantText",
    "userOriginalBytes",
    "assistantOriginalBytes",
    "stopReason",
    "toolCards",
    "images",
}
_FALLBACK_KEYS = {"sequence", "stopReason", "originalByteCounts", "message", "fallback"}
_TOOL_CARD_KEYS = {"kind", "content", "originalBytes"}
_IMAGE_KEYS = {
    "fileName",
    "mimeType",
    "binaryBytes",
    "width",
    "height",
    "sha256",
    "previewAvailable",
}
_STOP_REASONS = frozenset({"end_turn", "cancelled", "max_tokens", "max_turn_requests", "refusal", "error"})


def _is_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_positive_int(value: object) -> bool:
    return _is_nonnegative_int(value) and value > 0


def _validate_cache_payload(payload: dict[str, Any], sequence: int, byte_count: int) -> None:
    if payload.get("fallback") is True:
        if byte_count > MAX_FALLBACK_PROJECTION_BYTES:
            raise PresentationCacheError("fallback presentation is oversized")
        if set(payload) != _FALLBACK_KEYS:
            raise PresentationCacheError("fallback presentation schema is invalid")
        counts = payload.get("originalByteCounts")
        if (
            not _is_positive_int(payload.get("sequence"))
            or payload["sequence"] != sequence
            or payload.get("stopReason") not in _STOP_REASONS
            or payload.get("message") != FALLBACK_SENTENCE
            or not isinstance(counts, dict)
            or set(counts) != {"user", "assistant"}
            or not all(_is_nonnegative_int(value) for value in counts.values())
        ):
            raise PresentationCacheError("fallback presentation fields are invalid")
        return

    if set(payload) != _TURN_KEYS:
        raise PresentationCacheError("turn presentation schema is invalid")
    if (
        not _is_positive_int(payload.get("sequence"))
        or payload["sequence"] != sequence
        or not isinstance(payload.get("userText"), str)
        or not isinstance(payload.get("assistantText"), str)
        or not _is_nonnegative_int(payload.get("userOriginalBytes"))
        or not _is_nonnegative_int(payload.get("assistantOriginalBytes"))
        or payload.get("stopReason") not in _STOP_REASONS
        or not isinstance(payload.get("toolCards"), list)
        or not isinstance(payload.get("images"), list)
    ):
        raise PresentationCacheError("turn presentation fields are invalid")
    retained_user_bytes = len(payload["userText"].encode("utf-8"))
    retained_assistant_bytes = len(payload["assistantText"].encode("utf-8"))
    if retained_user_bytes > MAX_USER_TEXT_BYTES or payload["userOriginalBytes"] < retained_user_bytes:
        raise PresentationCacheError("turn user projection is oversized")
    if retained_assistant_bytes > MAX_ASSISTANT_TEXT_BYTES or payload["assistantOriginalBytes"] < retained_assistant_bytes:
        raise PresentationCacheError("turn assistant projection is oversized")

    tool_bytes = 0
    for card in payload["toolCards"]:
        if (
            not isinstance(card, dict)
            or set(card) != _TOOL_CARD_KEYS
            or not isinstance(card.get("kind"), str)
            or not card["kind"]
            or not isinstance(card.get("content"), str)
            or not _is_nonnegative_int(card.get("originalBytes"))
        ):
            raise PresentationCacheError("turn tool projection is invalid")
        card["kind"].encode("utf-8")
        retained_bytes = len(card["content"].encode("utf-8"))
        if retained_bytes > MAX_TOOL_CONTENT_BYTES_PER_CARD or card["originalBytes"] < retained_bytes:
            raise PresentationCacheError("turn tool projection is oversized")
        tool_bytes += retained_bytes
    if tool_bytes > MAX_TOOL_CONTENT_BYTES_PER_TURN:
        raise PresentationCacheError("turn tool projections are oversized")

    if len(payload["images"]) > MAX_IMAGES_PER_TURN:
        raise PresentationCacheError("turn image projection count is invalid")
    image_bytes = 0
    for image in payload["images"]:
        sha256 = image.get("sha256") if isinstance(image, dict) else None
        if (
            not isinstance(image, dict)
            or set(image) != _IMAGE_KEYS
            or not isinstance(image.get("fileName"), str)
            or not image["fileName"]
            or len(image["fileName"].encode("utf-8")) > MAX_IMAGE_FILE_NAME_UTF8_BYTES
            or image.get("mimeType") not in {"image/png", "image/jpeg", "image/webp"}
            or not _is_positive_int(image.get("binaryBytes"))
            or image["binaryBytes"] > MAX_IMAGE_BYTES
            or not _is_positive_int(image.get("width"))
            or image["width"] > MAX_IMAGE_DIMENSION
            or not _is_positive_int(image.get("height"))
            or image["height"] > MAX_IMAGE_DIMENSION
            or image["width"] * image["height"] > MAX_IMAGE_PIXELS
            or not isinstance(sha256, str)
            or len(sha256) != 64
            or any(char not in "0123456789abcdef" for char in sha256)
            or image.get("previewAvailable") is not False
        ):
            raise PresentationCacheError("turn image projection is invalid")
        image_bytes += image["binaryBytes"]
    if image_bytes > MAX_IMAGE_BYTES_PER_TURN:
        raise PresentationCacheError("turn image projections are oversized")


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
        entries = self._scan_entries_or_raise()
        sequence = max((entry.sequence for entry in entries), default=0) + 1
        payload = _canonical_json_bytes(turn.payload(sequence))
        if len(payload) > MAX_CACHED_TURN_BYTES:
            raise PresentationCacheError("projected turn is oversized")
        entries = self._evict_to_fit(entries, incoming_bytes=len(payload), incoming_turns=1)
        self._load_payloads_or_raise(entries)
        try:
            atomic_publish_noreplace(self._turn_path(sequence), payload)
        except PublicationAlreadyExists as exc:
            raise PresentationCacheError("presentation sequence already exists") from exc
        return sequence

    def publish_fallback(self, *, stop_reason: str, original_byte_counts: Mapping[str, int]) -> int:
        entries = self._scan_entries_or_raise()
        sequence = max((entry.sequence for entry in entries), default=0) + 1
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
        entries = self._evict_to_fit(entries, incoming_bytes=len(payload), incoming_turns=1)
        self._load_payloads_or_raise(entries)
        try:
            atomic_publish_noreplace(self._turn_path(sequence), payload)
        except PublicationAlreadyExists as exc:
            raise PresentationCacheError("presentation sequence already exists") from exc
        return sequence

    def load(self) -> PresentationHistory:
        try:
            metadata = self._evict_to_fit(self._scan_entries_or_raise(), incoming_bytes=0, incoming_turns=0)
            if not metadata:
                raise PresentationCacheError("presentation cache is empty")
            entries = self._load_payloads_or_raise(metadata)
        except (OSError, PresentationCacheError):
            return PresentationHistory(False, (), False, "presentation history unavailable")
        turns = tuple(payload for _, _, payload in entries)
        omitted = bool(entries and entries[0][0] > 1)
        return PresentationHistory(True, turns, omitted, OMITTED_HISTORY_SENTENCE if omitted else None)

    def _scan_entries_or_raise(self) -> list[_CacheEntry]:
        entries: list[_CacheEntry] = []
        for path in sorted(self.root.glob("*.json")):
            if (
                len(path.stem) != 8
                or any(char not in "0123456789" for char in path.stem)
                or path.is_symlink()
            ):
                raise PresentationCacheError("presentation cache entry is invalid")
            try:
                byte_count = path.stat().st_size
            except OSError as exc:
                raise PresentationCacheError("presentation cache entry is unavailable") from exc
            sequence = int(path.stem)
            entries.append(_CacheEntry(sequence, path, byte_count))
        return entries

    def _load_payloads_or_raise(
        self,
        entries: Iterable[_CacheEntry],
    ) -> list[tuple[int, Path, dict[str, Any]]]:
        materialized = list(entries)
        if any(
            current.sequence != previous.sequence + 1
            for previous, current in zip(materialized, materialized[1:])
        ):
            raise PresentationCacheError("presentation cache sequence is discontinuous")
        loaded: list[tuple[int, Path, dict[str, Any]]] = []
        for entry in materialized:
            if entry.byte_count > MAX_CACHED_TURN_BYTES:
                raise PresentationCacheError("presentation cache entry is invalid")
            try:
                raw = entry.path.read_bytes()
                payload = json.loads(raw.decode("utf-8", errors="strict"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise PresentationCacheError("presentation cache entry is corrupt") from exc
            if len(raw) != entry.byte_count or not isinstance(payload, dict) or payload.get("sequence") != entry.sequence:
                raise PresentationCacheError("presentation cache entry is invalid")
            try:
                _validate_cache_payload(payload, entry.sequence, entry.byte_count)
            except UnicodeEncodeError as exc:
                raise PresentationCacheError("presentation cache entry contains invalid Unicode") from exc
            loaded.append((entry.sequence, entry.path, payload))
        return loaded

    def _evict_to_fit(
        self,
        entries: list[_CacheEntry],
        *,
        incoming_bytes: int,
        incoming_turns: int,
    ) -> list[_CacheEntry]:
        if incoming_turns > self._max_turns or incoming_bytes > self._max_bytes:
            raise PresentationCacheError("presentation cache limits cannot admit turn")
        retained = list(entries)
        total = sum(entry.byte_count for entry in retained)
        while retained and (
            len(retained) + incoming_turns > self._max_turns
            or total + incoming_bytes > self._max_bytes
        ):
            entry = retained.pop(0)
            entry.path.unlink()
            total -= entry.byte_count
        if len(retained) + incoming_turns > self._max_turns or total + incoming_bytes > self._max_bytes:
            raise PresentationCacheError("presentation cache limits cannot admit turn")
        return retained

    def _turn_path(self, sequence: int) -> Path:
        return self.root / f"{sequence:08d}.json"


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"


def _bounded_utf8_with_marker(raw: bytes, limit: int, original_bytes: int) -> str:
    if len(raw) <= limit:
        return raw.decode("utf-8", errors="ignore")
    marker = TRUNCATION_TEMPLATE.format(original_bytes=original_bytes).encode("utf-8")
    content_limit = max(0, limit - len(marker))
    content = raw[:content_limit].decode("utf-8", errors="ignore")
    return content + marker.decode("utf-8")
