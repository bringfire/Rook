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
