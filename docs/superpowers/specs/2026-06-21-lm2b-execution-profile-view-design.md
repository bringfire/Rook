# LM2B: Read-Only Execution-Profile View Design

## Status

Design draft for senior review. This document defines the **LM2B** slice only —
a read-only `execution_profile` representation over Rook's existing tiers/groups,
resolved against the LM2A `CapabilityInventory`.

It must NOT be treated as approval for: an authoritative runtime profile catalog;
replacement of `ToolRegistry`; mutation of tool visibility; compilation of active
model-visible schemas; a provider/model profile system; PlanGraph integration;
or live Rhino/GH execution.

## Context

LM2A (merged, PR #293, merge commit `e11abec`) produced a read-only
`CapabilityInventory`: per-tool `CapabilityRecord`s carrying `tiers`, `groups`,
`dispatch_path`, `has_schema`, `risk`, `no_argument`, `mcp_only`, and a derived
`visibility` (`local_visible` / `mcp_only_visible` / `support_only`), plus
inventory-level `findings`.

The north-star (§5.2, §6.2) names execution profiles — `external_mcp`,
`rookchat_cloud`, `rookchat_local`, `readonly`, `planner` — but **no
`execution_profile` exists in code today**; the local surface is expressed only
through tier sets (`TIER_0`/`AGENT_TIER_0`/`READONLY_TIER_0`) and `TOOL_GROUPS`.

LM2B adds the first read-only `execution_profile` representation. A profile names
an intended initial tier, intended groups, and optional explicit tool pins. The
resolver expands that to an intended tool set **purely by inverting the LM2A
inventory records** (no `SurfaceSources`, no dispatch-table rescan), inherits
each tool's facts from its record, and emits findings when an intended tool is
unknown, MCP-only, non-dispatchable, or schema-missing. The output is a
diagnostic, deterministic artifact. It changes no runtime behavior.

`execution_profile` here is an execution-policy concept, **not** a provider/model
profile.

## Goals

- Define stdlib-only profile types: `ProfileDefinition`, `ProfileFinding`,
  `ProfileResolution`.
- Provide a pure resolver `resolve_profile(definition, inventory)` (and
  `resolve_profiles(definitions, inventory)`) that consumes only injected
  `ProfileDefinition`s plus an LM2A `CapabilityInventory`.
- Derive intended membership by inverting inventory records; never read
  `SurfaceSources` or rescan dispatch tables inside the resolver.
- Emit provenance-aware findings (unknown tier/group/tool, MCP-only,
  non-dispatchable, missing-schema, empty-profile) with deterministic severities.
- Provide a small **non-authoritative** diagnostic seed helper
  `default_profile_definitions()` for `rookchat_local` and `readonly`.
- Provide a pure secondary `format_profile_report(resolutions)`.
- Keep all output deterministic and all tests non-live.

## Non-Goals

- No authoritative runtime profile catalog or policy.
- No `ToolRegistry` replacement, no mutation of runtime tool visibility.
- No compilation of active model-visible schemas.
- No provider/model profile system (`execution_profile` is execution policy only).
- No `SurfaceSources` argument on the resolver; no dispatch-table rescan.
- No re-derivation of facts the inventory already holds.
- No PlanGraph integration, no MCP wire change, no file writes, no live Rhino/GH.
- No `planner` or `external_mcp` in the default seeds (see Future Work).

## Module Boundary

Create one module:

`mcp_server/src/rook/agent/execution_profile.py` — **stdlib-only** (imports only
`dataclasses`, `typing`, `collections.abc`, and `rook.agent.capability_record`).
It holds the types, the resolver, the seed helper, and the formatter. No split is
needed: the resolver consumes an already-built `CapabilityInventory`, so nothing
heavier than the stdlib-only LM2A record module is required, and
`default_profile_definitions()` returns a constant tier-only set with no
arguments.

Tests:

`mcp_server/tests/test_execution_profile.py`

Import direction:

```text
execution_profile imports capability_record (stdlib-only) only
execution_profile imports no tool_groups / tool_dispatcher / tool_registry /
  tool_contracts / capability_inventory
```

Live coupling stays in LM2A: a caller builds the inventory and live sources via
`build_inventory(...)` / `collect_live_sources()` and passes the results in.

## Data Model

`Severity` is reused from `capability_record` (`Literal["info","warning","error"]`).

### ProfileDefinition

```python
@dataclass(frozen=True)
class ProfileDefinition:
    name: str
    initial_tier: Literal["tier0", "agent_tier0", "readonly_tier0"] | None = None
    groups: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()          # explicit pins, additive
    description: str | None = None
```

### ProfileFinding

```python
@dataclass(frozen=True)
class ProfileFinding:
    profile: str                          # owning profile name
    code: str
    subject: str                          # offending tool / group / tier name
    severity: Severity
    message: str
```

### ProfileResolution

```python
@dataclass(frozen=True)
class ProfileResolution:
    profile: ProfileDefinition
    tools: tuple[CapabilityRecord, ...]   # resolved KNOWN records, sorted by name
    tool_names: tuple[str, ...]           # intended names (incl. unknown pins), sorted/deduped
    findings: tuple[ProfileFinding, ...]  # sorted by (code, subject)
```

`tool_names` is everything the profile intends (tier ∪ groups ∪ pins), including
explicit pins that have no record. `tools` is the resolved subset that has
records. The distinction lets a consumer see asked-for vs. resolved.

## Resolver

`resolve_profile(definition: ProfileDefinition, inventory: CapabilityInventory)
-> ProfileResolution`.

Algorithm (pure; inverts inventory records once):

1. Build indexes from `inventory.records`:
   - `by_name = {r.name: r for r in records}`
   - `known_groups = {g for r in records for g in r.groups}`
   - `known_tiers = {t for r in records for t in r.tiers}`
2. Expand intended names:
   - `tier_names = {r.name for r in records if definition.initial_tier in r.tiers}`
     when `initial_tier is not None`, else empty.
   - `group_names = ∪ over g in definition.groups of {r.name for r in records if g in r.groups}`.
   - `pin_names = set(definition.tools)`.
   - `intended = sorted(tier_names | group_names | pin_names)`.
3. Resolve records: `tools = tuple(by_name[n] for n in intended if n in by_name)`
   (already name-sorted because `intended` is sorted).
4. Emit findings (see table). Records found via tier/group inversion always have
   records, so `unknown_tool` arises only from explicit pins.
5. `tool_names = tuple(intended)`.
6. Return `ProfileResolution(definition, tools, tool_names, sorted_findings)`.

`resolve_profiles(definitions, inventory) -> tuple[ProfileResolution, ...]`
maps the resolver over a sequence of definitions, preserving input order.

The resolver never reads `SurfaceSources`, never imports `tool_groups` /
`tool_dispatcher`, and never recomputes dispatch/risk/schema facts — it reads
them off the records.

## Findings And Severity

Provenance-aware, mirroring LM2A so `mcp_only` and `not_dispatchable` do not
double-fire for the same tool:

| code | condition | severity |
|------|-----------|----------|
| `unknown_tier` | `initial_tier` is not None and not in `known_tiers` | warning |
| `unknown_group` | a `definition.groups` entry is not in `known_groups` | warning |
| `unknown_tool` | a `definition.tools` pin has no record | warning |
| `mcp_only_tool` | intended tool with `record.mcp_only` or `record.visibility == "mcp_only_visible"` | warning |
| `not_dispatchable` | intended **local_visible** tool with `record.dispatch_path is None` | error |
| `missing_schema` | intended **local_visible** tool with `record.has_schema is False` | warning |
| `empty_profile` | `tools` (resolved known records) is empty | warning |

Per-tool finding logic (for each intended name `n` with record `r`):

```text
if r.mcp_only or r.visibility == "mcp_only_visible":
    -> mcp_only_tool (warning)
elif r.visibility == "local_visible" and r.dispatch_path is None:
    -> not_dispatchable (error)
if r.visibility == "local_visible" and not r.has_schema:
    -> missing_schema (warning)
```

The `mcp_only` branch short-circuits `not_dispatchable` (an MCP-only tool is
expected to lack a local dispatch path — it yields only `mcp_only_tool`). The
`local_visible` gate keeps `missing_schema`/`not_dispatchable` from firing on
MCP-only or support-only tools. `missing_schema` can co-occur with a dispatchable
local tool.

`empty_profile` fires when the resolved known tool set is empty. It is reported
for actual resolution inputs only; it is never produced by shipping an empty
default seed (the defaults are non-empty — see below).

Findings are deterministically ordered: within a resolution, sorted by
`(code, subject)`.

## Diagnostic Seed Profiles

`default_profile_definitions() -> tuple[ProfileDefinition, ...]` returns a small,
**non-authoritative** constant set. It maps known names onto existing tier
references for diagnostic convenience; it is not runtime policy. Both seeds are
**tier-only** (`groups=()`), so the helper needs no `sources` argument.

- `rookchat_local`: `initial_tier="agent_tier0"`, `groups=()`,
  `description="Local in-file execution worker (diagnostic seed)."` No groups are
  named yet (local default groups are deferred).
- `readonly`: `initial_tier="readonly_tier0"`, `groups=()`,
  `description="Observation-only worker (diagnostic seed)."` No groups are named
  yet: a `*_readonly` name suffix is NOT a faithful proxy for the repo's
  `READONLY_ALLOWED_GROUPS` policy (e.g. `video_readonly` matches the suffix but
  is not in `READONLY_ALLOWED_GROUPS` and not in `MCP_ONLY_GROUPS`), so seeding
  by suffix would look more permissive than current readonly policy. Readonly
  group membership is deferred until the source snapshot carries explicit
  evidence (see Future Work).

No `planner` seed (a seeded empty/TBD profile would surface a misleading
`empty_profile` warning) and no `external_mcp` seed (its visibility needs a
separate interpretation). Both names are recorded in Future Work. The resolver
still handles an arbitrary injected `planner`/`external_mcp` definition if a
caller (or test) supplies one.

## Formatter

`format_profile_report(resolutions: tuple[ProfileResolution, ...]) -> str` renders
a human-readable summary (per profile: name, resolved tool count, finding counts
by severity, the findings). Pure, deterministic, no I/O. Secondary to the
structured `ProfileResolution`.

## Determinism

- `tools` sorted by name; `tool_names` sorted and deduped.
- Findings sorted by `(code, subject)` within a resolution.
- `resolve_profiles` preserves input definition order.
- No set-iteration order leaks into output; convert to sorted sequences before
  emitting.
- `default_profile_definitions()` returns a constant, deterministic set.

## Test Strategy

Add `mcp_server/tests/test_execution_profile.py`, deterministic and non-live,
driven by a tiny canned `CapabilityInventory` (hand-built `CapabilityRecord`s with
varied facts) and canned `ProfileDefinition`s.

Canned records should include:

- a `local_visible` dispatchable tool with a schema (no finding),
- a `local_visible` tool with `dispatch_path=None` (→ `not_dispatchable` error),
- a `local_visible` tool with `has_schema=False` (→ `missing_schema` warning),
- an `mcp_only` / `mcp_only_visible` tool with `dispatch_path=None` (→ only
  `mcp_only_tool`, NOT `not_dispatchable`),
- tools tagged with a tier label and a group label so inversion has something to
  expand.

Required tests:

- Tier expansion: a profile with `initial_tier="agent_tier0"` resolves exactly the
  records whose `tiers` contain `agent_tier0`.
- Group expansion: a profile naming a real group resolves the records whose
  `groups` contain it.
- Explicit pins are additive and deduped with tier/group expansion;
  `tool_names` is sorted.
- `unknown_tier` (warning) when `initial_tier` matches no record.
- `unknown_group` (warning) when a named group is absent from all records.
- `unknown_tool` (warning) when an explicit pin has no record.
- `mcp_only_tool` (warning) fires and `not_dispatchable` does NOT for an MCP-only
  tool with no dispatch path.
- `not_dispatchable` (error) for a local_visible tool with `dispatch_path=None`.
- `missing_schema` (warning) only for local_visible tools without a schema.
- `empty_profile` (warning) when a profile resolves to zero known tools.
- `tools` are sorted by name; findings sorted by `(code, subject)`.
- `resolve_profiles` preserves definition order.
- `default_profile_definitions()`: returns `rookchat_local` (`agent_tier0`,
  `groups=()`) and `readonly` (`readonly_tier0`, `groups=()`); contains no
  `planner` and no `external_mcp`; returns a constant deterministic set.
- An injected `planner` definition still resolves (proving the resolver is not
  hardcoded to the seed names).
- `format_profile_report` is pure and returns a stable string for fixed input.

Boundary check:

- AST direct-import check: `execution_profile.py` imports only stdlib +
  `rook.agent.capability_record`; it does NOT import `tool_groups`,
  `tool_dispatcher`, `tool_registry`, `tool_contracts`, or `capability_inventory`.

Suggested verification:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_execution_profile.py -q
mcp_server\.venv\Scripts\python.exe -m py_compile mcp_server/src/rook/agent/execution_profile.py
git diff --check
```

## Acceptance Criteria

- `ProfileDefinition`, `ProfileFinding`, `ProfileResolution` exist as frozen
  dataclasses in `execution_profile.py`; the module is stdlib-only (no
  `tool_groups`/`tool_dispatcher`/`tool_registry`/`tool_contracts`/
  `capability_inventory` imports), proven by an AST check.
- `resolve_profile(definition, inventory)` derives intended membership by
  inverting inventory records, with no `SurfaceSources` argument and no dispatch
  rescan.
- Findings match the severity table; `mcp_only_tool` and `not_dispatchable` do
  not double-fire; `not_dispatchable`/`missing_schema` are gated to
  `local_visible`.
- `unknown_tier`/`unknown_group`/`unknown_tool`/`empty_profile` are warnings;
  `not_dispatchable` is an error.
- `default_profile_definitions()` returns only `rookchat_local` and `readonly`,
  both tier-only (`groups=()`); no `planner`, no `external_mcp`.
- All tuple outputs and findings are deterministically ordered.
- `format_profile_report` is pure and secondary.
- No runtime visibility, `ToolRegistry`, ChatRunner, dispatcher, MCP wire, or
  PlanGraph behavior changes.

## Future Work

Future LM2 slices may: carry explicit readonly group evidence (likely
`READONLY_ALLOWED_GROUPS` from `tool_groups.py`) into the source snapshot so the
default `readonly` seed can include groups faithfully — rather than inferring
them from a name suffix, and without editing LM2A's `SurfaceSources` purely to
carry it until then; add `planner` and `external_mcp` profiles with deliberate,
evidence-backed membership and (for `external_mcp`) a distinct visibility
interpretation; promote profiles from diagnostic seeds toward an audited surface
compiler the registry consults; diff a profile's intended view against the
disposable-registry reconciliation from LM2A; and add execution-policy budgets
(tool/context/repair) per profile. All are out of scope for LM2B.
