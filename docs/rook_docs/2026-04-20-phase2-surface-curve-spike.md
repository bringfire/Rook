# Phase 2 Surface / Curve Extensions — Empirical Spike

**Date:** 2026-04-20
**Stage:** scope pass (pre-plan, pre-code)
**Branch:** `fix/phase2-surface-curve-spike` (Rook)
**Basis:**
- `rook_docs/2026-04-15-typed-route-gap-analysis.md` — §Category 4 (Curve Creation) + §Category 5 (Advanced Surface Operations) + `## Decision Record`
- `rook_docs/2026-04-17-typed-route-phase1-plan.md` — Worked Example: Pipe (substrate decision rhythm)
- `rook_docs/2026-04-17-typed-route-phase1-spike.md` — fallback-matrix rhythm to mirror
- `rook_docs/work-queue.md` — `Now` section (resume_entry_point)

**Status:** Live-Rhino `/command` probe **run 2026-04-20**. Results folded into
the spike matrix below (Fallback column). Pattern matches Phase 1 cleanly:
**5 urgent / 2 useful** of 7 live candidates (OffsetSrf dropped — already
shipped). No surprises that reorder the PR sequence; the campaign proceeds
as drafted.

**Gate posture — the live probe did NOT gate the plan doc.** The substrate
decision is API-reachability-driven (see §Substrate Fit), so the plan doc is
drafted on the codebase-side probe. The live probe is a PR-prioritization
confirmation — it verified the tentative `urgent`/`useful` labels. Both
`useful`-labeled candidates (EdgeSrf, FilletSrf) have known contract-quality
reasons to still prefer typed routes (opaque response signal for EdgeSrf;
no radius/edge control for FilletSrf), so neither is demoted from the
campaign on the strength of its scripted form working.

---

## Purpose of This Spike

The work-queue `Now` entry describes a pure-inheritance campaign:
> 6 surface ops (Patch / NetworkSrf / EdgeSrf / BlendSrf / FilletSrf / OffsetSrf) +
> 2 curve ops (curve blend, curve boolean). All extend existing handlers on the
> Phase 1 Pipe's `managed-bridge (reuse)` substrate via `CreateGeometry`.

That premise deserves empirical verification before a plan is written, because
pure inheritance does not apply by default:

1. **OffsetSrf may already be shipped.** `src/RookNative/Handlers/OffsetBrepHandler.cpp`
   implements `/offset/brep` via the native global function `RhinoOffsetBrep`
   (direct-sdk native, not managed-bridge). Category 5's "OffsetSrf" bullet
   overlaps with what that route already covers.
2. **The 2 curve ops are not obviously homed on SurfaceHandler's substrate.**
   Category 4 names `/curve/blend` and `/curve/boolean`. Existing `/curve/*`
   routes all live in `CurvesHandler.cpp` on the direct-sdk substrate. The
   Phase 1 plan's managed-bridge reuse pattern routes through the
   `CreateGeometry` callback — that callback already handles curve *creation*
   types (INTERPOLATED_CURVE, CONTROL_POINT_CURVE), so reuse is plausible,
   but the namespace mix (`/curve/*` routes in CurvesHandler today are direct-sdk,
   vs these two new ones which would be managed-bridge) needs to be called out
   explicitly.
3. **Two of the six surface ops (BlendSrf, FilletSrf) have picker-heavy inputs.**
   Rhino's command UI for BlendSrf and FilletSrf is edge/face/UV-point-picker
   driven. Programmatic API calls require structured input for edge and UV-point
   selection that doesn't exist anywhere else in the codebase today. That is a
   real scaffolding question, not a trivial schema decision.

The spike clarifies those three questions before any plan work.

---

## 8-Row Spike Matrix

Scope candidates from the work-queue `Now` entry + gap-analysis §Category 4 + §5.
**Cardinality column** is the response-shape cardinality per Rule 5 (singular →
bare ObjectSnapshot; plural → `{objects: [...]}`).
**Fallback** is live-Rhino scripted `/command` behavior — pending empirical
probe (Phase 1 spike script template forked to the Phase 2 namespace).

| # | Candidate | RhinoCommon API | Native C++ SDK affordance? | Existing Rook implementation? | Cardinality | API surface complexity | Fallback (live probe) | Conclusion label (tentative) |
|---|-----------|-----------------|----------------------------|-------------------------------|-------------|------------------------|-----------------------|------------------------------|
| 1 | **EdgeSrf** | `Brep.CreateEdgeSurface(curves)` or `NurbsSurface.CreateNetworkSurface(curves, 2, …)` for 2-curve → surface | **No** — no `RhinoEdgeSrf` in native SDK | None | Singular (one Brep from 2–4 curves) | **Simple** — 2–4 curves in, 1 surface out | **cleanly** — 3 lines triangle → 1 brep created | `typed route useful` — scripted form works but typed route still wins on structured response (type/layer/bbox for downstream chaining) |
| 2 | **BlendCurves** | `Curve.CreateBlendCurve(curveA, curveB, continuity)` [overload 1]; `(…, continuity, bulgeA, bulgeB)` [overload 2]; `(c0, t0, rev0, cont0, c1, t1, rev1, cont1)` [overload 3 full-control]. **Corrected 2026-04-20 via empirical introspection** — earlier memo draft specced a 6-arg `(c1, rev1, cont1, c2, rev2, cont2)` signature that does NOT exist | **No** — no native C++ factory | None | Singular (one Curve) | **Simple** — overload 1 takes 2 curves + continuity; reverse/bulge/t-on-curve are deferred (§plan-doc Non-goals + BlendCurves Explicit rejections) | **stalled** — `_-BlendCrv` rejects `_SelId`; options whitelist is `bulge / continuity / reverse` only (command wants interactive curve-end picks) | `typed route urgent` |
| 3 | **CurveBoolean** | `Curve.CreateBooleanUnion / CreateBooleanDifference / CreateBooleanIntersection` (+ `CreateBooleanRegions` for point-picked region form) | **No** — no native C++ factory | None in handler layer; `Brep.CreateBooleanUnion` *is* used elsewhere (`GumballExtrudeHandler.cs:101`) but that is brep, not curve | **Plural** (Curve[]) | **Medium** — overload choice: legacy `CreateBooleanX(curves)` vs region form `CreateBooleanRegions(curves, plane, points, combine, tol)` | **stalled** — `_-CurveBoolean` rejects `_SelId`; options whitelist is `_AllRegions / _CombineRegions / _None` (toggle flags, not curve picks) | `typed route urgent` |
| 4 | **Patch** | `Brep.CreatePatch(geometry, startSurface, uSpans, vSpans, trim, tangency, pointSpacing, flexibility, surfacePull, fixEdges, tol)` | **No** — no native C++ factory | None | Singular (one Brep) | **High** — ≥10 knobs in Rhino's `_Patch` command (Spans, Flexibility, PointSpacing, StartingSurface, PullCurves, PreserveEdges, AdjustTangency); need a safe core subset contract | **stalled** — `_-Patch` rejects `_SelId`; options whitelist is `command_line_mode / surface_parameters` only | `typed route urgent` |
| 5 | **NetworkSrf** | `NurbsSurface.CreateNetworkSurface(curves, continuity, edgeTol, interiorTol, angleTol, out error)` OR `CreateNetworkSurface(uCurves, vCurves, …)` with explicit directions | **No** — no native C++ factory | None | Singular (one Surface → Brep wrapper) | **Medium** — overload choice: auto-detect U/V from single curve list vs explicit `uCurves`/`vCurves` separation. 3 tolerance values (edge/interior/angle). | **stalled** — `_-NetworkSrf` rejects `_SelId`; options whitelist is `EdgeContinuity / InteriorContinuity / Tolerance / TrimAndSplit` only | `typed route urgent` |
| 6 | **BlendSrf** | `Brep.CreateBlendSurface(face1, edge1, t1Domain, rev1, cont1, face2, edge2, t2Domain, rev2, cont2)` | **No** — no native C++ factory | None | **Plural** (Brep[]) | **Very High** — inputs are face+edge indices + parameter domain + continuity + reverse flags. Requires an *edge-selection contract* that doesn't exist anywhere in the codebase. | **ambiguous** — `_-BlendSrf _SelId ... _SelId ... _Enter` returned `executed=true, objectsCreated=0` (silent no-op; same pattern as Phase 1 Sweep2). Command accepts the syntax but builds nothing without edge-picker input. | `typed route urgent` BUT defer: **scaffolding gap** (needs structured edge-identification schema) |
| 7 | **FilletSrf** | `Brep.CreateFilletSurface(face1, uv1, face2, uv2, radius, extend, tol)` or `Surface.CreateRollingBallFillet(face1, face2, radius, tol)` | **No** — no native C++ factory | None (note: `fillet_edge` already routes to `/fillet` via `FilletChamferHandler`, which is a *different* operation — fillets edges of ONE polysurface, not between TWO surfaces) | **Plural** (Brep[]) | **Very High** — inputs are face index + UV point + radius. Same UV-point schema gap as BlendSrf. | **cleanly** — `_-FilletSrf _SelId ... _SelId ... _Enter` on two perpendicular planar surfaces meeting at a shared edge produced **3 breps** (fillet surface + 2 trimmed inputs) with default radius. **Response is opaque** — no structured per-object role. | `typed route useful` BUT still defer from this campaign: scaffolding gap for radius + edge-position control still applies (scripted form is untrimmed default-radius; typed route contract needs explicit radius + UV-point or edge-auto-detection heuristic) |
| 8 | **OffsetSrf** | `Brep.CreateOffsetBrep(brep, dist, solid, extend, tol)` | **Yes** — native global `RhinoOffsetBrep()` | **ALREADY SHIPPED** at `src/RookNative/Handlers/OffsetBrepHandler.cpp` as `/offset/brep`, plus `offset_brep` in `intent_runtime.py:593` + MCP tool `rhino_offset_brep` | Singular | N/A — shipped | N/A (not probed) | **DROP from Phase 2 scope** — already covered. (Gap-analysis Category 5 OffsetSrf row is stale; the existing `/offset/brep` route subsumes it.) |

### Substrate column (per Rule 6 — reuse vs add)

| # | Candidate | Substrate | Reuses what? | ABI bump? |
|---|-----------|-----------|--------------|-----------|
| 1 | EdgeSrf | `managed-bridge (reuse)` via `CreateGeometry` — new type `"EDGE_SRF"` | `NativeGhBridgeRegistrar.CreateGeometry` callback at line 107 | **No** |
| 2 | BlendCrv | `managed-bridge (reuse)` via `CreateGeometry` — new type `"BLEND_CRV"` | same | **No** |
| 3 | CurveBoolean | `managed-bridge (reuse)` via `CreateGeometry` — new type `"CURVE_BOOLEAN"`; plural-contract route — adds a case to the `strictAttributes`-gated plural dispatch in `CreateHandler.cs` alongside LOFT/SWEEP1/SWEEP2 | same | **No** |
| 4 | Patch | `managed-bridge (reuse)` via `CreateGeometry` — new type `"PATCH"` | same | **No** |
| 5 | NetworkSrf | `managed-bridge (reuse)` via `CreateGeometry` — new type `"NETWORK_SRF"` | same | **No** |
| 6 | BlendSrf | `managed-bridge (reuse)` via `CreateGeometry` — new type `"BLEND_SRF"`, plural-contract | same | **No** — BUT requires upstream edge-identification schema scaffolding before the handler is usable |
| 7 | FilletSrf | `managed-bridge (reuse)` via `CreateGeometry` — new type `"FILLET_SRF"`, plural-contract | same | **No** — BUT requires upstream UV-point-on-face schema scaffolding |
| 8 | OffsetSrf | N/A (already shipped on direct-sdk native substrate) | — | — |

**Answer to work-queue Q3 ("does managed-bridge reuse still hold?"):** Substrate
fit is plausible for all 7 remaining candidates — every route is a new `type`
string added to the existing `CreateGeometry` dispatcher, no ABI bump. **But
"reuse" here is narrower than in Phase 1:**
- Phase 1 Pipe reused a live factory (`CreateHandler.CreatePipe` already existed
  at `CreateHandler.cs:776`). Only wiring was new.
- Phase 2 reuses the **bridge seam** (the `CreateGeometry` callback + `type`
  dispatcher + `_strictAttributes` gating), NOT route-specific managed code.
  None of PATCH / NETWORK_SRF / EDGE_SRF / BLEND_CRV / CURVE_BOOLEAN have any
  managed implementation today (`CreateHandler.cs:150` singular switch and
  `:134` plural switch — verified). Each route adds net-new `Brep.CreatePatch`,
  `NurbsSurface.CreateNetworkSurface`, etc. call sites in
  `CreateHandler.cs`.

**Scope statement (corrected to match PR plan below):** substrate fit plausible
for 7 candidates, but only **5 endpoints / 7 intent keys are shippable in this
campaign** — EdgeSrf, BlendCurves, Patch, NetworkSrf, CurveBoolean (the
CurveBoolean endpoint carries three intent keys per the per-operation split
discussed in §Campaign exit criterion). BlendSrf and FilletSrf are deferred
because their input schemas require new geometric primitives (edge-on-face,
UV-point-on-face) that do not exist anywhere in the contract today.

**Caveats on "pure inheritance":**
- **Namespace mix for curve ops.** `/curve/blend` and `/curve/boolean` route
  names live under `/curve/*`, but the substrate (managed-bridge reuse via
  `CreateGeometry` in `CreateHandler.cs`) is the same as the `/surface/*` family.
  Existing `CurvesHandler.cpp` is 100% direct-sdk today. Two options:
  - **Option A:** Add these two routes to `CurvesHandler.cpp`, carrying the
    managed-bridge helpers alongside the existing direct-sdk routes. First
    mixed-substrate handler in the codebase; substrate documented per-route.
  - **Option B:** Add these routes to `SurfaceHandler.cpp` since the substrate
    lives there; route name `/curve/*` reads weird in a "SurfaceHandler" file.
  - **Recommendation: Option A.** The handler file is a substrate-agnostic
    namespace bucket; mixing substrates in one file is lower cost than
    routing `/curve/*` through a file called `SurfaceHandler.cpp`. The
    substrate-per-route declaration in handler-local comments (Rule 6) already
    handles the documentation requirement.
- **Plural dispatch alignment — NOT pure inheritance for CurveBoolean.**
  CurveBoolean is plural (like LOFT/SWEEP), but the existing plural path is
  `Brep[]`-only:
  - `CreateHandler.cs:134` plural dispatch table only knows
    `LOFT` / `SWEEP1` / `SWEEP2`.
  - The shared plural insert helper `InsertBrepsAsPluralResponse` at
    `CreateHandler.cs:1398` is strictly `Brep[]`-shaped — calls
    `doc.Objects.AddBrep(brep, attributes)` per item.
  - Adding `CURVE_BOOLEAN` to the plural dispatch therefore requires one of:
    1. A parallel curve-specific helper
       (`InsertCurvesAsPluralResponse` using `doc.Objects.AddCurve`), or
    2. Generalizing `InsertBrepsAsPluralResponse` to dispatch per-class on
       `GeometryBase` — either `AddBrep` or `AddCurve` per item, with
       per-item atomicity preserved.
  - Either path is net-new code — not a wiring-only reuse.
  - **Recommendation:** Option 1 (parallel helper) for PR-4. Cleaner than
    generalizing a helper that is well-understood in its current Brep-only
    form, and keeps the Loft/Sweep call sites untouched while the new curve
    path proves out. Generalization can be a follow-up hygiene pass if a
    third geometry class ever joins the plural contract.
  - **Implementation risk for PR-4:** higher than PRs 1–3 of this campaign.
    Flag this explicitly in the plan doc's PR-4 execution block; expect a
    scope-pass round on the helper choice before implementation.
- **`CreateGeometry` return-geometry-class fit.** Existing types in the
  singular-geometry switch at `CreateHandler.cs:150` all return `GeometryBase?`.
  `Brep.CreatePatch`, `CreateEdgeSurface`, `CreateBlendCurve` all return a
  `GeometryBase` subclass (`Brep`, `Curve`). Clean fit.
  `NurbsSurface.CreateNetworkSurface` returns `NurbsSurface` (a `Surface`/`GeometryBase`)
  — wrap in `Brep.CreateFromSurface(nurbsSurface)` before insert so that the
  response-shape matches the sibling surface routes. **Flag for review:** decide
  whether the document insert should be the raw surface or a brep-wrapped
  surface; existing Phase 1 surface creators all insert breps, so consistency
  argues brep-wrapped. Record in plan doc.

---

## Substrate Fit, Contract Risks, Fidelity Limits (per route)

### EdgeSrf — *ship first*

- **API:** `Brep.CreateEdgeSurface(IEnumerable<Curve> curves)` — returns `Brep?`
  for 2–4 curves forming a boundary.
- **Schema (candidate):** `{curveIds: [uuid] (2..4), name?, layer?, color?, visible?}`.
- **Contract risk — boundary closure:** Factory returns `null` if curves don't form
  a valid boundary. → `operation_failed`. Match Pipe-style error taxonomy.
- **Contract risk — count bounds:** API accepts 2, 3, or 4 curves; reject outside
  that range on worker thread as `invalid_input` (route-specific code
  `invalid_curve_count`).
- **Fidelity limit:** Input curves need not be physically touching — factory
  best-fits. Contract does NOT promise "curves must meet at endpoints"; caller
  may pass disconnected curves and get operation_failed at UI-thread time.
- **Cardinality:** Singular (returns single Brep). Bare `ObjectSnapshot`.

### BlendCrv — *ship first (with EdgeSrf)*

- **API (corrected 2026-04-20 via empirical introspection of
  `Curve.CreateBlendCurve` overload set):**
  1. `Curve.CreateBlendCurve(Curve curveA, Curve curveB, BlendContinuity continuity)` — simplest. Returns `Curve?`. **PR-1 uses this overload.**
  2. `Curve.CreateBlendCurve(Curve curveA, Curve curveB, BlendContinuity continuity, double bulgeA, double bulgeB)` — simple + bulge doubles. Deferred.
  3. `Curve.CreateBlendCurve(Curve c0, double t0, bool reverse0, BlendContinuity continuity0, Curve c1, double t1, bool reverse1, BlendContinuity continuity1)` — full control: parameter-on-curve + reverse flags + asymmetric continuity. Deferred.
  - `BlendContinuity` enum: `Position` (G0), `Tangency` (G1), `Curvature` (G2).
  - **Earlier drafts of this memo documented a 6-arg `(c1, rev1, cont1, c2, rev2, cont2)` signature that does NOT exist in RhinoCommon.** Corrected in the spike matrix row above and here.
- **Schema (PR-1):** `{curve1Id: uuid, curve2Id: uuid, continuity?: "Position"|"Tangency"|"Curvature" (default "Tangency"), name?, layer?, color?, visible?}`.
- **Contract risk — continuity enum:** 3 values only; reject others as
  `invalid_continuity` on worker thread.
- **Contract risk — empirically permissive factory.** Probing 2026-04-20
  against overload 1 with coincident curves, zero-length+valid, and
  degenerate 2-point NURBS — all produced valid non-null blends. PR-1
  ships with `test_factory_permissive_smoke` per the Common Plan
  amendment in the Phase 1 plan doc (and mirrored in the Phase 2
  plan-doc Acceptance Gate). No `operation_failed` test required for
  BlendCurves.
- **Fidelity limit:** Overload 1 picks blend endpoints automatically
  (default-end selection). Caller cannot specify "which end" without
  moving to overload 3's `t`/`reverse` params — deferred. If a real
  workflow needs end-picking, the follow-up PR can extend to overload
  3; no-op for PR-1.
- **Deferred from PR-1 (tracked in plan-doc Non-goals):**
  - Overload 2 `bulge` controls
  - Overload 3 `t` + `reverse` params
  - Asymmetric per-end continuity (`continuity0` vs `continuity1`)
- **Cardinality:** Singular.

### CurveBoolean — *PR after EdgeSrf + BlendCrv prove the pattern; carries a helper-scope risk*

- **API choice:** Two distinct sub-operations under the same command name.
  - *Simple booleans:* `Curve.CreateBooleanUnion(curves, tol)`,
    `CreateBooleanDifference(curveA, curveB, tol)`,
    `CreateBooleanIntersection(curveA, curveB, tol)`. Return `Curve[]?`.
  - *Region form:* `Curve.CreateBooleanRegions(curves, plane, regionPoints, combineRegions, tol)` — returns `CurveBooleanRegions` (richer type with per-region metadata); the Rhino `_CurveBoolean` command uses this form.
- **Schema choice:** Start with simple booleans only (`{operation: "union"|"difference"|"intersection", curveIds: [uuid], tolerance?}`). Defer region form to a follow-up PR once the simpler form ships.
- **Contract risk — input arity per operation:** `union` takes `curves` (any count ≥ 2); `difference`/`intersection` take exactly `curveA` + `curveB` (or `curveA` + `curvesB: [uuid]`). Handler must branch on `operation` for the arity check.
- **Contract risk — planar requirement:** The boolean operations require all curves to lie in a common plane. RhinoCommon may tolerate slight out-of-plane curves; document the constraint and classify non-planar input as `operation_failed`.
- **Contract risk — NEW plural helper required.** Existing plural path
  (`CreateHandler.cs:1398` `InsertBrepsAsPluralResponse`) is `Brep[]`-only
  via `doc.Objects.AddBrep`. CurveBoolean returns `Curve[]`. PR-4 must add a
  curve-specific `InsertCurvesAsPluralResponse` helper (using
  `doc.Objects.AddCurve`) and wire a new `CURVE_BOOLEAN` case into the
  `strictAttributes`-gated plural dispatch at `CreateHandler.cs:134` that
  routes through that helper. See "Plural dispatch alignment — NOT pure
  inheritance" note above. **This is the single-biggest scope item in the
  campaign; expect a dedicated scope-pass round on PR-4 before
  implementation.**
- **Fidelity limit:** Simple boolean form can't select specific regions by point picker (the `_CurveBoolean` command's "click inside the region" UX). Region form is the only way to capture that; deferred.
- **Cardinality:** Plural (returns `Curve[]`).

### Patch — *third shipping PR; bigger API surface*

- **API:** `Brep.CreatePatch(IEnumerable<GeometryBase> geometry, Surface startSurface, int uSpans, int vSpans, bool trim, bool tangency, double pointSpacing, double flexibility, double surfacePull, bool[] fixEdges, double tolerance)` — returns `Brep?`.
- **Schema (candidate, minimal safe subset):**
  ```
  {
    geometryIds: [uuid] (min 1; curves, points, or point clouds),
    startingSurfaceId?: uuid,
    uSpans?: int (default 10),
    vSpans?: int (default 10),
    flexibility?: number (default 1.0; higher = more flexible),
    surfacePull?: number (default 1.0),
    tolerance?: number (default doc.ModelAbsoluteTolerance),
    name?, layer?, color?, visible?
  }
  ```
  Deliberately omitted (defer): `trim`, `tangency` (bool flags), `pointSpacing`,
  `fixEdges` (4-element bool[] per starting-surface edge). Adding these is cheap
  once the base contract is in.
- **Contract risk — input geometry class:** Patch accepts curves AND points AND
  point clouds as inputs. The handler must resolve each input's geometry class
  and build a heterogeneous list for the factory. Schema treats them all as
  `geometryIds` without discrimination; classify rejected inputs (e.g., brep
  input) as `invalid_input`.
- **Contract risk — starting surface:** Optional. If provided, API uses it as
  the seed. If omitted, API auto-creates a planar fit seed.
- **Fidelity limit:** The omitted knobs matter in real workflows — `trim` and
  `tangency` flags in particular. Ship minimum viable now, extend later with
  explicit workflow evidence.
- **Cardinality:** Singular.

### NetworkSrf — *fourth shipping PR (or bundled with Patch)*

- **API choice:**
  - *Auto-detect direction:* `NurbsSurface.CreateNetworkSurface(IEnumerable<Curve> curves, int continuity, double edgeTol, double interiorTol, double angleTol, out int error)` — returns `NurbsSurface?`.
  - *Explicit direction:* `NurbsSurface.CreateNetworkSurface(IEnumerable<Curve> uCurves, int uContinuity, IEnumerable<Curve> vCurves, int vContinuity, double edgeTol, double interiorTol, double angleTol, out int error)`.
- **Schema choice (candidate):**
  ```
  {
    # EITHER the auto-detect form:
    curveIds: [uuid] (min 2),
    # OR the explicit form — XOR with curveIds:
    uCurveIds: [uuid],
    vCurveIds: [uuid],
    continuity?: int in {0,1,2} (default 1 — tangent),
    edgeTolerance?: number (default doc.ModelAbsoluteTolerance),
    interiorTolerance?: number (default doc.ModelAbsoluteTolerance),
    angleTolerance?: number (default doc.ModelAngleToleranceRadians),
    name?, layer?, color?, visible?
  }
  ```
  XOR rejected as `invalid_input` per the Phase 1 pattern.
- **Contract risk — `out int error` semantics:** The API returns a specific
  error code when the surface can't be built (e.g. self-intersecting curves).
  Handler should surface the numeric code as structured `operation_failed`
  with `errorMessage` naming the cause where known.
- **Contract risk — wrap output:** Returns `NurbsSurface`. Insert as a brep
  wrapper (`Brep.CreateFromSurface(nurbsSurface)`) for response-shape parity
  with other /surface/* routes. **Flag for plan-doc review.**
- **Fidelity limit:** Auto-detect can pick wrong U/V direction on ambiguous
  networks. Explicit form is the escape hatch.
- **Cardinality:** Singular.

### BlendSrf, FilletSrf — *DEFER to Phase 3 or a follow-up campaign*

Both operations require inputs that have no schema precedent anywhere in the
Rook codebase:

- **BlendSrf:** needs structured `{brepId: uuid, faceIndex: int, edgeIndex: int, t0: float, t1: float, reverse: bool, continuity: enum}` pairs for each of two faces. That is a **new geometric primitive in the contract** (an "edge-on-face reference"), and shipping it requires:
  - A canonical schema form for "edge on face by index + parameter domain"
  - Serialization discipline across handlers (so Query routes can return this shape too, not just accept it)
  - Enough worked-example coverage (at least one other operation that uses the same schema) to prove the shape is right
- **FilletSrf:** needs `{brepId, faceIndex, u, v}` pairs (surface UV point). Same scaffolding gap — "UV point on face" is a new primitive.

**Recommendation:** explicitly defer both from the work-queue `Now` scope. Add
an entry to `Parked` with `trigger_to_revisit`:
> "When a canonical 'edge-on-face' / 'UV-point-on-face' schema shape is adopted
> elsewhere (e.g., a future `/brep/edge-intersect` or `/brep/face-project`
> route). Ship BlendSrf + FilletSrf as the second caller of that shape, not the
> inventor of it."

Not blocking — this is the clean way to close the campaign at 5 routes instead
of 7 and surface the remaining 2 as a separate scoped effort.

---

## Recommended First 2–3 Routes to Ship

Matching the Phase 1 spike rhythm ("5 urgent / 3 useful"; ship `useful` first as
worked examples, then `urgent`):

1. **EdgeSrf** — simplest plausible worked example. Mirrors Pipe's role in Phase 1.
2. **BlendCrv** — same simplicity tier; first `/curve/*` managed-bridge route; proves the cross-namespace substrate mix works.
3. **Patch** — first "big API surface" route of Category 5; validates the "safe core subset" contract pattern on a multi-knob command.

Then:

4. **NetworkSrf** — XOR schema pattern on `curveIds` vs `uCurveIds`/`vCurveIds`.
5. **CurveBoolean** — first plural-contract `/curve/*` route.

**Deferred from this campaign:** BlendSrf, FilletSrf, OffsetSrf (dropped — already shipped).

---

## Proposed PR Sequence

Four PRs, structured as Phase 1 was (worked-example first, pattern-inherited follow-ups):

| PR | Scope | Routes | Cardinality | Why this slice |
|----|-------|--------|-------------|----------------|
| **PR-1 (worked example)** | EdgeSrf + BlendCrv | `POST /surface/edge` + `POST /curve/blend` | Both singular | Two simplest routes, one per namespace (`/surface/*` and `/curve/*`). Establishes the Phase 2 Category 5/4 reuse pattern on both, with a single Codex scope pass. If bundling two proves awkward at review, split into PR-1a + PR-1b. |
| **PR-2** | Patch | `POST /surface/patch` | Singular | First big-API-surface route; proves the "safe core subset" schema approach. Standalone PR so scope review focuses on the defer-list of knobs. |
| **PR-3** | NetworkSrf | `POST /surface/network` | Singular | XOR schema between auto-detect and explicit U/V forms. Standalone because the `out int error` code mapping adds review surface. |
| **PR-4** | CurveBoolean | `POST /curve/boolean` | Plural | First `/curve/*` plural-contract route. **Carries the largest implementation risk of the campaign** — adds a new `InsertCurvesAsPluralResponse` helper (the existing `InsertBrepsAsPluralResponse` at `CreateHandler.cs:1398` is `Brep[]`-only via `AddBrep`) and extends the `strictAttributes`-gated plural dispatch at `CreateHandler.cs:134` with a `CURVE_BOOLEAN` case routing through the new helper. Expect a dedicated scope-pass round on the helper choice (parallel helper vs generalize-Brep-helper) before implementation. |
| **DEFER** | BlendSrf, FilletSrf | (not in this campaign) | — | Move to `Parked` with edge-on-face / UV-point-on-face scaffolding trigger. |
| **DROP** | OffsetSrf | (not in this campaign) | — | Already shipped as `/offset/brep`. Optional cleanup: update gap-analysis Category 5 to note this. |

**Campaign exit criterion:** CapabilityRouter Phase 2 surface/curve audit (mirror
of `test_capability_router_phase2_coverage.py`, whose parameterization shape is
`(intent, tool_name, endpoint, category)`) covers every new intent key across
the 4 surfaces: Tool registration, executor case-arm, RouteSpec presence, and
**expected category membership** per the table below. The audit test uses
`categories.get(category, ())` — category is per-intent, not a shared bucket.

**Taxonomy principle for curve ops:** new `/curve/*` routes are curve-op peers
of existing `fillet_curves` / `offset_curve` / `project_curve` / etc. Naming
follows the in-repo `/curve/*` precedent (`{operation}_curves` plural when the
op takes multiple curves; `{operation}_curve` singular when it takes one) and
category membership is `curves`, NOT `creation`. A `create_*` prefix is
reserved for primitive creators that build from scratch
(`create_interpolated_curve`, `create_control_point_curve`); `BlendCrv` and
`CurveBoolean` both derive new curves from existing geometry and so are NOT
`create_*` intents.

Proposed intent keys, routes, and category assignments:

| Intent | Endpoint | `CATEGORIES` bucket | Rationale |
|--------|----------|---------------------|-----------|
| `create_edge_srf` | `/surface/edge` | `creation` | Surface creator from 2–4 boundary curves; matches `create_loft` precedent (takes existing curves, produces new surface). |
| `create_patch` | `/surface/patch` | `creation` | Surface creator. |
| `create_network_srf` | `/surface/network` | `creation` | Surface creator. |
| `blend_curves` | `/curve/blend` | `curves` | **Renamed** (was `create_blend_crv` in earlier drafts). Peer of `fillet_curves` — derives a new curve from two existing curves. Plural naming matches `fillet_curves` / `join_curves` precedent (operation takes multiple curves). |
| `curve_boolean_union` | `/curve/boolean` (`operation=union`) | `curves` | Parallels the brep-boolean pattern where `boolean_union` / `boolean_difference` / `boolean_intersection` / `boolean_split` are four separate intent keys routing to one endpoint with an `operation` param. Same structure here: one `/curve/boolean` endpoint, three intents for the initial PR-4 schema (region form deferred). |
| `curve_boolean_difference` | `/curve/boolean` (`operation=difference`) | `curves` | As above. |
| `curve_boolean_intersection` | `/curve/boolean` (`operation=intersection`) | `curves` | As above. |

This yields **5 endpoints, 7 intent keys** for the shippable-in-campaign set
(EdgeSrf + Patch + NetworkSrf + BlendCurves + 3 CurveBoolean operations).

**Cost of adding to `CATEGORIES["curves"]` is not audit-only.** The
router-completeness test at
`test_intent_runtime.py:390-394` asserts
`len(CATEGORIES["curves"]) == 12` as a hard equality check. Adding four
entries (`blend_curves` + three `curve_boolean_*`) to that bucket updates the
expected count to 16 and requires a test-side edit; similar count-aware or
membership-aware assertions elsewhere in the repo need a sweep before PR-4
ships. Not a blocker — the current campaign keeps all new intents in existing
buckets, so the change set is `CATEGORIES["curves"]` itself + the test count
constant + any downstream router discovery code that enumerates
`CATEGORIES["curves"]` (discovery-path sweep is a plan-doc checklist item,
not a separate PR).

**What we explicitly are NOT doing:** introducing a new `CATEGORIES` bucket
(e.g., `curves_combine`) for these ops. The earlier draft floated that as an
alternative; dropped because (a) `fillet_curves` in `curves` is the direct
precedent, (b) a new bucket would force broader changes — router enumeration
surfaces, planner heuristics, explorer filters, and completeness tests like
`test_all_curve_ops` — that are disproportionate to the taxonomy gain, and
(c) the audit test's parameter-list tuple shape does NOT bound the blast
radius of category additions elsewhere in the codebase. Keeping all new
curve-op intents in `curves` costs one integer on one test constant and one
sweep of enumeration sites; inventing `curves_combine` costs those plus a
category-aware design review.

---

## Substrate Rationale Text (for handler headers + plan doc)

Unlike Phase 1 Pipe (which reused an already-live managed factory), every
Phase 2 Category 4/5 route **adds net-new managed factory code** in
`CreateHandler.cs`. The rationale is:

1. `<API name>` is a RhinoCommon-only static factory; no native C++ SDK
   equivalent.
2. Native re-implementation would require a significant new native C++
   code path with no existing scaffolding — not a small replication task.
3. The `CreateGeometry` bridge callback is already load-bearing for five
   Phase 1 `type` cases (PIPE / LOFT / SWEEP1 / SWEEP2 / REVOLVE);
   extending it with a new `type` carries zero ABI cost (no new callback
   surface, no `BridgeAbiVersion` bump) and inherits the full
   `_strictAttributes` attribute contract for free.

Paste into each new handler's opening comment per Rule 6:

> Substrate: `managed-bridge (reuse)` via existing `CreateGeometry` callback
> (`NativeGhBridgeRegistrar.cs:107`). RhinoCommon-only factory
> (`<API name>`) — no native C++ SDK equivalent. Native re-implementation
> would require building a new native C++ factory path from scratch, not
> duplicating existing code. Managed-bridge reuse (a) inherits the
> already-load-bearing Phase 1 `_strictAttributes` contract and
> (b) extends an existing callback surface at zero ABI cost.

---

## Live-Rhino Verification — Run 2026-04-20

Probe executed via `rhino_command` against a running RookNative instance
(blank document; geometry built fresh per candidate; canvas cleaned between
probes). Results folded into the spike matrix above.

### Observed pattern

- **5 urgent / 2 useful** — same ratio as Phase 1 (5 urgent / 3 useful).
- **Uniform failure mode for curve-input commands.** BlendCrv, CurveBoolean,
  Patch, NetworkSrf all rejected `_SelId` with an "Unknown option(s)" error
  whose options-whitelist is a small toggle set (continuity, tolerance, etc.)
  — NOT a curve-picker command form. Rhino's dash-form `-<Command>` for these
  four commands is an option-setter only; curve selection must happen before
  or interactively, and neither path works via `/command`.
- **Silent failure reproduced on BlendSrf.** Same `executed=true,
  objectsCreated=0` signature as Phase 1's Sweep2. Reinforces Rule 2 —
  document-dependent validation needs to be on the UI thread; the
  command-string substrate can lie about success.
- **FilletSrf scripted form unexpectedly worked** on two perpendicular planar
  surfaces with a shared edge, producing 3 breps at default radius. Response
  is opaque (no per-object role), so the `useful` label holds; scaffolding
  gap (radius + UV-point control) still justifies deferring the typed route
  from this campaign.
- **EdgeSrf scripted form worked cleanly** — 3 lines → 1 brep. Typed route
  still adds value via structured response (type/layer/bbox).

### Impact on campaign ordering

- PR ordering unchanged — tentative labels all confirmed.
- PR-1 choice of worked example (EdgeSrf + BlendCurves) still correct: one
  `useful` + one `urgent`, simplest of each namespace.
- Defer list unchanged: BlendSrf (silent failure, scaffolding gap) and
  FilletSrf (works scripted but scaffolding gap applies to typed route)
  both stay parked with the edge-on-face / UV-point-on-face schema trigger.

---

## Out-of-Scope Items Surfaced During Spike

- **Gap-analysis Category 5 OffsetSrf row is stale** — `/offset/brep` already ships
  this. Follow-up hygiene: update gap-analysis to mark OffsetSrf as shipped and
  drop it from Category 5. One-paragraph edit, no code change. *Park or bundle
  with PR-1.*
- **`FilletChamferHandler` vs `FilletSrf`** — the existing `fillet_edge` / `/fillet`
  route fillets edges of ONE polysurface. `FilletSrf` (deferred above) fillets
  BETWEEN TWO surfaces. These are genuinely different operations; do NOT conflate
  during Phase 2 scope review. Flag explicitly to reviewers because the name
  collision is easy to trip over.
- **`Brep.CreateFromSurface(nurbsSurface)` output wrapping for NetworkSrf** —
  discussed above; flag for plan-doc review.
- **Cross-namespace substrate mix in CurvesHandler.cpp** — also flagged above;
  recommendation is Option A (mix substrates in one file, documented per-route)
  but the user should confirm before code is written.
- **BlendCrv singular-curve insert is new territory on the managed-bridge path.**
  Existing managed bridge creators insert breps (`doc.Objects.AddBrep`). BlendCrv
  returns a `Curve`, inserted via `doc.Objects.Add(geometry, attributes)` or
  the explicit `AddCurve`. PR-1 is the first proof point for the
  singular-curve bridge path end-to-end (including `_strictAttributes`
  attribute handling on a curve object, `ObjectSnapshot` serialization of a
  curve via `RhinoSerializer.SerializeObject`, and `bbox` generation for a
  curve rather than a brep). **Flag for PR-1 scope pass:** confirm the
  Phase 1 attribute-handling / snapshot-serialization code paths in
  `CreateHandler.cs` (currently exercised only for breps in the strict
  plural path and for a mix of geometry classes in the singular path) behave
  correctly for a curve returned from a managed factory. Existing
  `INTERPOLATED_CURVE` / `CONTROL_POINT_CURVE` cases do exercise the
  singular-curve path under non-strict, but not under `_strictAttributes=true`;
  verify strict parity before declaring the pattern established.

---

## Rhythm Checks (matches 2026-04-17 Phase 1 spike)

- [x] **Observe before theorizing** — codebase probe complete; live `/command`
      probe still pending (documented as such, not faked).
- [x] **Scope pass before code** — this memo is the scope pass. Stops before any
      handler code, MCP tool registration, or CapabilityRouter edits.
- [ ] **2-3 review rounds before runtime-only risk remains** — zero so far; waiting
      on user + Codex review of this memo before proceeding.
