# OCCT adjacency test fixtures (STEP oracle)

These per-object `.stp` files are the **offline test oracle** for the
`OcctAdjacencyTests` target — an independent ground truth (kernel-independent:
Rhino writes STEP, OCCT reads it) used to validate the new `ON_Brep`→`TopoDS`
direct converter and the `Common().Area` kernel.

**They are NOT a runtime artifact.** Production never exports STEP — the shipped
adjacency engine uses the in-process direct converter (no disk, no STEP toolkits in
the `.rhp`). See `docs/superpowers/specs/2026-06-15-occt-adjacency-engine-design.md`
§1 invariant ("no STEP exporter in the runtime adjacency path"). STEP is the
calibration reference for the converter, used during development only.

**The `.stp` files are gitignored** (user geometry — see `.gitignore`). This README is
the committed record of what they are and how to regenerate them.

## Source

All exported from `SpatialTest.3dm (a local test model)` (units = **inches**;
STEP export writes **millimeters**, so model-units² × 645.16 = mm² when comparing
the direct converter (model units) against a STEP-read area).

## Regeneration

With Rhino open on `SpatialTest.3dm`, export each object by GUID via the Rook
`rhino_export` MCP route (typed; never curl), one object per file:

```
rhino_export(ids=["<full-guid>"], path="<this-dir>/<8char>.stp")
```

(Do NOT script the native STEP command in a way that can pop a modal dialog; the
typed `rhino_export` route is the safe path.)

## Fixtures

| File | Full GUID | Layer | Role | Total surface area (in², measured) |
|------|-----------|-------|------|-----------------------------------|
| `71065f57.stp` | `71065f57-ee93-4af5-8a67-9aa1c4e88302` | A-WALL | wall (primary planar fixture; wall×wall pair) | 668736.18 |
| `08d4dedf.stp` | `08d4dedf-1387-453a-9938-7f3ab516b8ac` | A5_PARTS_dwg::05_Slabs_Trim | **open floorplate** — Gate-4 engine was blind here (0 edges); OCCT must recover its abutments | 366883.73 |
| `5c12cc83.stp` | `5c12cc83-5fe3-4f2c-9fca-c0575c9f5dd3` | …06_Triage_Mode_B | floorplate abutment (Triage, ~5440 in² shared) | — |
| `be0ca730.stp` | `be0ca730-f3e9-4b41-a5bf-6b3848607b14` | …06_Triage_Mode_B | floorplate abutment (Triage, ~5423 in² shared) | — |
| `7e80db98.stp` | `7e80db98-d133-4a05-b9fe-ee6d37d9069d` | I-WALL | floorplate abutment (I-WALL, ~1040 in² shared) | — |
| `26b2c012.stp` | `26b2c012-24cf-4656-9e48-8083dc072cad` | I-WALL | floorplate abutment (I-WALL, ~1055 in² shared) | — |
| `7d55840d.stp` | `7d55840d-2516-4a78-9c7d-3a10152756b1` | A-WALL | **curved wall** — exercises rational/curved trims in the converter | 62626.77 |
| `502898fc.stp` | `502898fc-75f3-4d59-bddf-cc966a942795` | I-WALL | 1.69 in² sliver graze (real small contact; areaTol policy case) | — |

## Expected results (from the Spike-A campaign; the test bars)

- **Converter fidelity (Task 4–5):** direct-converter total surface area of an object
  matches its STEP-oracle total surface area within 1e-4 relative (compare in mm²:
  model-in² × 645.16). Headline: wall `71065f57` ≈ 668736.18 in² (≈ 4.314e8 mm²);
  curved wall `7d55840d` ≈ 62626.77 in².
- **Engine adjacency (Task 6 + Task 10):** wall×wall shared face = **18651.672 in²**
  (= 12,033,312.7 mm²). Open floorplate `08d4dedf` recovers 5 confirmed abutments:
  A-WALL `71065f57` (~3312 in²), Triage `5c12cc83`/`be0ca730` (~5440/5423), I-WALL
  `7e80db98`/`26b2c012` (~1040/1055), plus the `502898fc` sliver (~1.69 in²).
