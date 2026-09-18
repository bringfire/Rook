using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.UI.Chat
{
    public sealed class CreateConversationRequest
    {
        public string HostGenerationId { get; set; } = "";
        public uint DocumentSerialNumber { get; set; }
        public int RouteProcessId { get; set; }
        public string? SavedDocumentDirectory { get; set; }
        public string? Model { get; set; }
        public string? Reasoning { get; set; }
    }

    public sealed class ConversationView
    {
        [JsonPropertyName("conversationId")]
        public string ConversationId { get; set; } = "";

        [JsonPropertyName("durable")]
        public bool Durable { get; set; }

        [JsonPropertyName("targetAvailable")]
        public bool TargetAvailable { get; set; }

        [JsonIgnore]
        public Uri? BaseUri { get; set; }
    }

    public sealed class ConversationSummary
    {
        [JsonPropertyName("conversationId")]
        public string ConversationId { get; set; } = "";

        [JsonPropertyName("primeSessionId")]
        public string PrimeSessionId { get; set; } = "";

        [JsonPropertyName("runtimeId")]
        public string RuntimeId { get; set; } = "";

        [JsonPropertyName("profile")]
        public string Profile { get; set; } = "";

        [JsonPropertyName("hostGenerationId")]
        public string HostGenerationId { get; set; } = "";

        [JsonPropertyName("documentSerialNumber")]
        public uint DocumentSerialNumber { get; set; }

        [JsonPropertyName("routeProcessId")]
        public int RouteProcessId { get; set; }

        [JsonPropertyName("requestedInitialModel")]
        public string? RequestedInitialModel { get; set; }

        [JsonPropertyName("requestedInitialReasoning")]
        public string? RequestedInitialReasoning { get; set; }
    }

    internal sealed class ConversationListEnvelope
    {
        [JsonPropertyName("conversations")]
        public List<ConversationSummary> Conversations { get; set; } = new();
    }

    public sealed class ChatImageInput
    {
        public ChatImageInput(string fileName, string mimeType, string base64Data)
        {
            FileName = fileName;
            MimeType = mimeType;
            Base64Data = base64Data;
        }

        [JsonPropertyName("fileName")]
        public string FileName { get; }

        [JsonPropertyName("mimeType")]
        public string MimeType { get; }

        [JsonPropertyName("base64Data")]
        public string Base64Data { get; }
    }

    public sealed class PresentationImage
    {
        [JsonPropertyName("fileName")]
        public string FileName { get; set; } = "";

        [JsonPropertyName("mimeType")]
        public string MimeType { get; set; } = "";

        [JsonPropertyName("width")]
        public int Width { get; set; }

        [JsonPropertyName("height")]
        public int Height { get; set; }

        [JsonPropertyName("binaryBytes")]
        public long BinaryByteCount { get; set; }

        [JsonPropertyName("sha256")]
        public string Sha256 { get; set; } = "";

        [JsonIgnore]
        public string? Base64Data => null;
    }

    public sealed class PresentationTurn
    {
        [JsonPropertyName("sequence")]
        public long Sequence { get; set; }

        [JsonPropertyName("userText")]
        public string UserText { get; set; } = "";

        [JsonPropertyName("assistantText")]
        public string AssistantText { get; set; } = "";

        [JsonPropertyName("stopReason")]
        public string StopReason { get; set; } = "";

        [JsonPropertyName("toolCards")]
        public List<JsonElement> ToolCards { get; set; } = new();

        [JsonPropertyName("images")]
        public List<PresentationImage> Images { get; set; } = new();

        [JsonPropertyName("message")]
        public string? Message { get; set; }

        [JsonPropertyName("fallback")]
        public bool Fallback { get; set; }
    }

    public sealed class PresentationHistory
    {
        [JsonPropertyName("available")]
        public bool Available { get; set; }

        [JsonPropertyName("turns")]
        public List<PresentationTurn> Turns { get; set; } = new();

        [JsonPropertyName("earlierHistoryOmitted")]
        public bool EarlierHistoryOmitted { get; set; }

        [JsonPropertyName("message")]
        public string? Message { get; set; }
    }

    public sealed class ChatEvent
    {
        [JsonPropertyName("type")]
        public string Type { get; set; } = "";

        [JsonPropertyName("sourceOrdinal")]
        public long? SourceOrdinal { get; set; }

        [JsonPropertyName("messageId")]
        public string? MessageId { get; set; }

        [JsonPropertyName("text")]
        public string? Text { get; set; }

        [JsonPropertyName("kind")]
        public string? Kind { get; set; }

        [JsonPropertyName("payload")]
        public JsonElement? Payload { get; set; }

        [JsonPropertyName("outcome")]
        public string? Outcome { get; set; }

        [JsonPropertyName("stopReason")]
        public string? StopReason { get; set; }

        [JsonPropertyName("presentationOutcome")]
        public string? PresentationOutcome { get; set; }

        [JsonPropertyName("cachePublished")]
        public bool CachePublished { get; set; }

        [JsonPropertyName("errorCode")]
        public string? ErrorCode { get; set; }

        [JsonIgnore]
        public bool CertifiesMutation => false;
    }

    public sealed class CancelConversationResult
    {
        [JsonPropertyName("accepted")]
        public bool Accepted { get; set; }
    }

    public sealed class CloseConversationResult
    {
        [JsonPropertyName("outcome")]
        public string Outcome { get; set; } = "";

        [JsonPropertyName("childExitObserved")]
        public bool ChildExitObserved { get; set; }
    }

    public sealed class DeleteConversationResult
    {
        [JsonPropertyName("associationRemoved")]
        public bool AssociationRemoved { get; set; }

        [JsonPropertyName("artifactsRemoved")]
        public bool ArtifactsRemoved { get; set; }
    }

    public class AgentChatHttpException : HttpRequestException
    {
        public AgentChatHttpException(HttpStatusCode statusCode, string code, string message)
            : base(message)
        {
            StatusCodeValue = statusCode;
            Code = code;
        }

        public HttpStatusCode StatusCodeValue { get; }
        public string Code { get; }
    }

    internal sealed class ReopenIdentityMismatchException : AgentChatHttpException
    {
        public ReopenIdentityMismatchException(Uri baseUri, string authoritativeConversationId)
            : base(
                HttpStatusCode.OK,
                "invalid_response",
                "Chat service returned a different conversation identity during reopen.")
        {
            BaseUri = baseUri;
            AuthoritativeConversationId = authoritativeConversationId;
        }

        public Uri BaseUri { get; }
        public string AuthoritativeConversationId { get; }
    }

    /// <summary>
    /// Authenticated HTTP client for the ACP-backed RookChat product service.
    /// This type maps product JSON only; it does not implement ACP.
    /// </summary>
    public sealed class AgentChatClient : IDisposable
    {
        internal const int MaxErrorMessageUtf8Bytes = 8 * 1024;
        internal const int MaxErrorBodyUtf8Bytes = 64 * 1024;
        internal const int MaxEncodedHttpBodyBytes = 48 * 1024 * 1024;
        internal const int MaxImagesPerTurn = 8;

        private static readonly HashSet<string> AllowedImageMimeTypes = new(StringComparer.Ordinal)
        {
            "image/png",
            "image/jpeg",
            "image/webp",
        };

        private static readonly JsonSerializerOptions JsonOptions = new()
        {
            PropertyNameCaseInsensitive = true,
        };

        private const string SessionHeaderName = "X-Rook-Session";
        private readonly HttpClient _client;
        private readonly Uri? _fixedBaseUri;
        private readonly ChatServiceHealth? _fixedHealth;

        public AgentChatClient()
            : this(new HttpClient { Timeout = Timeout.InfiniteTimeSpan }, null, null)
        {
        }

        internal AgentChatClient(
            HttpClient client,
            Uri? fixedBaseUri = null,
            ChatServiceHealth? fixedHealth = null)
        {
            _client = client ?? throw new ArgumentNullException(nameof(client));
            _fixedBaseUri = fixedBaseUri;
            _fixedHealth = fixedHealth;
        }

        internal static AgentChatClient ForTests(HttpMessageHandler handler, Uri baseUri)
            => new(new HttpClient(handler) { Timeout = Timeout.InfiniteTimeSpan }, baseUri, null);

        internal static AgentChatClient ForTests(
            HttpMessageHandler handler,
            Uri baseUri,
            ChatServiceHealth fixedHealth)
            => new(new HttpClient(handler) { Timeout = Timeout.InfiniteTimeSpan }, baseUri, fixedHealth);

        public void SetSessionNonce(string? nonce)
        {
            _client.DefaultRequestHeaders.Remove(SessionHeaderName);
            if (!string.IsNullOrEmpty(nonce))
                _client.DefaultRequestHeaders.Add(SessionHeaderName, nonce);
        }

        public Task<ChatServiceHealth> GetHealthAsync(bool startIfNeeded, CancellationToken ct = default)
            => _fixedHealth == null
                ? ChatServiceManager.Instance.GetHealthAsync(startIfNeeded, ct)
                : Task.FromResult(_fixedHealth);

        public async Task<List<ConversationSummary>> ListAsync(CancellationToken ct = default)
        {
            var baseUri = await GetBaseUriAsync(startIfNeeded: true, ct);
            using var response = await _client.GetAsync(Route(baseUri, "/agent/chat/conversations"), ct);
            return (await ReadSuccessJsonAsync<ConversationListEnvelope>(response, ct)).Conversations;
        }

        public async Task<ConversationView> CreateAsync(CreateConversationRequest request, CancellationToken ct = default)
        {
            if (request == null) throw new ArgumentNullException(nameof(request));
            var baseUri = await GetBaseUriAsync(startIfNeeded: true, ct);
            var payload = new Dictionary<string, object?>
            {
                ["profile"] = "full",
                ["hostGenerationId"] = request.HostGenerationId,
                ["documentSerialNumber"] = request.DocumentSerialNumber,
                ["routeProcessId"] = request.RouteProcessId,
                ["savedDocumentDirectory"] = request.SavedDocumentDirectory,
            };
            if (!string.IsNullOrWhiteSpace(request.Model)) payload["model"] = request.Model;
            if (!string.IsNullOrWhiteSpace(request.Reasoning)) payload["reasoning"] = request.Reasoning;
            var view = await SendJsonAsync<ConversationView>(
                HttpMethod.Post, Route(baseUri, "/agent/chat/conversations"), payload, ct);
            view.BaseUri = baseUri;
            return view;
        }

        public async Task<ConversationView> ReopenAsync(string conversationId, CancellationToken ct = default)
        {
            var baseUri = await GetBaseUriAsync(startIfNeeded: true, ct);
            var view = await SendJsonAsync<ConversationView>(
                HttpMethod.Post,
                ConversationRoute(baseUri, conversationId, "reopen"),
                EmptyBody(),
                ct);
            if (!string.Equals(view.ConversationId, conversationId, StringComparison.Ordinal))
                throw new ReopenIdentityMismatchException(baseUri, conversationId);
            view.BaseUri = baseUri;
            return view;
        }

        public async Task<PresentationHistory> GetHistoryAsync(string conversationId, CancellationToken ct = default)
        {
            var baseUri = await GetBaseUriAsync(startIfNeeded: true, ct);
            return await GetHistoryAsync(baseUri, conversationId, ct);
        }

        internal async Task<PresentationHistory> GetHistoryAsync(
            Uri baseUri,
            string conversationId,
            CancellationToken ct)
        {
            using var response = await _client.GetAsync(ConversationRoute(baseUri, conversationId, "history"), ct);
            return await ReadSuccessJsonAsync<PresentationHistory>(response, ct);
        }

        public async Task PromptAsync(
            string conversationId,
            string text,
            IReadOnlyList<ChatImageInput> images,
            Action<ChatEvent> onEvent,
            CancellationToken ct = default)
        {
            var baseUri = await GetBaseUriAsync(startIfNeeded: true, ct);
            await PromptAsync(baseUri, conversationId, text, images, onEvent, ct);
        }

        internal async Task PromptAsync(
            Uri baseUri,
            string conversationId,
            string text,
            IReadOnlyList<ChatImageInput> images,
            Action<ChatEvent> onEvent,
            CancellationToken ct)
        {
            if (onEvent == null) throw new ArgumentNullException(nameof(onEvent));
            var body = JsonSerializer.SerializeToUtf8Bytes(new { text, images }, JsonOptions);
            ValidateImageAdmission(images, body.Length);

            using var request = new HttpRequestMessage(
                HttpMethod.Post,
                ConversationRoute(baseUri, conversationId, "prompt"))
            {
                Content = new ByteArrayContent(body),
            };
            request.Content.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("application/json");
            using var response = await _client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
            await EnsureSuccessAsync(response, ct);
            using var stream = await response.Content.ReadAsStreamAsync();
            using var reader = new StreamReader(stream, new UTF8Encoding(false, true));
            ChatEvent? terminal = null;
            string? line;
            while (true)
            {
                try
                {
                    line = await reader.ReadLineAsync();
                }
                catch (DecoderFallbackException exc)
                {
                    throw InvalidStream("Chat service returned malformed UTF-8: " + exc.Message);
                }
                if (line == null) break;
                ct.ThrowIfCancellationRequested();
                if (string.IsNullOrWhiteSpace(line)) continue;
                if (terminal != null)
                    throw InvalidStream("Chat service returned data after terminal settlement.");
                ChatEvent value;
                try
                {
                    using var document = JsonDocument.Parse(line);
                    if (document.RootElement.ValueKind != JsonValueKind.Object)
                        throw InvalidStream("Chat service returned a non-object stream row.");
                    value = document.RootElement.Deserialize<ChatEvent>(JsonOptions)
                        ?? throw InvalidStream("Chat service returned an empty stream row.");
                    if (value.Type == "terminal")
                        ValidateTerminal(document.RootElement, value);
                }
                catch (JsonException exc)
                {
                    throw InvalidStream("Chat service returned malformed NDJSON: " + exc.Message);
                }
                if (value.Type == "terminal")
                {
                    terminal = value;
                    continue;
                }
                if (value.Type is not ("text_delta" or "thought_delta" or "tool_update"))
                    throw InvalidStream("Chat service returned an unknown stream row type.");
                onEvent(value);
            }
            if (terminal == null)
                throw InvalidStream("Chat service stream ended without a terminal row.");
            onEvent(terminal);
        }

        private static void ValidateTerminal(JsonElement row, ChatEvent terminal)
        {
            var isTransportError = row.TryGetProperty("errorCode", out _);
            var expectedProperties = isTransportError
                ? new HashSet<string>(StringComparer.Ordinal) { "type", "outcome", "errorCode" }
                : new HashSet<string>(StringComparer.Ordinal)
                {
                    "type", "outcome", "stopReason", "presentationOutcome", "cachePublished",
                };
            var actualProperties = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in row.EnumerateObject())
            {
                if (!actualProperties.Add(property.Name) || !expectedProperties.Contains(property.Name))
                    throw InvalidStream("Chat service returned an invalid terminal schema.");
            }
            if (actualProperties.Count != expectedProperties.Count)
                throw InvalidStream("Chat service returned an incomplete terminal schema.");
            if (terminal.Outcome is not ("settled" or "cancelled" or "incomplete" or "refused" or "error"))
                throw InvalidStream("Chat service returned an unknown terminal outcome.");

            if (isTransportError)
            {
                if (terminal.Outcome != "error" || string.IsNullOrWhiteSpace(terminal.ErrorCode))
                    throw InvalidStream("Chat service returned an invalid transport-error terminal.");
                return;
            }

            if (!row.TryGetProperty("stopReason", out var stopReasonProperty) ||
                !row.TryGetProperty("presentationOutcome", out var presentationProperty) ||
                !row.TryGetProperty("cachePublished", out var cacheProperty) ||
                presentationProperty.ValueKind != JsonValueKind.String ||
                cacheProperty.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
                throw InvalidStream("Chat service returned invalid terminal field types.");

            var stopReason = stopReasonProperty.ValueKind switch
            {
                JsonValueKind.String => stopReasonProperty.GetString(),
                JsonValueKind.Null => null,
                _ => throw InvalidStream("Chat service returned an invalid stop reason."),
            };
            var mappedOutcome = stopReason switch
            {
                "end_turn" => "settled",
                "cancelled" => "cancelled",
                "max_tokens" or "max_turn_requests" => "incomplete",
                "refusal" => "refused",
                null => null,
                _ => throw InvalidStream("Chat service returned an unknown stop reason."),
            };
            var terminalOutcomeIsValid = terminal.Outcome == "error"
                ? stopReason == null || mappedOutcome != null
                : terminal.Outcome == mappedOutcome;
            if (!terminalOutcomeIsValid ||
                terminal.PresentationOutcome is not ("delivered" or "stream_failed" or "disconnected"))
                throw InvalidStream("Chat service returned an inconsistent terminal outcome.");
        }

        public async Task<CancelConversationResult> CancelAsync(string conversationId, CancellationToken ct = default)
        {
            var baseUri = await GetBaseUriAsync(startIfNeeded: false, ct);
            return await CancelAsync(baseUri, conversationId, ct);
        }

        internal Task<CancelConversationResult> CancelAsync(Uri baseUri, string conversationId, CancellationToken ct)
            => SendJsonAsync<CancelConversationResult>(
                HttpMethod.Post, ConversationRoute(baseUri, conversationId, "cancel"), EmptyBody(), ct);

        public async Task<CloseConversationResult> CloseAsync(string conversationId, CancellationToken ct = default)
        {
            var baseUri = await GetBaseUriAsync(startIfNeeded: false, ct);
            return await CloseAsync(baseUri, conversationId, ct);
        }

        internal Task<CloseConversationResult> CloseAsync(Uri baseUri, string conversationId, CancellationToken ct)
            => SendJsonAsync<CloseConversationResult>(
                HttpMethod.Post, ConversationRoute(baseUri, conversationId, "close"), EmptyBody(), ct);

        public async Task<DeleteConversationResult> DeleteAsync(string conversationId, CancellationToken ct = default)
        {
            var baseUri = await GetBaseUriAsync(startIfNeeded: false, ct);
            return await DeleteAsync(baseUri, conversationId, ct);
        }

        internal Task<DeleteConversationResult> DeleteAsync(Uri baseUri, string conversationId, CancellationToken ct)
            => SendJsonAsync<DeleteConversationResult>(
                HttpMethod.Delete, ConversationRoute(baseUri, conversationId, null), null, ct);

        internal static void ValidateImageAdmission(IReadOnlyList<ChatImageInput> images, int encodedBodyBytes)
        {
            if (images == null) throw new ArgumentNullException(nameof(images));
            if (images.Count > MaxImagesPerTurn)
                throw new ArgumentException($"At most {MaxImagesPerTurn} images may be sent in one turn.", nameof(images));
            if (encodedBodyBytes < 0 || encodedBodyBytes > MaxEncodedHttpBodyBytes)
                throw new ArgumentException("Encoded chat request is oversized.", nameof(encodedBodyBytes));
            foreach (var image in images)
            {
                if (image == null || !AllowedImageMimeTypes.Contains(image.MimeType))
                    throw new ArgumentException("Image MIME type is not supported.", nameof(images));
            }
        }

        private async Task<Uri> GetBaseUriAsync(bool startIfNeeded, CancellationToken ct)
        {
            if (_fixedBaseUri != null) return _fixedBaseUri;
            var health = await ChatServiceManager.Instance.GetHealthAsync(startIfNeeded, ct);
            if (!health.ServiceAvailable || health.BaseUri == null)
                throw new InvalidOperationException(health.ServiceMessage);
            return health.BaseUri;
        }

        private async Task<T> SendJsonAsync<T>(
            HttpMethod method,
            Uri uri,
            object? payload,
            CancellationToken ct)
        {
            using var request = new HttpRequestMessage(method, uri);
            if (payload != null)
            {
                request.Content = new StringContent(
                    JsonSerializer.Serialize(payload, JsonOptions), Encoding.UTF8, "application/json");
            }
            using var response = await _client.SendAsync(request, ct);
            return await ReadSuccessJsonAsync<T>(response, ct);
        }

        private static async Task<T> ReadSuccessJsonAsync<T>(HttpResponseMessage response, CancellationToken ct)
        {
            await EnsureSuccessAsync(response, ct);
            var body = await response.Content.ReadAsStringAsync();
            try
            {
                return JsonSerializer.Deserialize<T>(body, JsonOptions)
                    ?? throw new AgentChatHttpException(response.StatusCode, "invalid_response", "Chat service returned an empty response.");
            }
            catch (JsonException exc)
            {
                throw new AgentChatHttpException(response.StatusCode, "invalid_response", "Chat service returned invalid JSON: " + exc.Message);
            }
        }

        private static async Task EnsureSuccessAsync(HttpResponseMessage response, CancellationToken ct)
        {
            if (response.IsSuccessStatusCode) return;
            var raw = await ReadBoundedUtf8Async(response.Content, MaxErrorBodyUtf8Bytes, ct);
            var code = "chat_request_failed";
            var message = $"Chat service request failed with HTTP {(int)response.StatusCode}.";
            try
            {
                using var document = JsonDocument.Parse(raw);
                if (document.RootElement.ValueKind == JsonValueKind.Object &&
                    document.RootElement.TryGetProperty("error", out var errorValue) &&
                    errorValue.ValueKind == JsonValueKind.Object)
                {
                    if (errorValue.TryGetProperty("code", out var codeValue) && codeValue.ValueKind == JsonValueKind.String)
                        code = codeValue.GetString() ?? code;
                    if (errorValue.TryGetProperty("message", out var messageValue) && messageValue.ValueKind == JsonValueKind.String)
                        message = BoundUtf8(messageValue.GetString() ?? message, MaxErrorMessageUtf8Bytes);
                }
            }
            catch (JsonException)
            {
                // Keep the closed generic classification for malformed error bodies.
            }
            throw new AgentChatHttpException(response.StatusCode, code, message);
        }

        private static AgentChatHttpException InvalidStream(string message)
            => new(HttpStatusCode.OK, "invalid_stream", message);

        private static async Task<string> ReadBoundedUtf8Async(HttpContent content, int limit, CancellationToken ct)
        {
            using var stream = await content.ReadAsStreamAsync();
            using var buffer = new MemoryStream();
            var chunk = new byte[4096];
            while (buffer.Length < limit)
            {
                var remaining = Math.Min(chunk.Length, limit - (int)buffer.Length);
                var read = await stream.ReadAsync(chunk, 0, remaining, ct);
                if (read == 0) break;
                buffer.Write(chunk, 0, read);
            }
            return Encoding.UTF8.GetString(buffer.ToArray());
        }

        private static string BoundUtf8(string value, int limit)
        {
            var bytes = Encoding.UTF8.GetBytes(value);
            if (bytes.Length <= limit) return value;
            return Encoding.UTF8.GetString(bytes, 0, limit).TrimEnd('\uFFFD');
        }

        private static Dictionary<string, object> EmptyBody() => new();

        private static Uri Route(Uri baseUri, string path) => new(baseUri, path);

        private static Uri ConversationRoute(Uri baseUri, string conversationId, string? action)
        {
            if (string.IsNullOrWhiteSpace(conversationId))
                throw new ArgumentException("Conversation ID is required.", nameof(conversationId));
            var path = "/agent/chat/conversations/" + Uri.EscapeDataString(conversationId);
            if (!string.IsNullOrEmpty(action)) path += "/" + action;
            return Route(baseUri, path);
        }

        public void Dispose() => _client.Dispose();
    }
}
