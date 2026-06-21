# LM2F — Planner Profile Semantics (evidence-backed)

**Date:** 2026-06-21
**Status:** Approved (design)
**Campaign:** Local/Internal Models roadmap (LM2 — capability/surface evidence)
**Branch:** `codex/lm2f-planner-profile-semantics`

---

## Summary

The north-star's LM2 deliverable names execution-profile membership for
`external_mcp`, `rookchat_cloud`, `rookchat_local`, `readonly`, and `planner`.
LM2C delivered `rookchat_local` + `readonly`. LM2F adds **`planner`** as a
first-class, evidence-backed diagnostic profile, mirroring LM2C's `readonly`
exactly — using the planner's real runtime constants `PLANNER_TIER_0` and
`PLANNER_ALLOWED_GROUPS` (`rook.agent.planner`).

`external_mcp` is deferred to **LM2G** (it needs a distinct full-catalog /
MCP-wire visibility model, not a tier+groups subset). `rookchat_cloud` is
deferred until it has a runtime constant. `PLANNER_LOCAL_CATALOG` is out of scope
for LM2F (tier + allowed-groups evidence is sufficient).

**LM2F also centralizes tier-name knowledge** (`TIER_FIELDS`), because adding the
first new tier since LM2A revealed that the tier-name set is duplicated across
five sites (`_tiers_for`, `_universe`, `reconcile_active_schemas`'s `initial`
Literal, `ProfileDefinition.initial_tier` Literal, `profile_reconciliation._TIER_FIELDS`)
plus the `SurfaceSources` fields. A planning-time sweep found `_universe` would
have been **missed**, which would make a `planner_tier0`-only tool invisible to
the record universe (masked today only because `PLANNER_TIER_0 == READONLY_TIER_0`).
Centralizing removes the drift structurally for the runtime paths and adds drift
tests for the static `Literal` annotations.

Read-only / diagnostic only — no runtime, visibility, or policy change.

## Design

### Unit 0 — Tier-name centralization (`capability_record.py`)

Add a single source of truth for the tier field/name set, next to `SurfaceSources`
(stdlib-only; the tier field name *is* the tier name emitted by `_tiers_for`):

```python
TIER_FIELDS: tuple[str, ...] = ("tier0", "agent_tier0", "readonly_tier0", "planner_tier0")
```

The runtime tier allowlists derive from it (Unit 2 + the resolver gate); the two
static `Literal[...]` annotations cannot be generated from a runtime tuple, so
they stay manual but are pinned by drift tests.

### Unit 1 — Evidence carrier (`capability_record.py`)

Add two defaulted fields to `SurfaceSources` (stdlib-only; existing fixtures stay
valid):

```python
planner_tier0: frozenset[str] = frozenset()
planner_allowed_groups: frozenset[str] = frozenset()
```

### Unit 2 — Live collector + tier recognition (`capability_inventory.py`)

`collect_live_sources()` lazily imports the planner constants and populates both
fields. Importing `rook.agent.planner` was probed light (it pulls no
`dspy`/`litellm`/`base_agent`/`tool_registry` — its heavy machinery is
lazy-imported inside methods), so this stays consistent with the collector's
existing lazy `tool_dispatcher`/`tool_groups` imports:

```python
from rook.agent import planner as _planner
...
planner_tier0=frozenset(_planner.PLANNER_TIER_0),
planner_allowed_groups=frozenset(_planner.PLANNER_ALLOWED_GROUPS),
```

`_tiers_for(name, sources)` and `_universe(sources, catalog)` are refactored to
**derive from `TIER_FIELDS`** (importing it from `capability_record`) instead of
naming each field — so a new tier can never be silently missed again:

```python
def _tiers_for(name, sources):
    return tuple(sorted(tf for tf in TIER_FIELDS if name in getattr(sources, tf)))

# in _universe, replacing the explicit `tier0 | agent_tier0 | readonly_tier0` union:
for tf in TIER_FIELDS:
    names |= set(getattr(sources, tf))
```

`reconcile_active_schemas`'s `initial` `Literal[...]` parameter is broadened to
include `"planner_tier0"` (static annotation; the body already uses
`getattr(sources, initial)`, which now resolves the planner field). This widens a
read-only diagnostic helper — consistent with making planner first-class.

**Import-boundary guard:** a subprocess probe test asserts that calling
`collect_live_sources()` does not load `dspy`, `litellm`, or
`rook.agent.base_agent` — the safety net for the "planner import stays light"
assumption. (If it ever fails, relocate the constants to `tool_groups.py`; not
done in LM2F.)

### Unit 3 — Profile layer (`execution_profile.py`, stays import-light)

Imports only `rook.agent.capability_record` (unchanged boundary).

- Extend the `ProfileDefinition.initial_tier` Literal:
  `Literal["tier0", "agent_tier0", "readonly_tier0", "planner_tier0"] | None`.

- `planner_profile_from_sources(sources)` — exact analog of
  `readonly_profile_from_sources`:

  ```python
  def planner_profile_from_sources(sources: SurfaceSources) -> ProfileDefinition:
      local_groups = (
          sources.planner_allowed_groups & frozenset(sources.groups.keys())
      ) - sources.mcp_only_groups
      return ProfileDefinition(
          name="planner",
          initial_tier="planner_tier0",
          groups=tuple(sorted(local_groups)),
          description="Read-only planning/query worker (evidence-backed seed).",
      )
  ```

- `planner_excluded_mcp_only_groups(sources)` =
  `tuple(sorted(sources.planner_allowed_groups & sources.mcp_only_groups))`
  (full intersection, not filtered by `groups.keys()`).

- **Add `planner` to `default_profile_definitions()` — diagnostic, tier-only.**
  The constant default seed becomes `{rookchat_local, readonly, planner}`, with
  `planner` as `initial_tier="planner_tier0", groups=()`. This is a **diagnostic
  seed, not runtime policy** — the evidence-backed planner with real groups is
  `planner_profile_from_sources(...)`, exactly as `readonly` has both a tier-only
  default seed and the evidence-backed `readonly_profile_from_sources(...)`. The
  docstring states this explicitly. (This reverses LM2C's deliberate
  `"planner" not in by_name`; that assertion is updated — it is the LM2F
  deliverable.)

`resolve_profile` needs no change (it derives `known_tiers` from records' `.tiers`,
which now include `planner_tier0`). **`reconcile_profile` DOES need a change** (the
spec's earlier "no changes" claim was wrong): its disposable-registry tier seeding
is gated by `profile_reconciliation._TIER_FIELDS`. That constant is changed to
**derive from the central tuple**:

```python
# profile_reconciliation.py
from rook.agent.capability_record import TIER_FIELDS
_TIER_FIELDS = frozenset(TIER_FIELDS)
```

so `planner_tier0` is recognized and the planner tier is actually activated.
Without this, `reconcile_profile` would treat `initial_tier="planner_tier0"` as the
malformed/empty case.

## Evidence facts (pinned by tests)

From the live constants (`rook.agent.planner`, `tool_groups`):

- `PLANNER_ALLOWED_GROUPS = {gh_exploration, gh_knowledge, layers, rhino_measurement, rhino_selection, viewport}`.
- `planner_excluded_mcp_only_groups` (allowed ∩ MCP-only) =
  **`("gh_exploration", "gh_knowledge")`**.
- All six allowed groups exist in `TOOL_GROUPS`, so the `groups.keys()` filter
  drops none here; `planner_profile_from_sources(...).groups` (allowed ∩ defined
  − mcp_only) = **`("layers", "rhino_measurement", "rhino_selection", "viewport")`**.
- `PLANNER_TIER_0 = {gh_errors, gh_knowledge_query, gh_snapshot, knowledge_query,
  request_tools, rhino_geometry, rhino_knowledge_query, rhino_objects,
  rhino_ping, search_tools}` (currently equal to `READONLY_TIER_0`, but modeled
  as its own evidence since they may diverge).
- Of those, **`gh_knowledge_query`, `knowledge_query`, `rhino_knowledge_query`**
  are local-handler-backed (in `build_local_tools()`), so a faithful per-runtime
  reconcile fixture must mark them in `local_tool_names` (LM2E) to avoid false
  `not_dispatchable`.

## Out of scope

- `PLANNER_LOCAL_CATALOG` (deferred — tier + allowed-groups suffices).
- No constant relocation; `planner.py` is unchanged.
- `external_mcp` → LM2G; `rookchat_cloud` deferred.
- No `resolve_profile`/`reconcile_profile`/`classify_visible_tool` change.
- No runtime/policy change.

## Testing

**Drift tests (tier-name boundary — "prove every boundary agrees"):**
- `TIER_FIELDS` membership: every name in `TIER_FIELDS` is a real
  `SurfaceSources` dataclass field (`dataclasses.fields`).
- `profile_reconciliation._TIER_FIELDS == frozenset(TIER_FIELDS)`.
- `reconcile_active_schemas`'s `initial` `Literal` args ==
  `set(TIER_FIELDS)` (via `typing.get_type_hints` to resolve the
  `from __future__ import annotations` string form).
- `ProfileDefinition.initial_tier` Literal args == `set(TIER_FIELDS)`
  (resolve the `Optional[Literal[...]]`, find the `Literal`, compare its args).

These fail loudly if any tier-name site drifts from the central tuple.

**`test_capability_record.py`:** `SurfaceSources()` has `planner_tier0 == frozenset()`
and `planner_allowed_groups == frozenset()` (defaults; back-compat).

**`test_capability_inventory.py`:**
- `collect_live_sources()` populates `planner_tier0 == frozenset(PLANNER_TIER_0)`
  and `planner_allowed_groups == frozenset(PLANNER_ALLOWED_GROUPS)` (live-constants).
- `_tiers_for`: a `SurfaceSources(planner_tier0={"x"})` → `build_inventory`
  record for `x` has `"planner_tier0"` in `.tiers`.
- **Light-import probe (subprocess):** importing `capability_inventory` and
  calling `collect_live_sources()` does not load `dspy` / `litellm` /
  `rook.agent.base_agent`.

**`test_execution_profile.py`:**
- `planner_profile_from_sources` synthetic filter test: `{a, b, gh_knowledge}`
  allowed with `gh_knowledge` MCP-only and `ghost` allowed-but-undefined →
  `groups == ("a","b")`, `name=="planner"`, `initial_tier=="planner_tier0"`.
- `planner_excluded_mcp_only_groups` synthetic + **real-constant pin** ==
  `("gh_exploration", "gh_knowledge")`.
- `default_profile_definitions()` now == `{rookchat_local, readonly, planner}`;
  `planner` is `initial_tier="planner_tier0", groups=()` (tier-only); the
  constant is still no-arg and stable.

**`test_profile_reconciliation.py` — runtime-faithful planner reconcile:**
- Fixture uses **runtime-style `local_tool_names`** (LM2E): a planner-tier tool
  that is local-handler-backed (e.g. `knowledge_query`) is included in
  `sources.local_tool_names`, and a `planner_tier0`-tier'd, catalog-present tool
  resolves with **no** `not_dispatchable` for it. Paired negative (empty
  `local_tool_names`) shows the false positive returns — proving the test would
  catch a regression and that LM2F doesn't resurrect the class LM2E fixed.

**Back-compat:** existing LM2A–E tests pass unchanged (new fields defaulted;
`initial_tier` Literal extension is additive; the only updated assertion is the
`default_profile_definitions` membership set).

## Invariants

- `TIER_FIELDS` is the single source of truth for tier field/names; `_tiers_for`,
  `_universe`, and `profile_reconciliation._TIER_FIELDS` derive from it; the two
  static `Literal`s are pinned to it by drift tests. No tier-name set is hardcoded
  in more than one place except the (drift-tested) `Literal`s.
- `_tiers_for`/`_universe` refactor is behavior-preserving for the existing three
  tiers (the `TIER_FIELDS` iteration yields the same membership + sort).
- `SurfaceSources` gains two defaulted fields; `collect_live_sources` populates
  them; importing it stays light (probe-guarded).
- `execution_profile.py` import allow-list unchanged (`planner_profile_from_sources`
  reads only `SurfaceSources`).
- `planner.py` unchanged; constants not relocated; `PLANNER_LOCAL_CATALOG` unused.
- `default_profile_definitions()` planner seed is diagnostic/tier-only, not
  runtime policy; `resolve_profile`/`reconcile_profile`/`classify_visible_tool`
  unchanged.
- All tuple outputs sorted; read-only/diagnostic.

## File Touch List

- Modify: `mcp_server/src/rook/agent/capability_record.py` — `TIER_FIELDS`
  constant + 2 `SurfaceSources` fields.
- Modify: `mcp_server/src/rook/agent/capability_inventory.py` — `_tiers_for` and
  `_universe` derive from `TIER_FIELDS`; `reconcile_active_schemas` `initial`
  Literal += `planner_tier0`; `collect_live_sources` planner population.
- Modify: `mcp_server/src/rook/agent/profile_reconciliation.py` —
  `_TIER_FIELDS = frozenset(TIER_FIELDS)`.
- Modify: `mcp_server/src/rook/agent/execution_profile.py` — `initial_tier`
  Literal += `planner_tier0`, `planner_profile_from_sources`,
  `planner_excluded_mcp_only_groups`, `default_profile_definitions` planner seed.
- Modify tests: `test_capability_record.py`, `test_capability_inventory.py`,
  `test_execution_profile.py`, `test_profile_reconciliation.py` (incl. the 4 drift
  tests).
