using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.UI.Chat
{
    /// <summary>
    /// Data models for agent chat responses.
    /// </summary>
    public class PersonaInfo
    {
        public string Persona { get; set; } = "";
        public string Label { get; set; } = "";
        public string Description { get; set; } = "";
        public string Color { get; set; } = "#1d9bf0";

        [JsonPropertyName("model_role")]
        public string ModelRole { get; set; } = "worker";
    }

    public class ConversationInfo
    {
        [JsonPropertyName("conversation_id")]
        public string ConversationId { get; set; } = "";

        public string Persona { get; set; } = "";
        public string Label { get; set; } = "";
        public string Color { get; set; } = "#1d9bf0";
        public string Model { get; set; } = "";

        [JsonPropertyName("tool_access")]
        public string ToolAccess { get; set; } = "full";

        [JsonPropertyName("documentSerialNumber")]
        public uint DocumentSerialNumber { get; set; }

        [JsonIgnore]
        public Uri? BaseUri { get; set; }
    }

    public class ChatConversationModelInfo
    {
        [JsonPropertyName("conversation_id")]
        public string ConversationId { get; set; } = "";

        public string Persona { get; set; } = "";

        [JsonPropertyName("active_model")]
        public string? ActiveModel { get; set; }

        [JsonPropertyName("active_routing")]
        public string? ActiveRouting { get; set; }

        [JsonPropertyName("pending_model")]
        public string? PendingModel { get; set; }

        [JsonPropertyName("pending_routing")]
        public string? PendingRouting { get; set; }

        [JsonPropertyName("pending_applies_to")]
        public string? PendingAppliesTo { get; set; }

        [JsonPropertyName("api_base_source")]
        public string? ApiBaseSource { get; set; }
    }

    public class ChatModelsInfo
    {
        [JsonPropertyName("conversation")]
        public ChatConversationModelInfo? Conversation { get; set; }

        [JsonPropertyName("allowed_model_overrides")]
        public List<string> AllowedModelOverrides { get; set; } = new();
    }

    /// <summary>
    /// Outcome of POST /agent/chat/model. Success reflects HTTP 2xx, not any body
    /// envelope; known error fields are parsed opportunistically.
    /// </summary>
    public class SetModelResult
    {
        public bool Success { get; set; }
        public int StatusCode { get; set; }
        public string? ErrorCode { get; set; }
        public string? Message { get; set; }
        public List<string>? AllowedModelOverrides { get; set; }
    }

    public class ChatEvent
    {
        public string Type { get; set; } = "";
        public string? Content { get; set; }
        public string? Name { get; set; }
        public string? Model { get; set; }
        public JsonElement? Params { get; set; }
        public string? Result { get; set; }
        public JsonElement? Usage { get; set; }

        [JsonPropertyName("applies_to")]
        public string? AppliesTo { get; set; }

        [JsonPropertyName("tool_call_id")]
        public string? ToolCallId { get; set; }

        // ── Adaptive UI fields ──

        [JsonPropertyName("block_id")]
        public string? BlockId { get; set; }

        [JsonPropertyName("block_type")]
        public string? BlockType { get; set; }

        [JsonPropertyName("block_config")]
        public JsonElement? BlockConfig { get; set; }

        public bool? Verified { get; set; }

        [JsonPropertyName("verification_note")]
        public string? VerificationNote { get; set; }
    }

    /// <summary>
    /// HTTP client for the Rhino-owned agent chat service.
    /// </summary>
    public class AgentChatClient : IDisposable
    {
        private readonly HttpClient _client;

        private static readonly JsonSerializerOptions JsonOptions = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        };

        private const string SessionHeaderName = "X-Rook-Session";

        public AgentChatClient()
        {
            _client = new HttpClient();
            _client.Timeout = TimeSpan.FromMinutes(5); // Long timeout for streaming
        }

        /// <summary>
        /// Attach the session nonce so all subsequent requests include it.
        /// Called once the chat service is started and the nonce is available.
        /// </summary>
        public void SetSessionNonce(string nonce)
        {
            _client.DefaultRequestHeaders.Remove(SessionHeaderName);
            if (!string.IsNullOrEmpty(nonce))
                _client.DefaultRequestHeaders.Add(SessionHeaderName, nonce);
        }

        private async Task<Uri> GetBaseUriAsync(bool startIfNeeded, CancellationToken ct = default)
        {
            var health = await ChatServiceManager.Instance.GetHealthAsync(startIfNeeded, ct);
            if (!health.ServiceAvailable || health.BaseUri == null)
            {
                throw new InvalidOperationException(health.ServiceMessage);
            }
            return health.BaseUri;
        }

        public Task<ChatServiceHealth> GetHealthAsync(bool startIfNeeded, CancellationToken ct = default)
        {
            return ChatServiceManager.Instance.GetHealthAsync(startIfNeeded, ct);
        }

        public async Task<ChatServiceHealth> GetHealthAsync(Uri baseUri, CancellationToken ct = default)
        {
            return await ChatServiceManager.Instance.GetHealthForBaseUriAsync(baseUri, ct);
        }

        /// <summary>
        /// Get available personas.
        /// </summary>
        public async Task<List<PersonaInfo>> GetPersonasAsync(CancellationToken ct = default)
        {
            var baseUri = await GetBaseUriAsync(startIfNeeded: true, ct);
            var resp = await _client.GetAsync(new Uri(baseUri, "/agent/chat/personas"), ct);
            resp.EnsureSuccessStatusCode();
            var json = await resp.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<List<PersonaInfo>>(json, JsonOptions)
                   ?? new List<PersonaInfo>();
        }

        /// <summary>
        /// Start a new conversation.
        /// </summary>
        public async Task<ConversationInfo> StartAsync(
            string persona,
            uint documentSerialNumber = 0,
            CancellationToken ct = default)
        {
            var baseUri = await GetBaseUriAsync(startIfNeeded: true, ct);
            var body = JsonSerializer.Serialize(new
            {
                persona,
                documentSerialNumber,
            });
            var content = new StringContent(body, Encoding.UTF8, "application/json");
            var resp = await _client.PostAsync(new Uri(baseUri, "/agent/chat/start"), content, ct);
            resp.EnsureSuccessStatusCode();
            var json = await resp.Content.ReadAsStringAsync();
            var info = JsonSerializer.Deserialize<ConversationInfo>(json, JsonOptions)
                       ?? new ConversationInfo();
            info.BaseUri = baseUri;
            return info;
        }

        public async Task<ChatModelsInfo> GetModelsAsync(
            Uri baseUri,
            string? conversationId = null,
            CancellationToken ct = default)
        {
            var path = "/agent/chat/models";
            if (!string.IsNullOrEmpty(conversationId))
            {
                path += "?conversation_id=" + Uri.EscapeDataString(conversationId);
            }

            var resp = await _client.GetAsync(new Uri(baseUri, path), ct);
            resp.EnsureSuccessStatusCode();
            var json = await resp.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<ChatModelsInfo>(json, JsonOptions)
                   ?? new ChatModelsInfo();
        }

        /// <summary>
        /// Pure parse of a /agent/chat/model response. Success is HTTP-2xx-derived;
        /// the body is parsed opportunistically and never throws on malformed JSON.
        /// </summary>
        internal static SetModelResult ParseSetModelResult(int statusCode, bool isSuccess, string body)
        {
            var result = new SetModelResult
            {
                Success = isSuccess,
                StatusCode = statusCode,
            };

            if (string.IsNullOrWhiteSpace(body))
                return result;

            try
            {
                using var doc = JsonDocument.Parse(body);
                var root = doc.RootElement;
                if (root.ValueKind == JsonValueKind.Object)
                {
                    if (root.TryGetProperty("code", out var code) && code.ValueKind == JsonValueKind.String)
                        result.ErrorCode = code.GetString();
                    if (root.TryGetProperty("error", out var err) && err.ValueKind == JsonValueKind.String)
                        result.Message = err.GetString();
                    if (root.TryGetProperty("allowed_model_overrides", out var allowed)
                        && allowed.ValueKind == JsonValueKind.Array)
                    {
                        var list = new List<string>();
                        foreach (var item in allowed.EnumerateArray())
                        {
                            if (item.ValueKind == JsonValueKind.String)
                            {
                                var s = item.GetString();
                                if (!string.IsNullOrEmpty(s))
                                    list.Add(s!);
                            }
                        }
                        result.AllowedModelOverrides = list;
                    }
                }
            }
            catch (JsonException)
            {
                // Malformed body — keep HTTP-derived success/status, no error fields.
            }

            return result;
        }

        /// <summary>
        /// Apply a per-conversation model override via POST /agent/chat/model.
        /// The session nonce is auto-attached via the shared HttpClient headers.
        /// </summary>
        public async Task<SetModelResult> SetModelAsync(
            Uri baseUri,
            string conversationId,
            string modelOverride,
            string reason,
            CancellationToken ct = default)
        {
            var body = JsonSerializer.Serialize(new
            {
                conversation_id = conversationId,
                model_override = modelOverride,
                reason = reason,
            });
            var content = new StringContent(body, Encoding.UTF8, "application/json");
            var resp = await _client.PostAsync(new Uri(baseUri, "/agent/chat/model"), content, ct);
            var respBody = await resp.Content.ReadAsStringAsync();
            return ParseSetModelResult((int)resp.StatusCode, resp.IsSuccessStatusCode, respBody);
        }

        /// <summary>
        /// Send a message and yield streaming events.
        /// Uses HttpCompletionOption.ResponseHeadersRead for streaming.
        /// </summary>
        public async Task SendMessageStreamingAsync(
            Uri baseUri,
            string conversationId,
            string message,
            uint documentSerialNumber,
            Action<ChatEvent> onEvent,
            CancellationToken ct = default)
        {
            var body = JsonSerializer.Serialize(new
            {
                conversation_id = conversationId,
                message = message,
                documentSerialNumber = documentSerialNumber,
            });
            var request = new HttpRequestMessage(HttpMethod.Post, new Uri(baseUri, "/agent/chat/message"))
            {
                Content = new StringContent(body, Encoding.UTF8, "application/json")
            };

            using var resp = await _client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
            resp.EnsureSuccessStatusCode();

            using var stream = await resp.Content.ReadAsStreamAsync();
            using var reader = new StreamReader(stream, Encoding.UTF8);

            string? line;
            while ((line = await reader.ReadLineAsync()) != null)
            {
                if (ct.IsCancellationRequested) break;
                if (string.IsNullOrWhiteSpace(line)) continue;

                try
                {
                    var evt = JsonSerializer.Deserialize<ChatEvent>(line, JsonOptions);
                    if (evt != null)
                    {
                        onEvent(evt);
                    }
                }
                catch (JsonException)
                {
                    // Skip malformed lines
                }
            }
        }

        /// <summary>
        /// Submit a UI block response and yield the agent's reaction events as a stream.
        /// Mirrors SendMessageStreamingAsync but POSTs to /agent/chat/ui-response.
        /// Includes documentSerialNumber so Rhino tool calls in the agent's reaction
        /// stay scoped to the same document as a typed message would.
        /// </summary>
        public async Task SendUIResponseStreamingAsync(
            Uri baseUri,
            string conversationId,
            string blockId,
            object value,
            uint documentSerialNumber,
            Action<ChatEvent> onEvent,
            CancellationToken ct = default)
        {
            var body = JsonSerializer.Serialize(new
            {
                conversation_id = conversationId,
                block_id = blockId,
                value = value,
                documentSerialNumber = documentSerialNumber,
            });
            var request = new HttpRequestMessage(HttpMethod.Post, new Uri(baseUri, "/agent/chat/ui-response"))
            {
                Content = new StringContent(body, Encoding.UTF8, "application/json")
            };

            using var resp = await _client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
            resp.EnsureSuccessStatusCode();

            using var stream = await resp.Content.ReadAsStreamAsync();
            using var reader = new StreamReader(stream, Encoding.UTF8);

            string? line;
            while ((line = await reader.ReadLineAsync()) != null)
            {
                if (ct.IsCancellationRequested) break;
                if (string.IsNullOrWhiteSpace(line)) continue;

                try
                {
                    var evt = JsonSerializer.Deserialize<ChatEvent>(line, JsonOptions);
                    if (evt != null)
                    {
                        onEvent(evt);
                    }
                }
                catch (JsonException)
                {
                    // Skip malformed lines
                }
            }
        }

        /// <summary>
        /// Stop a conversation.
        /// </summary>
        public async Task StopAsync(string conversationId, CancellationToken ct = default)
        {
            var body = JsonSerializer.Serialize(new { conversation_id = conversationId });
            var content = new StringContent(body, Encoding.UTF8, "application/json");
            // Don't throw on failure (conversation may already be stopped)
            try
            {
                var baseUri = await GetBaseUriAsync(startIfNeeded: false, ct);
                var resp = await _client.PostAsync(new Uri(baseUri, "/agent/chat/stop"), content, ct);
                // Intentionally not calling EnsureSuccessStatusCode
            }
            catch
            {
                // Swallow errors — best-effort cleanup
            }
        }

        public async Task StopAsync(Uri baseUri, string conversationId, CancellationToken ct = default)
        {
            var body = JsonSerializer.Serialize(new { conversation_id = conversationId });
            var content = new StringContent(body, Encoding.UTF8, "application/json");
            try
            {
                var resp = await _client.PostAsync(new Uri(baseUri, "/agent/chat/stop"), content, ct);
            }
            catch
            {
                // Swallow errors — best-effort cleanup
            }
        }

        /// <summary>
        /// Check if the agent chat server is reachable.
        /// </summary>
        public async Task<bool> IsAvailableAsync()
        {
            try
            {
                var health = await GetHealthAsync(startIfNeeded: true);
                return health.ServiceAvailable;
            }
            catch
            {
                return false;
            }
        }

        public void Dispose()
        {
            _client.Dispose();
        }
    }
}
