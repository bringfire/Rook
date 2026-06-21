# LM2D — Profile Reconciliation Against Disposable Active-Schema Evidence

**Date:** 2026-06-21
**Status:** Approved (design)
**Campaign:** Local/Internal Models roadmap (LM2 continuation)
**Branch:** `codex/lm2d-profile-reconciliation`

---

## Summary

LM2D composes the merged LM2 pieces to answer, for one profile:

- what tools the profile *intends* (LM2B `ProfileResolution.tool_names`);
- what a *disposable* `ToolRegistry` actually *activates* from a canned catalog
  for that profile's initial tier plus all of its groups;
- what LM1A dispatchability findings appear on those active schemas;
- what drift exists between intended names and registry-active names;
- what existing profile findings the resolution already carries.

It is **diagnostic / read-only**. It is NOT a surface compiler and NOT runtime
policy. It mutates no shared/runtime registry state — it builds one throwaway
`ToolRegistry` per call.

## Motivation

LM2A's `reconcile_active_schemas(sources, catalog, *, group=None, initial=...)`
reconciles **one optional group** against a disposable registry. A real profile
(LM2B/LM2C) carries an initial tier plus **multiple** groups. LM2D generalizes
the reconciliation to a whole profile: activate the profile's initial tier, then
`request_group` for every group, audit the resulting active surface once, and
compare it to the profile's already-resolved intended names.

Two confirmed behaviors are the diagnostic value, not bugs to hide:

1. **The activation seam.** `ToolRegistry.request_group` activates from the live
   `TOOL_GROUPS` table filtered to the catalog (`_build_groups`), *not* from
   `sources.groups`. So registry-active and profile-intended can legitimately
   diverge; that drift is the signal (same seam LM2A already documents).
2. **Group rejection.** `request_group` returns `{"success": False, "error": …}`
   for an MCP-only group (and for an unknown group). LM2D turns each rejection
   into a finding — never a crash, never a silent skip.

## Design

### New module: `mcp_server/src/rook/agent/profile_reconciliation.py`

A composition module — intentionally **not** import-light. It may import
`ToolRegistry`, the LM1A audit (`audit_visible_tool_dispatchability`,
`DispatchabilityFinding`), LM2A inventory helpers
(`dispatch_context_from_sources`, `capability_findings_from_audit`), LM2A record
types (`CapabilityFinding`, `SurfaceSources`), and LM2B profile types
(`ProfileResolution`, `ProfileFinding`).

#### Report type (one new frozen type)

```python
@dataclass(frozen=True)
class ProfileReconciliation:
    profile_name: str
    intended_names: tuple[str, ...]                  # = resolution.tool_names (already sorted)
    active_names: tuple[str, ...]                    # sorted, from the disposable registry
    registry_findings: tuple[CapabilityFinding, ...] # dispatchability + drift + group failures, sorted
    profile_findings: tuple[ProfileFinding, ...]     # carried verbatim from resolution, never reinterpreted
```

Two typed finding streams are kept distinct by provenance:
`registry_findings` (capability/registry/audit/drift evidence) vs
`profile_findings` (profile definition/resolution evidence). `ProfileFinding`s
are **never** folded into `CapabilityFinding`.

#### Public function

```python
def reconcile_profile(
    resolution: ProfileResolution,
    sources: SurfaceSources,
    catalog: Mapping[str, dict],
) -> ProfileReconciliation:
    ...
```

Algorithm:

1. `definition = resolution.profile`.
2. Tier members (safe lookup — never crash on `None` or a malformed tier):

   ```python
   initial = definition.initial_tier
   tier_members = (
       frozenset()
       if initial is None
       else frozenset(getattr(sources, initial, frozenset()))
   )
   ```

   A malformed/unknown injected tier yields an empty tier-0; the profile's own
   `unknown_tier` diagnosis is already carried in `resolution.findings`.
3. Build the disposable registry: `ToolRegistry(catalog=dict(catalog),
   tier0=set(tier_members))`. No `allowed_groups` (so only MCP-only / unknown
   rejections occur).
4. For each `g in definition.groups`, call `registry.request_group(g)`. If
   `not result.get("success")`, append:

   ```python
   CapabilityFinding(
       code="group_activation_failed",
       tool=g,
       severity="warning",
       message=result.get("error", f"Group '{g}' could not be activated."),
   )
   ```

   The registry's own error string carries the MCP-only-vs-unknown distinction;
   no separate code or severity split, no clever subject encoding.
5. `active_names = frozenset(...)` extracted from `registry.get_active_schemas()`
   (read each schema's `function.name`; ignore entries lacking a string name).
6. `ctx = dispatch_context_from_sources(sources)`; run
   `audit_visible_tool_dispatchability(active_schemas, ctx)`; fold via
   `capability_findings_from_audit(...)` into `list[CapabilityFinding]`.
7. Drift, against `intended = set(resolution.tool_names)`:
   - `sorted(intended - active_names)` → `CapabilityFinding("intended_not_active",
     tool=name, "warning", …)`;
   - `sorted(active_names - intended)` → `CapabilityFinding("active_not_intended",
     tool=name, "warning", …)`.
8. `registry_findings = tuple(sorted(group_failures + folded_audit + drift,
   key=lambda f: (f.tool, f.code, f.severity)))` (same sort key as LM2A's
   `_sorted_findings`).
9. Return `ProfileReconciliation(profile_name=definition.name,
   intended_names=resolution.tool_names, active_names=tuple(sorted(active_names)),
   registry_findings=…, profile_findings=resolution.findings)`.

`resolution.tool_names` is already a sorted tuple from `resolve_profile`, so it
is reused directly for `intended_names`.

### Shared-helper promotions in `capability_inventory.py`

Two existing private utilities are promoted to public, shared between
`reconcile_active_schemas` and `reconcile_profile`, so the mapping logic lives in
one place as LM2 grows:

1. `_dispatch_context_from_sources` → public `dispatch_context_from_sources`.
   Rename the definition, update its two internal callers (`build_inventory`,
   `reconcile_active_schemas`), and drop the underscore name (no alias unless an
   existing caller needs it).
2. Extract the inline `DispatchabilityFinding` → `CapabilityFinding` mapping
   (currently inside `reconcile_active_schemas`, using the private
   `_DISPATCHABILITY_SEVERITY`) into a public helper:

   ```python
   def capability_findings_from_audit(
       audit_findings: Iterable[DispatchabilityFinding],
   ) -> list[CapabilityFinding]:
       ...
   ```

   It returns a `list` so callers combine/sort with their own findings.
   `_DISPATCHABILITY_SEVERITY` stays **private** in `capability_inventory.py`;
   only the mapping function is public. `reconcile_active_schemas` is refactored
   to call this helper (no behavior change — its existing tests stay green).

These promotions add shared surface infrastructure, not profile-level logic, so
they do not blur `capability_inventory.py`'s responsibility. `execution_profile.py`
remains untouched and import-light.

## Data Flow

```
collect_live_sources ─► build_inventory ─► resolve_profile ─► reconcile_profile ─► ProfileReconciliation
                              (LM2A)            (LM2B)              (LM2D, new)
                                                                       │
                          disposable ToolRegistry(tier0) + request_group(g)…  ─► active schemas
                          dispatch_context_from_sources ─► audit ─► capability_findings_from_audit
```

No new live collector. No PlanGraph. No registry-consults-profiles wiring.

## What LM2D Explicitly Does NOT Do

- No surface compiler; no runtime policy; registry does not consult profiles.
- No mutation of shared/runtime `ToolRegistry` state (disposable instance only).
- No `planner` / `external_mcp` profile semantics; no PlanGraph integration.
- No runtime-visibility or MCP wire-shape change.
- No live smoke this slice. (Noted for after LM2D/LM2E: a Surface Smoke plus the
  GH C# repair canary across RookChat and at least one external MCP client.)
- No `format_reconciliation_report` — deferred until an actual consumer/CLI slice
  needs it. The seam is proven by the report object and tests alone.
- `ProfileFinding`s are carried, never reinterpreted or folded.

## Error / Edge Handling

- **MCP-only group in `definition.groups`:** `request_group` rejects →
  `group_activation_failed` (warning, registry reason in message). No exception.
- **Unknown group (absent from live `TOOL_GROUPS`/catalog):** same code, registry
  reason in message.
- **`initial_tier is None`:** empty tier-0; active surface comes from groups only.
- **Malformed/unknown `initial_tier` string:** `getattr(..., frozenset())`
  default → empty tier-0; the profile's `unknown_tier` is already in
  `resolution.findings`. Reconciliation never crashes on an already-diagnosed
  profile.
- **Meta tools** (`request_tools` / `search_tools`) active via tier-0 classify as
  `chatrunner_intercepted` → never a false `not_dispatchable`.

## Testing

New `mcp_server/tests/test_profile_reconciliation.py`, deterministic with canned
catalogs / injected sources (no live catalog, no MCP):

1. **Clean profile:** tier + groups all activate; intended == active; no
   dispatchability problems → `registry_findings == ()`; `profile_findings`
   carried.
2. **`intended_not_active`:** profile intends a name the registry does not
   activate (catalog gap or group not in live `TOOL_GROUPS`) → warning finding.
3. **`active_not_intended`:** registry activates a live-`TOOL_GROUPS` member
   absent from the intended set (the documented seam) → warning finding.
4. **`group_activation_failed` (MCP-only):** `definition.groups` includes an
   MCP-only group → rejected → finding with the registry reason in the message;
   no crash; `tool` == group name.
5. **`group_activation_failed` (unknown):** `definition.groups` includes a group
   absent from live `TOOL_GROUPS` → rejected → finding.
6. **Folded dispatchability:** an active tool with no dispatch path →
   `not_dispatchable` (error) appears in `registry_findings`.
7. **`profile_findings` carried verbatim:** a resolution carrying findings →
   identical tuple in the report, not folded into `registry_findings`.
8. **Determinism:** `registry_findings` sorted by `(tool, code, severity)`;
   `intended_names` / `active_names` are sorted tuples.
9. **`initial_tier=None` edge:** `ToolRegistry(tier0=set())`; no crash; active
   surface from groups only.
10. **Malformed tier edge:** a `ProfileResolution` whose `profile.initial_tier`
    is an unknown string → empty tier-0, no crash; reconciliation still produces
    a report.

Updates to `mcp_server/tests/test_capability_inventory.py`:

- Rename usages of `_dispatch_context_from_sources` → `dispatch_context_from_sources`
  (import + `test_dispatch_context_maps_all_six_fields`).
- Add a focused test for `capability_findings_from_audit(...)`: a list of
  `DispatchabilityFinding`s maps to `CapabilityFinding`s with the expected
  codes/severities (`not_dispatchable`/`missing_function_name`/
  `strict_no_arg_schema_drift` = error, `duplicate_visible_name` = warning).
- Existing `reconcile_active_schemas` tests remain unchanged and green (proves
  the refactor is behavior-preserving).

## Invariants (do not violate)

- Read-only / diagnostic; no shared/runtime `ToolRegistry` mutation (disposable
  instance only).
- `reconcile_profile` re-derives no profile facts from `sources` — intended names
  come only from `resolution.tool_names`; `sources` supplies tier members and the
  `DispatchContext` only.
- `resolve_profile` and `reconcile_active_schemas` keep their observable
  behavior; `reconcile_active_schemas` is only refactored onto the shared
  helpers.
- `execution_profile.py` stays import-light and untouched; `capability_record.py`
  stays stdlib-only and untouched.
- `_DISPATCHABILITY_SEVERITY` stays private; only `dispatch_context_from_sources`
  and `capability_findings_from_audit` become public.
- All tuple/list finding outputs deterministically sorted; `ProfileFinding`s
  carried verbatim.

## File Touch List

- Create: `mcp_server/src/rook/agent/profile_reconciliation.py`
- Modify: `mcp_server/src/rook/agent/capability_inventory.py` — rename
  `_dispatch_context_from_sources` → public; extract public
  `capability_findings_from_audit`; refactor `reconcile_active_schemas` to use
  both.
- Create: `mcp_server/tests/test_profile_reconciliation.py`
- Modify: `mcp_server/tests/test_capability_inventory.py` — rename usage; add
  `capability_findings_from_audit` test.
