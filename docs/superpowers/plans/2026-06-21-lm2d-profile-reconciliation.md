# LM2D — Profile Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `reconcile_profile(...)` that activates a disposable `ToolRegistry` for a profile's tier+groups, audits the active surface (LM1A), and reports intended-vs-active drift plus group-activation failures, carrying profile findings verbatim.

**Architecture:** New composition module `profile_reconciliation.py` depends on `ToolRegistry` + LM1A audit + LM2A/LM2B types. Two private helpers in `capability_inventory.py` (`_dispatch_context_from_sources`, the inline audit→`CapabilityFinding` mapping) are promoted to public (`dispatch_context_from_sources`, `capability_findings_from_audit`) so the mapping logic has one home, shared by `reconcile_active_schemas` and `reconcile_profile`.

**Tech Stack:** Python 3.12, pytest. Source under `mcp_server/src/rook/agent/`, tests under `mcp_server/tests/`.

**Spec:** `docs/superpowers/specs/2026-06-21-lm2d-profile-reconciliation-design.md`

## Global Constraints

- Read-only / diagnostic only. No surface compiler, no runtime policy, no registry-consults-profiles wiring, no PlanGraph, no `planner`/`external_mcp` semantics, no runtime-visibility/MCP wire change.
- No mutation of shared/runtime `ToolRegistry` state — build a disposable instance per call.
- `reconcile_profile` re-derives no profile facts from `sources`: intended names come only from `resolution.tool_names`; `sources` supplies the tier member set and the `DispatchContext` only.
- `resolve_profile`, `reconcile_active_schemas`, and `build_inventory` keep their observable behavior; `reconcile_active_schemas`/`build_inventory` are only refactored onto the shared public helpers.
- `execution_profile.py` stays import-light and untouched; `capability_record.py` stays stdlib-only and untouched.
- `_DISPATCHABILITY_SEVERITY` stays private; only `dispatch_context_from_sources` and `capability_findings_from_audit` become public.
- `ProfileFinding`s carried verbatim, never reinterpreted or folded into `CapabilityFinding`.
- `registry_findings` sorted by `(tool, code, severity)`; `intended_names` = `resolution.tool_names` (already sorted); `active_names` sorted. All finding outputs deterministic.
- Tier lookup never crashes: `frozenset() if initial is None else frozenset(getattr(sources, initial, frozenset()))`.
- No `format_reconciliation_report` in this slice. No live smoke.
- Tests deterministic with canned catalogs / injected sources — no live catalog, no MCP.
- Run all commands from repo root (`C:/UDEV/Rook`) via the venv interpreter `mcp_server/.venv/Scripts/python.exe`. Do NOT `cd` into `mcp_server/` (boundary probes read repo-root-relative paths). Pass `-p no:cacheprovider`.

---

### Task 1: Promote shared helpers in capability_inventory.py

**Files:**
- Modify: `mcp_server/src/rook/agent/capability_inventory.py` — rename `_dispatch_context_from_sources` (def at line 38; callers at 115, 235) → public; add `capability_findings_from_audit`; refactor `reconcile_active_schemas` (line 221) to use it; import `DispatchabilityFinding` and `Iterable`.
- Test: `mcp_server/tests/test_capability_inventory.py` — rename usage (import line 5; `test_dispatch_context_maps_all_six_fields` line ~137); add a `capability_findings_from_audit` test.

**Interfaces:**
- Consumes: existing `DispatchabilityFinding` (`rook.agent.chat.tool_contracts`), `_DISPATCHABILITY_SEVERITY`, `CapabilityFinding`.
- Produces:
  - `dispatch_context_from_sources(sources: SurfaceSources) -> DispatchContext` (renamed from `_dispatch_context_from_sources`, same body).
  - `capability_findings_from_audit(audit_findings: Iterable[DispatchabilityFinding]) -> list[CapabilityFinding]` — maps each finding's `code`/`tool`/`message`, severity via `_DISPATCHABILITY_SEVERITY.get(code, "warning")`.

- [ ] **Step 1: Update the LM2A test for the rename + add the new-helper test**

In `mcp_server/tests/test_capability_inventory.py`, change the import block (currently importing `_dispatch_context_from_sources`) to:

```python
from rook.agent.capability_inventory import (
    INTERCEPTED_META_TOOLS,
    build_inventory,
    capability_findings_from_audit,
    collect_live_sources,
    dispatch_context_from_sources,
    format_report,
    reconcile_active_schemas,
)
```

In `test_dispatch_context_maps_all_six_fields`, replace the single call `ctx = _dispatch_context_from_sources(sources)` with `ctx = dispatch_context_from_sources(sources)` (the assertions below it are unchanged).

Add this new test at the end of the file:

```python
def test_capability_findings_from_audit_maps_codes_and_severities():
    from rook.agent.chat.tool_contracts import DispatchabilityFinding

    audit = [
        DispatchabilityFinding(
            code="not_dispatchable", tool="a", classification="failure", message="m1"
        ),
        DispatchabilityFinding(
            code="missing_function_name", tool="", classification="schema", message="m2"
        ),
        DispatchabilityFinding(
            code="strict_no_arg_schema_drift",
            tool="c",
            classification="bridge_route",
            message="m3",
        ),
        DispatchabilityFinding(
            code="duplicate_visible_name", tool="d", classification="schema", message="m4"
        ),
    ]
    out = capability_findings_from_audit(audit)
    assert {(f.code, f.tool, f.severity) for f in out} == {
        ("not_dispatchable", "a", "error"),
        ("missing_function_name", "", "error"),
        ("strict_no_arg_schema_drift", "c", "error"),
        ("duplicate_visible_name", "d", "warning"),
    }
    assert [f.message for f in out] == ["m1", "m2", "m3", "m4"]
```

- [ ] **Step 2: Run the updated + new tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_inventory.py -q`
Expected: FAIL — `ImportError: cannot import name 'dispatch_context_from_sources'` / `capability_findings_from_audit` (the public names don't exist yet).

- [ ] **Step 3: Promote the dispatch-context helper**

In `mcp_server/src/rook/agent/capability_inventory.py`, rename the function definition at line 38 from `def _dispatch_context_from_sources(` to `def dispatch_context_from_sources(` (body unchanged). Update both internal callers:
- in `build_inventory` (line 115): `ctx = dispatch_context_from_sources(sources)`
- in `reconcile_active_schemas` (line 235): `ctx = dispatch_context_from_sources(sources)`

- [ ] **Step 4: Add the import and the audit-mapping helper**

In the `tool_contracts` import block (lines 20-24), add `DispatchabilityFinding`:

```python
from rook.agent.chat.tool_contracts import (
    DispatchContext,
    DispatchabilityFinding,
    audit_visible_tool_dispatchability,
    classify_visible_tool,
)
```

Add `Iterable` to the typing import (line 11): `from typing import Iterable, Literal`.

Immediately after the `_DISPATCHABILITY_SEVERITY` dict (ends line 209), add:

```python
def capability_findings_from_audit(
    audit_findings: Iterable[DispatchabilityFinding],
) -> list[CapabilityFinding]:
    """Map LM1A dispatchability findings onto CapabilityFindings with severity.

    Shared by reconcile_active_schemas and profile_reconciliation so the severity
    table has a single home. Returns a list; callers combine/sort with their own
    findings.
    """
    return [
        CapabilityFinding(
            code=finding.code,
            tool=finding.tool,
            severity=_DISPATCHABILITY_SEVERITY.get(finding.code, "warning"),
            message=finding.message,
        )
        for finding in audit_findings
    ]
```

- [ ] **Step 5: Refactor reconcile_active_schemas onto the helper**

In `reconcile_active_schemas`, replace the inline audit-mapping loop (lines 237-246, the `findings: list[...] = []` declaration plus the `for audit_finding in audit_visible_tool_dispatchability(...)` loop) with:

```python
    findings: list[CapabilityFinding] = capability_findings_from_audit(
        audit_visible_tool_dispatchability(active_schemas, ctx)
    )
```

Leave the rest of `reconcile_active_schemas` (the drift loops and the final `return tuple(_sorted_findings(findings))`) unchanged.

- [ ] **Step 6: Run the capability_inventory tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_inventory.py -q`
Expected: PASS — all existing tests (proving the refactor is behavior-preserving) plus the new `capability_findings_from_audit` test.

- [ ] **Step 7: Confirm no stale references to the old private name remain**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_record.py mcp_server/tests/test_execution_profile.py -q`
Expected: PASS (these modules never referenced the helper; this confirms nothing else broke). There should be no remaining `_dispatch_context_from_sources` anywhere — the rename is complete.

- [ ] **Step 8: Commit**

```bash
git add mcp_server/src/rook/agent/capability_inventory.py mcp_server/tests/test_capability_inventory.py
git commit -m "refactor(lm2d): promote dispatch_context_from_sources + capability_findings_from_audit"
```

---

### Task 2: profile_reconciliation module

**Files:**
- Create: `mcp_server/src/rook/agent/profile_reconciliation.py`
- Test: `mcp_server/tests/test_profile_reconciliation.py`

**Interfaces:**
- Consumes (from Task 1 / merged): `dispatch_context_from_sources`, `capability_findings_from_audit` (`rook.agent.capability_inventory`); `build_inventory` (for the seam test); `CapabilityFinding`, `SurfaceSources` (`rook.agent.capability_record`); `audit_visible_tool_dispatchability` (`rook.agent.chat.tool_contracts`); `ProfileDefinition`, `ProfileFinding`, `ProfileResolution`, `resolve_profile` (`rook.agent.execution_profile`); `ToolRegistry` (`rook.agent.tool_registry`).
- Produces:
  - `@dataclass(frozen=True) ProfileReconciliation(profile_name: str, intended_names: tuple[str, ...], active_names: tuple[str, ...], registry_findings: tuple[CapabilityFinding, ...], profile_findings: tuple[ProfileFinding, ...])`.
  - `reconcile_profile(resolution: ProfileResolution, sources: SurfaceSources, catalog: Mapping[str, dict]) -> ProfileReconciliation`.

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_profile_reconciliation.py`:

```python
from __future__ import annotations

from rook.agent.capability_inventory import build_inventory
from rook.agent.capability_record import SurfaceSources
from rook.agent.execution_profile import (
    ProfileDefinition,
    ProfileFinding,
    ProfileResolution,
    resolve_profile,
)
from rook.agent.profile_reconciliation import ProfileReconciliation, reconcile_profile


def _schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": name,
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    }


def _resolution(definition, *, tool_names=(), findings=()) -> ProfileResolution:
    # reconcile_profile reads only profile, tool_names, findings -> tools can be ().
    return ProfileResolution(
        profile=definition,
        tools=(),
        tool_names=tuple(tool_names),
        findings=tuple(findings),
    )


def _codes(rec: ProfileReconciliation):
    return {(f.code, f.tool, f.severity) for f in rec.registry_findings}


def test_clean_profile_has_no_registry_findings():
    sources = SurfaceSources(
        agent_tier0=frozenset({"gh_snapshot"}),
        bridge_names=frozenset({"gh_snapshot"}),
    )
    definition = ProfileDefinition(name="p", initial_tier="agent_tier0", groups=())
    resolution = _resolution(definition, tool_names=("gh_snapshot",))
    rec = reconcile_profile(resolution, sources, {"gh_snapshot": _schema("gh_snapshot")})
    assert rec.registry_findings == ()
    assert rec.active_names == ("gh_snapshot",)
    assert rec.intended_names == ("gh_snapshot",)


def test_intended_not_active_flagged():
    sources = SurfaceSources(
        agent_tier0=frozenset({"gh_snapshot"}),
        bridge_names=frozenset({"gh_snapshot"}),
    )
    definition = ProfileDefinition(name="p", initial_tier="agent_tier0")
    resolution = _resolution(definition, tool_names=("ghost_tool", "gh_snapshot"))
    rec = reconcile_profile(resolution, sources, {"gh_snapshot": _schema("gh_snapshot")})
    assert ("intended_not_active", "ghost_tool", "warning") in _codes(rec)


def test_active_not_intended_proves_live_tool_groups_seam():
    # sources.groups lists ONLY gh_edit for gh_canvas, so the inventory (and thus
    # resolve_profile) intends only gh_edit. The disposable ToolRegistry activates
    # gh_canvas from the LIVE TOOL_GROUPS table, which also holds gh_move present
    # in the catalog -> active_not_intended for gh_move. Not a tautology: active
    # comes from the real registry, intended from resolve_profile.
    sources = SurfaceSources(
        groups={"gh_canvas": ("gh_edit",)},
        bridge_names=frozenset({"gh_edit", "gh_move"}),
    )
    catalog = {"gh_edit": _schema("gh_edit"), "gh_move": _schema("gh_move")}
    inventory = build_inventory(sources, catalog)
    resolution = resolve_profile(
        ProfileDefinition(name="canvas", groups=("gh_canvas",)), inventory
    )
    assert resolution.tool_names == ("gh_edit",)

    rec = reconcile_profile(resolution, sources, catalog)
    assert "gh_move" in rec.active_names
    assert ("active_not_intended", "gh_move", "warning") in _codes(rec)
    assert ("active_not_intended", "gh_edit", "warning") not in _codes(rec)


def test_group_activation_failed_for_mcp_only_group():
    definition = ProfileDefinition(name="p", groups=("gh_knowledge",))
    resolution = _resolution(definition, tool_names=())
    rec = reconcile_profile(resolution, SurfaceSources(), {})
    assert ("group_activation_failed", "gh_knowledge", "warning") in _codes(rec)
    msg = next(f.message for f in rec.registry_findings if f.tool == "gh_knowledge")
    assert "MCP-only" in msg


def test_group_activation_failed_for_unknown_group():
    definition = ProfileDefinition(name="p", groups=("nonexistent_group",))
    resolution = _resolution(definition, tool_names=())
    rec = reconcile_profile(resolution, SurfaceSources(), {})
    assert ("group_activation_failed", "nonexistent_group", "warning") in _codes(rec)
    msg = next(
        f.message for f in rec.registry_findings if f.tool == "nonexistent_group"
    )
    assert "Unknown group" in msg


def test_folds_not_dispatchable_audit_finding_as_error():
    # orphan_tool is tier-active and in catalog but in no dispatch surface.
    sources = SurfaceSources(agent_tier0=frozenset({"orphan_tool"}))
    definition = ProfileDefinition(name="p", initial_tier="agent_tier0")
    resolution = _resolution(definition, tool_names=("orphan_tool",))
    rec = reconcile_profile(
        resolution, sources, {"orphan_tool": _schema("orphan_tool")}
    )
    assert ("not_dispatchable", "orphan_tool", "error") in _codes(rec)


def test_profile_findings_carried_verbatim_and_not_folded():
    pf = ProfileFinding(
        profile="p",
        code="unknown_tier",
        subject="ghost_tier",
        severity="warning",
        message="m",
    )
    definition = ProfileDefinition(name="p", initial_tier="agent_tier0")
    resolution = _resolution(definition, tool_names=(), findings=(pf,))
    rec = reconcile_profile(resolution, SurfaceSources(), {})
    assert rec.profile_findings == (pf,)
    assert all(f.code != "unknown_tier" for f in rec.registry_findings)


def test_registry_findings_sorted_and_names_sorted():
    sources = SurfaceSources(
        agent_tier0=frozenset({"b_tool", "a_tool"}),
        bridge_names=frozenset({"a_tool", "b_tool"}),
    )
    definition = ProfileDefinition(name="p", initial_tier="agent_tier0")
    resolution = _resolution(definition, tool_names=("z_tool", "m_tool"))
    catalog = {"a_tool": _schema("a_tool"), "b_tool": _schema("b_tool")}
    rec = reconcile_profile(resolution, sources, catalog)
    tools_order = [f.tool for f in rec.registry_findings]
    assert tools_order == sorted(tools_order)
    assert rec.active_names == ("a_tool", "b_tool")
    assert rec.intended_names == ("z_tool", "m_tool")  # carried from resolution verbatim


def test_initial_tier_none_uses_empty_tier_zero():
    sources = SurfaceSources(bridge_names=frozenset({"gh_edit", "gh_move"}))
    definition = ProfileDefinition(name="p", initial_tier=None, groups=("gh_canvas",))
    resolution = _resolution(definition, tool_names=("gh_edit",))
    catalog = {"gh_edit": _schema("gh_edit"), "gh_move": _schema("gh_move")}
    rec = reconcile_profile(resolution, sources, catalog)
    assert set(rec.active_names) == {"gh_edit", "gh_move"}


def test_malformed_initial_tier_yields_empty_tier_zero_no_crash():
    definition = ProfileDefinition(name="p", initial_tier="not_a_real_tier")  # type: ignore[arg-type]
    resolution = _resolution(definition, tool_names=())
    rec = reconcile_profile(resolution, SurfaceSources(), {})
    assert rec.active_names == ()
    assert isinstance(rec, ProfileReconciliation)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_profile_reconciliation.py -q`
Expected: FAIL at import (`ModuleNotFoundError: rook.agent.profile_reconciliation`).

- [ ] **Step 3: Create the module**

Create `mcp_server/src/rook/agent/profile_reconciliation.py`:

```python
"""LM2D profile reconciliation against disposable active-schema evidence.

Composition module (not import-light): activates a disposable ToolRegistry for a
profile's initial tier plus its groups, audits the active surface (LM1A), and
reports intended-vs-active drift and group-activation failures as
CapabilityFindings, carrying the profile's own ProfileFindings verbatim.

Read-only/diagnostic: no shared/runtime registry mutation, no surface compiler,
no runtime policy. It re-derives no profile facts from `sources` -- intended
names come only from `resolution.tool_names`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from rook.agent.capability_inventory import (
    capability_findings_from_audit,
    dispatch_context_from_sources,
)
from rook.agent.capability_record import CapabilityFinding, SurfaceSources
from rook.agent.chat.tool_contracts import audit_visible_tool_dispatchability
from rook.agent.execution_profile import ProfileFinding, ProfileResolution
from rook.agent.tool_registry import ToolRegistry


@dataclass(frozen=True)
class ProfileReconciliation:
    profile_name: str
    intended_names: tuple[str, ...]
    active_names: tuple[str, ...]
    registry_findings: tuple[CapabilityFinding, ...]
    profile_findings: tuple[ProfileFinding, ...]


def _active_tool_names(registry: ToolRegistry) -> frozenset[str]:
    names: set[str] = set()
    for schema in registry.get_active_schemas():
        function = schema.get("function") if isinstance(schema, dict) else None
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            names.add(function["name"])
    return frozenset(names)


def reconcile_profile(
    resolution: ProfileResolution,
    sources: SurfaceSources,
    catalog: Mapping[str, dict],
) -> ProfileReconciliation:
    definition = resolution.profile
    initial = definition.initial_tier
    tier_members = (
        frozenset()
        if initial is None
        else frozenset(getattr(sources, initial, frozenset()))
    )
    registry = ToolRegistry(catalog=dict(catalog), tier0=set(tier_members))

    findings: list[CapabilityFinding] = []
    for group in definition.groups:
        result = registry.request_group(group)
        if not result.get("success"):
            findings.append(
                CapabilityFinding(
                    code="group_activation_failed",
                    tool=group,
                    severity="warning",
                    message=result.get(
                        "error", f"Group '{group}' could not be activated."
                    ),
                )
            )

    active_schemas = registry.get_active_schemas()
    active_names = _active_tool_names(registry)
    ctx = dispatch_context_from_sources(sources)
    findings.extend(
        capability_findings_from_audit(
            audit_visible_tool_dispatchability(active_schemas, ctx)
        )
    )

    intended = frozenset(resolution.tool_names)
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

    registry_findings = tuple(
        sorted(findings, key=lambda f: (f.tool, f.code, f.severity))
    )
    return ProfileReconciliation(
        profile_name=definition.name,
        intended_names=resolution.tool_names,
        active_names=tuple(sorted(active_names)),
        registry_findings=registry_findings,
        profile_findings=resolution.findings,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_profile_reconciliation.py -q`
Expected: PASS (all ten tests).

- [ ] **Step 5: Run the full LM2 suite + py_compile**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_record.py mcp_server/tests/test_capability_inventory.py mcp_server/tests/test_execution_profile.py mcp_server/tests/test_profile_reconciliation.py -q && mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/agent/capability_inventory.py mcp_server/src/rook/agent/profile_reconciliation.py`
Expected: PASS, and `py_compile` prints nothing (success).

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/agent/profile_reconciliation.py mcp_server/tests/test_profile_reconciliation.py
git commit -m "feat(lm2d): reconcile_profile over disposable active-schema evidence"
```

---

## Self-Review

**1. Spec coverage:**
- New `profile_reconciliation.py` module + `ProfileReconciliation` + `reconcile_profile` → Task 2. ✓
- Disposable registry, tier+groups activation, group-failure findings, audit fold, drift findings, carried profile findings → Task 2 Step 3. ✓
- Promote `dispatch_context_from_sources` + `capability_findings_from_audit`, refactor `reconcile_active_schemas`, keep `_DISPATCHABILITY_SEVERITY` private → Task 1. ✓
- Tier-lookup guard (None + malformed) → Task 2 Step 3 code + tests 9-10. ✓
- Spec tests 1-10 → Task 2 Step 1 (clean, intended_not_active, active_not_intended seam, group mcp-only, group unknown, folded not_dispatchable, profile_findings verbatim, determinism, None edge, malformed edge). ✓
- LM2A test updates (rename + new helper test) → Task 1 Step 1. ✓
- "Does NOT" list (no formatter, no live smoke, no runtime policy, no shared-registry mutation) → no step adds any; Global Constraints restate. ✓

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to". Every code step shows complete code; every run step shows the exact command and expected outcome. ✓

**3. Type consistency:** `dispatch_context_from_sources`, `capability_findings_from_audit`, `reconcile_profile`, `ProfileReconciliation` field names (`profile_name`/`intended_names`/`active_names`/`registry_findings`/`profile_findings`) identical across Interfaces, implementation, and tests. `CapabilityFinding(code, tool, severity, message)` and `ProfileFinding(profile, code, subject, severity, message)` match the merged definitions. `ProfileResolution(profile, tools, tool_names, findings)` matches LM2B. Finding codes (`group_activation_failed`, `intended_not_active`, `active_not_intended`, folded LM1A codes) consistent between spec, code, and test assertions. ✓
