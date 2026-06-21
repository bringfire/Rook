# LM2A: Capability Inventory Reconciliation Design

## Status

Design draft for senior review. This document defines the **LM2A** slice only —
a read-only capability inventory and reconciliation report over Rook's existing
RookChat/local tool-surface sources.

It must NOT be treated as approval for: an active "surface compiler" that feeds
or replaces `ToolRegistry`; mutation of runtime tool visibility; an
`execution_profile` implementation; a persistent capability registry;
PlanGraph integration; MCP wire-shape changes; or live Rhino/GH execution.

## Context

The LM1 scaffold is complete and proven end to end: raw tool result →
`ToolResultView` + `script_receipt` → `NodeOutcome` → `apply_tool_result` →
PlanGraph reducer → graph memory + repair readiness + completion (LM1A–LM1G,
LM1G merged to `main` as PR #291).

LM2 begins moving from scattered tool exposure toward a canonical capability
contract layer (north-star §5.3, §6, roadmap LM2). A surface audit of the
current code established three load-bearing facts that scope LM2A:

1. **No `execution_profile` exists in code.** The local surface is expressed
   only through tool *groups* (`TOOL_GROUPS`, `MCP_ONLY_GROUPS` in
   `mcp_server/src/rook/agent/tool_groups.py`) and three tier sets (`TIER_0`,
   `AGENT_TIER_0`, `READONLY_TIER_0`).
2. **No capability record exists.** The fields the north-star wants
   (name/groups/dispatch_path/risk/no-arg/reachability) are real but scattered
   across ≥4 modules: the LiteLLM catalog in
   `tool_registry.py`; dispatch membership in `tool_dispatcher.py`
   (`BRIDGE_ROUTES`, `TRANSFORM_FUNCTIONS`, runtime `local_tools`); risk sets in
   `agent/chat/execution_policy.py` (`CREATION_TOOLS`, `MODAL_RISK_TOOLS`,
   `NEEDS_VERIFICATION`); reachability in `MCP_ONLY_GROUPS`.
3. **LM1A's `audit_visible_tool_dispatchability(...)` is built but never
   called.** It is ready-made and currently has no runtime consumer.

LM2A unifies a **read-only view** of those scattered sources into capability
records, and reuses the LM1A audit as a diagnostic over a deterministic
disposable registry. It changes no runtime behavior.

## Goals

- Define a minimal, plain **capability record** and finding type (frozen
  dataclasses, fields only where real evidence exists).
- Build a deterministic, read-only **inventory** from an injected
  `SurfaceSources` snapshot plus a catalog dictionary.
- Provide a **reconciliation** layer that builds a disposable `ToolRegistry`
  from a canned catalog and compares intended membership against the schemas it
  actually activates (initial surface and post-`request_group`), reusing the
  LM1A dispatchability audit over those active schemas.
- Provide a thin live **collector** that reads module constants only, as a
  diagnostic convenience.
- Provide a pure **string formatter** as a secondary rendering of the
  structured product.
- Make unknowns **explicit findings**, never invented defaults.

## Non-Goals

- No active surface compilation; nothing feeds or replaces `ToolRegistry` at
  runtime.
- No mutation of runtime/shared tool visibility.
- No `execution_profile` type or membership implementation.
- No persistent capability registry, on-disk record store, or file writes.
- No ChatRunner, dispatcher, server, or MCP wire-shape changes.
- No new behavioral gate. `audit_visible_tool_dispatchability(...)` stays a
  read-only diagnostic dependency.
- No PlanGraph integration.
- No live Rhino/GH dependency, no MCP `list_tools`, no read of
  `knowledge/agent_tool_catalog.json`, no instantiation of `ToolDispatcher`.

## Module Boundary

Create two modules in the agent layer (import-light is not required here; the
pure types module nonetheless avoids the heavy dispatcher import):

- `mcp_server/src/rook/agent/capability_record.py` — **stdlib-only pure types**
  (`dataclasses`, `typing`, `enum` if needed). Contains `SurfaceSources`,
  `CapabilityRecord`, `CapabilityFinding`, `CapabilityInventory`. It must NOT
  import `rook.agent.chat.tool_contracts` (which imports `tool_dispatcher` at
  module load), `DispatchContext`, or anything heavier than stdlib. The
  `DispatchContext` mapping lives in `capability_inventory.py`, not here.
- `mcp_server/src/rook/agent/capability_inventory.py` — the **read-only
  builder/reconciler**: `build_inventory(...)`, `reconcile_active_schemas(...)`,
  `collect_live_sources()`, `format_report(...)`, and the internal
  `_dispatch_context_from_sources(sources) -> DispatchContext` helper. Imports
  `tool_groups`, dispatch membership sets from `tool_dispatcher`,
  `execution_policy`, `tool_registry.ToolRegistry`, and reuses
  `tool_contracts.audit_visible_tool_dispatchability` / `classify_visible_tool`
  / `DispatchContext`.

Tests:

- `mcp_server/tests/test_capability_inventory.py`
- `mcp_server/tests/test_capability_record.py` (if record-level logic warrants a
  separate file)

Import direction:

```text
capability_inventory imports capability_record, tool_groups, tool_dispatcher,
  execution_policy, tool_registry, tool_contracts
capability_record imports only stdlib (no tool_contracts, no tool_dispatcher)
```

## Data Model

### SurfaceSources (injected snapshot — the determinism boundary)

```python
@dataclass(frozen=True)
class SurfaceSources:
    # tier membership (tool_groups.py)
    tier0: frozenset[str]
    agent_tier0: frozenset[str]
    readonly_tier0: frozenset[str]
    # group membership
    groups: Mapping[str, tuple[str, ...]]      # TOOL_GROUPS: group -> tool names
    mcp_only_groups: frozenset[str]            # group NAMES (MCP_ONLY_GROUPS)
    # dispatch surfaces (feed DispatchContext)
    bridge_names: frozenset[str]               # BRIDGE_ROUTES keys
    transform_names: frozenset[str]            # TRANSFORM_FUNCTIONS keys
    intercepted_names: frozenset[str]          # ChatRunner/meta pseudo-tools
    excluded_names: frozenset[str]             # named exclusions
    local_tool_names: frozenset[str] = frozenset()   # MUST be explicitly provided
    # behavioral flags
    zero_argument_names: frozenset[str] = frozenset()        # ZERO_ARGUMENT_TOOLS
    strict_no_argument_names: frozenset[str] = frozenset()   # STRICT_NO_ARGUMENT_BRIDGE_TOOLS
    # risk (execution_policy.py)
    creation_tools: frozenset[str] = frozenset()
    modal_risk_tools: frozenset[str] = frozenset()
    needs_verification: frozenset[str] = frozenset()
```

Notes:

- `intercepted_names` must include the full ChatRunner/meta surface:
  `request_tools`, `search_tools`, `ui_block`, `list_chat_models`,
  `set_chat_model`. These must not fall into `dispatch_unknown`.
- `local_tool_names` defaults empty and is only populated when the caller
  explicitly supplies it. LM2A must never instantiate `ToolDispatcher` to
  discover runtime `_local_tools`.

The `DispatchContext` for LM1A audit reuse is built in `capability_inventory.py`
by `_dispatch_context_from_sources(sources)` — kept out of the record module so
`capability_record.py` stays stdlib-only (importing `DispatchContext` from
`tool_contracts` would pull in `tool_dispatcher`). It is a total, direct mapping:

```python
DispatchContext(
    intercepted_names=sources.intercepted_names,
    local_tool_names=sources.local_tool_names,
    transform_names=sources.transform_names,
    bridge_names=sources.bridge_names,
    excluded_names=sources.excluded_names,
    strict_no_argument_names=sources.strict_no_argument_names,
)
```

### Visibility provenance (derived)

To make `dispatch_unknown` severity correct, each record carries a derived
`visibility` classification (string literal):

```python
Visibility = Literal[
    "local_visible",     # in a tier set, or a group NOT in mcp_only_groups
    "mcp_only_visible",  # appears only in groups that are all in mcp_only_groups
    "support_only",      # not in any tier/group; present only via catalog/risk/dispatch sources
]
```

`local_visible` takes precedence: if a tool is in any tier set or any non-MCP
group, it is `local_visible` even if it also appears in an MCP-only group (that
co-membership is separately a `contradictory_membership` finding).

### CapabilityRecord

```python
@dataclass(frozen=True)
class CapabilityRecord:
    name: str
    visibility: Visibility
    tiers: tuple[str, ...]          # sorted: subset of {"tier0","agent_tier0","readonly_tier0"}
    groups: tuple[str, ...]         # sorted group names containing the tool
    dispatch_path: str | None       # classify_visible_tool result, or None when "failure"
    has_schema: bool                # present in the provided catalog
    risk: tuple[str, ...]           # sorted subset of {"creation","modal_risk","needs_verification"}
    no_argument: bool               # in zero_argument_names or strict_no_argument_names
    mcp_only: bool                  # all containing groups are MCP-only (and tool is in >=1 group)
```

`dispatch_path` values come from `classify_visible_tool`:
`"chatrunner_intercepted" | "dispatcher_local_tool" | "dispatcher_transform" |
"bridge_route" | "explicitly_excluded"`, or `None` when the classifier returns
`"failure"`. `None` is never replaced with an invented default; it produces a
finding (severity per rules below).

### CapabilityFinding

```python
@dataclass(frozen=True)
class CapabilityFinding:
    code: str
    tool: str
    severity: Literal["info", "warning", "error"]
    message: str
```

Finding `code` values for LM2A:

- `dispatch_unknown` — no dispatch/intercept/transform/bridge/exclusion path.
- `missing_schema` — a `local_visible` tool with no schema in the catalog.
- `contradictory_membership` — tool in both an MCP-only group and a non-MCP
  group.
- LM1A audit codes folded in from reconciliation: `not_dispatchable`,
  `duplicate_visible_name`, `strict_no_arg_schema_drift`,
  `missing_function_name`.

### CapabilityInventory

```python
@dataclass(frozen=True)
class CapabilityInventory:
    records: tuple[CapabilityRecord, ...]        # sorted by name
    findings: tuple[CapabilityFinding, ...]      # deterministic order (see Determinism)
```

The structured `CapabilityInventory` is the actual product. `format_report` is
secondary.

## Static Inventory Layer

`build_inventory(sources: SurfaceSources, catalog: Mapping[str, dict]) ->
CapabilityInventory` is the **deterministic test entry point**.

Algorithm:

1. **Universe** of tool names = union of: all tier sets; every member of every
   group; `bridge_names`; `transform_names`; `intercepted_names`;
   `excluded_names`; `local_tool_names`; `creation_tools`; `modal_risk_tools`;
   `needs_verification`; and the catalog keys.
2. For each name (iterated in sorted order), build a `CapabilityRecord`:
   - `tiers`, `groups` from membership (sorted).
   - `visibility` per the provenance rules above.
   - `dispatch_path = classify_visible_tool(name,
     _dispatch_context_from_sources(sources))` mapped to `None` on `"failure"`.
   - `has_schema = name in catalog`.
   - `risk`, `no_argument`, `mcp_only` from the respective sources.
3. Emit findings (no LM1A audit here — see Non-Goals item on the audit):
   - **`dispatch_unknown`** when `dispatch_path is None`, with **provenance-aware
     severity** keyed on `visibility` alone (because `local_visible` already
     means "in a tier or a non-MCP group", i.e. genuinely locally reachable):
     - `error` — `visibility == "local_visible"` (a locally reachable tool with
       no dispatch/intercept/exclusion path — the toxic case for local models).
     - `info` — `visibility == "mcp_only_visible"` (expected to lack a local
       dispatch path; the dual-membership case is caught separately as
       `contradictory_membership`).
     - `warning` — `visibility == "support_only"` (catalog-only / risk-only /
       dispatch-table-only name with no resolvable path).
   - **`missing_schema`** (`warning`) when `visibility == "local_visible"` and
     `has_schema is False`.
   - **`contradictory_membership`** (`error`) when the tool is in at least one
     MCP-only group and at least one non-MCP group.

`build_inventory` performs no I/O and imports nothing heavy beyond the pure
classifier; it operates entirely on its arguments.

## Reconciliation Layer (active-schema evidence)

`reconcile_active_schemas(sources: SurfaceSources, catalog: Mapping[str, dict],
*, group: str | None = None, initial: Literal["tier0", "agent_tier0",
"readonly_tier0"] = "agent_tier0") -> tuple[CapabilityFinding, ...]`.

- Selects the deterministic initial tier from the injected sources:
  `selected_tier = getattr(sources, initial)`. This avoids depending on
  `ToolRegistry`'s live `TIER_0` default.
- Builds a **disposable** `ToolRegistry` from the **canned `catalog`** only, with
  the initial tier pinned explicitly:
  `ToolRegistry(catalog=..., tier0=set(selected_tier))`. Never the live cache,
  never MCP, never a shared/runtime registry.
- If `group is None`, reconcile the initial active surface.
- If `group` is provided, call `registry.request_group(group)` on the disposable
  registry, then reconcile the resulting active surface. Mutating this disposable
  registry via `request_group` is explicitly allowed; mutating any
  runtime/shared registry is not.
- Read `registry.get_active_schemas()` → the **actual** active schema list.
- Run `audit_visible_tool_dispatchability(active_schemas,
  _dispatch_context_from_sources(sources))` over **those active schemas only**
  (never the whole catalog) and fold each `DispatchabilityFinding` into a
  `CapabilityFinding` (severity mapping below).
- Diff **intended vs. actual**, where the intended set is:
  - `selected_tier` when `group is None`;
  - `selected_tier | sources.groups.get(group, ())` when `group` is provided —
    post-`request_group` active schemas include the initial tier plus the
    requested group, so the initial tier MUST be in the intended set to avoid
    false `active_not_intended` findings for Tier-0/meta tools.
  - `warning` finding when an intended tool is absent from the active schemas
    (`intended_not_active`), and when an active schema is not in the intended
    set (`active_not_intended`).

**ToolRegistry group caveat:** even with a canned catalog, `ToolRegistry` builds
its group membership from the live `TOOL_GROUPS` table, not from
`SurfaceSources.groups`. For LM2A this is acceptable, but the canned
reconciliation fixture must therefore use **real group names and members from
the current code path** so `request_group(group)` resolves. `SurfaceSources.groups`
remains the **intended-membership reference** for the static inventory layer.
Tests should pick a small real group (e.g. `gh_canvas`) and a catalog containing
its real members.

LM1A `DispatchabilityFinding` → `CapabilityFinding` severity mapping:

- `not_dispatchable` → `error`
- `missing_function_name` → `error`
- `strict_no_arg_schema_drift` → `error`
- `duplicate_visible_name` → `warning`

## Live Collector (diagnostic convenience only)

`collect_live_sources() -> SurfaceSources` reads module-level constants only:
`TOOL_GROUPS`, `MCP_ONLY_GROUPS`, `TIER_0`, `AGENT_TIER_0`, `READONLY_TIER_0`,
`LOCAL_TIER_0_DISPATCH_EXCLUSIONS`, `BRIDGE_ROUTES.keys()`,
`TRANSFORM_FUNCTIONS.keys()`, `ZERO_ARGUMENT_TOOLS`,
`STRICT_NO_ARGUMENT_BRIDGE_TOOLS`, and `execution_policy` risk sets. The
ChatRunner/meta `intercepted_names` are supplied as a module-level constant in
`capability_inventory.py`.

It must NOT: read `agent_tool_catalog.json`; call MCP; instantiate a live
`ToolRegistry`; instantiate or inspect a `ToolDispatcher`; or populate
`local_tool_names` (left empty unless a caller supplies it elsewhere). The live
collector is convenience/diagnostic; `build_inventory` with injected
`SurfaceSources` is the source of deterministic tests.

## Formatter (pure, secondary)

`format_report(inventory: CapabilityInventory) -> str` renders a human-readable
summary (record count, finding counts by severity, the findings list). Pure, no
I/O, deterministic. It is a convenience over the structured product, not the
product.

## Determinism

- Every tuple output (`tiers`, `groups`, `risk`, `records`) is sorted with a
  stable key.
- `findings` are emitted in a deterministic order: sort by `(tool, code,
  severity)`.
- No use of set iteration order in output; convert to sorted sequences before
  emitting.
- Tests assert no read of the live catalog cache path occurs in
  `build_inventory` / `reconcile_active_schemas`.

## Test Strategy

Add `mcp_server/tests/test_capability_inventory.py` (and optionally
`test_capability_record.py`) with deterministic, non-live tests driven by a tiny
but representative canned `SurfaceSources` + catalog. The seed set includes:

- a Tier-0 intercepted/meta tool (e.g. `request_tools`),
- a bridge-route tool,
- a transform or explicitly-provided local tool,
- a `gh_canvas` group member,
- a readonly-surface member,
- one intentionally **missing** catalog entry for a `local_visible` tool, to
  prove `missing_schema` fires rather than a silent default,
- one MCP-only-only tool, to prove it yields `info` (not `error`),
- one tool in both an MCP-only and a non-MCP group, to prove
  `contradictory_membership` (`error`).

Required tests:

- `build_inventory` produces records sorted by name; tiers/groups/risk tuples
  sorted.
- `dispatch_unknown` severity is provenance-aware: `error` for a local-visible
  tool with no path; `info` for MCP-only-visible; `warning` for support-only.
- `missing_schema` fires only for `local_visible` tools absent from the catalog.
- `contradictory_membership` fires (error) for dual MCP/non-MCP membership and
  `mcp_only` is not silently collapsed.
- `intercepted_names` members (`request_tools`, `search_tools`, `ui_block`,
  `list_chat_models`, `set_chat_model`) classify as
  `chatrunner_intercepted` and produce no `dispatch_unknown`.
- `_dispatch_context_from_sources(sources)` maps all six fields correctly.
- `reconcile_active_schemas(group=None)` reconciles the initial active surface
  (intended = selected tier); `reconcile_active_schemas(group="gh_canvas")`
  reconciles post-`request_group` (intended = selected tier `|` real `gh_canvas`
  members), and Tier-0/meta tools in the active set do NOT produce
  `active_not_intended`. The LM1A audit runs over active schemas only (a
  catalog-only undispatchable tool that is NOT active produces no
  `not_dispatchable` finding).
- LM1A `DispatchabilityFinding`s fold into `CapabilityFinding`s with the
  specified severities.
- `findings` order is deterministic across runs.
- `local_tool_names` defaults empty; nothing instantiates `ToolDispatcher`.
- `format_report` is pure and returns a stable string for a fixed inventory.

Boundary checks:

- `capability_record.py` imports only stdlib (AST direct-import check: no
  `tool_contracts`, no `tool_dispatcher`).
- A subprocess probe proves `import rook.agent.capability_record` does not load
  `rook.agent.tool_dispatcher` into `sys.modules`.
- `reconcile_active_schemas` does not read the live catalog cache path (assert
  via monkeypatch or path guard).

Suggested verification:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_capability_inventory.py mcp_server/tests/test_capability_record.py -q
mcp_server\.venv\Scripts\python.exe -m py_compile mcp_server/src/rook/agent/capability_record.py mcp_server/src/rook/agent/capability_inventory.py
git diff --check
```

## Acceptance Criteria

- `CapabilityRecord`, `CapabilityFinding` (with
  `severity: Literal["info","warning","error"]`), `SurfaceSources`,
  `CapabilityInventory` exist as frozen dataclasses in `capability_record.py`.
- `capability_record.py` is stdlib-only (no `tool_contracts`/`tool_dispatcher`
  import); `_dispatch_context_from_sources(sources)` in `capability_inventory.py`
  returns a total `DispatchContext` mapping.
- `build_inventory(sources, catalog)` is pure, deterministic, and the test entry
  point; it emits provenance-aware `dispatch_unknown`, `missing_schema`, and
  `contradictory_membership` findings, with no invented defaults.
- `reconcile_active_schemas(..., group=None|str, initial=...)` pins the initial
  tier explicitly via `ToolRegistry(tier0=...)`, supports initial and
  post-`request_group` reconciliation, defines intended as selected-tier (`|`
  group members), and runs the LM1A audit over active schemas only.
- `collect_live_sources()` reads module constants only — no catalog cache, no
  MCP, no live `ToolRegistry`, no `ToolDispatcher`.
- All tuple outputs and findings are deterministically ordered.
- `format_report` is pure and secondary.
- No runtime visibility, `ToolRegistry`, ChatRunner, dispatcher, MCP wire, or
  PlanGraph behavior changes.

## Future Work

Future LM2 slices may: add `execution_profile` membership; promote the inventory
into an audited surface compiler that the registry consults; persist or diff
capability records across builds; add startup diagnostics; and extend
reconciliation to the full LM1A fixture matrix. All are out of scope for LM2A.
