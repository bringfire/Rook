# Gate 4 — Exact Planar Adjacency: Live-Rhino Smoke Results

> **⚠ Extraction note (Slice A, `feature/occt-adjacency-engine`):** These are smoke results for the
> **superseded Gate-4 Clipper2 planar engine**, retained as historical acceptance-case evidence. The
> Clipper2 code these results exercised is **not present on this OCCT extraction branch** (archived
> on `feature/spatial-intelligence`); the shipping engine is OCCT-only, and its live verification is
> `docs/rook_docs/occt-spike/live_verify_occt_adjacency.py`.

**Date:** 2026-06-14
**Branch:** `feature/spatial-intelligence` (worktree `rook-spatial`)
**Plugin build:** Release `RookNative.rhp` from this branch, deployed and loaded
(Rhino started 13:06 after the 12:47 deploy; native server on port 63762).
**Method:** route exercised over HTTP from Python (`urllib`, not curl — security-software
constraint) against the live native server; fixtures built via the Rook MCP geometry tools.

Closes Task 10 of `docs/superpowers/plans/2026-06-14-gate4-exact-adjacency.md`.

## Result: ALL spec §11 cases PASS

Fixtures (closed box solids unless noted), all on the Default layer, deleted after the run:
- `smoke_wallA` box [0,0,0]→[0.2,4,3]
- `smoke_wallB` box [0.2,0,0]→[0.4,4,3]  (shares the x=0.2 face with A, area 4×3 = 12)
- `smoke_wallC` box [-0.2,0,0]→[0,4,3]   (shares the x=0 face with A, area 12)
- `smoke_sphere` sphere r=2 @ (100,100,100) — curved
- mesh box 2×2×2 @ (200,200,200) — mesh

| # | Case | Request | Result | Verdict |
|---|------|---------|--------|---------|
| 1 | Single shared face | `wallA` (B only present) | 1 edge `adjacent_exact` → wallB, `sharedArea=12.0`, `sourceCapability=exact_planar` | ✅ exact 12 m² |
| 2 | Multi-neighbour | `wallA` (B+C present) | 2 edges, both `sharedArea=12.0`; `candidateCount=2/2`, `capped=false` | ✅ |
| 3 | Candidate cap | `wallA, maxCandidates=1` | `capped=true`, `candidateCount=1`, `totalCandidateCount=2`, nearest kept (wallB) | ✅ over-cap = successful partial |
| 4 | `includeCoarse=false` | `wallA` | served, 2 edges | ✅ |
| 5 | `includeCoarse=true` | `wallA` | served from the same core, 2 edges; `coarseRelationship=null` (no coarse edge existed for exactly-touching bboxes) | ✅ |
| 6 | Curved object | `sphere` | `sourceCapability=coarse_fallback_exact_unsupported`, 0 edges — **no false exact** | ✅ |
| 7 | Mesh object | mesh box | `sourceCapability=unsupported_geometry`, 0 edges | ✅ |
| 8 | Cache invalidation | delete `wallC`, re-query `wallA` | `graphSequence` 5→6, stale core dropped, recomputed to 1 edge (wallB) | ✅ |

Route validation: `POST /scene/graph/adjacency/exact {}` → HTTP 400 `Missing 'objectId'`
(handler validation live). `sharedArea` is exact (12.0, not approximate) on real Brep solids,
confirming the canonicalPlane fold + opposing-normal gate + Clipper2 net-area path end-to-end.

No fixes required — the implementation passed the live smoke as-is.

## Carried-forward v1 notes (validated or to watch)

- **`IsSolid()` orientation gate (Task 7):** the smoke used closed solids (boxes/sphere),
  which are eligible — the happy path is confirmed. NOT exercised: walls/slabs modeled as
  **open surfaces / non-solid polysurfaces**, which by design roll up to
  `coarse_fallback_exact_unsupported`. If real project geometry is frequently non-solid,
  relaxing the orientation gate (per-face consistency rather than whole-body `IsSolid`) is the
  first follow-up to prioritise. Confirmed behaviour, known limitation.
- **Coarse decoration:** `coarseRelationship` was `null` here because the coarse bbox pass
  records no edge for exactly-touching (zero-overlap) bboxes. Decoration plumbing is correct;
  it simply had nothing to attach. Worth a richer real-model check later.
- **Proximity radius (Task 5):** candidates surfaced correctly for face-flush 0.2 m-thick
  walls; no missed neighbours at this scale. Large-flush-face / thin-object edge cases remain
  a Gate-5 scale-validation item.
- **No MCP wrapper (v1, out of scope):** the route was exercised via direct HTTP. A thin MCP
  tool wrapping the route (through the existing bridge) is the natural follow-up so agents can
  drive it without raw HTTP.
