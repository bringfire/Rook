# Tutorial Extraction Report
Generated: 2026-02-22 (final — all levels complete)

## Summary

All four extraction scripts ran successfully. Full course coverage achieved.

| Level | Notes | Created | Updated | Skipped | Links Created | Status |
|-------|-------|---------|---------|---------|---------------|--------|
| Beginner | 26 | 26 | - | - | 253 | **Complete** (prior session) |
| Intermediate | 28 | 0 | 25 | 3 | 15 | **Complete** |
| Professional | 14 | 0 | 14 | 0 | 4 | **Complete** |
| Expert | 30 | 30 | 0 | 0 | 150 | **Complete** |
| **Total** | **98** | **56** | **39** | **3** | **422** | |

## Beginner (COMPLETE - prior session)
- **Images**: 26 (Lessons 1-3: Data Fundamentals, Curves/Tangents/Data Trees, Applied Projects)
- **Script**: `run_extract_beginner_tutorials.py`
- **Notes created**: 26
- **Links**: 253
- **Verified**: All queries pass

## Intermediate (COMPLETE)
- **Images**: 28 (Lessons 3-5: Attraction Algorithms, Surface Creation/List Ops, List Manipulation/Panelization)
- **Script**: `run_extract_intermediate_tutorials.py`
- **Result**: 25 updated, 3 unchanged (skipped), 0 new
- **Links created this run**: 15
- **Notes updated**: 3-10 through 5-6 (attractor patterns, boolean filtering, dispatch, image sampler, sub list, weave vs merge, map to surface, diamond panel manipulation)
- **No errors**

## Professional (COMPLETE)
- **Images**: 14 (Lessons 6-7: Advanced Data Tree/Structural, Advanced List Ops/Planes/Orient/Isotrim)
- **Script**: `run_extract_professional_tutorials.py`
- **Result**: 14 updated, 0 unchanged, 0 new
- **Links created this run**: 4
- **Notes updated**: 6-1 through 7-7 (shift list, gene pool shift, ruled surface vs loft, partition list, set operations, plane construction, orient/transform, isotrim/box morph)
- **No errors**

## Expert (COMPLETE)
- **Images**: 30 (Lessons 7-10: Advanced Mesh/Voronoi, Mesh Ops/Digital Fabrication, Path Mapper/Volumetric, Applied Expert Projects)
- **Script**: `run_extract_expert_tutorials.py`
- **Result**: 30 created, 0 updated, 0 skipped
- **Links created this run**: 150
- **Topics covered**:
  - Lesson 7 (7-8 to 7-11): Box Morph + MultiPipe, Populate 3D, Construct Mesh, Voronoi + Subdivision
  - Lesson 8 (8-1 to 8-10): Mesh construction, TriRemesh, Weaverbird (Snub, Fan, Picture Frame, Thicken, Catmull Clark), Image Sampler UV coloring, Graph Mapper displacement
  - Lesson 9 (9-1 to 9-6): Random displacement, attractor-driven facades, Path Mapper modulus/division expressions, Curve To Volume
  - Lesson 10 (10-1 to 10-10): Space Frame, Undulating Facades, Parametric Tower, Field Lines, Anemone Loop fractal, Flow component, Peacock Triangle Panels, Solid Difference, Sift Pattern weaving
- **Third-party plugins referenced**: Weaverbird, Peacock, Anemone
- **No errors**

### How Expert images were processed
The Expert images range from 3.1 Mpx to 174 Mpx (10-6.jpg: 27773x6263). Reading them directly would crash the session. Solution:
1. PIL resize script created downsized copies (max 4000px longest edge) + horizontal tiles for mega-images (>12000px)
2. 8 subagents read 1-5 images each, returning structured Python dicts
3. All 30 lesson dicts compiled into the extraction script
4. Temp images stored in `mcp_server/.tmp_expert_images/` (can be deleted)

## Store Health After All Extractions

```
Total notes:        1,207
  - component:        922
  - recipe:           121
  - teaching:         163 (65 from Unit files + 98 tutorials)
  - struggle:           1

Tutorial notes:      98 (26 beginner + 28 intermediate + 14 professional + 30 expert)
Linked notes:     1,164 / 1,207 (96.4%)
Total links:      9,116
Orphans:             43 (all component notes with niche names — no teaching/recipe/tutorial orphans)
Missing:              0
Store consistent:     YES
```

## Technical Notes

### Why "updated" not "created" for Intermediate/Professional
The previous session (that crashed) had already run partial extractions — all 68 beginner/intermediate/professional tutorial JSON files existed on disk. This run updated 39 of them because `brief` or `context` fields had been refined in the scripts since then. 3 intermediate notes were completely unchanged and skipped.

### Save method difference
- Beginner script uses `store.save()` (older API)
- Intermediate + Professional + Expert scripts use `store.save_all()` (newer API)
- Both work correctly. The `save_all()` method writes all notes + rebuilds the index.

### What killed the previous session
The previous session attempted to read a large tutorial image via the Read tool. The image was too large for the context window and the session died. **Lesson**: Never read tutorial images directly — resize/tile first, delegate to subagents.

### Orphan analysis
43 orphan notes are all component notes with niche names (Collide2d, Shortest Walk, Rod, Read CSV, etc.) that have no keyword overlap with any other note. These are expected — they represent uncommon components that haven't appeared in any recipe or tutorial yet. All 98 tutorial notes and 121 recipe notes are fully linked.

## Next Steps

1. **Optional**: Run `run_batch_evolution.py --relink` to rebuild ALL links deterministically across the full 1,207-note store (current links were built incrementally per-extraction).
2. **Optional**: Kill and restart MCP Python process to pick up the new notes in live queries.
3. **Optional**: Delete `mcp_server/.tmp_expert_images/` temp directory (82 resized/tiled images, no longer needed).
