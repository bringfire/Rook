# LM2C — Readonly Group Evidence & Faithful Local Readonly Seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Carry the repo's real `READONLY_ALLOWED_GROUPS` policy into the injected `SurfaceSources` snapshot and build a locally-executable readonly profile seed from that evidence, with the MCP-only exclusion exposed as testable data.

**Architecture:** Three tiny, read-only additions on top of merged LM2A/LM2B. Unit 1 adds one defaulted field to the stdlib-only `SurfaceSources`. Unit 2 populates it in `collect_live_sources()` (no new import — `tool_groups` is already imported there). Unit 3 adds two pure, deterministic functions to `execution_profile.py` that consume only `SurfaceSources`, preserving that module's import allow-list. No inventory, resolver, or runtime behavior changes.

**Tech Stack:** Python 3.12, stdlib-only modules, pytest. Source under `mcp_server/src/rook/agent/`, tests under `mcp_server/tests/`.

**Spec:** `docs/superpowers/specs/2026-06-21-lm2c-readonly-group-evidence-design.md`

## Global Constraints

- Read-only / diagnostic only. No `ToolRegistry`, no visibility mutation, no runtime policy, no PlanGraph wiring.
- `build_inventory(...)`, `CapabilityRecord`, and `CapabilityInventory` **behavior/output are unchanged**; the new `SurfaceSources` evidence field is ignored by inventory construction. (Adding a defaulted field does change the `SurfaceSources` dataclass repr/equality — that is expected and fine.)
- `default_profile_definitions()` stays no-arg, constant, tier-only — **do not modify it**.
- No `ProfileFinding` emitted from a builder; no `resolve_profile` change.
- `execution_profile.py` import allow-list stays `{__future__, dataclasses, typing, rook.agent.capability_record}`. `capability_record.py` stays stdlib-only (`{__future__, collections.abc, dataclasses, typing}`).
- All tuple outputs sorted; all new functions pure and deterministic; evidence-driven (no tool names, no name suffixes).
- Builder formula: `local_groups = (readonly_allowed_groups & groups.keys()) - mcp_only_groups`.
- Excluded formula: `excluded_mcp = readonly_allowed_groups & mcp_only_groups` (full intersection, **not** filtered by `groups.keys()`).
- Run tests from the `mcp_server/` directory so `pytest` resolves `rook.*` and the boundary tests' relative paths (`mcp_server/src/...`) resolve from repo root as the existing suite expects. Commands below use the repo root with explicit paths, matching the merged LM2A/LM2B test invocations.

---

### Task 1: Carry readonly-allowed group evidence into the snapshot

**Files:**
- Modify: `mcp_server/src/rook/agent/capability_record.py:25` (add one field to `SurfaceSources`, after `mcp_only_groups`)
- Modify: `mcp_server/src/rook/agent/capability_inventory.py:288` (add one line in `collect_live_sources()`, after the `mcp_only_groups=` line)
- Test: `mcp_server/tests/test_capability_record.py`
- Test: `mcp_server/tests/test_capability_inventory.py`

**Interfaces:**
- Consumes: existing `SurfaceSources` frozen dataclass; existing `collect_live_sources()`; `rook.agent.tool_groups.READONLY_ALLOWED_GROUPS`.
- Produces: `SurfaceSources.readonly_allowed_groups: frozenset[str]` (defaulted `frozenset()`), populated by `collect_live_sources()` from `READONLY_ALLOWED_GROUPS`. Task 2 consumes this field.

- [ ] **Step 1: Write the failing record-field test**

In `mcp_server/tests/test_capability_record.py`, add:

```python
def test_surface_sources_readonly_allowed_groups_defaults_empty():
    assert SurfaceSources().readonly_allowed_groups == frozenset()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_capability_record.py::test_surface_sources_readonly_allowed_groups_defaults_empty -v`
Expected: FAIL with `AttributeError: 'SurfaceSources' object has no attribute 'readonly_allowed_groups'`

- [ ] **Step 3: Add the field**

In `mcp_server/src/rook/agent/capability_record.py`, inside the `SurfaceSources` dataclass, add the new field immediately after `mcp_only_groups`:

```python
    mcp_only_groups: frozenset[str] = frozenset()
    readonly_allowed_groups: frozenset[str] = frozenset()
    bridge_names: frozenset[str] = frozenset()
```

(The `bridge_names` line already exists — it is shown only to anchor the insertion point. Insert the `readonly_allowed_groups` line between `mcp_only_groups` and `bridge_names`.)

- [ ] **Step 4: Run the record-field test to verify it passes**

Run: `cd mcp_server && python -m pytest tests/test_capability_record.py::test_surface_sources_readonly_allowed_groups_defaults_empty -v`
Expected: PASS

- [ ] **Step 5: Write the failing collector test**

In `mcp_server/tests/test_capability_inventory.py`, add:

```python
def test_collect_live_sources_carries_readonly_allowed_groups(monkeypatch):
    from rook.agent.tool_groups import READONLY_ALLOWED_GROUPS

    def _boom(*args, **kwargs):
        raise AssertionError("collect_live_sources must not load the catalog cache")

    monkeypatch.setattr(tool_registry_module, "load_catalog_from_cache", _boom)
    monkeypatch.setattr(tool_registry_module, "get_catalog_cache_path", _boom)

    sources = collect_live_sources()
    assert sources.readonly_allowed_groups == frozenset(READONLY_ALLOWED_GROUPS)
```

(`tool_registry_module` is already imported at the top of this test file; the `_boom` guards mirror the existing `test_collect_live_sources_reads_constants_only` to keep the no-cache invariant.)

- [ ] **Step 6: Run it to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_capability_inventory.py::test_collect_live_sources_carries_readonly_allowed_groups -v`
Expected: FAIL — `readonly_allowed_groups` is empty (`frozenset()`) because `collect_live_sources()` does not yet populate it, so it will not equal the non-empty `READONLY_ALLOWED_GROUPS`.

- [ ] **Step 7: Populate the field in the collector**

In `mcp_server/src/rook/agent/capability_inventory.py`, inside `collect_live_sources()`, add the new keyword argument immediately after the `mcp_only_groups=` line:

```python
        mcp_only_groups=frozenset(tg.MCP_ONLY_GROUPS),
        readonly_allowed_groups=frozenset(tg.READONLY_ALLOWED_GROUPS),
        bridge_names=frozenset(td.BRIDGE_ROUTES.keys()),
```

(The `bridge_names=` line already exists — shown only to anchor the insertion point. Insert the `readonly_allowed_groups=` line between them.)

- [ ] **Step 8: Run the collector test to verify it passes**

Run: `cd mcp_server && python -m pytest tests/test_capability_inventory.py::test_collect_live_sources_carries_readonly_allowed_groups -v`
Expected: PASS

- [ ] **Step 9: Run both touched test modules to confirm no regression**

Run: `cd mcp_server && python -m pytest tests/test_capability_record.py tests/test_capability_inventory.py -q`
Expected: PASS (all existing LM2A tests plus the two new ones). The unchanged `test_build_inventory_*` assertions confirm inventory output is unaffected by the new field.

- [ ] **Step 10: Commit**

```bash
git add mcp_server/src/rook/agent/capability_record.py mcp_server/src/rook/agent/capability_inventory.py mcp_server/tests/test_capability_record.py mcp_server/tests/test_capability_inventory.py
git commit -m "feat(lm2c): carry readonly-allowed group evidence into SurfaceSources"
```

---

### Task 2: Evidence-backed readonly seed builder + excluded-groups helper

**Files:**
- Modify: `mcp_server/src/rook/agent/execution_profile.py:14-18` (extend the `capability_record` import to include `SurfaceSources`)
- Modify: `mcp_server/src/rook/agent/execution_profile.py:210` (add two functions after `default_profile_definitions()`, before `format_profile_report`)
- Test: `mcp_server/tests/test_execution_profile.py`

**Interfaces:**
- Consumes: `SurfaceSources.readonly_allowed_groups`, `.groups`, `.mcp_only_groups` (from Task 1); existing `ProfileDefinition`, `build_inventory`, `resolve_profile`.
- Produces:
  - `readonly_profile_from_sources(sources: SurfaceSources) -> ProfileDefinition` — `name="readonly"`, `initial_tier="readonly_tier0"`, `groups=tuple(sorted((readonly_allowed_groups & groups.keys()) - mcp_only_groups))`.
  - `readonly_excluded_mcp_only_groups(sources: SurfaceSources) -> tuple[str, ...]` — `tuple(sorted(readonly_allowed_groups & mcp_only_groups))`.

- [ ] **Step 1: Write the failing builder + excluded unit tests**

In `mcp_server/tests/test_execution_profile.py`, add the new imports near the existing ones at the top of the file:

```python
from rook.agent.capability_record import SurfaceSources
from rook.agent.capability_inventory import build_inventory
from rook.agent.execution_profile import (
    readonly_excluded_mcp_only_groups,
    readonly_profile_from_sources,
)
```

Then add these tests at the end of the file:

```python
def test_readonly_profile_excludes_mcp_only_and_undefined_groups():
    sources = SurfaceSources(
        groups={"a": ("ta",), "b": ("tb",), "gh_knowledge": ("tk",)},
        mcp_only_groups=frozenset({"gh_knowledge"}),
        readonly_allowed_groups=frozenset({"a", "b", "gh_knowledge", "ghost_group"}),
    )
    profile = readonly_profile_from_sources(sources)
    assert profile.name == "readonly"
    assert profile.initial_tier == "readonly_tier0"
    # gh_knowledge dropped (MCP-only); ghost_group dropped (no definition).
    assert profile.groups == ("a", "b")


def test_readonly_profile_groups_are_sorted():
    sources = SurfaceSources(
        groups={"z": ("tz",), "a": ("ta",), "m": ("tm",)},
        readonly_allowed_groups=frozenset({"z", "a", "m"}),
    )
    assert readonly_profile_from_sources(sources).groups == ("a", "m", "z")


def test_readonly_profile_empty_evidence_degrades_to_tier_only():
    profile = readonly_profile_from_sources(SurfaceSources())
    assert profile.groups == ()
    assert profile.initial_tier == "readonly_tier0"


def test_readonly_excluded_mcp_only_groups_synthetic():
    sources = SurfaceSources(
        groups={"a": ("ta",), "gh_knowledge": ("tk",)},
        mcp_only_groups=frozenset({"gh_knowledge"}),
        readonly_allowed_groups=frozenset({"a", "gh_knowledge"}),
    )
    assert readonly_excluded_mcp_only_groups(sources) == ("gh_knowledge",)


def test_readonly_excluded_mcp_only_groups_real_constants_pin():
    from rook.agent.tool_groups import MCP_ONLY_GROUPS, READONLY_ALLOWED_GROUPS

    sources = SurfaceSources(
        mcp_only_groups=frozenset(MCP_ONLY_GROUPS),
        readonly_allowed_groups=frozenset(READONLY_ALLOWED_GROUPS),
    )
    assert readonly_excluded_mcp_only_groups(sources) == (
        "gh_exploration",
        "gh_knowledge",
        "gh_validation",
    )
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd mcp_server && python -m pytest tests/test_execution_profile.py -k "readonly_profile or readonly_excluded" -v`
Expected: FAIL at import (`ImportError: cannot import name 'readonly_profile_from_sources'`).

- [ ] **Step 3: Add `SurfaceSources` to the module import**

In `mcp_server/src/rook/agent/execution_profile.py`, extend the existing `capability_record` import block:

```python
from rook.agent.capability_record import (
    CapabilityInventory,
    CapabilityRecord,
    Severity,
    SurfaceSources,
)
```

- [ ] **Step 4: Implement the two functions**

In `mcp_server/src/rook/agent/execution_profile.py`, immediately after the end of `default_profile_definitions()` (the `return (...)` block) and before `def format_profile_report(`, add:

```python
def readonly_profile_from_sources(sources: SurfaceSources) -> ProfileDefinition:
    """Evidence-backed, locally-executable readonly seed.

    Groups = readonly-allowed groups that (a) have a definition in this same
    snapshot and (b) are not MCP-only. The result is resolvable against the
    inventory built from the same SurfaceSources and never knowingly emits an
    unknown_group finding from the default seed. Emits no findings itself.

    `(A & B) - C` is set-identical to Python's precedence-driven `A & (B - C)`;
    explicit parentheses are used for the reader.
    """
    local_groups = (
        sources.readonly_allowed_groups & frozenset(sources.groups.keys())
    ) - sources.mcp_only_groups
    return ProfileDefinition(
        name="readonly",
        initial_tier="readonly_tier0",
        groups=tuple(sorted(local_groups)),
        description="Locally-executable observation-only worker (evidence-backed seed).",
    )


def readonly_excluded_mcp_only_groups(sources: SurfaceSources) -> tuple[str, ...]:
    """Readonly-allowed groups deliberately excluded because they are MCP-only.

    Full policy intersection -- NOT filtered by groups.keys() -- so the excluded
    pin reflects policy regardless of whether a group definition exists.
    """
    return tuple(sorted(sources.readonly_allowed_groups & sources.mcp_only_groups))
```

- [ ] **Step 5: Run the unit tests to verify they pass**

Run: `cd mcp_server && python -m pytest tests/test_execution_profile.py -k "readonly_profile or readonly_excluded" -v`
Expected: PASS (all five tests).

- [ ] **Step 6: Write the failing integration test**

In `mcp_server/tests/test_execution_profile.py`, add:

```python
def test_readonly_seed_resolves_locally_executable_no_mcp_only_findings():
    # One readonly-allowed non-MCP group with a local-visible, dispatchable,
    # schema-backed tool; one readonly-allowed MCP-only group. Small deterministic
    # fixture -- no live catalog.
    sources = SurfaceSources(
        readonly_tier0=frozenset({"ro_tool_local"}),
        groups={"ro_local": ("ro_tool_local",), "ro_mcp": ("ro_tool_mcp",)},
        mcp_only_groups=frozenset({"ro_mcp"}),
        readonly_allowed_groups=frozenset({"ro_local", "ro_mcp"}),
        bridge_names=frozenset({"ro_tool_local"}),
    )
    catalog = {
        "ro_tool_local": {
            "type": "function",
            "function": {
                "name": "ro_tool_local",
                "description": "ro_tool_local",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        }
    }

    profile = readonly_profile_from_sources(sources)
    assert profile.groups == ("ro_local",)  # ro_mcp excluded

    inventory = build_inventory(sources, catalog)
    res = resolve_profile(profile, inventory)

    assert "ro_tool_mcp" not in res.tool_names
    assert not any(f.code == "mcp_only_tool" for f in res.findings)
```

- [ ] **Step 7: Run the integration test to verify it passes**

Run: `cd mcp_server && python -m pytest tests/test_execution_profile.py::test_readonly_seed_resolves_locally_executable_no_mcp_only_findings -v`
Expected: PASS. (`ro_tool_local` is local-visible via the non-MCP `ro_local` group, dispatchable via `bridge_names` → `dispatch_path="bridge_route"`, schema-backed via `catalog`; the profile carries only `ro_local`, so no MCP-only tool reaches resolution.)

- [ ] **Step 8: Run the full execution-profile module, including the import-boundary guard**

Run: `cd mcp_server && python -m pytest tests/test_execution_profile.py -q`
Expected: PASS. In particular `test_execution_profile_is_import_light` still passes: the only new import is `SurfaceSources` from `rook.agent.capability_record`, which is already on the allow-list, so `imports <= {"__future__", "dataclasses", "typing", "rook.agent.capability_record"}` holds. `test_default_profile_definitions_are_tier_only_seeds` and `test_default_profile_definitions_is_constant` confirm the constant seed is untouched.

- [ ] **Step 9: Run the full LM2 test trio + py_compile**

Run: `cd mcp_server && python -m pytest tests/test_capability_record.py tests/test_capability_inventory.py tests/test_execution_profile.py -q && python -m py_compile src/rook/agent/capability_record.py src/rook/agent/capability_inventory.py src/rook/agent/execution_profile.py`
Expected: PASS, and `py_compile` prints nothing (success).

- [ ] **Step 10: Commit**

```bash
git add mcp_server/src/rook/agent/execution_profile.py mcp_server/tests/test_execution_profile.py
git commit -m "feat(lm2c): evidence-backed readonly seed + excluded-mcp-group helper"
```

---

## Self-Review

**1. Spec coverage:**
- Unit 1 (`SurfaceSources.readonly_allowed_groups`) → Task 1, Steps 1-4. ✓
- Unit 2 (`collect_live_sources()` populates it) → Task 1, Steps 5-8. ✓
- Unit 3 (`readonly_profile_from_sources`, `readonly_excluded_mcp_only_groups`) → Task 2, Steps 3-5. ✓
- Spec tests 1-2 (record default, collector live-constants) → Task 1. ✓
- Spec tests 3-4 (builder both-way filter, excluded synthetic) → Task 2, Step 1. ✓
- Spec test 5 (real-constant excluded pin) → Task 2, Step 1. ✓
- Spec test 6 (empty edge) → Task 2, Step 1. ✓
- Spec test 7 (determinism/sorted) → Task 2, Step 1. ✓
- Spec test 8 (integration, small deterministic inventory) → Task 2, Steps 6-7. ✓
- Spec test 9 (import-boundary guards re-run) → Task 1 Step 9 (record stdlib-only test runs) + Task 2 Step 8 (execution_profile import-light test runs). ✓
- "Does NOT do" list (no `default_profile_definitions` change, no resolver change, no builder findings, no overload, no external profile, no runtime wiring) → none of the steps touch those; Global Constraints restate them. ✓

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to". Every code step shows complete code; every run step shows the exact command and expected outcome. ✓

**3. Type consistency:** `readonly_allowed_groups: frozenset[str]` used consistently in record, collector, and both functions. Function names `readonly_profile_from_sources` / `readonly_excluded_mcp_only_groups` identical in Interfaces, implementation, and tests. `ProfileDefinition(name, initial_tier, groups, description)` matches the merged LM2B signature. ✓
