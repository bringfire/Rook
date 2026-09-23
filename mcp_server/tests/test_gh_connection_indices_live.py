"""Disposable live regression for indexed Grasshopper wiring."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from rook.bridge import native_client
import pytest

from rook.server import _mcp_tool_executor


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


def _payload_with(result: Any, marker: str) -> dict[str, Any]:
    current = result
    for _ in range(4):
        if not isinstance(current, dict):
            break
        if current.get(marker) is True:
            return current
        current = current.get("data")
    pytest.fail(f"response did not contain {marker}=true: {result!r}")


def _guid(result: Any) -> str:
    current = result
    for _ in range(4):
        if not isinstance(current, dict):
            break
        for key in ("component_guid", "guid", "Guid"):
            value = current.get(key)
            if isinstance(value, str) and value:
                return value
        current = current.get("data")
    pytest.fail(f"response did not contain a component guid: {result!r}")


async def _prepare_blank_grasshopper_document(base_url: str) -> None:
    async with native_client(timeout=30.0) as client:
        open_response = await client.post(
            f"{base_url}/command",
            json={"command": "_Grasshopper"},
        )
        open_result = open_response.json()
        open_data = open_result.get("data") or {}
        command_timed_out = (
            open_result.get("success") is False
            and (
                open_data.get("code") == "native_command_timeout"
                or "timed out" in str(open_result.get("error", "")).lower()
            )
        )
        assert open_result.get("success") is True or command_timed_out, open_result

        last_status: dict[str, Any] = {}
        for _ in range(30):
            last_status = (await client.get(f"{base_url}/gh/status")).json()
            data = last_status.get("data") or {}
            if last_status.get("success") is True and data.get("available") is True:
                break
            await asyncio.sleep(0.5)
        else:
            pytest.fail(f"Grasshopper did not become available: {last_status!r}")

        new_result = (await client.post(f"{base_url}/gh/document/new", json={})).json()
        new_data = new_result.get("data") or {}
        assert new_result.get("success") is True or new_data.get("created") is True, new_result

        for _ in range(30):
            last_status = (await client.get(f"{base_url}/gh/status")).json()
            data = last_status.get("data") or {}
            ready = data.get("ready_for_edit") is True or data.get("readyForEdit") is True
            if last_status.get("success") is True and ready:
                return
            await asyncio.sleep(0.5)
        pytest.fail(f"Grasshopper did not become ready for edit: {last_status!r}")


async def _raw_post(base_url: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    async with native_client(timeout=15.0) as client:
        response = await client.post(f"{base_url}{path}", json=body)
    return response.json()


def _positive_harness_env(name: str) -> int:
    raw = os.environ.get(name)
    if raw is None:
        raise AssertionError(f"{name} must be set by scripts/run_rhino_runtime_harness.py")
    try:
        value = int(raw)
    except ValueError as exc:
        raise AssertionError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise AssertionError(f"{name} must be a positive integer")
    return value


def _require_owned_runtime_base_url() -> str:
    from rook.runtime_harness import DiscoveryError, OwnedRhinoDiscovery

    port = _positive_harness_env("ROOK_RHINO_PORT")
    pid = _positive_harness_env("ROOK_RHINO_PROCESS_ID")
    try:
        record = OwnedRhinoDiscovery().read_owned_record(pid)
    except DiscoveryError as exc:
        raise AssertionError(
            f"Could not verify owned Rhino discovery record for pid {pid}: {exc}"
        ) from exc
    if record.pid != pid or record.port != port:
        raise AssertionError(
            "ROOK_RHINO_PORT and ROOK_RHINO_PROCESS_ID do not refer to the same "
            f"owned runtime: env port {port}, discovery port {record.port}, pid {pid}"
        )
    return f"http://127.0.0.1:{port}"


async def _assert_no_preexisting_gh_documents(base_url: str) -> None:
    result = await _raw_post(
        base_url,
        "/execute",
        {
            "code": (
                "import Grasshopper\n"
                "print(len(list(Grasshopper.Instances.DocumentServer)))"
            ),
        },
    )
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    output = str(data.get("output", "")).strip()
    if result.get("success") is not True or output != "0":
        raise AssertionError(
            "Owned Rhino must have zero preexisting Grasshopper documents before "
            f"the disposable regression starts: {result!r}"
        )


async def _connections(base_url: str, guid: str) -> list[dict[str, Any]]:
    async with native_client(timeout=15.0) as client:
        response = await client.get(f"{base_url}/gh/connections", params={"guid": guid})
    envelope = response.json()
    assert envelope.get("success") is True, envelope
    return (envelope.get("data") or {}).get("inputs") or []


async def _discard_disposable_document_changes(base_url: str) -> None:
    result = await _raw_post(
        base_url,
        "/execute",
        {
            "code": (
                "import Grasshopper\n"
                "server = Grasshopper.Instances.DocumentServer\n"
                "documents = list(server)\n"
                "canvas = Grasshopper.Instances.ActiveCanvas\n"
                "if canvas is not None:\n"
                "    canvas.Document = None\n"
                "for document in documents:\n"
                "    server.RemoveDocument(document)\n"
                "    document.Dispose()"
            ),
        },
    )
    assert result.get("success") is True, result


async def _exercise_indexed_wiring(base_url: str) -> None:
    script_result = await _mcp_tool_executor(
        "gh_create_python_script",
        {
            "code": "Result = I5 + I6 + I7",
            "pins_in": [
                {"name": f"I{index}", "type": "float"}
                for index in range(8)
            ],
            "pins_out": [{"name": "Result", "type": "float"}],
            "name": "IndexedConnectionProbe",
        },
    )
    target_guid = _guid(script_result)

    sources: dict[int, str] = {}
    for index in (5, 6, 7):
        panel_result = await _mcp_tool_executor(
            "gh_create_panel",
            {"content": str(index), "x": 100, "y": 100 + index * 40},
        )
        source_guid = _guid(panel_result)
        sources[index] = source_guid

        connect_result = await _mcp_tool_executor(
            "gh_connect",
            {
                "sourceGuid": source_guid,
                "targetGuid": target_guid,
                "targetIndex": index,
            },
        )
        connected = _payload_with(connect_result, "connected")
        assert connected["target"] == {
            "guid": target_guid,
            "param": f"I{index}",
            "index": index,
        }

    connected_inputs = await _connections(base_url, target_guid)
    observed = {
        item.get("paramIndex"): len(item.get("sources") or [])
        for item in connected_inputs
    }
    assert observed == {5: 1, 6: 1, 7: 1}

    for index, source_guid in sources.items():
        disconnect_result = await _raw_post(
            base_url,
            "/gh/disconnect",
            {
                "sourceGuid": source_guid,
                "targetGuid": target_guid,
                "targetIndex": index,
            },
        )
        disconnected = _payload_with(disconnect_result, "disconnected")
        assert disconnected["target"] == {
            "guid": target_guid,
            "param": f"I{index}",
            "index": index,
        }

    assert await _connections(base_url, target_guid) == []


async def test_mcp_connect_and_raw_disconnect_honor_indices_five_through_seven():
    base_url = _require_owned_runtime_base_url()
    await _assert_no_preexisting_gh_documents(base_url)

    body_error: BaseException | None = None
    cleanup_error: BaseException | None = None
    try:
        await _prepare_blank_grasshopper_document(base_url)
        await _exercise_indexed_wiring(base_url)
    except BaseException as exc:
        body_error = exc

    try:
        await _discard_disposable_document_changes(base_url)
    except BaseException as exc:
        cleanup_error = exc

    if body_error is not None and cleanup_error is not None:
        raise BaseExceptionGroup(
            "indexed wiring regression and owned cleanup both failed",
            [body_error, cleanup_error],
        )
    if body_error is not None:
        raise body_error.with_traceback(body_error.__traceback__)
    if cleanup_error is not None:
        raise cleanup_error.with_traceback(cleanup_error.__traceback__)
