// SurfaceHandler.h
//
// Canonical home for Phase 1 typed surface-creation routes
// (/surface/pipe, /surface/loft, /surface/sweep1, /surface/sweep2,
// /surface/revolve). Managed-bridge (reuse) substrate — native owns
// HTTP entry, schema validation, XOR checks, and response-envelope
// normalization; managed side (via existing CreateGeometry callback)
// owns the RhinoCommon factory invocation and document insertion.
//
// See rook_docs/2026-04-17-typed-route-phase1-plan.md (§ Worked
// Example) for binding rule references and the substrate decision
// rationale per route.

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

// POST /surface/pipe — Create a pipe brep along a rail curve.
void HandlePipe(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
