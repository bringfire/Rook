# Spatial Intelligence — Return Checkpoint (pivot to RookBIM)

> **Durable return checkpoint set 2026-06-16.** The spatial-intelligence track is being
> PAUSED to do RookBIM work (Revit→Rhino geometry + data export for later calibration).
> This doc is the single resume point — read it FIRST on return.
>
> Branch `feature/spatial-intelligence`, worktree `C:/Users/aryan/source/repos/rook-spatial`
> (`main` untouched). Never stage `knowledge/contextual_mab.pkl`,
> `knowledge/gh/component_observations.json`, or `src/Rook/Properties/launchSettings.json`
> (known local/runtime files).

---

## 1. Completed (shipped on this branch)

- **OCCT exact-adjacency engine — production route complete.** `POST /scene/graph/adjacency/exact`
  runs the `Rook::occt::OcctAdjacencyEngine` (shared-face area). Decision/record:
  `docs/rook_docs/2026-06-14-occt-uniform-engine-decision.md` (§0 RESOLVED banner).
- **Exact Adjacency Projection v1 — complete + live-verified.** Python read-model projecting
  `adjacent_exact` edges into the networkx scene-graph mirror via the `scene_exact_neighbors`
  tool. Module `mcp_server/src/rook/scene/exact_projection.py`.
- **Semantic Containment Refinement v1 — complete + live-verified.** Python read-model refining
  bbox `contains` edges into confidence-scored semantic containment via the
  `scene_refine_containment` tool. Module `mcp_server/src/rook/scene/containment_refinement.py`.

Both intelligence-layer slices are Python read-model only (zero C++), lazy/explicit, ephemeral
(graphSequence-scoped), non-destructive (bbox edges preserved + annotated), and never expand work
into baseline scene sync or the UI thread.

## 2. Verification (re-run at checkpoint time, all green)

- `cd mcp_server && python -m pytest tests/test_containment_refinement.py tests/test_scene_graph.py tests/test_exact_projection.py -q`
  → **86 passed** (32 containment + 31 scene_graph + 23 exact_projection; zero regressions).
- `python docs/rook_docs/occt-spike/live_verify_exact_projection.py` → **ALL PASS**
  (9 exact floorplate neighbors projected; dual-verified earlier by Claude + Codex).
- `python docs/rook_docs/occt-spike/live_verify_containment_refinement.py` → **ALL PASS**
  (well-formed contract, Rhino stable; contract/wiring-only).

## 3. Current caveats

- **`contains_semantic` is PROVISIONAL evidence** until a labeled threshold-calibration slice.
  The live positive rate was high (27/28 on SpatialTest), so the additive ordinal thresholds
  (`MARGIN_EPS`, `DEPTH_*`, `VOLUME_RATIO_*`) are likely permissive on real models.
- **Do NOT let rooms/zones/circulation rely on the containment confidence tiers yet** — treat
  containment as provisional input, not a stable truth source, until calibration runs.
- **OCCT 7.9.3 pin remains deferred (Task 9b)** — when picked up, use a SEPARATE OCCT
  worktree/build dir; never switch the shared `C:/Users/aryan/source/repos/OCCT` checkout off the
  verified V8_0_0. See `docs/rook_docs/occt-build.md`.
- **`rhino_vision_presentation` targeting-gate drift is pre-existing branch drift from `main`**
  (classified there via merged #254; this branch forked before it). `test_every_exposed_tool_has_policy_entry`
  fails ONLY on that tool — NOT on `scene_exact_neighbors` / `scene_refine_containment`. Resolves on
  rebase/merge with main; do NOT duplicate #254's fix here.

## 4. Recommended return slice

**Threshold Calibration v1** — tune and validate the containment verdict thresholds against
**labeled positive/negative containment examples**, preferably **BIM/Revit-derived fixtures**
(which is exactly what the upcoming RookBIM export work can produce). Calibration unblocks
downstream reliance on `contains_semantic` confidence tiers (rooms/zones/circulation).

## 5. Read order on return

1. `docs/rook_docs/2026-06-16-spatial-intelligence-pivot-checkpoint.md` (this doc)
2. `docs/rook_docs/2026-06-14-spatial-graph-projection-design.md` (design direction; §5 layers,
   §6 IFC ontology, §7 forks A–G, §8 sequencing — top banner now reflects paused/partial state)
3. Exact Adjacency Projection — spec `docs/superpowers/specs/2026-06-16-exact-adjacency-projection-v1-design.md`
   + plan `docs/superpowers/plans/2026-06-16-exact-adjacency-projection-v1.md`
4. Semantic Containment Refinement — spec `docs/superpowers/specs/2026-06-16-semantic-containment-refinement-v1-design.md`
   + plan `docs/superpowers/plans/2026-06-16-semantic-containment-refinement-v1.md`

Memory topics: `project_spatial_intelligence_topology`, `project_exact_adjacency_projection_v1`,
`project_semantic_containment_refinement_v1`.

## 6. Pivot note (what we're doing instead)

- Next work is **RookBIM: Revit→Rhino Geometry Export / Calibration Fixture Export.**
- **Goal:** export Revit geometry PLUS stable labels/sidecars (correlating Rhino geometry imported
  from Revit with the data imported from Revit) for later use as labeled calibration fixtures.
- **Keep it SEPARATE from the Rhino spatial-intelligence runtime** — it is a data-gathering /
  fixture-export track, not a change to the read-model engines or scene-graph runtime. The
  fixtures it produces feed Threshold Calibration v1 on return.
