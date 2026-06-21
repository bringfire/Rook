# LM2F — Planner Profile Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `planner` as a first-class, evidence-backed diagnostic execution profile, and centralize tier-name knowledge (`TIER_FIELDS`) so the tier boundary can't silently drift.

**Architecture:** `TIER_FIELDS` (one tuple in `capability_record.py`) becomes the single source of truth; `_tiers_for`, `_universe`, and `profile_reconciliation._TIER_FIELDS` derive from it; the two static `Literal[...]` annotations stay manual but are pinned by drift tests. Planner evidence (`PLANNER_TIER_0`/`PLANNER_ALLOWED_GROUPS`) flows into two new `SurfaceSources` fields; `execution_profile.py` gains `planner_profile_from_sources` / `planner_excluded_mcp_only_groups` and a tier-only `planner` default seed. Read-only / diagnostic.

**Tech Stack:** Python 3.12 stdlib, pytest. Source under `mcp_server/src/rook/agent/`, tests under `mcp_server/tests/`.

**Spec:** `docs/superpowers/specs/2026-06-21-lm2f-planner-profile-semantics-design.md`

## Global Constraints

- Read-only / diagnostic only. No runtime/visibility/policy change; no MCP wire change.
- **Tier-name single source of truth:** `TIER_FIELDS = ("tier0","agent_tier0","readonly_tier0","planner_tier0")` in `capability_record.py`. `_tiers_for`, `_universe`, and `profile_reconciliation._TIER_FIELDS` MUST derive from it (no hardcoded tier-name set elsewhere). The two static `Literal[...]` (`ProfileDefinition.initial_tier`, `reconcile_active_schemas.initial`) stay manual but are drift-tested to equal `set(TIER_FIELDS)`.
- The `_tiers_for`/`_universe` refactor is behavior-preserving for the existing three tiers.
- Planner evidence: `rook.agent.planner.PLANNER_TIER_0` / `PLANNER_ALLOWED_GROUPS` (cheap static sets; importing `rook.agent.planner` is light — no `dspy`/`litellm`/`base_agent`). Do NOT relocate constants; do NOT use `PLANNER_LOCAL_CATALOG`.
- `planner_profile_from_sources` formula: `groups = (planner_allowed_groups & groups.keys()) - mcp_only_groups`. `planner_excluded_mcp_only_groups = planner_allowed_groups & mcp_only_groups`.
- The `planner` entry in `default_profile_definitions()` is a **diagnostic, tier-only seed**, NOT runtime policy (docstring says so).
- `_tiers_for` output stays `tuple(sorted(...))`.
- The planner reconcile test uses runtime-style `local_tool_names` (LM2E) so local-handler planner-tier tools (`gh_knowledge_query`, `knowledge_query`, `rhino_knowledge_query`) are not falsely `not_dispatchable`.
- Pinned facts: `planner_excluded_mcp_only_groups` real-constant == `("gh_exploration","gh_knowledge")`; `planner_profile_from_sources(...).groups` from live constants == `("layers","rhino_measurement","rhino_selection","viewport")`.
- `external_mcp`/`rookchat_cloud` out of scope.
- Run all commands from repo root (`C:/UDEV/Rook`) via `mcp_server/.venv/Scripts/python.exe`, with `-p no:cacheprovider`. Do NOT `cd` into `mcp_server/`.

---

### Task 1: Tier centralization + planner evidence carrier

**Files:**
- Modify: `mcp_server/src/rook/agent/capability_record.py` — `TIER_FIELDS` constant (before `SurfaceSources`); 2 `SurfaceSources` fields.
- Modify: `mcp_server/src/rook/agent/capability_inventory.py` — import `TIER_FIELDS`; `_tiers_for` (55-63) and `_universe` (102) derive from it; `reconcile_active_schemas.initial` Literal (248) += `planner_tier0`; `collect_live_sources` planner population (after line 304).
- Modify: `mcp_server/src/rook/agent/profile_reconciliation.py:27` — `_TIER_FIELDS = frozenset(TIER_FIELDS)`.
- Test: `test_capability_record.py`, `test_capability_inventory.py`, `test_profile_reconciliation.py`.

**Interfaces:**
- Consumes: `rook.agent.planner.PLANNER_TIER_0`, `PLANNER_ALLOWED_GROUPS`.
- Produces: `capability_record.TIER_FIELDS: tuple[str, ...]`; `SurfaceSources.planner_tier0`, `.planner_allowed_groups` (defaulted `frozenset()`); records' `.tiers` include `"planner_tier0"`; `profile_reconciliation._TIER_FIELDS == frozenset(TIER_FIELDS)`.

- [ ] **Step 1: Write the failing tests**

In `mcp_server/tests/test_capability_record.py`, add `TIER_FIELDS` to the `capability_record` import and add:

```python
def test_surface_sources_planner_fields_default_empty():
    s = SurfaceSources()
    assert s.planner_tier0 == frozenset()
    assert s.planner_allowed_groups == frozenset()


def test_tier_fields_are_all_surface_sources_fields():
    import dataclasses

    names = {f.name for f in dataclasses.fields(SurfaceSources)}
    assert set(TIER_FIELDS) <= names
    assert TIER_FIELDS == ("tier0", "agent_tier0", "readonly_tier0", "planner_tier0")
```

In `mcp_server/tests/test_capability_inventory.py`, add (it already imports `SurfaceSources`, `build_inventory`, `collect_live_sources`, `reconcile_active_schemas`, `tool_registry_module`, and has a `_schema` helper):

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
    sources = SurfaceSources(
        readonly_tier0=frozenset({"dual"}),
        planner_tier0=frozenset({"dual"}),
    )
    inv = build_inventory(sources, {"dual": _schema("dual")})
    record = {r.name: r for r in inv.records}["dual"]
    assert record.tiers == ("planner_tier0", "readonly_tier0")


def test_planner_only_tool_is_in_inventory_universe():
    # Guards the _universe drift: a tool present ONLY in planner_tier0 must get a
    # record (it would be missing if _universe didn't include planner_tier0).
    sources = SurfaceSources(planner_tier0=frozenset({"planner_only"}))
    inv = build_inventory(sources, {})
    assert "planner_only" in {r.name for r in inv.records}


def test_reconcile_active_schemas_initial_literal_matches_tier_fields():
    import typing

    from rook.agent.capability_record import TIER_FIELDS

    hints = typing.get_type_hints(reconcile_active_schemas)
    assert set(typing.get_args(hints["initial"])) == set(TIER_FIELDS)


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

In `mcp_server/tests/test_profile_reconciliation.py`, add:

```python
def test_reconcile_tier_fields_match_central_constant():
    from rook.agent.capability_record import TIER_FIELDS
    from rook.agent.profile_reconciliation import _TIER_FIELDS

    assert _TIER_FIELDS == frozenset(TIER_FIELDS)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_record.py mcp_server/tests/test_capability_inventory.py mcp_server/tests/test_profile_reconciliation.py -k "planner or tier_fields or tiers_for_planner or stays_light or universe or initial_literal or central_constant" -q`
Expected: FAIL — `ImportError: cannot import name 'TIER_FIELDS'` / `SurfaceSources` has no `planner_tier0`.

- [ ] **Step 3: Add `TIER_FIELDS` + the two SurfaceSources fields**

In `mcp_server/src/rook/agent/capability_record.py`, add the constant immediately before the `@dataclass(frozen=True)` / `class SurfaceSources` line:

```python
TIER_FIELDS: tuple[str, ...] = ("tier0", "agent_tier0", "readonly_tier0", "planner_tier0")
```

Add `planner_tier0` immediately after `readonly_tier0`, and `planner_allowed_groups` immediately after `readonly_allowed_groups`:

```python
    readonly_tier0: frozenset[str] = frozenset()
    planner_tier0: frozenset[str] = frozenset()
    groups: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    mcp_only_groups: frozenset[str] = frozenset()
    readonly_allowed_groups: frozenset[str] = frozenset()
    planner_allowed_groups: frozenset[str] = frozenset()
    bridge_names: frozenset[str] = frozenset()
```

(The `groups`/`mcp_only_groups`/`bridge_names` lines already exist — anchors only.)

- [ ] **Step 4: Derive `_tiers_for` and `_universe` from `TIER_FIELDS`**

In `mcp_server/src/rook/agent/capability_inventory.py`, add `TIER_FIELDS` to the `capability_record` import:

```python
from rook.agent.capability_record import (
    CapabilityFinding,
    CapabilityInventory,
    CapabilityRecord,
    SurfaceSources,
    TIER_FIELDS,
    Visibility,
)
```

Replace the body of `_tiers_for` with the `TIER_FIELDS`-derived form:

```python
def _tiers_for(name: str, sources: SurfaceSources) -> tuple[str, ...]:
    return tuple(sorted(tf for tf in TIER_FIELDS if name in getattr(sources, tf)))
```

In `_universe`, replace the explicit tier union line
(`names |= set(sources.tier0) | set(sources.agent_tier0) | set(sources.readonly_tier0)`)
with:

```python
    for tier_field in TIER_FIELDS:
        names |= set(getattr(sources, tier_field))
```

- [ ] **Step 5: Broaden the `reconcile_active_schemas` initial Literal + populate planner evidence**

In `reconcile_active_schemas`, broaden the `initial` parameter annotation:

```python
    initial: Literal["tier0", "agent_tier0", "readonly_tier0", "planner_tier0"] = "agent_tier0",
```

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

(The `bridge_names=` line already exists — anchor only.)

- [ ] **Step 6: Derive `profile_reconciliation._TIER_FIELDS` from the central tuple**

In `mcp_server/src/rook/agent/profile_reconciliation.py`, add `TIER_FIELDS` to its `capability_record` import and replace line 27:

```python
from rook.agent.capability_record import CapabilityFinding, SurfaceSources, TIER_FIELDS
...
_TIER_FIELDS = frozenset(TIER_FIELDS)
```

- [ ] **Step 7: Run the Task 1 tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_record.py mcp_server/tests/test_capability_inventory.py mcp_server/tests/test_profile_reconciliation.py -q`
Expected: PASS (all existing LM2A–E tests — `_tiers_for`/`_universe` refactor is behavior-preserving — plus the new centralization + evidence + drift tests).

- [ ] **Step 8: Commit**

```bash
git add mcp_server/src/rook/agent/capability_record.py mcp_server/src/rook/agent/capability_inventory.py mcp_server/src/rook/agent/profile_reconciliation.py mcp_server/tests/test_capability_record.py mcp_server/tests/test_capability_inventory.py mcp_server/tests/test_profile_reconciliation.py
git commit -m "feat(lm2f): centralize tier names (TIER_FIELDS) + carry planner evidence"
```

---

### Task 2: Planner profile builder + seed + reconcile proof

**Files:**
- Modify: `mcp_server/src/rook/agent/execution_profile.py` — `ProfileDefinition.initial_tier` Literal (25); `planner_profile_from_sources` + `planner_excluded_mcp_only_groups` (after `readonly_excluded_mcp_only_groups`, ~242); `default_profile_definitions` planner seed (190-211).
- Test: `test_execution_profile.py`, `test_profile_reconciliation.py`.

**Interfaces:**
- Consumes (Task 1): `SurfaceSources.planner_tier0`, `.planner_allowed_groups`; records carrying `"planner_tier0"` in `.tiers`; `profile_reconciliation._TIER_FIELDS` includes `planner_tier0`; `capability_record.TIER_FIELDS`.
- Produces: `planner_profile_from_sources(sources) -> ProfileDefinition`; `planner_excluded_mcp_only_groups(sources) -> tuple[str, ...]`; `default_profile_definitions()` == `{rookchat_local, readonly, planner}`.

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


def test_profile_definition_initial_tier_literal_matches_tier_fields():
    import typing

    from rook.agent.capability_record import TIER_FIELDS

    hints = typing.get_type_hints(ProfileDefinition)
    union_args = typing.get_args(hints["initial_tier"])  # (Literal[...], NoneType)
    literal = next(a for a in union_args if typing.get_origin(a) is typing.Literal)
    assert set(typing.get_args(literal)) == set(TIER_FIELDS)
```

Also update the existing `test_default_profile_definitions_are_tier_only_seeds`: change its membership assertion to `assert set(by_name) == {"rookchat_local", "readonly", "planner"}`, **remove** the `assert "planner" not in by_name` line, and add `assert by_name["planner"].initial_tier == "planner_tier0"` and `assert by_name["planner"].groups == ()` (keep the existing `assert "external_mcp" not in by_name`).

In `mcp_server/tests/test_profile_reconciliation.py`, add (reuses its `_schema`/`_resolution` helpers and imported `SurfaceSources`, `ProfileDefinition`, `reconcile_profile`):

```python
def test_planner_tier_local_tool_not_falsely_not_dispatchable():
    # knowledge_query is a planner_tier0 tool that is local-handler-backed.
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

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_execution_profile.py mcp_server/tests/test_profile_reconciliation.py -k "planner or initial_tier_literal" -q`
Expected: FAIL — `ImportError` on `planner_profile_from_sources`; the reconcile + Literal drift tests also fail.

- [ ] **Step 3: Extend the `initial_tier` Literal**

In `mcp_server/src/rook/agent/execution_profile.py` line 25:

```python
    initial_tier: Literal["tier0", "agent_tier0", "readonly_tier0", "planner_tier0"] | None = None
```

- [ ] **Step 4: Add the planner builder + excluded helper**

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

- [ ] **Step 5: Add the tier-only planner default seed**

In `default_profile_definitions()`, add a third seed after the `readonly` seed:

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

- [ ] **Step 6: Run the Task 2 tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_execution_profile.py mcp_server/tests/test_profile_reconciliation.py -q`
Expected: PASS (the new/updated execution_profile assertions + the Literal drift test + the paired reconcile proof + all existing tests).

- [ ] **Step 7: Run the full LM2 suite + py_compile**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_record.py mcp_server/tests/test_capability_inventory.py mcp_server/tests/test_execution_profile.py mcp_server/tests/test_profile_reconciliation.py -q && mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/agent/capability_record.py mcp_server/src/rook/agent/capability_inventory.py mcp_server/src/rook/agent/execution_profile.py mcp_server/src/rook/agent/profile_reconciliation.py`
Expected: PASS; `py_compile` silent.

- [ ] **Step 8: Commit**

```bash
git add mcp_server/src/rook/agent/execution_profile.py mcp_server/tests/test_execution_profile.py mcp_server/tests/test_profile_reconciliation.py
git commit -m "feat(lm2f): planner_profile_from_sources + planner seed + reconcile proof"
```

---

## Self-Review

**1. Spec coverage:**
- Unit 0 (`TIER_FIELDS`) → Task 1 Step 3. ✓
- Unit 1 (2 SurfaceSources fields) → Task 1 Step 3. ✓
- Unit 2 (`_tiers_for`/`_universe` derive; `reconcile_active_schemas` Literal; collect_live_sources population; light-import probe) → Task 1 Steps 4-5 + tests Step 1. ✓
- `_TIER_FIELDS = frozenset(TIER_FIELDS)` → Task 1 Step 6. ✓
- Unit 3 (initial_tier Literal; `planner_profile_from_sources`; `planner_excluded_mcp_only_groups`; tier-only default seed) → Task 2 Steps 3-5. ✓
- Drift tests (TIER_FIELDS-are-fields, `_TIER_FIELDS` match, both Literal matches) → Task 1 (record/inventory/reconcile) + Task 2 (ProfileDefinition Literal). ✓
- `_universe` correctness guard (planner-only tool in universe) → Task 1 Step 1 `test_planner_only_tool_is_in_inventory_universe`. ✓
- Runtime-style local_tool_names reconcile proof + both-tiers sorted → Task 2 / Task 1. ✓
- Real-constant excluded pin `("gh_exploration","gh_knowledge")` → Task 2 Step 1. ✓
- Out of scope (PLANNER_LOCAL_CATALOG, relocation, external_mcp) → no step touches them. ✓

**2. Placeholder scan:** No TBD/TODO. Every code step shows complete code; every run step shows command + expected outcome. ✓

**3. Type consistency:** `TIER_FIELDS` identical across record, inventory, profile_reconciliation, and tests. `planner_tier0`/`planner_allowed_groups`, `planner_profile_from_sources`/`planner_excluded_mcp_only_groups` consistent in Interfaces, implementation, tests. `initial_tier="planner_tier0"` consistent with both extended Literals, `TIER_FIELDS`, and `_TIER_FIELDS`. Drift tests resolve annotations via `typing.get_type_hints` (correct for `from __future__ import annotations`). ✓
