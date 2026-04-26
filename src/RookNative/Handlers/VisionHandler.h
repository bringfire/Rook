// VisionHandler.h
//
// Native HTTP entry points for the /vision/* routes. All handlers
// proxy through a single managed bridge callback (vision_dispatch,
// ABI v14) with a long-form op discriminator in the request body.
// The managed trampoline (NativeGhBridgeRegistrar.HandleVisionDispatch)
// routes by op to the right managed handler:
//
//   - Image ops (generate, enhance_prompt, capture_depth, list/get/
//     approve/delete artifacts, consume_approved) → VisionHandler.cs
//   - V2 video ops (submit_video_job, get_video_job, cancel_video_job,
//     get_video_job_result, estimate_video_job) → VideoOpHandler.cs
//
// Each managed handler is the validation boundary for its domain.

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

// POST /vision/generate — Gemini image generation from input image +
// prompt. Input is a file path (not an artifact ID, not inline base64).
// Returns an artifact ID and a file path to the generated PNG; the
// response never carries the image bytes (bridge 1 MB buffer).
void HandleVisionGenerate(const httplib::Request& req, httplib::Response& res);

// POST /vision/enhance-prompt — Text-only Gemini call that expands a
// short prompt into a structured prompt. Stores the result as an
// artifact (prompt.json blob) and returns the artifact ID + path.
void HandleVisionEnhancePrompt(const httplib::Request& req, httplib::Response& res);

// POST /vision/capture-depth — Depth map via Arctic display mode
// (RhinoCommon view.CaptureToBitmap). Full Tier 3 viewport-state
// restore discipline applies (see ViewportHandler.cs). Stores the
// depth map as an artifact and returns artifact ID + path.
void HandleVisionCaptureDepth(const httplib::Request& req, httplib::Response& res);

// GET /vision/artifacts — List artifacts with optional filters.
// Query params (?kind=..., ?approved=..., ?limit=N) are folded into
// the forwarded JSON body before dispatch. Response envelope is
// {artifacts: [...], count: N}. Ordering is newest-CreatedAt-first
// with a deterministic Id-ascending tie-break.
void HandleVisionListArtifacts(const httplib::Request& req, httplib::Response& res);

// GET /vision/artifacts/{id} — Fetch one artifact by id. Returns path
// + metadata only; no inline blob bytes (callers read the file at
// file_path directly). 404-equivalent surfaces as success=false with
// an "Artifact '…' not found" data message.
void HandleVisionGetArtifact(const httplib::Request& req, httplib::Response& res);

// POST /vision/artifacts/{id}/approve — Set flags.approved = true on
// an existing artifact. Idempotent. Returns the updated envelope.
void HandleVisionApproveArtifact(const httplib::Request& req, httplib::Response& res);

// DELETE /vision/artifacts/{id} — Hard-delete the artifact (directory
// + blobs + manifest). Returns {artifact_id, deleted: true} on
// success. Orphaned parent_ids on other artifacts are tolerated —
// lineage is history, not referential integrity.
void HandleVisionDeleteArtifact(const httplib::Request& req, httplib::Response& res);

// POST /vision/artifacts/consume-approved — Most recent approved
// artifact filtered by kind (default "generated_image") and optional
// "since" ISO 8601 timestamp. Global scope in v1 — no session or
// document filtering (the manifest schema doesn't carry them).
// Returns {artifact: {...} | null}.
void HandleVisionConsumeApproved(const httplib::Request& req, httplib::Response& res);

// ─── V2 video routes ────────────────────────────────────────────────
// All five proxy through the same vision_dispatch bridge callback
// (ABI v14, no bump). Long-form op names are injected by native and
// matched by C# canonically; the per-route op string is the wire
// contract that v3.1 D5 pinned. See rook_docs/2026-04-22-v3-video-decisions.md.

// POST /vision/video/jobs — Submit a video generation job. Body
// references input media by artifact_id (D2.1: no inline base64,
// no path refs in V2). Returns {job_id, state} on success;
// returns the typed VideoJobError envelope with HTTP status mapped
// from VideoErrorCode (400/415/500/503) on failure.
void HandleVisionVideoSubmit(const httplib::Request& req, httplib::Response& res);

// GET /vision/video/jobs/{job_id} — Read job status. Returns
// {job_id, state, progress?, result_artifact_id?, error?}.
void HandleVisionVideoStatus(const httplib::Request& req, httplib::Response& res);

// POST /vision/video/jobs/{job_id}/cancel — Request cancellation.
// Returns {job_id, state} where state reflects the post-cancel
// terminal state (typically Cancelled; may be Complete if the job
// finished between the user's intent and the cancel reaching the
// provider).
void HandleVisionVideoCancel(const httplib::Request& req, httplib::Response& res);

// GET /vision/video/jobs/{job_id}/result — Read terminal result.
// Returns {job_id, state, result_artifact_id, files[]}. Fails when
// the job is not Complete or the result artifact is missing.
void HandleVisionVideoResult(const httplib::Request& req, httplib::Response& res);

// POST /vision/video/estimate — First-class cost estimation (v3.1 D3).
// Same body shape as submit; pricing-relevant fields only (model,
// duration, resolution, options, number_of_videos). Returns
// {dollars_usd, model, resolution, duration_seconds, breakdown[],
// pricing}. Both the tab UI's gating modal and a future GH dry-run
// sink consume this route.
void HandleVisionVideoEstimate(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
