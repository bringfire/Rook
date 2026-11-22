"""Lifecycle broker for the opt-in Prime-backed RookChat path."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .prime_process import (
    PrimeControlTimeout,
    PrimeProcessError,
    PrimeProcessLost,
    PrimeRpcProcess,
    PrimeRuntimeState,
    PrimeLaunchConfiguration,
    parse_runtime_state,
)
from .prime_registry import (
    LifecycleRecord,
    PrimeConversationRecord,
    PrimeConversationRecordUnion,
    PrimeConversationRecordV2,
    PrimeConversationRegistry,
    PrimeModelSelection,
    PrimeRuntimeContractRef,
    RuntimePreparation,
    TargetFingerprint,
    TargetFingerprintV2,
)
from .prime_runtime_contract import PrimeRuntimeContractOwner, RuntimeContractError
from .prime_rpc_protocol import (
    PrimeProtocolError,
    parse_ipython_runtime_preparation,
    parse_prompt_settlement,
    parse_rlm_max_depth_status,
    project_prime_event,
)


TERMINAL_ROW_TYPES = frozenset({"done", "cancelled", "error"})


class PrimeBackendError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        actual_model: PrimeModelSelection | None = None,
    ) -> None:
        super().__init__(message or code)
        self.code = code
        self.actual_model = actual_model


def admit_prime_panel_prompt(message: str) -> None:
    remaining = message.lstrip()
    if not remaining.startswith("/"):
        return
    token = remaining.split(maxsplit=1)[0]
    if token != "/goal":
        raise PrimeBackendError("prime_command_not_admitted")


@dataclass(frozen=True)
class PendingAbort:
    abort_request_id: str
    prompt_request_id: str
    launch_generation: int


class PrimeProcessLike(Protocol):
    generation: int

    async def start(self) -> PrimeRuntimeState: ...

    async def command(
        self,
        command: dict[str, Any],
        *,
        expected_command: str,
        timeout_seconds: float | None = 10.0,
    ) -> dict[str, Any]: ...

    def subscribe(
        self,
        listener: Callable[[int, dict[str, Any]], None],
    ) -> Callable[[], None]: ...

    async def retire(self, grace_seconds: float) -> None: ...


ProcessFactory = Callable[
    [int, PrimeModelSelection, str | None, PrimeLaunchConfiguration | None],
    PrimeProcessLike,
]


class PromptSubscriptionBuffer:
    MAX_ROWS = 128
    MAX_NONTERMINAL_ROWS = 127

    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []
        self._ready = asyncio.Event()
        self._terminal_published = False
        self._terminal_consumed = False
        self._closed = False

    def __len__(self) -> int:
        return len(self._rows)

    @property
    def rows(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(row) for row in self._rows)

    @property
    def terminal_count(self) -> int:
        return int(self._terminal_published)

    def publish(self, row: dict[str, Any]) -> None:
        if self._closed or self._terminal_published:
            return
        row_type = row.get("type")
        if row_type in TERMINAL_ROW_TYPES:
            if len(self._rows) > self.MAX_NONTERMINAL_ROWS:
                raise RuntimeError("subscription buffer violated its reserved terminal slot")
            self._rows.append(dict(row))
            self._terminal_published = True
            self._ready.set()
            return
        if row_type == "text_delta":
            content = row.get("content")
            if not isinstance(content, str) or not content:
                return
            if self._rows and self._rows[-1].get("type") == "text_delta":
                self._rows[-1]["content"] += content
                self._ready.set()
                return
            if len(self._rows) < self.MAX_NONTERMINAL_ROWS:
                self._rows.append({"type": "text_delta", "content": content})
                self._ready.set()
                return
            self._remove_status_rows()
            if len(self._rows) < self.MAX_NONTERMINAL_ROWS:
                self._rows.append({"type": "text_delta", "content": content})
            else:
                self._coalesce_all_text(content)
            self._ready.set()
            return
        if row_type == "status":
            if len(self._rows) < self.MAX_NONTERMINAL_ROWS:
                self._rows.append(dict(row))
                self._ready.set()
            return
        if row_type == "model_update":
            for index in range(len(self._rows) - 1, -1, -1):
                if self._rows[index].get("type") == "model_update":
                    self._rows[index] = dict(row)
                    self._ready.set()
                    return
            self._remove_status_rows()
            if len(self._rows) < self.MAX_NONTERMINAL_ROWS:
                self._rows.append(dict(row))
                self._ready.set()

    def _remove_status_rows(self) -> None:
        self._rows = [row for row in self._rows if row.get("type") != "status"]

    def _coalesce_all_text(self, new_content: str) -> None:
        text_indices = [
            index
            for index, row in enumerate(self._rows)
            if row.get("type") == "text_delta"
        ]
        if not text_indices:
            self._rows = [{"type": "text_delta", "content": new_content}]
            return
        first = text_indices[0]
        combined = "".join(
            str(row["content"])
            for row in self._rows
            if row.get("type") == "text_delta"
        ) + new_content
        self._rows = [
            row for row in self._rows if row.get("type") != "text_delta"
        ]
        self._rows.insert(first, {"type": "text_delta", "content": combined})

    async def next(self) -> dict[str, Any]:
        while True:
            if self._rows:
                row = self._rows.pop(0)
                if row.get("type") in TERMINAL_ROW_TYPES:
                    self._terminal_consumed = True
                return row
            if self._closed or (
                self._terminal_published and self._terminal_consumed
            ):
                raise StopAsyncIteration
            self._ready.clear()
            if self._rows or self._closed:
                continue
            await self._ready.wait()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._rows.clear()
        self._ready.set()


class PromptSubscription:
    def __init__(
        self,
        buffer: PromptSubscriptionBuffer,
        unregister: Callable[[], None],
    ) -> None:
        self.buffer = buffer
        self._unregister = unregister
        self._closed = False

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        return self

    async def __anext__(self) -> dict[str, Any]:
        return await self.buffer.next()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.buffer.close()
        self._unregister()


@dataclass
class ResidentPrimeConversation:
    process: PrimeProcessLike
    launch_generation: int
    pending_prompt_id: str | None
    pending_abort: PendingAbort | None
    last_activity_monotonic: float
    prompt_task: asyncio.Task[None] | None
    lifecycle_lock: asyncio.Lock
    subscriptions: set[PromptSubscriptionBuffer] = field(default_factory=set)
    unsubscribe_process: Callable[[], None] | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _lifecycle(state: str, reason: str | None = None) -> LifecycleRecord:
    return LifecycleRecord(
        state=state,
        reason=reason,
        updated_at_utc=_utc_now(),
    )


class PrimeChatBackend:
    MAX_RESIDENTS = 10
    IDLE_RETIRE_SECONDS = 1_800.0
    SHUTDOWN_TIMEOUT_SECONDS = 10.0

    def __init__(
        self,
        registry: PrimeConversationRegistry,
        process_factory: ProcessFactory,
        default_model: PrimeModelSelection,
        *,
        runtime_contract_owner: PrimeRuntimeContractOwner | None = None,
        max_residents: int = MAX_RESIDENTS,
        idle_retire_seconds: float = IDLE_RETIRE_SECONDS,
        retirement_grace_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.registry = registry
        self.process_factory = process_factory
        self.default_model = default_model
        self.runtime_contract_owner = runtime_contract_owner
        self.max_residents = max_residents
        self.idle_retire_seconds = idle_retire_seconds
        self.retirement_grace_seconds = retirement_grace_seconds
        self.clock = clock
        self._residents: dict[str, ResidentPrimeConversation] = {}
        self._generation = 0
        self._request_counter = 0
        self._residency_lock = asyncio.Lock()
        self._event_tasks: set[asyncio.Task[None]] = set()
        self._maintenance_task: asyncio.Task[None] | None = None
        self._shutdown = False
        self.registry.reconcile_interrupted_records()

    def pending_abort(self, conversation_id: str) -> PendingAbort | None:
        resident = self._residents.get(conversation_id)
        return resident.pending_abort if resident is not None else None

    async def create(
        self,
        conversation_id: str,
        target: TargetFingerprint | TargetFingerprintV2,
    ) -> PrimeConversationRecordUnion:
        async with self._residency_lock:
            self._require_available()
            if self.registry.exists(conversation_id):
                raise PrimeBackendError("conversation_exists")
            await self._ensure_capacity_locked()
            owner = self.runtime_contract_owner
            if owner is not None and not isinstance(target, TargetFingerprintV2):
                raise PrimeBackendError("runtime_contract_unavailable")
            try:
                resident, runtime = await self._launch_locked(
                    conversation_id,
                    self.default_model,
                    None,
                    target if isinstance(target, TargetFingerprintV2) else None,
                )
            except RuntimeContractError as error:
                raise PrimeBackendError(
                    "runtime_contract_unavailable", str(error)
                ) from error
            if owner is not None:
                assert isinstance(target, TargetFingerprintV2)
                pending = PrimeConversationRecordV2(
                    schema_version=2,
                    conversation_id=conversation_id,
                    prime_session_id=runtime.session_id,
                    prime_session_path=runtime.session_path,
                    model=PrimeModelSelection(
                        runtime.provider,
                        runtime.model_id,
                        runtime.thinking,
                    ),
                    runtime=PrimeRuntimeContractRef(
                        contract_fingerprint_sha256=owner.contract.fingerprint,
                        capability_profile=owner.contract.record[
                            "capabilityProfile"
                        ],
                        kernel_environment_path=str(
                            owner.contract.kernel_environment_path
                        ),
                        preparation=RuntimePreparation(
                            status="pending",
                            interpreter_path=None,
                            prepared_at_utc=None,
                        ),
                    ),
                    target=target,
                    last_lifecycle=_lifecycle("idle"),
                )
                try:
                    self.registry.write_new_v2(pending)
                    prepared = await self._prepare_first_use_runtime(
                        conversation_id,
                        resident,
                        owner,
                    )
                except BaseException as error:
                    if self.registry.exists(conversation_id):
                        try:
                            self.registry.mark_pending_runtime_unavailable(
                                conversation_id
                            )
                        except BaseException:
                            pass
                    self._detach_locked(conversation_id, resident)
                    await resident.process.retire(self.retirement_grace_seconds)
                    if isinstance(error, asyncio.CancelledError):
                        raise
                    raise PrimeBackendError(
                        "runtime_contract_unavailable", str(error)
                    ) from error
                self._start_maintenance()
                return prepared
            record = PrimeConversationRecord(
                schema_version=1,
                conversation_id=conversation_id,
                prime_session_id=runtime.session_id,
                prime_session_path=runtime.session_path,
                model=PrimeModelSelection(
                    runtime.provider,
                    runtime.model_id,
                    runtime.thinking,
                ),
                target=target,
                last_lifecycle=_lifecycle("idle"),
            )
            try:
                self.registry.write(record)
            except BaseException:
                self._detach_locked(conversation_id, resident)
                await resident.process.retire(self.retirement_grace_seconds)
                raise
            self._start_maintenance()
            return record

    async def reopen(
        self,
        conversation_id: str,
        target: TargetFingerprint | TargetFingerprintV2,
    ) -> PrimeConversationRecordUnion:
        async with self._residency_lock:
            self._require_available()
            if not self.registry.exists(conversation_id):
                raise PrimeBackendError("conversation_not_found")
            record = self.registry.load(conversation_id)
            if record.target != target:
                raise PrimeBackendError("target_mismatch")
            if record.last_lifecycle.state == "closed":
                raise PrimeBackendError("conversation_closed")
            if record.last_lifecycle.state not in {"idle", "failed"}:
                raise PrimeBackendError("conversation_not_reopenable")
            if not Path(record.prime_session_path).is_file():
                raise PrimeBackendError("session_missing")
            owner = self.runtime_contract_owner
            if isinstance(record, PrimeConversationRecordV2):
                if owner is None or not isinstance(target, TargetFingerprintV2):
                    raise PrimeBackendError("runtime_contract_unavailable")
                try:
                    self._verify_reopen_runtime(record, owner)
                except (RuntimeContractError, OSError) as error:
                    self._mark_runtime_failed(record)
                    raise PrimeBackendError(
                        "runtime_contract_unavailable", str(error)
                    ) from error
            existing = self._residents.get(conversation_id)
            if existing is not None:
                if record.last_lifecycle.state == "idle":
                    return record
                self._detach_locked(conversation_id, existing)
                await existing.process.retire(self.retirement_grace_seconds)
            await self._ensure_capacity_locked()
            resident, runtime = await self._launch_locked(
                conversation_id,
                record.model,
                record.prime_session_path,
                target if isinstance(target, TargetFingerprintV2) else None,
            )
            if (
                runtime.session_id != record.prime_session_id
                or os.path.normcase(os.path.abspath(runtime.session_path))
                != os.path.normcase(os.path.abspath(record.prime_session_path))
            ):
                self._detach_locked(conversation_id, resident)
                await resident.process.retire(self.retirement_grace_seconds)
                raise PrimeBackendError("session_identity_mismatch")
            if isinstance(record, PrimeConversationRecordV2):
                assert owner is not None
                try:
                    await self._verify_reopened_runtime(resident, record, owner)
                except BaseException as error:
                    self._detach_locked(conversation_id, resident)
                    await resident.process.retire(self.retirement_grace_seconds)
                    self._mark_runtime_failed(record)
                    if isinstance(error, asyncio.CancelledError):
                        raise
                    raise PrimeBackendError(
                        "runtime_contract_unavailable", str(error)
                    ) from error
            reopened = replace(
                record,
                model=PrimeModelSelection(
                    runtime.provider,
                    runtime.model_id,
                    runtime.thinking,
                ),
                last_lifecycle=_lifecycle("idle"),
            )
            try:
                self.registry.write(reopened)
            except BaseException:
                self._detach_locked(conversation_id, resident)
                await resident.process.retire(self.retirement_grace_seconds)
                raise
            self._start_maintenance()
            return reopened

    async def _launch_locked(
        self,
        conversation_id: str,
        model: PrimeModelSelection,
        resume_session_path: str | None,
        target: TargetFingerprintV2 | None,
    ) -> tuple[ResidentPrimeConversation, PrimeRuntimeState]:
        self._generation += 1
        launch_configuration = None
        if self.runtime_contract_owner is not None:
            if target is None:
                raise RuntimeContractError("v2 target is required for runtime launch")
            launch_configuration = self.runtime_contract_owner.launch_configuration(
                target
            )
        process = self.process_factory(
            self._generation,
            model,
            resume_session_path,
            launch_configuration,
        )
        resident = ResidentPrimeConversation(
            process=process,
            launch_generation=self._generation,
            pending_prompt_id=None,
            pending_abort=None,
            last_activity_monotonic=self.clock(),
            prompt_task=None,
            lifecycle_lock=asyncio.Lock(),
        )
        self._residents[conversation_id] = resident
        resident.unsubscribe_process = process.subscribe(
            lambda generation, event: self._schedule_process_event(
                conversation_id,
                resident,
                generation,
                event,
            )
        )
        try:
            runtime = await process.start()
        except BaseException:
            self._detach_locked(conversation_id, resident)
            await process.retire(self.retirement_grace_seconds)
            raise
        return resident, runtime

    async def _prepare_first_use_runtime(
        self,
        conversation_id: str,
        resident: ResidentPrimeConversation,
        owner: PrimeRuntimeContractOwner,
    ) -> PrimeConversationRecordV2:
        set_response = await resident.process.command(
            {"type": "set_rlm_max_depth", "maxDepth": 0, "global": False},
            expected_command="set_rlm_max_depth",
        )
        set_status = parse_rlm_max_depth_status(
            set_response,
            expected_command="set_rlm_max_depth",
        )
        if set_status.max_depth != 0 or set_status.source != "chat":
            raise PrimeProtocolError("Prime recursion depth was not locked to chat zero")
        get_response = await resident.process.command(
            {"type": "get_rlm_max_depth_status"},
            expected_command="get_rlm_max_depth_status",
        )
        get_status = parse_rlm_max_depth_status(
            get_response,
            expected_command="get_rlm_max_depth_status",
        )
        if get_status.max_depth != 0 or get_status.source != "chat":
            raise PrimeProtocolError("Prime recursion depth custody was not retained")
        prepare_response = await resident.process.command(
            {"type": "prepare_ipython_runtime"},
            expected_command="prepare_ipython_runtime",
        )
        prepared = parse_ipython_runtime_preparation(prepare_response)
        owner.verify_prepared_runtime(prepared)
        return self.registry.mark_runtime_prepared(
            conversation_id,
            prepared.interpreter_path,
            _utc_now(),
        )

    def _verify_reopen_runtime(
        self,
        record: PrimeConversationRecordV2,
        owner: PrimeRuntimeContractOwner,
    ) -> None:
        owner.verify()
        if (
            record.runtime.contract_fingerprint_sha256
            != owner.contract.fingerprint
            or record.runtime.capability_profile
            != owner.contract.record["capabilityProfile"]
            or Path(record.runtime.kernel_environment_path).resolve(strict=False)
            != owner.contract.kernel_environment_path.resolve(strict=False)
            or record.runtime.preparation.status != "prepared"
            or record.runtime.preparation.interpreter_path is None
        ):
            raise RuntimeContractError("recorded runtime contract is unavailable")
        environment = Path(record.runtime.kernel_environment_path)
        interpreter = Path(record.runtime.preparation.interpreter_path)
        if not environment.is_dir() or not interpreter.is_file():
            raise RuntimeContractError("prepared runtime environment is unavailable")

    async def _verify_reopened_runtime(
        self,
        resident: ResidentPrimeConversation,
        record: PrimeConversationRecordV2,
        owner: PrimeRuntimeContractOwner,
    ) -> None:
        depth_response = await resident.process.command(
            {"type": "get_rlm_max_depth_status"},
            expected_command="get_rlm_max_depth_status",
        )
        depth = parse_rlm_max_depth_status(
            depth_response,
            expected_command="get_rlm_max_depth_status",
        )
        if depth.max_depth != 0 or depth.source != "chat":
            raise RuntimeContractError("recorded recursion depth custody drifted")
        prepare_response = await resident.process.command(
            {"type": "prepare_ipython_runtime"},
            expected_command="prepare_ipython_runtime",
        )
        prepared = parse_ipython_runtime_preparation(prepare_response)
        owner.verify_prepared_runtime(
            prepared,
            expected_interpreter_path=record.runtime.preparation.interpreter_path,
        )

    def _mark_runtime_failed(self, record: PrimeConversationRecordV2) -> None:
        try:
            self.registry.write(
                replace(
                    record,
                    last_lifecycle=_lifecycle(
                        "failed", "runtime_contract_unavailable"
                    ),
                )
            )
        except BaseException:
            pass

    def _schedule_process_event(
        self,
        conversation_id: str,
        resident: ResidentPrimeConversation,
        generation: int,
        event: dict[str, Any],
    ) -> None:
        task = asyncio.create_task(
            self._publish_process_event(
                conversation_id,
                resident,
                generation,
                event,
            )
        )
        self._event_tasks.add(task)
        task.add_done_callback(self._event_tasks.discard)

    async def _publish_process_event(
        self,
        conversation_id: str,
        resident: ResidentPrimeConversation,
        generation: int,
        event: dict[str, Any],
    ) -> None:
        projected = project_prime_event(event)
        if projected is None:
            return
        async with resident.lifecycle_lock:
            if not self._is_current(conversation_id, resident, generation):
                return
            if self.registry.load(conversation_id).last_lifecycle.state == "closed":
                return
            for buffer in tuple(resident.subscriptions):
                buffer.publish(projected)

    async def start_prompt(
        self,
        conversation_id: str,
        message: str,
    ) -> PromptSubscription:
        admit_prime_panel_prompt(message)
        resident = self._require_resident(conversation_id)
        async with resident.lifecycle_lock:
            record = self.registry.load(conversation_id)
            if record.last_lifecycle.state == "failed":
                raise PrimeBackendError(
                    "explicit_reopen_required",
                    "failed conversation requires explicit reopen",
                )
            if record.last_lifecycle.state != "idle":
                raise PrimeBackendError("conversation_not_idle")
            self._request_counter += 1
            prompt_id = f"prompt-{resident.launch_generation}-{self._request_counter}"
            self.registry.write(
                replace(record, last_lifecycle=_lifecycle("running"))
            )
            buffer = PromptSubscriptionBuffer()
            resident.subscriptions.add(buffer)
            subscription = PromptSubscription(
                buffer,
                lambda: resident.subscriptions.discard(buffer),
            )
            resident.pending_prompt_id = prompt_id
            resident.pending_abort = None
            resident.last_activity_monotonic = self.clock()
            resident.prompt_task = asyncio.create_task(
                self._run_prompt(
                    conversation_id,
                    resident,
                    prompt_id,
                    message,
                )
            )
            return subscription

    async def _run_prompt(
        self,
        conversation_id: str,
        resident: ResidentPrimeConversation,
        prompt_id: str,
        message: str,
    ) -> None:
        settlement = None
        failure_code: str | None = None
        failure_message: str | None = None
        retire_after = False
        try:
            response = await resident.process.command(
                {
                    "id": prompt_id,
                    "type": "prompt_and_wait",
                    "message": message,
                    "images": [],
                },
                expected_command="prompt_and_wait",
                timeout_seconds=None,
            )
            # Process event callbacks are queued before the correlated response.
            # Yield once so their lock-checked projections precede the terminal row.
            await asyncio.sleep(0)
            settlement = parse_prompt_settlement(response)
            if settlement.error_code is not None:
                failure_code = settlement.error_code
                failure_message = settlement.error_message
                retire_after = True
        except PrimeProtocolError as error:
            failure_code = "protocol_failed"
            failure_message = str(error)
            retire_after = True
        except (PrimeProcessLost, PrimeProcessError) as error:
            failure_code = "settlement_unknown"
            failure_message = str(error)
            retire_after = True
        except Exception as error:
            failure_code = "settlement_unknown"
            failure_message = str(error)
            retire_after = True

        async with resident.lifecycle_lock:
            if not self._is_current(
                conversation_id,
                resident,
                resident.launch_generation,
            ):
                return
            record = self.registry.load(conversation_id)
            if record.last_lifecycle.state == "closed":
                return
            if resident.pending_prompt_id != prompt_id:
                return

            if failure_code is not None:
                updated = replace(
                    record,
                    last_lifecycle=_lifecycle("failed", failure_code),
                )
                terminal = {
                    "type": "error",
                    "code": failure_code,
                    "message": failure_message or failure_code,
                }
            else:
                assert settlement is not None and settlement.outcome is not None
                prior_state = record.last_lifecycle.state
                if settlement.outcome == "aborted":
                    reason = "aborted"
                    terminal = {"type": "cancelled", "reason": reason}
                elif prior_state == "cancel_requested":
                    reason = "completed_before_abort"
                    terminal = {"type": "done", "reason": reason}
                else:
                    reason = None
                    terminal = {"type": "done", "reason": "completed"}
                updated = replace(
                    record,
                    last_lifecycle=_lifecycle("idle", reason),
                )
            self.registry.write(updated)
            resident.pending_prompt_id = None
            resident.pending_abort = None
            resident.prompt_task = None
            resident.last_activity_monotonic = self.clock()
            for buffer in tuple(resident.subscriptions):
                buffer.publish(terminal)
            if retire_after:
                self._detach(conversation_id, resident)

        if retire_after:
            await resident.process.retire(self.retirement_grace_seconds)

    async def cancel(self, conversation_id: str) -> LifecycleRecord:
        resident = self._require_resident(conversation_id)
        async with resident.lifecycle_lock:
            record = self.registry.load(conversation_id)
            if record.last_lifecycle.state == "cancel_requested":
                return record.last_lifecycle
            if record.last_lifecycle.state != "running":
                raise PrimeBackendError("conversation_not_running")
            if resident.pending_prompt_id is None:
                raise PrimeBackendError("prompt_correlation_missing")
            self._request_counter += 1
            abort_id = f"abort-{resident.launch_generation}-{self._request_counter}"
            lifecycle = _lifecycle("cancel_requested")
            self.registry.write(replace(record, last_lifecycle=lifecycle))
            resident.pending_abort = PendingAbort(
                abort_request_id=abort_id,
                prompt_request_id=resident.pending_prompt_id,
                launch_generation=resident.launch_generation,
            )

        try:
            await resident.process.command(
                {"id": abort_id, "type": "abort"},
                expected_command="abort",
            )
        except Exception:
            await resident.process.retire(self.retirement_grace_seconds)
            if resident.prompt_task is not None:
                await asyncio.gather(resident.prompt_task, return_exceptions=True)
        return self.registry.load(conversation_id).last_lifecycle

    async def models(self, conversation_id: str) -> list[dict[str, Any]]:
        resident = self._require_resident(conversation_id)
        response = await resident.process.command(
            {"type": "get_available_models"},
            expected_command="get_available_models",
        )
        if response.get("success") is not True:
            raise PrimeBackendError("models_failed")
        data = response.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("models"), list):
            raise PrimeBackendError("models_protocol_failed")
        projected = []
        for model in data["models"]:
            if not isinstance(model, dict):
                continue
            provider = model.get("provider")
            model_id = model.get("id")
            if not isinstance(provider, str) or not isinstance(model_id, str):
                continue
            projected.append(
                {
                    "id": f"{provider}/{model_id}",
                    "provider": provider,
                    "model": model_id,
                    "contextWindow": model.get("contextWindow"),
                    "reasoning": model.get("reasoning"),
                }
            )
        resident.last_activity_monotonic = self.clock()
        return projected

    async def set_model(
        self,
        conversation_id: str,
        provider: str,
        model_id: str,
        thinking: str | None,
    ) -> PrimeModelSelection:
        resident = self._require_resident(conversation_id)
        mutation_error: Exception | None = None
        readback_error: Exception | None = None
        actual: PrimeModelSelection | None = None
        async with resident.lifecycle_lock:
            record = self.registry.load(conversation_id)
            if record.last_lifecycle.state != "idle":
                raise PrimeBackendError("conversation_not_idle")
            try:
                response = await resident.process.command(
                    {
                        "type": "set_model",
                        "provider": provider,
                        "modelId": model_id,
                    },
                    expected_command="set_model",
                )
                if response.get("success") is not True:
                    raise PrimeBackendError("set_model_failed")
                if thinking is not None:
                    response = await resident.process.command(
                        {"type": "set_thinking_level", "level": thinking},
                        expected_command="set_thinking_level",
                    )
                    if response.get("success") is not True:
                        raise PrimeBackendError("set_thinking_level_failed")
            except Exception as error:
                mutation_error = error
            try:
                state_response = await resident.process.command(
                    {"type": "get_state"},
                    expected_command="get_state",
                )
                runtime = parse_runtime_state(state_response)
                actual = PrimeModelSelection(
                    runtime.provider,
                    runtime.model_id,
                    runtime.thinking,
                )
            except Exception as error:
                readback_error = error

            if readback_error is not None or actual is None:
                self.registry.write(
                    replace(
                        record,
                        last_lifecycle=_lifecycle(
                            "failed", "model_reconciliation_failed"
                        ),
                    )
                )
                self._detach(conversation_id, resident)
            else:
                reason = (
                    "model_update_failed_reconciled"
                    if mutation_error is not None
                    else None
                )
                self.registry.write(
                    replace(
                        record,
                        model=actual,
                        last_lifecycle=_lifecycle("idle", reason),
                    )
                )
                resident.last_activity_monotonic = self.clock()

        if readback_error is not None or actual is None:
            await resident.process.retire(self.retirement_grace_seconds)
            raise PrimeBackendError(
                "model_reconciliation_failed",
                "model_reconciliation_failed",
            ) from readback_error
        if mutation_error is not None:
            raise PrimeBackendError(
                "model_update_failed_reconciled",
                "model update failed and actual runtime state was reconciled",
                actual_model=actual,
            ) from mutation_error
        return actual

    async def close(self, conversation_id: str) -> LifecycleRecord:
        if not self.registry.exists(conversation_id):
            raise PrimeBackendError("conversation_not_found")
        resident = self._residents.get(conversation_id)
        record = self.registry.load(conversation_id)
        if record.last_lifecycle.state == "closed":
            return record.last_lifecycle
        lifecycle = _lifecycle("closed", "user_closed")
        if resident is None:
            self.registry.write(replace(record, last_lifecycle=lifecycle))
            return lifecycle

        was_active = record.last_lifecycle.state in {"running", "cancel_requested"}
        async with resident.lifecycle_lock:
            record = self.registry.load(conversation_id)
            if record.last_lifecycle.state == "closed":
                return record.last_lifecycle
            self.registry.write(replace(record, last_lifecycle=lifecycle))
            self._detach(conversation_id, resident)
            for buffer in tuple(resident.subscriptions):
                buffer.close()
            resident.subscriptions.clear()

        if was_active:
            try:
                self._request_counter += 1
                await resident.process.command(
                    {
                        "id": f"abort-{resident.launch_generation}-{self._request_counter}",
                        "type": "abort",
                    },
                    expected_command="abort",
                )
            except Exception:
                pass
        await resident.process.retire(self.retirement_grace_seconds)
        if resident.prompt_task is not None:
            await asyncio.gather(resident.prompt_task, return_exceptions=True)
        return lifecycle

    async def retire_document(self, target: TargetFingerprint) -> None:
        conversation_ids = [
            conversation_id
            for conversation_id in self.registry.conversation_ids()
            if self.registry.load(conversation_id).target == target
        ]
        for conversation_id in conversation_ids:
            await self.close(conversation_id)

    async def retire_idle(self) -> None:
        now = self.clock()
        retired: list[ResidentPrimeConversation] = []
        async with self._residency_lock:
            for conversation_id, resident in tuple(self._residents.items()):
                record = self.registry.load(conversation_id)
                if (
                    record.last_lifecycle.state == "idle"
                    and now - resident.last_activity_monotonic
                    >= self.idle_retire_seconds
                ):
                    self._detach_locked(conversation_id, resident)
                    retired.append(resident)
        for resident in retired:
            await resident.process.retire(self.retirement_grace_seconds)

    async def _ensure_capacity_locked(self) -> None:
        if len(self._residents) < self.max_residents:
            return
        candidates = [
            (resident.last_activity_monotonic, conversation_id, resident)
            for conversation_id, resident in self._residents.items()
            if self.registry.load(conversation_id).last_lifecycle.state == "idle"
        ]
        if not candidates:
            raise PrimeBackendError("capacity_exhausted")
        _activity, conversation_id, resident = min(candidates, key=lambda row: row[0])
        self._detach_locked(conversation_id, resident)
        await resident.process.retire(self.retirement_grace_seconds)

    def _require_resident(self, conversation_id: str) -> ResidentPrimeConversation:
        if not self.registry.exists(conversation_id):
            raise PrimeBackendError("conversation_not_found")
        record = self.registry.load(conversation_id)
        if record.last_lifecycle.state == "failed":
            raise PrimeBackendError(
                "explicit_reopen_required",
                "failed conversation requires explicit reopen",
            )
        if record.last_lifecycle.state == "closed":
            raise PrimeBackendError("conversation_closed")
        resident = self._residents.get(conversation_id)
        if resident is None:
            raise PrimeBackendError("explicit_reopen_required")
        return resident

    def _is_current(
        self,
        conversation_id: str,
        resident: ResidentPrimeConversation,
        generation: int,
    ) -> bool:
        return (
            self._residents.get(conversation_id) is resident
            and resident.launch_generation == generation
        )

    def _detach(
        self,
        conversation_id: str,
        resident: ResidentPrimeConversation,
    ) -> None:
        if self._residents.get(conversation_id) is resident:
            self._residents.pop(conversation_id, None)
        if resident.unsubscribe_process is not None:
            resident.unsubscribe_process()
            resident.unsubscribe_process = None

    def _detach_locked(
        self,
        conversation_id: str,
        resident: ResidentPrimeConversation,
    ) -> None:
        self._detach(conversation_id, resident)

    def _require_available(self) -> None:
        if self._shutdown:
            raise PrimeBackendError("backend_shutdown")

    def _start_maintenance(self) -> None:
        if self._maintenance_task is None:
            self._maintenance_task = asyncio.create_task(self._maintenance_loop())

    async def _maintenance_loop(self) -> None:
        interval = max(1.0, min(60.0, self.idle_retire_seconds / 2))
        try:
            while not self._shutdown:
                await asyncio.sleep(interval)
                await self.retire_idle()
        except asyncio.CancelledError:
            return

    async def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        deadline = (
            asyncio.get_running_loop().time() + self.SHUTDOWN_TIMEOUT_SECONDS
        )
        if self._maintenance_task is not None:
            self._maintenance_task.cancel()
            await asyncio.gather(self._maintenance_task, return_exceptions=True)
            self._maintenance_task = None

        active_cancellations = []
        for conversation_id in tuple(self._residents):
            state = self.registry.load(conversation_id).last_lifecycle.state
            if state == "running":
                active_cancellations.append(
                    asyncio.create_task(self.cancel(conversation_id))
                )
        if active_cancellations:
            remaining = max(0.0, deadline - asyncio.get_running_loop().time())
            try:
                await asyncio.wait_for(
                    asyncio.gather(*active_cancellations, return_exceptions=True),
                    timeout=max(0.001, remaining),
                )
            except asyncio.TimeoutError:
                for task in active_cancellations:
                    task.cancel()

        prompt_tasks = [
            resident.prompt_task
            for resident in self._residents.values()
            if resident.prompt_task is not None
        ]
        if prompt_tasks:
            remaining = max(0.0, deadline - asyncio.get_running_loop().time())
            done, _pending = await asyncio.wait(prompt_tasks, timeout=remaining)
            for task in done:
                task.exception()

        residents = list(self._residents.items())
        self._residents.clear()
        for conversation_id, resident in residents:
            record = self.registry.load(conversation_id)
            if record.last_lifecycle.state in {"running", "cancel_requested"}:
                self.registry.write(
                    replace(
                        record,
                        last_lifecycle=_lifecycle(
                            "failed", "broker_shutdown_interrupted"
                        ),
                    )
                )
            if resident.unsubscribe_process is not None:
                resident.unsubscribe_process()
                resident.unsubscribe_process = None
            for buffer in tuple(resident.subscriptions):
                buffer.close()
            resident.subscriptions.clear()
        for _conversation_id, resident in residents:
            remaining = max(0.0, deadline - asyncio.get_running_loop().time())
            await resident.process.retire(remaining)

        for task in tuple(self._event_tasks):
            task.cancel()
        if self._event_tasks:
            await asyncio.gather(*self._event_tasks, return_exceptions=True)
        self._event_tasks.clear()
