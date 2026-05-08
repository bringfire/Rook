from __future__ import annotations

import asyncio
import inspect
import json
import time
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

import httpx


LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}
DEFAULT_DISCOVERY_DIR = Path(tempfile.gettempdir()) / "rook"
MIN_POLL_SECONDS = 0.001


class DiscoveryError(RuntimeError):
    pass


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
    def __init__(self, discovery_dir: Path = DEFAULT_DISCOVERY_DIR):
        self.discovery_dir = discovery_dir

    def owned_path(self, pid: int) -> Path:
        return self.discovery_dir / f"instance-{pid}-native.json"

    def read_owned_record(self, pid: int) -> OwnedRhinoRecord:
        path = self.owned_path(pid)
        if not path.exists():
            raise DiscoveryError(f"owned Rhino discovery file not found: {path}")

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DiscoveryError(f"malformed JSON in owned Rhino discovery file: {path}") from exc
        if not isinstance(raw, dict):
            raise DiscoveryError(f"owned Rhino discovery JSON must be an object: {path}")

        process_id = raw.get("processId")
        if not isinstance(process_id, int) or isinstance(process_id, bool) or process_id != pid:
            raise DiscoveryError(f"wrong processId in owned Rhino discovery file: {process_id}")

        plugin_type = raw.get("pluginType")
        if plugin_type != "native":
            raise DiscoveryError(f"unexpected pluginType in owned Rhino discovery file: {plugin_type}")

        raw_host = raw.get("host")
        if raw_host is None or raw_host == "":
            host = "127.0.0.1"
        elif not isinstance(raw_host, str):
            raise DiscoveryError(f"owned Rhino discovery host must be loopback: {raw_host}")
        else:
            host = raw_host.strip().lower()
        if host not in LOOPBACK_HOSTS:
            raise DiscoveryError(f"owned Rhino discovery host must be loopback: {host}")

        port = raw.get("port")
        if not isinstance(port, int) or isinstance(port, bool) or port <= 0:
            raise DiscoveryError(f"invalid port in owned Rhino discovery file: {port}")

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
                        f"Rhino exited with code {exit_code} before RookNative became pingable"
                    )
                raise DiscoveryError(
                    f"Rhino exited with code {exit_code} before RookNative discovery appeared"
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
                        f"owned RookNative discovery for Rhino pid {pid} did not become pingable"
                    )
                if last_discovery_error is not None:
                    raise DiscoveryError(str(last_discovery_error)) from last_discovery_error
                raise DiscoveryError(f"owned Rhino discovery file not found for pid {pid}")

            wait_seconds = poll_seconds if poll_seconds > 0 else MIN_POLL_SECONDS
            _sleep(min(wait_seconds, deadline - now))
