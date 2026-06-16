using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Eto.Drawing;
using Eto.Forms;

namespace Rook.UI.Chat
{
    /// <summary>
    /// Chat tab for agent conversations via the Python chat server.
    /// </summary>
    public class AgentChatTab : ChatTab
    {
        private readonly AgentChatClient _client;
        private readonly string _persona;
        private readonly string _personaLabel;
        private readonly Func<uint>? _documentSerialNumberProvider;
        private readonly uint _documentSerialNumber;
        private string? _conversationId;
        private Uri? _conversationBaseUri;
        private CancellationTokenSource? _cts;
        private ChatServiceHealth? _lastHealth;
        private readonly SemaphoreSlim _initializeGate = new SemaphoreSlim(1, 1);
        private bool _connectionBannerShown;
        private string? _activeUIBlockId;
        private string? _activeModelLabel;

        public AgentChatTab(
            string persona,
            string label,
            Color color,
            Func<uint>? documentSerialNumberProvider = null,
            uint documentSerialNumber = 0)
            : base(label, color, "agent-chat")
        {
            _persona = persona;
            _personaLabel = label;
            _documentSerialNumberProvider = documentSerialNumberProvider;
            _documentSerialNumber = documentSerialNumber;
            _client = new AgentChatClient();
        }

        private uint GetCurrentDocumentSerialNumber()
        {
            if (_documentSerialNumberProvider != null)
            {
                var current = _documentSerialNumberProvider();
                if (current != 0)
                {
                    return current;
                }
            }
            return _documentSerialNumber;
        }

        /// <summary>
        /// Initialize the conversation with the agent server.
        /// </summary>
        public async Task InitializeAsync()
        {
            await _initializeGate.WaitAsync();
            try
            {
                if (_conversationId != null)
                {
                    if (_lastHealth != null)
                    {
                        ApplyHealthStatus(_lastHealth);
                    }
                    await RefreshModelStatusAsync(_conversationId);
                    return;
                }

                SetStatus("Starting chat service...", Colors.Blue);

                var health = await _client.GetHealthAsync(startIfNeeded: true);
                if (!health.ServiceAvailable)
                {
                    SetStatus("Chat service unavailable", Colors.Red);
                    AddMessageToChat("error", health.ServiceMessage);
                    return;
                }

                // Attach session nonce so all HTTP calls include X-Rook-Session.
                var nonce = ChatServiceManager.Instance.SessionNonce;
                if (!string.IsNullOrEmpty(nonce))
                    _client.SetSessionNonce(nonce);

                if (!health.LlmConfigured)
                {
                    SetStatus("Chat service unavailable", Colors.Red);
                    AddMessageToChat("error", string.IsNullOrWhiteSpace(health.LlmMessage)
                        ? "Anthropic API key is missing. Configure ANTHROPIC_API_KEY for the Rhino-owned chat service."
                        : health.LlmMessage);
                    return;
                }

                var currentDocument = GetCurrentDocumentSerialNumber();
                var info = await _client.StartAsync(_persona, currentDocument);
                _conversationId = info.ConversationId;
                _conversationBaseUri = info.BaseUri;
                _activeModelLabel = info.Model;
                ApplyHealthStatus(health);
                await RefreshModelStatusAsync(_conversationId);

                // Set persona color and initial on the WebView
                var hex = $"#{(int)(TabColor.R * 255):X2}{(int)(TabColor.G * 255):X2}{(int)(TabColor.B * 255):X2}";
                var initial = TabLabel.Length > 0 ? TabLabel[0].ToString() : "A";
                ExecuteScript($"window.chatAPI.setPersona('{hex}', '{initial}')");

                // Inject conversation context for JS fetch bridge (UI block responses)
                var host = _conversationBaseUri?.Host ?? "127.0.0.1";
                var port = _conversationBaseUri?.Port ?? 0;
                ExecuteScript($"window.chatAPI.setConversation('{_conversationId}', '{host}', {port})");

                if (!_connectionBannerShown)
                {
                    AddMessageToChat("system", $"Connected to {_personaLabel} agent");
                    if (!health.RhinoConnected)
                    {
                        AddMessageToChat("system", "Chat service is running, but the Rhino bridge is currently unavailable.");
                    }
                    _connectionBannerShown = true;
                }
            }
            catch (Exception ex)
            {
                SetStatus("Conversation start failed", Colors.Red);
                AddMessageToChat("error", $"Failed to start conversation: {ex.Message}");
            }
            finally
            {
                _initializeGate.Release();
            }
        }

        public async Task ReconnectToServiceAsync()
        {
            await _initializeGate.WaitAsync();
            try
            {
                _conversationId = null;
                _conversationBaseUri = null;
                _activeModelLabel = null;
                _connectionBannerShown = false;
            }
            finally
            {
                _initializeGate.Release();
            }

            SetStatus("Starting chat service...", Colors.Blue);
            var health = await _client.GetHealthAsync(startIfNeeded: true);
            if (!health.ServiceAvailable)
            {
                SetStatus("Chat service unavailable", Colors.Red);
                AddMessageToChat("error", health.ServiceMessage);
                return;
            }

            await InitializeAsync();
        }

        private async Task RefreshModelStatusAsync(string? expectedConversationId = null, CancellationToken ct = default)
        {
            var baseUri = _conversationBaseUri;
            var conversationId = expectedConversationId ?? _conversationId;
            if (baseUri == null || conversationId == null || conversationId.Length == 0)
            {
                return;
            }
            var currentConversationId = conversationId;

            try
            {
                var models = await _client.GetModelsAsync(baseUri, currentConversationId, ct);
                var conversation = models.Conversation;
                if (conversation == null || string.IsNullOrEmpty(conversation.ActiveModel))
                {
                    return;
                }
                var activeModel = conversation.ActiveModel;

                if (!IsCurrentConversation(currentConversationId))
                {
                    return;
                }

                var status = string.IsNullOrEmpty(conversation.PendingModel)
                    ? $"Model: {activeModel}"
                    : $"Model: {activeModel}; next turn: {conversation.PendingModel}";

                Application.Instance.Invoke(() =>
                {
                    if (!IsCurrentConversation(currentConversationId))
                    {
                        return;
                    }

                    _activeModelLabel = activeModel;
                    SetStatus(status, Colors.Blue);
                });
            }
            catch
            {
                // Model status is best-effort feedback only.
            }
        }

        private bool IsCurrentConversation(string expectedConversationId)
        {
            return string.Equals(_conversationId, expectedConversationId, StringComparison.Ordinal);
        }

        private void ApplyModelUpdateEvent(ChatEvent evt)
        {
            if (string.IsNullOrEmpty(evt.Model))
            {
                return;
            }

            if (evt.AppliesTo == "next_turn")
            {
                var active = _activeModelLabel ?? evt.Model;
                SetStatus($"Model: {active}; next turn: {evt.Model}", Colors.Blue);
                return;
            }

            _activeModelLabel = evt.Model;
            SetStatus($"Model: {evt.Model}", Colors.Blue);
        }

        private void ApplyHealthStatus(ChatServiceHealth health)
        {
            _lastHealth = health;
            if (!health.ServiceAvailable)
            {
                SetStatus("Chat service unavailable", Colors.Red);
                return;
            }

            if (!health.LlmConfigured)
            {
                SetStatus("Chat service unavailable", Colors.Red);
                return;
            }

            if (health.RhinoConnected)
            {
                SetStatus("Chat service ready, Rhino bridge healthy", Colors.Green);
            }
            else
            {
                SetStatus("Chat service ready, Rhino bridge unhealthy", Color.FromArgb(0xd9, 0x77, 0x06));
            }
        }

        protected override async Task OnSendMessage(string message)
        {
            if (_conversationId == null)
            {
                await InitializeAsync();
                if (_conversationId == null || _conversationBaseUri == null)
                {
                    AddMessageToChat("error", "Not connected to chat service");
                    return;
                }
            }

            _cts?.Cancel();
            _cts?.Dispose();
            _cts = new CancellationTokenSource();
            var textBuffer = new StringBuilder();

            try
            {
                var health = await _client.GetHealthAsync(_conversationBaseUri!, _cts.Token);
                ApplyHealthStatus(health);
                if (!health.ServiceAvailable)
                {
                    AddMessageToChat("error", "Chat service is unavailable for this conversation. Use Restart Chat to reconnect.");
                    SetProcessing(false);
                    return;
                }
                if (!health.LlmConfigured)
                {
                    AddMessageToChat("error", string.IsNullOrWhiteSpace(health.LlmMessage)
                        ? "Anthropic API key is missing. Configure ANTHROPIC_API_KEY for the Rhino-owned chat service."
                        : health.LlmMessage);
                    SetProcessing(false);
                    return;
                }
                var currentDocument = GetCurrentDocumentSerialNumber();
                await _client.SendMessageStreamingAsync(
                    _conversationBaseUri!,
                    _conversationId,
                    message,
                    currentDocument,
                    evt => HandleChatEvent(evt, textBuffer),
                    _cts.Token);
            }
            catch (OperationCanceledException)
            {
                // User cancelled — handled by OnStopClicked in base
            }
            catch (HttpRequestException ex)
            {
                AddMessageToChat("error", $"Chat service unavailable: {ex.Message}");
                SetStatus("Chat service unavailable", Colors.Red);
                SetProcessing(false);
            }
            catch (InvalidOperationException ex)
            {
                AddMessageToChat("error", ex.Message);
                SetStatus("Chat service unavailable", Colors.Red);
                SetProcessing(false);
            }
        }

        private void HandleChatEvent(ChatEvent evt, StringBuilder textBuffer)
        {
            Application.Instance.Invoke(() =>
            {
                switch (evt.Type)
                {
                    case "text_delta":
                        textBuffer.Append(evt.Content ?? "");
                        ShowTypingIndicator(false);
                        UpdateStreamingChat(textBuffer.ToString());
                        SetStatus("Receiving...", Colors.Blue);
                        break;

                    case "tool_start":
                        // Finalize any in-progress text, then render a tool card
                        if (textBuffer.Length > 0)
                        {
                            FinalizeStreaming();
                            textBuffer.Clear();
                        }
                        var paramsJson = evt.Params.HasValue
                            ? evt.Params.Value.GetRawText()
                            : "{}";
                        ExecuteScript(
                            $"window.chatAPI.renderToolCard('{EscapeForJavaScript(evt.Name ?? "")}', {paramsJson}, '{EscapeForJavaScript(evt.ToolCallId ?? "")}')");
                        SetStatus($"Running {evt.Name}...", Colors.Blue);
                        break;

                    case "tool_result":
                        // Transition the tool card to its final state
                        var verified = evt.Verified.HasValue
                            ? (evt.Verified.Value ? "true" : "false")
                            : "null";
                        var note = EscapeForJavaScript(evt.VerificationNote ?? "");
                        var summary = BuildToolSummary(evt);
                        ExecuteScript(
                            $"window.chatAPI.finalizeToolCard('{EscapeForJavaScript(evt.ToolCallId ?? "")}', {verified}, '{note}', '{EscapeForJavaScript(summary)}')");
                        break;

                    case "ui_block":
                        // Finalize any in-progress text, then render a UI block
                        if (textBuffer.Length > 0)
                        {
                            FinalizeStreaming();
                            textBuffer.Clear();
                        }
                        var blockConfigJson = evt.BlockConfig.HasValue
                            ? evt.BlockConfig.Value.GetRawText()
                            : "{}";
                        ExecuteScript(
                            $"window.chatAPI.renderUIBlock('{EscapeForJavaScript(evt.BlockId ?? "")}', '{EscapeForJavaScript(evt.BlockType ?? "")}', {blockConfigJson})");
                        break;

                    case "model_update":
                        ApplyModelUpdateEvent(evt);
                        _ = RefreshModelStatusAsync(_conversationId);
                        break;

                    case "done":
                        if (_activeUIBlockId != null)
                        {
                            var doneBlockId = _activeUIBlockId;
                            _activeUIBlockId = null;
                            ExecuteScript(
                                $"window.chatAPI.updateUIBlock('{EscapeForJavaScript(doneBlockId)}', {{state:'done', result_text:'Submitted'}})");
                        }
                        FinalizeStreaming();
                        if (_lastHealth != null)
                        {
                            ApplyHealthStatus(_lastHealth);
                        }
                        else
                        {
                            SetStatus("Ready", Colors.Green);
                        }
                        SetProcessing(false);
                        _ = RefreshModelStatusAsync(_conversationId);
                        break;

                    case "error":
                        MarkActiveUIBlockStale();
                        FinalizeStreaming();
                        AddMessageToChat("error", evt.Content ?? "Unknown error");
                        SetStatus("Error", Colors.Red);
                        SetProcessing(false);
                        break;
                }
            });
        }

        /// <summary>
        /// Build a short human-readable summary from a tool result event.
        /// </summary>
        private static string BuildToolSummary(ChatEvent evt)
        {
            if (string.IsNullOrEmpty(evt.Result))
                return "Done";

            try
            {
                using var doc = JsonDocument.Parse(evt.Result);
                var root = doc.RootElement;

                // Check for objectsCreated (creation tools)
                if (root.TryGetProperty("data", out var data) &&
                    data.TryGetProperty("objectsCreated", out var created))
                {
                    return $"Created {created.GetInt32()} object(s)";
                }

                // Check for success field
                if (root.TryGetProperty("success", out var success))
                {
                    return success.GetBoolean() ? "Success" : "Failed";
                }
            }
            catch
            {
                // Not valid JSON or unexpected structure
            }

            return "Done";
        }

        protected override void OnStopRequested()
        {
            _cts?.Cancel();
        }

        protected override async Task OnUIBlockSubmitAsync(string blockId, JsonNode? value)
        {
            // Capture refs into locals after the null check — fields can be
            // mutated (cleared on tab close) between check and use, and the
            // local-capture pattern also satisfies the C# 11 nullable analyzer
            // since field reads aren't tracked across awaits.
            var baseUri = _conversationBaseUri;
            var conversationId = _conversationId;
            if (baseUri == null || string.IsNullOrEmpty(conversationId))
            {
                return;
            }

            // Refuse if ANY chat work is in flight — a typed /message stream
            // OR another UI block submission. Without this guard, a click on
            // Apply during a typed-message stream would overwrite _cts and
            // orphan the original stream's cancel token (Stop button would
            // no longer cancel it). Mark the just-clicked block stale so its
            // optimistic spinner clears.
            if (IsProcessing || _activeUIBlockId != null)
            {
                Application.Instance.Invoke(() =>
                {
                    ExecuteScript(
                        $"window.chatAPI.updateUIBlock('{EscapeForJavaScript(blockId)}', {{state:'stale'}})");
                });
                return;
            }

            _activeUIBlockId = blockId;
            // Dispose the previous (completed) CTS before replacing — the
            // IsProcessing guard above ensures no live stream is using it.
            _cts?.Dispose();
            _cts = new CancellationTokenSource();
            var textBuffer = new StringBuilder();
            SetProcessing(true);

            // Pass the raw JsonNode as the value payload — JsonSerializer
            // round-trips JsonNode correctly into the request body.
            object valuePayload = (object?)value ?? new { };

            try
            {
                var currentDocument = GetCurrentDocumentSerialNumber();
                await _client.SendUIResponseStreamingAsync(
                    baseUri,
                    conversationId!,
                    blockId,
                    valuePayload,
                    currentDocument,
                    evt => HandleChatEvent(evt, textBuffer),
                    _cts.Token);
            }
            catch (OperationCanceledException)
            {
                MarkActiveUIBlockStale();
                SetProcessing(false);
            }
            catch (HttpRequestException ex)
            {
                AddMessageToChat("error", $"UI block submission failed: {ex.Message}");
                MarkActiveUIBlockStale();
                SetProcessing(false);
            }
            catch (InvalidOperationException ex)
            {
                AddMessageToChat("error", ex.Message);
                MarkActiveUIBlockStale();
                SetProcessing(false);
            }
        }

        private void MarkActiveUIBlockStale()
        {
            if (_activeUIBlockId == null) return;
            var blockId = _activeUIBlockId;
            _activeUIBlockId = null;
            Application.Instance.Invoke(() =>
            {
                ExecuteScript(
                    $"window.chatAPI.updateUIBlock('{EscapeForJavaScript(blockId)}', {{state:'stale'}})");
            });
        }

        protected override void OnClearRequested()
        {
            // Nothing to reset — agent server keeps its own history
        }

        public override void OnTabClosed()
        {
            if (!CloseWebSurface())
                return;

            if (_conversationId != null && _conversationBaseUri != null)
            {
                _ = _client.StopAsync(_conversationBaseUri, _conversationId);
                _conversationId = null;
                _conversationBaseUri = null;
            }
            _cts?.Cancel();
            _cts?.Dispose();
            _cts = null;
            _client.Dispose();
        }
    }
}
