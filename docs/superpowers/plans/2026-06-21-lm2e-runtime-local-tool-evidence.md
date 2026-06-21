# LM2E — Runtime-Faithful Local-Tool Dispatch Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `collect_runtime_sources()` — a runtime-enriched surface snapshot that fills `local_tool_names` from the actual local tools in this runtime — so the LM2D visible-implies-dispatchable audit stops emitting false `not_dispatchable` for local-handler tools.

**Architecture:** `collect_runtime_sources()` lives beside the unchanged `collect_live_sources()` in `capability_inventory.py`. It returns `dataclasses.replace(collect_live_sources(), local_tool_names=frozenset(td.build_local_tools().keys()))` with a lazy `tool_dispatcher` import and no `ToolDispatcher` instantiation. The live-smoke `surface` command switches to it. Read-only / diagnostic only.

**Tech Stack:** Python 3.12 stdlib (`dataclasses`), pytest. Source under `mcp_server/src/rook/agent/`, tests under `mcp_server/tests/`, smoke under `scripts/`.

**Spec:** `docs/superpowers/specs/2026-06-21-lm2e-runtime-local-tool-evidence-design.md`

## Global Constraints

- Read-only / diagnostic only. No runtime, visibility, or policy change; no MCP wire change.
- `collect_live_sources()` behavior/output is **unchanged** (static, import-light, `local_tool_names` stays empty).
- `collect_runtime_sources()` lazily imports `tool_dispatcher` **inside the function only** — no module-top dispatcher import. It must **not** instantiate `ToolDispatcher`.
- Unexpected `build_local_tools()` failure **propagates** out of `collect_runtime_sources()` (plain exception, no custom type) — never a silently-empty `local_tool_names`.
- `classify_visible_tool`, the LM1A audit, `build_inventory`, `reconcile_profile`, and the LM2A–D modules are otherwise untouched.
- **Test patch targets (critical):** patch `rook.agent.capability_inventory.collect_live_sources` (the module global the function calls) and `rook.agent.tool_dispatcher.build_local_tools` (the attribute the lazy `from rook.agent import tool_dispatcher as td; td.build_local_tools()` resolves at call time). Do **not** patch a re-bound symbol the lazy import would bypass. The real heavy `build_local_tools()` is never called in unit tests.
- Run all commands from repo root (`C:/UDEV/Rook`) via the venv interpreter `mcp_server/.venv/Scripts/python.exe`, with `-p no:cacheprovider`. Do NOT `cd` into `mcp_server/`.

---

### Task 1: `collect_runtime_sources()` + tests + audit-path proof

**Files:**
- Modify: `mcp_server/src/rook/agent/capability_inventory.py` — add `import dataclasses` (after line 8); append `collect_runtime_sources()` at end of file (after `collect_live_sources`, which ends at EOF).
- Test: `mcp_server/tests/test_capability_inventory.py` — add `import dataclasses` + `import pytest` to top imports; add tests 1–2.
- Test: `mcp_server/tests/test_profile_reconciliation.py` — add the paired audit-path proof (tests 4–5).

**Interfaces:**
- Consumes: `collect_live_sources() -> SurfaceSources`; `rook.agent.tool_dispatcher.build_local_tools() -> dict[str, Any]`; `SurfaceSources` (frozen dataclass); existing `ProfileDefinition`, `ProfileResolution`, `reconcile_profile`, and the `_schema`/`_resolution` test helpers.
- Produces: `collect_runtime_sources() -> SurfaceSources` — `collect_live_sources()` with `local_tool_names` replaced by `frozenset(build_local_tools().keys())`.

- [ ] **Step 1: Write the failing collector unit tests**

In `mcp_server/tests/test_capability_inventory.py`, add `import dataclasses` and `import pytest` near the top of the file (with the other imports). Then add:

```python
def test_collect_runtime_sources_enriches_local_tool_names(monkeypatch):
    import rook.agent.capability_inventory as ci
    import rook.agent.tool_dispatcher as td

    base = SurfaceSources(
        agent_tier0=frozenset({"a"}),
        bridge_names=frozenset({"a"}),
    )
    # Patch the module global the function calls, and the lazy-import target
    # (td.build_local_tools is resolved as an attribute at call time).
    monkeypatch.setattr(ci, "collect_live_sources", lambda: base)
    monkeypatch.setattr(td, "build_local_tools", lambda: {"loc1": object(), "loc2": object()})

    out = ci.collect_runtime_sources()
    assert out.local_tool_names == frozenset({"loc1", "loc2"})
    # enriched, not rebuilt: every other field identical to base
    assert dataclasses.replace(out, local_tool_names=frozenset()) == base


def test_collect_runtime_sources_propagates_builder_failure(monkeypatch):
    import rook.agent.capability_inventory as ci
    import rook.agent.tool_dispatcher as td

    monkeypatch.setattr(ci, "collect_live_sources", lambda: SurfaceSources())

    def _boom():
        raise RuntimeError("builder exploded")

    monkeypatch.setattr(td, "build_local_tools", _boom)
    with pytest.raises(RuntimeError):
        ci.collect_runtime_sources()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_inventory.py -k collect_runtime_sources -q`
Expected: FAIL — `AttributeError: module 'rook.agent.capability_inventory' has no attribute 'collect_runtime_sources'`.

- [ ] **Step 3: Add the import and the collector**

In `mcp_server/src/rook/agent/capability_inventory.py`, add `import dataclasses` to the stdlib imports (immediately after `from __future__ import annotations` on line 8):

```python
from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Iterable, Literal
```

Then append `collect_runtime_sources()` at the very end of the file (after the `collect_live_sources()` `return` block):

```python
def collect_runtime_sources() -> SurfaceSources:
    """Runtime-enriched surface snapshot.

    collect_live_sources() plus the ACTUAL local tools dispatchable in THIS
    runtime (build_local_tools().keys()). Diagnostic runtime evidence -- NOT a
    static registry or policy source, and intentionally environment-dependent
    (a local tool whose optional import fails is faithfully absent, so it is
    genuinely not dispatchable here).

    An unexpected build_local_tools() failure propagates; this never silently
    returns empty local_tool_names. Per-tool optional-import failures are
    handled inside build_local_tools() itself.
    """
    from rook.agent import tool_dispatcher as td  # lazy, like collect_live_sources

    base = collect_live_sources()
    local_names = frozenset(td.build_local_tools().keys())
    return dataclasses.replace(base, local_tool_names=local_names)
```

- [ ] **Step 4: Run the collector tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_inventory.py -k collect_runtime_sources -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Write the failing audit-path proof**

In `mcp_server/tests/test_profile_reconciliation.py`, add (it reuses the existing `_schema` and `_resolution` helpers and the already-imported `SurfaceSources`, `ProfileDefinition`, `reconcile_profile`):

```python
def test_local_tool_names_clears_not_dispatchable_on_audit_path():
    # x is tier-active and in the catalog; its ONLY dispatch route is the local
    # handler. With x in local_tool_names the LM2D audit must NOT flag
    # not_dispatchable; without it the false positive returns -> proves the
    # enrichment is load-bearing on reconcile_profile's audit path.
    definition = ProfileDefinition(name="p", initial_tier="agent_tier0")
    resolution = _resolution(definition, tool_names=("x",))
    catalog = {"x": _schema("x")}

    enriched = SurfaceSources(
        agent_tier0=frozenset({"x"}),
        local_tool_names=frozenset({"x"}),
    )
    rec = reconcile_profile(resolution, enriched, catalog)
    assert not any(
        f.code == "not_dispatchable" and f.tool == "x" for f in rec.registry_findings
    )

    bare = SurfaceSources(agent_tier0=frozenset({"x"}))
    rec_bare = reconcile_profile(resolution, bare, catalog)
    assert any(
        f.code == "not_dispatchable" and f.tool == "x" for f in rec_bare.registry_findings
    )
```

- [ ] **Step 6: Run the audit-path proof to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_profile_reconciliation.py::test_local_tool_names_clears_not_dispatchable_on_audit_path -v`
Expected: PASS. (The positive branch: `x` classifies `dispatcher_local_tool` → no finding. The negative branch: empty `local_tool_names` → `x` classifies `failure` → `not_dispatchable` error. This passes immediately because it exercises existing `reconcile_profile`/`classify_visible_tool` behavior; it is the load-bearing justification for the collector and guards against regressions.)

- [ ] **Step 7: Run both touched test modules + py_compile**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_inventory.py mcp_server/tests/test_profile_reconciliation.py -q && mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/agent/capability_inventory.py`
Expected: PASS (all existing tests — including the unchanged `test_collect_live_sources_*` back-compat tests proving `collect_live_sources` still returns empty `local_tool_names` — plus the 3 new ones). `py_compile` prints nothing.

- [ ] **Step 8: Commit**

```bash
git add mcp_server/src/rook/agent/capability_inventory.py mcp_server/tests/test_capability_inventory.py mcp_server/tests/test_profile_reconciliation.py
git commit -m "feat(lm2e): collect_runtime_sources enriches local_tool_names from build_local_tools"
```

---

### Task 2: Smoke `surface` uses the runtime collector

**Files:**
- Modify: `scripts/lm_surface_smoke.py:189` (import) and `:207` (call site) inside `run_surface()`.

**Interfaces:**
- Consumes: `collect_runtime_sources()` from Task 1.
- Produces: nothing (diagnostic script behavior change only).

- [ ] **Step 1: Switch the import**

In `scripts/lm_surface_smoke.py`, change the `capability_inventory` import inside `run_surface()` (line 189):

```python
    from rook.agent.capability_inventory import build_inventory, collect_runtime_sources
```

- [ ] **Step 2: Use the runtime collector with explicit failure handling**

Replace the `sources = collect_live_sources()` line (line 207) with:

```python
    try:
        sources = collect_runtime_sources()
    except Exception as exc:
        _p("FAIL", f"collect_runtime_sources() failed: {exc!r}")
        return 1
    print(f"  local tools (runtime-enriched): {len(sources.local_tool_names)}")
```

(The following `inventory = build_inventory(sources, catalog)` line and everything after it are unchanged.)

- [ ] **Step 3: Verify the script compiles and the runtime-free tests still pass**

Run: `mcp_server/.venv/Scripts/python.exe -m py_compile scripts/lm_surface_smoke.py && mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_lm_surface_smoke.py -q`
Expected: `py_compile` silent; the 9 smoke tests PASS unchanged (they cover the pure helpers, the PYTHONPATH gate, and the parser — none import `collect_runtime_sources`, and `run_surface`'s deployed-runtime path is exercised only by the live run, not unit tests).

- [ ] **Step 4: Commit**

```bash
git add scripts/lm_surface_smoke.py
git commit -m "feat(lm2e): smoke surface uses collect_runtime_sources + prints enriched local-tool count"
```

---

## Self-Review

**1. Spec coverage:**
- Unit 1 `collect_runtime_sources()` (lazy import, no instantiation, `dataclasses.replace`, propagation) → Task 1 Step 3. ✓
- `collect_live_sources()` unchanged → no step modifies it; the existing `test_collect_live_sources_*` tests run in Task 1 Step 7 as the back-compat proof. ✓
- Failure propagation (not silent-empty) → Task 1 test 2 + the collector's plain propagation. ✓
- Audit-path paired proof (`reconcile_profile(...).registry_findings`, positive + negative) → Task 1 Steps 5–6. ✓
- Enrich/identity test (`dataclasses.replace(out, ...) == base`) → Task 1 test 1. ✓
- Patch targets (`capability_inventory.collect_live_sources`, `tool_dispatcher.build_local_tools`) → Global Constraints + the test code. ✓
- Unit 2 smoke switch + enriched count line + FAIL-on-raise → Task 2. ✓
- Invariants (no module-top dispatcher import; no instantiation; diagnostic only) → Global Constraints; the collector's lazy import + `dataclasses.replace` honor them. ✓

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to". Every code step shows complete code; every run step shows the exact command and expected outcome. ✓

**3. Type consistency:** `collect_runtime_sources` name/return type identical across spec, collector, smoke import, and tests. `build_local_tools` patched at `rook.agent.tool_dispatcher.build_local_tools` consistently. `SurfaceSources(local_tool_names=...)`, `ProfileDefinition(name, initial_tier)`, `ProfileResolution` via `_resolution(definition, tool_names=...)`, and `CapabilityFinding.code`/`.tool` on `registry_findings` all match the merged LM2A–D definitions. ✓
