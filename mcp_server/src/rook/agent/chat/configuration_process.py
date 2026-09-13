"""One private configuration child, with persistence independent of cleanup."""

from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import configuration_protocol as wire
from .prime_runtime import PrimeRuntimeContract, build_configuration_argv, build_configuration_env

OPERATION_SECONDS = {operation: (20.0 if operation in wire.READ_OPERATIONS else 600.0 if operation == "oauth.connect" else 30.0)
                     for operation in wire.OPERATIONS}
BEGIN_SECONDS = 5.0
CLEANUP_SECONDS = 15.0
COOPERATIVE_SECONDS = 10.0


@dataclass(frozen=True)
class ConfigurationSettlement:
    result: wire.ConfigurationResult | None
    exit_code: int | None
    cleanup: str
    failure_code: str | None

    def wire(self) -> dict:
        return {"type": "configuration_settled", "result": self.result.wire() if self.result else None,
                "exit_code": self.exit_code, "cleanup": self.cleanup, "failure_code": self.failure_code}


class PrimeConfigurationOperation:
    def __init__(self, contract: PrimeRuntimeContract, begin: wire.ConfigurationBegin, base_environment, data_root: Path):
        self.argv = build_configuration_argv(contract)
        self.environment = build_configuration_env(base_environment, contract, data_root)
        self.cwd = str(data_root)
        self.begin = begin
        self.process: asyncio.subprocess.Process | None = None
        self.result: wire.ConfigurationResult | None = None
        self.failure_code: str | None = None
        self._interrupt = asyncio.Event()
        self._input_lock = asyncio.Lock()
        self._pending: dict | None = None
        self._request_id = 0
        self._request_count = 0
        self._stdin_bytes = self._stdin_count = 0
        self._stdout_bytes = self._stdout_count = self._stderr_bytes = 0
        self._cancelled = False
        self._trusted = True
        self._begun = False
        self._running = False
        self._cleanup_end: float | None = None
        self._spawn: asyncio.Task | None = None
        self._tasks: list[asyncio.Task] = []
        self._deadline = 0.0

    @property
    def cleanup_deadline(self) -> float | None:
        return self._cleanup_end

    def _stop(self, code: str | None, *, trusted: bool = True) -> None:
        if code and (self.failure_code is None or self.failure_code == "cancelled" or
                     (self.failure_code == "output_failed" and code in {"protocol_error", "bounds_exceeded"})):
            self.failure_code = code
        self._trusted &= trusted
        self._pending = None
        if self._cleanup_end is None:
            self._cleanup_end = asyncio.get_running_loop().time() + CLEANUP_SECONDS
        self._interrupt.set()

    def cancel(self, operation_id: str) -> None:
        wire.require(operation_id == self.begin.operation_id)
        if self.result is None:
            self._cancelled = True
            self._stop("cancelled")

    async def reply(self, operation_id: str, request_id: int, value: str) -> None:
        record = wire.validate_control({"v": 1, "type": "reply", "operationId": operation_id,
                                        "requestId": request_id, "value": value}, "reply")
        wire.require(operation_id == self.begin.operation_id)
        wire.require(not self._cancelled and self.result is None)
        if self._pending is None or self._pending["requestId"] != request_id:
            self._stop("protocol_error", trusted=False)
            raise wire.ConfigurationError()
        if self._pending["kind"] == "select" and value not in {item["id"] for item in self._pending["choices"]}:
            self._stop("protocol_error", trusted=False)
            raise wire.ConfigurationError()
        self._pending = None
        try:
            await self._send(record)
        except wire.ConfigurationError as exc:
            if self._cancelled:
                raise wire.ConfigurationError("cancelled") from None
            self._stop(exc.code, trusted=False)
            raise
        except Exception:
            self._stop("stdin_failed", trusted=False)
            raise wire.ConfigurationError("stdin_failed") from None

    async def _send(self, record: dict, *, cleanup: bool = False) -> None:
        deadline = self._cleanup_end if cleanup else self._deadline
        async with asyncio.timeout_at(deadline):
            async with self._input_lock:
                if record["type"] != "cancel":
                    wire.require(not self._cancelled and self.result is None)
                raw = wire.encode_record(record, wire.INPUT_RECORD)
                wire.require(self._stdin_bytes + len(raw) <= wire.INPUT_TOTAL and self._stdin_count < wire.INPUT_COUNT,
                             "bounds_exceeded")
                self._stdin_bytes += len(raw)
                self._stdin_count += 1
                wire.require(self.process is not None and self.process.stdin is not None)
                self.process.stdin.write(raw)
                if record["type"] == "begin":
                    self._begun = True
                await self.process.stdin.drain()

    async def _stdout(self, emit) -> None:
        pending = bytearray()
        delivery_failed = False
        try:
            while chunk := await self.process.stdout.read(16384):
                self._stdout_bytes += len(chunk)
                wire.require(self._stdout_bytes <= wire.OUTPUT_TOTAL, "bounds_exceeded")
                pending.extend(chunk)
                while (end := pending.find(b"\n")) >= 0:
                    wire.require(end + 1 <= wire.OUTPUT_RECORD and self._stdout_count < wire.OUTPUT_COUNT, "bounds_exceeded")
                    raw = bytes(pending[:end])
                    del pending[:end + 1]
                    self._stdout_count += 1
                    wire.require(self._begun and self.result is None)
                    record = wire.validate_event(wire.parse_record(raw, wire.OUTPUT_RECORD), self.begin)
                    if record["type"] == "input":
                        wire.require((not self._cancelled or delivery_failed) and
                                     self._pending is None and record["requestId"] > self._request_id)
                        self._request_count += 1
                        wire.require(self._request_count <= 16, "bounds_exceeded")
                        self._request_id = record["requestId"]
                        self._pending = record
                    elif record["type"] == "result":
                        self.result = wire.ConfigurationResult(record["operationId"], record["outcome"], record["persistence"],
                                                               record["code"], record.get("data"))
                        self._stop(None)
                    if not delivery_failed:
                        try:
                            await emit(record)
                        except Exception:
                            # A lost HTTP sink is not a broken Prime protocol. Keep draining
                            # in-flight events and the terminal result within existing cleanup.
                            delivery_failed = True
                            self._stop("output_failed")
                            self.cancel(self.begin.operation_id)
                wire.require(len(pending) < wire.OUTPUT_RECORD, "bounds_exceeded")
            wire.require(not pending)
            if self.result is None:
                self._stop("missing_result", trusted=False)
        except asyncio.CancelledError:
            raise
        except wire.ConfigurationError as exc:
            self._stop("bounds_exceeded" if exc.code == "bounds_exceeded" else "protocol_error", trusted=False)
        except Exception:
            self._stop("output_failed", trusted=False)

    async def _stderr(self) -> None:
        try:
            while chunk := await self.process.stderr.read(4096):
                self._stderr_bytes += len(chunk)
                if self._stderr_bytes > wire.STDERR_TOTAL:
                    self._stop("bounds_exceeded", trusted=False)
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            self._stop("stderr_failed", trusted=False)

    def _adopt_spawn(self, task: asyncio.Task) -> None:
        try:
            self.process = task.result()
        except BaseException:
            self._stop("spawn_failed", trusted=False)

    async def run(self, emit) -> ConfigurationSettlement:
        wire.require(not self._running)
        self._running = True
        loop = asyncio.get_running_loop()
        self._deadline = loop.time() + OPERATION_SECONDS[self.begin.operation]
        try:
            if self._cancelled:
                raise wire.ConfigurationError("cancelled")
            flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            self._spawn = asyncio.create_task(asyncio.create_subprocess_exec(
                *self.argv, cwd=self.cwd, env=self.environment, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **flags,
            ))
            self._spawn.add_done_callback(self._adopt_spawn)
            async with asyncio.timeout_at(self._deadline):
                interrupted = asyncio.create_task(self._interrupt.wait())
                try:
                    await asyncio.wait({self._spawn, interrupted}, return_when=asyncio.FIRST_COMPLETED)
                    if self._interrupt.is_set():
                        raise wire.ConfigurationError(self.failure_code or "cancelled")
                    self.process = self._spawn.result()
                finally:
                    interrupted.cancel()
                    await asyncio.gather(interrupted, return_exceptions=True)
                self._tasks = [asyncio.create_task(self._stdout(emit)), asyncio.create_task(self._stderr()),
                               asyncio.create_task(self.process.wait())]
                self._tasks[-1].add_done_callback(lambda _: self._interrupt.set())
                async with asyncio.timeout(min(BEGIN_SECONDS, max(0, self._deadline - loop.time()))):
                    await self._send(self.begin.wire())
                # Retain only nonsecret correlation data after the private begin write.
                old = self.begin
                self.begin = wire.ConfigurationBegin(old.operation_id, old.operation, {"provider": old.input.get("provider")})
                old.input.clear()
                await self._interrupt.wait()
        except TimeoutError:
            self._stop("deadline_exceeded")
        except asyncio.CancelledError:
            self._cancelled = True
            self._stop("cancelled")
        except wire.ConfigurationError as exc:
            self._stop(exc.code, trusted=False)
        except Exception:
            self._stop("spawn_failed" if self.process is None else "process_failed", trusted=False)
        finally:
            self._stop(None)
        return await self._finish()

    async def _finish(self) -> ConfigurationSettlement:
        loop = asyncio.get_running_loop()
        end = self._cleanup_end
        cooperative = min(end, end - CLEANUP_SECONDS + COOPERATIVE_SECONDS)
        if self._spawn is not None and not self._spawn.done():
            await asyncio.wait({self._spawn}, timeout=max(0, cooperative - loop.time()))
        if self.process is not None:
            if not self._tasks:
                self._tasks = [asyncio.create_task(self.process.wait())]
            if self._begun and self.result is None and self._trusted and self.process.returncode is None:
                try:
                    async with asyncio.timeout_at(cooperative):
                        await self._send({"v": 1, "type": "cancel", "operationId": self.begin.operation_id}, cleanup=True)
                except Exception:
                    self._stop("stdin_failed", trusted=False)
            _, pending = await asyncio.wait(self._tasks, timeout=max(0, cooperative - loop.time()))
            if pending:
                self._stop("cleanup_failed")
                if self.process.returncode is None:
                    try:
                        self.process.terminate()
                    except ProcessLookupError:
                        pass
                    except Exception:
                        self._stop("cleanup_failed", trusted=False)
                    await asyncio.wait({self._tasks[-1]}, timeout=max(0, min(2.0, (end - loop.time()) / 2)))
                    if self.process.returncode is None:
                        try:
                            self.process.kill()
                        except ProcessLookupError:
                            pass
                        except Exception:
                            self._stop("cleanup_failed", trusted=False)
                for task in self._tasks[:-1]:
                    if not task.done():
                        task.cancel()
                await asyncio.wait(self._tasks, timeout=max(0, end - loop.time()))
            if self.process.stdin is not None:
                try:
                    self.process.stdin.close()
                except Exception:
                    self._stop("cleanup_failed", trusted=False)
        self.begin.input.clear()
        self._pending = None
        settled = (self._spawn is None or self._spawn.done()) and all(task.done() for task in self._tasks)
        for task in self._tasks:
            if task.done() and not task.cancelled():
                try:
                    task.result()
                except Exception:
                    self._stop("cleanup_failed", trusted=False)
        code = self.process.returncode if self.process is not None else None
        if self.process is not None and code is None:
            settled = False
        if not settled:
            self._stop("cleanup_unconfirmed", trusted=False)
        elif code not in (0, None):
            self._stop("child_exit_failed")
        if self.result is None and self.failure_code is None:
            self._stop("missing_result", trusted=False)
        return ConfigurationSettlement(self.result, code, "exited" if settled else "unconfirmed", self.failure_code)
