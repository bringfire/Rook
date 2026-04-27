# Phase 3 PR-1 — `curve_intersects_axis` on `/surface/revolve`

**Date:** 2026-04-21
**Stage:** plan (scope pass locked; pre-code)
**Basis:**
- `rook_docs/2026-04-21-typed-route-phase3-spike.md` — spike memo (probe findings locked the scope)
- `rook_docs/2026-04-17-typed-route-phase1-plan.md` §`/surface/revolve` — original Revolve sub-plan (source of the deferred code)
- `rook_docs/2026-04-15-typed-route-gap-analysis.md` — Decision Record (binding rules)

---

## TL;DR

Add a pre-factory geometric check inside `CreateRevolveStrict` that detects profile curves crossing the revolution axis and rejects with a new `curve_intersects_axis` error code. **Managed-only.** No native schema change, no new route, no new MCP tool, no ABI bump. Single detection rule: `Intersection.CurveLine(curve, axis, tol, tol)` classified by parameter-on-curve into *interior-crossing* (reject) vs *endpoint-touch* (accept, e.g. vase profiles with pole). Initial tolerance `doc.ModelAbsoluteTolerance * 10`; validated empirically against characterization test suite before PR open.

---

## Managed Touch Points

Single-file source change in [`src/Rook/Handlers/CreateHandler.cs`](../Rook/src/Rook/Handlers/CreateHandler.cs):

### Change site 1 — method body

`CreateRevolveStrict` at `CreateHandler.cs:1900-1946`. Insert the detection block **after** axis construction at `:1931` (`var axis = new Line(...)`) and **before** `RevSurface.Create(...)` at `:1935`. By that point all inputs have been resolved (`curve`, `axis`, angles) and no geometry has been created — clean insertion point.

Exact pattern:
```csharp
var axis = new Line(axisStart.Value, axisEnd.Value);

// Phase 3 PR-1: detect curve-crosses-axis interior before RevSurface.Create
// produces silent invalid geometry. Endpoints lying on the axis are legal
// (e.g. vase profiles terminating on the pole); only interior crossings are
// rejected. Tolerance: ModelAbsoluteTolerance * 10.
var axisIntersectTol = doc.ModelAbsoluteTolerance * 10.0;
var intersectionEvents = Intersection.CurveLine(
    curve, axis, axisIntersectTol, axisIntersectTol);
if (intersectionEvents != null)
{
    var curveDomain = curve.Domain;
    foreach (var evt in intersectionEvents)
    {
        // evt.ParameterA is the parameter on `curve` at the intersection point.
        // Endpoint-touch is permitted (profile anchored on the axis at one end).
        // Interior crossing causes RevSurface.Create to emit self-intersecting
        // geometry or silently produce invalid breps — reject upfront.
        double t = evt.ParameterA;
        bool atStart = Math.Abs(t - curveDomain.Min) <= RhinoMath.ZeroTolerance;
        bool atEnd = Math.Abs(t - curveDomain.Max) <= RhinoMath.ZeroTolerance;
        if (!atStart && !atEnd)
        {
            throw new CreateInvalidInputException(
                "Profile curve crosses the revolution axis at an interior point; "
                + "only endpoint contacts are permitted (e.g. profiles anchored "
                + "on the axis at one end).",
                errorCode: "curve_intersects_axis");
        }
    }
}

var startRad = RhinoMath.ToRadians(startAngleDeg);
// ... (existing code unchanged from :1932 onward)
```

### Change site 2 — method docstring

`CreateRevolveStrict` docstring at `CreateHandler.cs:1893-1898`. Replace the "DEFERRED PLAN-CODE" paragraph with a forward-pointing description of the shipped check:

```csharp
/// `curve_intersects_axis` detects interior crossings of the revolution
/// axis by the profile curve via Intersection.CurveLine. Endpoints on the
/// axis are permitted (vase profile with pole). Phase 3 PR-1 (2026-04-21)
/// replaced the earlier fallthrough with real detection — the factory
/// emits invalid-but-successful geometry for interior-crossing profiles,
/// so this check is the only diagnostic signal the caller receives.
```

### Change site 3 — native pointer comment

[`src/RookNative/Handlers/SurfaceHandler.cpp:557-563`](../Rook/src/RookNative/Handlers/SurfaceHandler.cpp) — the native-side `HandleRevolve` has a pointer comment describing the managed-side deferral. Update it in lockstep to point at the shipped detection so the two sides don't drift:

```cpp
// curve_intersects_axis is detected on the managed side in
// CreateRevolveStrict (Phase 3 PR-1, 2026-04-21). The native path here
// does not need to reproduce the check — it dispatches with
// _strictAttributes=true, and the managed method runs the detection
// before RevSurface.Create.
```

### No other files modified

- Native `HandleRevolve` schema unchanged (no new fields).
- `ROOK_ABI_VERSION` unchanged.
- No MCP tool schema or descriptor changes.
- `rhino_create_revolve` tool registration unchanged.
- `intent_runtime.py` route table unchanged.
- `explorer/registry.py` HTTP_MAPPINGS unchanged.
- CapabilityRouter Phase 1/2 coverage tests unchanged.

---

## Detection Rule: Interior vs Endpoint

The factory `RevSurface.Create(curve, axis, t0, t1)` accepts curve-crosses-axis inputs and produces **self-intersecting breps** with `success: true` envelopes — verified empirically via Probe 1 Case 1.2 on 2026-04-21 (line profile `(-2,0,3)→(2,0,7)` crossing Z axis produced a Brep with `bbox [-2,-2,3]→[2,2,~7]`).

The detection must distinguish two geometric shapes that `Intersection.CurveLine` returns in the same event list:

1. **Endpoint touch** — profile anchored on the axis at `curve.Domain.Min` or `curve.Domain.Max`. Legal (produces cones-with-pole, spheres from arcs, cylinders-with-endcap). Examples from Probe 1:
   - Case 1.1: line `(0,0,0)→(5,0,5)` — `curve.Domain.Min` parameter maps to the on-axis point.
   - Case 1.3: horizontal line `(0,0,5)→(3,0,5)` — same shape on the other axis position.
2. **Interior crossing** — profile passes through the axis at a parameter strictly between `curve.Domain.Min` and `curve.Domain.Max`. Illegal (produces invalid geometry). Probe 1 Case 1.2 is the canonical instance.

### The rule

```
for each event in Intersection.CurveLine(curve, axis, tol, tol):
    t = event.ParameterA  # parameter on `curve`
    if t is NOT within tol of curve.Domain.Min AND
       t is NOT within tol of curve.Domain.Max:
        REJECT: curve_intersects_axis
```

### Why `event.ParameterA` and not `event.PointA`

Parameter-space comparison is what naturally distinguishes "curve endpoint lies on axis" from "curve passes through axis." A point-space distance check would need to separately test each endpoint against the axis, duplicating what `Intersection.CurveLine` already computed.

### Why `RhinoMath.ZeroTolerance` for the domain comparison

`curveDomain.Min` / `.Max` are analytic parameter values. The intersection solver returns `ParameterA` values quantized to floating-point solver precision, so comparing with `ZeroTolerance` (~1e-12) is correct. Using `axisIntersectTol` here would **loosen** the endpoint-detection window to ~0.001 units of parameter space on a 1-unit-domain curve, which could accept near-endpoint interior crossings as "endpoints" — regression risk.

### Compound-curve / polycurve note

`Curve.Domain` for a `PolyCurve` is the aggregate parameter space. An interior crossing between two segments of a polycurve with a kink at the axis would register as `t` strictly between `.Min` and `.Max`. That's the correct behavior — a polyline bouncing off the axis is still an interior crossing. No special-case handling needed.

### Parameter reparameterization note

RhinoCommon does NOT normalize `Curve.Domain` to `[0, 1]`. For a `LineCurve`, `Domain.Min == 0` and `Domain.Max == line.Length`. My check reads `curve.Domain` at query time, so it's correct regardless of how the curve was constructed. No `curve.Domain = new Interval(0, 1)` needed.

---

## Initial Tolerance Choice + Validation Plan

### Choice: `doc.ModelAbsoluteTolerance * 10`

`doc.ModelAbsoluteTolerance` defaults to `0.001` in small-unit templates and `0.01` in large-unit templates. Multiplied by 10: `0.01` to `0.1` units. The `Intersection.CurveLine` tolerance argument is the maximum distance at which two geometries are considered to intersect — tighter tolerances miss true crossings that happen near the axis but aren't exactly on it; looser tolerances report spurious "intersections" for curves passing near the axis without touching.

Rationale for the 10× multiplier over raw `ModelAbsoluteTolerance`:
- Phase 1/2 managed routes (e.g. Sweep2's empty-result threshold, Patch's preflight) use `doc.ModelAbsoluteTolerance` at 1× for factory calls. The intersection solver is numerically more sensitive than factory evaluation, so 1× risks missing near-axis crossings that happen in practice (Case 1.2 Probe 1 example line runs within ~0.5 units of the axis at its midpoint — well above 1× but well below 10× the default tolerance).
- 10× is the same factor Phase 1 Sweep1 probe used for endpoint-touch detection in its non-scope prototype (the "heuristic too eager" case that killed PR-2 in Phase 3 used tighter tolerances — 1× and 3×).
- 10× is still well below the minimum meaningful geometric scale (Rhino's default unit tolerance for imported DWG files is 0.1; 10× default = 0.01 in small-unit templates stays below that).

### Validation against the characterization suite

Before PR opens, run the 4 empirical probe cases plus 2 additional characterization cases against the `axisIntersectTol = doc.ModelAbsoluteTolerance * 10` choice and record the behavior:

| Case | Profile | Expected | If tolerance wrong |
|------|---------|----------|---------------------|
| 1.1 (Probe 1) | Line endpoint on axis — `(0,0,0)→(5,0,5)` | ✓ Accept | Regression: reject false positive |
| 1.2 (Probe 1) | Line crosses axis interior — `(-2,0,3)→(2,0,7)` | ✗ Reject (`curve_intersects_axis`) | Regression: accept silently |
| 1.3 (Probe 1) | Horizontal line endpoint on axis — `(0,0,5)→(3,0,5)` | ✓ Accept | Regression: reject false positive |
| 1.4 (Probe 1) | Line parallel to axis — `(3,0,0)→(3,0,10)` | ✓ Accept (never intersects) | N/A, no intersection events |
| **NEW A** | Arc profile endpoint on axis — arc from `(0,0,0)` to `(3,0,3)` via `(3,0,0)` | ✓ Accept | Regression: reject false positive |
| **NEW B** | S-curve crossing axis twice — polycurve via midpoints `(1,0,2)`, `(-1,0,5)`, `(1,0,8)` | ✗ Reject (both crossings interior) | Regression: accept silently |

If all 6 cases pass with `tol = ModelAbsoluteTolerance * 10`, PR opens.

If **Case NEW A** regresses (arc tangent-to-axis false-positive — an intersection event fires at the arc's apex where it tangents the axis, with `ParameterA` in curve interior, triggering spurious rejection):

**Fallback, step 1 — tighten the geometric tolerance.** Drop `axisIntersectTol` from `* 10` to `* 5` or `* 3`. The spurious event is an artifact of the **intersection solver's** tolerance, not the parameter-space classifier. Probe 1 Case 1.2 (3-unit crossing) has a wide geometric margin, so a tighter `axisIntersectTol` still catches real crossings. The parameter-space classifier at `RhinoMath.ZeroTolerance` stays unchanged. Re-run the 6-case probe.

**Fallback, step 2 — add explicit geometric endpoint-on-axis allowance.** If step 1 doesn't resolve NEW A at a tolerance that still catches Case 1.2, add a second filter **after** the parameter-space check: for each event whose `ParameterA` is classified as interior, compute `PointA.DistanceTo(closest point on curve endpoints)`. If `PointA` coincides with `curve.PointAtStart` or `curve.PointAtEnd` within `axisIntersectTol`, treat as endpoint-touch regardless of the parameter-space result. This adds a geometric allowance without widening the parameter-space classifier (so near-endpoint interior crossings — which are genuinely illegal — still reject cleanly).

**Do NOT loosen the parameter-space endpoint window** (i.e. do not swap `RhinoMath.ZeroTolerance` for `axisIntersectTol` in the `.Domain.{Min,Max}` comparison). The §Detection Rule section's rejection of that approach stands — it creates a near-endpoint dead zone inside the curve's interior where real crossings go undetected.

Document the chosen fallback step in the `CreateRevolveStrict` docstring if either fires.

The 6 cases execute in `.scratch/pr1_tolerance_probe.py` — not committed, runs from the repo root against live Rhino. Running it IS the PR acceptance gate for the tolerance choice.

---

## Live-Test Cases

Extend [`mcp_server/tests/test_revolve_live.py`](../Rook/mcp_server/tests/test_revolve_live.py). The file already has 16 tests covering the Phase 1 happy paths and validation errors. Add **3 new tests** in the validation-error section:

1. **`test_revolve_curve_crosses_axis_interior`** — line profile `(-2,0,3)→(2,0,7)` with axis Z — expect structured error `curve_intersects_axis`. This is Probe 1 Case 1.2 promoted to a regression test. **Replaces the current silent-bad-brep behavior** (was: `success: true` with invalid geometry; is: `success: false` with `errorCode: "curve_intersects_axis"`).

2. **`test_revolve_arc_crosses_axis_twice_rejected`** — S-curve polycurve crossing axis at two interior points — expect structured error `curve_intersects_axis` (first interior crossing detected exits early). Pins the loop's "first-hit-wins" semantics.

3. **`test_revolve_endpoint_on_axis_still_accepted`** — line profile `(0,0,0)→(5,0,5)` with axis Z — expect `success: true` with bare `ObjectSnapshot`. This is Probe 1 Case 1.1 promoted to a regression test guarding against **tolerance too loose → rejects endpoint-touch as interior-crossing**. Critical regression floor.

No existing tests need to change. The Phase 1 happy-path suite (`test_revolve_line_profile_full_360`, `test_revolve_arc_profile_full_360`, `test_revolve_partial_sweep`, `test_revolve_non_z_axis`) all use profiles well-separated from their axes and continue to pass unchanged.

---

## Scope Containment (explicit non-goals)

Per Phase 1/2 contract-stability rhythm + Codex scope-pass feedback, the following are explicitly OUT of this PR:

- **No native schema change.** `SurfaceHandler.cpp::HandleRevolve` is pointer-comment-only (Change site 3 above). Request JSON shape unchanged.
- **No new route path.** `/surface/revolve` stays. No `/surface/revolve/v2` or similar.
- **No new MCP tool.** `rhino_create_revolve` descriptor unchanged.
- **No ABI bump.** `ROOK_ABI_VERSION` and native↔managed callback signatures unchanged.
- **No BRIDGE_ROUTES / HTTP_MAPPINGS / CapabilityRouter changes.** `/surface/revolve` was already wired in all 4 discovery surfaces in Phase 1 PR-4.
- **No tolerance schema exposure.** Phase 1 deliberately omitted `tolerance` from `/surface/revolve`'s schema because `RevSurface.ToBrep` takes no tolerance parameter. The new intersection check uses `doc.ModelAbsoluteTolerance * 10` internally — NOT exposed as a request field. Exposing it would be a scope creep away from "one error code + no schema change."
- **No legacy `CreateRevolve` method change.** Legacy `/create?type=REVOLVE` callers (non-strict path) continue to hit `CreateRevolve` (no `Strict` suffix) with silent defaults and no curve-intersects-axis detection. Scope containment matches the Phase 1 PR-4 posture (strict-vs-legacy boundary preserved).
- **No polycurve-structure-aware detection.** A polycurve with a kink on the axis detects as interior crossing (correct) but doesn't distinguish "kink" from "smooth interior crossing" — both are equally illegal for revolve. If a user workflow surfaces a case where kink-on-axis should be legal, that's a follow-up issue.
- **No `operation_failed` deprecation.** `RevSurface.Create` returning null for non-curve-intersects-axis reasons (degenerate inputs unrelated to the axis intersection) still falls through to `operation_failed`. The new code adds an EARLIER filter; the later fallthrough stays as a backstop.

---

## Scope Containment (explicitly IN)

- One new error code: `curve_intersects_axis`.
- One detection block in `CreateRevolveStrict`.
- Three docstring / pointer-comment updates for diff traceability.
- Three new live-test cases.
- Characterization probe (not committed) for tolerance validation before PR opens.

---

## Acceptance Gate

PR opens after:

1. ✓ Code change matches §Managed Touch Points (3 change sites, single source file for the behavior change).
2. ✓ All 6 characterization probes pass with the chosen tolerance (see §Initial Tolerance Choice).
3. ✓ `pytest -m requires_rhino mcp_server/tests/test_revolve_live.py` green — 16 pre-existing + 3 new = **19/19**.
4. ✓ `pytest mcp_server/tests/test_intent_runtime.py` green — 45/45 regression floor.
5. ✓ Scope containment checklist (§non-goals) reviewed and confirmed.

Build & deploy cycle: companion only. Native unchanged means only `dotnet build src/Rook -c Release -p:Platform=x64` + deploy the new `.rhp`. No `build-native.bat`.

---

## Git Workflow

Per project convention (`feedback_pr_workflow` memory):

- Branch: `fix/phase3-pr1-revolve-axis-intersection`
- Single commit
- PR title: `fix(surface): detect curve-crosses-axis in /surface/revolve (closes Phase 3 PR-1)`
- Squash-merge with `gh pr merge --squash --delete-branch` after Codex sign-off
- Update `work-queue.md` post-merge: move PR-1 to Recently shipped; promote PR-2 (`AlignWithSurface`) from Next → Now

---

## Resolved Decision-Record Questions

- Detection algorithm: `Intersection.CurveLine` with parameter-space classification of events. (Confirmed feasible at the §Detection Rule tolerance choice via codebase-side RhinoCommon introspection — `Intersection.CurveLine` returns `CurveIntersections` with `.ParameterA` per event.)
- Endpoint vs interior boundary: `RhinoMath.ZeroTolerance` comparison against `Curve.Domain.{Min,Max}`. No special-casing for arcs, polycurves, or splines.
- Tolerance choice: `doc.ModelAbsoluteTolerance * 10`, validated empirically against 6-case characterization probe before PR opens.
- Scope containment: managed-only; 3 change sites, 1 behavior file, 1 pointer-comment touch on the native side.

---

## Post-Merge Follow-ups

None anticipated. The detection rule is self-contained. If a user workflow surfaces a case where the tolerance is wrong (either direction), file a follow-up issue and treat it as tolerance re-calibration — same pattern as Phase 2's factory-permissiveness findings got folded back into subsequent plan docs via empirical probes.

The `rails_disconnected` permanent deferral documented in the Phase 3 spike memo is NOT a post-merge follow-up here; it's a standalone item with its own user-workflow trigger.
