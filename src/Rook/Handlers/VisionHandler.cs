using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rhino;
using Rook.Artifacts;
using Rook.Services.Vision;

namespace Rook.Handlers
{
    /// <summary>
    /// Single validation boundary for the /vision/* routes. Dispatched
    /// through the <c>vision_dispatch</c> bridge callback (ABI v14). Native
    /// owns the <c>op</c> discriminator — callers cannot override it from
    /// the HTTP body because <c>VisionHandler.cpp</c> overwrites any caller
    /// <c>op</c> field with the route-specific value before forwarding.
    ///
    /// Threading model: three entry points.
    /// <list type="bullet">
    ///   <item><see cref="Dispatch"/> (sync, UI thread) runs on Rhino's UI
    ///         thread via <c>ExecuteApiResponseCallback</c> — used for
    ///         <c>capture_depth</c> because depth capture touches the
    ///         Rhino viewport and must be on the UI thread.</item>
    ///   <item><see cref="DispatchAsync"/> (async, threadpool) runs off
    ///         the UI thread via <c>ExecuteAsyncApiResponseCallback</c> —
    ///         used for <c>generate</c> / <c>enhance_prompt</c> because
    ///         they are network-bound, do not touch Rhino state, and
    ///         blocking the UI thread for 30–60 s during Gemini calls is
    ///         unacceptable.</item>
    ///   <item><see cref="DispatchOffUi"/> (sync, threadpool) runs off
    ///         the UI thread via <c>ExecuteOffUiApiResponseCallback</c> —
    ///         used for the artifact-management ops
    ///         (<c>list_artifacts</c>, <c>get_artifact</c>,
    ///         <c>approve_artifact</c>, <c>delete_artifact</c>,
    ///         <c>consume_approved</c>). These touch only the on-disk
    ///         artifact store; running them off the UI thread prevents
    ///         a large store from starving Rhino during disk scans or
    ///         recursive directory deletes.</item>
    /// </list>
    /// The bridge trampoline peeks the <c>op</c> and selects the correct
    /// dispatcher. Unknown ops are rejected before dispatcher selection.
    ///
    /// Secret hygiene: the Gemini API key is read from
    /// <see cref="VisionSecretStore"/> (DPAPI-wrapped). It is never logged,
    /// never included in response envelopes or error messages, and never
    /// written to artifact metadata. Provider error text is passed through
    /// <see cref="GenericizeProviderError"/> before surfacing.
    /// </summary>
    public class VisionHandler
    {
        public const string ArtifactKindGeneratedImage = "generated_image";
        public const string ArtifactKindEnhancedPrompt = "enhanced_prompt";
        public const string ArtifactKindDepthMap = "depth_map";
        public const string ArtifactKindCapturedViewport = "captured_viewport";

        // Thumbnail dimensions used by `open_image_picker` to keep the
        // bridge response under the 1 MB response-buffer ceiling.
        internal const int ThumbnailMaxEdge = 512;
        internal const long ThumbnailMaxBytes = 512 * 1024;

        // Ops exposed exclusively on the in-process JS bridge
        // (VisionWebSurface). Not routed by the native trampoline —
        // `NativeGhBridgeRegistrar.HandleVisionDispatch` rejects anything
        // outside its own allowlist, so these never become agent-reachable.
        // Documented here so future edits stay aware of the split.
        //
        //   set_api_key             (off-UI)  — widens the secret-setting surface
        //                                        over HTTP; UI-only.
        //   get_settings_overview   (off-UI)  — UI composition, not an agent signal.
        //   test_api_key            (async)   — network probe for UI feedback.
        //   capture_viewport        (UI)      — agents already have the
        //                                        `/viewport` route; this variant
        //                                        exists to produce an artifact.
        //   preview_viewport        (UI)      — transient source preview for
        //                                        Vision; does not create an
        //                                        artifact.
        //   list_views              (UI)      — view enumeration for the UI's
        //                                        viewport selector.
        //   open_image_picker       (UI)      — opens an OS file dialog; no
        //                                        agent affordance.

        internal const int MaxPromptLength = 16_000;
        internal const int MaxContextLength = 4_000;
        internal const long MaxInputImageBytes = 10L * 1024 * 1024; // 10 MB per file
        internal const int MaxReferenceImages = 8;
        // Aggregate raw-byte cap for primary + all reference images
        // combined, BEFORE base64 expansion. Gemini's inline-payload
        // guidance sits around 20 MB per request; 15 MB raw becomes
        // ~20 MB after base64, leaving safety margin for JSON envelope
        // overhead. Protects against 1 × 10 MB + 8 × 10 MB = 90 MB raw
        // requests that per-file limits alone would allow.
        internal const long MaxAggregateImageBytes = 15L * 1024 * 1024;
        internal const int MaxDepthMaxEdge = 4096;
        internal const int DefaultDepthMaxEdge = 1024;

        // list_artifacts bounds. The bridge response buffer is a fixed
        // 1 MB (GrasshopperProxyHandler.cpp). Full artifact envelopes
        // include metadata dictionaries that may carry multi-KB prompts;
        // an unbounded list easily exceeds the buffer and drops into the
        // same silent-oversize failure class PR-5a fixed for blobs. The
        // hard max is enforced below any value a caller can set; the
        // default applies when no limit is supplied.
        internal const int DefaultListLimit = 100;
        internal const int MaxListLimit = 500;

        internal static readonly string[] AllowedResolutions =
            { "512", "1K", "2K", "4K" };

        internal static readonly string[] CommonResolutions =
            { "1K", "2K", "4K" };

        internal static readonly string[] AllowedAspectRatios =
        {
            "1:1", "1:4", "4:1", "1:8", "8:1",
            "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
            "9:16", "16:9", "21:9",
        };

        private readonly ArtifactStore _artifactStore;
        private readonly VisionSecretStore _secrets;
        private readonly GeminiClient _gemini;
        private readonly PromptEnhancer _enhancer;
        private readonly ViewportHandler _viewportHandler;

        public VisionHandler()
            : this(new ArtifactStore(), new VisionSecretStore(),
                   new GeminiClient(), new PromptEnhancer(),
                   new ViewportHandler())
        { }

        internal VisionHandler(
            ArtifactStore artifactStore,
            VisionSecretStore secrets,
            GeminiClient gemini,
            PromptEnhancer enhancer,
            ViewportHandler viewportHandler)
        {
            _artifactStore = artifactStore ?? throw new ArgumentNullException(nameof(artifactStore));
            _secrets = secrets ?? throw new ArgumentNullException(nameof(secrets));
            _gemini = gemini ?? throw new ArgumentNullException(nameof(gemini));
            _enhancer = enhancer ?? throw new ArgumentNullException(nameof(enhancer));
            _viewportHandler = viewportHandler ?? throw new ArgumentNullException(nameof(viewportHandler));
        }

        // ─── Synchronous dispatcher (capture_depth only) ────────────────

        /// <summary>
        /// Sync entry point. Only handles <c>capture_depth</c> — the
        /// network-bound ops use <see cref="DispatchAsync"/> instead.
        /// Any other op is rejected as a defensive guard; the bridge
        /// trampoline is the primary gate.
        /// </summary>
        public ApiResponse Dispatch(string? body)
        {
            Dictionary<string, JsonElement> args;
            try
            {
                args = ParseObjectBody(body);
            }
            catch (ArgumentException ex)
            {
                return Fail(ex.Message);
            }

            var op = GetStringArg(args, "op");
            if (string.IsNullOrEmpty(op))
            {
                return Fail("Vision request missing required 'op' discriminator.");
            }

            try
            {
                return op switch
                {
                    "capture_depth" => CaptureDepth(args),
                    "capture_viewport" => CaptureViewport(args),
                    "preview_viewport" => PreviewViewport(args),
                    "list_views" => ListViews(args),
                    "open_image_picker" => OpenImagePicker(args),
                    "generate" or "enhance_prompt" or "test_api_key" => Fail(
                        $"op '{op}' must be routed through the async dispatcher, not the sync dispatcher."),
                    "list_artifacts" or "get_artifact" or "approve_artifact"
                        or "delete_artifact" or "consume_approved"
                        or "set_api_key" or "get_settings_overview"
                        or "open_artifacts_folder" or "reveal_artifact_file" => Fail(
                        $"op '{op}' must be routed through the off-UI dispatcher, not the sync UI-thread dispatcher."),
                    _ => Fail($"Unknown vision op '{op}'."),
                };
            }
            catch (ArgumentException ex)
            {
                return Fail(ex.Message);
            }
            catch (InvalidOperationException ex)
            {
                return Fail(ex.Message);
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine(
                    $"Rook Vision: unhandled error in op '{op}': {ex.GetType().Name}: {ex.Message}");
                return Fail($"Vision op '{op}' failed. See Rhino command line for details.");
            }
        }

        // ─── Off-UI sync dispatcher (artifact-management ops) ───────────

        /// <summary>
        /// Off-UI sync entry point. Handles the artifact-management ops
        /// (<c>list_artifacts</c>, <c>get_artifact</c>,
        /// <c>approve_artifact</c>, <c>delete_artifact</c>,
        /// <c>consume_approved</c>, <c>open_artifacts_folder</c>,
        /// <c>reveal_artifact_file</c>) — all
        /// disk/shell-only, no Rhino state, no network. Runs on the
        /// threadpool so a large artifact store doesn't stall the Rhino
        /// UI thread during scans/deletes.
        /// Any other op is rejected as a defensive guard; the bridge
        /// trampoline is the primary gate.
        /// </summary>
        public ApiResponse DispatchOffUi(string? body)
        {
            Dictionary<string, JsonElement> args;
            try
            {
                args = ParseObjectBody(body);
            }
            catch (ArgumentException ex)
            {
                return Fail(ex.Message);
            }

            var op = GetStringArg(args, "op");
            if (string.IsNullOrEmpty(op))
            {
                return Fail("Vision request missing required 'op' discriminator.");
            }

            try
            {
                return op switch
                {
                    "list_artifacts" => ListArtifacts(args),
                    "get_artifact" => GetArtifact(args),
                    "approve_artifact" => ApproveArtifact(args),
                    "delete_artifact" => DeleteArtifact(args),
                    "consume_approved" => ConsumeApproved(args),
                    "set_api_key" => SetApiKey(args),
                    "get_settings_overview" => GetSettingsOverview(args),
                    "open_artifacts_folder" => OpenArtifactsFolder(args),
                    "reveal_artifact_file" => RevealArtifactFile(args),
                    "capture_depth" or "capture_viewport" or "preview_viewport"
                        or "list_views" or "open_image_picker" => Fail(
                        $"op '{op}' must be routed through the sync UI-thread dispatcher, not the off-UI dispatcher."),
                    "generate" or "enhance_prompt" or "test_api_key" => Fail(
                        $"op '{op}' must be routed through the async dispatcher, not the off-UI dispatcher."),
                    _ => Fail($"Unknown vision op '{op}'."),
                };
            }
            catch (KeyNotFoundException ex)
            {
                // Artifact-lookup misses — distinct from bad input. The
                // response still lands as success=false with the message
                // the bridge maps to a 400 status code. v1 does not have
                // a separate 404 semantic; the `data` field carries the
                // distinction.
                return Fail(ex.Message);
            }
            catch (ArgumentException ex)
            {
                return Fail(ex.Message);
            }
            catch (InvalidDataException ex)
            {
                return Fail(ex.Message);
            }
            catch (InvalidOperationException ex)
            {
                return Fail(ex.Message);
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine(
                    $"Rook Vision: unhandled error in op '{op}': {ex.GetType().Name}: {ex.Message}");
                return Fail($"Vision op '{op}' failed. See Rhino command line for details.");
            }
        }

        // ─── Async dispatcher (generate + enhance_prompt) ───────────────

        /// <summary>
        /// Async entry point. Handles the network-bound ops. Accepts a
        /// <see cref="CancellationToken"/> that fires on bridge timeout —
        /// the outbound Gemini request is cancelled rather than left to
        /// spend API quota past the deadline.
        /// </summary>
        public async Task<ApiResponse> DispatchAsync(
            string? body, CancellationToken cancellationToken = default)
        {
            Dictionary<string, JsonElement> args;
            try
            {
                args = ParseObjectBody(body);
            }
            catch (ArgumentException ex)
            {
                return Fail(ex.Message);
            }

            var op = GetStringArg(args, "op");
            if (string.IsNullOrEmpty(op))
            {
                return Fail("Vision request missing required 'op' discriminator.");
            }

            try
            {
                return op switch
                {
                    "generate" => await GenerateAsync(args, cancellationToken).ConfigureAwait(false),
                    "enhance_prompt" => await EnhancePromptAsync(args, cancellationToken).ConfigureAwait(false),
                    "test_api_key" => await TestApiKeyAsync(args, cancellationToken).ConfigureAwait(false),
                    "capture_depth" or "capture_viewport" or "preview_viewport"
                        or "list_views" or "open_image_picker" => Fail(
                        $"op '{op}' must be routed through the sync dispatcher, not the async dispatcher."),
                    "list_artifacts" or "get_artifact" or "approve_artifact"
                        or "delete_artifact" or "consume_approved"
                        or "set_api_key" or "get_settings_overview"
                        or "open_artifacts_folder" or "reveal_artifact_file" => Fail(
                        $"op '{op}' must be routed through the off-UI dispatcher, not the async dispatcher."),
                    _ => Fail($"Unknown vision op '{op}'."),
                };
            }
            catch (ArgumentException ex)
            {
                return Fail(ex.Message);
            }
            catch (InvalidOperationException ex)
            {
                return Fail(ex.Message);
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine(
                    $"Rook Vision: unhandled error in op '{op}': {ex.GetType().Name}: {ex.Message}");
                return Fail($"Vision op '{op}' failed. See Rhino command line for details.");
            }
        }

        // ─── op: generate (async) ───────────────────────────────────────

        internal async Task<ApiResponse> GenerateAsync(
            Dictionary<string, JsonElement> args, CancellationToken cancellationToken)
        {
            var prompt = RequireString(args, "prompt", MaxPromptLength);
            var inputImagePath = RequireString(args, "input_image_path", 2048);

            if (!File.Exists(inputImagePath))
            {
                throw new ArgumentException(
                    $"input_image_path does not exist: '{inputImagePath}'.");
            }
            var info = new FileInfo(inputImagePath);
            if (info.Length > MaxInputImageBytes)
            {
                throw new ArgumentException(
                    $"input_image_path exceeds size limit of {MaxInputImageBytes} bytes " +
                    $"({info.Length} bytes).");
            }

            // Track aggregate raw bytes across primary + all references
            // to enforce MaxAggregateImageBytes. Base64 expansion happens
            // downstream — we cap BEFORE encoding to avoid exceeding
            // Gemini's practical inline-payload limit.
            long aggregateBytes = info.Length;

            string[]? referenceBase64 = null;
            if (args.TryGetValue("reference_image_paths", out var refsEl)
                && refsEl.ValueKind == JsonValueKind.Array)
            {
                if (refsEl.GetArrayLength() > MaxReferenceImages)
                {
                    throw new ArgumentException(
                        $"reference_image_paths exceeds the limit of {MaxReferenceImages}.");
                }
                var list = new List<string>();
                foreach (var el in refsEl.EnumerateArray())
                {
                    if (el.ValueKind != JsonValueKind.String)
                        throw new ArgumentException("reference_image_paths entries must be strings.");
                    var path = el.GetString()!;
                    if (!File.Exists(path))
                        throw new ArgumentException($"reference_image_paths entry not found: '{path}'.");
                    var refInfo = new FileInfo(path);
                    if (refInfo.Length > MaxInputImageBytes)
                        throw new ArgumentException($"reference image exceeds size limit: '{path}'.");
                    aggregateBytes += refInfo.Length;
                    if (aggregateBytes > MaxAggregateImageBytes)
                    {
                        throw new ArgumentException(
                            $"Aggregate image payload exceeds {MaxAggregateImageBytes} bytes " +
                            $"({aggregateBytes} bytes so far). Reduce the number or size of " +
                            "reference images.");
                    }
                    list.Add(Convert.ToBase64String(File.ReadAllBytes(path)));
                }
                referenceBase64 = list.ToArray();
            }

            // Accept either a short name ("nano-banana-2") from the UI
            // dropdown or a full Gemini model ID from an agent caller.
            // `ResolveShortName` performs the short→full lookup and passes
            // through unknown values so power users can target newer
            // models at their own risk.
            var modelInput = GetStringArg(args, "model");
            var model = GeminiClient.Models.ResolveShortName(modelInput);
            var resolutionInput = GetStringArg(args, "resolution");
            var resolution = string.IsNullOrWhiteSpace(resolutionInput)
                ? "1K"
                : resolutionInput!;
            var aspectRatio = NormalizeAspectRatio(GetStringArg(args, "aspect_ratio"));

            ValidateResolution(resolution, model);

            var apiKey = _secrets.GetGeminiApiKey();
            if (string.IsNullOrEmpty(apiKey))
            {
                return Fail(
                    "Gemini API key is not configured. Set it via the Vision settings " +
                    "before calling /vision/generate.");
            }

            var inputBytes = File.ReadAllBytes(inputImagePath);

            var result = await _gemini.GenerateImageAsync(
                apiKey!, prompt, inputBytes, referenceBase64,
                model, resolution, aspectRatio, cancellationToken)
                .ConfigureAwait(false);

            if (!result.Success || string.IsNullOrEmpty(result.ImageBase64))
            {
                return Fail(
                    "Image generation failed. " +
                    GenericizeProviderError(result.Error));
            }

            byte[] imageBytes;
            try
            {
                imageBytes = Convert.FromBase64String(result.ImageBase64!);
            }
            catch (FormatException)
            {
                return Fail("Gemini response image was not valid base64.");
            }

            var mimeType = result.ImageMimeType ?? "image/png";
            var extension = ExtensionForMime(mimeType);

            var metadata = new Dictionary<string, JsonNode?>
            {
                ["prompt"] = prompt,
                ["model"] = result.Model ?? model,
                ["resolution"] = resolution,
                ["aspect_ratio"] = aspectRatio ?? "auto",
                ["mime_type"] = mimeType,
                ["generated_at"] = result.GeneratedAt.ToString("o"),
                ["reference_count"] = referenceBase64?.Length ?? 0,
            };

            var blob = new BlobInput("image", imageBytes, extension);
            var artifact = _artifactStore.Create(
                kind: ArtifactKindGeneratedImage,
                blobs: new[] { blob },
                metadata: metadata);

            return Ok(ArtifactEnvelope(artifact));
        }

        // ─── op: enhance_prompt (async) ─────────────────────────────────

        internal async Task<ApiResponse> EnhancePromptAsync(
            Dictionary<string, JsonElement> args, CancellationToken cancellationToken)
        {
            var prompt = RequireString(args, "prompt", MaxPromptLength);
            var context = GetStringArg(args, "context");
            if (context != null && context.Length > MaxContextLength)
            {
                throw new ArgumentException(
                    $"context exceeds maximum length of {MaxContextLength}.");
            }

            var apiKey = _secrets.GetGeminiApiKey();
            if (string.IsNullOrEmpty(apiKey))
            {
                return Fail(
                    "Gemini API key is not configured. Set it via the Vision settings " +
                    "before calling /vision/enhance-prompt.");
            }

            var result = await _enhancer.EnhancePromptAsync(
                apiKey!, prompt, context, cancellationToken).ConfigureAwait(false);

            if (!result.Success || string.IsNullOrEmpty(result.EnhancedPrompt))
            {
                return Fail(
                    "Prompt enhancement failed. " +
                    GenericizeProviderError(result.Error));
            }

            var metadata = new Dictionary<string, JsonNode?>
            {
                ["original_prompt"] = prompt,
                ["context"] = context,
                ["model"] = "gemini-2.5-flash",
                // Surface the enhanced text in metadata so bridge consumers
                // can read it without a secondary fetch against the blob
                // (CSP `connect-src 'none'` blocks XHR/fetch against the
                // virtual host; image tags still work for blob roles but
                // not for text). The blob on disk remains authoritative;
                // this is a convenience field for the UI and for agents
                // pulling the artifact envelope.
                ["enhanced_prompt"] = result.EnhancedPrompt!,
            };

            var blob = new BlobInput(
                "prompt",
                Encoding.UTF8.GetBytes(result.EnhancedPrompt!),
                "json");

            var artifact = _artifactStore.Create(
                kind: ArtifactKindEnhancedPrompt,
                blobs: new[] { blob },
                metadata: metadata);

            return Ok(ArtifactEnvelope(artifact));
        }

        // ─── op: test_api_key (async) ───────────────────────────────────

        /// <summary>
        /// Probe an API key by running a cheap, short prompt through the
        /// enhancer. Accepts either an inline <c>api_key</c> arg (to test
        /// a key BEFORE saving — common UX for "validate then save") or
        /// falls back to the already-stored key.
        ///
        /// UI-only op: not registered on the native trampoline. The probe
        /// costs a few tokens on the user's Gemini account; exposing it
        /// as an agent-reachable HTTP route would let any caller (CORS
        /// permitting) burn quota.
        ///
        /// Success envelope: <c>{ ok: true }</c>. Failure envelope:
        /// <c>Fail("<generic provider error>")</c>. The inline key is
        /// never logged or stored — it only flows into the enhancer call
        /// and is dropped when the method returns.
        /// </summary>
        internal async Task<ApiResponse> TestApiKeyAsync(
            Dictionary<string, JsonElement> args, CancellationToken cancellationToken)
        {
            string? apiKey = GetStringArg(args, "api_key");
            if (string.IsNullOrEmpty(apiKey))
            {
                try
                {
                    apiKey = _secrets.GetGeminiApiKey();
                }
                catch (InvalidOperationException ex)
                {
                    return Fail(ex.Message);
                }
                if (string.IsNullOrEmpty(apiKey))
                {
                    return Fail(
                        "No API key provided or stored. Pass 'api_key' to test a " +
                        "candidate key, or configure one via set_api_key first.");
                }
            }

            var probe = await _enhancer.EnhancePromptAsync(
                apiKey!, "ping", null, cancellationToken).ConfigureAwait(false);

            if (probe.Success)
            {
                return Ok(new Dictionary<string, object?> { ["ok"] = true });
            }
            return Fail(GenericizeProviderError(probe.Error));
        }

        // ─── op: capture_depth (sync — UI thread) ───────────────────────

        internal ApiResponse CaptureDepth(Dictionary<string, JsonElement> args)
        {
            var maxEdge = GetIntArg(args, "max_edge") ?? DefaultDepthMaxEdge;
            if (maxEdge < 100 || maxEdge > MaxDepthMaxEdge)
            {
                throw new ArgumentException(
                    $"max_edge must be between 100 and {MaxDepthMaxEdge}.");
            }

            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return Fail("No active document.");
            }

            var view = doc.Views.ActiveView;
            if (view == null)
            {
                return Fail("No active view available.");
            }

            using var depth = DepthMapGenerator.GenerateDepthMap(view, maxEdge);
            if (depth.Bitmap == null)
            {
                return Fail(
                    $"Depth-map capture produced no bitmap (resolved mode: {depth.ResolvedMode}).");
            }

            byte[] pngBytes;
            using (var ms = new MemoryStream())
            {
                depth.Bitmap.Save(ms, ImageFormat.Png);
                pngBytes = ms.ToArray();
            }

            var metadata = new Dictionary<string, JsonNode?>
            {
                ["resolved_mode"] = depth.ResolvedMode,
                ["width"] = depth.Width,
                ["height"] = depth.Height,
                ["max_edge"] = maxEdge,
            };

            var blob = new BlobInput("image", pngBytes, "png");
            var artifact = _artifactStore.Create(
                kind: ArtifactKindDepthMap,
                blobs: new[] { blob },
                metadata: metadata);

            return Ok(ArtifactEnvelope(artifact));
        }

        // ─── op: capture_viewport (sync — UI thread) ────────────────────

        /// <summary>
        /// Wrap the Tier 3 viewport capture (shipped in #94) in the artifact
        /// flow. Forwards parameters to <see cref="ViewportHandler.CaptureTier3"/>
        /// with <c>captureBackend="tier3"</c> injected, reads the produced PNG
        /// from disk, writes it into the artifact store under kind
        /// <see cref="ArtifactKindCapturedViewport"/>, and returns an envelope.
        /// Mirrors <see cref="CaptureDepth"/>'s artifact-creating shape.
        ///
        /// Parameter mapping — snake_case here to camelCase on the Viewport
        /// contract, so the VisionHandler surface stays uniformly snake_case:
        /// <list type="bullet">
        ///   <item><c>view_id</c> → <c>viewId</c></item>
        ///   <item><c>view_name</c> → <c>view</c></item>
        ///   <item><c>display_mode</c> → <c>displayMode</c></item>
        ///   <item><c>zoom_extents</c> → <c>zoomExtents</c></item>
        ///   <item><c>raytraced_converge</c> → <c>raytracedConverge</c></item>
        ///   <item><c>raytraced_timeout_ms</c> → <c>raytracedTimeoutMs</c></item>
        ///   <item><c>width</c>, <c>height</c> pass through unchanged</item>
        /// </list>
        ///
        /// UI-only op: not registered on the native <c>vision_dispatch</c>
        /// trampoline. Agents that need a viewport bitmap continue to call
        /// the existing <c>/viewport</c> HTTP route.
        /// </summary>
        internal ApiResponse CaptureViewport(Dictionary<string, JsonElement> args)
        {
            var captureResp = CaptureViewportToTemp(args);
            if (!captureResp.Success) return captureResp;
            var data = (Dictionary<string, object?>)captureResp.Data!;
            var filePath = (string)data["filePath"]!;

            byte[] pngBytes;
            try
            {
                pngBytes = File.ReadAllBytes(filePath);
            }
            catch (Exception ex)
            {
                return Fail($"Tier 3 viewport PNG could not be read: {ex.Message}");
            }

            var metadata = new Dictionary<string, JsonNode?>();
            if (data.TryGetValue("viewId", out var vi) && vi is string viStr)
                metadata["view_id"] = JsonValue.Create(viStr);
            if (data.TryGetValue("viewName", out var vn) && vn is string vnStr)
                metadata["view_name"] = JsonValue.Create(vnStr);
            if (data.TryGetValue("displayMode", out var dm) && dm is string dmStr)
                metadata["display_mode"] = JsonValue.Create(dmStr);
            if (data.TryGetValue("width", out var w) && w is int wInt)
                metadata["width"] = JsonValue.Create(wInt);
            if (data.TryGetValue("height", out var h) && h is int hInt)
                metadata["height"] = JsonValue.Create(hInt);
            if (data.TryGetValue("captureBackend", out var cb) && cb is string cbStr)
                metadata["capture_backend"] = JsonValue.Create(cbStr);
            if (data.TryGetValue("raytracedSamples", out var rs) && rs is int rsInt)
                metadata["raytraced_samples"] = JsonValue.Create(rsInt);
            metadata["captured_at"] = JsonValue.Create(
                DateTimeOffset.UtcNow.ToString("o"));

            var blob = new BlobInput("image", pngBytes, "png");
            var artifact = _artifactStore.Create(
                kind: ArtifactKindCapturedViewport,
                blobs: new[] { blob },
                metadata: metadata);

            // Best-effort cleanup of the Tier 3 temp file. The artifact store
            // has its own copy; the temp file is no longer needed.
            try { File.Delete(filePath); }
            catch { /* non-fatal — %TEMP%\rook\viewports accumulates otherwise */ }

            return Ok(ArtifactEnvelope(artifact));
        }

        // ─── op: preview_viewport (sync — UI thread) ───────────────────

        /// <summary>
        /// Capture a viewport for Vision's source preview without creating
        /// a durable artifact. The returned <c>file_path</c> can be passed
        /// directly to <c>generate</c>; <c>preview_url</c> is served by
        /// <see cref="UI.Vision.VisionWebSurface"/> from the temp folder.
        /// </summary>
        internal ApiResponse PreviewViewport(Dictionary<string, JsonElement> args)
        {
            var captureResp = CaptureViewportToTemp(args);
            if (!captureResp.Success) return captureResp;
            var data = (Dictionary<string, object?>)captureResp.Data!;
            var filePath = (string)data["filePath"]!;
            var fileName = Path.GetFileName(filePath);

            return Ok(new Dictionary<string, object?>
            {
                ["file_path"] = filePath,
                ["preview_url"] = $"/viewport-preview/{fileName}",
                ["width"] = data.TryGetValue("width", out var w) ? w : null,
                ["height"] = data.TryGetValue("height", out var h) ? h : null,
                ["view_id"] = data.TryGetValue("viewId", out var vi) ? vi : null,
                ["view_name"] = data.TryGetValue("viewName", out var vn) ? vn : null,
                ["display_mode"] = data.TryGetValue("displayMode", out var dm) ? dm : null,
                ["capture_backend"] = data.TryGetValue("captureBackend", out var cb) ? cb : null,
                ["captured_at"] = DateTimeOffset.UtcNow.ToString("o"),
            });
        }

        private ApiResponse CaptureViewportToTemp(Dictionary<string, JsonElement> args)
        {
            var forward = new JsonObject { ["captureBackend"] = "tier3" };
            CopyIntArg(args, "width", forward, "width");
            CopyIntArg(args, "height", forward, "height");
            CopyStringArg(args, "view_id", forward, "viewId");
            CopyStringArg(args, "view_name", forward, "view");
            CopyStringArg(args, "display_mode", forward, "displayMode");
            CopyBoolArg(args, "zoom_extents", forward, "zoomExtents");
            CopyBoolArg(args, "raytraced_converge", forward, "raytracedConverge");
            CopyIntArg(args, "raytraced_timeout_ms", forward, "raytracedTimeoutMs");

            var viewportResp = _viewportHandler.CaptureTier3(forward.ToJsonString());
            if (!viewportResp.Success)
            {
                return viewportResp;
            }

            if (viewportResp.Data is not Dictionary<string, object?> data
                || !data.TryGetValue("filePath", out var filePathObj)
                || filePathObj is not string filePath
                || string.IsNullOrEmpty(filePath))
            {
                return Fail("Tier 3 viewport capture returned no file path.");
            }

            return Ok(data);
        }

        // ─── op: list_views (sync — UI thread) ──────────────────────────

        /// <summary>
        /// Enumerate the active document's viewports and named views for the
        /// VisionTab's viewport selector. Active-doc only; named views are
        /// flagged but returned in a separate bucket so the UI can style
        /// them differently.
        ///
        /// Standard projections (Top/Front/Right/Perspective/etc.) are NOT
        /// synthesized here — the UI's selector lifted from SA_Banana
        /// populates from this list alone, and the per-viewport
        /// <c>view.ActiveViewport.Name</c> already covers "Top" / "Front" in
        /// the standard four-view layout. If a future UI revision wants a
        /// pinned standard-view list, add a <c>standard_views</c> bucket.
        ///
        /// UI-only op: not registered on the native trampoline.
        /// </summary>
        internal ApiResponse ListViews(Dictionary<string, JsonElement> args)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return Fail("No active document.");
            }

            var views = new List<Dictionary<string, object?>>();
            var active = doc.Views.ActiveView;
            foreach (var view in doc.Views)
            {
                if (view == null) continue;
                var vp = view.ActiveViewport;
                views.Add(new Dictionary<string, object?>
                {
                    ["id"] = view.RuntimeSerialNumber.ToString(),
                    ["name"] = vp.Name ?? "(unnamed)",
                    ["is_active"] = active != null && ReferenceEquals(view, active),
                    ["width"] = vp.Size.Width,
                    ["height"] = vp.Size.Height,
                    ["projection"] = vp.IsPerspectiveProjection ? "perspective" : "parallel",
                });
            }

            var namedViews = new List<Dictionary<string, object?>>();
            for (int i = 0; i < doc.NamedViews.Count; i++)
            {
                namedViews.Add(new Dictionary<string, object?>
                {
                    ["name"] = doc.NamedViews[i].Name ?? "(unnamed)",
                });
            }

            return Ok(new Dictionary<string, object?>
            {
                ["views"] = views,
                ["named_views"] = namedViews,
            });
        }

        // ─── op: open_image_picker (sync — UI thread) ───────────────────

        /// <summary>
        /// Open an Eto <c>OpenFileDialog</c> and return the selected image
        /// path(s) plus a JPEG thumbnail base64 for each, so the UI can
        /// render a preview without a second round-trip or access to the
        /// raw file bytes over the bridge's 1 MB response buffer.
        ///
        /// Threading: runs on Rhino's UI thread because
        /// <c>OpenFileDialog.ShowDialog</c> requires it. During the dialog
        /// every HTTP request through the native server serializes behind
        /// the Rhino UI thread (the fundamental concurrency constraint —
        /// see CLAUDE.md). A user who stalls on the dialog stalls Rhino.
        /// This is an accepted v1 ceiling; a future STA-thread variant
        /// could decouple but adds apartment-affinity risk with Eto + Rhino
        /// panels.
        ///
        /// UI-only op: not registered on the native trampoline. Agents
        /// cannot drive a file dialog.
        ///
        /// Args: <c>{ "multi": bool (default false) }</c>. Returns
        /// <c>{ "paths": [{ "path", "thumbnail_base64", "thumbnail_mime_type",
        ///    "width", "height", "mime_type" }] }</c>. The array is empty when
        /// the user cancels the dialog. Files that fail thumbnail generation
        /// still land in the array with <c>thumbnail_base64 = null</c>.
        /// </summary>
        internal ApiResponse OpenImagePicker(Dictionary<string, JsonElement> args)
        {
            var multi = GetBoolArg(args, "multi") ?? false;

            string[] pickedPaths;
            try
            {
                pickedPaths = ShowOpenDialog(multi);
            }
            catch (Exception ex)
            {
                return Fail($"File picker failed: {ex.Message}");
            }

            var results = new List<Dictionary<string, object?>>();
            foreach (var path in pickedPaths)
            {
                results.Add(BuildPickedImageEntry(path));
            }

            return Ok(new Dictionary<string, object?> { ["paths"] = results });
        }

        /// <summary>
        /// Extracted for unit-testability: build the per-path payload, with
        /// thumbnail and metadata. Safe to call off-UI because it only
        /// touches the file system and in-memory bitmaps.
        /// </summary>
        internal static Dictionary<string, object?> BuildPickedImageEntry(string path)
        {
            var entry = new Dictionary<string, object?>
            {
                ["path"] = path,
                ["thumbnail_base64"] = null,
                ["thumbnail_mime_type"] = null,
                ["width"] = null,
                ["height"] = null,
                ["mime_type"] = GuessImageMimeFromExtension(path),
            };

            if (!File.Exists(path)) return entry;

            try
            {
                using var src = Image.FromFile(path);
                entry["width"] = src.Width;
                entry["height"] = src.Height;

                using var thumb = ResizeToFit(src, ThumbnailMaxEdge, ThumbnailMaxEdge);
                using var ms = new MemoryStream();
                // JPEG at Q75 keeps a 512×512 preview well under the
                // 1 MB bridge buffer (typically < 80 KB).
                var jpegEncoder = GetEncoder(ImageFormat.Jpeg);
                if (jpegEncoder != null)
                {
                    using var ep = new EncoderParameters(1);
                    ep.Param[0] = new EncoderParameter(
                        System.Drawing.Imaging.Encoder.Quality, 75L);
                    thumb.Save(ms, jpegEncoder, ep);
                }
                else
                {
                    thumb.Save(ms, ImageFormat.Jpeg);
                }
                var bytes = ms.ToArray();
                if (bytes.LongLength <= ThumbnailMaxBytes)
                {
                    entry["thumbnail_base64"] = Convert.ToBase64String(bytes);
                    entry["thumbnail_mime_type"] = "image/jpeg";
                }
                else
                {
                    // Defensive: a 512×512 JPEG at Q75 over the buffer
                    // threshold is nearly impossible, but a contrived
                    // 16-bit grayscale-with-alpha source could surprise us.
                    // Logging the overflow keeps the failure loud.
                    RhinoApp.WriteLine(
                        $"Rook Vision: thumbnail exceeded {ThumbnailMaxBytes} bytes for '{path}'; omitting preview bytes.");
                }
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine(
                    $"Rook Vision: thumbnail generation failed for '{path}': {ex.Message}");
            }

            return entry;
        }

        private static string[] ShowOpenDialog(bool multi)
        {
            var dlg = new Eto.Forms.OpenFileDialog
            {
                MultiSelect = multi,
                Title = multi ? "Select images" : "Select an image",
            };
            dlg.Filters.Add(new Eto.Forms.FileFilter(
                "Images", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"));
            dlg.Filters.Add(new Eto.Forms.FileFilter("All files", ".*"));

            var result = dlg.ShowDialog(null);
            if (result != Eto.Forms.DialogResult.Ok)
            {
                return Array.Empty<string>();
            }
            if (multi)
            {
                return dlg.Filenames?.ToArray() ?? Array.Empty<string>();
            }
            return string.IsNullOrEmpty(dlg.FileName)
                ? Array.Empty<string>()
                : new[] { dlg.FileName };
        }

        private static string GuessImageMimeFromExtension(string path)
        {
            var ext = Path.GetExtension(path).ToLowerInvariant();
            return ext switch
            {
                ".png" => "image/png",
                ".jpg" or ".jpeg" => "image/jpeg",
                ".webp" => "image/webp",
                ".gif" => "image/gif",
                ".bmp" => "image/bmp",
                _ => "application/octet-stream",
            };
        }

        private static Bitmap ResizeToFit(Image src, int maxW, int maxH)
        {
            double scale = Math.Min((double)maxW / src.Width, (double)maxH / src.Height);
            if (scale >= 1.0 || scale <= 0.0)
            {
                // Small enough to embed as-is; copy into a fresh bitmap so
                // the caller's `using` doesn't dispose the source too early.
                return new Bitmap(src);
            }
            int w = Math.Max(1, (int)(src.Width * scale));
            int h = Math.Max(1, (int)(src.Height * scale));
            var dst = new Bitmap(w, h);
            using var g = Graphics.FromImage(dst);
            g.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic;
            g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.HighQuality;
            g.PixelOffsetMode = System.Drawing.Drawing2D.PixelOffsetMode.HighQuality;
            g.DrawImage(src, 0, 0, w, h);
            return dst;
        }

        private static ImageCodecInfo? GetEncoder(ImageFormat format)
        {
            foreach (var codec in ImageCodecInfo.GetImageEncoders())
            {
                if (codec.FormatID == format.Guid) return codec;
            }
            return null;
        }

        // ─── op: list_artifacts (off-UI) ────────────────────────────────

        /// <summary>
        /// List artifacts with optional filters. Optional <c>kind</c>
        /// (exact match) and <c>approved</c> (boolean; matches
        /// <c>flags.approved</c>). Optional <c>limit</c> caps the result
        /// count; a value above <see cref="MaxListLimit"/> is rejected
        /// (the response must fit within the bridge's 1 MB buffer).
        /// When no limit is supplied, <see cref="DefaultListLimit"/>
        /// applies. Always returns the store's canonical ordering
        /// (newest <c>CreatedAt</c> first, <c>Id</c> ascending tie-break).
        /// The response includes an <c>applied_limit</c> field so callers
        /// can detect truncation by comparing it to <c>count</c>.
        /// </summary>
        internal ApiResponse ListArtifacts(Dictionary<string, JsonElement> args)
        {
            var kindFilter = GetStringArg(args, "kind");
            if (kindFilter != null && string.IsNullOrWhiteSpace(kindFilter))
            {
                throw new ArgumentException("'kind' filter must be non-empty when specified.");
            }

            var approvedFilter = GetBoolArg(args, "approved");

            var rawLimit = GetIntArg(args, "limit");
            int appliedLimit;
            if (!rawLimit.HasValue)
            {
                appliedLimit = DefaultListLimit;
            }
            else if (rawLimit.Value <= 0)
            {
                throw new ArgumentException(
                    $"'limit' must be a positive integer (got {rawLimit.Value}).");
            }
            else if (rawLimit.Value > MaxListLimit)
            {
                throw new ArgumentException(
                    $"'limit' exceeds maximum of {MaxListLimit} (got {rawLimit.Value}). " +
                    "The bridge response buffer is bounded; paginate by requesting " +
                    "smaller slices or filter by kind/approved.");
            }
            else
            {
                appliedLimit = rawLimit.Value;
            }

            IEnumerable<Artifact> results = _artifactStore.List();

            if (kindFilter != null)
            {
                results = results.Where(a =>
                    string.Equals(a.Kind, kindFilter, StringComparison.Ordinal));
            }

            if (approvedFilter.HasValue)
            {
                results = results.Where(a => IsApproved(a) == approvedFilter.Value);
            }

            results = results.Take(appliedLimit);

            // Compact summary — NOT the full envelope. Drops `metadata`
            // (which can carry a 16 KB prompt on a generated_image) and
            // `file_path` (which requires a per-artifact directory scan
            // to resolve). Under worst-case 100 × 16 KB metadata, the
            // full envelope would exceed the bridge's 1 MB response
            // buffer even at the default limit. Consumers that need
            // metadata or the absolute file path call
            // GET /vision/artifacts/{id} for the full envelope.
            var summaries = new List<Dictionary<string, object?>>();
            foreach (var artifact in results)
            {
                summaries.Add(ArtifactListSummary(artifact));
            }

            return Ok(new Dictionary<string, object?>
            {
                ["artifacts"] = summaries,
                ["count"] = summaries.Count,
                ["applied_limit"] = appliedLimit,
            });
        }

        /// <summary>
        /// Compact list-response entry. Contains only the fields a UI or
        /// agent needs to drive selection / filtering. Deliberately omits
        /// <c>metadata</c> (unbounded size) and <c>file_path</c> (per-item
        /// directory scan). Full detail is available via the get-artifact
        /// route.
        /// </summary>
        private static Dictionary<string, object?> ArtifactListSummary(Artifact artifact)
        {
            return new Dictionary<string, object?>
            {
                ["artifact_id"] = artifact.Id.ToString("D"),
                ["kind"] = artifact.Kind,
                ["created_at"] = artifact.CreatedAt.ToString("o"),
                ["files"] = BuildFilesList(artifact),
                ["parent_ids"] = artifact.ParentIds,
                ["flags"] = artifact.Flags,
            };
        }

        // ─── op: get_artifact (off-UI) ──────────────────────────────────

        /// <summary>
        /// Fetch one artifact by id. v1 returns path + metadata only — no
        /// inline blob bytes. Callers read the file at
        /// <c>file_path</c>/<c>files[].path</c> directly. The
        /// <c>include_blob</c> flag is deliberately absent; adding it
        /// would reintroduce the 1 MB bridge buffer hazard.
        /// </summary>
        internal ApiResponse GetArtifact(Dictionary<string, JsonElement> args)
        {
            var id = RequireArtifactId(args);
            var artifact = _artifactStore.Get(id);
            if (artifact is null)
            {
                throw new KeyNotFoundException($"Artifact '{id:D}' not found.");
            }
            return Ok(ArtifactEnvelope(artifact));
        }

        // ─── op: approve_artifact (off-UI) ──────────────────────────────

        /// <summary>
        /// Set <c>flags.approved = true</c> on an existing artifact.
        /// Idempotent — approving an already-approved artifact is a
        /// successful no-op-shaped call. No unset/disapprove affordance
        /// in v1; if a consumer needs to withdraw approval, delete the
        /// artifact.
        /// </summary>
        internal ApiResponse ApproveArtifact(Dictionary<string, JsonElement> args)
        {
            var id = RequireArtifactId(args);
            // Single-flag schema: { approved: true }. No approved_at, no
            // approved_by — single-user local tool.
            var updated = _artifactStore.SetFlag(id, "approved", JsonValue.Create(true)!);
            return Ok(ArtifactEnvelope(updated));
        }

        // ─── op: delete_artifact (off-UI) ───────────────────────────────

        /// <summary>
        /// Hard-delete an artifact (directory + blobs + manifest). Mirrors
        /// <see cref="ArtifactStore.Create"/>'s inverse.
        ///
        /// Lineage semantics: <c>parent_ids</c> on other artifacts that
        /// referenced the deleted id are left dangling. Lineage is
        /// best-effort history, not referential integrity — a missing
        /// parent is not corruption, it's just a record whose ancestor
        /// has been cleaned up. No cascade, no refcount, no soft-delete
        /// in v1.
        /// </summary>
        internal ApiResponse DeleteArtifact(Dictionary<string, JsonElement> args)
        {
            var id = RequireArtifactId(args);
            if (!_artifactStore.Delete(id))
            {
                throw new KeyNotFoundException($"Artifact '{id:D}' not found.");
            }
            return Ok(new Dictionary<string, object?>
            {
                ["artifact_id"] = id.ToString("D"),
                ["deleted"] = true,
            });
        }

        // ─── op: consume_approved (off-UI) ──────────────────────────────

        /// <summary>
        /// Agent-facing entry point for "give me the most recent approved
        /// concept." Scope is GLOBAL in v1 — the manifest schema does not
        /// carry document/session context, so filtering beyond
        /// <c>kind</c>/<c>since</c> is not available. Callers that need
        /// session-scoped consume must stash a session identifier in
        /// <c>metadata</c> and wait for a future schema extension.
        ///
        /// Default filter: <c>kind == "generated_image"</c> and
        /// <c>flags.approved == true</c>. The kind default is deliberate
        /// — the 2D→3D handoff consumes a concept image, not a depth map
        /// or an enhanced prompt. Callers can override via the request
        /// body.
        ///
        /// Sort: <c>CreatedAt</c> descending, <c>Id</c> descending as a
        /// deterministic tie-breaker so polling does not race on equal
        /// timestamps.
        ///
        /// Returns <c>{ artifact: null }</c> when nothing matches. That
        /// is a steady state the agent polls, not an error.
        /// </summary>
        internal ApiResponse ConsumeApproved(Dictionary<string, JsonElement> args)
        {
            var kindFilter = GetStringArg(args, "kind") ?? ArtifactKindGeneratedImage;
            if (string.IsNullOrWhiteSpace(kindFilter))
            {
                throw new ArgumentException("'kind' filter must be non-empty when specified.");
            }

            DateTimeOffset? sinceFilter = null;
            if (args.TryGetValue("since", out var sinceEl))
            {
                if (sinceEl.ValueKind != JsonValueKind.String)
                {
                    throw new ArgumentException("'since' filter must be an ISO 8601 string with explicit offset.");
                }
                var sinceStr = sinceEl.GetString()!;
                // Reuse the store's manifest-date invariant: require an
                // explicit Z or ±HH:MM offset before handing off to
                // DateTimeOffset.TryParse (which, on its own, silently
                // interprets offset-less strings as local time).
                if (!ArtifactStore.Iso8601WithOffsetPattern.IsMatch(sinceStr))
                {
                    throw new ArgumentException(
                        $"'since' value '{sinceStr}' is not ISO 8601 with explicit offset (Z or ±HH:MM).");
                }
                if (!DateTimeOffset.TryParse(
                        sinceStr,
                        System.Globalization.CultureInfo.InvariantCulture,
                        System.Globalization.DateTimeStyles.RoundtripKind,
                        out var parsed))
                {
                    throw new ArgumentException(
                        $"'since' value '{sinceStr}' is not a valid ISO 8601 datetime.");
                }
                sinceFilter = parsed;
            }

            var match = _artifactStore.List()
                .Where(a => string.Equals(a.Kind, kindFilter, StringComparison.Ordinal))
                .Where(IsApproved)
                .Where(a => !sinceFilter.HasValue || a.CreatedAt >= sinceFilter.Value)
                .OrderByDescending(a => a.CreatedAt)
                .ThenByDescending(a => a.Id)
                .FirstOrDefault();

            return Ok(new Dictionary<string, object?>
            {
                ["artifact"] = match is null ? null : (object)ArtifactEnvelope(match),
            });
        }

        // ─── op: set_api_key (off-UI) ───────────────────────────────────

        /// <summary>
        /// Persist a Gemini API key via <see cref="VisionSecretStore"/>
        /// (DPAPI-wrapped, CurrentUser scope). Never logs the key, never
        /// echoes it in the response. Returns <c>has_api_key=true</c> and
        /// a short preview so the UI can show "sk-...xyz1" without
        /// holding the plaintext.
        ///
        /// UI-only op: not registered on the native trampoline. Agents
        /// must not be able to plant a key through the HTTP surface.
        /// </summary>
        internal ApiResponse SetApiKey(Dictionary<string, JsonElement> args)
        {
            var apiKey = RequireString(args, "api_key", 1024);
            try
            {
                _secrets.SetGeminiApiKey(apiKey);
            }
            catch (ArgumentException ex)
            {
                return Fail(ex.Message);
            }

            return Ok(new Dictionary<string, object?>
            {
                ["has_api_key"] = true,
                // Same preview the store persists — consumers can
                // display it immediately without a follow-up
                // `get_settings_overview` round-trip.
                ["api_key_preview"] = VisionSecretStore.BuildPreview(apiKey),
            });
        }

        // ─── op: get_settings_overview (off-UI) ─────────────────────────

        /// <summary>
        /// Composite read for the Settings view: whether a key is
        /// configured (cheap — no decrypt), the default generation model,
        /// and the artifact count. No inputs.
        ///
        /// UI-only op: not registered on the native trampoline. Agents
        /// have no use for a UI-composed overview.
        /// </summary>
        internal ApiResponse GetSettingsOverview(Dictionary<string, JsonElement> args)
        {
            var overview = new Dictionary<string, object?>
            {
                ["has_api_key"] = _secrets.HasGeminiApiKey(),
                // api_key_preview is the first-4…last-4 obscured form
                // of the stored key, read directly from the settings
                // file without decrypting the DPAPI ciphertext. The
                // Settings UI uses it as an input placeholder ("AIza…
                // xyz1") so it's visually obvious the key persists
                // across sessions — matching SA_Banana's behavior.
                // Null when no key is stored, or when the settings
                // file predates the preview field (next save rebuilds).
                ["api_key_preview"] = _secrets.GetApiKeyPreview(),
                // default_model is the short name the UI dropdown uses,
                // not the full Gemini ID — UI matches option values
                // against this to set the selected entry.
                ["default_model"] = GeminiClient.Models.DefaultShortName,
                // Full catalog so the UI can rebuild dropdowns without
                // hard-coding model IDs alongside the backend. Mirrors
                // SA_Banana's hardcoded pair: paid-tier only. Free-tier
                // models are deliberately absent — API keys can't use
                // them, so listing them would generate only 429s.
                ["available_models"] = GeminiClient.Models.AvailableModels,
                ["allowed_resolutions"] = CommonResolutions,
                ["default_model_supported_resolutions"] =
                    SupportedResolutionsForModel(GeminiClient.Models.Default),
                ["supported_resolutions_by_model"] =
                    SupportedResolutionsByModelShortName(),
                ["allowed_aspect_ratios"] = AllowedAspectRatios,
            };

            try
            {
                var artifacts = _artifactStore.List();
                overview["artifact_count"] = artifacts.Count;
                overview["artifact_counts_by_kind"] = BuildArtifactCountsByKind(artifacts);
            }
            catch (Exception ex)
            {
                // List() throws if the store has duplicate UUIDs across
                // day buckets (corruption). Report the count as null and
                // surface the reason on the Rhino command line, but don't
                // fail the whole overview call — Settings still needs to
                // render so the user can fix the key.
                RhinoApp.WriteLine($"Rook Vision: settings overview artifact_count failed: {ex.Message}");
                overview["artifact_count"] = null;
                overview["artifact_counts_by_kind"] = null;
            }

            return Ok(overview);
        }

        internal static Dictionary<string, int> BuildArtifactCountsByKind(
            IEnumerable<Artifact> artifacts)
        {
            var counts = new Dictionary<string, int>(StringComparer.Ordinal)
            {
                [ArtifactKindGeneratedImage] = 0,
                [ArtifactKindCapturedViewport] = 0,
                [ArtifactKindEnhancedPrompt] = 0,
                [ArtifactKindDepthMap] = 0,
            };

            foreach (var artifact in artifacts)
            {
                if (artifact == null || string.IsNullOrEmpty(artifact.Kind))
                    continue;

                if (!counts.ContainsKey(artifact.Kind))
                    counts[artifact.Kind] = 0;
                counts[artifact.Kind]++;
            }

            return counts;
        }

        // ─── op: open_artifacts_folder (off-UI) ─────────────────────────

        /// <summary>
        /// Open the Vision artifact root in Explorer. The path is not
        /// caller-controlled; it always resolves to
        /// <see cref="RookPaths.ArtifactsRoot"/>.
        /// </summary>
        internal ApiResponse OpenArtifactsFolder(Dictionary<string, JsonElement> args)
        {
            _ = args;
            var folder = RookPaths.ArtifactsRoot;
            Directory.CreateDirectory(folder);

            using var shellProcess = Process.Start(BuildOpenFolderStartInfo(folder));

            return Ok(new Dictionary<string, object?>
            {
                ["path"] = folder,
                ["opened"] = true,
            });
        }

        // ─── op: reveal_artifact_file (off-UI) ───────────────────────────

        /// <summary>
        /// Reveal a specific artifact blob in Explorer. The caller supplies
        /// the artifact id and role; the path itself is resolved through the
        /// artifact store so callers cannot pass arbitrary filesystem paths.
        /// </summary>
        internal ApiResponse RevealArtifactFile(Dictionary<string, JsonElement> args)
        {
            string filePath;
            try
            {
                filePath = ResolveArtifactFilePathForReveal(_artifactStore, args);
            }
            catch (Exception ex) when (TryMapRevealArtifactFileException(ex, out var message))
            {
                return Fail(message!);
            }

            using var shellProcess = Process.Start(BuildRevealFileStartInfo(filePath));

            return Ok(new Dictionary<string, object?>
            {
                ["path"] = Path.GetFullPath(filePath),
                ["opened"] = true,
            });
        }

        internal static ProcessStartInfo BuildOpenFolderStartInfo(string folderPath)
            => new()
            {
                FileName = Path.GetFullPath(folderPath),
                UseShellExecute = true,
            };

        internal static ProcessStartInfo BuildRevealFileStartInfo(string filePath)
            => new()
            {
                FileName = "explorer.exe",
                Arguments = $"/select,\"{Path.GetFullPath(filePath)}\"",
            };

        /// <summary>
        /// Public wrapper used by the VisionTab UI (and any in-process
        /// caller that already has a dispatcher context). Agents route
        /// through the bridge's <c>approve_artifact</c> op instead.
        /// </summary>
        public Artifact SetApproved(Guid artifactId, bool approved)
            => _artifactStore.SetFlag(artifactId, "approved", JsonValue.Create(approved)!);

        // ─── artifact-management helpers ────────────────────────────────

        internal static Guid RequireArtifactId(Dictionary<string, JsonElement> args)
        {
            if (!args.TryGetValue("artifact_id", out var el) || el.ValueKind != JsonValueKind.String)
            {
                throw new ArgumentException("Missing or non-string field 'artifact_id'.");
            }
            var raw = el.GetString();
            if (string.IsNullOrWhiteSpace(raw))
            {
                throw new ArgumentException("Field 'artifact_id' must be non-empty.");
            }
            if (!Guid.TryParseExact(raw, "D", out var id))
            {
                throw new ArgumentException(
                    $"Field 'artifact_id' is not a valid GUID: '{raw}'.");
            }
            return id;
        }

        internal const string RevealFileUnavailableMessage =
            "Image file is no longer available on disk.";

        internal static string RequireNonEmptyString(
            Dictionary<string, JsonElement> args, string field)
        {
            if (!args.TryGetValue(field, out var el) || el.ValueKind != JsonValueKind.String)
            {
                throw new ArgumentException($"Missing or non-string field '{field}'.");
            }

            var raw = el.GetString();
            if (string.IsNullOrWhiteSpace(raw))
            {
                throw new ArgumentException($"Field '{field}' must be non-empty.");
            }

            return raw;
        }

        internal static string ResolveArtifactFilePathForReveal(
            ArtifactStore artifactStore,
            Dictionary<string, JsonElement> args)
        {
            if (artifactStore is null)
            {
                throw new ArgumentNullException(nameof(artifactStore));
            }

            var id = RequireArtifactId(args);
            var role = RequireNonEmptyString(args, "role");
            return artifactStore.GetBlobAbsolutePath(id, role);
        }

        /// <summary>
        /// Maps reveal-time exceptions to the user-facing UX message,
        /// or signals "not mine" so the caller propagates the original.
        /// Only <see cref="KeyNotFoundException"/> (artifact id or role
        /// missing in manifest) and <see cref="FileNotFoundException"/>
        /// (manifest references a blob that no longer exists on disk)
        /// map to <see cref="RevealFileUnavailableMessage"/> — both
        /// share the same user remediation. Traversal/integrity
        /// (<c>InvalidDataException</c>) and bad-input
        /// (<c>ArgumentException</c>) deliberately do NOT map; they
        /// surface their real messages so integrity violations and
        /// contract bugs are visible.
        /// </summary>
        internal static bool TryMapRevealArtifactFileException(
            Exception ex,
            out string? message)
        {
            if (ex is KeyNotFoundException or FileNotFoundException)
            {
                message = RevealFileUnavailableMessage;
                return true;
            }

            message = null;
            return false;
        }

        internal static bool IsApproved(Artifact artifact)
        {
            if (!artifact.Flags.TryGetValue("approved", out var node) || node is null)
                return false;
            try { return node.GetValue<bool>(); }
            catch { return false; }
        }

        // ─── validation helpers ─────────────────────────────────────────

        internal static void ValidateResolution(string resolution)
            => ValidateResolution(resolution, GeminiClient.Models.Default);

        internal static void ValidateResolution(string resolution, string model)
        {
            if (string.IsNullOrEmpty(resolution)) return;
            var upper = resolution.ToUpperInvariant();
            var allowedResolutions = SupportedResolutionsForModel(model);
            foreach (var allowed in allowedResolutions)
            {
                if (upper == allowed) return;
            }
            throw new ArgumentException(
                $"resolution must be one of: {string.Join(", ", allowedResolutions)} " +
                $"for model '{ModelShortNameForMessage(model)}'.");
        }

        internal static string? NormalizeAspectRatio(string? raw)
        {
            if (string.IsNullOrWhiteSpace(raw)) return null;
            var value = raw!.Trim();
            if (value.Equals("auto", StringComparison.OrdinalIgnoreCase)) return null;
            if (value.Equals("current", StringComparison.OrdinalIgnoreCase)) return null;

            foreach (var allowed in AllowedAspectRatios)
            {
                if (value == allowed) return value;
            }

            throw new ArgumentException(
                "aspect_ratio must be 'auto' or one of: " +
                string.Join(", ", AllowedAspectRatios) + ".");
        }

        internal static string[] SupportedResolutionsForModel(string model)
        {
            if (string.Equals(model, GeminiClient.Models.NanoBanana2,
                    StringComparison.Ordinal)
                || string.Equals(model, GeminiClient.Models.DefaultShortName,
                    StringComparison.Ordinal))
            {
                return AllowedResolutions;
            }

            return new[] { "1K", "2K", "4K" };
        }

        internal static Dictionary<string, string[]> SupportedResolutionsByModelShortName()
        {
            return new Dictionary<string, string[]>
            {
                ["nano-banana-2"] =
                    SupportedResolutionsForModel(GeminiClient.Models.NanoBanana2),
                ["nano-banana-pro"] =
                    SupportedResolutionsForModel(GeminiClient.Models.NanoBananaPro),
            };
        }

        private static string ModelShortNameForMessage(string model)
        {
            if (string.Equals(model, GeminiClient.Models.NanoBananaPro,
                    StringComparison.Ordinal))
                return "nano-banana-pro";
            if (string.Equals(model, GeminiClient.Models.NanoBanana2,
                    StringComparison.Ordinal))
                return "nano-banana-2";
            return model;
        }

        /// <summary>
        /// Map MIME type to a file extension for artifact storage. Gemini
        /// can return PNG, JPEG, or WebP; storing all as ".png" would hide
        /// the actual format behind a misleading extension. The raw bytes
        /// are preserved — no decode/re-encode — so the extension must
        /// reflect the content. Unknown MIMEs fall back to "png" and a
        /// warning is logged.
        /// </summary>
        internal static string ExtensionForMime(string? mimeType)
        {
            var norm = (mimeType ?? "").Trim().ToLowerInvariant();
            switch (norm)
            {
                case "image/png": return "png";
                case "image/jpeg":
                case "image/jpg": return "jpg";
                case "image/webp": return "webp";
                case "image/gif": return "gif";
                case "image/bmp": return "bmp";
                default:
                    RhinoApp.WriteLine(
                        $"Rook Vision: unknown image MIME '{mimeType}', " +
                        "storing as .png (bytes unmodified).");
                    return "png";
            }
        }

        /// <summary>
        /// Strip anything that looks like an API key query parameter from
        /// the provider error text before surfacing it externally. Guards
        /// against accidental key leaks through echoed request URLs.
        /// </summary>
        internal static string GenericizeProviderError(string? raw)
        {
            if (string.IsNullOrEmpty(raw)) return "(no detail)";
            var sanitized = System.Text.RegularExpressions.Regex.Replace(
                raw!, @"[?&]key=[^\s&""]+", "$0".Substring(0, 1) + "key=REDACTED",
                System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            if (sanitized.Length > 500)
            {
                sanitized = sanitized.Substring(0, 500) + "... [truncated]";
            }
            return sanitized;
        }

        internal static Dictionary<string, JsonElement> ParseObjectBody(string? body)
        {
            if (string.IsNullOrEmpty(body))
            {
                return new Dictionary<string, JsonElement>();
            }
            Dictionary<string, JsonElement>? parsed;
            try
            {
                parsed = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body!);
            }
            catch (JsonException ex)
            {
                throw new ArgumentException($"Invalid JSON body: {ex.Message}");
            }
            return parsed ?? new Dictionary<string, JsonElement>();
        }

        internal static string RequireString(
            Dictionary<string, JsonElement> args, string name, int maxLength)
        {
            if (!args.TryGetValue(name, out var el) || el.ValueKind != JsonValueKind.String)
            {
                throw new ArgumentException($"Missing or non-string field '{name}'.");
            }
            var value = el.GetString();
            if (string.IsNullOrEmpty(value))
            {
                throw new ArgumentException($"Field '{name}' must be non-empty.");
            }
            if (value!.Length > maxLength)
            {
                throw new ArgumentException(
                    $"Field '{name}' exceeds maximum length of {maxLength}.");
            }
            return value!;
        }

        private static string? GetStringArg(
            Dictionary<string, JsonElement> args, string name)
        {
            if (!args.TryGetValue(name, out var el)) return null;
            if (el.ValueKind == JsonValueKind.String) return el.GetString();
            return null;
        }

        private static int? GetIntArg(
            Dictionary<string, JsonElement> args, string name)
        {
            if (!args.TryGetValue(name, out var el)) return null;
            if (el.ValueKind == JsonValueKind.Number && el.TryGetInt32(out var v))
                return v;
            return null;
        }

        internal static bool? GetBoolArg(
            Dictionary<string, JsonElement> args, string name)
        {
            if (!args.TryGetValue(name, out var el)) return null;
            return el.ValueKind switch
            {
                JsonValueKind.True => true,
                JsonValueKind.False => false,
                _ => null,
            };
        }

        // ─── snake_case → camelCase arg forwarding ──────────────────────
        //
        // VisionHandler uses snake_case uniformly; ViewportHandler (and a
        // handful of other forwarded handlers) use camelCase. Copy* helpers
        // preserve types while renaming keys on the way out.

        private static void CopyStringArg(
            Dictionary<string, JsonElement> src, string srcKey,
            JsonObject dst, string dstKey)
        {
            if (src.TryGetValue(srcKey, out var el)
                && el.ValueKind == JsonValueKind.String)
            {
                dst[dstKey] = el.GetString();
            }
        }

        private static void CopyIntArg(
            Dictionary<string, JsonElement> src, string srcKey,
            JsonObject dst, string dstKey)
        {
            if (src.TryGetValue(srcKey, out var el)
                && el.ValueKind == JsonValueKind.Number
                && el.TryGetInt32(out var v))
            {
                dst[dstKey] = v;
            }
        }

        private static void CopyBoolArg(
            Dictionary<string, JsonElement> src, string srcKey,
            JsonObject dst, string dstKey)
        {
            if (src.TryGetValue(srcKey, out var el))
            {
                if (el.ValueKind == JsonValueKind.True) dst[dstKey] = true;
                else if (el.ValueKind == JsonValueKind.False) dst[dstKey] = false;
            }
        }

        private Dictionary<string, object?> ArtifactEnvelope(Artifact artifact)
        {
            string? filePath = null;
            if (artifact.Files.Count > 0)
            {
                var primary = artifact.Files[0];
                try
                {
                    filePath = _artifactStore.GetBlobAbsolutePath(artifact.Id, primary.Role);
                }
                catch
                {
                    // If path can't be resolved, the ID is still returned.
                }
            }

            return new Dictionary<string, object?>
            {
                ["artifact_id"] = artifact.Id.ToString("D"),
                ["kind"] = artifact.Kind,
                ["created_at"] = artifact.CreatedAt.ToString("o"),
                ["file_path"] = filePath,
                ["files"] = BuildFilesList(artifact),
                ["parent_ids"] = artifact.ParentIds,
                ["metadata"] = artifact.Metadata,
                // Approval and any other persisted flags must be visible to
                // route consumers — without this the approve response and
                // the get/list/consume envelopes cannot carry observable
                // approval state, forcing callers to re-read the manifest.
                ["flags"] = artifact.Flags,
            };
        }

        private static List<Dictionary<string, object?>> BuildFilesList(Artifact artifact)
        {
            var result = new List<Dictionary<string, object?>>();
            foreach (var f in artifact.Files)
            {
                result.Add(new Dictionary<string, object?>
                {
                    ["role"] = f.Role,
                    ["path"] = f.Path,
                });
            }
            return result;
        }

        private static ApiResponse Fail(string message)
            => new() { Success = false, Data = message };

        private static ApiResponse Ok(object data)
            => new() { Success = true, Data = data };
    }
}
