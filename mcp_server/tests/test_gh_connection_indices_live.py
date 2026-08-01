"""Disposable live regression for indexed Grasshopper wiring."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from rook.bridge import get_rhino_host
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
    async with httpx.AsyncClient(timeout=30.0) as client:
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
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(f"{base_url}{path}", json=body)
    return response.json()


async def _connections(base_url: str, guid: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(f"{base_url}/gh/connections", params={"guid": guid})
    envelope = response.json()
    assert envelope.get("success") is True, envelope
    return (envelope.get("data") or {}).get("inputs") or []


async def test_mcp_connect_and_raw_disconnect_honor_indices_five_through_seven():
    base_url = get_rhino_host(endpoint="/gh/status")
    assert base_url is not None, "owned RookNative endpoint was not discoverable"
    await _prepare_blank_grasshopper_document(base_url)

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
