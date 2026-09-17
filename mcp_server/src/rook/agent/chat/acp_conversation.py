"""Compose durable ACP associations with one optional directly owned process."""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, Protocol

from acp.schema import ImageContentBlock, TextContentBlock

from .acp_images import ValidatedImage
from .acp_presentation import (
    BoundedPromptProjection,
    PresentationCache,
    PresentationQueue,
    PresentationSink,
    ProjectedEvent,
    PromptGeneration,
    map_stop_reason,
)
from .acp_process import OwnedAcpProcess, PrimeLaunch
from .configuration_storage import ConfigurationStorageRefused, admit_configuration_storage
from .acp_storage import (
    AssociationStore,
    ConversationAssociation,
    OpenClaim,
    ProvisionalAssociation,
    RookBinding,
    SessionRecoveryRequired,
    WorkingDirectoryUnavailable,
    validate_prime_session_header,
)
from .prime_runtime import (
    PrimeRuntimeContract,
    RuntimeCatalog,
    build_prime_argv,
    build_prime_child_env,
    build_configuration_env,
    supports_configuration,
    build_rook_mcp_server,
)


PROMPT_SETTLEMENT_AFTER_CANCEL_SECONDS = 10.0
PRESENTATION_DRAIN_SECONDS = 5.0


class ConversationError(RuntimeError):
    code = "conversation_error"

    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        super().__init__(f"{self.code}: {conversation_id}")


class ConversationNotOpen(ConversationError):
    code = "conversation_not_open"


class ConversationBusy(ConversationError):
    code = "conversation_busy"


class TargetUnavailable(RuntimeError):
    code = "target_unavailable"

    def __init__(self) -> None:
        super().__init__(self.code)


class ImageUnsupported(RuntimeError):
    code = "image_unsupported"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True)
class PromptInput:
    text: str
    images: tuple[ValidatedImage, ...]


@dataclass(frozen=True)
class PromptResult:
    outcome: Literal["settled", "cancelled", "incomplete", "refused", "error"]
    stop_reason: str | None
    presentation_outcome: Literal["delivered", "stream_failed", "disconnected"]
    cache_published: bool


@dataclass(frozen=True)
class CreateConversationRequest:
    binding: RookBinding
    saved_document_directory: str | None
    requested_initial_model: str | None
    requested_initial_reasoning: str | None


@dataclass(frozen=True)
class ConversationView:
    conversation_id: str
    durable: bool
    target_available: bool
    effective_settings: dict[str, str | None] | None = None


@dataclass(frozen=True)
class CloseResult:
    outcome: Literal["clean", "unclean", "interrupted"]
    child_exit_observed: bool


@dataclass(frozen=True)
class DeleteResult:
    association_removed: bool
    artifacts_removed: bool


@dataclass
class ActivePromptSupervisor:
    generation: PromptGeneration
    cancel_signal: asyncio.Event = field(default_factory=asyncio.Event)
    _result_task: asyncio.Task[PromptResult] | None = field(init=False, default=None)
    _cancel_requested: bool = False

    @property
    def result_task(self) -> asyncio.Future[PromptResult]:
        if self._result_task is None:
            raise RuntimeError("prompt supervisor has not started")
        return asyncio.shield(self._result_task)

    def start(self, coroutine) -> None:
        if self._result_task is not None:
            raise RuntimeError("prompt supervisor already started")
        self._result_task = asyncio.create_task(coroutine)

    def request_cancel(self, source: str) -> bool:
        del source
        if self._cancel_requested:
            return False
        self._cancel_requested = True
        self.cancel_signal.set()
        return True


@dataclass
class ResidentConversation:
    association: ProvisionalAssociation | ConversationAssociation
    contract: PrimeRuntimeContract
    claim: OpenClaim
    process: OwnedAcpProcess
    launch_generation: int
    active_prompt: ActivePromptSupervisor | None = None
    transport_watch: asyncio.Task[None] | None = field(default=None, repr=False)
    retirement_task: asyncio.Task[CloseResult] | None = field(default=None, repr=False)
    deletion_task: asyncio.Task[DeleteResult] | None = field(default=None, repr=False)
    _prompt_sequence: int = 0

    @property
    def durable(self) -> bool:
        return isinstance(self.association, ConversationAssociation)

    def next_prompt_generation(self) -> PromptGeneration:
        if self.process.session_id is None:
            raise ConversationNotOpen(self.association.conversation_id)
        self._prompt_sequence += 1
        return PromptGeneration(
            launch_generation=self.launch_generation,
            acp_session_id=self.process.session_id,
            prompt_id=f"prompt-{self._prompt_sequence}",
        )


class PreparedAcpProcessLaunch(Protocol):
    async def start(
        self,
        claim: OpenClaim,
        *,
        launch_generation: int,
    ) -> OwnedAcpProcess: ...


class AcpProcessFactory(Protocol):
    def prepare(
        self,
        contract: PrimeRuntimeContract,
        association: ProvisionalAssociation | ConversationAssociation,
        reopen: bool,
    ) -> PreparedAcpProcessLaunch: ...


@dataclass(frozen=True)
class PreparedDirectAcpLaunch:
    launch: PrimeLaunch
    configuration_directory: Path | None = None

    async def start(
        self,
        claim: OpenClaim,
        *,
        launch_generation: int,
    ) -> OwnedAcpProcess:
        if self.configuration_directory is not None:
            try:
                admit_configuration_storage(self.configuration_directory)
            except ConfigurationStorageRefused:
                claim.release_no_child_created()
                raise
        return await OwnedAcpProcess.start(
            self.launch,
            claim,
            launch_generation=launch_generation,
        )


class DirectAcpProcessFactory:
    def __init__(self, base_environment: Mapping[str, str]) -> None:
        self._base_environment = dict(base_environment)

    def prepare(
        self,
        contract: PrimeRuntimeContract,
        association: ProvisionalAssociation | ConversationAssociation,
        reopen: bool,
    ) -> PreparedDirectAcpLaunch:
        argv = build_prime_argv(
            contract,
            Path(association.session_path),
            None if reopen else association.requested_initial_model,
            None if reopen else association.requested_initial_reasoning,
            reopen,
        )
        # The service injects this canonical root; neither cwd nor session paths own configuration.
        environment = (build_configuration_env(self._base_environment, contract,
                       Path(self._base_environment["ROOK_DATA_DIR"]))
                       if supports_configuration(contract)
                       else build_prime_child_env(self._base_environment, contract))
        return PreparedDirectAcpLaunch(
            PrimeLaunch(argv=argv, environment=environment, cwd=Path(association.working_directory)),
            Path(environment["PRIME_AGENT_CODING_AGENT_DIR"]) if supports_configuration(contract) else None,
        )


class AcpConversationManager:
    def __init__(
        self,
        store: AssociationStore,
        runtime_catalog: RuntimeCatalog,
        process_factory: AcpProcessFactory,
        cache: PresentationCache,
        *,
        target_available: Callable[[RookBinding], bool] | None = None,
    ) -> None:
        self.store = store
        self._runtime_catalog = runtime_catalog
        self._process_factory = process_factory
        self._cache_root = cache.root
        self._target_available = target_available or (lambda _binding: True)
        self._resident: dict[str, ResidentConversation] = {}
        self._launch_generation = itertools.count(1)
        self._admission_lock = asyncio.Lock()

    async def create(self, request: CreateConversationRequest) -> ConversationView:
        if not self._binding_available(request.binding):
            raise TargetUnavailable()
        contract = self._runtime_catalog.latest()
        working_directory = self._saved_working_directory(request.saved_document_directory)
        if working_directory is None:
            seed = self.store.reserve_provisional(
                binding=request.binding,
                runtime_id=contract.runtime_id,
                working_directory=self.store.paths.workspaces_root,
                requested_model=request.requested_initial_model,
                requested_reasoning=request.requested_initial_reasoning,
            )
            workspace = self.store.paths.workspace_path(seed.conversation_id)
            workspace.mkdir(parents=False, exist_ok=False)
            provisional = replace(seed, working_directory=str(workspace.resolve()))
        else:
            provisional = self.store.reserve_provisional(
                binding=request.binding,
                runtime_id=contract.runtime_id,
                working_directory=working_directory,
                requested_model=request.requested_initial_model,
                requested_reasoning=request.requested_initial_reasoning,
            )
        prepared = self._process_factory.prepare(contract, provisional, False)
        claim = OpenClaim.acquire(self.store.paths.claims_root, provisional.session_path)
        generation = next(self._launch_generation)
        process = await self._launch_process(prepared, contract, provisional, claim, generation)
        resident = ResidentConversation(provisional, contract, claim, process, generation)
        await self._publish_resident(resident)
        return self._view(resident)

    async def reopen(self, conversation_id: str) -> ConversationView:
        session_path = self.store.locate_session(conversation_id)
        claim = OpenClaim.acquire(self.store.paths.claims_root, session_path)
        try:
            association = self.store.get(conversation_id)
            working_directory = self._required_working_directory(association.working_directory)
            contract = self._runtime_catalog.get(association.runtime_id)
            validate_prime_session_header(
                Path(association.session_path),
                expected_id=association.prime_session_id,
                expected_cwd=working_directory,
                sessions_root=self.store.paths.sessions_root,
            )
            prepared = self._process_factory.prepare(contract, association, True)
        except Exception:
            claim.release_no_child_created()
            raise
        generation = next(self._launch_generation)
        process = await self._launch_process(prepared, contract, association, claim, generation)
        resident = ResidentConversation(association, contract, claim, process, generation)
        await self._publish_resident(resident)
        return self._view(resident)

    async def _publish_resident(self, resident: ResidentConversation) -> None:
        try:
            await self._insert_resident(resident)
        except BaseException:
            cleanup = asyncio.create_task(self._discard_unpublished_resident(resident))
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.shield(cleanup)
            raise

    async def _insert_resident(self, resident: ResidentConversation) -> None:
        async with self._admission_lock:
            self._resident[resident.association.conversation_id] = resident
            resident.transport_watch = asyncio.create_task(self._watch_transport_failure(resident))

    async def _discard_unpublished_resident(self, resident: ResidentConversation) -> None:
        async with self._admission_lock:
            current = self._resident.get(resident.association.conversation_id)
            if current is resident:
                self._resident.pop(resident.association.conversation_id)
        await self._stop_transport_watch(resident)
        await resident.process.retire(send_close=True)

    async def _watch_transport_failure(self, resident: ResidentConversation) -> None:
        try:
            await resident.process.transport_failure.wait()
            await self._retire_if_current(resident, send_close=False)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            if resident.transport_watch is asyncio.current_task():
                resident.transport_watch = None

    @staticmethod
    async def _stop_transport_watch(resident: ResidentConversation) -> None:
        watch = resident.transport_watch
        if watch is None or watch is asyncio.current_task():
            return
        resident.transport_watch = None
        watch.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await watch

    async def _launch_process(
        self,
        prepared: PreparedAcpProcessLaunch,
        contract: PrimeRuntimeContract,
        association: ProvisionalAssociation | ConversationAssociation,
        claim: OpenClaim,
        generation: int,
    ) -> OwnedAcpProcess:
        process = await prepared.start(
            claim,
            launch_generation=generation,
        )
        try:
            await process.initialize()
            await process.new_session(
                cwd=association.working_directory,
                mcp_servers=[build_rook_mcp_server(association.binding)],
            )
            return process
        except BaseException:
            cleanup = asyncio.create_task(process.retire(send_close=False))
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.shield(cleanup)
            raise

    async def start_prompt(
        self,
        conversation_id: str,
        prompt: PromptInput,
        sink: PresentationSink,
    ) -> ActivePromptSupervisor:
        async with self._admission_lock:
            resident = self._resident.get(conversation_id)
            if resident is None:
                raise ConversationNotOpen(conversation_id)
            if resident.active_prompt is not None:
                raise ConversationBusy(conversation_id)
            if prompt.images and not resident.process.image_supported:
                raise ImageUnsupported()
            supervisor = ActivePromptSupervisor(generation=resident.next_prompt_generation())
            resident.active_prompt = supervisor
            supervisor.start(
                self._run_supervised_prompt(resident, supervisor, prompt, sink)
            )
            return supervisor

    async def _run_supervised_prompt(
        self,
        resident: ResidentConversation,
        supervisor: ActivePromptSupervisor,
        prompt: PromptInput,
        sink: PresentationSink,
    ) -> PromptResult:
        try:
            return await self._run_prompt(resident, supervisor, prompt, sink)
        finally:
            async with self._admission_lock:
                if resident.active_prompt is supervisor:
                    resident.active_prompt = None

    async def _run_prompt(
        self,
        resident: ResidentConversation,
        supervisor: ActivePromptSupervisor,
        prompt: PromptInput,
        sink: PresentationSink,
    ) -> PromptResult:
        queue = PresentationQueue()
        projection = BoundedPromptProjection(
            generation=supervisor.generation,
            queue=queue,
            user_text=prompt.text,
        )
        presentation_failed = asyncio.Event()
        consumer = asyncio.create_task(self._consume_projection(queue, sink, presentation_failed))
        await queue.admit(ProjectedEvent(-1, "session_status", None, None, None,
                                        dict(resident.process.client.effective_settings)))
        blocks: list[TextContentBlock | ImageContentBlock] = [TextContentBlock(type="text", text=prompt.text)]
        blocks.extend(image.acp_block for image in prompt.images)
        prompt_task = asyncio.create_task(
            resident.process.prompt(blocks, generation=supervisor.generation, projection=projection)
        )
        cancel_wait = asyncio.create_task(supervisor.cancel_signal.wait())
        overflow_wait = asyncio.create_task(projection.overflow_signal.wait())
        presentation_failure_wait = asyncio.create_task(presentation_failed.wait())
        response = None
        error = False
        uncertain = False
        try:
            done, _ = await asyncio.wait(
                {prompt_task, cancel_wait, overflow_wait, presentation_failure_wait},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if prompt_task not in done:
                await resident.process.cancel()
                try:
                    response = await asyncio.wait_for(
                        asyncio.shield(prompt_task), timeout=PROMPT_SETTLEMENT_AFTER_CANCEL_SECONDS
                    )
                except asyncio.TimeoutError:
                    uncertain = True
            else:
                response = await prompt_task
        except Exception:
            error = True
            uncertain = True
        finally:
            for waiter in (cancel_wait, overflow_wait, presentation_failure_wait):
                waiter.cancel()
            await asyncio.gather(
                cancel_wait,
                overflow_wait,
                presentation_failure_wait,
                return_exceptions=True,
            )
            projection.close_producer()
            try:
                await asyncio.wait_for(consumer, timeout=PRESENTATION_DRAIN_SECONDS)
            except Exception:
                consumer.cancel()
                try:
                    await consumer
                except asyncio.CancelledError:
                    pass
                presentation_failed.set()

        if uncertain:
            resident.process.transport_failure.set()
            prompt_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await prompt_task
            await self._retire_if_current(resident, send_close=False)
            error = True
        stop_reason = None if response is None else response.stop_reason
        outcome = "error" if error else map_stop_reason(stop_reason or "")

        association_published = resident.durable
        if not resident.durable and not uncertain:
            try:
                header = validate_prime_session_header(
                    Path(resident.association.session_path),
                    expected_id=None,
                    expected_cwd=Path(resident.association.working_directory),
                    sessions_root=self.store.paths.sessions_root,
                )
                published = self.store.publish(resident.association, header)
                resident.association = published
                association_published = True
            except Exception:
                outcome = "error"
                await self._retire_if_current(resident, send_close=True)

        projection_value = projection.finalize(
            stop_reason or "error",
            image_metadata=(image.cache_metadata() for image in prompt.images),
        )
        cache_published = False
        if association_published:
            cache = self._cache_for(resident.association.conversation_id)
            try:
                cache.publish(projection_value)
                cache_published = True
            except Exception:
                try:
                    cache.publish_fallback(
                        stop_reason=stop_reason or "error",
                        original_byte_counts={
                            "user": projection_value.user_original_bytes,
                            "assistant": projection_value.assistant_original_bytes,
                        },
                    )
                    cache_published = True
                except Exception:
                    pass

        try:
            drained = await asyncio.wait_for(
                sink.drain(PRESENTATION_DRAIN_SECONDS),
                timeout=PRESENTATION_DRAIN_SECONDS,
            )
        except Exception:
            drained = False
        presentation_outcome = "delivered" if drained and not presentation_failed.is_set() else "stream_failed"
        return PromptResult(outcome, stop_reason, presentation_outcome, cache_published)

    @staticmethod
    async def _consume_projection(
        queue: PresentationQueue,
        sink: PresentationSink,
        failed: asyncio.Event,
    ) -> None:
        sink_available = True
        while True:
            event = await queue.get()
            if event is None:
                return
            if not sink_available:
                continue
            try:
                await sink.write(event)
            except Exception:
                failed.set()
                sink_available = False

    async def request_cancel(self, conversation_id: str, source: str) -> bool:
        async with self._admission_lock:
            resident = self._resident.get(conversation_id)
            supervisor = None if resident is None else resident.active_prompt
        return False if supervisor is None else supervisor.request_cancel(source)

    async def detach_resident_for_retirement(self, conversation_id: str) -> ResidentConversation:
        async with self._admission_lock:
            resident = self._resident.pop(conversation_id, None)
            if resident is None:
                raise ConversationNotOpen(conversation_id)
        await self._stop_transport_watch(resident)
        return resident

    async def close(self, conversation_id: str) -> CloseResult:
        resident = await self.detach_resident_for_retirement(conversation_id)
        return await self._retire_detached(resident)

    async def _retire_detached(
        self,
        resident: ResidentConversation,
        *,
        release_claim: bool = True,
    ) -> CloseResult:
        if resident.retirement_task is None:
            resident.retirement_task = asyncio.create_task(
                self._retire_detached_once(resident, release_claim=release_claim)
            )
        return await asyncio.shield(resident.retirement_task)

    async def _retire_detached_once(
        self,
        resident: ResidentConversation,
        *,
        release_claim: bool,
    ) -> CloseResult:
        supervisor = resident.active_prompt
        allow_session_close = not resident.process.transport_failure.is_set()
        if supervisor is not None:
            supervisor.request_cancel("retirement")
            try:
                await asyncio.wait_for(
                    supervisor.result_task,
                    timeout=PROMPT_SETTLEMENT_AFTER_CANCEL_SECONDS,
                )
            except asyncio.TimeoutError:
                result = await resident.process.retire(
                    send_close=False,
                    release_claim=release_claim,
                )
                return CloseResult("interrupted", result.child_exit_observed)
            except Exception:
                allow_session_close = False
            else:
                allow_session_close = allow_session_close and not resident.process.transport_failure.is_set()
        result = await resident.process.retire(
            send_close=allow_session_close,
            release_claim=release_claim,
        )
        return CloseResult("clean" if result.clean else "unclean", result.child_exit_observed)

    async def _retire_if_current(self, resident: ResidentConversation, *, send_close: bool) -> None:
        async with self._admission_lock:
            current = self._resident.get(resident.association.conversation_id)
            if current is not resident:
                return
            self._resident.pop(resident.association.conversation_id)
        await self._stop_transport_watch(resident)
        await resident.process.retire(send_close=send_close)

    async def delete(self, conversation_id: str) -> DeleteResult:
        async with self._admission_lock:
            live = conversation_id in self._resident
        if live:
            resident = await self.detach_resident_for_retirement(conversation_id)
            if resident.deletion_task is None:
                resident.deletion_task = asyncio.create_task(self._delete_live_resident(resident))
            return await asyncio.shield(resident.deletion_task)
        else:
            session_path = self.store.locate_session(conversation_id)
            claim = OpenClaim.acquire(self.store.paths.claims_root, session_path)
            try:
                association = self.store.get(conversation_id)
                working_directory = self._required_working_directory(association.working_directory)
                self._runtime_catalog.get(association.runtime_id)
                validate_prime_session_header(
                    Path(association.session_path),
                    expected_id=association.prime_session_id,
                    expected_cwd=working_directory,
                    sessions_root=self.store.paths.sessions_root,
                )
            except Exception:
                claim.release_no_child_created()
                raise
            release_claim = claim.release_no_child_created

        return self._delete_owned_association(association, release_claim)

    async def _delete_live_resident(self, resident: ResidentConversation) -> DeleteResult:
        close_result = await self._retire_detached(resident, release_claim=False)
        if not close_result.child_exit_observed:
            raise SessionRecoveryRequired()
        return self._delete_owned_association(
            resident.association,
            resident.claim.release_after_observed_exit,
        )

    def _delete_owned_association(
        self,
        association: ProvisionalAssociation | ConversationAssociation,
        release_claim: Callable[[], None],
    ) -> DeleteResult:
        association_removed = False
        artifacts_removed = False
        try:
            if isinstance(association, ConversationAssociation):
                self.store.delete_record(association)
                association_removed = True
            artifacts_removed = self._remove_artifacts(association)
        finally:
            release_claim()
        return DeleteResult(association_removed, artifacts_removed)

    def _remove_artifacts(self, association: ProvisionalAssociation | ConversationAssociation) -> bool:
        try:
            session = self.store.paths.session_path(association.conversation_id)
            if session.resolve(strict=False) != Path(association.session_path).resolve(strict=False):
                return False
            session.unlink(missing_ok=True)
            presentation = self.store.paths.presentation_path(association.conversation_id)
            if presentation.exists():
                shutil.rmtree(presentation)
            workspace = self.store.paths.workspace_path(association.conversation_id)
            owns_workspace = (
                Path(association.working_directory).resolve(strict=False) == workspace.resolve(strict=False)
            )
            if owns_workspace and workspace.exists():
                shutil.rmtree(workspace)
            return True
        except OSError:
            return False

    async def shutdown(self) -> tuple[CloseResult, ...]:
        async with self._admission_lock:
            detached = tuple(self._resident.values())
            self._resident.clear()
        for resident in detached:
            await self._stop_transport_watch(resident)
        outcomes = await asyncio.gather(
            *(self._retire_detached(resident) for resident in detached),
            return_exceptions=True,
        )
        return tuple(
            outcome
            if isinstance(outcome, CloseResult)
            else CloseResult("unclean", bool(getattr(resident.process, "child_exit_observed", False)))
            for resident, outcome in zip(detached, outcomes, strict=True)
        )

    def goal_projection(self, conversation_id: str):
        resident = self._resident.get(conversation_id)
        if resident is None:
            raise ConversationNotOpen(conversation_id)
        return resident.process.client.prime_meta.goal

    def _cache_for(self, conversation_id: str) -> PresentationCache:
        return PresentationCache(self._cache_root / conversation_id)

    def _view(self, resident: ResidentConversation) -> ConversationView:
        return ConversationView(
            conversation_id=resident.association.conversation_id,
            durable=resident.durable,
            target_available=self._binding_available(resident.association.binding),
            effective_settings=dict(resident.process.client.effective_settings),
        )

    def _binding_available(self, binding: RookBinding) -> bool:
        try:
            return bool(self._target_available(binding))
        except Exception:
            return False

    @staticmethod
    def _saved_working_directory(value: str | None) -> Path | None:
        if value is None:
            return None
        path = Path(value)
        if not path.is_absolute():
            raise WorkingDirectoryUnavailable()
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise WorkingDirectoryUnavailable() from exc
        if not resolved.is_dir():
            raise WorkingDirectoryUnavailable()
        return resolved

    @staticmethod
    def _required_working_directory(value: str) -> Path:
        result = AcpConversationManager._saved_working_directory(value)
        if result is None:
            raise WorkingDirectoryUnavailable()
        return result
