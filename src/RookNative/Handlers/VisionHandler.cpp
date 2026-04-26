// VisionHandler.cpp
//
// Native HTTP routes for /vision/*. All handlers are thin: parse body,
// inject the op discriminator (and a path id field where applicable),
// forward to the managed vision_dispatch bridge callback (ABI v14).
// Native owns transport only; managed handlers are the validation
// boundary — image ops dispatch to VisionHandler.cs (the original
// single boundary for the image domain, PR-5a/5b), and the V2 video
// ops dispatch to VideoOpHandler.cs (validates VideoGenerationRequest
// shape, rejects kind:"path" media refs, maps VideoErrorCode → typed
// HTTP status via ApiResponse.HttpStatus).
//
// Single-callback shape rationale: keeps ABI stable as new vision
// routes land (list/get/approve/delete/consume in PR-5b; submit/
// status/cancel/result/estimate in V2) without requiring a per-route
// callback slot. The op discriminator lives in the request JSON; the
// managed trampoline (NativeGhBridgeRegistrar.HandleVisionDispatch)
// peeks the op and routes to the right managed handler.

#include "stdafx.h"
#include "Handlers/VisionHandler.h"
#include "Handlers/GrasshopperProxyHandler.h"
#include "Infrastructure/JsonHelpers.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

namespace {

// Parse the request body as a JSON object, or start from {}.  Returns
// true on success; on failure, writes the error response + 400 and
// returns false.
bool ParseBodyAsObject(
    const httplib::Request& req,
    httplib::Response& res,
    const char* op,
    nlohmann::json& out)
{
    if (!req.body.empty())
    {
        try
        {
            out = nlohmann::json::parse(req.body);
        }
        catch (const std::exception& ex)
        {
            CRookServer::SendError(
                res,
                std::string("Invalid JSON body for /vision/") + op + ": " + ex.what());
            res.status = 400;
            res.set_header("X-Rook-Vision-Op", op);
            return false;
        }
        if (!out.is_object())
        {
            CRookServer::SendError(
                res,
                std::string("Vision request body must be a JSON object (got ") +
                    out.type_name() + ").");
            res.status = 400;
            res.set_header("X-Rook-Vision-Op", op);
            return false;
        }
    }
    else
    {
        out = nlohmann::json::object();
    }
    return true;
}

// Core dispatch helper: forward a pre-built body with an injected op
// through the vision_dispatch bridge callback and forward the response
// as-is.
void ForwardVisionDispatch(
    httplib::Response& res,
    const char* op,
    nlohmann::json& body)
{
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

// Body-forwarding dispatch: parse body, inject op, forward. Used by
// routes that carry their payload in the request body (POST generate /
// enhance-prompt / capture-depth / consume-approved).
void DispatchVisionOp(
    const httplib::Request& req,
    httplib::Response& res,
    const char* op)
{
    nlohmann::json body;
    if (!ParseBodyAsObject(req, res, op, body)) return;
    ForwardVisionDispatch(res, op, body);
}

// Path-param dispatch: extract {id} from req.matches[1], inject into
// body under the supplied field name, then forward. Used by GET/
// DELETE/POST routes where the id is a path segment and any request
// body is also merged.
//
// V2 (Codex review of step 2 follow-ups): the field name was previously
// hardcoded to "artifact_id". Image-side artifact routes still pass
// "artifact_id"; video-side routes pass "job_id". A native unit-test
// gap remains for this helper — the function lives in an anonymous
// namespace to avoid project-file churn. Coverage lands in C# at the
// vision_dispatch boundary (step 8 video route smoke tests).
void DispatchVisionOpWithPathId(
    const httplib::Request& req,
    httplib::Response& res,
    const char* op,
    const char* path_id_field)
{
    nlohmann::json body;
    if (!ParseBodyAsObject(req, res, op, body)) return;

    if (req.matches.size() < 2)
    {
        CRookServer::SendError(
            res,
            std::string("/vision/.../") + op +
                ": path id match missing.");
        res.status = 500;
        res.set_header("X-Rook-Vision-Op", op);
        return;
    }

    // Path id takes precedence over any body-supplied id field —
    // native owns both the op discriminator and the primary identity
    // the route URL claimed. Callers cannot smuggle a different id
    // through the body.
    body[path_id_field] = req.matches[1].str();

    ForwardVisionDispatch(res, op, body);
}

// Query-param dispatch: fold whitelisted query parameters into the
// body before forwarding. Used by GET /vision/artifacts (list).
// Only known filter params are forwarded — unknown query strings are
// silently dropped so a malformed request surfaces through managed
// validation, not as a silent bridge-side mismatch.
void DispatchVisionListWithQuery(
    const httplib::Request& req,
    httplib::Response& res,
    const char* op)
{
    nlohmann::json body = nlohmann::json::object();

    if (req.has_param("kind"))
    {
        body["kind"] = req.get_param_value("kind");
    }

    if (req.has_param("approved"))
    {
        const auto raw = req.get_param_value("approved");
        // Accept common truthy/falsy spellings; managed validation
        // rejects anything else. Canonicalize to a JSON bool here so
        // the dispatcher's GetBoolArg picks it up.
        if (raw == "true" || raw == "1")
        {
            body["approved"] = true;
        }
        else if (raw == "false" || raw == "0")
        {
            body["approved"] = false;
        }
        else
        {
            CRookServer::SendError(
                res,
                std::string("/vision/artifacts: 'approved' must be 'true' or 'false', got '") +
                    raw + "'.");
            res.status = 400;
            res.set_header("X-Rook-Vision-Op", op);
            return;
        }
    }

    if (req.has_param("limit"))
    {
        const auto raw = req.get_param_value("limit");
        // std::stoi silently accepts trailing garbage ("5abc" -> 5).
        // Require the entire string to be consumed so a malformed
        // value is rejected, matching the route's "malformed limits
        // are rejected" contract. Also reject an empty string up
        // front so stoi doesn't throw before we can message it.
        if (raw.empty())
        {
            CRookServer::SendError(
                res,
                std::string("/vision/artifacts: 'limit' must be a non-empty integer."));
            res.status = 400;
            res.set_header("X-Rook-Vision-Op", op);
            return;
        }
        try
        {
            std::size_t consumed = 0;
            const int parsed = std::stoi(raw, &consumed);
            if (consumed != raw.size())
            {
                CRookServer::SendError(
                    res,
                    std::string("/vision/artifacts: 'limit' has trailing non-numeric characters, got '") +
                        raw + "'.");
                res.status = 400;
                res.set_header("X-Rook-Vision-Op", op);
                return;
            }
            body["limit"] = parsed;
        }
        catch (const std::exception&)
        {
            CRookServer::SendError(
                res,
                std::string("/vision/artifacts: 'limit' must be an integer, got '") +
                    raw + "'.");
            res.status = 400;
            res.set_header("X-Rook-Vision-Op", op);
            return;
        }
    }

    ForwardVisionDispatch(res, op, body);
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

void HandleVisionListArtifacts(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionListWithQuery(req, res, "list_artifacts");
}

void HandleVisionGetArtifact(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOpWithPathId(req, res, "get_artifact", "artifact_id");
}

void HandleVisionApproveArtifact(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOpWithPathId(req, res, "approve_artifact", "artifact_id");
}

void HandleVisionDeleteArtifact(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOpWithPathId(req, res, "delete_artifact", "artifact_id");
}

void HandleVisionConsumeApproved(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOp(req, res, "consume_approved");
}

// ─── Video routes (V2 — long-form ops; C# accepts these names canonically) ──

void HandleVisionVideoSubmit(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOp(req, res, "submit_video_job");
}

void HandleVisionVideoStatus(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOpWithPathId(req, res, "get_video_job", "job_id");
}

void HandleVisionVideoCancel(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOpWithPathId(req, res, "cancel_video_job", "job_id");
}

void HandleVisionVideoResult(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOpWithPathId(req, res, "get_video_job_result", "job_id");
}

void HandleVisionVideoEstimate(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOp(req, res, "estimate_video_job");
}

} // namespace Handlers
} // namespace Rook
