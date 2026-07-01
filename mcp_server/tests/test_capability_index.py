from __future__ import annotations
import ast, os, subprocess, sys
from pathlib import Path
import pytest
from rook.agent.capability_record import CapabilityRecord
from rook.capability_index import McpCapabilityRecord, CapabilityIndex


def test_record_is_frozen_and_has_fields():
    rec = McpCapabilityRecord(
        name="t", path="/x/t", domain="x", groups=(), summary="s", description="d",
        readonly_safe=True, mcp_dispatchable=True, input_schema={}, agent_record=None,
    )
    assert rec.name == "t" and rec.agent_record is None
    with pytest.raises(Exception):
        rec.name = "other"  # frozen


def test_index_indexes_by_name():
    rec = McpCapabilityRecord(
        name="t", path="/x/t", domain="x", groups=(), summary="s", description="d",
        readonly_safe=False, mcp_dispatchable=True, input_schema={}, agent_record=None,
    )
    idx = CapabilityIndex(records=(rec,), by_name={"t": rec})
    assert idx.by_name["t"] is rec


def _direct_imports(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mods.add(f'{"." * node.level}{node.module or ""}')
        elif isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
    return mods


def test_capability_index_import_boundary():
    # Allowed: CapabilityRecord type + leaf data modules. Forbidden: server,
    # capability_inventory, agent runtime.
    imports = _direct_imports("mcp_server/src/rook/capability_index.py")
    forbidden = {
        "rook.server", "rook.agent.capability_inventory",
        "rook.agent.tool_dispatcher", "rook.agent.tool_registry",
    }
    assert imports.isdisjoint(forbidden), f"forbidden imports present: {imports & forbidden}"


def test_importing_capability_index_does_not_load_server_or_inventory():
    env = os.environ.copy()
    src = str(Path("mcp_server/src").resolve())
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    probe = (
        "import sys, rook.capability_index\n"
        "bad = {'rook.server','rook.agent.capability_inventory'} & set(sys.modules)\n"
        "raise SystemExit('loaded: ' + ','.join(sorted(bad)) if bad else 0)\n"
    )
    subprocess.run([sys.executable, "-c", probe], check=True, env=env)


from types import SimpleNamespace
from rook.capability_index import build_index
from rook.mcp_tool_profiles import PUBLIC_READONLY_TOOL_NAMES


def _tool(name, desc="Do a thing. Second sentence.", schema=None):
    return SimpleNamespace(name=name, description=desc, inputSchema=schema or {"type": "object"})


def _agent_rec(name, dispatch_path="bridge_route", mcp_only=False):
    return CapabilityRecord(name=name, visibility="local_visible", tiers=(), groups=(),
                            dispatch_path=dispatch_path, has_schema=True, risk=(),
                            no_argument=False, mcp_only=mcp_only)


def test_build_index_covers_all_tools_and_links_agent_records():
    tools = [_tool("rhino_director_preview_motion"), _tool("rhino_objects")]
    agent = {"rhino_objects": _agent_rec("rhino_objects")}
    idx = build_index(tools, agent, frozenset({"rhino_director_preview_motion", "rhino_objects"}))
    assert {r.name for r in idx.records} == {"rhino_director_preview_motion", "rhino_objects"}
    assert idx.by_name["rhino_objects"].agent_record.name == "rhino_objects"   # linked by name
    assert idx.by_name["rhino_director_preview_motion"].agent_record is None    # absent -> None


def test_readonly_safe_matches_audited_allowlist():
    name = next(iter(PUBLIC_READONLY_TOOL_NAMES))
    idx = build_index([_tool(name), _tool("rhino_create")], {}, frozenset({name, "rhino_create"}))
    assert idx.by_name[name].readonly_safe is True
    assert idx.by_name["rhino_create"].readonly_safe is False


def test_mcp_dispatchable_is_from_dispatchable_names_not_agent_mcp_only():
    # A tool with agent_mcp_only=True but NOT in dispatchable_names must be mcp_dispatchable=False,
    # and vice-versa — the two axes never derive from each other.
    tools = [_tool("a"), _tool("b")]
    agent = {"a": _agent_rec("a", mcp_only=True), "b": _agent_rec("b", mcp_only=False)}
    idx = build_index(tools, agent, frozenset({"b"}))  # only b is dispatchable
    assert idx.by_name["a"].mcp_dispatchable is False and idx.by_name["a"].agent_record.mcp_only is True
    assert idx.by_name["b"].mcp_dispatchable is True and idx.by_name["b"].agent_record.mcp_only is False


def test_build_index_tolerates_empty_agent_records():
    idx = build_index([_tool("x")], {}, frozenset({"x"}))
    assert idx.by_name["x"].agent_record is None  # LM2A "unavailable" still yields a working index


def test_summary_is_first_sentence():
    idx = build_index([_tool("x", desc="First. Second.")], {}, frozenset({"x"}))
    assert idx.by_name["x"].summary == "First."
