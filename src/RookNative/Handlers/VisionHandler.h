// VisionHandler.h
//
// Native HTTP entry points for the /vision/* routes. All three route
// handlers proxy through a single managed bridge callback
// (vision_dispatch, ABI v14) with an op discriminator in the request
// body. The managed VisionHandler.cs routes by op to the appropriate
// internal method, which is the single validation boundary for the
// vision domain (PR-5a).

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

} // namespace Handlers
} // namespace Rook
