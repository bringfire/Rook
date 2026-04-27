# Intent Runtime — Substrate Coverage Followups

**Date opened:** 2026-04-14
**Trigger:** PR #18 (CapabilityRouter coverage for batch tools + paired singles)
**Audience:** future maintainers picking up substrate-coverage work

This file captures items deferred during the intent-runtime substrate-coverage
track so they don't get lost. Add new items with `## YYYY-MM-DD: <name>` and
keep them sorted by severity within sections.

---

## Open — architectural

### XOR payload shape support in `RouteSpec`
**Severity:** Medium
**Discovered:** PR #18 Codex review round 1
**Context:** `CapabilityRouter.validate_params()` only checks `required_params`.
For handlers that accept "field A XOR field B" (e.g. `set_block_materials`
accepts `material` OR `mappings`), there's no way to express that in
`RouteSpec`. PR #18 worked around it by exposing only the bulk path and
dropping per-index `mappings` from router coverage.

**Proposed fix:** add `requires_one_of: tuple[tuple[str, ...], ...]` to
`RouteSpec`; update `validate_params()` to check that at least one of each
inner tuple's keys is present. Keep `required_params` for hard requirements.

**Why deferred:** Router-model architectural change deserves its own design
pass and PR. Bugfix-sized fix isn't sufficient.

**Trigger to revisit:** another XOR shape lands, or the per-index `mappings`
path becomes a real `/intent` use case.

**Affected routes if adopted:**
- `set_block_materials` — `name` + (`material` XOR `mappings`)
- `set_block_object_colors` — `name` + (`color` XOR `mappings`)
- `set_block_object_user_strings` — `name` + (`userStrings` XOR `mappings`)
- `set_block_instance_visibility` — bulk `ids` shape (single-`id` shape currently routed)
- `block_array_instances` — linear (`direction`+`basePoint`) XOR circular (`center`+`radius`+`startAngle`+`endAngle`)
- `block_rebase` — `anchor` XOR `targetPoint` plus `dryRun` mode toggle
- `block_rebase_recursive` — same as `block_rebase`
- `block_set_instance_properties` — `id` XOR `ids` + "at least one property to set"
- `block_user_strings` — `action: get/set/delete` mode XOR with mode-specific required fields

The first 4 entries above (`set_block_materials`/`_object_colors`/`_object_user_strings` mappings shape, `set_block_instance_visibility` bulk shape) reach the document via partial coverage already (one shape exposed, the other parked); the next 5 entries are entirely deferred from `CapabilityRouter` until this lands.

---

## Open — coverage gaps (deferred during PR #18)

### Per-index `mappings` payload reachability for block property mutations
**Severity:** Low
**Status:** Router-unreachable; remains MCP-direct callable
**Routes:** `set_block_materials`, `set_block_object_colors`,
`set_block_object_user_strings` (per-index `mappings` shape)
**Why deferred:** No clear natural-language path to per-index per-object
property assignment. The XOR fix above would make these reachable; until
then, this is intentional scope.

### Layer read/query intent reachability
**Severity:** Low
**Routes not in `CapabilityRouter`:** `rename_layer`, `move_layer_objects`,
`merge_layers`, `layer_dependencies`
**Why deferred:** PR #18 scoped to mutation reachability for recently shipped
batch tools + singles. Read/query is a separate concern.

### Historical block tools without `RouteSpec`
**Severity:** Medium
**Routes not in `CapabilityRouter`:** `block_array_instances`, `block_purge`,
`block_rebase`, `block_rebase_recursive`, `block_replace_geometry`,
`block_replace_object_geometry`, `block_transform_object`,
`block_set_instance_properties`, `block_set_instance_visibility`,
`block_replace_instance`, `block_reset_scale`, `block_link`, `block_unlink`,
`block_refresh`, `block_user_strings`, `block_find_instances`,
`block_objects_detailed`
**Why deferred:** These pre-date the batch work; expanding coverage to all
historical block tools is a substrate-coverage PR, not a hygiene fix.
**Suggested approach:** one PR per family (instance ops; replace/rebase;
read/query; metadata).

---

## Open — parallel substrate surfaces (post-PR #18)

The intent-runtime substrate has two parallel surfaces still missing the
PR #18 ops:

### `mcp_server/src/rook/explorer/registry.py`
**Severity:** Medium → resolved via PR #19 for the immediate 14-tool gap.
**Status:** PR #19 (2026-04-14) categorized 14 block + layer mutation tools
in `TOOL_CATEGORIES`. A separate metadata-cleanup item remains — see below.
**Suggested approach:** add a follow-up sweep for the historical block tools
listed above (separate sub-item, not yet in flight).

### explorer registry metadata cleanup (`HTTP_MAPPINGS` staleness)
**Severity:** Low-Medium
**Discovered:** PR #19 audit (2026-04-14)
**Context:** `explorer/registry.py` has a parallel `HTTP_MAPPINGS` dict
alongside `TOOL_CATEGORIES`. Existing entries use stale endpoint paths
(e.g. `"rhino_layer_create": ("/layer/create", "POST")` while the actual
server route is `/layers`). The map covers only ~10 of ~250 tools and is
not consumed for runtime routing — server.py calls `call_rhino()` directly
with its own endpoints. `HTTP_MAPPINGS` is loose metadata only, populated
into `ToolDefinition.http_endpoint` for display/debug purposes.

**Why deferred:** Adding correct entries beside stale ones would create
worse confusion than leaving the gap. Reconciling against canonical
tool/route definitions is its own substrate cleanup.

**Trigger to revisit:** when doing the broader `explorer/registry.py`
sweep, OR if explorer starts consuming `http_endpoint` for execution/
planning rather than display/debug metadata.

**Suggested approach:**
- Identify canonical source of truth for tool→endpoint mappings (likely
  `mcp_server/src/rook/agent/tool_dispatcher.py`'s `ROUTE_TABLE` after
  PR #16, which already has parity discipline applied)
- Either: (a) replace `HTTP_MAPPINGS` with a live derivation from the
  canonical source, or (b) bulk-update the existing stale entries +
  backfill missing ones from the canonical source.
- Verify nothing else depends on the current incorrect endpoints.

### `mcp_server/src/rook/bootstrap/test_matrix.py`
**Severity:** Lower
**Status:** Knowledge-graph bootstrap doesn't exercise the batch tools.
**Suggested approach:** add representative test cases after intent routing
and explorer classification stabilize. Don't front-load while semantics may
still move.

---

## Resolved

(items move here once they ship; cite the PR that closed them)
