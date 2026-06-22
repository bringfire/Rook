# #303 — Readonly Visible-But-Not-Dispatchable Remediation

**Date:** 2026-06-22
**Status:** Approved (design)
**Campaign:** Local/Internal Models roadmap (LM2 follow-on — surface cleanliness)
**Branch:** `codex/lm2-303-readonly-dispatch-remediation`
**Issue:** https://github.com/bringfire/Rook/issues/303

---

## Summary

The LM2 surface smoke reports `not_dispatchable: 4` on the readonly profile. These are
**genuine** visible-implies-dispatchable violations (true positives — the audit is working):
four tools are local-visible through a readonly-allowed group but have no agent-side
ToolDispatcher route. This slice remediates them by **fixing the dispatch reality**, not the
audit. It is a route-table + group-membership correction; no new architecture.

Per-tool remediation (classification confirmed against code evidence):

| tool | server handler | remediation |
|---|---|---|
| `scene_query` | `call_rhino("/scene/graph/query","POST")` | **add bridge route** |
| `scene_classify` | `call_rhino("/scene/graph/classify","POST")` | **add bridge route** |
| `scene_overlay` | `call_rhino("/scene/graph/overlay","POST")` | **add bridge route** |
| `gh_canvas_image` | `call_rhino("/gh/canvas/image","GET")` | **remove from `gh_canvas_readonly`** |

## Why these classifications

### Scene trio → add bridge routes (the dispatch path is intended; the table missed it)

- The `scene_graph` group is explicitly documented as agent-bridge-accessible:
  `tool_groups.py` — *"Agents access these via the Rhino HTTP bridge (`/scene/graph/*`)."*
- The three handlers in `server._call_tool_dispatch` are pure `call_rhino` calls to
  `/scene/graph/query|classify|overlay` — endpoints that already exist and work for MCP
  clients. An agent-side `BRIDGE_ROUTES` entry routes to the *same* endpoint, so no
  Rhino-native / C# change is needed.
- Their sibling tools are already covered (4 registered as local tools:
  `scene_exact_neighbors`, `scene_refine_containment`,
  `scene_project_bim_relationships`, `scene_bim_facts`; 3 deliberately parked in
  `LOCAL_TIER_0_DISPATCH_EXCLUSIONS`: `scene_graph`, `scene_context`, `scene_stats`).
  The trio is the only scene subset that is *neither* routed *nor* parked — an incomplete
  route table, not a deliberate exclusion.
- Parking the trio in the exclusions list would be the wrong call: exclusions mean "valid
  MCP tool, not intended for local dispatch yet." Here the intent (group comment) and the
  mechanism (pure bridge handlers) both point to local bridge access. Routing is the
  faithful fix.

### `gh_canvas_image` → remove from `gh_canvas_readonly` (exposure was mislabeled)

- The authoritative read-write `gh_canvas` group comment in `tool_groups.py` states:
  *"gh_canvas_focus, gh_canvas_zoom, gh_canvas_image … are MCP/server-side tools today.
  Do not expose them to local RookChat execution profiles until ToolDispatcher paths
  exist."* The read-write group deliberately omits it; its presence in `gh_canvas_readonly`
  contradicts that intent.
- It returns a canvas **PNG**, which the local text/JSON agent surface cannot consume (no
  agent-side equivalent of the MCP `Read` tool). Adding a dispatcher path would expose a
  tool an agent cannot use.
- Removing it from `gh_canvas_readonly` aligns readonly with the read-write group's
  deliberate omission. It remains advertised over MCP (`list_tools`) for Claude Code /
  external clients, and LM2G's `external_mcp` audit still correctly sees it as
  advertised-with-handler. This is correcting a mislabeled exposure, not changing inventory
  semantics.

## Changes

### 1. `mcp_server/src/rook/agent/tool_dispatcher.py` — add three bridge routes

Add a Scene Graph section to `BRIDGE_ROUTES` (matching the existing `"name": ("/endpoint",
"METHOD"),` style):

```python
    # --- Scene Graph (agent bridge access; mirrors server._call_tool_dispatch) ---
    "scene_query":    ("/scene/graph/query", "POST"),
    "scene_classify": ("/scene/graph/classify", "POST"),
    "scene_overlay":  ("/scene/graph/overlay", "POST"),
```

Endpoints/methods are copied verbatim from the server handlers so the agent path and the
MCP path hit the identical Rhino route. No other dispatcher change.

### 2. `mcp_server/src/rook/agent/tool_groups.py` — drop `gh_canvas_image` from the readonly group

Remove the `"gh_canvas_image",` line from the `gh_canvas_readonly` group list and leave a
one-line comment recording why (MCP-only; returns a PNG; no agent dispatch path; consistent
with the read-write `gh_canvas` group's deliberate omission; #303).

## Out of scope / guardrails (do NOT do)

- No audit / reporting changes (no severity edits, no hiding tools).
- No `CapabilityInventory` / `capability_record` / `execution_profile` /
  `profile_reconciliation` changes.
- No MCP wire changes (`server.list_tools` / `_call_tool_dispatch` untouched).
- No bridge route or local handler for `gh_canvas_image`.
- Do not touch the `scene_graph` / `scene_context` / `scene_stats` entries in
  `LOCAL_TIER_0_DISPATCH_EXCLUSIONS`.
- Do not touch `external_mcp` (LM2G) anything.
- Keep the change to `tool_groups.py`, `tool_dispatcher.py`, and focused tests.

## Testing

- **`mcp_server/tests/test_dispatcher_safety.py`** (or a focused new test module mirroring
  `test_display_modes.py`'s `BRIDGE_ROUTES` coverage idiom): assert each of `scene_query`,
  `scene_classify`, `scene_overlay` is in `BRIDGE_ROUTES` with the exact endpoint + method
  above.
- **Classification regression (deterministic, no live runtime):** build a `DispatchContext`
  from `collect_live_sources()` and assert `classify_visible_tool` returns `bridge_route`
  for each scene-trio tool (was `failure`). `collect_live_sources` populates `bridge_names`
  from `BRIDGE_ROUTES.keys()`, so this is deterministic.
- **`mcp_server/tests/test_phase5b_readonly_enforcement.py::test_has_inspection_tools`**:
  update — drop `gh_canvas_image` from the expected-present tuple (leave `gh_snapshot`,
  `gh_inspect_output`) and add a positive assertion that `gh_canvas_image` is **NOT** in
  `TOOL_GROUPS["gh_canvas_readonly"]`, with a comment citing the MCP-only rationale + #303.
- **No-regression for the readonly surface (deterministic):** assert `gh_canvas_image` is
  not in any `READONLY_ALLOWED_GROUPS` group's member list (so it cannot re-enter the
  readonly profile's intended set).

## Verification (post-merge)

Re-mirror current `main` into the deployed venv (#300 stopgap), then run the deployed
smoke `surface` (deployed interpreter, empty `PYTHONPATH`). Expected: the readonly
profile `not_dispatchable` residue goes **4 → 0**. `coherence` and `external` remain PASS;
`external` should be unaffected (`gh_canvas_image` is still advertised-with-handler;
`advertised_not_dispatchable: 0` unchanged).

## File Touch List

- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py` — 3 `BRIDGE_ROUTES` entries.
- Modify: `mcp_server/src/rook/agent/tool_groups.py` — remove `gh_canvas_image` from
  `gh_canvas_readonly` (+ comment).
- Modify: `mcp_server/tests/test_phase5b_readonly_enforcement.py` — update
  `test_has_inspection_tools`.
- Add/modify tests: scene-trio `BRIDGE_ROUTES` coverage + classify-as-bridge_route
  regression + `gh_canvas_image` not-in-readonly-groups assertion (in
  `test_dispatcher_safety.py` and/or a focused module).
