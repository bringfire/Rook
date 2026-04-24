using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Rhino;

namespace Rook.Services.Vision
{
    /// <summary>
    /// Result payload for a single Gemini image-generation call. Lives in
    /// <see cref="Rook.Services.Vision"/> rather than being shared across
    /// consumers — adapters (VisionHandler) transform this into artifacts.
    /// </summary>
    public sealed class GenerationResult
    {
        public bool Success { get; set; }
        public string? ImageBase64 { get; set; }
        public string? ImageMimeType { get; set; }
        public string? Error { get; set; }
        public string? Prompt { get; set; }
        public string? Model { get; set; }
        public DateTime GeneratedAt { get; set; }
    }

    /// <summary>
    /// Client for Google Gemini / Nano Banana image generation API.
    ///
    /// REST body uses camelCase field names per
    /// https://ai.google.dev/gemini-api/docs/image-generation — SA_Banana's
    /// original snake_case was SDK-style and would have been partially
    /// ignored by the REST endpoint.
    ///
    /// Authentication: the API key rides in the <c>x-goog-api-key</c>
    /// request header, NOT in the URL query string. URL-embedded secrets
    /// leak into proxy access logs, browser history, exception messages
    /// that echo full URLs, and diagnostic traces far more readily than
    /// request headers. The key never appears in constructed URLs.
    ///
    /// Cooperative cancellation: all network awaits accept a
    /// <see cref="CancellationToken"/>. Bridge trampolines pass a token
    /// that fires when the 180 s vision timeout hits — this stops the
    /// outbound Gemini request rather than letting it continue spending
    /// API quota after the caller has already seen failure.
    /// </summary>
    public class GeminiClient
    {
        private const string ApiKeyHeader = "x-goog-api-key";
        private readonly HttpClient _httpClient;
        private const string BaseUrl =
            "https://generativelanguage.googleapis.com/v1beta/models";

        public GeminiClient()
        {
            _httpClient = new HttpClient
            {
                Timeout = TimeSpan.FromMinutes(5)
            };
        }

        /// <summary>
        /// Image-generation models exposed to the UI and agent surface.
        /// Only paid-tier models are offered — API keys cannot use
        /// free-tier generation endpoints, so listing free-tier models
        /// would only confuse users with 429s on every call.
        ///
        /// Two classes of identifier:
        /// <list type="bullet">
        ///   <item><b>Short names</b> (<c>"nano-banana-2"</c>,
        ///         <c>"nano-banana-pro"</c>) — what the UI sends. Stable
        ///         across Gemini model version bumps.</item>
        ///   <item><b>Full IDs</b> (<c>"gemini-3.1-flash-image-preview"</c>,
        ///         <c>"gemini-3-pro-image-preview"</c>) — what the
        ///         Gemini REST API expects in the URL. Will change as
        ///         Google GA's and retires preview endpoints.</item>
        /// </list>
        /// <see cref="ResolveShortName"/> performs the short→full lookup
        /// and passes through anything not in the short-name map, so
        /// power users can still request newer models by full ID at
        /// their own risk.
        /// </summary>
        public static class Models
        {
            /// <summary>Nano Banana 2 — fast, high quality
            /// (Gemini 3.1 Flash Image, paid tier).</summary>
            public const string NanoBanana2 = "gemini-3.1-flash-image-preview";

            /// <summary>Nano Banana Pro — highest quality
            /// (Gemini 3 Pro Image, paid tier).</summary>
            public const string NanoBananaPro = "gemini-3-pro-image-preview";

            /// <summary>Full Gemini model ID used when no model is
            /// specified. Exposed for agent-path consumers who bypass
            /// the short-name mapping.</summary>
            public const string Default = NanoBanana2;

            /// <summary>Short-name key for <see cref="Default"/>.
            /// UI dropdowns use short names so display labels stay
            /// stable across model version bumps.</summary>
            public const string DefaultShortName = "nano-banana-2";

            /// <summary>Map short name → full Gemini model ID. Entries
            /// here drive both UI dropdown population (via
            /// <see cref="AvailableModels"/>) and backend resolution
            /// (via <see cref="ResolveShortName"/>).</summary>
            public static readonly IReadOnlyDictionary<string, string> ShortNameToId =
                new Dictionary<string, string>(StringComparer.Ordinal)
                {
                    ["nano-banana-2"] = NanoBanana2,
                    ["nano-banana-pro"] = NanoBananaPro,
                };

            /// <summary>UI-facing catalog — one entry per user-selectable
            /// model, with a human label + one-line description. Order is
            /// the display order (default first). The dropdown is
            /// populated from this list via
            /// <c>get_settings_overview</c>.</summary>
            public static readonly IReadOnlyList<IReadOnlyDictionary<string, object?>> AvailableModels =
                new List<IReadOnlyDictionary<string, object?>>
                {
                    new Dictionary<string, object?>
                    {
                        ["short_name"] = "nano-banana-2",
                        ["label"] = "Nano Banana 2",
                        ["description"] = "Fast, high quality",
                        ["supported_resolutions"] = new[] { "512", "1K", "2K", "4K" },
                    },
                    new Dictionary<string, object?>
                    {
                        ["short_name"] = "nano-banana-pro",
                        ["label"] = "Nano Banana Pro",
                        ["description"] = "Highest quality",
                        ["supported_resolutions"] = new[] { "1K", "2K", "4K" },
                    },
                };

            /// <summary>Resolve a short name or full ID to the Gemini
            /// model identifier that belongs in the request URL. Null /
            /// empty returns <see cref="Default"/>; anything not in
            /// <see cref="ShortNameToId"/> passes through unchanged so
            /// power users can target newer models.</summary>
            public static string ResolveShortName(string? nameOrId)
            {
                if (string.IsNullOrEmpty(nameOrId)) return Default;
                return ShortNameToId.TryGetValue(nameOrId!, out var fullId)
                    ? fullId
                    : nameOrId!;
            }
        }

        public async Task<GenerationResult> GenerateImageAsync(
            string apiKey,
            string prompt,
            byte[]? viewportCapture = null,
            string[]? referenceImages = null,
            string model = Models.Default,
            string resolution = "1K",
            string? aspectRatio = null,
            CancellationToken cancellationToken = default)
        {
            try
            {
                // API key rides in x-goog-api-key header, NOT in URL.
                var url = $"{BaseUrl}/{model}:generateContent";

                // Part order: 1) prompt, 2) reference/style images, 3)
                // viewport capture last. Last image determines aspect
                // ratio, and viewport is the "subject" to transform.
                var parts = new List<object>
                {
                    new { text = prompt }
                };

                if (referenceImages != null && referenceImages.Length > 0)
                {
                    foreach (var refImage in referenceImages)
                    {
                        if (!string.IsNullOrEmpty(refImage))
                        {
                            parts.Add(new
                            {
                                inlineData = new
                                {
                                    mimeType = "image/png",
                                    data = refImage
                                }
                            });
                        }
                    }
                }

                if (viewportCapture != null && viewportCapture.Length > 0)
                {
                    parts.Add(new
                    {
                        inlineData = new
                        {
                            mimeType = "image/png",
                            data = Convert.ToBase64String(viewportCapture)
                        }
                    });
                }

                var imageConfig = BuildImageConfig(resolution, aspectRatio);

                var requestDict = new Dictionary<string, object>
                {
                    ["contents"] = new[]
                    {
                        new Dictionary<string, object> { ["parts"] = parts }
                    },
                    ["generationConfig"] = new Dictionary<string, object>
                    {
                        ["responseModalities"] = new[] { "IMAGE" },
                        ["imageConfig"] = imageConfig
                    }
                };

                var jsonOptions = new JsonSerializerOptions
                {
                    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
                };

                var json = JsonSerializer.Serialize(requestDict, jsonOptions);

                RhinoApp.WriteLine($"Rook Vision: Sending request to {model}...");

                using var request = new HttpRequestMessage(HttpMethod.Post, url)
                {
                    Content = new StringContent(json, Encoding.UTF8, "application/json"),
                };
                request.Headers.Add(ApiKeyHeader, apiKey);

                var response = await _httpClient.SendAsync(request, cancellationToken)
                    .ConfigureAwait(false);
                var responseJson = await response.Content.ReadAsStringAsync()
                    .ConfigureAwait(false);

                if (!response.IsSuccessStatusCode)
                {
                    RhinoApp.WriteLine($"Rook Vision: API Error: {response.StatusCode}");
                    return new GenerationResult
                    {
                        Success = false,
                        Error = $"API Error ({response.StatusCode}): {responseJson}",
                        Prompt = prompt,
                        Model = model,
                        GeneratedAt = DateTime.Now
                    };
                }

                var geminiResponse = JsonSerializer.Deserialize<GeminiResponse>(
                    responseJson, new JsonSerializerOptions
                    {
                        PropertyNameCaseInsensitive = true
                    });

                var (imageData, mimeType) = ExtractImageFromResponse(geminiResponse);

                if (imageData == null)
                {
                    return new GenerationResult
                    {
                        Success = false,
                        Error = "No image in response",
                        Prompt = prompt,
                        Model = model,
                        GeneratedAt = DateTime.Now
                    };
                }

                RhinoApp.WriteLine("Rook Vision: Image generated successfully.");

                return new GenerationResult
                {
                    Success = true,
                    ImageBase64 = imageData,
                    ImageMimeType = mimeType ?? "image/png",
                    Prompt = prompt,
                    Model = model,
                    GeneratedAt = DateTime.Now
                };
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                // Bridge timeout cancelled us — don't swallow as generic error.
                return new GenerationResult
                {
                    Success = false,
                    Error = "Request cancelled (bridge timeout).",
                    Prompt = prompt,
                    Model = model,
                    GeneratedAt = DateTime.Now
                };
            }
            catch (TaskCanceledException)
            {
                // HttpClient's own 5-min hard timeout fired.
                return new GenerationResult
                {
                    Success = false,
                    Error = "Request timed out. Try a simpler prompt or smaller resolution.",
                    Prompt = prompt,
                    Model = model,
                    GeneratedAt = DateTime.Now
                };
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"Rook Vision: Generation error: {ex.Message}");
                return new GenerationResult
                {
                    Success = false,
                    Error = ex.Message,
                    Prompt = prompt,
                    Model = model,
                    GeneratedAt = DateTime.Now
                };
            }
        }

        internal static Dictionary<string, object> BuildImageConfig(
            string resolution,
            string? aspectRatio)
        {
            var imageConfig = new Dictionary<string, object>
            {
                ["imageSize"] = string.IsNullOrWhiteSpace(resolution)
                    ? "1K"
                    : resolution.ToUpperInvariant()
            };

            if (!string.IsNullOrWhiteSpace(aspectRatio))
            {
                imageConfig["aspectRatio"] = aspectRatio!;
            }

            return imageConfig;
        }

        private (string? data, string? mimeType) ExtractImageFromResponse(GeminiResponse? response)
        {
            if (response?.Candidates == null) return (null, null);

            foreach (var candidate in response.Candidates)
            {
                if (candidate?.Content?.Parts == null) continue;

                foreach (var part in candidate.Content.Parts)
                {
                    if (part.InlineData?.Data != null)
                    {
                        return (part.InlineData.Data, part.InlineData.MimeType);
                    }
                }
            }

            return (null, null);
        }

        public async Task<bool> TestApiKeyAsync(
            string apiKey, CancellationToken cancellationToken = default)
        {
            try
            {
                var url = $"{BaseUrl}/{Models.Default}";
                using var request = new HttpRequestMessage(HttpMethod.Get, url);
                request.Headers.Add(ApiKeyHeader, apiKey);
                var response = await _httpClient.SendAsync(request, cancellationToken)
                    .ConfigureAwait(false);
                return response.IsSuccessStatusCode
                    || response.StatusCode == System.Net.HttpStatusCode.MethodNotAllowed;
            }
            catch
            {
                return false;
            }
        }

        #region Response Models

        // PropertyNameCaseInsensitive = true on the deserializer; these
        // PascalCase properties match Gemini's camelCase JSON fields
        // (candidates, content, parts, inlineData, mimeType, data).
        internal class GeminiResponse
        {
            public GeminiCandidate[]? Candidates { get; set; }
        }

        internal class GeminiCandidate
        {
            public GeminiContent? Content { get; set; }
        }

        internal class GeminiContent
        {
            public GeminiPart[]? Parts { get; set; }
        }

        internal class GeminiPart
        {
            public string? Text { get; set; }
            public GeminiInlineData? InlineData { get; set; }
        }

        internal class GeminiInlineData
        {
            public string? MimeType { get; set; }
            public string? Data { get; set; }
        }

        #endregion
    }
}
