"""Disposable live regression for indexed Grasshopper wiring."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest

from rook.server import _mcp_tool_executor


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

POINT_ON_CURVE_GUID = "7f6a9d34-0470-4bb7-aadd-07496bcbe572"
CIRCLE_GUID = "807b86e3-be8d-4970-92b5-f8cdcb45b06b"


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
        initial_status = (await client.get(f"{base_url}/gh/status")).json()
        initial_data = initial_status.get("data") or {}
        has_active_canvas = (
            initial_data.get("has_active_canvas") is True
            or initial_data.get("hasActiveCanvas") is True
        )
        if not has_active_canvas:
            open_result = (
                await client.post(
                    f"{base_url}/execute",
                    json={
                        "code": (
                            "import Rhino\n"
                            "print(Rhino.RhinoApp.RunScript('_Grasshopper', False))"
                        )
                    },
                )
            ).json()
            assert open_result.get("success") is True, open_result

        last_status: dict[str, Any] = {}
        for _ in range(30):
            last_status = (await client.get(f"{base_url}/gh/status")).json()
            data = last_status.get("data") or {}
            has_active_canvas = (
                data.get("has_active_canvas") is True
                or data.get("hasActiveCanvas") is True
            )
            if last_status.get("success") is True and has_active_canvas:
                break
            await asyncio.sleep(0.5)
        else:
            pytest.fail(f"Grasshopper did not expose an active canvas: {last_status!r}")

        new_result = (await client.post(f"{base_url}/gh/document/new", json={})).json()
        new_data = new_result.get("data")
        created = isinstance(new_data, dict) and new_data.get("created") is True
        assert new_result.get("success") is True or created, new_result

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


def _response_data(result: dict[str, Any]) -> dict[str, Any]:
    assert result.get("success") is True, result
    data = result.get("data")
    assert isinstance(data, dict), result
    return data


def _field(payload: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in payload:
            return payload[name]
    pytest.fail(f"response did not contain any of {names!r}: {payload!r}")


async def _fenced_snapshot_after_edit(
    base_url: str,
    edit_result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    edit_data = _response_data(edit_result)
    receipt = edit_data.get("solve_readiness_receipt")
    assert isinstance(receipt, dict), edit_result
    receipt_id = receipt.get("receipt_id")
    assert isinstance(receipt_id, str) and receipt_id, receipt

    wait_result = await _raw_post(
        base_url,
        "/gh/wait-for-solve-readiness",
        {"readiness_receipt_id": receipt_id, "timeout_ms": 10_000},
    )
    wait_data = _response_data(wait_result)
    ready_receipt = wait_data.get("receipt")
    assert isinstance(ready_receipt, dict), wait_result
    assert ready_receipt.get("receipt_id") == receipt_id, ready_receipt
    assert ready_receipt.get("status") == "ready", ready_receipt

    snapshot_result = await _raw_post(
        base_url,
        "/gh/snapshot",
        {
            "include_data": True,
            "max_preview_items": 3,
            "readiness_receipt_id": receipt_id,
        },
    )
    snapshot_data = _response_data(snapshot_result)
    readiness_fence = snapshot_data.get("readiness_fence")
    assert isinstance(readiness_fence, dict), snapshot_data
    assert readiness_fence.get("readiness_receipt_id") == receipt_id, readiness_fence
    return snapshot_data, ready_receipt


def _find_nested_guid(result: Any, expected_guid: str) -> dict[str, Any] | None:
    if isinstance(result, dict):
        guid = result.get("guid") or result.get("component_guid")
        if isinstance(guid, str) and guid.lower() == expected_guid.lower():
            return result
        for value in result.values():
            found = _find_nested_guid(value, expected_guid)
            if found is not None:
                return found
    elif isinstance(result, list):
        for value in result:
            found = _find_nested_guid(value, expected_guid)
            if found is not None:
                return found
    return None


def _component_by_guid(snapshot: dict[str, Any], guid: str) -> dict[str, Any]:
    for component in snapshot.get("components") or []:
        component_guid = component.get("componentGuid")
        if isinstance(component_guid, str) and component_guid.lower() == guid.lower():
            return component
    pytest.fail(f"snapshot did not contain component guid {guid}: {snapshot!r}")


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
    async with httpx.AsyncClient(timeout=15.0) as client:
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


async def test_point_on_curve_parameter_rejects_i1_and_projects_confirmed_i0_flow():
    base_url = _require_owned_runtime_base_url()
    await _assert_no_preexisting_gh_documents(base_url)

    body_error: BaseException | None = None
    cleanup_error: BaseException | None = None
    try:
        await _prepare_blank_grasshopper_document(base_url)

        metadata_result = await _mcp_tool_executor(
            "gh_batch_component_info",
            {"guids": [POINT_ON_CURVE_GUID]},
        )
        metadata = _find_nested_guid(metadata_result, POINT_ON_CURVE_GUID)
        assert metadata is not None, metadata_result
        params = metadata.get("params")
        assert isinstance(params, dict), metadata
        assert params.get("isSimpleParam") is True, params
        assert [item.get("index") for item in params.get("inputs") or []] == [0], params
        assert [item.get("index") for item in params.get("outputs") or []] == [0], params

        baseline = _response_data(
            await _raw_post(base_url, "/gh/snapshot", {"include_data": False})
        )
        create_result = await _raw_post(
            base_url,
            "/gh/edit",
            {
                "epoch": baseline["epoch"],
                "create": [
                    {"temp_id": "T1", "guid": CIRCLE_GUID, "pos": [120, 120]},
                    {
                        "temp_id": "T2",
                        "guid": POINT_ON_CURVE_GUID,
                        "pos": [360, 120],
                    },
                ],
            },
        )
        created, create_receipt = await _fenced_snapshot_after_edit(base_url, create_result)
        circle = _component_by_guid(created, CIRCLE_GUID)
        point_on_curve = _component_by_guid(created, POINT_ON_CURVE_GUID)
        source_id = circle["id"]
        target_id = point_on_curve["id"]
        invalid_flow = f"{source_id}.O0>{target_id}.I1"
        valid_flow = f"{source_id}.O0>{target_id}.I0"

        invalid_result = await _raw_post(
            base_url,
            "/gh/edit",
            {"epoch": created["epoch"], "connect": [invalid_flow]},
        )
        invalid_data = _response_data(invalid_result)
        invalid_summary = invalid_data.get("edit_summary") or {}
        invalid_receipt = invalid_data.get("solve_readiness_receipt") or {}
        assert invalid_summary.get("connected") == 0, invalid_data
        assert invalid_summary.get("errors") == [
            f"connect '{invalid_flow}': Target input index 1 is out of range for 1 input"
        ], invalid_data
        assert invalid_receipt.get("reason") == "no_solve_relevant_mutation_committed"

        after_invalid = _response_data(
            await _raw_post(base_url, "/gh/snapshot", {"include_data": False})
        )
        assert invalid_flow not in (after_invalid.get("flows") or []), after_invalid
        assert valid_flow not in (after_invalid.get("flows") or []), after_invalid

        valid_result = await _raw_post(
            base_url,
            "/gh/edit",
            {"epoch": after_invalid["epoch"], "connect": [valid_flow]},
        )
        valid_data = _response_data(valid_result)
        assert (valid_data.get("edit_summary") or {}).get("connected") == 1, valid_data
        connected, valid_receipt = await _fenced_snapshot_after_edit(base_url, valid_result)
        assert valid_flow in (connected.get("flows") or []), connected

        connected_target = _component_by_guid(connected, POINT_ON_CURVE_GUID)
        assert connected_target.get("is_param") is True, connected_target
        assert [item.get("idx") for item in connected_target.get("inputs") or []] == [0]
        assert [item.get("idx") for item in connected_target.get("outputs") or []] == [0]
        assert connected_target["inputs"][0].get("sources") == 1, connected_target

        standalone_connections = await _connections(base_url, target_id)
        standalone_input = standalone_connections[0]
        assert standalone_input.get("paramIndex") == 0, standalone_input
        standalone_sources = standalone_input.get("sources") or []
        assert len(standalone_sources) == 1, standalone_input
        assert isinstance(standalone_sources[0].get("componentGuid"), str), standalone_input

        duplicate_result = await _raw_post(
            base_url,
            "/gh/edit",
            {"epoch": connected["epoch"], "connect": [valid_flow]},
        )
        duplicate_data = _response_data(duplicate_result)
        duplicate_summary = duplicate_data.get("edit_summary") or {}
        duplicate_receipt = duplicate_data.get("solve_readiness_receipt") or {}
        assert duplicate_summary.get("connected") == 0, duplicate_data
        assert duplicate_summary.get("errors") == [
            f"connect '{valid_flow}': connection already exists"
        ], duplicate_data
        assert duplicate_receipt.get("reason") == "no_solve_relevant_mutation_committed"
        after_duplicate = _response_data(
            await _raw_post(base_url, "/gh/snapshot", {"include_data": False})
        )
        assert (after_duplicate.get("flows") or []).count(valid_flow) == 1, after_duplicate

        missing_flow = f"{target_id}.O0>{source_id}.I0"
        missing_result = await _raw_post(
            base_url,
            "/gh/edit",
            {"epoch": after_duplicate["epoch"], "disconnect": [missing_flow]},
        )
        missing_data = _response_data(missing_result)
        missing_summary = missing_data.get("edit_summary") or {}
        missing_receipt = missing_data.get("solve_readiness_receipt") or {}
        assert missing_summary.get("disconnected") == 0, missing_data
        assert missing_summary.get("errors") == [
            f"disconnect '{missing_flow}': connection does not exist"
        ], missing_data
        assert missing_receipt.get("reason") == "no_solve_relevant_mutation_committed"
        after_missing = _response_data(
            await _raw_post(base_url, "/gh/snapshot", {"include_data": False})
        )
        assert valid_flow in (after_missing.get("flows") or []), after_missing
        assert missing_flow not in (after_missing.get("flows") or []), after_missing

        raw_duplicate_result = await _raw_post(
            base_url,
            "/gh/connect",
            {
                "sourceGuid": source_id,
                "sourceIndex": 0,
                "targetGuid": target_id,
                "targetIndex": 0,
            },
        )
        raw_duplicate = _response_data(raw_duplicate_result)
        assert _field(raw_duplicate, "connected", "Connected") is False, raw_duplicate
        assert _field(raw_duplicate, "noOp", "NoOp") is True, raw_duplicate
        assert _field(raw_duplicate, "reason", "Reason") == "connection_already_exists"
        after_raw_duplicate = _response_data(
            await _raw_post(base_url, "/gh/snapshot", {"include_data": False})
        )
        assert (after_raw_duplicate.get("flows") or []).count(valid_flow) == 1

        raw_missing_result = await _raw_post(
            base_url,
            "/gh/disconnect",
            {
                "sourceGuid": target_id,
                "sourceIndex": 0,
                "targetGuid": source_id,
                "targetIndex": 0,
            },
        )
        raw_missing = _response_data(raw_missing_result)
        assert _field(raw_missing, "disconnected", "Disconnected") is False, raw_missing
        assert _field(raw_missing, "noOp", "NoOp") is True, raw_missing
        assert _field(raw_missing, "reason", "Reason") == "connection_does_not_exist"
        after_raw_missing = _response_data(
            await _raw_post(base_url, "/gh/snapshot", {"include_data": False})
        )
        assert valid_flow in (after_raw_missing.get("flows") or []), after_raw_missing
        assert missing_flow not in (after_raw_missing.get("flows") or []), after_raw_missing

        artifact_dir = Path(os.environ["ROOK_HARNESS_ARTIFACT_DIR"])
        evidence = {
            "schema": "rook.live_parameter_connection_truthfulness:v1",
            "pointOnCurveGuid": POINT_ON_CURVE_GUID,
            "circleGuid": CIRCLE_GUID,
            "sourceId": source_id,
            "targetId": target_id,
            "metadataParams": params,
            "createdEpoch": created["epoch"],
            "createReceipt": create_receipt,
            "invalidAttempt": {
                "flow": invalid_flow,
                "editSummary": invalid_summary,
                "receipt": invalid_receipt,
                "epochAfter": after_invalid["epoch"],
                "flowsAfter": after_invalid.get("flows") or [],
            },
            "validAttempt": {
                "flow": valid_flow,
                "editSummary": valid_data.get("edit_summary"),
                "receipt": valid_receipt,
                "epochAfter": connected["epoch"],
                "flowsAfter": connected.get("flows") or [],
                "target": connected_target,
                "connections": standalone_connections,
            },
            "duplicateConnect": {
                "flow": valid_flow,
                "editSummary": duplicate_summary,
                "receipt": duplicate_receipt,
                "epochAfter": after_duplicate["epoch"],
                "flowsAfter": after_duplicate.get("flows") or [],
            },
            "missingDisconnect": {
                "flow": missing_flow,
                "editSummary": missing_summary,
                "receipt": missing_receipt,
                "epochAfter": after_missing["epoch"],
                "flowsAfter": after_missing.get("flows") or [],
            },
            "rawDuplicateConnect": {
                "response": raw_duplicate,
                "epochAfter": after_raw_duplicate["epoch"],
                "flowsAfter": after_raw_duplicate.get("flows") or [],
            },
            "rawMissingDisconnect": {
                "response": raw_missing,
                "epochAfter": after_raw_missing["epoch"],
                "flowsAfter": after_raw_missing.get("flows") or [],
            },
        }
        (artifact_dir / "parameter-connection-evidence.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except BaseException as exc:
        body_error = exc

    try:
        await _discard_disposable_document_changes(base_url)
    except BaseException as exc:
        cleanup_error = exc

    if body_error is not None and cleanup_error is not None:
        raise BaseExceptionGroup(
            "standalone parameter regression and owned cleanup both failed",
            [body_error, cleanup_error],
        )
    if body_error is not None:
        raise body_error.with_traceback(body_error.__traceback__)
    if cleanup_error is not None:
        raise cleanup_error.with_traceback(cleanup_error.__traceback__)
