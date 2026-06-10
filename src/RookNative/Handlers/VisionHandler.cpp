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
#include "Infrastructure/RouteDiagnostics.h"
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
    nlohmann::json& body,
    const nlohmann::json* unavailableDiagnostic = nullptr)
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
    {
        const std::string message =
            "Vision routes require the Rook companion plugin. "
            "Ensure Rook.rhp is loaded in Rhino, then retry.";
        if (unavailableDiagnostic != nullptr)
        {
            CRookServer::SendErrorWithDiagnostic(res, message, *unavailableDiagnostic);
        }
        else
        {
            CRookServer::SendError(res, message);
        }
        res.status = 503;
        res.set_header("X-Rook-Vision-Op", op);
        return;
    }
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

void ForwardVisionDispatchWithUnavailableDiagnostic(
    httplib::Response& res,
    const char* route,
    const char* op,
    nlohmann::json& body)
{
    const auto unavailableDiagnostic =
        Rook::Diagnostics::BuildVisionDispatchCallbackUnavailable(route, op);
    ForwardVisionDispatch(res, op, body, &unavailableDiagnostic);
}

// Body-forwarding dispatch: parse body, inject op, forward. Used by
// routes that carry their payload in the request body (POST generate /
// enhance-prompt / capture-depth / consume-approved).
void DispatchVisionOp(
    const httplib::Request& req,
    httplib::Response& res,
    const char* route,
    const char* op)
{
    nlohmann::json body;
    if (!ParseBodyAsObject(req, res, op, body)) return;
    ForwardVisionDispatchWithUnavailableDiagnostic(res, route, op, body);
}

// Path-param dispatch: extract {id} from req.matches[1], inject into
// body under the supplied field name, then forward. Used by GET/
// DELETE/POST routes where the id is a path segment and any request
// body is also merged.
//
// V2 (Codex review of step 2 follow-ups): the field name was previously
// hardcoded to "artifact_id". Image-side artifact routes still pass
// "artifact_id"; video-side routes pass "job_id". The helper stays in
// this anonymous namespace to avoid project-file churn; source-level
// regression tests pin the route wiring and the parameterized body field.
void DispatchVisionOpWithPathId(
    const httplib::Request& req,
    httplib::Response& res,
    const char* route,
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

    ForwardVisionDispatchWithUnavailableDiagnostic(res, route, op, body);
}

// V4: strict integer-string grammar /^-?[0-9]+$/. Used by the video
// jobs-list query folding to decide whether ?limit=N parses as a JSON
// Number or stays a JSON String.
//
// Stricter than std::stoi — std::stoi accepts leading whitespace, '+',
// and certain locale digit shapes. The V3 contract pins
// VideoOpHandler.TryGetOptionalPositiveInt as the SINGLE validation
// boundary for `limit`. C++ admitting " 5" or "+5" as a Number would
// produce a state managed cannot reproduce on its own, breaking the
// "same envelope whether MCP, agent, or curl" parity. So we only
// promote to Number when the input is unambiguously a canonical
// integer; everything else forwards as a String for managed to reject
// with the typed `field:"limit"` envelope.
//
// Negative values DO match this grammar and forward as Numbers —
// managed's `value < 1` arm rejects with the same `field:"limit"`
// envelope (different message text, same code).
bool IsCanonicalIntegerString(const std::string& s)
{
    if (s.empty()) return false;
    std::size_t i = 0;
    if (s[0] == '-')
    {
        if (s.size() == 1) return false;       // bare "-"
        i = 1;
    }
    for (; i < s.size(); ++i)
    {
        if (s[i] < '0' || s[i] > '9') return false;
    }
    return true;
}

// V4: GET /vision/video/jobs query folding.
//
// Unlike DispatchVisionListWithQuery (image-side artifacts list), this
// helper does NOT pre-reject malformed `limit` at C++. The V3 contract
// pins managed VideoOpHandler.TryGetOptionalPositiveInt as the single
// validation boundary; C++ pre-rejection would lose the typed
// `field:"limit"` discriminator and break agent error handling.
//
// Strategy:
//   - Canonical integer string → forward as JSON Number (managed's
//     TryGetOptionalPositiveInt then handles the value<1 case via the
//     same `field:"limit"` envelope).
//   - Anything else (whitespace, "+5", "0x10", "abc", "", overflow) →
//     forward as raw JSON String so managed's wrong-kind arm rejects
//     with the established envelope.
void DispatchVideoJobsList(
    httplib::Response& res,
    const httplib::Request& req,
    const char* route,
    const char* op)
{
    nlohmann::json body = nlohmann::json::object();

    if (req.has_param("limit"))
    {
        const auto raw = req.get_param_value("limit");
        if (IsCanonicalIntegerString(raw))
        {
            try
            {
                body["limit"] = std::stoi(raw);   // safe: grammar pre-validated
            }
            catch (const std::out_of_range&)
            {
                body["limit"] = raw;              // overflow → forward as String
            }
        }
        else
        {
            body["limit"] = raw;                  // bad shape → forward as String
        }
    }

    ForwardVisionDispatchWithUnavailableDiagnostic(res, route, op, body);
}

// Query-param dispatch: fold whitelisted query parameters into the
// body before forwarding. Used by GET /vision/artifacts (list).
// Only known filter params are forwarded — unknown query strings are
// silently dropped so a malformed request surfaces through managed
// validation, not as a silent bridge-side mismatch.
void DispatchVisionListWithQuery(
    const httplib::Request& req,
    httplib::Response& res,
    const char* route,
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

    ForwardVisionDispatchWithUnavailableDiagnostic(res, route, op, body);
}

} // namespace

void HandleVisionGenerate(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOp(req, res, "POST /vision/generate", "generate");
}

void HandleVisionEnhancePrompt(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOp(req, res, "POST /vision/enhance-prompt", "enhance_prompt");
}

void HandleVisionCaptureDepth(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOp(req, res, "POST /vision/capture-depth", "capture_depth");
}

void HandleVisionListArtifacts(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionListWithQuery(req, res, "GET /vision/artifacts", "list_artifacts");
}

void HandleVisionGetArtifact(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOpWithPathId(req, res, "GET /vision/artifacts/{artifact_id}", "get_artifact", "artifact_id");
}

void HandleVisionApproveArtifact(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOpWithPathId(req, res, "POST /vision/artifacts/{artifact_id}/approve", "approve_artifact", "artifact_id");
}

void HandleVisionDeleteArtifact(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOpWithPathId(req, res, "DELETE /vision/artifacts/{artifact_id}", "delete_artifact", "artifact_id");
}

void HandleVisionConsumeApproved(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOp(req, res, "POST /vision/artifacts/consume-approved", "consume_approved");
}

void HandleVisionDirectorPublishVideo(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOp(req, res, "POST /vision/director/publish-video", "publish_director_video");
}

// ─── Video routes (V2 — long-form ops; C# accepts these names canonically) ──

void HandleVisionVideoSubmit(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOp(req, res, "POST /vision/video/jobs", "submit_video_job");
}

void HandleVisionVideoStatus(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOpWithPathId(req, res, "GET /vision/video/jobs/{job_id}", "get_video_job", "job_id");
}

void HandleVisionVideoCancel(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOpWithPathId(req, res, "POST /vision/video/jobs/{job_id}/cancel", "cancel_video_job", "job_id");
}

void HandleVisionVideoResult(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOpWithPathId(req, res, "GET /vision/video/jobs/{job_id}/result", "get_video_job_result", "job_id");
}

void HandleVisionVideoEstimate(const httplib::Request& req, httplib::Response& res)
{
    DispatchVisionOp(req, res, "POST /vision/video/estimate", "estimate_video_job");
}

// ─── V4 video list routes ───────────────────────────────────────────

void HandleVisionVideoJobsList(const httplib::Request& req, httplib::Response& res)
{
    DispatchVideoJobsList(res, req, "GET /vision/video/jobs", "list_video_jobs");
}

void HandleVisionVideoModelsList(const httplib::Request& /*req*/, httplib::Response& res)
{
    // No params, no body — forward an empty JSON object. Managed
    // VideoOpHandler.ListModels reads no fields beyond `op`.
    nlohmann::json body = nlohmann::json::object();
    ForwardVisionDispatchWithUnavailableDiagnostic(
        res,
        "GET /vision/video/models",
        "list_video_models",
        body);
}

// ─── Presentation diagnostics / repair (reconciler spec 2026-06-10) ─

void HandleVisionPresentation(const httplib::Request& req, httplib::Response& res)
{
    // STRICT contract: {"action":"dump"|"repair"}. This route is NOT a
    // pass-through — native parses the action, rejects anything else
    // with HTTP 400, and constructs the managed op body itself so no
    // user-controlled bytes reach vision_dispatch and the route cannot
    // invoke any other Vision op.
    nlohmann::json parsed;
    if (!ParseBodyAsObject(req, res, "presentation", parsed)) return;

    std::string action;
    if (parsed.contains("action") && parsed["action"].is_string())
    {
        action = parsed["action"].get<std::string>();
    }

    const char* op = nullptr;
    if (action == "dump")
    {
        op = "get_presentation_diagnostics";
    }
    else if (action == "repair")
    {
        op = "repair_presentation";
    }
    else
    {
        CRookServer::SendError(
            res,
            "POST /vision/presentation: 'action' must be 'dump' or 'repair'.");
        res.status = 400;
        res.set_header("X-Rook-Vision-Op", "presentation");
        return;
    }

    // Freshly-constructed body: ForwardVisionDispatch injects the op, so
    // the forwarded JSON is exactly {"op":"<op>"} — nothing else.
    nlohmann::json body = nlohmann::json::object();
    ForwardVisionDispatchWithUnavailableDiagnostic(
        res,
        "POST /vision/presentation",
        op,
        body);
}

} // namespace Handlers
} // namespace Rook
