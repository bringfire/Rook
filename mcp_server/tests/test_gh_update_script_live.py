"""Live-Rhino coverage for the `gh_update_script` MCP tool.

These tests exercise C# script updates end-to-end through the MCP dispatcher
against a running Rhino + Grasshopper session with Rook loaded. They are marked
`requires_rhino` and should only be run explicitly in a throwaway live session.

Run from repo root, with Rhino open, Grasshopper open, and Rook loaded:
    pytest -m requires_rhino mcp_server/tests/test_gh_update_script_live.py
"""

from __future__ import annotations

from typing import Any

import pytest

from .conftest import _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


def _get_guid(result: Any) -> str | None:
    """Extract a component GUID from a GH tool response shape."""
    if not isinstance(result, dict):
        return None
    for key in ("component_guid", "guid", "Guid"):
        val = result.get(key)
        if isinstance(val, str) and val:
            return val
    data = result.get("data")
    if isinstance(data, dict):
        for key in ("component_guid", "guid", "Guid"):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val
    return None


def _get_data(result: Any) -> dict[str, Any]:
    data = result.get("data") if isinstance(result, dict) else None
    assert isinstance(data, dict), f"unexpected tool response: {result!r}"
    return data


def _get_script_source(result: Any) -> str:
    data = _get_data(result)
    for key in ("script", "Script", "source", "Source"):
        val = data.get(key)
        if isinstance(val, str):
            return val
    raise AssertionError(f"no script source in gh_set_script response: {result!r}")


async def _create_csharp_script(name: str, x: int, y: int) -> str:
    from rook.server import _mcp_tool_executor

    result = await _mcp_tool_executor(
        "gh_create_script",
        {
            "language": "csharp",
            "code": "A = Convert.ToDouble(R);",
            "pins_in": [{"name": "R", "type": "double"}],
            "pins_out": [{"name": "A", "type": "double"}],
            "name": name,
            "x": x,
            "y": y,
        },
    )
    assert not _is_error(result), f"gh_create_script failed: {result!r}"

    guid = _get_guid(result)
    assert isinstance(guid, str) and guid, f"no component guid in response: {result!r}"
    return guid


async def test_gh_update_script_csharp_body_end_to_end():
    from rook.server import _mcp_tool_executor

    guid = await _create_csharp_script("UpdateBodyCSLive", 520, 300)

    result = await _mcp_tool_executor(
        "gh_update_script",
        {
            "guid": guid,
            "code": "A = Convert.ToDouble(R) * 3.0;",
            "mode": "body",
            "language": "csharp",
        },
    )

    assert not _is_error(result), f"gh_update_script body update failed: {result!r}"
    data = _get_data(result)
    assert data["mode_used"] == "body"
    assert data["wrapped"] is True
    assert data["detected_language"] == "csharp"
    assert data["component_errors"] == []
    assert any(pin.get("name") == "A" for pin in data["outputs_used"])


async def test_gh_update_script_csharp_full_source_round_trip():
    from rook.server import _mcp_tool_executor

    guid = await _create_csharp_script("UpdateFullSourceCSLive", 720, 300)
    read_result = await _mcp_tool_executor("gh_set_script", {"guid": guid})
    assert not _is_error(read_result), f"gh_set_script raw read failed: {read_result!r}"
    source = _get_script_source(read_result)
    changed_source = source.replace(
        "A = Convert.ToDouble(R);",
        "A = Convert.ToDouble(R) * 4.0;",
        1,
    )
    assert changed_source != source, f"expected generated C# body was absent: {source!r}"

    result = await _mcp_tool_executor(
        "gh_update_script",
        {
            "guid": guid,
            "code": changed_source,
            "mode": "full_source",
            "language": "csharp",
        },
    )

    assert not _is_error(result), f"gh_update_script full_source failed: {result!r}"
    data = _get_data(result)
    assert data["mode_used"] == "full_source"
    assert data["wrapped"] is False
    assert data["component_errors"] == []

    verify_result = await _mcp_tool_executor("gh_set_script", {"guid": guid})
    assert not _is_error(verify_result), (
        f"gh_set_script raw read after full_source update failed: {verify_result!r}"
    )
    assert "A = Convert.ToDouble(R) * 4.0;" in _get_script_source(verify_result)


async def test_gh_update_script_csharp_compile_error_reports_hint():
    from rook.server import _mcp_tool_executor

    guid = await _create_csharp_script("UpdateCompileErrorCSLive", 920, 300)
    cleanup_error: Any = None

    try:
        result = await _mcp_tool_executor(
            "gh_update_script",
            {
                "guid": guid,
                "code": "A = N;",
                "mode": "body",
                "language": "csharp",
            },
        )

        assert not _is_error(result), (
            "compile errors should be returned in success data, "
            f"not as MCP errors: {result!r}"
        )
        data = _get_data(result)
        assert data["component_errors"]
        hint = data.get("recovery_hint")
        assert isinstance(hint, str)
        assert "Current inputs" in hint
        assert "gh_set_script_pins" in hint
    finally:
        cleanup = await _mcp_tool_executor(
            "gh_update_script",
            {
                "guid": guid,
                "code": "A = Convert.ToDouble(R);",
                "mode": "body",
                "language": "csharp",
                "check_errors": False,
            },
        )
        if _is_error(cleanup):
            cleanup_error = cleanup

    if cleanup_error is not None:
        pytest.fail(f"failed to restore compile-error test component: {cleanup_error!r}")
