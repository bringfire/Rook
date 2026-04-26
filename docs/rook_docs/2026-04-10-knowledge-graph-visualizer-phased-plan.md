# Knowledge Graph Visualizer Phased Implementation Plan

**Date:** 2026-04-10  
**Status:** Execution plan  
**Authors:** Codex + aryan  
**Primary spec:** `C:\Users\aryan\source\repos\rook_docs\2026-04-10-knowledge-graph-visualizer-spec.md`

---

## 1. Goal

Implement the first Phase 2 WebUI module: a dockable `Knowledge Graph` panel backed by the hardened WebUI trust model and the existing Python chat server.

This plan is intentionally phased so the highest-risk architecture work lands before the graph-specific UI work.

---

## 2. Delivery Strategy

Build in this order:

1. stabilize the reusable substrate
2. define and test the backend graph contract
3. stand up the Rhino panel shell
4. add graph interactions
5. harden and verify

The graph panel should be the **first consumer** of the substrate, not a one-off that gets generalized later.

---

## 3. Phase Overview

| Phase | Name | Purpose | Output |
|------|------|---------|--------|
| 0 | Prep + schema validation | Confirm real `UnifiedStore` shapes against the spec | validated payload examples, vendored JS ready |
| 1 | Substrate extraction | Create `RookWebSurface` and decouple `ChatTab` | reusable hardened WebView host |
| 2 | Backend graph API | Implement exporter and routes | `/knowledge/graph`, `/knowledge/note/{id}` |
| 3 | Rhino panel shell | Register and open the new panel | empty graph panel loading its own page |
| 4 | Frontend graph UX | Render, search, inspect, filter, focus | usable Cytoscape graph explorer |
| 5 | Validation + polish | Test, harden, and document gaps | shippable v1 module |

---

## 4. Phase 0: Prep + Schema Validation

### Scope

- vendor `cytoscape.min.js`
- vendor `cytoscape-fcose.min.js`
- inspect representative `UnifiedStore` notes for each `note_type`
- confirm category, tags, components, `type_data.guid`, and link shape
- produce 2-3 real sample payloads matching the spec

### Files expected

- `src/Rook/UI/Knowledge/Resources/vendor/cytoscape.min.js`
- `src/Rook/UI/Knowledge/Resources/vendor/cytoscape-fcose.min.js`

### Tasks

1. sample at least one note each for:
   - `component`
   - `recipe`
   - `struggle`
   - `teaching`
2. verify:
   - `links` are always note ids
   - `type_data.guid` is populated only where expected
   - `deprecated` filtering will not unexpectedly empty important graph regions
3. record any schema drift back into the spec before Phase 1 starts

### Exit criteria

- vendored JS files are present
- schema matches real notes
- no unresolved ambiguity remains around directionality or required fields

### Risk

Low. This is a fact-finding and asset-vendoring phase.

---

## 5. Phase 1: Substrate Extraction

### Scope

Extract a reusable hardened WebView host from `ChatTab` into `RookWebSurface`.

### New files

- `src/Rook/UI/Web/RookWebSurface.cs`

### Modified files

- `src/Rook/UI/Chat/ChatTab.cs`
- `src/Rook/Rook.csproj`

### Tasks

1. create `RookWebSurface` in `Rook.UI.Web`
2. move generic WebView and virtual-host logic out of `ChatTab`
3. parameterize resource lookup with `ResourceRoot`
4. preserve:
   - nonce injection
   - CSP behavior
   - in-memory resource serving
   - minimal HTML fallback
5. restructure `ChatTab` so it composes the shared Web surface into its own chat-specific layout
6. update csproj embedded-resource entries to:
   - `UI\Chat\Resources\**\*`
   - `UI\Knowledge\Resources\**\*`

### Checkpoint

Before moving on, existing chat tabs must still:

- load from `https://app.rook.invalid`
- show no resource 404s
- show no CSP regressions
- continue to function without any knowledge-graph code present

### Exit criteria

- `RookWebSurface` exists and is used by `ChatTab`
- resource lookup is no longer chat-hardcoded
- chat behavior is unchanged from a user perspective

### Risk

High. This is the architectural phase with the largest blast radius.

### Rollback strategy

If this phase destabilizes chat, stop here and repair the substrate before any graph work continues.

---

## 6. Phase 2: Backend Graph API

### Scope

Implement the graph exporter and the two knowledge routes on the existing chat server.

### New files

- `mcp_server/src/rook/agent/chat/knowledge_graph_export.py`

### Modified files

- `mcp_server/src/rook/agent/chat/server.py`
- `mcp_server/tests/test_chat_server.py`

### Tasks

1. implement:
   - `build_knowledge_graph_payload(store: UnifiedStore) -> dict`
   - `build_note_detail_payload(store: UnifiedStore, note_id: str) -> dict | None`
2. enforce export rules:
   - exclude deprecated notes
   - drop dangling edges
   - deduplicate edges
   - compute `inDegree`, `outDegree`, `degree`
3. map `UnifiedStore.get_related()` correctly:
   - `linksFrom` = forward links
   - `linksTo` = backlinks
4. add routes:
   - `GET /knowledge/graph`
   - `GET /knowledge/note/{note_id}`
5. tighten nonce exemption:
   - from suffix match to exact `/agent/chat/health`
6. add tests for route shape and auth behavior

### Checkpoint

Route work is complete before any Rhino panel exists when:

- both routes can be hit in tests
- both routes are protected by nonce middleware
- note detail directionality is correct

### Exit criteria

- backend contract matches the spec
- tests cover both new endpoints and the health exemption tightening

### Risk

Medium. The main risk is silent data-contract drift, not architecture.

---

## 7. Phase 3: Rhino Panel Shell

### Scope

Create the dockable Rhino panel and command without yet implementing the full graph UX.

### New files

- `src/Rook/UI/Knowledge/KnowledgeGraphPanel.cs`
- `src/Rook/Commands/ShowRookKnowledgeGraphCommand.cs`
- `src/Rook/UI/Knowledge/Resources/knowledge-graph.html`
- `src/Rook/UI/Knowledge/Resources/knowledge-graph.css`
- `src/Rook/UI/Knowledge/Resources/knowledge-graph.js`

### Modified files

- `src/Rook/RookPlugin.cs`

### Tasks

1. register `KnowledgeGraphPanel` in `RookPlugin.OnLoad(...)`
2. add `ShowRookKnowledgeGraph`
3. derive panel from `RookWebSurface`
4. in `PanelShown(...)`:
   - call `ChatServiceManager.Instance.EnsureStartedAsync()`
   - extract host and port from `ChatServiceHealth.BaseUri`
   - inject nonce + host + port before navigation
5. get the panel to load its own HTML/CSS/JS with no graph logic yet

### Checkpoint

This phase is done when the panel opens reliably and the page boots without:

- resource 404s
- nonce issues
- CSP violations

### Exit criteria

- Rhino panel exists
- command opens it
- page loads from embedded resources under the hardened host

### Risk

Medium. The likely failures are resource namespace mistakes and bootstrap injection mistakes.

---

## 8. Phase 4: Frontend Graph UX

### Scope

Implement the actual graph explorer behavior in the panel.

### Tasks

1. fetch `/knowledge/graph` on load
2. render Cytoscape with `fcose`
3. define node styling by `noteType`
4. implement toolbar controls:
   - search
   - note type filter
   - category filter
   - reset / fit
   - focus neighborhood
5. implement node click:
   - fetch `/knowledge/note/{id}`
   - populate sidebar
6. keep filtering client-side for v1

### UX rules

- initial load should render the whole graph
- search should not require roundtrips
- note detail should roundtrip for correctness and freshness
- graph operations should remain responsive on the current dataset

### Exit criteria

- graph renders
- node click works
- search/filter/focus all work
- sidebar shows full note detail

### Risk

Medium. Performance and usability tuning are the likely issues here.

---

## 9. Phase 5: Validation + Polish

### Scope

Finish the module to the point where it is safe to merge and practical to use.

### Tasks

1. run backend tests
2. manually validate in Rhino:
   - open panel
   - load graph
   - search
   - click note
   - filter
   - focus neighborhood
3. inspect browser console for:
   - CSP violations
   - failed resource loads
   - failed fetches
4. confirm no remote URLs are introduced
5. document any deferred issues separately rather than quietly expanding scope

### Exit criteria

- acceptance criteria in the spec are met
- no known blocking correctness or trust-model regressions remain

### Risk

Low to medium. This phase is mostly cleanup and confidence-building.

---

## 10. Recommended PR Shape

Do not land this as one giant change if it can be avoided.

Recommended sequence:

1. **PR A:** substrate extraction
2. **PR B:** backend exporter + routes + tests
3. **PR C:** knowledge graph panel shell + frontend UX

If repository pressure requires fewer PRs, merge B and C, but keep A separate. The substrate change is the one most worth reviewing in isolation.

---

## 11. Acceptance Gates by Phase

### Gate after Phase 1

- existing chat still works
- no trust-model regressions

### Gate after Phase 2

- graph contract is stable and tested

### Gate after Phase 3

- panel shell loads independently of chat tabs

### Gate after Phase 4

- graph is usable for inspection work

### Gate after Phase 5

- module is ready to merge

---

## 12. Known Deferrals

These are intentionally deferred beyond v1:

- live graph updates while learning runs
- saved layouts
- graph clustering
- cross-module deep links
- generic shared `GraphCanvas` capability
- promotion of common graph widgets into a shared capability layer

Do not absorb these into v1 unless one becomes necessary to solve a concrete failure.

---

## 13. Immediate Next Step

Start with **Phase 0** and **Phase 1** only.

The first implementation task should be:

1. vendor Cytoscape assets
2. sample real `UnifiedStore` notes
3. begin `RookWebSurface` extraction

That sequence keeps the architecture honest and prevents the graph panel from becoming the substrate by accident.
