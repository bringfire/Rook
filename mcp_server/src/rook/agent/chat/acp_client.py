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

    def on_connect(self, connection: Any) -> None:
        self._connection = connection

    def reset_for_session(self, *, launch_generation: int, acp_session_id: str) -> None:
        self._launch_generation = launch_generation
        self._session_id = acp_session_id
        self._active = None
        self.prime_meta = PrimeMetaProjection(None, None, _EMPTY_UNKNOWN)

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
        active = self._active
        if active is None or session_id != self._session_id:
            return
        # This assignment is intentionally before the callback's first await.
        source_ordinal = active.next_ordinal
        active.next_ordinal += 1
        metadata = kwargs or getattr(update, "field_meta", None)
        if isinstance(metadata, Mapping) and metadata:
            self.observe_prime_meta(metadata)
        await active.projection.accept_source_update(
            source_ordinal,
            update,
            generation=active.generation,
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
