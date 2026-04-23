using System;
using System.Collections.Generic;
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

        internal static readonly string[] AllowedResolutions =
            { "1K", "2K", "4K" };

        private readonly ArtifactStore _artifactStore;
        private readonly VisionSecretStore _secrets;
        private readonly GeminiClient _gemini;
        private readonly PromptEnhancer _enhancer;

        public VisionHandler()
            : this(new ArtifactStore(), new VisionSecretStore(),
                   new GeminiClient(), new PromptEnhancer())
        { }

        internal VisionHandler(
            ArtifactStore artifactStore,
            VisionSecretStore secrets,
            GeminiClient gemini,
            PromptEnhancer enhancer)
        {
            _artifactStore = artifactStore ?? throw new ArgumentNullException(nameof(artifactStore));
            _secrets = secrets ?? throw new ArgumentNullException(nameof(secrets));
            _gemini = gemini ?? throw new ArgumentNullException(nameof(gemini));
            _enhancer = enhancer ?? throw new ArgumentNullException(nameof(enhancer));
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
                    "generate" or "enhance_prompt" => Fail(
                        $"op '{op}' must be routed through the async dispatcher, not the sync dispatcher."),
                    "list_artifacts" or "get_artifact" or "approve_artifact"
                        or "delete_artifact" or "consume_approved" => Fail(
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
        /// <c>consume_approved</c>) — all disk-only, no Rhino state, no
        /// network. Runs on the threadpool so a large artifact store
        /// doesn't stall the Rhino UI thread during scans/deletes.
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
                    "capture_depth" => Fail(
                        $"op '{op}' must be routed through the sync UI-thread dispatcher, not the off-UI dispatcher."),
                    "generate" or "enhance_prompt" => Fail(
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
                    "capture_depth" => Fail(
                        $"op '{op}' must be routed through the sync dispatcher, not the async dispatcher."),
                    "list_artifacts" or "get_artifact" or "approve_artifact"
                        or "delete_artifact" or "consume_approved" => Fail(
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

            var model = GetStringArg(args, "model") ?? GeminiClient.Models.Default;
            var resolution = GetStringArg(args, "resolution") ?? "1K";
            var aspectRatio = GetStringArg(args, "aspect_ratio") ?? "1:1";

            ValidateResolution(resolution);

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
                ["aspect_ratio"] = aspectRatio,
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

        // ─── op: list_artifacts (off-UI) ────────────────────────────────

        /// <summary>
        /// List artifacts with optional filters. Optional <c>kind</c>
        /// (exact match) and <c>approved</c> (boolean; matches
        /// <c>flags.approved</c>). Optional <c>limit</c> caps the result
        /// count to the most-recent N; unspecified or &lt;=0 means no cap.
        /// Always returns the store's canonical ordering (newest
        /// <c>CreatedAt</c> first, <c>Id</c> ascending tie-break).
        /// </summary>
        internal ApiResponse ListArtifacts(Dictionary<string, JsonElement> args)
        {
            var kindFilter = GetStringArg(args, "kind");
            if (kindFilter != null && string.IsNullOrWhiteSpace(kindFilter))
            {
                throw new ArgumentException("'kind' filter must be non-empty when specified.");
            }

            var approvedFilter = GetBoolArg(args, "approved");
            var limit = GetIntArg(args, "limit");

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

            if (limit.HasValue && limit.Value > 0)
            {
                results = results.Take(limit.Value);
            }

            var envelopes = new List<Dictionary<string, object?>>();
            foreach (var artifact in results)
            {
                envelopes.Add(ArtifactEnvelope(artifact));
            }

            return Ok(new Dictionary<string, object?>
            {
                ["artifacts"] = envelopes,
                ["count"] = envelopes.Count,
            });
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

        internal static bool IsApproved(Artifact artifact)
        {
            if (!artifact.Flags.TryGetValue("approved", out var node) || node is null)
                return false;
            try { return node.GetValue<bool>(); }
            catch { return false; }
        }

        // ─── validation helpers ─────────────────────────────────────────

        internal static void ValidateResolution(string resolution)
        {
            if (string.IsNullOrEmpty(resolution)) return;
            var upper = resolution.ToUpperInvariant();
            foreach (var allowed in AllowedResolutions)
            {
                if (upper == allowed) return;
            }
            throw new ArgumentException(
                $"resolution must be one of: {string.Join(", ", AllowedResolutions)}.");
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
