// SurfaceHandler.h
//
// Canonical home for Phase 1 typed surface-creation routes
// (/surface/pipe, /surface/loft, /surface/sweep1, /surface/sweep2,
// /surface/revolve) + Phase 2 extension routes (/surface/edge — PR-1;
// /surface/patch — PR-2; /surface/network — PR-3). Managed-bridge
// (reuse) substrate — native owns HTTP entry, schema validation, XOR
// checks, and response-envelope normalization; managed side (via
// existing CreateGeometry callback) owns the RhinoCommon factory
// invocation and document insertion.
//
// See rook_docs/2026-04-17-typed-route-phase1-plan.md (§ Worked
// Example) for binding rule references and the substrate decision
// rationale per route. Phase 2 extension: see
// rook_docs/2026-04-20-phase2-surface-curve-plan.md.

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

// POST /surface/pipe — Create a pipe brep along a rail curve.
void HandlePipe(const httplib::Request& req, httplib::Response& res);

// POST /surface/loft — Create lofted brep(s) through 2+ profile curves.
// Plural-contract route: response wraps result in {objects: [...]} even
// when the loft factory returns exactly one brep.
void HandleLoft(const httplib::Request& req, httplib::Response& res);

// POST /surface/sweep1 — Sweep profile(s) along one rail. Plural-contract.
// style: "Freeform" (default) | "Roadlike". Roadlike requires roadlikeUp.
void HandleSweep1(const httplib::Request& req, httplib::Response& res);

// POST /surface/sweep2 — Sweep profile(s) between two rails. Plural-contract.
// maintainHeight: false (default) preserves profile shape; true preserves
// vertical height when rails diverge (maps to SweepTwoRail.MaintainHeight).
void HandleSweep2(const httplib::Request& req, httplib::Response& res);

// POST /surface/revolve — Revolve a profile curve around a line axis.
// Singular-contract (RevSurface.Create produces one surface → one brep).
// axisStart/axisEnd required; startAngle/endAngle optional (degrees,
// defaults 0 and 360).
void HandleRevolve(const httplib::Request& req, httplib::Response& res);

// POST /surface/edge — Phase 2 PR-1. Create a single brep from 2-4
// boundary curves via Brep.CreateEdgeSurface. Singular-contract.
// curveIds required (min 2, max 4). Factory is empirically permissive;
// pathological inputs (zero-length, disjoint, degenerate) still succeed
// — see Common Plan permissiveness amendment at
// rook_docs/2026-04-17-typed-route-phase1-plan.md:257.
void HandleEdgeSrf(const httplib::Request& req, httplib::Response& res);

// POST /surface/patch — Phase 2 PR-2. Brep.CreatePatch: fit a surface
// through curves/points/point-clouds, optionally constrained by a
// starting seed surface. Singular-contract.
//
// Dispatch branches on startingSurfaceId presence (overload 3 seeded vs
// overload 2 no-seed — empirically non-equivalent 2026-04-20).
// flexibility/surfacePull require startingSurfaceId; rejected otherwise.
// Worker-thread rejects uSpans/vSpans <= 0, flexibility <= 0, and
// tolerance <= 0 (factory silently coerces these into garbage surfaces).
void HandlePatch(const httplib::Request& req, httplib::Response& res);

// POST /surface/network — Phase 2 PR-3. NurbsSurface.CreateNetworkSurface
// via auto-detect (curveIds) or explicit (uCurveIds + vCurveIds) input
// forms. Singular-contract; output wrapped via Brep.CreateFromSurface.
// Single continuity param applied to all 4 slots of the explicit overload
// (asymmetric per-direction-per-end continuity deferred).
//
// Worker-thread rejects: both forms present (input_form_conflict),
// one-sided explicit (input_form_incomplete), empty explicit arrays,
// neither form, curveIds < 2, continuity outside {0,1,2}
// (invalid_continuity), and any tolerance <= 0 (factory silently
// coerces these).
void HandleNetworkSrf(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
