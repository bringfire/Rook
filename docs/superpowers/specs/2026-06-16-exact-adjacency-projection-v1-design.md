# Exact Adjacency Projection v1 — design

> **Status (2026-06-16): DESIGN APPROVED (brainstorm complete) — ready for writing-plans.**
> Slice owner: spatial-intelligence track, branch `feature/spatial-intelligence`
> (worktree `C:/Users/aryan/source/repos/rook-spatial`; `main` untouched).
>
> This is the first **intelligence-layer** slice that consumes the production OCCT
> exact-adjacency engine. The engine (`docs/rook_docs/2026-06-14-occt-uniform-engine-decision.md`,
> route `POST /scene/graph/adjacency/exact`) produces the **edges**; this slice
> **projects** those edges into Rook's existing networkx scene-graph mirror as typed,
> IFC-aligned relationship edges. Design direction:
> `docs/rook_docs/2026-06-14-spatial-graph-projection-design.md` (this slice = §5 layer-2 /
> §8 step-1). Memory: `project_spatial_intelligence_topology`.

---

## 1. Problem & goal

`/scene/graph/adjacency/exact` is a **stable production edge source**: given an `objectId`
it runs its own bbox broad-phase, computes OCCT shared-face adjacency for each candidate,
and returns exact `adjacent_exact` edges with `sharedArea` / `facePairs` / `lengthUnit` /
`areaUnit` / `sourceCapability` / the full `candidates[]` set considered. It has **no Python
consumer today** — it is referenced only in C++, docs, and spike scripts.

The Python scene-graph mirror (`mcp_server/src/rook/scene/scene_graph.py`,
`SceneGraphAnalytics`) is a networkx `MultiDiGraph`, RookId-keyed, synced from C++ via
`/scene/graph` (full) + `/scene/graph/diff` (incremental, sequence-tracked). Its edges are
**bbox-approximate** (`contains`/`supports`/`adjacent`/`above`/`near`/`intersects`).

**Goal of v1:** make Python the first consumer of the exact route — project its
`adjacent_exact` edges into the mirror as typed, IFC-aligned (`IfcRelSpaceBoundary`)
relationship edges with properties; preserve and locally annotate the approximate bbox
edges; expose an `scene_exact_neighbors` query; teach the existing NL surface to render
exact edges. **Enrichment of an existing graph, not a greenfield build.**

### In scope
- A Python read-model projector over the existing native route (no C++ changes).
- `scene_exact_neighbors(object_ids=[...])` MCP tool — explicit object set primitive.
- Typed canonical `adjacent_exact` edges with full provenance, idempotently upserted.
- Projection-scoped reconciliation annotations on touched bbox `adjacent` edges.
- Sequence-keyed cache + active prune of projection artifacts on sequence advance.
- NL rendering of exact edges via the existing `get_context` surface.

### Out of scope (deferred to later slices)
- Containment refinement, hosting/apertures, circulation, zones, Spike F construction tier.
- Persistent native exact edges; native incremental invalidation.
- Internal neighborhood expansion / graph-walk; whole-model sweep (`project_exact_all`).
- Bounded-radius expansion.
- Any unit conversion.

---

## 2. Architecture & component placement

**The whole slice is a Python read-model layer over the existing native edge source. Zero
C++ changes.** The OCCT engine and `/scene/graph/adjacency/exact` are unchanged.

New isolated module **`mcp_server/src/rook/scene/exact_projection.py`** holding an
`ExactAdjacencyProjector` class that takes the `SceneGraphAnalytics` mirror as a
collaborator. (Rationale: `scene_graph.py` already does sync + analytics + NL; projection +
caching + reconciliation is a distinct job. A dedicated unit has one purpose, is testable in
isolation with a faked route, and keeps the seam clean. Alternatives — methods on
`SceneGraphAnalytics` (grows the god-object) or inline in the tool handler (untestable) —
rejected.)

```
scene/exact_projection.py
  class ExactAdjacencyProjector:
      def __init__(self, analytics: SceneGraphAnalytics)
      async def project(object_ids, *, candidate_scope, port) -> dict   # the tool payload
      # internals: _call_exact_route, _prepare_source_delta, _commit_source_delta,
      #            _purge_projection_artifacts, cache (graphSequence+sourceId+options+engineVersion)
  _instance singleton via get_exact_projector(analytics)
```

- The projector **reads and writes the mirror's `MultiDiGraph`** but owns no graph of its
  own — the mirror stays the single source of truth.
- Cache + projection-artifact bookkeeping live on the projector singleton.

### Tool registration scope (all four required)
Surfacing the tool reliably needs four coordinated edits, not just a dispatch case:
1. **Dispatch case** — `server.py` gains a `scene_exact_neighbors` case that syncs the mirror,
   constructs/reuses the projector, calls `project(...)`, returns the structured JSON.
2. **Tool schema** — register the `scene_exact_neighbors` `Tool(...)` in `list_tools` (next to
   the other `scene_*` tools, ~`server.py:11073`).
3. **Tool group** — add `"scene_exact_neighbors"` to the `scene_graph` group in
   `mcp_server/src/rook/agent/tool_groups.py:452`, so progressive tool disclosure surfaces it.
   Omitting this leaves the tool undiscoverable to agents.
4. **Agent-direct local handler** — register a `scene_exact_neighbors` handler in
   `mcp_server/src/rook/agent/tool_dispatcher.py::build_local_tools()`. `tool_dispatcher.py` has
   no `scene` references, so the existing `scene_context`/`scene_stats` are MCP-only; without a
   local handler a direct agent would *discover* `scene_exact_neighbors` via its group but fail
   to *execute* it ("unknown tool"). The handler calls `get_scene_graph()` + `get_exact_projector()`
   + `project(...)`. Required because the roadmap wants agent semantic reasoning over exact adjacency.

### Unit Contract Invariant (load-bearing)
> Exact projection preserves the native route's unit contract. `/scene/graph/adjacency/exact`
> returns `lengthUnit` + `areaUnit`; `scene_exact_neighbors` copies both onto the response
> and onto every projected edge. Python treats `sharedArea` as a numeric value *in* `areaUnit`
> — it does **not** assume mm/inches or perform any conversion in v1. `get_context` formats
> using the edge's own `areaUnit`, never a hardcoded unit. A unit / `graphSequence` mismatch
> is cache-invalidating.

---

## 3. Data model

### Projected exact edge — single canonical, idempotent-upserted
Stored as a `MultiDiGraph` edge with a **deterministic key**, oriented canonically so the
symmetric physical fact is one edge:

```python
canonical_src, canonical_tgt = sorted((id_a, id_b))   # min, max
graph.add_edge(canonical_src, canonical_tgt, key="occt:adjacent_exact",
    relationship      = "adjacent_exact",
    provenance        = "occt",                 # NOT 'source' — 'source' means endpoint in exports/diffs
    symmetric         = True,
    canonical         = True,
    queriedSourceId   = "<the id we asked the route about>",
    queriedTargetId   = "<the candidate id>",
    facePairsFrom     = "queried_source_to_candidate",
    sharedArea        = 3311.978,
    lengthUnit        = "inches",               # from route, never inferred
    areaUnit          = "inches^2",             # from route, never inferred
    facePairs         = [{"sourceFaceIndex": .., "candidateFaceIndex": .., "sharedArea": ..}],
    capabilitiesById  = {"A": "exact_brep", "B": "exact_brep"},  # orientation-safe; survives re-projection from either side
    graphSequence     = 123,
    engineVersion     = 2,
)
```

**Upsert identity** = `(canonical_src, canonical_tgt, key="occt:adjacent_exact")`. If the edge
exists, update provenance / `graphSequence` / cache fields in place — never append a parallel
duplicate. Re-projecting B after A resolves to the same key → update, not a second edge.

`facePairs` indices are relative to `facePairsFrom` (the queried source → candidate); kept
verbatim from the route. No reverse-orientation swap is performed (single canonical edge).

### bbox `adjacent` annotation — projection-scoped, non-destructive
Only edges the projection **actually touched** are annotated. Never stamp every edge globally
(that would imply global truth the projection did not establish):

```python
bbox_edge["approximate"]    = True
bbox_edge["exact_status"]   = "exact_confirmed"   # an adjacent_exact edge exists for this pair
                            | "exact_refuted"      # pair was EVALUABLE and no shared face >= areaTol
                            | "exact_failed"       # attempted but unsupported/conversion-failed
bbox_edge["exact_reason"]   = "no_shared_face"     # on refuted
bbox_edge["exact_diagnostics"] = [...]             # on failed
bbox_edge["exact_graphSequence"] = 123
```

- **`exact_refuted` only when the pair was evaluable** and produced no shared face ≥
  `areaTol`. A candidate that is mesh / SubD / unsupported / conversion-failed →
  **`exact_failed`** with diagnostics, never `exact_refuted`.
- **No invented graph edges for negative facts.** Refuted/failed candidates are reported in
  the tool response, and annotate a bbox edge *only if one already exists* for that pair.
- `_inverse_rel` gains `adjacent_exact → "adjacent to (exact)"`.

### IFC alignment
`adjacent_exact` ≙ `IfcRelSpaceBoundary` (physical), per the design-direction §6 ontology
table. v1 adopts the edge-type *name + meaning*, not the IFC data model.

---

## 4. Data flow & cache

**`scene_exact_neighbors(object_ids=[...], candidate_scope="broad_phase_default", port=...)`:**

1. **Sync the mirror** — `await analytics.sync(port)` so nodes + bbox edges exist and we hold
   the current `graphSequence`.
2. **Prune-on-advance** — if `graphSequence` advanced since the last projection, purge
   projection artifacts (see below) and drop stale cache entries *before* projecting.
3. **Per source id**, check cache key `(graphSequence, sourceId, frozenset(options), engineVersion)`:
   - **hit** → reuse cached per-source result, no route call, `fromCache=True`.
   - **miss** → `POST /scene/graph/adjacency/exact {objectId, ...}`.
4. **Prepare delta** (in memory) — parse the route response; build the exact-edge upserts, the
   bbox annotations, and the response block (neighbors / refuted / failed). Classify each
   considered candidate into confirmed / refuted / failed.
5. **Commit delta** — apply all graph mutations for that source in one shot (prepare-then-commit
   atomicity). If parse/classify failed, apply nothing for that source. **Every commit that
   adds/removes edges or annotations calls `analytics._invalidate_caches()`** (or a small public
   wrapper) so cached `community`/`centrality` results computed before projection are not reused.
6. **Cache** the per-source result under its key.
7. **Return** the structured JSON (§5).

### Cache & invalidation
- Cache lives on the projector singleton, keyed `(graphSequence, sourceId, frozenset(options),
  engineVersion)`. Unit / `engineVersion` mismatch also invalidates.
- **Only durable outcomes are cached** — a per-source block is cached when
  `routeStatus ∈ {ok, skipped}`. `failed` / `timeout` are **never cached**, so a transient
  Rhino/UI-thread timeout is retried on the next call rather than becoming sticky until the
  sequence advances.
- **Active prune on `graphSequence` advance** (load-bearing — stale exact edges are worse than
  none; they present old geometry as precise truth to `get_context`/`scene_stats`/`find_path`/
  the agent). On advance the projector:
  - removes every edge with `key == "occt:adjacent_exact"` (and any `provenance == "occt"` edge);
  - strips projection-owned bbox annotations: `approximate`, `exact_status`, `exact_reason`,
    `exact_diagnostics`, `exact_graphSequence`;
  - calls `analytics._invalidate_caches()` (prune mutates the graph too);
  - Then new explicit calls repopulate for the requested ids.
- **Invariant:** exact facts are **ephemeral read-model enrichment, valid only for the
  `graphSequence` they were computed against.**

### Hard constraints (from the locked design forks)
- **Explicit call only** — never invoked during `sync()` / `/scene/graph/diff`.
- **No internal expansion** — exactly `len(object_ids)` route calls minus cache hits.
  Progressive disclosure is **agent behavior**: the agent picks the next frontier from
  approximate-graph context + already-projected exact edges and calls again with new ids.
  The projector never traverses the graph itself.
- **No whole-model sweep** in v1 (that is a separate, job-based slice with progress /
  cancellation / throttling).

---

## 5. Tool surface & return contract

**New MCP tool** (the only new tool in v1):

```
scene_exact_neighbors(object_ids: [str], candidate_scope?, port?)
```

`candidate_scope` is an **enum with a single v1 value** `"broad_phase_default"` (default).
It is constrained in the tool schema AND **validated inside `project()`** (not only in the MCP
schema) so the agent-direct path is guarded too — any other value returns
`{"success": false, "error": "unsupported candidate_scope ..."}`. (Kept as a named param only as
a forward-compat seam; if it adds friction it may be dropped until a second scope exists.)

**Return** — structured JSON is the contract:

```json
{
  "success": true,
  "graphSequence": 123,
  "unitsUniform": true,
  "lengthUnit": "inches",
  "areaUnit": "inches^2",
  "projected": [
    {
      "sourceId": "A",
      "routeStatus": "ok",
      "error": null,
      "sourceCapability": "exact_brep",
      "capabilitiesById": { "A": "exact_brep", "B": "exact_brep" },
      "neighbors": [
        {
          "id": "B",
          "relationship": "adjacent_exact",
          "sharedArea": 3311.978,
          "lengthUnit": "inches",
          "areaUnit": "inches^2",
          "facePairs": [ ... ],
          "targetCapability": "exact_brep",
          "fromCache": false
        }
      ],
      "refuted": [ { "id": "C", "reason": "no_shared_face" } ],
      "failed":  [ { "id": "D", "reason": "unsupported_geometry", "diagnostics": [ ... ] } ],
      "diagnostics": []
    }
  ],
  "cache": { "hits": 0, "misses": 1 }
}
```

Contract rules:
- **Per-source block** so a multi-id call is unambiguous.
- **`routeStatus`** ∈ `"ok" | "failed" | "timeout" | "skipped"`.
  - `ok` = exact evaluation succeeded (neighbors may be empty = genuinely no exact adjacency).
  - `failed` / `timeout` = could not evaluate (route error / timeout); `error` populated.
  - `skipped` = object not in mirror after sync → `error="object_not_in_scene"`; route not called.
- **Top-level `lengthUnit`/`areaUnit` only if uniform** across all source calls; otherwise omit
  and set `"unitsUniform": false`. **Edge-level units are the source of truth.**
- Neighbor carries **`targetCapability`** (orientation-safe); per-source block carries
  **`capabilitiesById`** and `sourceCapability`. No bare `capability` field.
- **Per-source isolation:** one source failing/timing out never aborts the batch; the
  approximate graph stays usable.

### NL convenience (existing surface, small extension)
`_format_node` + `_inverse_rel` learn `adjacent_exact`, rendering from the edge's own
`areaUnit` (no hardcoded `in²`):

```
exactly adjacent to: WALL "Wall-01", shared face 3311.98 inches^2
```

No new NL tool; `scene_context` picks this up once the edge is in the mirror. A deliberate
display-unit abbreviation map (`inches^2` → `in²`) is a later, opt-in nicety.

---

## 6. Error handling

- Route failure / timeout → **per-source isolated** (`routeStatus` + `error`); batch continues;
  approximate graph untouched.
- Queried object missing from mirror after sync → `routeStatus="skipped"`,
  `error="object_not_in_scene"`, no exception, no route call.
- Malformed / partial route payload → defensive `.get()` parsing (mirrors `_add_edge`'s
  tolerance); missing fields degrade to that source's `failed` / `diagnostics`, never a crash.
- **Atomic per source** via prepare-delta-then-commit: build edges + annotations + response in
  memory, then apply graph mutations in one shot; on parse/classify failure, apply nothing for
  that source (no half-projected source in the mirror).

---

## 7. Testing

- **Unit (pytest, no Rhino) — carries the confidence.** Fake `call_rhino`'s exact-route
  response with a fixture mirroring the SpatialTest payload (5 abutments + a refuted candidate +
  an unsupported candidate). Assert:
  - canonical-edge upsert with the deterministic key;
  - **idempotency** — project A then B → one `occt:adjacent_exact` edge, not two;
  - bbox annotation statuses (confirmed / refuted=`no_shared_face` / failed-with-diagnostics);
  - **prune on `graphSequence` advance** — artifacts removed, repopulate on next call;
  - cache hit / miss accounting and `fromCache`;
  - **unit pass-through** — no conversion; `unitsUniform:false` path when sources disagree;
  - per-source isolation on injected route failure / timeout / `skipped` (object_not_in_scene);
  - **transient failure/timeout is not cached** — a second call retries (no sticky failure);
  - **`candidate_scope` rejection** — an unsupported scope returns `success:false` with an error;
  - **agent-direct registration** — `build_local_tools()` contains a `scene_exact_neighbors`
    handler and `TOOL_GROUPS["scene_graph"]` lists it;
  - prepare-then-commit atomicity — a parse failure leaves the graph unmutated for that source;
  - **analytics-cache invalidation** — compute `centrality()`/`community_detection()`, then
    project (and separately, prune), then verify the cached object is recomputed (not the stale
    pre-projection object).
- **Live smoke (Rhino open, SpatialTest.3dm) — proves wiring only, does not revalidate the
  engine.** One urllib script (sibling to `live_verify_occt_adjacency.py`) calling
  `scene_exact_neighbors` for floorplate `08d4dedf`: the 5 `adjacent_exact` edges land in the
  mirror with correct `sharedArea`/`areaUnit`, `scene_context` renders them, and a re-call is a
  cache hit.

---

## 8. Carried-forward caveats (separate from this slice's code)

1. **Engine acceptance contract (engine's gate, not Projection v1).** Before the *branch* is
   merge/release-gated, extend the engine's live-verify `live_verify_occt_adjacency.py` to also
   cover wall×wall `18651.672 in²`, unsupported-geometry diagnostics, and an `exact_brep`
   no-neighbor (zero-edge) case. Independent of this slice.
2. **Task 9b — pin OCCT 7.9.3 (deferred).** Use a separate OCCT worktree / build dir, point
   `OCCT_ROOT` at it; **never switch the shared `C:/Users/aryan/source/repos/OCCT` checkout off
   the verified V8_0_0.** See `docs/rook_docs/occt-build.md`.

---

## 9. Dependencies & sequencing within v1

1. `ExactAdjacencyProjector` module (edge model + prepare/commit + cache + prune) — unit-tested
   against the faked route.
2. `scene_exact_neighbors` MCP tool case in `server.py` (sync → project → return).
3. `get_context` / `_inverse_rel` NL extension for `adjacent_exact`.
4. Live smoke script + run on SpatialTest.3dm.

This slice depends only on the shipped OCCT engine. It does **not** depend on Spike F,
containment refinement, or hosting/apertures — those are later slices that build on this
projection substrate.
