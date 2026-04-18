// ArrayHandler.h
//
// Canonical home for Phase 1 typed array routes:
//   - /array/linear
//   - /array/rectangular
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

// INTERNAL / TEST-ONLY. Not an MCP tool.
// POST /array/_debug/fail-next-copy — arm a one-shot synthetic TransformObject
// failure for the Nth copy attempt in the next array request.
void HandleDebugFailNextCopy(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
