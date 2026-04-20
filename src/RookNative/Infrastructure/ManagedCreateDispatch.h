// ManagedCreateDispatch.h
//
// Shared normalization + dispatch tail for HTTP handlers that delegate
// geometry creation to the managed (C#) companion via the
// `CreateGeometry` bridge callback.
//
// Promoted from an anonymous namespace in SurfaceHandler.cpp (lines
// 45-135 prior to Phase 2 PR-4) after a third caller landed
// (`HandleCurveBoolean` joins `HandleBlendCurves` + every
// `HandleX` on SurfaceHandler). Rule 6 promotion-on-third-caller
// convention — the local-mirror copy in `HandleBlendCurves` is
// removed in the same change.
//
// Callers must have already:
//   - finished worker-thread schema validation and returned early on
//     failure,
//   - injected `type` + `_strictAttributes` into the body JSON,
//   - dumped the body to a string.
//
// Failure modes are uniform across callers:
//   - Managed success        -> HTTP 2xx (passed through)
//   - Managed structured err -> HTTP 4xx/5xx mapped by CRookServer::SendErrorData
//   - Managed string err     -> rewritten as {errorCode:"operation_failed"}
//   - Malformed response     -> {errorCode:"operation_failed"}
//   - Bridge unavailable     -> HTTP 503 {errorCode:"bridge_unavailable"}
//   - Bridge invocation fail -> HTTP 500 {errorCode:"operation_failed"}

#pragma once

#include <string>

namespace httplib { struct Response; }

namespace Rook {
namespace Infrastructure {

// Normalize a managed CreateGeometry response into a handler's contract.
// Managed success: {success:true, data:ObjectSnapshot} → passed through.
// Managed string error: {success:false, data:"..."} → rewritten as
//   {success:false, data:{errorCode:"operation_failed", errorMessage:"..."}}.
// Managed structured error (already {errorCode, errorMessage}) → passed through.
// Malformed managed response → {success:false, data:{errorCode:"operation_failed",
//   errorMessage:"Managed response could not be parsed"}}.
void EmitNormalized(httplib::Response& res,
                    const std::string& managedResponseJson,
                    int managedStatus);

// Dispatch to the managed CreateGeometry callback with `bodyJson`, and
// normalize the response. Handles Ok / Unavailable / Failed branches
// uniformly — callers never see the raw `ManagedCreateInvokeResult` enum.
void DispatchToManagedCreate(const std::string& bodyJson,
                             httplib::Response& res);

} // namespace Infrastructure
} // namespace Rook
