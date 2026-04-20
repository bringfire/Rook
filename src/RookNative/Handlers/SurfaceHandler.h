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

} // namespace Handlers
} // namespace Rook
