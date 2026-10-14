using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;

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
        public string? Provider { get; set; }
        public string? Model { get; set; }
        public bool FallbackUsed { get; set; }
        public string? FallbackReason { get; set; }
    }

    /// <summary>
    /// Uses Gemini directly, or through fal when Google credentials are missing or rejected, to expand a short user prompt into a
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
    /// request header, NOT in the URL. Same rationale as image generation —
    /// URL secrets leak into proxy logs, diagnostics, and exception text
    /// more readily than headers.
    /// </summary>
    public class PromptEnhancer
    {
        private const string ApiKeyHeader = "x-goog-api-key";
        private readonly HttpClient _httpClient;
        private readonly FalApiClient _falClient;
        private readonly Func<TimeSpan, CancellationTokenSource> _deadlineFactory;
        private const string FalTextModel = "google/gemini-2.5-flash";
        private static readonly Uri FalTextEndpoint = new("https://fal.run/openrouter/router");
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
            : this(new HttpClient { Timeout = Timeout.InfiniteTimeSpan })
        { }

        internal PromptEnhancer(HttpClient httpClient,
            Func<TimeSpan, CancellationTokenSource>? deadlineFactory = null)
        {
            _httpClient = httpClient ?? throw new ArgumentNullException(nameof(httpClient));
            _falClient = new FalApiClient(_httpClient);
            _deadlineFactory = deadlineFactory ?? (timeout => new CancellationTokenSource(timeout));
        }

        // Explicit credential probes must only contact Google: fal success cannot validate a Google key.
        public Task<PromptEnhanceResult> EnhancePromptAsync(string apiKey, string userPrompt,
            string? context = null, CancellationToken cancellationToken = default) =>
            ExecuteAsync(apiKey, null, userPrompt, context, allowFallback: false, cancellationToken);

        public Task<PromptEnhanceResult> EnhanceWithFallbackAsync(string? geminiKey, string? falKey,
            string userPrompt, string? context = null, CancellationToken cancellationToken = default) =>
            EnhanceWithFallbackAsync(geminiKey, () => falKey, userPrompt, context, cancellationToken);

        internal Task<PromptEnhanceResult> EnhanceWithFallbackAsync(string? geminiKey, Func<string?> falKey,
            string userPrompt, string? context, CancellationToken cancellationToken) =>
            ExecuteAsync(geminiKey, falKey, userPrompt, context, allowFallback: true, cancellationToken);

        private async Task<PromptEnhanceResult> ExecuteAsync(string? geminiKey, Func<string?>? falKeyProvider,
            string userPrompt, string? context, bool allowFallback, CancellationToken cancellationToken)
        {
            // One timer owns both attempts and response parsing. Record the first observed stop.
            using var deadline = _deadlineFactory(TimeSpan.FromSeconds(30));
            using var stopped = new CancellationTokenSource();
            var stopReason = 0; // 1 = caller cancellation, 2 = deadline
            void Stop(int reason)
            {
                if (Interlocked.CompareExchange(ref stopReason, reason, 0) == 0) stopped.Cancel();
            }
            using var callerRegistration = cancellationToken.Register(() => Stop(1));
            using var deadlineRegistration = deadline.Token.Register(() => Stop(2));
            var ct = stopped.Token;
            var result = new PromptEnhanceResult { OriginalPrompt = userPrompt, Provider = "gemini", Model = TextModel };
            try
            {
                ct.ThrowIfCancellationRequested();
                var framing = string.IsNullOrEmpty(context)
                    ? $"Transform this prompt for Nano Banana image generation:\n\n\"{userPrompt}\""
                    : $"Transform this prompt for Nano Banana image generation:\n\nContext: {context}\nPrompt: \"{userPrompt}\"";
                TextResponse? primary = null;
                if (!string.IsNullOrWhiteSpace(geminiKey))
                    primary = await AwaitAsync(SendGoogleAsync(geminiKey!, framing, ct), ct).ConfigureAwait(false);
                ct.ThrowIfCancellationRequested();
                TextResponse response;
                if (allowFallback && (primary == null || primary.KeyRejected))
                {
                    result.Provider = "fal";
                    result.Model = FalTextModel;
                    result.FallbackUsed = true;
                    result.FallbackReason = primary == null ? "gemini_key_missing" : "gemini_key_rejected";
                    var falKey = falKeyProvider?.Invoke();
                    if (string.IsNullOrWhiteSpace(falKey))
                    {
                        result.Error = primary == null
                            ? "Configure a Gemini or fal.ai API key in Vision settings before calling /vision/enhance-prompt."
                            : "Gemini API key was rejected. Configure a fal.ai API key in Vision settings to enhance prompts.";
                        return result;
                    }
                    ct.ThrowIfCancellationRequested();
                    response = await AwaitAsync(SendFalAsync(falKey!, framing, ct), ct).ConfigureAwait(false);
                }
                else response = primary ?? new(false, null, false, "Gemini API key is not configured.");
                ct.ThrowIfCancellationRequested();
                if (!response.Success)
                {
                    result.Error = response.Error;
                    return result;
                }
                var json = BuildFinalJsonPrompt(CleanJsonResponse(response.Output!), userPrompt);
                ct.ThrowIfCancellationRequested();
                result.Success = true;
                result.EnhancedPrompt = result.StructuredJson = json;
                return result;
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                result.Error = Volatile.Read(ref stopReason) == 2
                    ? "Prompt enhancement timed out after 30 seconds."
                    : "Prompt enhancement cancelled.";
                return result;
            }
            catch (JsonException)
            {
                result.Error = ProviderLabel(result.Provider) + " returned an invalid structured prompt.";
                return result;
            }
            catch (Exception)
            {
                // Provider bodies, exception text and credentials never enter errors or artifacts.
                result.Error = ProviderLabel(result.Provider) + " prompt enhancement request failed.";
                return result;
            }
        }

        private sealed record TextResponse(bool Success, string? Output, bool KeyRejected, string? Error);
        private static string ProviderLabel(string? provider) => provider == "fal" ? "fal.ai" : "Google AI";

        private async Task<TextResponse> SendGoogleAsync(string key, string framing, CancellationToken ct)
        {
            var payload = new
            {
                systemInstruction = new { parts = new[] { new { text = SystemPrompt } } },
                contents = new[] { new { parts = new[] { new { text = framing } } } },
                generationConfig = new { temperature = 0.7, maxOutputTokens = 1024 }
            };
            using var request = new HttpRequestMessage(HttpMethod.Post, $"{BaseUrl}/{TextModel}:generateContent")
            {
                Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json")
            };
            request.Headers.Add(ApiKeyHeader, key);
            using var response = await _httpClient.SendAsync(request, ct).ConfigureAwait(false);
            var body = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
            ct.ThrowIfCancellationRequested();
            if (!response.IsSuccessStatusCode)
            {
                JsonObject? error = null;
                try { error = (JsonNode.Parse(body) as JsonObject)?["error"] as JsonObject; } catch (JsonException) { }
                var rejected = GoogleCredentialErrors.IsRejectedKey(response.StatusCode, error);
                return new(false, null, rejected, rejected ? "Gemini API key was rejected."
                    : $"Google AI prompt enhancement failed (HTTP {(int)response.StatusCode}).");
            }
            using var doc = JsonDocument.Parse(body);
            var root = doc.RootElement;
            if (root.TryGetProperty("candidates", out var candidates) && candidates.ValueKind == JsonValueKind.Array &&
                candidates.GetArrayLength() > 0 && candidates[0].TryGetProperty("finishReason", out var finish) &&
                finish.GetString() != "STOP")
                return new(false, null, false, "Google AI returned an incomplete or blocked prompt.");
            var output = ExtractTextFromResponse(root);
            return string.IsNullOrWhiteSpace(output)
                ? new(false, null, false, "Google AI returned no enhanced prompt.")
                : new(true, output, false, null);
        }

        private async Task<TextResponse> SendFalAsync(string key, string framing, CancellationToken ct)
        {
            var payload = JsonSerializer.Serialize(new
            {
                prompt = framing, system_prompt = SystemPrompt, model = FalTextModel,
                reasoning = false, temperature = 0.7, max_tokens = 1024, enable_web_search = false
            });
            var response = await _falClient.PostJsonAsync(key, FalTextEndpoint, payload, ct).ConfigureAwait(false);
            ct.ThrowIfCancellationRequested();
            if (response.StatusCode < 200 || response.StatusCode >= 300)
                return new(false, null, false, response.StatusCode == 401 ? "fal.ai API key was rejected. Update it in Vision settings."
                    : $"fal.ai prompt enhancement failed (HTTP {response.StatusCode}).");
            using var doc = JsonDocument.Parse(response.Body);
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object ||
                (root.TryGetProperty("partial", out var partial) && partial.ValueKind != JsonValueKind.False) ||
                (root.TryGetProperty("error", out var error) && error.ValueKind != JsonValueKind.Null &&
                    (error.ValueKind != JsonValueKind.String || !string.IsNullOrEmpty(error.GetString()))) ||
                !root.TryGetProperty("output", out var output) || output.ValueKind != JsonValueKind.String ||
                string.IsNullOrWhiteSpace(output.GetString()))
                return new(false, null, false, "fal.ai returned an incomplete or failed prompt enhancement.");
            return new(true, output.GetString(), false, null);
        }

        private static async Task<T> AwaitAsync<T>(Task<T> task, CancellationToken ct)
        {
            var stopped = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            using var registration = ct.Register(() => stopped.TrySetResult(true));
            if (await Task.WhenAny(task, stopped.Task).ConfigureAwait(false) != task)
            {
                // A non-cooperative transport can finish later; its body and response stay owned by Send*Async.
                _ = task.ContinueWith(t => { _ = t.Exception; }, CancellationToken.None,
                    TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
                ct.ThrowIfCancellationRequested();
            }
            return await task.ConfigureAwait(false);
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
            if (JsonNode.Parse(jsonPrompt) is not JsonObject prompt ||
                prompt["subject"] is not JsonValue subject || !subject.TryGetValue<string>(out var text) ||
                string.IsNullOrWhiteSpace(text))
                throw new JsonException("Expected a structured prompt object with a subject.");
            // Apply locally even if the model ignores its system instructions.
            prompt["camera_constraint"] = CameraPreservationDirective;
            return prompt.ToJsonString();
        }
    }
}
