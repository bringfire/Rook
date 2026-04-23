using System;
using System.Collections.Generic;
using System.Drawing.Imaging;
using System.IO;
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
    /// Threading model: two entry points, one sync + one async.
    /// <list type="bullet">
    ///   <item><see cref="Dispatch"/> (sync) runs on Rhino's UI thread
    ///         via <c>ExecuteApiResponseCallback</c> — used for
    ///         <c>capture_depth</c> because depth capture touches the
    ///         Rhino viewport and must be on the UI thread.</item>
    ///   <item><see cref="DispatchAsync"/> (async) runs off the UI thread
    ///         via <c>ExecuteAsyncApiResponseCallback</c> — used for
    ///         <c>generate</c> / <c>enhance_prompt</c> because they are
    ///         network-bound, do not touch Rhino state, and blocking the
    ///         UI thread for 30–60 s during Gemini calls is
    ///         unacceptable.</item>
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
        internal const long MaxInputImageBytes = 10L * 1024 * 1024; // 10 MB
        internal const int MaxReferenceImages = 8;
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
