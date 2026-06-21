from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from rook.agent.capability_record import (
    CapabilityFinding,
    CapabilityInventory,
    CapabilityRecord,
    SurfaceSources,
    TIER_FIELDS,
)


def test_surface_sources_defaults_are_empty():
    sources = SurfaceSources()
    assert sources.tier0 == frozenset()
    assert sources.groups == {}
    assert sources.local_tool_names == frozenset()


def test_surface_sources_readonly_allowed_groups_defaults_empty():
    assert SurfaceSources().readonly_allowed_groups == frozenset()


def test_capability_record_is_frozen():
    record = CapabilityRecord(
        name="t",
        visibility="local_visible",
        tiers=("agent_tier0",),
        groups=("gh_canvas",),
        dispatch_path="bridge_route",
        has_schema=True,
        risk=("creation",),
        no_argument=False,
        mcp_only=False,
    )
    with pytest.raises(Exception):
        record.name = "other"  # frozen dataclass rejects assignment


def test_inventory_holds_records_and_findings():
    finding = CapabilityFinding(
        code="dispatch_unknown", tool="t", severity="error", message="m"
    )
    inv = CapabilityInventory(records=(), findings=(finding,))
    assert inv.findings[0].severity == "error"
    assert inv.records == ()


def _direct_import_modules(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            modules.add(f"{prefix}{node.module or ''}")
    return modules


def test_capability_record_is_stdlib_only():
    imports = _direct_import_modules(
        "mcp_server/src/rook/agent/capability_record.py"
    )
    assert "rook.agent.chat.tool_contracts" not in imports
    assert "rook.agent.tool_dispatcher" not in imports
    assert imports <= {"__future__", "collections.abc", "dataclasses", "typing"}


def test_importing_capability_record_does_not_load_tool_dispatcher():
    env = os.environ.copy()
    src_path = str(Path("mcp_server/src").resolve())
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )
    probe = (
        "import sys\n"
        "import rook.agent.capability_record\n"
        "if 'rook.agent.tool_dispatcher' in sys.modules:\n"
        "    raise SystemExit('rook.agent.tool_dispatcher loaded')\n"
    )
    subprocess.run([sys.executable, "-c", probe], check=True, env=env)


def test_surface_sources_planner_fields_default_empty():
    s = SurfaceSources()
    assert s.planner_tier0 == frozenset()
    assert s.planner_allowed_groups == frozenset()


def test_tier_fields_are_all_surface_sources_fields():
    import dataclasses

    names = {f.name for f in dataclasses.fields(SurfaceSources)}
    assert set(TIER_FIELDS) <= names
    assert TIER_FIELDS == ("tier0", "agent_tier0", "readonly_tier0", "planner_tier0")
