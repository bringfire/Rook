from __future__ import annotations

import ast
from pathlib import Path

import pytest

from rook import server, targeting


PROCESS_START_TICKS = "638918000000000000"
GH_DOCUMENT_ID = "01234567-89ab-cdef-0123-456789abcdef"


@pytest.fixture(autouse=True)
def _reset_targeting() -> None:
    targeting.reset_targeting_state_for_tests()
    yield
    targeting.reset_targeting_state_for_tests()


def _initialize_full_panel_lock() -> None:
    targeting.initialize_from_environment(
        {
            "ROOK_MCP_TARGET_MODE": "panel_locked",
            "ROOK_MCP_TOOL_PROFILE": "full",
            "ROOK_MCP_TARGET_PROCESS_ID": "7101",
            "ROOK_MCP_TARGET_PROCESS_START_UTC_TICKS": PROCESS_START_TICKS,
            "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
            "ROOK_MCP_TARGET_GRASSHOPPER_DOCUMENT_ID": GH_DOCUMENT_ID,
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("gh_document_new", {}),
        ("gh_document_open", {"path": "C:/fixtures/other.gh"}),
        ("gh_learn_directory", {"directory": "C:/fixtures"}),
    ],
)
async def test_panel_locked_full_refuses_document_switch_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    arguments: dict,
) -> None:
    _initialize_full_panel_lock()
    calls: list[tuple] = []

    def fail_route(*args, **kwargs):
        calls.append(("route", args, kwargs))
        raise AssertionError("target routing occurred")

    async def fail_dispatch(*args, **kwargs):
        calls.append(("dispatch", args, kwargs))
        raise AssertionError("nested GH dispatch occurred")

    monkeypatch.setattr(targeting, "resolve_tool_route", fail_route)
    monkeypatch.setattr(server, "call_rhino", fail_dispatch)

    result = await server.call_tool(tool_name, arguments, _public_mcp=True)

    assert result.isError is True
    assert result.structuredContent == {
        "success": False,
        "data": {
            "error": "panel_grasshopper_document_locked",
            "tool": tool_name,
        },
    }
    assert calls == []


def test_v1_document_switch_audit_matches_direct_and_transitive_dispatch() -> None:
    source_path = Path(server.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    switchers: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.match_case):
            continue
        pattern = node.pattern
        if not isinstance(pattern, ast.MatchValue) or not isinstance(pattern.value, ast.Constant):
            continue
        tool_name = pattern.value.value
        if not isinstance(tool_name, str):
            continue
        for call in (child for child in ast.walk(node) if isinstance(child, ast.Call)):
            if not (
                isinstance(call.func, ast.Name)
                and call.func.id == "call_rhino"
                and call.args
                and isinstance(call.args[0], ast.Constant)
            ):
                continue
            endpoint = call.args[0].value
            if endpoint in {"/gh/document/open", "/gh/document/new"}:
                switchers.add(tool_name)

    assert switchers == {"gh_document_new", "gh_document_open", "gh_learn_directory"}
    assert targeting.PANEL_LOCKED_GH_DOCUMENT_SWITCH_TOOLS == frozenset(switchers)
