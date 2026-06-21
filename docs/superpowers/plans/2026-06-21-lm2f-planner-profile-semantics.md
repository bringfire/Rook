# LM2F — Planner Profile Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `planner` as a first-class, evidence-backed diagnostic execution profile (from the runtime's `PLANNER_TIER_0` / `PLANNER_ALLOWED_GROUPS`), mirroring LM2C's `readonly`.

**Architecture:** Two new `SurfaceSources` fields carry planner evidence; `collect_live_sources()` populates them from `rook.agent.planner` (probed light); `_tiers_for` recognizes `planner_tier0`; `execution_profile.py` gains `planner_profile_from_sources` / `planner_excluded_mcp_only_groups` and a tier-only `planner` default seed; `profile_reconciliation._TIER_FIELDS` learns `planner_tier0` so the disposable registry activates the planner tier. Read-only / diagnostic.

**Tech Stack:** Python 3.12 stdlib, pytest. Source under `mcp_server/src/rook/agent/`, tests under `mcp_server/tests/`.

**Spec:** `docs/superpowers/specs/2026-06-21-lm2f-planner-profile-semantics-design.md`

## Global Constraints

- Read-only / diagnostic only. No runtime/visibility/policy change; no MCP wire change.
- **SPEC CORRECTION (carry into implementation):** the spec said `reconcile_profile` needs no changes — it does. `profile_reconciliation._TIER_FIELDS` (line 27) gates the tier lookup; `planner_tier0` MUST be added to it, or `reconcile_profile` treats the planner tier as empty.
- Planner evidence comes from `rook.agent.planner.PLANNER_TIER_0` and `PLANNER_ALLOWED_GROUPS` (cheap static set literals). Importing `rook.agent.planner` is light (no `dspy`/`litellm`/`base_agent`). Do NOT relocate the constants; do NOT use `PLANNER_LOCAL_CATALOG`.
- `planner_profile_from_sources` formula: `groups = (planner_allowed_groups & groups.keys()) - mcp_only_groups`. `planner_excluded_mcp_only_groups = planner_allowed_groups & mcp_only_groups` (full intersection, not `groups.keys()`-filtered).
- The `planner` entry in `default_profile_definitions()` is a **diagnostic, tier-only seed** (`initial_tier="planner_tier0"`, `groups=()`), NOT runtime policy — the docstring says so; the evidence-backed one with groups is `planner_profile_from_sources`.
- `_tiers_for` output stays `tuple(sorted(...))` — a tool in both `readonly_tier0` and `planner_tier0` yields `("planner_tier0","readonly_tier0")`, no declaration-order drift.
- The planner reconcile test uses runtime-style `local_tool_names` (LM2E) so local-handler-backed planner-tier tools (`gh_knowledge_query`, `knowledge_query`, `rhino_knowledge_query`) are not falsely `not_dispatchable`.
- `execution_profile.py` import allow-list unchanged (`planner_profile_from_sources` reads only `SurfaceSources`). `planner.py` unchanged. `external_mcp`/`rookchat_cloud` out of scope.
- Run all commands from repo root (`C:/UDEV/Rook`) via `mcp_server/.venv/Scripts/python.exe`, with `-p no:cacheprovider`. Do NOT `cd` into `mcp_server/`.

---

### Task 1: Planner evidence carrier + collector + tier recognition

**Files:**
- Modify: `mcp_server/src/rook/agent/capability_record.py` — 2 `SurfaceSources` fields (after `readonly_tier0:23` and after `readonly_allowed_groups:26`).
- Modify: `mcp_server/src/rook/agent/capability_inventory.py` — `_tiers_for` branch (after line 62); `collect_live_sources` lazy planner import + 2 populations (after `readonly_allowed_groups=` line 304).
- Test: `mcp_server/tests/test_capability_record.py`, `mcp_server/tests/test_capability_inventory.py`.

**Interfaces:**
- Consumes: `rook.agent.planner.PLANNER_TIER_0`, `PLANNER_ALLOWED_GROUPS`.
- Produces: `SurfaceSources.planner_tier0: frozenset[str]`, `SurfaceSources.planner_allowed_groups: frozenset[str]` (both defaulted `frozenset()`); inventory records' `.tiers` include `"planner_tier0"` for planner-tier tools.

- [ ] **Step 1: Write the failing record + collector + tier tests**

In `mcp_server/tests/test_capability_record.py`, add:

```python
def test_surface_sources_planner_fields_default_empty():
    s = SurfaceSources()
    assert s.planner_tier0 == frozenset()
    assert s.planner_allowed_groups == frozenset()
```

In `mcp_server/tests/test_capability_inventory.py`, add (it already imports `SurfaceSources`, `build_inventory`, `collect_live_sources`, `tool_registry_module`, and has a `_schema` helper):

```python
def test_collect_live_sources_carries_planner_evidence(monkeypatch):
    from rook.agent.planner import PLANNER_ALLOWED_GROUPS, PLANNER_TIER_0

    def _boom(*args, **kwargs):
        raise AssertionError("collect_live_sources must not load the catalog cache")

    monkeypatch.setattr(tool_registry_module, "load_catalog_from_cache", _boom)
    monkeypatch.setattr(tool_registry_module, "get_catalog_cache_path", _boom)

    sources = collect_live_sources()
    assert sources.planner_tier0 == frozenset(PLANNER_TIER_0)
    assert sources.planner_allowed_groups == frozenset(PLANNER_ALLOWED_GROUPS)


def test_tiers_for_planner_and_readonly_is_sorted():
    # A tool in BOTH readonly_tier0 and planner_tier0 must yield a sorted tuple
    # (no declaration-order drift).
    sources = SurfaceSources(
        readonly_tier0=frozenset({"dual"}),
        planner_tier0=frozenset({"dual"}),
    )
    inv = build_inventory(sources, {"dual": _schema("dual")})
    record = {r.name: r for r in inv.records}["dual"]
    assert record.tiers == ("planner_tier0", "readonly_tier0")


def test_collect_live_sources_stays_light_no_planner_machinery():
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = os.environ.copy()
    src_path = str(Path("mcp_server/src").resolve())
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )
    probe = (
        "import sys\n"
        "from rook.agent.capability_inventory import collect_live_sources\n"
        "collect_live_sources()\n"
        "heavy = [m for m in ('dspy', 'litellm', 'rook.agent.base_agent') "
        "if m in sys.modules]\n"
        "if heavy:\n"
        "    raise SystemExit('heavy modules loaded by collect_live_sources: ' + repr(heavy))\n"
    )
    subprocess.run([sys.executable, "-c", probe], check=True, env=env)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_record.py mcp_server/tests/test_capability_inventory.py -k "planner or tiers_for_planner or stays_light" -q`
Expected: FAIL — `SurfaceSources` has no `planner_tier0` attribute.

- [ ] **Step 3: Add the two SurfaceSources fields**

In `mcp_server/src/rook/agent/capability_record.py`, add `planner_tier0` immediately after `readonly_tier0`:

```python
    readonly_tier0: frozenset[str] = frozenset()
    planner_tier0: frozenset[str] = frozenset()
    groups: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
```

and `planner_allowed_groups` immediately after `readonly_allowed_groups`:

```python
    readonly_allowed_groups: frozenset[str] = frozenset()
    planner_allowed_groups: frozenset[str] = frozenset()
    bridge_names: frozenset[str] = frozenset()
```

(The `groups`/`bridge_names` lines already exist — shown only to anchor the insertions.)

- [ ] **Step 4: Add the `_tiers_for` planner branch**

In `mcp_server/src/rook/agent/capability_inventory.py`, in `_tiers_for`, add the planner branch before the `return`:

```python
    if name in sources.readonly_tier0:
        out.append("readonly_tier0")
    if name in sources.planner_tier0:
        out.append("planner_tier0")
    return tuple(sorted(out))
```

- [ ] **Step 5: Populate planner evidence in `collect_live_sources`**

In `collect_live_sources()`, add the lazy planner import alongside the existing lazy imports:

```python
    from rook.agent import planner as _planner
```

and add the two populations immediately after the `readonly_allowed_groups=` line:

```python
        readonly_allowed_groups=frozenset(tg.READONLY_ALLOWED_GROUPS),
        planner_tier0=frozenset(_planner.PLANNER_TIER_0),
        planner_allowed_groups=frozenset(_planner.PLANNER_ALLOWED_GROUPS),
        bridge_names=frozenset(td.BRIDGE_ROUTES.keys()),
```

(The `bridge_names=` line already exists — shown only to anchor the insertion.)

- [ ] **Step 6: Run the Task 1 tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_record.py mcp_server/tests/test_capability_inventory.py -q`
Expected: PASS (all existing LM2A tests plus the 4 new ones, including the subprocess light-import probe and the both-tiers-sorted assertion).

- [ ] **Step 7: Commit**

```bash
git add mcp_server/src/rook/agent/capability_record.py mcp_server/src/rook/agent/capability_inventory.py mcp_server/tests/test_capability_record.py mcp_server/tests/test_capability_inventory.py
git commit -m "feat(lm2f): carry planner tier+group evidence into SurfaceSources"
```

---

### Task 2: Planner profile builder + seed + reconcile tier recognition

**Files:**
- Modify: `mcp_server/src/rook/agent/execution_profile.py` — `ProfileDefinition.initial_tier` Literal (line 25); `default_profile_definitions` planner seed (190-211); add `planner_profile_from_sources` + `planner_excluded_mcp_only_groups` (after `readonly_excluded_mcp_only_groups`, ~242).
- Modify: `mcp_server/src/rook/agent/profile_reconciliation.py:27` — add `"planner_tier0"` to `_TIER_FIELDS`.
- Test: `mcp_server/tests/test_execution_profile.py`, `mcp_server/tests/test_profile_reconciliation.py`.

**Interfaces:**
- Consumes (Task 1): `SurfaceSources.planner_tier0`, `.planner_allowed_groups`; records carrying `"planner_tier0"` in `.tiers`.
- Produces:
  - `planner_profile_from_sources(sources) -> ProfileDefinition` (`name="planner"`, `initial_tier="planner_tier0"`, `groups=tuple(sorted((planner_allowed_groups & groups.keys()) - mcp_only_groups))`).
  - `planner_excluded_mcp_only_groups(sources) -> tuple[str, ...]` = `tuple(sorted(planner_allowed_groups & mcp_only_groups))`.
  - `default_profile_definitions()` now yields `{rookchat_local, readonly, planner}`.

- [ ] **Step 1: Write the failing profile-layer tests**

In `mcp_server/tests/test_execution_profile.py`, extend the `execution_profile` import to add `planner_profile_from_sources` and `planner_excluded_mcp_only_groups`, and add:

```python
def test_planner_profile_from_sources_filters_groups():
    sources = SurfaceSources(
        groups={"a": ("ta",), "b": ("tb",), "gh_knowledge": ("tk",)},
        mcp_only_groups=frozenset({"gh_knowledge"}),
        planner_allowed_groups=frozenset({"a", "b", "gh_knowledge", "ghost"}),
    )
    p = planner_profile_from_sources(sources)
    assert p.name == "planner"
    assert p.initial_tier == "planner_tier0"
    # gh_knowledge dropped (MCP-only); ghost dropped (no definition).
    assert p.groups == ("a", "b")


def test_planner_excluded_mcp_only_groups_real_constants_pin():
    from rook.agent.planner import PLANNER_ALLOWED_GROUPS
    from rook.agent.tool_groups import MCP_ONLY_GROUPS

    sources = SurfaceSources(
        planner_allowed_groups=frozenset(PLANNER_ALLOWED_GROUPS),
        mcp_only_groups=frozenset(MCP_ONLY_GROUPS),
    )
    assert planner_excluded_mcp_only_groups(sources) == ("gh_exploration", "gh_knowledge")


def test_default_profile_definitions_includes_planner_tier_only():
    by_name = {d.name: d for d in default_profile_definitions()}
    assert set(by_name) == {"rookchat_local", "readonly", "planner"}
    assert by_name["planner"].initial_tier == "planner_tier0"
    assert by_name["planner"].groups == ()
    assert "external_mcp" not in by_name
```

Also update the existing `test_default_profile_definitions_are_tier_only_seeds`: change its membership assertion to `assert set(by_name) == {"rookchat_local", "readonly", "planner"}`, **remove** the `assert "planner" not in by_name` line, and add `assert by_name["planner"].initial_tier == "planner_tier0"` and `assert by_name["planner"].groups == ()` (keep the existing `assert "external_mcp" not in by_name`).

In `mcp_server/tests/test_profile_reconciliation.py`, add (reuses its `_schema`/`_resolution` helpers and imported `SurfaceSources`, `ProfileDefinition`, `reconcile_profile`):

```python
def test_planner_tier_local_tool_not_falsely_not_dispatchable():
    # knowledge_query is a planner_tier0 tool that is local-handler-backed.
    # With runtime-style local_tool_names it must NOT be not_dispatchable;
    # without it the false positive returns (proving both the fix and that the
    # planner tier is activated -> _TIER_FIELDS must include planner_tier0).
    definition = ProfileDefinition(name="planner", initial_tier="planner_tier0")
    resolution = _resolution(definition, tool_names=("knowledge_query",))
    catalog = {"knowledge_query": _schema("knowledge_query")}

    enriched = SurfaceSources(
        planner_tier0=frozenset({"knowledge_query"}),
        local_tool_names=frozenset({"knowledge_query"}),
    )
    rec = reconcile_profile(resolution, enriched, catalog)
    assert not any(
        f.code == "not_dispatchable" and f.tool == "knowledge_query"
        for f in rec.registry_findings
    )

    bare = SurfaceSources(planner_tier0=frozenset({"knowledge_query"}))
    rec_bare = reconcile_profile(resolution, bare, catalog)
    assert any(
        f.code == "not_dispatchable" and f.tool == "knowledge_query"
        for f in rec_bare.registry_findings
    )
```

- [ ] **Step 2: Run them to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_execution_profile.py mcp_server/tests/test_profile_reconciliation.py -k "planner" -q`
Expected: FAIL — `ImportError` on `planner_profile_from_sources`; the reconcile test also fails (planner tier not activated yet).

- [ ] **Step 3: Extend the `initial_tier` Literal**

In `mcp_server/src/rook/agent/execution_profile.py` line 25:

```python
    initial_tier: Literal["tier0", "agent_tier0", "readonly_tier0", "planner_tier0"] | None = None
```

- [ ] **Step 4: Add `planner_tier0` to `_TIER_FIELDS`**

In `mcp_server/src/rook/agent/profile_reconciliation.py` line 27:

```python
_TIER_FIELDS = frozenset({"tier0", "agent_tier0", "readonly_tier0", "planner_tier0"})
```

- [ ] **Step 5: Add the planner profile builder + excluded helper**

In `execution_profile.py`, immediately after `readonly_excluded_mcp_only_groups(...)`, add:

```python
def planner_profile_from_sources(sources: SurfaceSources) -> ProfileDefinition:
    """Evidence-backed, locally-executable planner seed (read-only plan/query).

    Groups = planner-allowed groups that have a definition in this snapshot and
    are not MCP-only. Mirrors readonly_profile_from_sources.
    """
    local_groups = (
        sources.planner_allowed_groups & frozenset(sources.groups.keys())
    ) - sources.mcp_only_groups
    return ProfileDefinition(
        name="planner",
        initial_tier="planner_tier0",
        groups=tuple(sorted(local_groups)),
        description="Read-only planning/query worker (evidence-backed seed).",
    )


def planner_excluded_mcp_only_groups(sources: SurfaceSources) -> tuple[str, ...]:
    """Planner-allowed groups excluded because they are MCP-only.

    Full policy intersection -- NOT filtered by groups.keys().
    """
    return tuple(sorted(sources.planner_allowed_groups & sources.mcp_only_groups))
```

- [ ] **Step 6: Add the tier-only planner default seed**

In `default_profile_definitions()`, add a third seed to the returned tuple (after the `readonly` seed). Update the docstring to note the planner seed is diagnostic/tier-only, not runtime policy:

```python
        ProfileDefinition(
            name="readonly",
            initial_tier="readonly_tier0",
            groups=(),
            description="Observation-only worker (diagnostic seed).",
        ),
        ProfileDefinition(
            name="planner",
            initial_tier="planner_tier0",
            groups=(),
            description="Read-only planning/query worker (diagnostic tier-only seed; "
            "evidence-backed groups via planner_profile_from_sources).",
        ),
    )
```

- [ ] **Step 7: Run the Task 2 tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_execution_profile.py mcp_server/tests/test_profile_reconciliation.py -q`
Expected: PASS (the 4 new/updated execution_profile assertions + the paired reconcile proof + all existing tests).

- [ ] **Step 8: Run the full LM2 suite + py_compile**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_record.py mcp_server/tests/test_capability_inventory.py mcp_server/tests/test_execution_profile.py mcp_server/tests/test_profile_reconciliation.py -q && mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/agent/capability_record.py mcp_server/src/rook/agent/capability_inventory.py mcp_server/src/rook/agent/execution_profile.py mcp_server/src/rook/agent/profile_reconciliation.py`
Expected: PASS; `py_compile` silent.

- [ ] **Step 9: Commit**

```bash
git add mcp_server/src/rook/agent/execution_profile.py mcp_server/src/rook/agent/profile_reconciliation.py mcp_server/tests/test_execution_profile.py mcp_server/tests/test_profile_reconciliation.py
git commit -m "feat(lm2f): planner_profile_from_sources + planner seed + reconcile tier recognition"
```

---

## Self-Review

**1. Spec coverage:**
- Unit 1 (2 SurfaceSources fields) → Task 1 Step 3. ✓
- Unit 2 (collect_live_sources population + _tiers_for + light-import probe) → Task 1 Steps 4-5, test in Step 1. ✓
- Unit 3 (Literal + planner_profile_from_sources + planner_excluded_mcp_only_groups + default seed) → Task 2 Steps 3,5,6. ✓
- SPEC CORRECTION (_TIER_FIELDS += planner_tier0) → Task 2 Step 4 + Global Constraints. ✓
- Diagnostic/tier-only seed (not policy) → Task 2 Step 6 docstring + Global Constraints. ✓
- Runtime-style local_tool_names reconcile test → Task 2 Step 1 (paired). ✓
- Both-tiers sorted assertion → Task 1 Step 1 (`test_tiers_for_planner_and_readonly_is_sorted`). ✓
- Real-constant excluded pin `("gh_exploration","gh_knowledge")` → Task 2 Step 1. ✓
- Out of scope (PLANNER_LOCAL_CATALOG, relocation, external_mcp) → no step touches them; Global Constraints restate. ✓

**2. Placeholder scan:** No TBD/TODO. Every code step shows complete code; every run step shows the command + expected outcome. ✓

**3. Type consistency:** `planner_tier0`/`planner_allowed_groups` field names identical across record, collector, builder, and tests. `planner_profile_from_sources`/`planner_excluded_mcp_only_groups` signatures identical in Interfaces, implementation, and tests. `initial_tier="planner_tier0"` consistent with the extended Literal and `_TIER_FIELDS`. `ProfileDefinition(name, initial_tier, groups, description)` and `ProfileResolution` via `_resolution(definition, tool_names=...)` match merged LM2B/D. The reconcile test's `not_dispatchable`/`registry_findings` match LM2D. ✓
