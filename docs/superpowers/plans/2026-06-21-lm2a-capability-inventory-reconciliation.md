# LM2A Capability Inventory Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only capability inventory and reconciliation report over Rook's existing RookChat/local tool-surface sources, without changing any runtime behavior.

**Architecture:** A stdlib-only `capability_record.py` holds the data types; a `capability_inventory.py` builder reads an injected `SurfaceSources` snapshot + catalog into capability records (static layer), and reconciles intended membership against a disposable canned-catalog `ToolRegistry` (reconciliation layer), reusing the LM1A dispatchability audit over active schemas only. Unknowns become explicit findings; nothing mutates runtime visibility.

**Tech Stack:** Python 3.12, pytest, existing `rook.agent.tool_registry`, `rook.agent.tool_groups`, `rook.agent.tool_dispatcher`, `rook.agent.chat.execution_policy`, `rook.agent.chat.tool_contracts`. Tests run via `mcp_server/.venv`.

## Global Constraints

- `capability_record.py` is **stdlib-only**: imports only `dataclasses`, `typing`, `collections.abc`. It must NOT import `tool_contracts`, `tool_dispatcher`, or `DispatchContext` (importing `tool_contracts` pulls `tool_dispatcher` at module load).
- `capability_inventory.py` may import `capability_record`, `tool_groups`, `tool_dispatcher`, `execution_policy`, `tool_registry`, `tool_contracts`.
- Read-only only: no mutation of runtime/shared tool visibility; no replacement of `ToolRegistry`; no `execution_profile`; no PlanGraph; no MCP wire change; no file writes; no live Rhino/GH.
- `collect_live_sources()` reads module constants only — never `agent_tool_catalog.json`, MCP `list_tools`, a live/shared `ToolRegistry`, or a `ToolDispatcher` instance; it leaves `local_tool_names` empty.
- `reconcile_active_schemas(...)` builds a **disposable** `ToolRegistry` from a **canned** catalog only and may call `request_group` on it; never the live cache, MCP, or a shared registry.
- `audit_visible_tool_dispatchability(...)` runs over **active schemas from the disposable registry only**, never the whole catalog. It stays a diagnostic; it is not wired as a new gate.
- The `intercepted_names` canonical set is `{request_tools, search_tools, ui_block, list_chat_models, set_chat_model}`.
- `dispatch_unknown` severity is provenance-aware: `error` for `local_visible`, `info` for `mcp_only_visible`, `warning` for `support_only`. No invented defaults — unknowns are explicit findings.
- All tuple outputs (`tiers`, `groups`, `risk`, `records`) are sorted; `findings` are sorted by `(tool, code, severity)`.
- `CapabilityFinding.severity` is `Literal["info", "warning", "error"]`.
- Run all commands from `C:/UDEV/Rook`. Python: `mcp_server/.venv/Scripts/python.exe`.

---

### Task 1: `capability_record.py` — stdlib-only types + boundary probes

**Files:**
- Create: `mcp_server/src/rook/agent/capability_record.py`
- Test: `mcp_server/tests/test_capability_record.py`

**Interfaces:**
- Produces:
  - `Visibility = Literal["local_visible", "mcp_only_visible", "support_only"]`
  - `Severity = Literal["info", "warning", "error"]`
  - `SurfaceSources` (frozen dataclass) — fields per Step 3 below; all `frozenset[str]` default empty, `groups: Mapping[str, tuple[str, ...]]` defaults to `{}`.
  - `CapabilityRecord(name, visibility, tiers, groups, dispatch_path, has_schema, risk, no_argument, mcp_only)` (frozen).
  - `CapabilityFinding(code, tool, severity, message)` (frozen).
  - `CapabilityInventory(records: tuple[CapabilityRecord, ...], findings: tuple[CapabilityFinding, ...])` (frozen).

- [ ] **Step 1: Write the failing construction + frozen test**

Create `mcp_server/tests/test_capability_record.py`:

```python
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
)


def test_surface_sources_defaults_are_empty():
    sources = SurfaceSources()
    assert sources.tier0 == frozenset()
    assert sources.groups == {}
    assert sources.local_tool_names == frozenset()


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_record.py -q`
Expected: collection/import error — `ModuleNotFoundError: No module named 'rook.agent.capability_record'`.

- [ ] **Step 3: Implement the stdlib-only record module**

Create `mcp_server/src/rook/agent/capability_record.py`:

```python
"""LM2A capability record types (stdlib-only).

Plain frozen dataclasses describing the read-only capability inventory. This
module must stay stdlib-only: it must not import tool_contracts or
tool_dispatcher. The DispatchContext mapping for the LM1A audit lives in
capability_inventory.py instead.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

Visibility = Literal["local_visible", "mcp_only_visible", "support_only"]
Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class SurfaceSources:
    tier0: frozenset[str] = frozenset()
    agent_tier0: frozenset[str] = frozenset()
    readonly_tier0: frozenset[str] = frozenset()
    groups: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    mcp_only_groups: frozenset[str] = frozenset()
    bridge_names: frozenset[str] = frozenset()
    transform_names: frozenset[str] = frozenset()
    intercepted_names: frozenset[str] = frozenset()
    excluded_names: frozenset[str] = frozenset()
    local_tool_names: frozenset[str] = frozenset()
    zero_argument_names: frozenset[str] = frozenset()
    strict_no_argument_names: frozenset[str] = frozenset()
    creation_tools: frozenset[str] = frozenset()
    modal_risk_tools: frozenset[str] = frozenset()
    needs_verification: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CapabilityRecord:
    name: str
    visibility: Visibility
    tiers: tuple[str, ...]
    groups: tuple[str, ...]
    dispatch_path: str | None
    has_schema: bool
    risk: tuple[str, ...]
    no_argument: bool
    mcp_only: bool


@dataclass(frozen=True)
class CapabilityFinding:
    code: str
    tool: str
    severity: Severity
    message: str


@dataclass(frozen=True)
class CapabilityInventory:
    records: tuple[CapabilityRecord, ...]
    findings: tuple[CapabilityFinding, ...]
```

- [ ] **Step 4: Write the import-boundary probes**

Append to `mcp_server/tests/test_capability_record.py`:

```python
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
```

- [ ] **Step 5: Run the full record test file to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_record.py -q`
Expected: PASS (5 tests passed).

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/agent/capability_record.py mcp_server/tests/test_capability_record.py
git commit -m "feat(lm2a): stdlib-only capability record types

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `capability_inventory.py` — static inventory layer

**Files:**
- Create: `mcp_server/src/rook/agent/capability_inventory.py`
- Test: `mcp_server/tests/test_capability_inventory.py`

**Interfaces:**
- Consumes: `SurfaceSources`, `CapabilityRecord`, `CapabilityFinding`, `CapabilityInventory`, `Visibility` from `rook.agent.capability_record` (Task 1); `DispatchContext`, `classify_visible_tool` from `rook.agent.chat.tool_contracts`.
- Produces:
  - `INTERCEPTED_META_TOOLS: frozenset[str]`
  - `_dispatch_context_from_sources(sources: SurfaceSources) -> DispatchContext`
  - `build_inventory(sources: SurfaceSources, catalog: Mapping[str, dict]) -> CapabilityInventory`
  - `format_report(inventory: CapabilityInventory) -> str`
  - `_sorted_findings(findings: list[CapabilityFinding]) -> list[CapabilityFinding]` (used by Task 3)

- [ ] **Step 1: Write the failing static-layer tests**

Create `mcp_server/tests/test_capability_inventory.py`:

```python
from __future__ import annotations

from rook.agent.capability_record import CapabilityInventory, SurfaceSources
from rook.agent.capability_inventory import (
    INTERCEPTED_META_TOOLS,
    _dispatch_context_from_sources,
    build_inventory,
    format_report,
)


def _schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"{name} tool",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    }


def _static_sources() -> SurfaceSources:
    return SurfaceSources(
        agent_tier0=frozenset({"request_tools", "gh_snapshot"}),
        readonly_tier0=frozenset({"rhino_objects"}),
        groups={
            "gh_canvas": ("gh_edit", "gh_move"),
            "gh_knowledge": ("gh_knowledge_query",),
            "rhino_geometry": ("rhino_create",),
            "dual_group": ("dual_tool",),
            "gh_patterns": ("dual_tool",),
        },
        mcp_only_groups=frozenset({"gh_knowledge", "gh_patterns"}),
        bridge_names=frozenset(
            {"gh_edit", "gh_move", "gh_snapshot", "rhino_objects", "rhino_create"}
        ),
        intercepted_names=INTERCEPTED_META_TOOLS,
        zero_argument_names=frozenset({"gh_snapshot"}),
        strict_no_argument_names=frozenset({"gh_snapshot"}),
        creation_tools=frozenset({"gh_edit"}),
        needs_verification=frozenset({"gh_edit"}),
    )


def _static_catalog() -> dict:
    # NOTE: "gh_edit" intentionally absent -> missing_schema for a local_visible tool.
    return {
        name: _schema(name)
        for name in (
            "gh_snapshot",
            "gh_move",
            "rhino_objects",
            "rhino_create",
            "gh_knowledge_query",
            "dual_tool",
            "request_tools",
        )
    }


def _finding_keys(inventory: CapabilityInventory):
    return {(f.code, f.tool, f.severity) for f in inventory.findings}


def test_build_inventory_emits_expected_findings():
    inv = build_inventory(_static_sources(), _static_catalog())

    assert _finding_keys(inv) == {
        ("dispatch_unknown", "dual_tool", "error"),
        ("contradictory_membership", "dual_tool", "error"),
        ("dispatch_unknown", "gh_knowledge_query", "info"),
        ("missing_schema", "gh_edit", "warning"),
    }


def test_build_inventory_records_cover_full_universe_sorted():
    inv = build_inventory(_static_sources(), _static_catalog())
    names = [r.name for r in inv.records]

    assert names == sorted(names)
    assert set(names) == {
        "request_tools", "search_tools", "ui_block", "list_chat_models",
        "set_chat_model", "gh_snapshot", "gh_move", "rhino_objects",
        "rhino_create", "gh_edit", "gh_knowledge_query", "dual_tool",
    }


def test_intercepted_meta_tools_are_not_dispatch_unknown():
    inv = build_inventory(_static_sources(), _static_catalog())
    by_name = {r.name: r for r in inv.records}

    for meta in ("request_tools", "search_tools", "ui_block", "list_chat_models", "set_chat_model"):
        assert by_name[meta].dispatch_path == "chatrunner_intercepted"
    assert not any(
        f.code == "dispatch_unknown" and f.tool in INTERCEPTED_META_TOOLS
        for f in inv.findings
    )


def test_record_fields_are_sorted_and_provenance_correct():
    inv = build_inventory(_static_sources(), _static_catalog())
    by_name = {r.name: r for r in inv.records}

    gh_edit = by_name["gh_edit"]
    assert gh_edit.visibility == "local_visible"
    assert gh_edit.dispatch_path == "bridge_route"
    assert gh_edit.has_schema is False
    assert gh_edit.risk == ("creation", "needs_verification")  # sorted-stable order
    assert gh_edit.mcp_only is False

    knowledge = by_name["gh_knowledge_query"]
    assert knowledge.visibility == "mcp_only_visible"
    assert knowledge.mcp_only is True

    snap = by_name["gh_snapshot"]
    assert snap.no_argument is True
    assert snap.tiers == ("agent_tier0",)


def test_dispatch_context_maps_all_six_fields():
    sources = SurfaceSources(
        intercepted_names=frozenset({"a"}),
        local_tool_names=frozenset({"b"}),
        transform_names=frozenset({"c"}),
        bridge_names=frozenset({"d"}),
        excluded_names=frozenset({"e"}),
        strict_no_argument_names=frozenset({"f"}),
    )
    ctx = _dispatch_context_from_sources(sources)
    assert ctx.intercepted_names == frozenset({"a"})
    assert ctx.local_tool_names == frozenset({"b"})
    assert ctx.transform_names == frozenset({"c"})
    assert ctx.bridge_names == frozenset({"d"})
    assert ctx.excluded_names == frozenset({"e"})
    assert ctx.strict_no_argument_names == frozenset({"f"})


def test_format_report_is_pure_and_stable():
    inv = build_inventory(_static_sources(), _static_catalog())
    first = format_report(inv)
    second = format_report(inv)
    assert first == second
    assert first.startswith("Capability inventory: 12 records, 4 findings")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_inventory.py -q`
Expected: collection/import error — `ModuleNotFoundError: No module named 'rook.agent.capability_inventory'`.

- [ ] **Step 3: Implement the static inventory layer**

Create `mcp_server/src/rook/agent/capability_inventory.py`:

```python
"""LM2A capability inventory and reconciliation (read-only).

Builds capability records from an injected SurfaceSources snapshot plus a
catalog (static layer), and reconciles intended membership against a disposable
canned-catalog ToolRegistry (reconciliation layer). Changes no runtime behavior.
"""

from __future__ import annotations

from collections.abc import Mapping

from rook.agent.capability_record import (
    CapabilityFinding,
    CapabilityInventory,
    CapabilityRecord,
    SurfaceSources,
    Visibility,
)
from rook.agent.chat.tool_contracts import (
    DispatchContext,
    classify_visible_tool,
)

INTERCEPTED_META_TOOLS: frozenset[str] = frozenset(
    {"request_tools", "search_tools", "ui_block", "list_chat_models", "set_chat_model"}
)

_DISPATCH_UNKNOWN_SEVERITY = {
    "local_visible": "error",
    "mcp_only_visible": "info",
    "support_only": "warning",
}


def _dispatch_context_from_sources(sources: SurfaceSources) -> DispatchContext:
    return DispatchContext(
        intercepted_names=frozenset(sources.intercepted_names),
        local_tool_names=frozenset(sources.local_tool_names),
        transform_names=frozenset(sources.transform_names),
        bridge_names=frozenset(sources.bridge_names),
        excluded_names=frozenset(sources.excluded_names),
        strict_no_argument_names=frozenset(sources.strict_no_argument_names),
    )


def _sorted_findings(findings: list[CapabilityFinding]) -> list[CapabilityFinding]:
    return sorted(findings, key=lambda f: (f.tool, f.code, f.severity))


def _tiers_for(name: str, sources: SurfaceSources) -> tuple[str, ...]:
    out: list[str] = []
    if name in sources.tier0:
        out.append("tier0")
    if name in sources.agent_tier0:
        out.append("agent_tier0")
    if name in sources.readonly_tier0:
        out.append("readonly_tier0")
    return tuple(out)


def _groups_for(name: str, sources: SurfaceSources) -> tuple[str, ...]:
    return tuple(
        sorted(g for g, tools in sources.groups.items() if name in tools)
    )


def _risk_for(name: str, sources: SurfaceSources) -> tuple[str, ...]:
    out: list[str] = []
    if name in sources.creation_tools:
        out.append("creation")
    if name in sources.modal_risk_tools:
        out.append("modal_risk")
    if name in sources.needs_verification:
        out.append("needs_verification")
    return tuple(out)


def _visibility(
    name: str, sources: SurfaceSources, groups: tuple[str, ...]
) -> tuple[Visibility, bool, bool]:
    in_tier = bool(_tiers_for(name, sources))
    mcp_groups = [g for g in groups if g in sources.mcp_only_groups]
    non_mcp_groups = [g for g in groups if g not in sources.mcp_only_groups]
    mcp_only = bool(groups) and not non_mcp_groups
    contradictory = bool(mcp_groups) and bool(non_mcp_groups)
    if in_tier or non_mcp_groups:
        visibility: Visibility = "local_visible"
    elif groups:
        visibility = "mcp_only_visible"
    else:
        visibility = "support_only"
    return visibility, mcp_only, contradictory


def _universe(sources: SurfaceSources, catalog: Mapping[str, dict]) -> list[str]:
    names: set[str] = set()
    names |= set(sources.tier0) | set(sources.agent_tier0) | set(sources.readonly_tier0)
    for tools in sources.groups.values():
        names |= set(tools)
    names |= set(sources.bridge_names) | set(sources.transform_names)
    names |= set(sources.intercepted_names) | set(sources.excluded_names)
    names |= set(sources.local_tool_names)
    names |= set(sources.creation_tools) | set(sources.modal_risk_tools)
    names |= set(sources.needs_verification)
    names |= set(catalog.keys())
    return sorted(names)


def build_inventory(
    sources: SurfaceSources, catalog: Mapping[str, dict]
) -> CapabilityInventory:
    ctx = _dispatch_context_from_sources(sources)
    records: list[CapabilityRecord] = []
    findings: list[CapabilityFinding] = []

    for name in _universe(sources, catalog):
        groups = _groups_for(name, sources)
        tiers = _tiers_for(name, sources)
        risk = _risk_for(name, sources)
        visibility, mcp_only, contradictory = _visibility(name, sources, groups)
        classification = classify_visible_tool(name, ctx)
        dispatch_path = None if classification == "failure" else classification
        has_schema = name in catalog
        no_argument = (
            name in sources.zero_argument_names
            or name in sources.strict_no_argument_names
        )

        records.append(
            CapabilityRecord(
                name=name,
                visibility=visibility,
                tiers=tiers,
                groups=groups,
                dispatch_path=dispatch_path,
                has_schema=has_schema,
                risk=risk,
                no_argument=no_argument,
                mcp_only=mcp_only,
            )
        )

        if dispatch_path is None:
            findings.append(
                CapabilityFinding(
                    code="dispatch_unknown",
                    tool=name,
                    severity=_DISPATCH_UNKNOWN_SEVERITY[visibility],
                    message=(
                        f"No dispatch/intercept/transform/bridge/exclusion path "
                        f"for '{name}'."
                    ),
                )
            )
        if visibility == "local_visible" and not has_schema:
            findings.append(
                CapabilityFinding(
                    code="missing_schema",
                    tool=name,
                    severity="warning",
                    message=f"Locally-visible tool '{name}' has no catalog schema.",
                )
            )
        if contradictory:
            findings.append(
                CapabilityFinding(
                    code="contradictory_membership",
                    tool=name,
                    severity="error",
                    message=(
                        f"Tool '{name}' is in both an MCP-only group and a "
                        f"non-MCP group."
                    ),
                )
            )

    return CapabilityInventory(
        records=tuple(records),
        findings=tuple(_sorted_findings(findings)),
    )


def format_report(inventory: CapabilityInventory) -> str:
    counts = {"error": 0, "warning": 0, "info": 0}
    for finding in inventory.findings:
        counts[finding.severity] += 1
    lines = [
        f"Capability inventory: {len(inventory.records)} records, "
        f"{len(inventory.findings)} findings",
        f"  errors={counts['error']} warnings={counts['warning']} "
        f"info={counts['info']}",
    ]
    for finding in inventory.findings:
        lines.append(
            f"  [{finding.severity}] {finding.code} {finding.tool}: "
            f"{finding.message}"
        )
    return "\n".join(lines)
```

- [ ] **Step 4: Run the static-layer tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_inventory.py -q`
Expected: PASS (6 tests passed).

- [ ] **Step 5: Compile-check the new module**

Run: `mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/agent/capability_inventory.py`
Expected: no output, exit 0.

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/agent/capability_inventory.py mcp_server/tests/test_capability_inventory.py
git commit -m "feat(lm2a): static capability inventory layer

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: reconciliation layer + live collector

**Files:**
- Modify: `mcp_server/src/rook/agent/capability_inventory.py` (append reconciliation + collector)
- Modify: `mcp_server/tests/test_capability_inventory.py` (append reconciliation + collector tests)

**Interfaces:**
- Consumes: `build_inventory` helpers and `_dispatch_context_from_sources`, `_sorted_findings`, `INTERCEPTED_META_TOOLS` from Task 2; `audit_visible_tool_dispatchability` from `tool_contracts`; `ToolRegistry` from `tool_registry`; `tool_groups`, `tool_dispatcher`, `execution_policy` constants.
- Produces:
  - `reconcile_active_schemas(sources, catalog, *, group=None, initial="agent_tier0") -> tuple[CapabilityFinding, ...]`
  - `collect_live_sources() -> SurfaceSources`

- [ ] **Step 1: Write the failing reconciliation tests**

Append to `mcp_server/tests/test_capability_inventory.py`:

```python
import rook.agent.tool_registry as tool_registry_module
from rook.agent.capability_inventory import (
    collect_live_sources,
    reconcile_active_schemas,
)


def _reconcile_sources(gh_canvas_members: tuple[str, ...]) -> SurfaceSources:
    return SurfaceSources(
        agent_tier0=frozenset({"request_tools", "search_tools", "gh_snapshot"}),
        groups={"gh_canvas": gh_canvas_members},
        mcp_only_groups=frozenset(),
        bridge_names=frozenset({"gh_snapshot", "gh_edit", "gh_move"}),
        intercepted_names=INTERCEPTED_META_TOOLS,
    )


def _reconcile_catalog(extra: dict | None = None) -> dict:
    catalog = {name: _schema(name) for name in ("gh_snapshot", "gh_edit", "gh_move")}
    if extra:
        catalog.update(extra)
    return catalog


def test_reconcile_initial_surface_is_clean():
    findings = reconcile_active_schemas(
        _reconcile_sources(("gh_edit", "gh_move")), _reconcile_catalog(), group=None
    )
    assert findings == ()


def test_reconcile_group_activates_real_members_cleanly():
    findings = reconcile_active_schemas(
        _reconcile_sources(("gh_edit", "gh_move")),
        _reconcile_catalog(),
        group="gh_canvas",
    )
    assert findings == ()


def test_reconcile_flags_intended_member_absent_from_catalog():
    # gh_status is a real gh_canvas member but absent from the canned catalog,
    # so request_group cannot activate it -> intended_not_active.
    findings = reconcile_active_schemas(
        _reconcile_sources(("gh_edit", "gh_move", "gh_status")),
        _reconcile_catalog(),
        group="gh_canvas",
    )
    keys = {(f.code, f.tool, f.severity) for f in findings}
    assert ("intended_not_active", "gh_status", "warning") in keys


def test_reconcile_audit_runs_over_active_schemas_only():
    # mystery_tool is tier-active but has no dispatch path -> not_dispatchable.
    # ghost_tool is catalog-only and never active -> produces no finding.
    sources = SurfaceSources(
        agent_tier0=frozenset({"mystery_tool"}),
        intercepted_names=INTERCEPTED_META_TOOLS,
    )
    catalog = {"mystery_tool": _schema("mystery_tool"), "ghost_tool": _schema("ghost_tool")}
    findings = reconcile_active_schemas(sources, catalog, group=None)
    keys = {(f.code, f.tool, f.severity) for f in findings}
    assert ("not_dispatchable", "mystery_tool", "error") in keys
    assert not any(f.tool == "ghost_tool" for f in findings)


def test_reconcile_does_not_read_live_catalog_cache(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("reconcile must not read the live catalog cache")

    monkeypatch.setattr(tool_registry_module, "load_catalog_from_cache", _boom)
    monkeypatch.setattr(tool_registry_module, "get_catalog_cache_path", _boom)
    findings = reconcile_active_schemas(
        _reconcile_sources(("gh_edit", "gh_move")), _reconcile_catalog(), group=None
    )
    assert findings == ()


def test_collect_live_sources_reads_constants_only(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("collect_live_sources must not load the catalog cache")

    monkeypatch.setattr(tool_registry_module, "load_catalog_from_cache", _boom)
    monkeypatch.setattr(tool_registry_module, "get_catalog_cache_path", _boom)

    sources = collect_live_sources()
    assert isinstance(sources, SurfaceSources)
    assert sources.intercepted_names == INTERCEPTED_META_TOOLS
    assert sources.local_tool_names == frozenset()
    assert "gh_snapshot" in sources.bridge_names or "gh_snapshot" in sources.agent_tier0
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider "mcp_server/tests/test_capability_inventory.py::test_reconcile_initial_surface_is_clean" -q`
Expected: FAIL — `ImportError: cannot import name 'reconcile_active_schemas'` (and `collect_live_sources`).

- [ ] **Step 3: Implement the reconciliation layer + collector**

Append to `mcp_server/src/rook/agent/capability_inventory.py`:

```python
from typing import Literal

from rook.agent.chat.tool_contracts import audit_visible_tool_dispatchability
from rook.agent.tool_registry import ToolRegistry

_DISPATCHABILITY_SEVERITY = {
    "not_dispatchable": "error",
    "missing_function_name": "error",
    "strict_no_arg_schema_drift": "error",
    "duplicate_visible_name": "warning",
}


def _active_tool_names(registry: ToolRegistry) -> frozenset[str]:
    names: set[str] = set()
    for schema in registry.get_active_schemas():
        function = schema.get("function") if isinstance(schema, dict) else None
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            names.add(function["name"])
    return frozenset(names)


def reconcile_active_schemas(
    sources: SurfaceSources,
    catalog: Mapping[str, dict],
    *,
    group: str | None = None,
    initial: Literal["tier0", "agent_tier0", "readonly_tier0"] = "agent_tier0",
) -> tuple[CapabilityFinding, ...]:
    selected_tier = frozenset(getattr(sources, initial))
    registry = ToolRegistry(catalog=dict(catalog), tier0=set(selected_tier))
    if group is not None:
        registry.request_group(group)

    active_schemas = registry.get_active_schemas()
    active_names = _active_tool_names(registry)
    ctx = _dispatch_context_from_sources(sources)

    findings: list[CapabilityFinding] = []
    for audit_finding in audit_visible_tool_dispatchability(active_schemas, ctx):
        findings.append(
            CapabilityFinding(
                code=audit_finding.code,
                tool=audit_finding.tool,
                severity=_DISPATCHABILITY_SEVERITY.get(audit_finding.code, "warning"),
                message=audit_finding.message,
            )
        )

    if group is None:
        intended = selected_tier
    else:
        intended = selected_tier | frozenset(sources.groups.get(group, ()))

    for name in sorted(intended - active_names):
        findings.append(
            CapabilityFinding(
                code="intended_not_active",
                tool=name,
                severity="warning",
                message=f"Intended tool '{name}' is not in the active schema set.",
            )
        )
    for name in sorted(active_names - intended):
        findings.append(
            CapabilityFinding(
                code="active_not_intended",
                tool=name,
                severity="warning",
                message=f"Active tool '{name}' is not in the intended set.",
            )
        )

    return tuple(_sorted_findings(findings))


def collect_live_sources() -> SurfaceSources:
    """Read module constants only. No catalog cache, no MCP, no live ToolRegistry,
    no ToolDispatcher instantiation. local_tool_names is left empty."""
    from rook.agent import tool_groups as tg
    from rook.agent import tool_dispatcher as td
    from rook.agent.chat import execution_policy as ep

    return SurfaceSources(
        tier0=frozenset(tg.TIER_0),
        agent_tier0=frozenset(tg.AGENT_TIER_0),
        readonly_tier0=frozenset(tg.READONLY_TIER_0),
        groups={g: tuple(tools) for g, tools in tg.TOOL_GROUPS.items()},
        mcp_only_groups=frozenset(tg.MCP_ONLY_GROUPS),
        bridge_names=frozenset(td.BRIDGE_ROUTES.keys()),
        transform_names=frozenset(td.TRANSFORM_FUNCTIONS.keys()),
        intercepted_names=INTERCEPTED_META_TOOLS,
        excluded_names=frozenset(tg.LOCAL_TIER_0_DISPATCH_EXCLUSIONS),
        local_tool_names=frozenset(),
        zero_argument_names=frozenset(td.STRICT_NO_ARGUMENT_BRIDGE_TOOLS),
        strict_no_argument_names=frozenset(td.STRICT_NO_ARGUMENT_BRIDGE_TOOLS),
        creation_tools=frozenset(ep.CREATION_TOOLS),
        modal_risk_tools=frozenset(ep.MODAL_RISK_TOOLS),
        needs_verification=frozenset(ep.NEEDS_VERIFICATION),
    )
```

- [ ] **Step 4: Run the full inventory test file to verify everything passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_inventory.py -q`
Expected: PASS (12 tests passed).

- [ ] **Step 5: Run the whole LM2A suite + py_compile**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_record.py mcp_server/tests/test_capability_inventory.py -q`
Expected: PASS (17 tests passed).

Run: `mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/agent/capability_record.py mcp_server/src/rook/agent/capability_inventory.py`
Expected: no output, exit 0.

- [ ] **Step 6: Whitespace check**

Run: `git diff --check`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add mcp_server/src/rook/agent/capability_inventory.py mcp_server/tests/test_capability_inventory.py
git commit -m "feat(lm2a): reconciliation layer and live source collector

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage** (against `docs/superpowers/specs/2026-06-21-lm2a-capability-inventory-reconciliation-design.md`):

- Stdlib-only `capability_record.py` with the four types → Task 1.
- `capability_record.py` does not import `tool_contracts`/`tool_dispatcher`; subprocess probe → Task 1 Steps 4–5.
- `SurfaceSources` shape (all fields) → Task 1 Step 3.
- `_dispatch_context_from_sources` total mapping (moved out of the record module) → Task 2 Step 3; test Task 2 Step 1.
- `build_inventory` universe, per-record derivation, provenance-aware `dispatch_unknown` severity, `missing_schema`, `contradictory_membership`, no invented defaults → Task 2 Step 3; tests Task 2 Step 1.
- `intercepted_names` canonical set incl. `request_tools`/`search_tools` not `dispatch_unknown` → Task 2 (`INTERCEPTED_META_TOOLS`) + `test_intercepted_meta_tools_are_not_dispatch_unknown`.
- `mcp_only` group-derived, contradictory not collapsed → `_visibility` + `test_build_inventory_emits_expected_findings`.
- `reconcile_active_schemas` with explicit `initial` tier via `ToolRegistry(tier0=...)`, `group=None` initial surface and post-`request_group`, intended = selected_tier (`|` group members), LM1A audit over active schemas only → Task 3 Step 3; tests Task 3 Step 1.
- LM1A `DispatchabilityFinding` severity mapping → `_DISPATCHABILITY_SEVERITY`.
- ToolRegistry group caveat (canned catalog uses real `gh_canvas` members) → `_reconcile_catalog`/`_reconcile_sources` use real members (`gh_edit`, `gh_move`, `gh_status`).
- `collect_live_sources` reads constants only, leaves `local_tool_names` empty, no cache/MCP/registry/dispatcher → Task 3 Step 3; `test_collect_live_sources_reads_constants_only`.
- `reconcile` does not read live cache → `test_reconcile_does_not_read_live_catalog_cache`.
- `format_report` pure/secondary → Task 2 + `test_format_report_is_pure_and_stable`.
- Deterministic ordering (sorted records, findings by `(tool, code, severity)`) → `_sorted_findings`, `_universe` sorted; `test_build_inventory_records_cover_full_universe_sorted`.

No gaps found.

**2. Placeholder scan:** No TBD/TODO, no "add error handling", no "write tests for the above", no "similar to Task N". All module and test code is shown in full. Real `gh_canvas` members are used verbatim from `tool_groups.py:401-413`. Risk-set names (`CREATION_TOOLS`, `MODAL_RISK_TOOLS`, `NEEDS_VERIFICATION`) verified in `execution_policy.py:50,63,69`. `ToolRegistry(catalog=, tier0=)` and `get_active_schemas`/`request_group` verified in `tool_registry.py:132-319`.

**3. Type consistency:** `SurfaceSources`, `CapabilityRecord`, `CapabilityFinding`, `CapabilityInventory`, `Visibility`, `Severity` are defined once in Task 1 and consumed unchanged in Tasks 2–3. `_dispatch_context_from_sources`, `_sorted_findings`, `INTERCEPTED_META_TOOLS`, `build_inventory`, `format_report` are defined in Task 2 and reused by name in Task 3. `reconcile_active_schemas(sources, catalog, *, group=None, initial="agent_tier0")` and `collect_live_sources()` signatures match the spec and the Task 3 interfaces block. `request_group` and `get_active_schemas` match the real `ToolRegistry` API. The `Literal` import for `initial` is added in the Task 3 append block.
