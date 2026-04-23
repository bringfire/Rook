using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rhino;

namespace Rook.Services.Vision
{
    /// <summary>
    /// Result of a prompt-enhancement call.
    /// </summary>
    public sealed class PromptEnhanceResult
    {
        public bool Success { get; set; }
        public string? OriginalPrompt { get; set; }
        public string? EnhancedPrompt { get; set; }
        public string? StructuredJson { get; set; }
        public string? Error { get; set; }
    }

    /// <summary>
    /// Uses a Gemini text model to expand a short user prompt into a
    /// structured JSON prompt suitable for Nano Banana image generation,
    /// with an enforced camera-preservation directive so the generated
    /// image respects the source viewport's framing.
    ///
    /// Image mode only — video modes (VideoT2V/VideoI2V/VideoInterp) are
    /// intentionally not ported; they belong with the deferred video track.
    ///
    /// REST body uses camelCase (systemInstruction, generationConfig,
    /// maxOutputTokens) per
    /// https://ai.google.dev/gemini-api/docs/text-generation. Accepts a
    /// CancellationToken wired to the bridge's async timeout so the outbound
    /// request is cancelled rather than left to run past the deadline.
    ///
    /// Authentication: the API key rides in the <c>x-goog-api-key</c>
    /// request header, NOT in the URL. Same rationale as GeminiClient —
    /// URL secrets leak into proxy logs, diagnostics, and exception text
    /// more readily than headers.
    /// </summary>
    public class PromptEnhancer
    {
        private const string ApiKeyHeader = "x-goog-api-key";
        private readonly HttpClient _httpClient;
        private const string BaseUrl =
            "https://generativelanguage.googleapis.com/v1beta/models";

        // Text-only model for prompt enhancement. Gemini 2.0 Flash retired
        // March 2026; 2.5 Flash is the current text model.
        private const string TextModel = "gemini-2.5-flash";

        private const string CameraPreservationDirective =
            "Maintain the EXACT camera angle, perspective, framing, and " +
            "composition of the source image. Do NOT change the viewpoint, " +
            "do NOT reframe, do NOT alter proportions.";

        private const string SystemPrompt =
@"You are a JSON prompt engineer for Gemini Nano Banana image generation. Generate structured JSON prompts following this exact format.

## OUTPUT FORMAT
Return ONLY valid JSON with NO markdown code blocks, NO explanations. Just the raw JSON object.

## JSON STRUCTURE
{
  ""subject"": ""[user's core concept and description]"",
  ""camera_constraint"": ""[ALWAYS include: preserve exact camera angle and composition]"",
  ""style"": {
    ""primary"": ""[photorealistic/cinematic/painterly - use what user specified or photorealistic for architecture]"",
    ""rendering_quality"": ""[ultra-realistic, high fidelity]"",
    ""lighting"": ""[user's lighting or appropriate default]""
  },
  ""materials"": {
    ""primary"": ""[main materials visible]"",
    ""texture"": ""[surface quality details]""
  },
  ""environment"": {
    ""time_of_day"": ""[from user or inferred]"",
    ""weather"": ""[atmospheric conditions]"",
    ""atmosphere"": ""[mood descriptors]""
  },
  ""quality"": {
    ""resolution"": ""ultra high resolution"",
    ""detail"": ""[detail level descriptors]""
  }
}

## RULES
1. PRESERVE everything the user specified - copy their exact words into appropriate fields
2. The ""subject"" field contains the user's full description
3. The ""camera_constraint"" field ALWAYS says to preserve camera angle
4. Fill every field - use reasonable defaults for architectural visualization when details aren't provided
5. Return compact JSON (no extra whitespace)
6. Never wrap in markdown code blocks

## EXAMPLE INPUT
""Modern glass building with warm sunset lighting""

## EXAMPLE OUTPUT
{""subject"":""Modern glass building with warm sunset lighting, architectural visualization"",""camera_constraint"":""Preserve the exact camera angle, perspective, and framing of the source image. Do not change viewpoint or reframe."",""style"":{""primary"":""photorealistic"",""rendering_quality"":""ultra-realistic, high fidelity"",""lighting"":""warm sunset lighting, golden hour""},""materials"":{""primary"":""glass curtain wall, polished surfaces"",""texture"":""pristine, reflective""},""environment"":{""time_of_day"":""sunset"",""weather"":""clear skies"",""atmosphere"":""warm, serene""},""quality"":{""resolution"":""ultra high resolution"",""detail"":""architectural visualization quality""}}";

        public PromptEnhancer()
        {
            _httpClient = new HttpClient
            {
                Timeout = TimeSpan.FromSeconds(30)
            };
        }

        public async Task<PromptEnhanceResult> EnhancePromptAsync(
            string apiKey,
            string userPrompt,
            string? context = null,
            CancellationToken cancellationToken = default)
        {
            try
            {
                // API key rides in x-goog-api-key header, NOT in URL.
                var url = $"{BaseUrl}/{TextModel}:generateContent";

                var userFraming = string.IsNullOrEmpty(context)
                    ? $"Transform this prompt for Nano Banana image generation:\n\n\"{userPrompt}\""
                    : $"Transform this prompt for Nano Banana image generation:\n\nContext: {context}\nPrompt: \"{userPrompt}\"";

                var request = new
                {
                    systemInstruction = new
                    {
                        parts = new[] { new { text = SystemPrompt } }
                    },
                    contents = new[]
                    {
                        new { parts = new[] { new { text = userFraming } } }
                    },
                    generationConfig = new
                    {
                        temperature = 0.7,
                        maxOutputTokens = 1024
                    }
                };

                var json = JsonSerializer.Serialize(request);

                RhinoApp.WriteLine("Rook Vision: Enhancing prompt...");

                using var httpReq = new HttpRequestMessage(HttpMethod.Post, url)
                {
                    Content = new StringContent(json, Encoding.UTF8, "application/json"),
                };
                httpReq.Headers.Add(ApiKeyHeader, apiKey);

                var response = await _httpClient.SendAsync(httpReq, cancellationToken)
                    .ConfigureAwait(false);
                var responseJson = await response.Content.ReadAsStringAsync()
                    .ConfigureAwait(false);

                if (!response.IsSuccessStatusCode)
                {
                    return new PromptEnhanceResult
                    {
                        Success = false,
                        Error = $"API Error ({response.StatusCode}): {responseJson}",
                        OriginalPrompt = userPrompt,
                    };
                }

                var geminiResponse = JsonSerializer.Deserialize<JsonElement>(responseJson);
                var enhancedPrompt = ExtractTextFromResponse(geminiResponse);

                if (string.IsNullOrEmpty(enhancedPrompt))
                {
                    return new PromptEnhanceResult
                    {
                        Success = false,
                        Error = "No response from prompt enhancer",
                        OriginalPrompt = userPrompt,
                    };
                }

                enhancedPrompt = CleanJsonResponse(enhancedPrompt!);
                var finalPrompt = BuildFinalJsonPrompt(enhancedPrompt, userPrompt);

                RhinoApp.WriteLine("Rook Vision: Prompt enhanced.");

                return new PromptEnhanceResult
                {
                    Success = true,
                    OriginalPrompt = userPrompt,
                    EnhancedPrompt = finalPrompt,
                    StructuredJson = finalPrompt,
                };
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                return new PromptEnhanceResult
                {
                    Success = false,
                    Error = "Request cancelled (bridge timeout).",
                    OriginalPrompt = userPrompt,
                };
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"Rook Vision: Prompt enhancement error: {ex.Message}");
                return new PromptEnhanceResult
                {
                    Success = false,
                    Error = ex.Message,
                    OriginalPrompt = userPrompt,
                };
            }
        }

        private static string? ExtractTextFromResponse(JsonElement response)
        {
            try
            {
                if (response.TryGetProperty("candidates", out var candidates) &&
                    candidates.GetArrayLength() > 0)
                {
                    var first = candidates[0];
                    if (first.TryGetProperty("content", out var content) &&
                        content.TryGetProperty("parts", out var parts) &&
                        parts.GetArrayLength() > 0)
                    {
                        var firstPart = parts[0];
                        if (firstPart.TryGetProperty("text", out var text))
                        {
                            return text.GetString();
                        }
                    }
                }
            }
            catch { /* fall through */ }
            return null;
        }

        internal static string CleanJsonResponse(string response)
        {
            response = response.Trim();

            if (response.StartsWith("```json", StringComparison.Ordinal))
                response = response.Substring(7);
            else if (response.StartsWith("```", StringComparison.Ordinal))
                response = response.Substring(3);

            if (response.EndsWith("```", StringComparison.Ordinal))
                response = response.Substring(0, response.Length - 3);

            response = response.Trim();

            var startIndex = response.IndexOf('{');
            var endIndex = response.LastIndexOf('}');
            if (startIndex >= 0 && endIndex > startIndex)
            {
                response = response.Substring(startIndex, endIndex - startIndex + 1);
            }

            return response.Trim();
        }

        internal static string BuildFinalJsonPrompt(string jsonPrompt, string originalPrompt)
        {
            try
            {
                JsonSerializer.Deserialize<JsonElement>(jsonPrompt);
                return jsonPrompt;
            }
            catch
            {
                RhinoApp.WriteLine(
                    "Rook Vision: JSON parsing failed, using fallback structure.");

                var fallback = new
                {
                    subject = originalPrompt,
                    camera_constraint = CameraPreservationDirective,
                    style = new
                    {
                        primary = "photorealistic",
                        rendering_quality = "ultra-realistic, high fidelity"
                    },
                    quality = new
                    {
                        resolution = "ultra high resolution",
                        detail = "professional architectural visualization"
                    }
                };

                return JsonSerializer.Serialize(fallback, new JsonSerializerOptions
                {
                    WriteIndented = false
                });
            }
        }
    }
}
