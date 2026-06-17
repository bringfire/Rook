# Semantic Containment Refinement v1 — design

> **Status (2026-06-16): DESIGN APPROVED (brainstorm complete) — ready for writing-plans.**
> Slice owner: spatial-intelligence track, branch `feature/spatial-intelligence`
> (worktree `C:/Users/aryan/source/repos/rook-spatial`; `main` untouched).
>
> The second **intelligence-layer** slice, after Exact Adjacency Projection v1. Where
> Projection v1 turned the OCCT engine's exact adjacency into typed graph edges, this slice
> refines the scene graph's **approximate bbox `contains` edges** into **semantic,
> confidence-scored, provenance-tagged** containment between actual modeled objects — the
> first trustworthy relationship-confidence substrate that later room reconstruction,
> hosting/apertures, and zones will build on.
>
> Companions: `docs/rook_docs/2026-06-14-spatial-graph-projection-design.md` (parent direction,
> §6 IFC ontology `contains/contained_in → IfcRelContainedInSpatialStructure`, §8 step 1's
> containment half), `docs/superpowers/specs/2026-06-16-exact-adjacency-projection-v1-design.md`
> (the read-model pattern this mirrors), memory `project_spatial_intelligence_topology`.

---

## 1. Problem & goal

The scene graph's `contains` edges are **pure bbox** today: `CSceneGraph::ComputePairRelationships`
emits `contains` whenever `BBoxContains(A, B)` (A's bbox fully encloses B's). That is a coarse
signal — it fires on penetration (a slab's bbox "containing" a column passing through it),
near-coincident bboxes, and non-solid containers. There is **no** semantic/confidence layer.

**Goal of v1:** an explicit, lazy, **Python read-model** refiner that evaluates the existing
bbox `contains` candidates incident to queried objects and classifies each into a semantic
verdict with ordinal confidence and an explicit evidence list — preserving the bbox edges,
adding parallel `contains_semantic` edges only for positive verdicts, and annotating every
evaluated bbox edge with the result. Object↔object only. **Enrichment of approximate facts,
not a geometry oracle.**

### Honesty constraint (load-bearing)
v1 has **no way to verify a container is a closed solid**: `metrics.volume` is *bbox* volume
(`ComputeMetrics(bboxMin, bboxMax)`), and no `IsClosed`/`IsSolid` is captured. Therefore every
positive verdict is **`contains_semantic`** (ordinal confidence), **never `contains_exact`**.
A geometrically-exact verdict is the deferred **"Exact Containment Engine"** slice. The module
name, edge `relationship` (`contains_semantic`), and provenance (`semantic_refiner`) make this
explicit so no consumer mistakes a v1 fact for geometric truth.

### In scope
- A Python read-model `ContainmentRefiner` over existing bbox `contains` edges (no C++ changes).
- `scene_refine_containment(object_ids=[...])` MCP tool — explicit object-set primitive.
- Verdict + ordinal confidence + evidence model; parallel `semantic:contains` edges on positive
  verdicts; non-destructive bbox-edge annotation for every evaluated candidate.
- Request-level sequence-keyed cache + active prune of artifacts on `graphSequence` advance.
- NL rendering of semantic containment via the existing `get_context` surface.

### Out of scope (deferred to later slices)
Room/space reconstruction, `bounded_by`, hosting/apertures, circulation, zones, **native
point-in-solid** ("Exact Containment Engine"), persistence, IFC export, any new native route,
any unit conversion (containment is structural, unitless).

---

## 2. Architecture & component placement

A Python read-model layer over the synced mirror. **Zero C++ changes.** New isolated module
**`mcp_server/src/rook/scene/containment_refinement.py`** holding a `ContainmentRefiner` class
(+ singleton `get_containment_refiner`) that takes the `SceneGraphAnalytics` mirror as a
collaborator — parallel to `ExactAdjacencyProjector`. It owns no graph; it reads/refines the
mirror, which stays the single source of truth.

```
scene/containment_refinement.py
  class ContainmentRefiner:
      def __init__(self, analytics: SceneGraphAnalytics)
      async def refine(object_ids, *, port=None) -> dict   # the tool payload
      # internals: _candidate_contains_edges, _evaluate_candidate (verdict+evidence),
      #            _commit_delta (prepare-then-commit), _purge_artifacts, request cache
  _refiner singleton via get_containment_refiner(analytics)
```

**Why a new module, not `exact_projection.py`:** different relation family (directional
containment vs symmetric adjacency), different evidence (pure read-model inference vs route
projection), different verdict model. A separate, focused unit preserves the
single-responsibility that made Projection v1 clean and is testable in isolation with a
synthetic mirror. (Rejected alternative: folding into `exact_projection.py` — would erode the
boundary and mix two relation families.)

### Ephemeral read-model invariant
Semantic containment facts are **ephemeral read-model enrichment, valid only for the
`graphSequence` they were computed against.** On sequence advance the refiner purges edges with
`key == "semantic:contains"` (and any `provenance == "semantic_refiner"` edge) and strips
refiner-owned annotations from bbox `contains` edges, then invalidates analytics caches. No
baseline-sync work; no persistence.

---

## 3. Candidate set & trigger surface

**Tool:** `scene_refine_containment(object_ids=[...], port?)` — explicit object-set primitive
(Projection v1 pattern). Progressive disclosure is **agent behavior** (call again with new ids);
no internal graph-walk, no whole-model sweep.

**Candidates per queried id `X`** = every existing bbox `contains` edge incident to X **in either
role**:
- X is the **container** (`X →contains→ Y`) — "what does X contain?"
- X is the **contained** (`Z →contains→ X`) — "what contains X?"

Both roles are evaluated (an agent asking about an object wants both; restricting to one
direction forces callers to know graph orientation).

Rules:
- **Candidate identity is ordered** `(container_id, contained_id)` — containment is not symmetric;
  dedup by the ordered pair. If both endpoints are queried, evaluate **once** and reference it
  from each relevant source block.
- Candidates come **only** from `contains` edges already in the synced mirror. v1 **never**
  invents pairs and never tests arbitrary/overlapping/near object pairs.
- If multiple `contains` multiedges exist for the same ordered pair, **evaluate once** and
  annotate **all** matching bbox `contains` edges for that ordered pair.
- If X has no bbox `contains` edges, its per-source block is `ok` with empty role lists (nothing
  to refine — not an error).
- **Bounded work:** total evaluations ≤ number of `contains` edges incident to the queried ids.

---

## 4. Evidence signals & verdict inference

Enclosure is *given* (the candidate exists because `BBoxContains` fired), so it is not itself
discriminating — **margin/clearance quality**, corroboration, and disqualification are. The model
is **additive multi-signal → ordinal confidence**: independent evidence accumulates toward
higher/lower confidence, and the full evidence list is always exposed so the verdict is
explainable. Confidence is **ordinal, not probabilistic** (the foundation for later calibration;
no numeric probability claims in v1).

Each signal emits one or more `{signal, polarity, detail}` items, `polarity ∈ {supports,
weakens, disqualifies}`:

| Signal | Source | Polarity logic |
|---|---|---|
| `bbox_margin` | bboxMin/Max of the pair | positive clearance beyond tolerance on all axes → **supports**; **flush on one axis** (object validly resting flush to a container's floor) → **weakens** (never disqualifies) |
| `containment_depth` | normalized clearances of contained within container | contained sits meaningfully inside on multiple axes → **supports**; inside only by tiny numeric tolerance → **weakens** (may be the quantitative core of `bbox_margin`, but named for clarity) |
| `container_solidity` | container `geometry_type` | Brep/Extrusion → **supports** (weak — closure unverified); Curve/Point/Annotation/Light/Hatch/TextDot → **disqualifies** (`not_a_solid`); open Surface → **weakens**; **Mesh and SubD are NOT lumped** — both are weak/unknown (neither auto-support nor disqualify) absent closure metadata we don't have |
| `class_pair` | `shape_class`/`domain_label` of A & B | compact/block container → **supports**; **thin** container (wall/column/beam; vertical-planar/thin-*) → **weakens strongly** (NOT an automatic veto — walls/cabinets/blocks can legitimately contain embedded objects) |
| `bbox_volume_ratio` | bbox volumes (named to avoid implying mass/solid volume) | contained ≪ container → **supports**; contained ≈ container (near-coincident) → **weakens** |
| `grouping_hint` | **layer only (v1)** | shared non-empty layer → **supports** (weak only — never reaches `high` on its own). Name- and user-string-based grouping are **deferred** (user strings aren't in the mirror; name heuristics are noisy) until the mirror carries normalized grouping metadata |
| `touching_exact` | an **already-projected** `adjacent_exact` edge for the pair | present → **weakens** (disambiguation: a shared face *suggests* adjacency/bounding rather than containment) — but **NOT a standalone veto**, because a contained object can legitimately rest flush against an interior container face. It contributes to the compound `likely_penetration` veto (below). Used **only if already in the mirror**; the refiner never calls the exact projector itself |

### Hard vetoes (→ `disqualified`, confidence `none`)
Exactly **two** conditions disqualify:
1. **`not_a_solid`** — container `geometry_type` cannot be a container (Curve/Point/Annotation/Light/Hatch/TextDot).
2. **`likely_penetration`** — a **compound** pattern only: thin container class **AND** flush/poor
   `bbox_margin`/`containment_depth` **AND** contained spans through the container's depth —
   optionally **reinforced by `touching_exact`** (a shared face on a thin, poorly-clearing pair is
   strong penetration evidence). (Thin class *alone* strongly weakens, never vetoes; `touching_exact`
   *alone* weakens, never vetoes — this avoids brittle folklore and the "inside-but-touching" false
   negative, while still catching the slab-bbox-"contains"-column false positive when geometry agrees.)

`touching_exact` is **not** a standalone veto: contact and containment are not mutually exclusive
(a contained object can rest flush against an interior face). It is a strong disambiguation
*weakener* that can tip a thin/poor-margin pair into the compound penetration veto.

### Verdict mapping
- **`disqualified`** (confidence `none`): a hard geometry/type veto (`not_a_solid`) or the
  compound penetration pattern (`likely_penetration`); record `reason`. (Exact touching alone does
  NOT disqualify — see vetoes above.)
- **`contains_semantic` / `high`**: strong positive bbox clearance + plausible solid/container
  class + favorable bbox volume ratio + no weakens/disqualifiers.
- **`contains_semantic` / `medium`**: strong bbox clearance + plausible container, but
  class/grouping corroboration is neutral or one weakener exists.
- **`contains_semantic` / `low`**: bbox containment is real and no disqualifier fires, but
  evidence is thin.
- **`insufficient_evidence`** (confidence `none`): bbox `contains` exists, but container
  solidity/type/class is unknown or mixed evidence cannot distinguish containment from a coarse
  bbox artifact.

All numeric cutoffs (`bbox_margin` tolerance/epsilon, `containment_depth` and `bbox_volume_ratio`
thresholds) are **named constants** pinned in the spec/plan, tunable — never magic literals inline.

---

## 5. Edge representation & reconciliation

Containment is **directional** — no canonical min/max (unlike adjacency).

On a `contains_semantic` verdict, idempotently upsert a single parallel directed edge keyed by
`(container_id, contained_id, key="semantic:contains")`:

```python
graph.add_edge(container_id, contained_id, key="semantic:contains",
    relationship   = "contains_semantic",   # plain, get_context/agent-readable
    provenance     = "semantic_refiner",
    verdict        = "contains_semantic",
    confidence     = "high" | "medium" | "low",
    reason         = "<controlled_reason_code>",   # e.g. strong_clearance_plausible_container
    evidence       = [{"signal":.., "polarity":"supports|weakens|disqualifies", "detail":..}],
    graphSequence  = <mirror seq>,
)
```

**Bbox `contains` edge annotation** — applied to **all** matching bbox `contains` edges for the
ordered pair, for **every** evaluated candidate (semantic, insufficient, and disqualified):

```python
bbox_edge["containment_status"]        = "contains_semantic" | "insufficient_evidence" | "disqualified"
bbox_edge["containment_confidence"]    = "high|medium|low|none"
bbox_edge["containment_reason"]        = "<controlled_reason_code>" | None
bbox_edge["containment_evidence"]      = [ ... ]   # so a consumer sees WHY without re-running
bbox_edge["containment_graphSequence"] = <mirror seq>
```

- **Negative facts** (`insufficient_evidence` / `disqualified`) create **no** graph edge — they
  live only in the bbox-edge annotation and the tool response.
- **`reason` is a controlled vocabulary**, not free prose: positive codes (e.g.
  `strong_clearance_plausible_container`, `enclosed_thin_evidence`) and negative codes
  (`not_a_solid`, `likely_penetration`, `insufficient_evidence`). (Note: `touching_exact` is an
  *evidence signal*, not a disqualification reason — it only reinforces `likely_penetration`.)
- **Prune-on-sequence-advance** removes `semantic:contains` / `provenance=="semantic_refiner"`
  edges and strips `containment_status`/`containment_confidence`/`containment_reason`/
  `containment_evidence`/`containment_graphSequence` from bbox edges; invalidates analytics caches.
- **Prepare-then-commit atomicity, request-level (candidate-oriented):** because candidates are
  directional and deduped across the queried set (`A|contains|B` is evaluated once even if both A
  and B are queried), atomicity is defined over the **request's candidate delta**, not per source.
  Build the full candidate delta (edges + annotations + per-candidate results) in memory, then
  commit all evaluated candidates in one shot; derive each affected source block from that prepared
  result. A candidate whose evaluation raises is dropped to `failed` and contributes **no** partial
  edge/annotation; the source blocks referencing it are marked accordingly.

### IFC alignment (IFC-aware, NOT IFC-exportable in v1)
`contains_semantic` here refines **arbitrary object↔object** containment, which is broader than any
single IFC relation. In IFC, `IfcRelContainedInSpatialStructure` is specifically containment in a
*spatial structure* element (site/building/storey/space) — which this slice explicitly excludes
(no rooms/spaces). So v1's edge is **IFC-aware but not directly IFC-exportable**: it may map to
`IfcRelContainedInSpatialStructure` only once the container is later classified as a spatial
structure, and arbitrary object↔object containment may otherwise map to aggregation/nesting/hosting
or remain a Rook-local relation. v1 makes **no** IFC export claim.

---

## 6. Return contract, cache & NL

### Data flow (`refine(object_ids, port)`)
1. **Sync the mirror** — `await analytics.sync(port)` so nodes + bbox `contains` edges exist and
   we hold the current `graphSequence` (the refiner owns the sync, like `project()`, so both the
   MCP and agent-direct paths behave identically).
2. **Prune-if-advanced** — if `graphSequence` advanced since the last refine, purge artifacts (§5)
   and clear the request cache *before* evaluating.
3. **Request cache** — if `(graphSequence, tuple(sorted(set(object_ids))))` is cached, return it;
   else continue.
4. **Collect candidates** (§3, deduped by ordered pair), **evaluate** each (§4) into an in-memory
   **request-level candidate delta**, then **commit** all evaluated candidates in one shot (§5,
   prepare-then-commit); derive each `bySource` block from the prepared result.
5. **Cache** the request result (only if no source is `failed`) and **return** (§6 contract).

**Candidate-oriented `refined[]` + per-source role index** (resolves the directional/multi-role
ambiguity — each candidate appears once; queried ids reference it by `candidateId` and role):

```json
{
  "success": true,
  "graphSequence": 123,
  "refined": [
    { "candidateId": "A|contains|B", "containerId": "A", "containedId": "B",
      "verdict": "contains_semantic", "confidence": "high",
      "reason": "strong_clearance_plausible_container",
      "evidence": [ {"signal":"bbox_margin","polarity":"supports","detail":"clearance 0.4m all axes"}, ... ] },
    { "candidateId": "A|contains|C", "containerId": "A", "containedId": "C",
      "verdict": "disqualified", "confidence": "none", "reason": "likely_penetration",
      "evidence": [ {"signal":"class_pair","polarity":"weakens","detail":"thin container (wall)"},
                    {"signal":"bbox_margin","polarity":"weakens","detail":"flush on 2 axes"},
                    {"signal":"touching_exact","polarity":"weakens","detail":"shared face present"} ] }
  ],
  "bySource": {
    "A": { "status": "ok", "error": null, "asContainer": ["A|contains|B","A|contains|C"], "asContained": [] },
    "Z": { "status": "skipped", "error": "object_not_in_scene", "asContainer": [], "asContained": [] }
  },
  "cache": { "hits": 0, "misses": 1 }
}
```

Contract rules:
- `candidateId = "<containerId>|contains|<containedId>"`; `bySource.asContainer`/`asContained`
  list **candidateIds** (not bare opposite ids) — unambiguous for agent parsing.
- **`status` enum** ∈ `{ok, skipped, failed}` — **no `timeout`** (pure read-model, no route).
  `skipped` = not in mirror (`object_not_in_scene`); `failed` = evaluation raised (per-source
  isolated; prepare-then-commit means no partial mutation); `ok` + empty role lists = genuinely
  no `contains` candidates.
- **No unit fields** — containment is structural/unitless.
- **Top-level failure propagation:** the MCP/agent handlers return a top-level failure when
  `payload.success is false` (the Projection v1 finding-4 lesson).

### Cache & invalidation
- **Request-level cache**, key = `(graphSequence, tuple(sorted(set(object_ids))))` — duplicate
  query ids are deduped (not meaningful). Identical repeat calls hit; different object sets
  recompute (acceptable — pure read-model, bounded). Candidate-level caching is a later optimization.
- Cache only durable outcomes; a request that produced any `failed` source is **not** cached.
- **Active prune on `graphSequence` advance** clears the cache and purges graph artifacts (§5).

### NL via `get_context`
Extend `_FORWARD_RELS` / `_INVERSE_RELS` with `contains_semantic → "contains (semantic)"` /
inverse `"within (semantic)"`, and `_edge_detail` to render confidence, e.g.
`contains (semantic, high): WALL "W-01"`. No new NL tool; `scene_context` picks it up once the
edge is in the mirror.

---

## 7. Registration (applies both Projection v1 lessons)

1. **Dispatch case** `scene_refine_containment` in `server.py` (sync mirror → refiner → return;
   propagate top-level failure when `payload.success is false`).
2. **Tool schema** in `list_tools` (`object_ids` required array of strings; `port`).
3. **Tool group**: add `"scene_refine_containment"` to `TOOL_GROUPS["scene_graph"]`
   (`tool_groups.py:102`).
4. **Agent-direct local handler** in `tool_dispatcher.py::build_local_tools()` (the dispatcher has
   no scene refs → group-only registration is discoverable-but-unexecutable).
5. **Targeting policy** (the finding-1 lesson): add to `_ALL_KNOWN_TOOLS` **and**
   `_RHINO_READ_TOOLS` → `RhinoToolPolicy(requires_rhino=True, risk="read")` — it syncs the mirror
   (which calls `/scene/graph`), so it needs Rhino and is read-only.

---

## 8. Error handling

- Per-candidate isolation: one candidate's evaluation failure never aborts the request; other
  candidates still commit. Affected `bySource` blocks are marked `failed` (with `error`); the
  approximate graph stays usable.
- Queried object missing from the mirror after sync → that source block `skipped` +
  `error="object_not_in_scene"` (no candidates collected for it).
- Malformed/partial graph data → defensive `.get()` parsing; degrade the affected candidate to
  `failed`, never a crash.
- **Atomic, request-level candidate delta** (prepare-delta-then-commit): build all edges +
  annotations + per-candidate results in memory, apply in one shot; a candidate whose evaluation
  raises is dropped to `failed` and partially annotates nothing — source blocks referencing it are
  marked from the prepared result.

---

## 9. Testing

- **Unit (pytest, no Rhino) — carries verdict confidence.** Synthetic mirror with bbox `contains`
  edges + node attrs (`geometry_type`, `shape_class`/`domain_label`, bbox, layer/name). Assert:
  - each verdict/confidence tier (`high`/`medium`/`low`/`insufficient_evidence`);
  - the **two** hard vetoes: `not_a_solid` (Curve container) and compound `likely_penetration`
    (thin class + flush margin + spans depth, optionally reinforced by `touching_exact`);
  - **`touching_exact` alone weakens but does NOT veto** (regression guard: an `adjacent_exact`
    edge present + otherwise strong containment evidence still yields `contains_semantic`, not
    `disqualified` — the "inside-but-touching" case);
  - thin-class-alone **weakens but does not veto** (regression guard against brittle class folklore);
  - both-role evaluation + ordered-pair dedup + multi-edge annotation;
  - semantic edge only on positive; bbox annotation on **all** evaluated; negatives non-edged;
  - `candidateId` format; `bySource` references candidateIds; `refined[]` candidate-oriented;
  - **projection-artifact interaction**: with an `adjacent_exact` edge present → consumed as the
    `touching_exact` signal; **with projection artifacts absent → the refiner does NOT call the
    exact projector** (guards the pure-read-model boundary);
  - **request-level cache** hit (same `sorted(set(object_ids))`, incl. duplicate-id dedup) + miss
    (different set) + failed-uncached;
  - **prune + cache invalidation on `graphSequence` advance** (edges + annotations stripped,
    analytics caches invalidated, request cache cleared);
  - **request-level prepare-then-commit atomicity** (a candidate raising → no partial edge/annotation
    anywhere; other candidates still commit);
  - `status` ok/skipped/failed; NL render of `contains_semantic`;
  - targeting policy classification (`requires_rhino`/`read`) + `_ALL_KNOWN_TOOLS` membership;
  - registration: `TOOL_GROUPS` membership + `build_local_tools()` handler + handler propagates
    top-level failure.
- **Live smoke (gated, Rhino on SpatialTest.3dm) — contract/wiring only, NOT domain acceptance.**
  SpatialTest is abutting walls/floorplate and may produce **zero** semantic containment
  positives; that is acceptable if the contract is well-formed and Rhino remains stable. The smoke
  asserts the tool runs end-to-end against the live mirror and returns a well-formed contract
  (clean `ok`, even if `refined[]` is empty); verdict logic is owned by the unit tests. (If a
  containment case exists, assert its verdict; do not hard-require one.)

---

## 10. Carried-forward caveats (separate from this slice)

1. **Exact Containment Engine** (deferred): a native point-in-solid test for a geometrically-exact
   verdict (`contains_exact`). v1 is deliberately semantic-only because closure is unverifiable
   from current mirror metadata. Sequence this after the read-model layer tells us which verdicts
   and confidence explanations are actually useful.
2. **`rhino_vision_presentation`** targeting-gate drift (from main's merged #254, not on this
   branch) — resolves on rebase/merge; do not duplicate here.
3. **Task 9b** (pin OCCT 7.9.3) — deferred; separate OCCT worktree/build dir, never switch the
   shared checkout off V8_0_0.

---

## 11. Dependencies & sequencing within v1

1. `ContainmentRefiner` module (candidate set + evidence/verdict inference + prepare/commit +
   request cache + prune) — unit-tested against a synthetic mirror.
2. `scene_refine_containment` MCP tool (dispatch + schema + group + agent-direct handler) +
   targeting policy.
3. `get_context` / `_FORWARD_RELS` / `_INVERSE_RELS` NL extension for `contains_semantic`.
4. Live wiring smoke + gated run on SpatialTest.3dm.

This slice depends only on the existing scene-graph mirror + bbox `contains` edges. It does **not**
depend on the exact projector at runtime (it only *uses* `adjacent_exact` edges opportunistically
if already present) and introduces no native changes.
