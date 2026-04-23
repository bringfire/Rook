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

} // namespace Handlers
} // namespace Rook
