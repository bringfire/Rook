# Spatial Graph — Projection, Ontology & Intelligence (design direction)

> **Current north star (2026-06-28):** This document is retained as historical design direction
> for topology projection and graph-policy ideas. For the current canonical spatial-intelligence
> framing, use `docs/rook_docs/SPATIAL_INTELLIGENCE_NORTH_STAR.md`. In particular, treat graph
> relationships as claims, evidence, verdicts, observations, profiles, or views before adding a
> new layer.

> **⚠ Extraction note (Slice A, `feature/occt-adjacency-engine`):** Included on the OCCT engine
> branch as a **docs-only downstream companion** — it gives the engine PR its consuming-layer
> context with no code coupling. The graph/projection layer described here is **implemented in
> Slice B (Exact Adjacency Projection v1)**, not on this branch.

> **Status (2026-06-14): DESIGN DIRECTION captured for later — NOT yet executed.**
> This is the *intelligence* layer that sits on top of the adjacency engine. The
> OCCT engine (see `2026-06-14-occt-uniform-engine-decision.md`) produces the
> **edges** (exact relations); this doc is about the **graph** those edges feed and
> the queries that make it "spatial intelligence." When we pick this up, it deserves
> its own brainstorm → spec → plan. The purpose of this doc is so we resume from the
> grounded conclusions below instead of relitigating from scratch.
>
> Companions: `2026-06-13-spatial-intelligence-foundation.md` (gated roadmap),
> `2026-06-14-occt-uniform-engine-decision.md` (the engine/edges), memory
> `project_spatial_intelligence_topology`.

---

## 1. The core reframe (the biggest lesson from reading Topologic's source)

**The graph is a *projection* of a coherent topology — not the primary stored artifact.**

Topologic does not store-and-maintain a graph. It builds a coherent **topology** first
(a CellComplex, via OCCT imprinting/`MakerVolume`), then **projects** a graph from it on
demand: `Graph::ByTopology` → cells become nodes (at centroids), shared faces become
edges. The graph is a **dual** of the topology.

Consequence for Rook: resist computing a graph ad-hoc from independent pairwise
adjacency tests (what the current exact engine does, pair by pair). Derive the graph
from a coherent topology so every edge traces to a *real shared sub-shape* and neighbors
can't disagree. **This is the deepest reason the construction tier (Spike F:
`MakerVolume`/`CellsBuilder`) matters specifically for the graph** — pairwise adjacency
is enough for "what touches what," but a *consistent* graph (and circulation, and zones)
wants the constructed topology underneath.

(Pragmatic nuance: pairwise exact adjacency is a fine *bootstrap* for the adjacency
graph alone; the topology-first requirement bites for circulation + zones. See Fork B.)

---

## 2. Lessons from Topologic (grounded — we read `TopologicCore` + `topologicpy`)

1. **Edge semantics are policy-parametric.** `Graph::ByTopology` takes flags — *direct*
   (cell↔cell via shared face), *via-shared-topology* (route through a node placed ON the
   shared wall → the wall itself becomes a graph node), *via-aperture* (route through
   doors/windows), *to-exterior-topologies/apertures*, *to-contents*, *use-internal-vertex*.
   **One geometry yields different graphs depending on the question.** Adjacency graph,
   circulation graph, and containment tree are different *projections* of one topology.
   ⇒ the graph layer is a configurable **projector**, not a single fixed graph.

2. **Apertures are first-class, and they are the bridge.** Doors/windows are "apertures"
   hosted in a face; they become traversal nodes/edges. This is the distinction between
   *"two rooms share a wall"* (adjacency) and *"two rooms are connected by a door"*
   (circulation). **Hosting (aperture-in-host) is the relationship that turns an
   adjacency graph into a circulation graph.** Sealed-room-with-no-door correctly has no
   egress edge — Gate 2 spike confirmed this end-to-end.

3. **Adjacency = shared sub-shape IDENTITY** (`IsSame` over the imprinted topology),
   recovered via `TopExp::MapShapesAndUniqueAncestors` (face→cells ancestor map; a face
   with 2 solid-ancestors = interior shared wall = adjacency). ⇒ edges keyed by **stable
   identity**, not transient geometry.

4. **Every entity carries a Dictionary** (attributes). ⇒ graph nodes/edges carry
   semantic payload (type, classification, properties) — geometry + semantics fused, not
   a bare topology.

5. **Topology hierarchy** (Vertex/Edge/Wire/Face/Shell/Cell/CellComplex/Cluster) gives a
   clean vocabulary; we don't need all of it, but Cell (zone) + Face (boundary) + Aperture
   (opening) + the dual Graph are the load-bearing concepts.

---

## 3. Lessons from other precedents (trust real-world precedent)

- **IFC relationship ontology** — the mature, standard building-relationship vocabulary;
  align our edge types to it rather than inventing a private ontology (also gives interop
  with the FreeCAD/IFC track):
  - `IfcRelSpaceBoundary` — space↔element adjacency, with *physical vs virtual* distinction.
  - `IfcRelContainedInSpatialStructure` — the containment hierarchy site→building→storey→space→element.
  - `IfcRelVoidsElement` / `IfcRelFillsElement` — openings and their fillings = **apertures**.
  - `IfcRelConnectsElements`, `IfcRelConnectsPathElements` — element-to-element connection.
  - `IfcRelAggregates` — part/whole.
  Lesson: adopt this *vocabulary* for edge types so semantics are standard and exportable.

- **Space syntax / Justified Plan Graph (JPG)** — where the graph becomes *intelligence*.
  Once the circulation dual exists: depth-from-entrance, integration, connectivity,
  choice, egress paths, isovist/visibility graphs. **These are the queries a practice would
  actually value, and they are domain knowledge, not new geometry.** The graph's payoff
  is this analytics catalog, not the graph itself.

- **Property graphs (Neo4j-style)** — the right *model*: typed nodes + typed edges +
  properties + traversal queries. And we already have one — **networkx is a property
  graph** (attribute dicts on nodes/edges). No new graph DB needed for our scale.

- **Game-engine nav meshes** — weak analogy; the "walkable connectivity" idea parallels
  circulation, but their hierarchies are render/nav-specific. Not a primary precedent.

---

## 4. What Rook already has (the head start — don't rebuild)

- Live scene-graph mirror: networkx `MultiDiGraph`, RookId-keyed nodes carrying
  classification (`shape_class`/`domain_label`) + provenance, edges for bbox relationships
  (contains/supports/adjacent/near/intersects/above), maintained **incrementally**.
- Shipped algorithms: `find_path`, Louvain communities, centrality, containment-tree.
- The thing Topologic lacks: **an AI agent + a human in the loop.** ⇒ the graph must be
  **agent-legible** and answer natural-language questions ("which rooms reach the lobby
  without stairs?"), not only feed algorithms.

So this is *enrichment* of an existing graph substrate, not a greenfield graph build.

---

## 5. Proposed architecture (the shape to build toward)

A **multi-layer property graph, projected from a coherent topology, IFC-aligned,
queryable by both algorithms and the agent:**

1. **Substrate** — the existing networkx mirror, RookId-keyed. Keep + enrich.
2. **Exact relations** (the engine's output, in flight) — adjacency (OCCT shared-face),
   containment, hosting (voids/fillings). These *refine* today's bbox-approximate edges.
3. **Projection layer** — Topologic's lesson made concrete: from the relations, project
   the *specific* graph a question needs (adjacency / circulation-via-apertures /
   containment-tree / change-impact), **edge-policy parametric**, edge types aligned to
   the IFC vocabulary (§3).
4. **Intelligence layer** — graph analytics (paths, egress, depth, integration,
   communities) + the agent/NL query surface.

**Where it lives** (follows the already-decided data-locality rule): geometry + exact
relations in **C++** (co-located with objects); the **reduced graph** (N nodes, ~kN
edges — tiny vs geometry) shipped to **Python/networkx** for projection + analytics.
Never ship geometry across the boundary.

---

## 6. Edge ontology (proposed IFC-aligned mapping)

| Rook edge | Source | IFC analogue | Notes |
|---|---|---|---|
| `adjacent_exact` | OCCT shared-face area | `IfcRelSpaceBoundary` (physical) | the engine's core output; carries `sharedArea` |
| `contains` / `contained_in` | bbox + point-in-solid | `IfcRelContainedInSpatialStructure` | refine bbox version with exact containment |
| `hosts` / `hosted_by` (aperture) | void/fill detection | `IfcRelVoidsElement`/`IfcRelFillsElement` | the adjacency→circulation bridge |
| `connects` (circulation) | derived: adjacency + shared aperture | `IfcRelConnectsPathElements` | the space-syntax dual edge |
| `supports` / `supported_by` | bbox vertical + contact | `IfcRelConnectsElements` | already approximate; refine |
| `aggregates` (part/whole) | block/assembly structure | `IfcRelAggregates` | ties to block/instance model |
| `impacts` (change-propagation) | derived from the above | — | dependency edges for change-impact queries |

---

## 7. Open design forks (decide later — do NOT relitigate from scratch)

**Fork A — one topology, many projections vs. one maintained graph.**
Topologic = build topology, project graphs on demand. Lean: **projection model** (a
projector with edge-policy flags). Tension: interacts with incremental update (re-project
on change vs. patch the projected graph). Resolution likely: maintain the *relations*
incrementally; project the *question-specific graph* lazily/cached (mirrors the
adjacency-service lazy+cache pattern).

**Fork B — topology-first (Spike F) vs. pairwise-adjacency bootstrap.**
Pairwise exact adjacency (current engine) gives a consistent-enough *adjacency* graph
now. Circulation + zones *need* the constructed topology (cells, apertures). Lean: ship
the adjacency graph on pairwise first; build the construction tier (Spike F) when
circulation/zones are the goal, and let it *supersede* pairwise adjacency as the
consistency source. Decision point: when do we commit Spike F.

**Fork C — how much IFC ontology to adopt.**
Enough vocabulary for standard, exportable semantics (the §6 table) without dragging in
IFC's full schema weight. Lean: adopt the *edge-type names + meanings*, not the IFC data
model. Revisit when the FreeCAD/IFC interop track is live.

**Fork D — incremental maintenance.**
The scene graph already updates incrementally (watcher → processor thread). The
exact-relation + projection layers must follow the same discipline so the graph stays
**live**, not batch-recomputed. Open: how relation edges invalidate on geometry change
(graphSequence-keyed, like the adjacency cache) and how projections re-derive.

**Fork E — identity spine.**
Nodes/edges keyed by **RookId** (stable across recompute/save/export), per the BIM-doc
identity decision (RookId, NOT IFC GlobalId which export overwrites). Open: edge identity
(do edges get stable IDs, or are they derived/ephemeral from node-pair + type?).

**Fork F — agent-legibility & NL query surface.**
The projection + query layer must let the agent reason over it and the human query in
natural language. This is a *design constraint Topologic never had*. Open: graph→agent
representation (serialized subgraph? a query DSL? MCP tools like
`scene_query`/`find_path` extended to circulation/egress?), and how NL maps to graph
queries.

**Fork G — the analytics catalog (what queries = "intelligence").**
Decide the first-class queries: adjacency neighborhood, containment tree, egress/shortest
accessible path, depth-from-entrance, integration/centrality, zone communities,
change-impact propagation, visibility/isovist. Lean: start with adjacency + containment +
egress (highest architectural value), then space-syntax metrics. These are domain
knowledge to mine (practice analyses, space-syntax literature).

---

## 8. Dependencies & sequencing

- **Depends on** the OCCT adjacency engine (edges) — in flight.
- **Circulation + zones depend on** the construction tier (Spike F) — deferred.
- **Substrate already exists** (networkx mirror + algorithms) — enrich, don't rebuild.
- Suggested order: (1) refine existing networkx edges with the engine's exact adjacency +
  containment; (2) add hosting (apertures) once void/fill detection lands; (3) build the
  projection layer (edge-policy parametric, IFC-aligned); (4) Spike F construction tier →
  zones + circulation; (5) the analytics catalog + agent/NL query surface.

When picked up: brainstorm → spec → plan (this is a sibling subsystem to the engine, not
a small feature).
