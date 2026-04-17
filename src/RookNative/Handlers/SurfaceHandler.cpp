// SurfaceHandler.cpp
//
// Phase 1 typed surface-creation routes. See plan:
//   rook_docs/2026-04-17-typed-route-phase1-plan.md
//
// Substrate: managed-bridge (reuse) with native error-envelope normalization.
//   - Native owns: HTTP entry, JSON parse, schema validation (required fields,
//     XOR exclusivity), response envelope shape, error-taxonomy mapping.
//   - Managed owns (via CreateGeometry callback at
//     src/Rook/Handlers/CreateHandler.cs): RhinoCommon factory invocation
//     (Brep.CreatePipe etc.), attribute application, document insertion,
//     ObjectSnapshot payload serialization.
//
// Error-envelope normalization: the managed CreateGeometry surface returns
// string-only errors ({success:false, data:"..."}). These routes rewrite
// managed string errors into structured {errorCode, errorMessage} form
// on the way back so the typed route ships the target contract from day
// one, rather than inheriting the reuse seam's legacy error shape.

#include "stdafx.h"
#include "Handlers/SurfaceHandler.h"
#include "Handlers/GrasshopperProxyHandler.h"
#include "Infrastructure/JsonHelpers.h"
#include "RookServer.h"

#include <nlohmann/json.hpp>
#include <string>

namespace Rook {
namespace Handlers {

namespace {

// Normalize a managed CreateGeometry response into this route's contract.
// Managed success: {success:true, data:ObjectSnapshot} → passed through.
// Managed string error: {success:false, data:"..."} → rewritten as
//   {success:false, data:{errorCode:"operation_failed", errorMessage:"..."}}.
// Malformed managed response → {success:false, data:{errorCode:"operation_failed",
//   errorMessage:"Managed response could not be parsed"}}.
void EmitNormalized(httplib::Response& res, const std::string& managedResponseJson, int managedStatus)
{
    auto parsed = nlohmann::json::parse(managedResponseJson, nullptr, false);
    if (parsed.is_discarded() || !parsed.is_object() || !parsed.contains("success"))
    {
        nlohmann::json err = {
            {"errorCode", "operation_failed"},
            {"errorMessage", "Managed response could not be parsed"},
        };
        CRookServer::SendErrorData(res, err);
        return;
    }

    const bool ok = parsed.value("success", false);
    if (ok)
    {
        res.status = (managedStatus >= 200 && managedStatus < 300) ? managedStatus : 200;
        const nlohmann::json& data = parsed.value("data", nlohmann::json(nullptr));
        CRookServer::SendSuccess(res, data);
        return;
    }

    // Managed failure. Preserve structured data if managed already returned an
    // object; otherwise wrap a string message into the structured shape.
    const auto& data = parsed.contains("data") ? parsed["data"] : nlohmann::json("Unknown managed error");
    if (data.is_object() && data.contains("errorCode"))
    {
        CRookServer::SendErrorData(res, data);
        return;
    }

    std::string message;
    if (data.is_string())
        message = data.get<std::string>();
    else
        message = data.dump();

    nlohmann::json err = {
        {"errorCode", "operation_failed"},
        {"errorMessage", message},
    };
    CRookServer::SendErrorData(res, err);
}

} // namespace

// --- POST /surface/pipe -------------------------------------------------

void HandlePipe(const httplib::Request& req, httplib::Response& res)
{
    // documentSerialNumber is forwarded to managed in the body; native does
    // not need to resolve the doc here (the managed bridge marshals onto the
    // UI thread and calls ParseDocumentSerialNumber itself).
    auto [docSn, body] = ParseBodyAndDocSn(req);
    (void)docSn;

    // Worker-thread schema validation (Rule 2).
    auto invalidInput = [&](const std::string& message) {
        nlohmann::json err = {
            {"errorCode", "invalid_input"},
            {"errorMessage", message},
        };
        CRookServer::SendErrorData(res, err);
    };

    // curveId — UUID format is checked here; object-existence + curve-ness
    // are deferred to the managed side (main-thread, doc-dependent).
    try { (void)ParseUuid(body, "curveId"); }
    catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }

    const bool hasRadius = body.contains("radius");
    const bool hasStart = body.contains("startRadius");
    const bool hasEnd = body.contains("endRadius");

    // XOR: either `radius`, or both `startRadius` AND `endRadius`, not both
    // forms and not partial.
    if (hasRadius && (hasStart || hasEnd))
    {
        invalidInput("Provide either 'radius' OR both 'startRadius' and 'endRadius', not both forms");
        return;
    }
    if (!hasRadius && (hasStart != hasEnd))
    {
        invalidInput("Variable-radius pipe requires both 'startRadius' and 'endRadius'");
        return;
    }
    if (!hasRadius && !hasStart)
    {
        invalidInput("Missing radius: provide 'radius' OR both 'startRadius' and 'endRadius'");
        return;
    }

    auto requirePositiveNumber = [&](const nlohmann::json& el, const char* fieldName) -> bool {
        if (!el.is_number())
        {
            invalidInput(std::string("Field '") + fieldName + "' must be a number");
            return false;
        }
        const double v = el.get<double>();
        if (!(v > 0.0))
        {
            invalidInput(std::string("Field '") + fieldName + "' must be > 0");
            return false;
        }
        return true;
    };

    if (hasRadius && !requirePositiveNumber(body["radius"], "radius")) return;
    if (hasStart && !requirePositiveNumber(body["startRadius"], "startRadius")) return;
    if (hasEnd && !requirePositiveNumber(body["endRadius"], "endRadius")) return;

    if (body.contains("tolerance"))
    {
        if (!body["tolerance"].is_number() || body["tolerance"].get<double>() <= 0.0)
        {
            invalidInput("Field 'tolerance' must be a positive number");
            return;
        }
    }

    if (body.contains("cap") && !body["cap"].is_boolean())
    {
        invalidInput("Field 'cap' must be a boolean");
        return;
    }

    // Attribute bundle — syntactic checks (Rule 2 worker-thread). Document-
    // dependent checks (layer existence) happen managed-side, where bad
    // values now surface as structured invalid_input errors that pass
    // through the EmitNormalized path unchanged.
    if (body.contains("name") && !body["name"].is_string())
    {
        invalidInput("Field 'name' must be a string");
        return;
    }
    if (body.contains("layer"))
    {
        if (!body["layer"].is_string() || body["layer"].get<std::string>().empty())
        {
            invalidInput("Field 'layer' must be a non-empty string");
            return;
        }
    }
    if (body.contains("visible") && !body["visible"].is_boolean())
    {
        invalidInput("Field 'visible' must be a boolean");
        return;
    }
    if (body.contains("color"))
    {
        // Parse color natively; bad format → invalid_input before dispatch.
        try { (void)ParseColor(body, "color"); }
        catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }
    }

    // Build the managed CreateGeometry request: inject type:"PIPE" and
    // passthrough the validated params (including the attribute bundle).
    // `_strictAttributes` opts into the Phase 1 attribute-contract: unknown
    // layers and unparseable colors reject as structured invalid_input
    // rather than silently ignore. The managed-side gate keeps legacy
    // /create callers on the pre-PR-1 silent-ignore path, containing the
    // contract change to the typed surface routes.
    body["type"] = "PIPE";
    body["_strictAttributes"] = true;

    std::string responseJson;
    int managedStatus = 0;
    std::string bridgeError;
    const auto result = InvokeManagedCreateWithBody(body.dump(), responseJson, managedStatus, bridgeError);

    switch (result)
    {
    case ManagedCreateInvokeResult::Ok:
        EmitNormalized(res, responseJson, managedStatus);
        return;
    case ManagedCreateInvokeResult::Unavailable:
    {
        nlohmann::json err = {
            {"errorCode", "bridge_unavailable"},
            {"errorMessage", "Managed Grasshopper/Rhino bridge is not registered for this Rhino process."},
        };
        res.status = 503;
        nlohmann::json envelope = {{"success", false}, {"data", err}};
        res.set_content(envelope.dump(), "application/json");
        return;
    }
    case ManagedCreateInvokeResult::Failed:
    default:
    {
        nlohmann::json err = {
            {"errorCode", "operation_failed"},
            {"errorMessage", bridgeError.empty() ? std::string("Managed bridge invocation failed") : bridgeError},
        };
        res.status = 500;
        nlohmann::json envelope = {{"success", false}, {"data", err}};
        res.set_content(envelope.dump(), "application/json");
        return;
    }
    }
}

} // namespace Handlers
} // namespace Rook
