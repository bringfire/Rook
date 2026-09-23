"""Live native command-control saturation smoke tests for an owned Rhino runtime."""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from rook.bridge import NATIVE_CLIENT_HEADERS
import pytest


pytestmark = [
    pytest.mark.requires_rhino,
    pytest.mark.command_control_live,
]


CONTROL_TIMEOUT_SECONDS = 2.5
REQUEST_TIMEOUT_SECONDS = 8.0
RECOVERY_TIMEOUT_SECONDS = 6.0
PRESSURE_WORKERS = 12
NORMAL_PRESSURE_ROUTES = ("/document", "/layers", "/objects")
BUSY_MESSAGE = "RookNative dispatcher is busy: Rhino command is active"


@dataclass(frozen=True)
class NativeResult:
    method: str
    path: str
    status_code: int | None
    payload: dict[str, Any] | None
    elapsed_seconds: float
    error: str | None = None


def _positive_env_int(name: str) -> int:
    raw = os.environ.get(name)
    if raw is None:
        pytest.fail(f"{name} must be set by scripts/run_rhino_runtime_harness.py")
    try:
        value = int(raw)
    except ValueError:
        pytest.fail(f"{name} must be a positive integer")
    if value <= 0:
        pytest.fail(f"{name} must be a positive integer")
    return value


def _owned_port() -> int:
    return _positive_env_int("ROOK_RHINO_PORT")


def _owned_pid() -> int:
    return _positive_env_int("ROOK_RHINO_PROCESS_ID")


def _base_url() -> str:
    return f"http://127.0.0.1:{_owned_port()}"


def _artifact_dir() -> Path | None:
    raw = os.environ.get("ROOK_HARNESS_ARTIFACT_DIR")
    if not raw:
        return None
    artifact_dir = Path(raw)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir


def _assert_owned_runtime_binding() -> None:
    from rook.runtime_harness import DiscoveryError, OwnedRhinoDiscovery

    pid = _owned_pid()
    port = _owned_port()
    try:
        record = OwnedRhinoDiscovery().read_owned_record(pid)
    except DiscoveryError as exc:
        pytest.fail(f"Could not verify owned Rhino discovery record for pid {pid}: {exc}")
    if record.port != port:
        pytest.fail(
            "ROOK_RHINO_PORT and ROOK_RHINO_PROCESS_ID do not refer to the same "
            f"owned runtime: env port {port}, discovery port {record.port}, pid {pid}"
        )


def _write_diagnostic(name: str, payload: Any) -> None:
    artifact_dir = _artifact_dir()
    if artifact_dir is None:
        return
    path = artifact_dir / name
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


async def _native_request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
) -> NativeResult:
    started = time.monotonic()
    try:
        if method == "GET":
            response = await client.get(path, timeout=timeout_seconds)
        elif method == "POST":
            response = await client.post(path, json=body or {}, timeout=timeout_seconds)
        else:
            raise AssertionError(f"Unsupported method: {method}")
    except httpx.HTTPError as exc:
        return NativeResult(
            method=method,
            path=path,
            status_code=None,
            payload=None,
            elapsed_seconds=time.monotonic() - started,
            error=repr(exc),
        )

    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = {"nonJsonResponse": response.text}
    if not isinstance(payload, dict):
        payload = {"jsonResponse": payload}

    return NativeResult(
        method=method,
        path=path,
        status_code=response.status_code,
        payload=payload,
        elapsed_seconds=time.monotonic() - started,
    )


def _success_data(result: NativeResult) -> dict[str, Any]:
    assert result.error is None, f"{result.method} {result.path} failed: {result.error}"
    assert result.status_code is not None
    assert result.status_code < 500, (
        f"{result.method} {result.path} returned HTTP {result.status_code}: "
        f"{result.payload!r}"
    )
    payload = result.payload
    assert isinstance(payload, dict)
    assert payload.get("success") is True, (
        f"{result.method} {result.path} did not succeed: {payload!r}"
    )
    data = payload.get("data")
    assert isinstance(data, dict), f"{result.method} {result.path} returned non-object data"
    return data


def _is_idle_prompt_data(data: dict[str, Any]) -> bool:
    prompt = str(data.get("prompt") or "").strip()
    return data.get("is_active") is False and prompt in {"", "Command"}


def _is_active_prompt_data(data: dict[str, Any]) -> bool:
    prompt = str(data.get("prompt") or "").strip()
    return data.get("is_active") is True or prompt not in {"", "Command"}


def _is_busy_result(result: NativeResult) -> bool:
    payload = result.payload
    if not isinstance(payload, dict):
        return False
    if payload.get("success") is not False:
        return False
    text = json.dumps(payload, default=str)
    return BUSY_MESSAGE in text


async def _cancel_until_idle(client: httpx.AsyncClient) -> None:
    deadline = time.monotonic() + RECOVERY_TIMEOUT_SECONDS
    last_prompt: NativeResult | None = None
    while time.monotonic() < deadline:
        await _native_request(client, "POST", "/command/cancel", {}, CONTROL_TIMEOUT_SECONDS)
        last_prompt = await _native_request(
            client, "GET", "/command/prompt", timeout_seconds=CONTROL_TIMEOUT_SECONDS
        )
        if last_prompt.error is None and last_prompt.payload:
            payload = last_prompt.payload
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, dict) and _is_idle_prompt_data(data):
                return
        await asyncio.sleep(0.2)
    pytest.fail(f"Could not recover idle command prompt: {last_prompt!r}")


async def _wait_for_active_prompt(client: httpx.AsyncClient) -> NativeResult:
    deadline = time.monotonic() + RECOVERY_TIMEOUT_SECONDS
    last_prompt: NativeResult | None = None
    while time.monotonic() < deadline:
        last_prompt = await _native_request(
            client, "GET", "/command/prompt", timeout_seconds=CONTROL_TIMEOUT_SECONDS
        )
        if last_prompt.error is None and last_prompt.payload:
            payload = last_prompt.payload
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, dict) and _is_active_prompt_data(data):
                return last_prompt
        await asyncio.sleep(0.2)
    pytest.fail(f"Rhino command prompt did not become active: {last_prompt!r}")


async def _start_line_command(client: httpx.AsyncClient) -> None:
    await _cancel_until_idle(client)
    await _native_request(
        client,
        "POST",
        "/command",
        {"command": "_-Line", "echo": False},
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
    )
    await _wait_for_active_prompt(client)


async def _normal_pressure_worker(
    client: httpx.AsyncClient,
    started: asyncio.Event,
    stop: asyncio.Event,
    results: list[NativeResult],
    worker_index: int,
) -> None:
    await started.wait()
    route_index = worker_index % len(NORMAL_PRESSURE_ROUTES)
    while not stop.is_set():
        path = NORMAL_PRESSURE_ROUTES[route_index % len(NORMAL_PRESSURE_ROUTES)]
        route_index += 1
        result = await _native_request(
            client,
            "GET",
            path,
            timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        )
        results.append(result)
        await asyncio.sleep(0)


async def _bounded_control_call(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> NativeResult:
    return await asyncio.wait_for(
        _native_request(client, method, path, body, timeout_seconds=CONTROL_TIMEOUT_SECONDS),
        timeout=CONTROL_TIMEOUT_SECONDS + 0.5,
    )


@pytest.mark.asyncio
async def test_prompt_send_and_cancel_survive_normal_dispatch_worker_pressure() -> None:
    _assert_owned_runtime_binding()
    pressure_results: list[NativeResult] = []
    started = asyncio.Event()
    stop = asyncio.Event()

    async with httpx.AsyncClient(base_url=_base_url(), headers=NATIVE_CLIENT_HEADERS) as client:
        try:
            await _start_line_command(client)

            pressure_tasks = [
                asyncio.create_task(
                    _normal_pressure_worker(client, started, stop, pressure_results, worker)
                )
                for worker in range(PRESSURE_WORKERS)
            ]
            started.set()
            await asyncio.sleep(0.25)

            prompt = await _bounded_control_call(client, "GET", "/command/prompt")
            prompt_data = _success_data(prompt)
            assert _is_active_prompt_data(prompt_data)

            send = await _bounded_control_call(
                client,
                "POST",
                "/command/send",
                {"input": "0,0,0"},
            )
            send_data = _success_data(send)
            assert send_data.get("sent") is True
            assert send_data.get("input_sent") == "0,0,0"
            assert "objects_before" not in send_data

            cancel = await _bounded_control_call(client, "POST", "/command/cancel", {})
            cancel_data = _success_data(cancel)
            assert cancel_data.get("cancelled") is True
            assert cancel_data.get("verified") is True
            assert cancel_data.get("is_active") is False
        finally:
            stop.set()
            if "pressure_tasks" in locals():
                await asyncio.gather(*pressure_tasks, return_exceptions=True)
            await _cancel_until_idle(client)
            _write_diagnostic(
                "command-control-saturation.json",
                {
                    "pressure_results": [result.__dict__ for result in pressure_results],
                    "pressure_workers": PRESSURE_WORKERS,
                    "normal_pressure_routes": NORMAL_PRESSURE_ROUTES,
                },
            )

    assert len(pressure_results) >= PRESSURE_WORKERS, (
        f"Expected at least {PRESSURE_WORKERS} normal pressure samples, "
        f"got {len(pressure_results)}"
    )
    assert any(_is_busy_result(result) for result in pressure_results), (
        "Normal dispatch pressure did not observe the command-active busy response. "
        f"Samples: {pressure_results!r}"
    )
