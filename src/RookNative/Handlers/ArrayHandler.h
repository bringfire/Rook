// ArrayHandler.h
//
// Canonical home for Phase 1 typed array routes:
//   - /array/linear
//   - /array/rectangular
//   - /array/polar
//
// Substrate: direct-sdk (native C++). No managed-bridge crossing, no ABI
// impact. Array operations are composed from elementary ON_Xform transforms
// applied through CRhinoDoc::TransformObject on duplicated objects.
// BridgeAbiVersion remains unchanged.
//
// Contract notes:
//   - one UndoScope per request
//   - count is total-including-source
//   - rectangular arrays use the active CPlane captured at UI-thread dispatch
//     and echo it back as planeUsed
//   - polar arrays use literal world Z [0,0,1] as the default rotation axis
//     (no ambient viewport state) and accept negative angles as reverse-sweep
//   - internal /array/_debug/* routes are test-only and not part of the MCP
//     surface

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

// POST /array/linear — Array source objects along a direction vector.
void HandleLinear(const httplib::Request& req, httplib::Response& res);

// POST /array/rectangular — Array source objects in an X/Y(/Z) grid aligned
// to the active viewport's construction plane.
void HandleRectangular(const httplib::Request& req, httplib::Response& res);

// POST /array/polar — Polar (rotational) array around a center + axis. Negative
// angles are accepted as reverse-direction sweep; ±360 are treated as full
// circle via abs(abs(angle) - 360.0) < 1e-9. count==1 short-circuits step
// computation and the copy loop after schema + source pre-flight, so bogus
// uuids still surface as not_found at count=1. rotate=false preserves source
// orientation by orbiting each source's tight-bbox center.
void HandlePolar(const httplib::Request& req, httplib::Response& res);

// INTERNAL / TEST-ONLY. Not an MCP tool.
// POST /array/_debug/fail-next-copy — arm a one-shot synthetic TransformObject
// failure for the Nth copy attempt in the next array request.
void HandleDebugFailNextCopy(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
