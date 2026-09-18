"""ACP callbacks for one directly owned Prime conversation process."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Mapping

from acp.schema import (
    PermissionOption,
    RequestPermissionResponse,
    ToolCallUpdate,
)

from .acp_presentation import (
    BoundedPromptProjection,
    PromptGeneration,
    UnknownMetaProjection,
    project_unknown_meta,
)


@dataclass(frozen=True)
class PrimeMetaProjection:
    goal: dict[str, Any] | None
    compaction: dict[str, Any] | None
    unknown: UnknownMetaProjection


_EMPTY_UNKNOWN = project_unknown_meta(())
PRIME_META_NAMESPACE = "ai.primeintellect.prime-agent"


def parse_effective_settings(value: Any) -> dict[str, str | None]:
    unknown = {"provider": None, "model": None, "reasoning": None}
    if not isinstance(value, Mapping) or set(value) - unknown.keys():
        return unknown
    for key in unknown:
        text = value.get(key)
        if text is None:
            continue
        try:
            if type(text) is not str or not text or "\0" in text or len(text.encode("utf-8")) > 256:
                return dict.fromkeys(unknown)
        except UnicodeError:
            return dict.fromkeys(unknown)
        unknown[key] = text
    return unknown


def _effective_record(metadata: Any):
    envelope = metadata.get(PRIME_META_NAMESPACE) if isinstance(metadata, Mapping) else None
    if not isinstance(envelope, Mapping) or "effectiveSettings" not in envelope:
        return None
    sequence = envelope.get("eventSequence")
    if sequence is not None and (type(sequence) is not int or not 0 < sequence <= 2**53 - 1):
        return None
    return parse_effective_settings(envelope["effectiveSettings"]), sequence


@dataclass
class _ActivePrompt:
    generation: PromptGeneration
    projection: BoundedPromptProjection
    cancellation: asyncio.Event
    next_ordinal: int = 0
    permission_cancelled: bool = False


class RookChatAcpClient:
    """Immediate client callbacks; prompt orchestration remains outside callbacks."""

    def __init__(self) -> None:
        self._connection: Any | None = None
        self._launch_generation = 0
        self._session_id: str | None = None
        self._active: _ActivePrompt | None = None
        self.prime_meta = PrimeMetaProjection(None, None, _EMPTY_UNKNOWN)
        self.effective_settings = parse_effective_settings(None)
        self._settings_sequence = 0
        self._settings_pending = False
        self._pending_settings: list[tuple[str, Any]] = []
        self._pending_settings_overflow = False
        self._settings_retired = False

    def on_connect(self, connection: Any) -> None:
        self._connection = connection

    def reset_for_session(self, *, launch_generation: int, acp_session_id: str | None) -> None:
        self._launch_generation = launch_generation
        self._session_id = acp_session_id
        self._active = None
        self.prime_meta = PrimeMetaProjection(None, None, _EMPTY_UNKNOWN)
        self.effective_settings = parse_effective_settings(None)
        self._settings_sequence = 0
        self._settings_pending = False
        self._pending_settings.clear()
        self._pending_settings_overflow = False
        self._settings_retired = False

    def begin_session(self, launch_generation: int) -> None:
        self.reset_for_session(launch_generation=launch_generation, acp_session_id=None)
        self._settings_pending = True

    def complete_session(self, session_id: str, metadata: Any) -> None:
        if self._settings_retired:
            return
        # SDK notification tasks may run before the response await resumes. Replay only
        # bounded summaries for the returned session, after its older initial snapshot.
        pending, overflow = self._pending_settings[:], self._pending_settings_overflow
        self.reset_for_session(launch_generation=self._launch_generation, acp_session_id=session_id)
        record = _effective_record(metadata)
        if record is not None:
            self._apply_settings(record)
        for candidate, record in pending:
            if candidate == session_id:
                self._apply_settings(record)
        if overflow:
            self.effective_settings = parse_effective_settings(None)

    def retire_session_settings(self) -> None:
        self._settings_retired = True
        self._settings_pending = False
        self._pending_settings.clear()
        self.effective_settings = parse_effective_settings(None)

    def _apply_settings(self, record) -> bool:
        settings, sequence = record
        if sequence is not None and sequence <= self._settings_sequence:
            return False
        self.effective_settings = settings
        if sequence is not None:
            self._settings_sequence = sequence
        return True

    def activate_prompt(
        self,
        generation: PromptGeneration,
        projection: BoundedPromptProjection,
        cancellation: asyncio.Event,
    ) -> None:
        if generation.acp_session_id != self._session_id:
            if self._session_id is None:
                self.reset_for_session(
                    launch_generation=generation.launch_generation,
                    acp_session_id=generation.acp_session_id,
                )
            else:
                raise RuntimeError("prompt generation does not match the active ACP session")
        if generation.launch_generation != self._launch_generation:
            raise RuntimeError("prompt generation does not match the active launch")
        if self._active is not None:
            raise RuntimeError("an ACP prompt is already active")
        self._active = _ActivePrompt(generation, projection, cancellation)

    def clear_prompt(self, generation: PromptGeneration) -> None:
        if self._active is not None and self._active.generation == generation:
            self._active = None

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        metadata = getattr(update, "field_meta", None) or kwargs
        record = _effective_record(metadata)
        if self._settings_pending and not self._settings_retired and record is not None:
            if len(self._pending_settings) < 32 and type(session_id) is str and len(session_id) <= 256:
                self._pending_settings.append((session_id, record))
            else:
                self._pending_settings_overflow = True
            return
        matched = session_id == self._session_id and not self._settings_retired
        changed = matched and record is not None and self._apply_settings(record)
        active = self._active
        if active is None or session_id != self._session_id:
            return
        # This assignment is intentionally before the callback's first await.
        source_ordinal = active.next_ordinal
        active.next_ordinal += 1
        if isinstance(metadata, Mapping) and metadata:
            self.observe_prime_meta(metadata)
        await active.projection.accept_source_update(
            source_ordinal,
            update,
            generation=active.generation,
            **({"effective_settings": dict(self.effective_settings)} if changed else {}),
        )

    async def request_permission(
        self,
        session_id: str,
        tool_call: ToolCallUpdate,
        options: list[PermissionOption],
        **kwargs: Any,
    ) -> RequestPermissionResponse:
        del tool_call, kwargs
        active = self._active
        if active is None or session_id != self._session_id or active.permission_cancelled:
            return RequestPermissionResponse(outcome={"outcome": "cancelled"})

        identifiers = [option.option_id for option in options]
        valid_shape = all(
            isinstance(identifier, str)
            and bool(identifier.strip())
            and option.kind in {"allow_once", "allow_always", "reject_once", "reject_always"}
            for identifier, option in zip(identifiers, options, strict=True)
        )
        if valid_shape and len(set(identifiers)) == len(identifiers):
            selected = next((option for option in options if option.kind == "allow_once"), None)
            selected = selected or next((option for option in options if option.kind == "allow_always"), None)
            if selected is not None:
                return RequestPermissionResponse(
                    outcome={"outcome": "selected", "optionId": selected.option_id}
                )

        active.permission_cancelled = True
        active.cancellation.set()
        return RequestPermissionResponse(outcome={"outcome": "cancelled"})

    def observe_prime_meta(self, metadata: Mapping[str, Any]) -> None:
        goal = metadata.get("goal")
        compaction = metadata.get("compaction")
        known_goal = dict(goal) if isinstance(goal, Mapping) else self.prime_meta.goal
        known_compaction = dict(compaction) if isinstance(compaction, Mapping) else self.prime_meta.compaction
        unknown_records = [
            {key: value for key, value in metadata.items() if key not in {"goal", "compaction"}}
        ]
        unknown = project_unknown_meta(unknown_records) if unknown_records[0] else self.prime_meta.unknown
        self.prime_meta = PrimeMetaProjection(known_goal, known_compaction, unknown)
