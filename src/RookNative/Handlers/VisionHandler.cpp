// VisionHandler.cpp
//
// Native HTTP routes for /vision/*. All three handlers are thin: parse
// body, inject the op discriminator, forward to the managed
// vision_dispatch bridge callback (ABI v14). The managed VisionHandler
// is the single validation boundary — native does transport only.
//
// Single-callback shape rationale: keeps ABI stable as PR-5b adds more
// vision routes (list/get/approve/delete/consume) without requiring a
// per-route slot. The op discriminator lives in the request JSON.

#include "stdafx.h"
#include "Handlers/VisionHandler.h"
#include "Handlers/GrasshopperProxyHandler.h"
#include "Infrastructure/JsonHelpers.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

namespace {

// Dispatch helper: parse body, inject op, forward through bridge,
// forward response as-is. All three /vision/* routes reuse this.
void DispatchVisionOp(
    const httplib::Request& req,
    httplib::Response& res,
    const char* op)
{
    // Parse the body (or start from an empty object when absent) so we
    // can reliably set the op field without relying on string splicing.
    nlohmann::json body;
    if (!req.body.empty())
    {
        try
        {
            body = nlohmann::json::parse(req.body);
        }
        catch (const std::exception& ex)
        {
            CRookServer::SendError(
                res,
                std::string("Invalid JSON body for /vision/") + op + ": " + ex.what());
            res.status = 400;
            return;
        }
        if (!body.is_object())
        {
            CRookServer::SendError(
                res,
                std::string("Vision request body must be a JSON object (got ") +
                    body.type_name() + ").");
            res.status = 400;
            return;
        }
    }
    else
    {
        body = nlohmann::json::object();
    }

    // Inject op. Native owns the op string — callers cannot override it
    // by sending their own op field, because we always overwrite.
    body["op"] = op;

    const std::string requestJson = body.dump();

    std::string responseJson;
    int statusCode = 0;
    std::string invokeError;
    const auto result = InvokeVisionDispatchWithBody(
        requestJson,
        responseJson,
        statusCode,
        invokeError);

    switch (result)
    {
    case ManagedCreateInvokeResult::Ok:
        res.status = statusCode == 0 ? 200 : statusCode;
        res.set_content(responseJson, "application/json");
        res.set_header("X-Rook-Vision-Op", op);
        return;
    case ManagedCreateInvokeResult::Unavailable:
        CRookServer::SendError(
            res,
            std::string("Vision routes require the Rook companion plugin. "
                        "Ensure Rook.rhp is loaded in Rhino, then retry."));
        res.status = 503;
        res.set_header("X-Rook-Vision-Op", op);
        return;
    case ManagedCreateInvokeResult::Failed:
    default:
        CRookServer::SendError(
            res,
            std::string("Vision dispatch failed for /vision/") + op + ": " + invokeError);
        res.status = 500;
        res.set_header("X-Rook-Vision-Op", op);
        return;
    }
}

} // namespace

void HandleVisionGenerate(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOp(req, res, "generate");
}

void HandleVisionEnhancePrompt(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOp(req, res, "enhance_prompt");
}

void HandleVisionCaptureDepth(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOp(req, res, "capture_depth");
}

} // namespace Handlers
} // namespace Rook
