"""Authenticated service plumbing for one finite, short-lived configuration operation."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from aiohttp import web

from . import prime_runtime
from .configuration_process import PrimeConfigurationOperation
from .configuration_protocol import ConfigurationError, INPUT_RECORD, OUTPUT_RECORD, encode_record, parse_record, validate_begin, validate_control
from .prime_runtime import PrimeLaunchError, RuntimeUnavailable, build_configuration_argv

CONFIGURATION_KEY = web.AppKey("_prime_configuration", object)


class ConfigurationHttp:
    """One app-local slot. No queue, result cache or persistent operation registry."""

    def __init__(self, catalog, base_environment, data_root: Path):
        self.catalog = catalog
        self.base_environment = base_environment
        self.data_root = data_root
        self.active: PrimeConfigurationOperation | None = None
        self.task: asyncio.Task | None = None
        self.stopping = False

    def available(self) -> bool:
        if not prime_runtime.SUPPORTED_CONFIGURATION_COMMITS:
            return False
        try:
            build_configuration_argv(self.catalog.latest())
            return True
        except (RuntimeUnavailable, PrimeLaunchError):
            return False

    def start(self, begin, emit) -> PrimeConfigurationOperation:
        if self.stopping or self.active is not None:
            raise ConfigurationError("configuration_busy")
        # Synchronous admission reserves the only slot before any coroutine yields.
        contract = self.catalog.latest()
        operation = PrimeConfigurationOperation(contract, begin, self.base_environment, self.data_root)
        self.active = operation
        self.task = asyncio.create_task(operation.run(emit))
        self.task.add_done_callback(self._finished)
        return operation

    def _finished(self, task: asyncio.Task) -> None:
        try:
            settlement = task.result()
        except BaseException:
            return  # Preserve the exact uncertain owner; never overlap another child.
        if settlement.cleanup == "exited":
            self.active = None
            self.task = None

    def matching(self, operation_id: str) -> PrimeConfigurationOperation:
        if self.active is None or self.active.begin.operation_id != operation_id:
            raise ConfigurationError("invalid_request")
        return self.active

    async def shutdown(self) -> None:
        self.stopping = True
        if self.active is not None:
            self.active.cancel(self.active.begin.operation_id)
        if self.task is not None:
            await asyncio.shield(self.task)


def _error(code: str, status: int) -> web.Response:
    return web.json_response({"error": {"code": code, "message": code}}, status=status, headers={"Cache-Control": "no-store"})


async def _body(request: web.Request) -> dict:
    raw = bytearray()
    async for chunk in request.content.iter_chunked(8192):
        raw.extend(chunk)
        if len(raw) > INPUT_RECORD:
            raise ConfigurationError("bounds_exceeded")
    return parse_record(bytes(raw))


async def handle_configuration(request: web.Request) -> web.StreamResponse:
    from .server import _with_cors

    dependency = request.app[CONFIGURATION_KEY]
    if dependency is None:
        return _error("configuration_unavailable", 503)
    response = _with_cors(web.StreamResponse(headers={"Content-Type": "application/x-ndjson", "Cache-Control": "no-store"}))
    operation = None
    task = None
    writable = True
    ready = asyncio.Event()

    async def emit(event):
        await ready.wait()
        if writable:
            await response.write(encode_record(event, OUTPUT_RECORD))

    try:
        begin = validate_begin(await _body(request))
        # Select/verify and reserve before preparing a success stream or starting work.
        # The task cannot run until this handler yields at prepare().
        operation = dependency.start(begin, emit)
        task = dependency.task
        await response.prepare(request)
        ready.set()
        while not task.done():
            if request.transport is None or request.transport.is_closing():
                writable = False
                operation.cancel(operation.begin.operation_id)
                break
            await asyncio.wait({task}, timeout=0.1)
        settlement = await asyncio.shield(task)
        if writable:
            async with asyncio.timeout_at(operation.cleanup_deadline):
                await response.write(encode_record(settlement.wire(), OUTPUT_RECORD + 1024))
                await response.write_eof()
        return response
    except (asyncio.CancelledError, ConnectionError):
        writable = False
        if operation is not None:
            operation.cancel(operation.begin.operation_id)
        raise
    except Exception as exc:
        writable = False
        if operation is not None:
            operation.cancel(operation.begin.operation_id)
        if response.prepared:
            return response
        if isinstance(exc, (RuntimeUnavailable, PrimeLaunchError)):
            return _error("configuration_unavailable", 503)
        if isinstance(exc, ConfigurationError):
            return _error(exc.code, 409 if exc.code == "configuration_busy" else 400)
        return _error("configuration_failed", 500)
    finally:
        ready.set()
        if task is not None and not task.done():
            # HTTP cancellation must not cancel the child's retained owner task.
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.shield(task)


async def handle_control(request: web.Request) -> web.Response:
    try:
        kind = "reply" if request.path.endswith("/reply") else "cancel"
        body = validate_control(await _body(request), kind)
        dependency = request.app[CONFIGURATION_KEY]
        if dependency is None:
            return _error("configuration_unavailable", 503)
        operation = dependency.matching(body["operationId"])
        if kind == "reply":
            await operation.reply(body["operationId"], body["requestId"], body["value"])
        else:
            operation.cancel(body["operationId"])
        return web.Response(status=204, headers={"Cache-Control": "no-store"})
    except ConfigurationError as exc:
        return _error(exc.code, 400)
    except Exception:
        return _error("configuration_failed", 500)


async def shutdown_configuration(app: web.Application) -> None:
    if app[CONFIGURATION_KEY] is not None:
        await app[CONFIGURATION_KEY].shutdown()


def register_configuration_routes(app: web.Application, dependency: ConfigurationHttp | None) -> None:
    app[CONFIGURATION_KEY] = dependency
    app.router.add_post("/agent/chat/configuration", handle_configuration)
    app.router.add_post("/agent/chat/configuration/reply", handle_control)
    app.router.add_post("/agent/chat/configuration/cancel", handle_control)
    app.on_shutdown.append(shutdown_configuration)
