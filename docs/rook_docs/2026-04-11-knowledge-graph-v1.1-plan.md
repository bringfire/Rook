# Knowledge Graph Visualizer v1.1 — Phased Implementation Plan

**Date:** 2026-04-11  
**Status:** Implementation plan (pending Codex review)  
**Design:** `2026-04-11-knowledge-graph-v1.1-design.md`  
**Builds on:** `76af230 fix(knowledge): set WebView directly as panel content`

---

## 1. Delivery Strategy

Three enhancements in dependency order. Each phase is independently
testable and deployable. The backend change (Phase 2) is the only
cross-boundary modification.

---

## 2. Phase Overview

| Phase | Name | Changes | Risk |
|-------|------|---------|------|
| 0 | Toolbar restructure | HTML + CSS | Low |
| 1 | Hover tooltips | JS + CSS | Low |
| 2 | Category spotlight | JS + CSS | Low |
| 3 | `similar_to` exporter + toggle | Python + JS + tests | Medium |
| 4 | Validation | Tests + manual Rhino check | Low |

---

## 3. Phase 0: Toolbar Restructure

### Scope

Add visual grouping to the toolbar before adding new controls to it.

### Files modified

- `src/Rook/UI/Knowledge/Resources/knowledge-graph.html`
- `src/Rook/UI/Knowledge/Resources/knowledge-graph.css`

### Tasks

1. Wrap existing toolbar controls in two groups:
   - `.toolbar-filters` (search, type, category)
   - `.toolbar-actions` (fit, reset)
2. Add subtle separator between groups (border or spacing)
3. Add placeholder for the "Similar" toggle button (Phase 2 wires it)

### Exit criteria

- Toolbar renders with visible grouping
- Existing filter/button behavior unchanged

---

## 4. Phase 1: Hover Tooltips

### Scope

Floating information card on node hover.

### Files modified

- `src/Rook/UI/Knowledge/Resources/knowledge-graph.js`
- `src/Rook/UI/Knowledge/Resources/knowledge-graph.css`
- `src/Rook/UI/Knowledge/Resources/knowledge-graph.html` (tooltip container div)

### Tasks

1. Add a `<div id="tooltip" class="hidden">` to the HTML body
2. Style the tooltip:
   - Dark card matching sidebar aesthetic (`--bg-tertiary` background)
   - Subtle border, small padding, max-width ~280px
   - `pointer-events: none` and `position: fixed`
   - `z-index` above the graph but below any modal
3. Add tooltip rendering function:
   - Takes a cytoscape node, extracts `label`, `noteType`, `category`,
     `inDegree`, `outDegree`, `brief`
   - Renders type badge (colored dot or small span), degree as "X in / Y out"
   - Truncates `brief` to ~80 chars on word boundary
4. Wire cytoscape events:
   - `mouseover` on node: show tooltip, position near cursor
   - `mousemove` on node: update tooltip position with fixed offset
   - `mouseout` on node: hide tooltip
   - Suppress tooltip when `selectedNodeId` is set (sidebar is open)
5. Viewport clamping:
   - Before positioning, check if tooltip would overflow right or bottom edge
   - If so, flip offset to keep tooltip inside the viewport

### Exit criteria

- Hovering a node shows the tooltip with correct data
- Moving the cursor updates position smoothly
- Tooltip disappears on mouseout
- Tooltip does not appear when sidebar is open for the hovered node
- Tooltip does not spill off screen edges

---

## 5. Phase 2: Category Spotlight

### Scope

Enhanced visual treatment when category dropdown is active.

### Files modified

- `src/Rook/UI/Knowledge/Resources/knowledge-graph.js`
- `src/Rook/UI/Knowledge/Resources/knowledge-graph.css`

### Tasks

1. Add `category-spotlight` cytoscape style selector:
   - Thicker border (2-3px)
   - Border color matches node type color
   - Higher border opacity
   - Label: fully opaque, slightly larger font, bold
2. Add `category-dimmed` style for non-matching nodes when category is active:
   - Opacity 0.1 (slightly lower than generic dimmed)
   - Label: `visibility: 'hidden'` (completely hidden, not just faded)
3. In `recomputeVisibility()`:
   - Detect when category filter is the active constraint
   - Apply `category-spotlight` instead of generic `highlighted` to matching
     nodes
   - Apply `category-dimmed` instead of generic `dimmed` to non-matching nodes
   - When category filter is cleared, remove both classes
4. Implement `updateStatusBar()` — unified status bar function:
   - `status-counts`: `{nodeCount} nodes, {edgeCount} edges`
     (later extended with `+ {similarCount} similar` in Phase 3)
   - `status-text` priority: category > search > neighborhood > default
   - If category active: `Showing {N} nodes in '{category}'`
   - If search active: `{N} matches`
   - If neighborhood focus: `Neighborhood of '{label}'`
   - Default: `Ready`
   - All status updates call `updateStatusBar()` instead of writing DOM directly
5. Ensure `category-spotlight` does NOT activate during:
   - Search-only filtering
   - Type-only filtering
   - Neighborhood focus
   - Combined filters where category is not one of the constraints

### Exit criteria

- Category selection produces a visually distinct spotlight effect
- Clearing the category filter returns to normal appearance
- Search and type filter do not trigger the spotlight
- Non-matching labels are fully hidden when category is active
- Status bar composes correctly from all active state

---

## 6. Phase 3: `similar_to` Edge Toggle

### Scope

Backend: add `similarEdges` to the graph payload.
Frontend: toggle button that lazily adds/removes similarity edges.

### New files

None.

### Files modified

- `mcp_server/src/rook/agent/chat/knowledge_graph_export.py`
- `mcp_server/tests/test_chat_server.py`
- `src/Rook/UI/Knowledge/Resources/knowledge-graph.html` (toggle button)
- `src/Rook/UI/Knowledge/Resources/knowledge-graph.js`
- `src/Rook/UI/Knowledge/Resources/knowledge-graph.css` (toggle button style)

### Backend tasks

1. In `build_knowledge_graph_payload()`:
   - **Build a GUID→note_id map first.** `similar_to` stores component
     GUIDs, not note IDs. Iterate active component notes and build
     `guid_to_note_id = {note.type_data["guid"]: note.note_id}` for
     all active components that have a GUID.
   - After building normal edges, iterate active component notes
   - For each note with `type_data.similar_to`, resolve each GUID to a
     note_id using the map. Skip GUIDs that don't resolve (component
     not in active set or not in store).
   - Filter: both notes must be active (not deprecated, not missing)
   - Deduplicate: for each pair, sort note IDs alphabetically, use
     `similar:{id_a}|{id_b}` as the edge ID
   - Track pairs in a set to avoid duplicates
   - Build `similarEdges` array with `{id, source, target, linkType: "similar"}`
   - Add `meta.similarEdgeCount` to the metadata
2. Add tests:
   - `test_knowledge_graph_similar_edges_present` — payload has `similarEdges` array
   - `test_knowledge_graph_similar_edges_deduped` — no duplicate pairs
   - `test_knowledge_graph_similar_edges_skip_deprecated` — deprecated notes excluded
   - `test_knowledge_graph_similar_edge_count_in_meta` — `meta.similarEdgeCount` matches array length

### Frontend tasks

3. **Fix base edge construction to include `linkType`.** The existing
   `renderGraph()` in `knowledge-graph.js` builds edge elements without
   preserving `linkType` from the payload. Add `linkType: e.linkType || 'related'`
   to the edge `data` object so that `connectedEdges('[linkType = "related"]')`
   works for neighborhood filtering. This is a prerequisite for the
   related-only neighborhood rule.
4. Store `similarEdges` from the graph payload in a JS variable (not in
   cytoscape instance)
5. Add "Similar" toggle button to the `.toolbar-actions` group
6. On toggle ON:
   - Build cytoscape edge elements from stored `similarEdges`
   - Add via `cy.batch()`
   - Set cytoscape style for `edge[linkType = "similar"]`:
     - `line-style: 'dashed'`
     - `line-color: '#a78bfa'`
     - `target-arrow-shape: 'none'`
     - `width: 0.8`
     - `opacity: 0.4`
     - `events: 'no'`
   - Call `updateStatusBar()` to append `+ {similarCount} similar`
   - Add `.active` class to toggle button
7. On toggle OFF:
   - Remove `similar_to` edges via `cy.batch()`
   - Call `updateStatusBar()`
   - Remove `.active` class from toggle button
8. In `recomputeVisibility()`:
   - When similar edges are present, dim those whose endpoints are dimmed
   - Same logic as structural edges
9. In `focusNeighborhood()`:
   - Filter to structural edges only
   - Use `node.connectedEdges('[linkType = "related"]')` to collect the
     neighborhood nodes, then union with the focus node itself
   - This requires task 3 (base edge `linkType` preservation) to work
10. Backward compatibility:
    - If `similarEdges` or `meta.similarEdgeCount` are absent from the
      payload, default to `[]` and `0`
    - Toggle button still renders but shows "(0)" and does nothing

### Checkpoint

- Run Python tests: all pass including new similar-edge tests
- Deploy and test in Rhino: toggle adds/removes dashed purple edges
- Nodes do NOT move when toggling (no layout recompute)
- Neighborhood focus does NOT include similar neighbors

### Exit criteria

- Backend payload includes `similarEdges` and `meta.similarEdgeCount`
- Toggle adds/removes edges visually without layout disruption
- Edges respect filter/dimming state
- Tests cover dedup, deprecated filtering, and meta count

---

## 7. Phase 4: Validation + Polish

### Scope

Final verification pass.

### Tasks

1. Run `cd mcp_server && python -m pytest tests/test_chat_server.py -v`
   and verify all pass (includes existing tests + new similar-edge tests)
2. Build C# (net7.0 + net48), verify 0 errors
3. Deploy to Rhino and manually test:
   - Hover tooltip: appears, tracks cursor, shows correct data, disappears
   - Category spotlight: distinct glow, labels hidden for non-matching
   - Similar toggle: edges appear/disappear, purple dashed, no layout shift
   - All three working together: search + category + similar
   - Panel toggle (close + reopen): all state resets cleanly
4. Check browser console (if accessible) for CSP violations or resource errors
5. Verify no remote URLs introduced

### Exit criteria

- All tests pass
- All three enhancements work in Rhino
- No regressions to existing v1 behavior
- Clean for commit

---

## 8. PR Shape

Single PR for all three enhancements. They share modified files
(`knowledge-graph.js`, `knowledge-graph.css`) and are small enough to
review together. The only backend change is the `similarEdges` addition
to the exporter.

---

## 9. Risk Assessment

| Risk | Mitigation |
|------|------------|
| `similar_to` edges too dense visually | Low opacity (0.4), dashed, thin, off by default |
| Tooltip flicker on fast mouse movement | `pointer-events: none` + `mousemove` tracking |
| Category spotlight conflicts with other classes | Dedicated `category-spotlight` class, isolated in `recomputeVisibility` |
| `similar_to` toggle triggers layout recompute | Edges not in cytoscape until toggled, no layout call on add/remove |
| Backward-incompatible payload change | `similarEdges` and `similarEdgeCount` are additive, frontend defaults to empty |

---

## 10. Files Changed Summary

### Modified

| File | Phase | Change |
|------|-------|--------|
| `knowledge-graph.html` | 0, 1, 2 | Toolbar groups, tooltip div, similar toggle button |
| `knowledge-graph.css` | 0, 1, 2, 3 | Toolbar layout, tooltip card, toggle button, spotlight styles |
| `knowledge-graph.js` | 1, 2, 3 | Tooltip logic, similar edge management, category spotlight, neighborhood filter fix |
| `knowledge_graph_export.py` | 2 | `similarEdges` + `similarEdgeCount` in payload |
| `test_chat_server.py` | 2 | 4 new similar-edge tests |

### No new files
