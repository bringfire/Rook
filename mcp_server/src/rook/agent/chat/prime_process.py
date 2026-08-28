"""Owned Prime RPC child process for the opt-in RookChat broker."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, cast

from .prime_rpc_protocol import PrimeProtocolError


MAX_JSONL_ROW_BYTES = 64 * 1024 * 1024
MAX_STDERR_TAIL_BYTES = 256 * 1024
_CREDENTIAL_ENV_NAME = re.compile(
    r"(API_KEY|OAUTH_TOKEN|ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN|"
    r"BEARER_TOKEN_BEDROCK|WEB_IDENTITY_TOKEN_FILE|GITHUB_TOKEN|GH_TOKEN|"
    r"HF_TOKEN|COPILOT_GITHUB_TOKEN|AWS_PROFILE|"
    r"GOOGLE_APPLICATION_CREDENTIALS)$",
    re.IGNORECASE,
)


def _sanitized_prime_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if _CREDENTIAL_ENV_NAME.search(key) is None
    }


class PrimeProcessError(RuntimeError):
    """Base error for the owned Prime RPC process."""


class PrimeProcessLost(PrimeProcessError):
    """The owned process exited or was retired before a command settled."""


class PrimeControlTimeout(PrimeProcessError, TimeoutError):
    def __init__(self, command: str) -> None:
        super().__init__(f"Prime control command timed out: {command}")
        self.command = command


@dataclass(frozen=True)
class PrimeRuntimeState:
    session_id: str
    session_path: str
    provider: str
    model_id: str
    thinking: str | None


@dataclass
class _PendingCommand:
    expected_command: str
    future: asyncio.Future[dict[str, Any]]


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PrimeProtocolError(f"{label} must be a non-empty string")
    return value


def _validate_response_shape(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PrimeProtocolError("RPC response must be an object")
    if value.get("type") != "response":
        raise PrimeProtocolError("RPC response type is invalid")
    _nonempty_string(value.get("id"), "RPC response id")
    _nonempty_string(value.get("command"), "RPC response command")
    success = value.get("success")
    if type(success) is not bool:
        raise PrimeProtocolError("RPC response success must be boolean")
    base = {"id", "type", "command", "success"}
    if success:
        allowed = base | ({"data"} if "data" in value else set())
        if set(value) != allowed:
            raise PrimeProtocolError("RPC success response has an invalid closed shape")
    else:
        if set(value) != base | {"error"}:
            raise PrimeProtocolError("RPC failure response has an invalid closed shape")
        error = value["error"]
        if not isinstance(error, (str, dict)):
            raise PrimeProtocolError("RPC failure error must be a string or object")
    return cast(dict[str, Any], value)


def parse_runtime_state(response: Mapping[str, Any]) -> PrimeRuntimeState:
    if response.get("success") is not True:
        raise PrimeProtocolError("get_state did not succeed")
    data = response.get("data")
    if not isinstance(data, dict):
        raise PrimeProtocolError("get_state data must be an object")
    session_id = _nonempty_string(data.get("sessionId"), "Prime session ID")
    session_path = _nonempty_string(data.get("sessionFile"), "Prime session path")
    if not Path(session_path).is_absolute():
        raise PrimeProtocolError("Prime session path must be absolute")
    model = data.get("model")
    if not isinstance(model, dict):
        raise PrimeProtocolError("Prime model state must be an object")
    provider = _nonempty_string(model.get("provider"), "Prime provider")
    model_id = _nonempty_string(model.get("id"), "Prime model ID")
    thinking = data.get("thinkingLevel")
    if thinking is not None and not isinstance(thinking, str):
        raise PrimeProtocolError("Prime thinking level must be a string or null")
    return PrimeRuntimeState(
        session_id=session_id,
        session_path=session_path,
        provider=provider,
        model_id=model_id,
        thinking=thinking,
    )


class PrimeRpcProcess:
    CONTROL_COMMAND_TIMEOUT_SECONDS = 10.0

    def __init__(
        self,
        *,
        node_path: str | os.PathLike[str],
        cli_path: str | os.PathLike[str],
        session_dir: str | os.PathLike[str],
        generation: int,
        provider: str | None = None,
        model_id: str | None = None,
        thinking: str | None = None,
        resume_session_path: str | os.PathLike[str] | None = None,
        extra_args: Sequence[str] = (),
        control_timeout_seconds: float = CONTROL_COMMAND_TIMEOUT_SECONDS,
        max_row_bytes: int = MAX_JSONL_ROW_BYTES,
    ) -> None:
        if type(generation) is not int or generation < 1:
            raise ValueError("generation must be a positive integer")
        if (provider is None) != (model_id is None):
            raise ValueError("provider and model_id must be configured together")
        if control_timeout_seconds <= 0:
            raise ValueError("control_timeout_seconds must be positive")
        if max_row_bytes < 1 or max_row_bytes > MAX_JSONL_ROW_BYTES:
            raise ValueError("max_row_bytes must be within the 64 MiB ceiling")

        self.generation = generation
        self.control_timeout_seconds = float(control_timeout_seconds)
        self.max_row_bytes = max_row_bytes
        self._node_path = str(node_path)
        self._cli_path = str(cli_path)
        self._session_dir = str(session_dir)
        self._provider = provider
        self._model_id = model_id
        self._thinking = thinking
        self._resume_session_path = (
            str(resume_session_path) if resume_session_path is not None else None
        )
        self._extra_args = tuple(extra_args)
        if any(argument == "--api-key" or argument.startswith("--api-key=") for argument in self.argv):
            raise ValueError("--api-key is prohibited for Prime RPC launch")

        self._process: asyncio.subprocess.Process | None = None
        self._pending: dict[str, _PendingCommand] = {}
        self._listeners: list[Callable[[int, dict[str, Any]], None]] = []
        self._request_counter = 0
        self._write_lock = asyncio.Lock()
        self._retire_lock = asyncio.Lock()
        self._tasks: list[asyncio.Task[Any]] = []
        self._lost_error: PrimeProcessLost | PrimeProtocolError | None = None
        self._retiring = False
        self._retired = False
        self._stderr_tail = bytearray()

    @property
    def argv(self) -> list[str]:
        result = [
            self._node_path,
            self._cli_path,
            "--mode",
            "rpc",
            "--session-dir",
            self._session_dir,
            "--no-tools",
            "--no-extensions",
            "--no-skills",
            "--no-context-files",
            "--no-prompt-templates",
        ]
        if self._provider is not None and self._model_id is not None:
            result.extend(["--model", f"{self._provider}/{self._model_id}"])
        if self._thinking is not None:
            result.extend(["--thinking", self._thinking])
        if self._resume_session_path is not None:
            result.extend(["--resume", self._resume_session_path])
        result.extend(self._extra_args)
        return result

    @property
    def stderr_tail(self) -> str:
        return bytes(self._stderr_tail).decode("utf-8", errors="replace")

    async def start(self) -> PrimeRuntimeState:
        if self._process is not None or self._retired:
            raise PrimeProcessError("Prime process has already been started")
        Path(self._session_dir).mkdir(parents=True, exist_ok=True)
        self._process = await asyncio.create_subprocess_exec(
            *self.argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_sanitized_prime_environment(),
        )
        self._tasks = [
            asyncio.create_task(self._read_stdout()),
            asyncio.create_task(self._read_stderr()),
            asyncio.create_task(self._watch_process()),
        ]
        try:
            response = await self.command(
                {"type": "get_state"},
                expected_command="get_state",
            )
            return parse_runtime_state(response)
        except BaseException:
            await self.retire(0.5)
            raise

    def subscribe(
        self,
        listener: Callable[[int, dict[str, Any]], None],
    ) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return unsubscribe

    async def command(
        self,
        command: dict[str, Any],
        *,
        expected_command: str,
        timeout_seconds: float | None = CONTROL_COMMAND_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        process = self._process
        if process is None or process.stdin is None or self._retired:
            raise self._lost_error or PrimeProcessLost("Prime process is not running")
        if self._lost_error is not None:
            raise self._lost_error
        if command.get("type") != expected_command:
            raise ValueError("outgoing command type does not match expected_command")

        request_id = command.get("id")
        if request_id is None:
            self._request_counter += 1
            request_id = f"rook-{self.generation}-{self._request_counter}"
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("outgoing command ID must be a non-empty string")
        if request_id in self._pending:
            raise ValueError(f"duplicate outgoing request ID: {request_id}")

        outbound = dict(command)
        outbound["id"] = request_id
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = _PendingCommand(expected_command, future)
        effective_timeout = timeout_seconds
        if timeout_seconds == self.CONTROL_COMMAND_TIMEOUT_SECONDS:
            effective_timeout = self.control_timeout_seconds
        deadline = (
            None
            if effective_timeout is None
            else asyncio.get_running_loop().time() + effective_timeout
        )

        try:
            await self._await_with_deadline(self._write_command(outbound), deadline)
            return await self._await_with_deadline(asyncio.shield(future), deadline)
        except asyncio.TimeoutError as error:
            self._pending.pop(request_id, None)
            future.cancel()
            raise PrimeControlTimeout(expected_command) from error
        except asyncio.CancelledError:
            self._pending.pop(request_id, None)
            future.cancel()
            raise
        except (BrokenPipeError, ConnectionResetError) as error:
            lost = PrimeProcessLost("Prime process stdin was lost")
            self._mark_lost(lost)
            raise lost from error

    async def _await_with_deadline(
        self,
        awaitable: Any,
        deadline: float | None,
    ) -> Any:
        if deadline is None:
            return await awaitable
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            if asyncio.iscoroutine(awaitable):
                awaitable.close()
            raise asyncio.TimeoutError
        return await asyncio.wait_for(awaitable, timeout=remaining)

    async def _write_command(self, command: Mapping[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.stdin.is_closing():
            raise PrimeProcessLost("Prime process stdin is closed")
        encoded = (
            json.dumps(command, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        async with self._write_lock:
            process.stdin.write(encoded)
            await process.stdin.drain()

    async def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        buffer = bytearray()
        try:
            while True:
                chunk = await process.stdout.read(64 * 1024)
                if not chunk:
                    if buffer and not self._retiring:
                        self._protocol_failure(
                            PrimeProtocolError(
                                "Prime RPC stdout ended with an unterminated row"
                            )
                        )
                    elif not self._retiring:
                        self._mark_lost(PrimeProcessLost("Prime RPC stdout closed"))
                    return
                buffer.extend(chunk)
                while True:
                    newline = buffer.find(b"\n")
                    if newline < 0:
                        if len(buffer) > self.max_row_bytes:
                            self._protocol_failure(
                                PrimeProtocolError(
                                    "Prime RPC JSONL row exceeds the 64 MiB ceiling"
                                )
                            )
                            return
                        break
                    if newline > self.max_row_bytes:
                        self._protocol_failure(
                            PrimeProtocolError(
                                "Prime RPC JSONL row exceeds the 64 MiB ceiling"
                            )
                        )
                        return
                    row = bytes(buffer[:newline])
                    del buffer[: newline + 1]
                    if row.endswith(b"\r"):
                        self._protocol_failure(
                            PrimeProtocolError("Prime RPC JSONL must use LF delimiters")
                        )
                        return
                    self._handle_row(row)
                    if self._lost_error is not None:
                        return
        except asyncio.CancelledError:
            raise
        except BaseException as error:
            if not self._retiring:
                self._protocol_failure(
                    PrimeProtocolError(f"Prime RPC stdout reader failed: {error}")
                )

    def _handle_row(self, row: bytes) -> None:
        try:
            value = json.loads(row.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            self._protocol_failure(PrimeProtocolError("Prime RPC emitted invalid JSON"))
            return
        if not isinstance(value, dict) or not isinstance(value.get("type"), str):
            self._protocol_failure(PrimeProtocolError("Prime RPC row must be an event object"))
            return
        if value["type"] == "response":
            try:
                response = _validate_response_shape(value)
            except PrimeProtocolError as error:
                self._protocol_failure(error)
                return
            request_id = response["id"]
            pending = self._pending.get(request_id)
            if pending is None:
                return
            if response["command"] != pending.expected_command:
                self._protocol_failure(
                    PrimeProtocolError(
                        "Prime RPC response command does not match its request"
                    )
                )
                return
            self._pending.pop(request_id, None)
            if not pending.future.done():
                pending.future.set_result(response)
            return
        if "id" in value:
            self._protocol_failure(PrimeProtocolError("Prime RPC event must not contain an ID"))
            return
        loop = asyncio.get_running_loop()
        for listener in tuple(self._listeners):
            loop.call_soon(self._deliver_event, listener, value)

    def _deliver_event(
        self,
        listener: Callable[[int, dict[str, Any]], None],
        event: dict[str, Any],
    ) -> None:
        try:
            listener(self.generation, event)
        except Exception:
            pass

    async def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        try:
            while chunk := await process.stderr.read(64 * 1024):
                self._stderr_tail.extend(chunk)
                overflow = len(self._stderr_tail) - MAX_STDERR_TAIL_BYTES
                if overflow > 0:
                    del self._stderr_tail[:overflow]
        except asyncio.CancelledError:
            raise
        except Exception:
            return

    async def _watch_process(self) -> None:
        process = self._process
        if process is None:
            return
        return_code = await process.wait()
        if not self._retiring:
            self._mark_lost(
                PrimeProcessLost(f"Prime process exited with code {return_code}")
            )

    def _protocol_failure(self, error: PrimeProtocolError) -> None:
        self._mark_lost(error)
        process = self._process
        if process is not None and process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass

    def _mark_lost(self, error: PrimeProcessLost | PrimeProtocolError) -> None:
        if self._lost_error is None:
            self._lost_error = error
        pending = tuple(self._pending.values())
        self._pending.clear()
        for command in pending:
            if not command.future.done():
                command.future.set_exception(self._lost_error)

    async def retire(self, grace_seconds: float) -> None:
        if grace_seconds < 0:
            raise ValueError("grace_seconds must be non-negative")
        async with self._retire_lock:
            if self._retired:
                return
            self._retiring = True
            self._mark_lost(PrimeProcessLost("Prime process retired"))
            process = self._process
            if process is not None:
                deadline = asyncio.get_running_loop().time() + grace_seconds
                if process.stdin is not None and not process.stdin.is_closing():
                    process.stdin.close()
                    try:
                        await process.stdin.wait_closed()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                if process.returncode is None:
                    try:
                        await asyncio.wait_for(
                            process.wait(),
                            timeout=max(
                                0.001,
                                deadline - asyncio.get_running_loop().time(),
                            ),
                        )
                    except asyncio.TimeoutError:
                        try:
                            process.terminate()
                        except ProcessLookupError:
                            pass
                if process.returncode is None and sys.platform == "win32":
                    killer = await asyncio.create_subprocess_exec(
                        "taskkill",
                        "/PID",
                        str(process.pid),
                        "/T",
                        "/F",
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await killer.wait()
                elif process.returncode is None:
                    process.kill()
                if process.returncode is None:
                    await process.wait()

            current = asyncio.current_task()
            for task in self._tasks:
                if task is not current and not task.done():
                    task.cancel()
            await asyncio.gather(
                *(task for task in self._tasks if task is not current),
                return_exceptions=True,
            )
            self._listeners.clear()
            self._retired = True
