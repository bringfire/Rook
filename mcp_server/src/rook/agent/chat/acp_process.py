"""Direct ownership of one Prime ACP subprocess and SDK transport."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from acp import PROTOCOL_VERSION
from acp.schema import (
    ClientCapabilities,
    Implementation,
    McpServerStdio,
    PromptResponse,
)
from acp.stdio import spawn_agent_process

from .acp_client import RookChatAcpClient
from .acp_presentation import BoundedPromptProjection, PromptGeneration
from .acp_storage import OpenClaim
from .prime_runtime import validate_windows_launch_argv


STDERR_READ_CHUNK_BYTES = 8 * 1024
STDERR_TAIL_BYTES = 64 * 1024
ACP_CONTROL_TIMEOUT_SECONDS = 10.0
ACP_CANCEL_SEND_TIMEOUT_SECONDS = 2.0
ACP_RETIRE_TIMEOUT_SECONDS = 10.0


class AcpCapabilityError(RuntimeError):
    pass


class AcpCancellationUncertain(RuntimeError):
    pass


@dataclass(frozen=True)
class PrimeLaunch:
    argv: tuple[str, ...]
    environment: Mapping[str, str]
    cwd: Path


@dataclass(frozen=True)
class InitializedAcp:
    image_supported: bool


@dataclass(frozen=True)
class RetirementResult:
    clean: bool
    child_exit_observed: bool
    stderr_total_bytes: int
    stderr_truncated: bool
    stderr_failure_code: str | None


class OwnedAcpProcess:
    def __init__(
        self,
        launch: PrimeLaunch,
        claim: OpenClaim,
        launch_generation: int,
        client: RookChatAcpClient,
        spawn_context: Any,
        connection: Any,
        process: asyncio.subprocess.Process,
    ) -> None:
        self.launch = launch
        self.claim = claim
        self.launch_generation = launch_generation
        self.client = client
        self._spawn_context = spawn_context
        self.connection = connection
        self.process = process
        self.session_id: str | None = None
        self.image_supported = False
        self.child_exit_observed = False
        self._retirement_task: asyncio.Task[RetirementResult] | None = None
        self._retirement_result: RetirementResult | None = None
        self._active_cancel: asyncio.Event | None = None
        self._pending_cancel = False
        self._cancel_sent = False
        self._stderr_tail = bytearray()
        self._stderr_total_bytes = 0
        self._stderr_failure_code: str | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self.transport_failure = asyncio.Event()

    @classmethod
    async def start(
        cls,
        launch: PrimeLaunch,
        claim: OpenClaim,
        *,
        launch_generation: int,
        spawn_context_factory: Callable[..., Any] = spawn_agent_process,
    ) -> "OwnedAcpProcess":
        validate_windows_launch_argv(launch.argv)
        client = RookChatAcpClient()
        context = spawn_context_factory(
            client,
            *launch.argv,
            env=launch.environment,
            cwd=launch.cwd,
            transport_kwargs={"stderr": asyncio.subprocess.PIPE},
            use_unstable_protocol=True,
        )
        try:
            connection, process = await context.__aenter__()
        except (FileNotFoundError, PermissionError):
            claim.release_no_child_created()
            raise
        except BaseException as exc:
            cleanup = asyncio.create_task(cls._close_partial_spawn(context, exc))
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.shield(cleanup)
            raise

        owned = cls(launch, claim, launch_generation, client, context, connection, process)
        if process.stderr is None:
            await owned.retire(send_close=False)
            raise RuntimeError("stderr_unavailable")
        try:
            owned._stderr_task = asyncio.create_task(owned._drain_stderr(process.stderr))
        except Exception:
            await owned.retire(send_close=False)
            raise
        return owned

    @staticmethod
    async def _close_partial_spawn(context: Any, exc: BaseException) -> None:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(
                context.__aexit__(type(exc), exc, exc.__traceback__),
                timeout=ACP_RETIRE_TIMEOUT_SECONDS,
            )

    async def _drain_stderr(self, stderr: asyncio.StreamReader) -> None:
        try:
            while True:
                chunk = await stderr.read(STDERR_READ_CHUNK_BYTES)
                if not chunk:
                    return
                self._stderr_total_bytes += len(chunk)
                self._stderr_tail.extend(chunk)
                if len(self._stderr_tail) > STDERR_TAIL_BYTES:
                    del self._stderr_tail[: len(self._stderr_tail) - STDERR_TAIL_BYTES]
        except asyncio.CancelledError:
            raise
        except Exception:
            self._stderr_failure_code = "stderr_drain_failed"
            self.transport_failure.set()

    async def initialize(self) -> InitializedAcp:
        response = await asyncio.wait_for(
            self.connection.initialize(
                protocol_version=PROTOCOL_VERSION,
                client_capabilities=ClientCapabilities(),
                client_info=Implementation(name="rookchat", title="RookChat", version="1"),
            ),
            timeout=ACP_CONTROL_TIMEOUT_SECONDS,
        )
        if response.protocol_version != PROTOCOL_VERSION:
            raise AcpCapabilityError("protocol_version_mismatch")
        capabilities = response.agent_capabilities
        session_capabilities = None if capabilities is None else capabilities.session_capabilities
        if session_capabilities is None or session_capabilities.close is None:
            raise AcpCapabilityError("session_close_required")
        prompt_capabilities = capabilities.prompt_capabilities
        self.image_supported = bool(prompt_capabilities is not None and prompt_capabilities.image)
        return InitializedAcp(image_supported=self.image_supported)

    async def new_session(
        self,
        *,
        cwd: Any,
        mcp_servers: Sequence[McpServerStdio],
    ) -> str:
        if self.session_id is not None:
            raise RuntimeError("ACP session already exists")
        self.client.begin_session(self.launch_generation)
        response = await asyncio.wait_for(
            self.connection.new_session(cwd=str(cwd), mcp_servers=list(mcp_servers)),
            timeout=ACP_CONTROL_TIMEOUT_SECONDS,
        )
        self.session_id = response.session_id
        self.client.complete_session(self.session_id, response.field_meta)
        return self.session_id

    async def prompt(
        self,
        content_blocks: list[Any],
        *,
        generation: PromptGeneration,
        projection: BoundedPromptProjection,
    ) -> PromptResponse:
        if self.session_id is None or generation.acp_session_id != self.session_id:
            raise RuntimeError("ACP session is unavailable")
        cancellation = asyncio.Event()
        self._active_cancel = cancellation
        self._cancel_sent = False
        if self._pending_cancel:
            cancellation.set()
        self.client.activate_prompt(generation, projection, cancellation)
        prompt_task = asyncio.create_task(self.connection.prompt(self.session_id, content_blocks))
        permission_cancel = asyncio.create_task(cancellation.wait())
        overflow_cancel = asyncio.create_task(projection.overflow_signal.wait())
        try:
            done, _ = await asyncio.wait(
                {prompt_task, permission_cancel, overflow_cancel},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if prompt_task not in done:
                await self._send_cancel_once()
            response = await prompt_task
            if response.field_meta:
                self.client.observe_prime_meta(response.field_meta)
            return response
        finally:
            permission_cancel.cancel()
            overflow_cancel.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await permission_cancel
            with contextlib.suppress(asyncio.CancelledError):
                await overflow_cancel
            self.client.clear_prompt(generation)
            self._active_cancel = None
            self._pending_cancel = False

    async def _send_cancel_once(self) -> None:
        if self.session_id is None or self._cancel_sent:
            return
        self._cancel_sent = True
        try:
            await asyncio.wait_for(
                self.connection.cancel(self.session_id),
                timeout=ACP_CANCEL_SEND_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            self.transport_failure.set()
            raise
        except Exception as exc:
            self.transport_failure.set()
            raise AcpCancellationUncertain("session_cancel_uncertain") from exc

    async def cancel(self) -> None:
        self._pending_cancel = True
        if self._active_cancel is None:
            return
        self._active_cancel.set()
        await self._send_cancel_once()

    async def close_session(self) -> None:
        if self.session_id is None:
            return
        await asyncio.wait_for(
            self.connection.close_session(self.session_id),
            timeout=ACP_CONTROL_TIMEOUT_SECONDS,
        )

    async def retire(
        self,
        *,
        send_close: bool = True,
        release_claim: bool = True,
    ) -> RetirementResult:
        task = self.begin_retirement(send_close=send_close, release_claim=release_claim)
        return await asyncio.shield(task)

    def begin_retirement(
        self,
        *,
        send_close: bool = True,
        release_claim: bool = True,
    ) -> asyncio.Task[RetirementResult]:
        if self._retirement_task is None:
            self.client.retire_session_settings()
            self._retirement_task = asyncio.create_task(
                self._retire_once(send_close=send_close, release_claim=release_claim)
            )
        return self._retirement_task

    async def _retire_once(
        self,
        *,
        send_close: bool,
        release_claim: bool,
    ) -> RetirementResult:
        clean = not (self.session_id is not None and not send_close)
        if send_close and self.session_id is not None:
            try:
                await self.close_session()
            except Exception:
                clean = False

        try:
            await asyncio.wait_for(
                self._spawn_context.__aexit__(None, None, None),
                timeout=ACP_RETIRE_TIMEOUT_SECONDS,
            )
        except Exception:
            clean = False

        exit_observed = False
        if self.process.returncode is None:
            clean = False
            with contextlib.suppress(ProcessLookupError):
                self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=ACP_RETIRE_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    self.process.kill()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=ACP_RETIRE_TIMEOUT_SECONDS)
                except asyncio.TimeoutError:
                    pass
                else:
                    exit_observed = True
            else:
                exit_observed = True
        else:
            try:
                await asyncio.wait_for(self.process.wait(), timeout=ACP_RETIRE_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                clean = False
            else:
                exit_observed = True
        self.child_exit_observed = exit_observed
        if exit_observed and self.process.returncode != 0:
            clean = False

        if self._stderr_task is not None:
            if not exit_observed:
                self._stderr_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.wait_for(self._stderr_task, timeout=ACP_RETIRE_TIMEOUT_SECONDS)
            else:
                try:
                    await asyncio.wait_for(self._stderr_task, timeout=ACP_RETIRE_TIMEOUT_SECONDS)
                except Exception:
                    self._stderr_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self._stderr_task
                    self._stderr_failure_code = self._stderr_failure_code or "stderr_drain_failed"
                    self.transport_failure.set()
                    clean = False
        if self._stderr_failure_code is not None:
            clean = False
        self._stderr_tail.clear()
        if release_claim and exit_observed:
            self.claim.release_after_observed_exit()
        self._retirement_result = self._result(clean=clean)
        return self._retirement_result

    def _result(self, *, clean: bool) -> RetirementResult:
        return RetirementResult(
            clean=clean,
            child_exit_observed=self.child_exit_observed,
            stderr_total_bytes=self._stderr_total_bytes,
            stderr_truncated=self._stderr_total_bytes > STDERR_TAIL_BYTES,
            stderr_failure_code=self._stderr_failure_code,
        )
