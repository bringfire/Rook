"""Leaf module owning the Rhino launch + readiness primitives.

This is the canonical home for the discovery/readiness/window-read primitives that
`runtime_harness.py` and `workbench.py` both use. They live here (not in
`runtime_harness.py`) so the future launch helpers in this module can reuse them
without `runtime_harness` ↔ `rhino_launch` becoming a circular import.

`runtime_harness.py` re-exports the names below for back-compat; `close_windows_for_pid`
and `WM_CLOSE` (cleanup, not evidence) stay in `runtime_harness.py`.

Imports only stdlib, `httpx`, and the leaf `.bridge` (`resolve_discovery_folder`) — never
`runtime_harness` or `workbench`.
"""

from __future__ import annotations

import asyncio
import ctypes
from ctypes import wintypes
import inspect
import json
import os
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

import httpx

from .bridge import resolve_discovery_folder


LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}
MIN_POLL_SECONDS = 0.001


class DiscoveryFailureReason(Enum):
    FILE_NOT_FOUND = "file_not_found"
    INVALID_RECORD = "invalid_record"
    EXITED_BEFORE_BIND = "exited_before_bind"
    EXITED_BEFORE_READY = "exited_before_ready"
    BIND_TIMEOUT_NO_DISCOVERY = "bind_timeout_no_discovery"
    BIND_TIMEOUT_NO_PING = "bind_timeout_no_ping"
    INVALID_DISCOVERY_RECORD = "invalid_discovery_record"


class DiscoveryError(RuntimeError):
    def __init__(self, message: str, *, reason: "DiscoveryFailureReason | None" = None):
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class OwnedRhinoRecord:
    pid: int
    host: str
    port: int
    path: Path
    raw: dict[str, Any]


class ProcessLike(Protocol):
    pid: int
    returncode: int | None

    def poll(self) -> int | None: ...


PingFunction = Callable[[str, int], bool | Awaitable[bool]]


def default_discovery_dir() -> Path:
    folder, _, _ = resolve_discovery_folder(temp_root=Path(tempfile.gettempdir()))
    return folder


def _windows_user32() -> ctypes.WinDLL:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    return user32


def _window_title(user32: ctypes.WinDLL, hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    copied = user32.GetWindowTextW(hwnd, buffer, length + 1)
    if copied <= 0:
        return ""
    return buffer.value


def describe_windows_for_pid(pid: int) -> list[dict[str, Any]]:
    if os.name != "nt":
        return []

    user32 = _windows_user32()
    windows: list[dict[str, Any]] = []

    def enum_window(hwnd, lparam):
        visible = bool(user32.IsWindowVisible(hwnd))
        if not visible:
            return True

        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value == pid:
            windows.append(
                {
                    "hwnd": f"0x{int(hwnd):x}",
                    "visible": visible,
                    "title": _window_title(user32, hwnd),
                }
            )
        return True

    enum_windows_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(enum_windows_proc(enum_window), 0)
    return windows


def _run_awaitable_sync(awaitable: Awaitable[bool]) -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return bool(asyncio.run(awaitable))
    if inspect.iscoroutine(awaitable):
        awaitable.close()
    raise DiscoveryError("async ping function cannot be used from a running event loop")


async def ping_native(host: str, port: int) -> bool:
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            response = await client.get(f"http://{host}:{port}/ping")
        except httpx.HTTPError:
            return False
    if response.text.strip() == "pong":
        return True
    try:
        data = response.json()
    except ValueError:
        return False
    if data == "pong":
        return True
    return isinstance(data, dict) and (data.get("data") == "pong" or data.get("success") is True)


class OwnedRhinoDiscovery:
    def __init__(self, discovery_dir: Path | None = None):
        self.discovery_dir = discovery_dir or default_discovery_dir()

    def owned_path(self, pid: int) -> Path:
        return self.discovery_dir / f"instance-{pid}-native.json"

    def read_owned_record(self, pid: int) -> OwnedRhinoRecord:
        path = self.owned_path(pid)
        if not path.exists():
            raise DiscoveryError(
                f"owned Rhino discovery file not found: {path}",
                reason=DiscoveryFailureReason.FILE_NOT_FOUND,
            )

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DiscoveryError(
                f"malformed JSON in owned Rhino discovery file: {path}",
                reason=DiscoveryFailureReason.INVALID_RECORD,
            ) from exc
        if not isinstance(raw, dict):
            raise DiscoveryError(
                f"owned Rhino discovery JSON must be an object: {path}",
                reason=DiscoveryFailureReason.INVALID_RECORD,
            )

        process_id = raw.get("processId")
        if not isinstance(process_id, int) or isinstance(process_id, bool) or process_id != pid:
            raise DiscoveryError(
                f"wrong processId in owned Rhino discovery file: {process_id}",
                reason=DiscoveryFailureReason.INVALID_RECORD,
            )

        plugin_type = raw.get("pluginType")
        if plugin_type != "native":
            raise DiscoveryError(
                f"unexpected pluginType in owned Rhino discovery file: {plugin_type}",
                reason=DiscoveryFailureReason.INVALID_RECORD,
            )

        raw_host = raw.get("host")
        if raw_host is None or raw_host == "":
            host = "127.0.0.1"
        elif not isinstance(raw_host, str):
            raise DiscoveryError(
                f"owned Rhino discovery host must be loopback: {raw_host}",
                reason=DiscoveryFailureReason.INVALID_RECORD,
            )
        else:
            host = raw_host.strip().lower()
        if host not in LOOPBACK_HOSTS:
            raise DiscoveryError(
                f"owned Rhino discovery host must be loopback: {host}",
                reason=DiscoveryFailureReason.INVALID_RECORD,
            )

        port = raw.get("port")
        if not isinstance(port, int) or isinstance(port, bool) or port <= 0:
            raise DiscoveryError(
                f"invalid port in owned Rhino discovery file: {port}",
                reason=DiscoveryFailureReason.INVALID_RECORD,
            )

        return OwnedRhinoRecord(pid=pid, host=host, port=port, path=path, raw=raw)

    def snapshot_owned_record(self, record: OwnedRhinoRecord, artifact_dir: Path) -> Path:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = artifact_dir / f"owned-discovery-{record.path.name}"
        snapshot_path.write_text(json.dumps(record.raw, indent=2), encoding="utf-8")
        return snapshot_path

    def wait_for_ready(
        self,
        pid: int,
        process: ProcessLike,
        ping: PingFunction = ping_native,
        timeout_seconds: float = 30.0,
        poll_seconds: float = 0.25,
        *,
        _monotonic: Callable[[], float] = time.monotonic,
        _sleep: Callable[[float], None] = time.sleep,
    ) -> OwnedRhinoRecord:
        deadline = _monotonic() + timeout_seconds
        last_discovery_error: DiscoveryError | None = None
        saw_discovery = False

        while True:
            exit_code = process.poll()
            if exit_code is not None:
                if saw_discovery:
                    raise DiscoveryError(
                        f"Rhino exited with code {exit_code} before RookNative became pingable",
                        reason=DiscoveryFailureReason.EXITED_BEFORE_READY,
                    )
                raise DiscoveryError(
                    f"Rhino exited with code {exit_code} before RookNative discovery appeared",
                    reason=DiscoveryFailureReason.EXITED_BEFORE_BIND,
                )

            try:
                record = self.read_owned_record(pid)
            except DiscoveryError as exc:
                last_discovery_error = exc
            else:
                saw_discovery = True
                ping_result = ping(record.host, record.port)
                if inspect.isawaitable(ping_result):
                    ping_result = _run_awaitable_sync(ping_result)
                if ping_result:
                    return record

            now = _monotonic()
            if now >= deadline:
                if saw_discovery:
                    raise DiscoveryError(
                        f"owned RookNative discovery for Rhino pid {pid} did not become pingable",
                        reason=DiscoveryFailureReason.BIND_TIMEOUT_NO_PING,
                    )
                if (
                    last_discovery_error is not None
                    and last_discovery_error.reason is DiscoveryFailureReason.INVALID_RECORD
                ):
                    raise DiscoveryError(
                        str(last_discovery_error),
                        reason=DiscoveryFailureReason.INVALID_DISCOVERY_RECORD,
                    ) from last_discovery_error
                raise DiscoveryError(
                    str(last_discovery_error)
                    if last_discovery_error is not None
                    else f"owned Rhino discovery file not found for pid {pid}",
                    reason=DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY,
                )

            wait_seconds = poll_seconds if poll_seconds > 0 else MIN_POLL_SECONDS
            _sleep(min(wait_seconds, deadline - now))
