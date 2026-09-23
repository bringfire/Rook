# Knowledge Graph Visualizer v1.1 — Enhancement Design

**Date:** 2026-04-11  
**Status:** Approved design  
**Authors:** Claude + Bringfire + Codex  
**Builds on:** `d9f7aa8 feat(knowledge): add Knowledge Graph visualizer panel (#5)`  
**Contract:** `2026-04-10-webui-substrate-contract.md`

---

## 1. Purpose

Enhance the shipped Knowledge Graph panel from a basic graph browser into
an information-rich visualization tool. The graph is the primary interface
to the knowledge store for most users — they will never read raw files.

v1.1 focuses on **interpretive enhancements** (better ways to read the
graph), not operational features (editing, writing back to the store).

---

## 2. Scope: Three Enhancements

### 2.1 Hover Tooltips

Show a floating information card when hovering over a node. Provides enough
context to decide whether to click for the full sidebar detail.

**Content:** Name, type badge (colored), category, degree (X in / Y out),
first ~80 characters of brief (truncated on word boundary).

**Behavior:**
- Track cursor position via `mouseover` + `mousemove` + `mouseout`
- `pointer-events: none` on the tooltip div to prevent flicker
- Fixed cursor offset, clamped inside viewport (no spill off edges)
- Suppressed when a node is selected (sidebar is already showing detail)
- No delay or animation — appears immediately, disappears immediately

**Data source:** All fields already present in cytoscape node data. Zero
backend changes.

**Example layout:**
```
+---------------------------------+
| * Sphere            component   |
| Primitives           4 in / 9 out|
| Creates a sphere from center... |
+---------------------------------+
```

### 2.2 Enhanced Category Highlighting (Category Spotlight)

When the category dropdown filter is active, matching nodes get a distinct
"spotlight" treatment instead of just being "not dimmed."

**Visual treatment for matching nodes:**
- Brighter border via cytoscape style properties (not CSS box-shadow)
- Type-colored glow effect (border-color matches note type)
- Label fully opaque, slightly larger
- Uses a dedicated `category-spotlight` cytoscape class, NOT the generic
  `highlighted` class (prevents search/focus from picking up the glow)

**Visual treatment for non-matching nodes:**
- Current dimming stays (opacity 0.15)
- Labels hidden entirely (not just faded) to reduce noise

**Status bar update:** "Showing 41 nodes in 'curves'"

**No backend changes.** Pure cytoscape style + class refinement.

### 2.3 `similar_to` Edge Toggle

Add a second edge type showing conceptual similarity between components.
880 components have `similar_to` lists, yielding ~533 unique undirected pairs.

**Backend change (exporter):**
- Add `similarEdges` array to the graph payload (separate from `edges`)
- Add `meta.similarEdgeCount` to the metadata
- Edges are undirected and deduped: if A has B in `similar_to` and B has A,
  emit one edge with alphabetically sorted id
- Edge id format: `similar:comp_aaa|comp_bbb`
- Apply same filtering rules as normal edges: drop pairs where either note
  is missing or deprecated
- Component-only: `similar_to` only exists on component notes

**Frontend behavior:**
- `similarEdges` stored in JS state but NOT added to cytoscape instance on
  initial render (preserves layout stability — hidden edges still influence
  force calculations)
- Toggle button "Similar" in toolbar activates/deactivates
- On toggle ON: add edges to cytoscape via `cy.batch()` — nodes stay in
  place, edges appear between existing positions
- On toggle OFF: remove edges via `cy.batch()`
- Edges are non-selectable (`events: 'no'`) and non-arrowed (undirected)

**Visual style:**
- Dashed line (`line-style: 'dashed'`)
- Muted purple (`#a78bfa`)
- Slightly thinner than structural edges
- No arrowheads

**Interaction with filters:**
- `similar_to` edges respect `recomputeVisibility()` — if either endpoint
  is dimmed, the edge is dimmed
- Neighborhood focus (`closedNeighborhood()`) filters to `linkType ===
  "related"` only — similar neighbors are NOT pulled into focus
- Node degree (tooltip + node sizing) reflects structural links only

**Status bar:** `1,211 nodes, 9,128 edges + 533 similar` (when toggled on)

**Backward compatibility:** Frontend treats `similarEdges` and
`meta.similarEdgeCount` as optional with safe defaults (`[]` and `0`).

---

## 3. Data Contract Change

`GET /knowledge/graph` response gains two fields:

```json
{
  "meta": {
    "generatedAt": "...",
    "source": "UnifiedStore",
    "noteCount": 1211,
    "edgeCount": 9128,
    "excludedDeprecatedCount": 18,
    "excludedDanglingEdgeCount": 0,
    "similarEdgeCount": 533
  },
  "nodes": [ ... ],
  "edges": [ ... ],
  "similarEdges": [
    {
      "id": "similar:comp_aaa|comp_bbb",
      "source": "comp_aaa",
      "target": "comp_bbb",
      "linkType": "similar"
    }
  ]
}
```

Existing `nodes`, `edges`, and `meta` fields are unchanged.

---

## 4. Toolbar Layout

```
[Search...............] [Type v] [Category v]  |  [Similar] [Fit] [Reset]
 <- filtering zone ->                            <- view actions zone ->
```

Visual separator (subtle border or spacing) between filtering controls and
view action controls. Single row, no wrapping.

---

## 5. Design Principles

- **Default state is clean:** `similar_to` edges off, tooltips only on
  hover, no spotlight until a category is selected.
- **Each enhancement answers a specific question:**
  - Tooltips: "What is this node?"
  - Category spotlight: "Where does this topic cluster?"
  - `similar_to` edges: "What else is conceptually like this?"
- **Information-rich but legible:** Dense data presentation, but every
  element must be readable and actually informative.
- **No layout disruption:** Adding/removing `similar_to` edges does not
  trigger layout recomputation.

---

## 6. Sequencing

1. **Hover tooltips** — zero backend changes, lowest risk, immediate UX win
2. **Category spotlight** — zero backend changes, CSS/style refinement only
3. **`similar_to` edge toggle** — exporter change + frontend toggle, highest
   complexity

---

## 7. Deferred to v1.2+

- Provenance (`created_from`) coloring — 71% of notes are `expansion`,
  limited visual value
- Graph analytics (hubs, bridges, orphans, gap detection)
- Trigger intent search
- Schema visualization
- Operational/editor features (tag editing, link management, deprecation)
- Teaching path / sequence view
- `similar_to` influencing layout (would require layout recompute UX)
- Usage/retrieval heat map (data too sparse currently)
