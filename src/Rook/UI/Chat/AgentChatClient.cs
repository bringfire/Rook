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

    public class ChatEvent
    {
        public string Type { get; set; } = "";
        public string? Content { get; set; }
        public string? Name { get; set; }
        public JsonElement? Params { get; set; }
        public string? Result { get; set; }
        public JsonElement? Usage { get; set; }

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

        public AgentChatClient()
        {
            _client = new HttpClient();
            _client.Timeout = TimeSpan.FromMinutes(5); // Long timeout for streaming
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
