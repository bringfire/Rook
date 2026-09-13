using System;
using System.Collections.Generic;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Eto.Drawing;
using Eto.Forms;

namespace Rook.UI.Chat
{
    internal readonly struct InitializationIdentityHandoff
    {
        public InitializationIdentityHandoff(bool publishToTab, bool queueClose, bool disposeClient)
        {
            PublishToTab = publishToTab;
            QueueClose = queueClose;
            DisposeClient = disposeClient;
        }

        public bool PublishToTab { get; }
        public bool QueueClose { get; }
        public bool DisposeClient { get; }
    }

    internal sealed class InitializationRequestCustody
    {
        private readonly object _gate = new();
        private bool _attached = true;
        private bool _started;
        private bool _inFlight;

        public bool IsAttached
        {
            get { lock (_gate) return _attached; }
        }

        public bool TryBegin()
        {
            lock (_gate)
            {
                if (!_attached || _started) return false;
                _started = true;
                _inFlight = true;
                return true;
            }
        }

        public bool Detach()
        {
            lock (_gate)
            {
                _attached = false;
                return !_inFlight;
            }
        }

        public InitializationIdentityHandoff CompleteWithIdentity()
        {
            lock (_gate)
            {
                _inFlight = false;
                return _attached
                    ? new InitializationIdentityHandoff(true, false, false)
                    : new InitializationIdentityHandoff(false, true, true);
            }
        }

        public bool CompleteWithoutIdentity()
        {
            lock (_gate)
            {
                if (!_inFlight) return false;
                _inFlight = false;
                return !_attached;
            }
        }
    }

    internal sealed class PresentationHistoryMessage
    {
        public PresentationHistoryMessage(string role, string text)
        {
            Role = role;
            Text = text;
        }

        public string Role { get; }
        public string Text { get; }
    }

    internal static class PresentationHistoryFormatter
    {
        private const int MaxSummaryUtf8Bytes = 512;

        public static IReadOnlyList<PresentationHistoryMessage> Format(PresentationHistory history)
        {
            var messages = new List<PresentationHistoryMessage>();
            if (!history.Available)
            {
                messages.Add(new PresentationHistoryMessage(
                    "system",
                    history.Message ?? "Presentation history unavailable."));
                return messages;
            }
            if (history.EarlierHistoryOmitted)
            {
                messages.Add(new PresentationHistoryMessage(
                    "system",
                    history.Message ?? "Earlier presentation history was omitted. Prime retains the authoritative conversation state."));
            }
            foreach (var turn in history.Turns)
            {
                if (turn.Fallback)
                {
                    messages.Add(new PresentationHistoryMessage(
                        "system",
                        turn.Message ?? "A bounded presentation projection was unavailable for this turn."));
                    continue;
                }
                if (!string.IsNullOrEmpty(turn.UserText))
                    messages.Add(new PresentationHistoryMessage("user", turn.UserText));
                foreach (var image in turn.Images)
                {
                    messages.Add(new PresentationHistoryMessage(
                        "system",
                        $"Image preview unavailable after reopen: {image.FileName} ({image.MimeType}, {image.BinaryByteCount} bytes)."));
                }
                if (!string.IsNullOrEmpty(turn.AssistantText))
                    messages.Add(new PresentationHistoryMessage("assistant", turn.AssistantText));
                foreach (var card in turn.ToolCards)
                    messages.Add(new PresentationHistoryMessage("system", FormatToolCard(card)));
                if (!string.IsNullOrEmpty(turn.StopReason) && turn.StopReason != "end_turn")
                    messages.Add(new PresentationHistoryMessage("system", "Turn ended: " + BoundUtf8(turn.StopReason)));
            }
            return messages;
        }

        private static string FormatToolCard(JsonElement card)
        {
            var kind = ReadString(card, "kind") ?? "tool update";
            var label = (string?)null;
            var status = (string?)null;
            if (card.ValueKind == JsonValueKind.Object &&
                card.TryGetProperty("content", out var content) &&
                content.ValueKind == JsonValueKind.String)
            {
                try
                {
                    using var projected = JsonDocument.Parse(content.GetString() ?? "");
                    var root = projected.RootElement;
                    label = ReadString(root, "text");
                    if (root.ValueKind == JsonValueKind.Object &&
                        root.TryGetProperty("payload", out var payload) &&
                        payload.ValueKind == JsonValueKind.Object)
                        status = ReadString(payload, "status");
                }
                catch (JsonException)
                {
                }
            }
            var summary = "Tool: " + (string.IsNullOrWhiteSpace(label) ? kind : label);
            if (!string.IsNullOrWhiteSpace(status)) summary += " (" + status + ")";
            return BoundUtf8(summary);
        }

        private static string? ReadString(JsonElement value, string propertyName)
        {
            if (value.ValueKind != JsonValueKind.Object ||
                !value.TryGetProperty(propertyName, out var property) ||
                property.ValueKind != JsonValueKind.String)
                return null;
            return property.GetString();
        }

        private static string BoundUtf8(string value)
        {
            var bytes = Encoding.UTF8.GetBytes(value);
            if (bytes.Length <= MaxSummaryUtf8Bytes) return value;
            return Encoding.UTF8.GetString(bytes, 0, MaxSummaryUtf8Bytes - 3).TrimEnd('\uFFFD') + "...";
        }
    }

    /// <summary>
    /// One Prime ACP conversation projected through the Python product service.
    /// The tab owns presentation only; the service owns ACP settlement and Prime.
    /// </summary>
    public sealed class AgentChatTab : ChatTab
    {
        private static readonly Color PrimeAccent = Color.FromArgb(0x25, 0x63, 0xeb);
        internal static readonly TimeSpan InvalidStreamCancelDeadline = TimeSpan.FromSeconds(1);

        private readonly AgentChatClient _client;
        private readonly ConversationCloseCoordinator _closeCoordinator;
        private readonly CreateConversationRequest? _createRequest;
        private readonly ConversationSummary? _reopenAssociation;
        private readonly SemaphoreSlim _initializeGate = new(1, 1);
        private readonly InitializationRequestCustody _initializationCustody = new();
        private readonly object _promptGate = new();
        private readonly object _lifetimeGate = new();

        private string? _conversationId;
        private Uri? _conversationBaseUri;
        private volatile bool _uiAttached = true;
        private bool _deleted;
        private bool _terminalSeen;
        private StringBuilder? _assistantBuffer;
        private Label? _effectiveSettingsLabel;
        private string? _requestedModel;
        private string? _requestedReasoning;

        public AgentChatTab(
            CreateConversationRequest createRequest,
            AgentChatClient? client = null,
            ConversationCloseCoordinator? closeCoordinator = null)
            : this(createRequest, client, closeCoordinator, initializePresentation: true)
        {
        }

        internal AgentChatTab(
            CreateConversationRequest createRequest,
            AgentChatClient? client,
            ConversationCloseCoordinator? closeCoordinator,
            bool initializePresentation)
            : base("Prime", PrimeAccent, "agent-chat", initializePresentation)
        {
            _createRequest = createRequest ?? throw new ArgumentNullException(nameof(createRequest));
            _client = client ?? new AgentChatClient();
            _closeCoordinator = closeCoordinator ?? ConversationCloseCoordinator.Instance;
            if (initializePresentation)
            {
                EnableWebComposer();
                ShowRequestedSettings(createRequest.Model, createRequest.Reasoning);
            }
        }

        public AgentChatTab(
            ConversationSummary association,
            AgentChatClient? client = null,
            ConversationCloseCoordinator? closeCoordinator = null)
            : this(association, client, closeCoordinator, initializePresentation: true)
        {
        }

        internal AgentChatTab(
            ConversationSummary association,
            AgentChatClient? client,
            ConversationCloseCoordinator? closeCoordinator,
            bool initializePresentation)
            : base("Prime", PrimeAccent, "agent-chat", initializePresentation)
        {
            _reopenAssociation = association ?? throw new ArgumentNullException(nameof(association));
            _client = client ?? new AgentChatClient();
            _closeCoordinator = closeCoordinator ?? ConversationCloseCoordinator.Instance;
            if (initializePresentation)
            {
                EnableWebComposer();
                ShowRequestedSettings(association.RequestedInitialModel, association.RequestedInitialReasoning);
            }
        }

        public string? ConversationId => _conversationId ?? _reopenAssociation?.ConversationId;

        protected override bool WaitForStopSettlement => true;

        public async Task InitializeAsync()
        {
            if (!_initializationCustody.TryBegin()) return;
            await _initializeGate.WaitAsync();
            try
            {
                var health = await _client.GetHealthAsync(startIfNeeded: true);
                if (!health.ServiceAvailable)
                    throw new InvalidOperationException(health.ServiceMessage);
                if (!health.RuntimeAvailable)
                    throw new InvalidOperationException("The installed Prime ACP runtime is unavailable.");
                if (!_initializationCustody.IsAttached) return;

                _client.SetSessionNonce(ChatServiceManager.Instance.SessionNonce);
                ConversationView view;
                if (_reopenAssociation != null)
                {
                    view = await _client.ReopenAsync(_reopenAssociation.ConversationId);
                    if (!HandOffInitializedIdentity(view)) return;
                    var history = await _client.GetHistoryAsync(
                        view.BaseUri ?? throw new InvalidOperationException("Prime conversation URI is unavailable."),
                        view.ConversationId,
                        CancellationToken.None);
                    if (!_initializationCustody.IsAttached) return;
                    RenderPresentationHistory(history);
                }
                else
                {
                    view = await _client.CreateAsync(_createRequest!);
                    if (!HandOffInitializedIdentity(view)) return;
                }

                if (!_initializationCustody.IsAttached) return;
                ApplyConversationStatus(view);
                AddMessageToChat("system", _reopenAssociation == null
                    ? "Prime is ready. This conversation becomes durable after its first completed turn."
                    : "Prime conversation reopened.");
            }
            catch (Exception ex)
            {
                if (ex is ReopenIdentityMismatchException mismatch)
                    QueueClose(mismatch.BaseUri, mismatch.AuthoritativeConversationId);
                if (_uiAttached)
                {
                    SetStatus("Conversation unavailable", Colors.Red);
                    AddMessageToChat("error", ex.Message);
                }
            }
            finally
            {
                _initializeGate.Release();
                if (_initializationCustody.CompleteWithoutIdentity()) _client.Dispose();
            }
        }

        private bool HandOffInitializedIdentity(ConversationView view)
        {
            var handoff = _initializationCustody.CompleteWithIdentity();
            if (handoff.PublishToTab && TryPublishConversation(view)) return true;
            if (handoff.QueueClose || !_uiAttached)
                QueueClose(view.BaseUri, view.ConversationId);
            if (handoff.DisposeClient) _client.Dispose();
            return false;
        }

        protected override Task OnSendMessage(string message)
            => RunPromptAsync(message, Array.Empty<ChatImageInput>());

        protected override Task OnWebSubmitAsync(string text, IReadOnlyList<ChatImageInput> images)
        {
            if (images.Count > 0 && _uiAttached)
            {
                AddMessageToChat("system", images.Count == 1
                    ? $"Attached image: {images[0].FileName}"
                    : $"Attached {images.Count} images.");
            }
            return RunPromptAsync(text, images);
        }

        private async Task RunPromptAsync(string text, IReadOnlyList<ChatImageInput> images)
        {
            GetConversation(out var baseUri, out var conversationId);
            if (baseUri == null || string.IsNullOrEmpty(conversationId))
                throw new InvalidOperationException("Prime conversation is not open.");

            lock (_promptGate)
            {
                _assistantBuffer = new StringBuilder();
                _terminalSeen = false;
            }

            await RunOwnedPromptAsync(
                _client,
                baseUri,
                conversationId,
                text,
                images,
                HandleChatEvent,
                CancellationToken.None);

            lock (_promptGate)
            {
                if (!_terminalSeen)
                    throw new InvalidOperationException("Prime prompt ended without a terminal outcome.");
            }
        }

        internal static async Task RunOwnedPromptAsync(
            AgentChatClient client,
            Uri baseUri,
            string conversationId,
            string text,
            IReadOnlyList<ChatImageInput> images,
            Action<ChatEvent> onEvent,
            CancellationToken ct)
        {
            try
            {
                await client.PromptAsync(baseUri, conversationId, text, images, onEvent, ct);
            }
            catch (AgentChatHttpException ex) when (ex.Code == "invalid_stream")
            {
                try
                {
                    using var cancelDeadline = new CancellationTokenSource(InvalidStreamCancelDeadline);
                    await client.CancelAsync(baseUri, conversationId, cancelDeadline.Token);
                }
                catch
                {
                    // The stream failure remains authoritative for the panel. The
                    // service still owns settlement and may already be retiring it.
                }
                throw;
            }
        }

        private void HandleChatEvent(ChatEvent evt)
        {
            if (!_uiAttached) return;
            switch (evt.Type)
            {
                case "session_status":
                    Application.Instance.Invoke(() => ApplyReportedSettings(evt.EffectiveSettings));
                    break;
                case "text_delta":
                    lock (_promptGate) _assistantBuffer?.Append(evt.Text);
                    Application.Instance.Invoke(() =>
                    {
                        if (_uiAttached) UpdateStreamingChat(_assistantBuffer?.ToString() ?? string.Empty);
                    });
                    break;
                case "thought_delta":
                    Application.Instance.Invoke(() =>
                    {
                        if (_uiAttached) SetStatus("Prime is reasoning...", Colors.Blue);
                    });
                    break;
                case "tool_update":
                    HandleToolUpdate(evt);
                    break;
                case "terminal":
                    lock (_promptGate) _terminalSeen = true;
                    Application.Instance.Invoke(() => ApplyTerminal(evt));
                    break;
            }
        }

        private void HandleToolUpdate(ChatEvent evt)
        {
            // ACP tool cards are presentation only. They never certify a Rook
            // mutation; authentic Rook receipts and evidence retain that authority.
            var presentationOnly = !evt.CertifiesMutation;
            if (!presentationOnly || !_uiAttached) return;

            var id = EscapeForJavaScript(evt.MessageId ?? string.Empty);
            var name = EscapeForJavaScript(evt.Text ?? evt.Kind ?? "Tool");
            var payload = evt.Payload?.GetRawText() ?? "{}";
            var status = ReadPayloadString(evt.Payload, "status");
            Application.Instance.Invoke(() =>
            {
                if (!_uiAttached) return;
                if (status == "completed" || status == "failed")
                {
                    var summary = EscapeForJavaScript(evt.Text ?? status);
                    ExecuteScript(
                        $"window.chatAPI.finalizeToolCard('{id}', null, null, '{summary}', '{EscapeForJavaScript(status == "completed" ? "success" : "failed")}')");
                }
                else
                {
                    // renderToolCard finalizes the current bubble; subsequent text starts a new segment.
                    lock (_promptGate) _assistantBuffer?.Clear();
                    ExecuteScript($"window.chatAPI.renderToolCard('{name}', {payload}, '{id}')");
                }
            });
        }

        private void ApplyTerminal(ChatEvent evt)
        {
            if (!_uiAttached) return;
            ShowTypingIndicator(false);
            FinalizeStreaming();
            SetProcessing(false);
            var status = evt.Outcome switch
            {
                "settled" => "Ready",
                "cancelled" => "Cancelled",
                "incomplete" => "Prime turn incomplete",
                "refused" => "Prime refused the request",
                _ => "Prime turn failed",
            };
            if (evt.PresentationOutcome == "stream_failed")
                status += " (live presentation failed)";
            SetStatus(status, evt.Outcome == "settled" ? Colors.Green : Colors.Orange);
        }

        protected override void OnStopRequested()
        {
            GetConversation(out var baseUri, out var conversationId);
            if (baseUri == null || string.IsNullOrEmpty(conversationId)) return;
            _ = RequestCancelAsync(baseUri, conversationId);
        }

        private async Task RequestCancelAsync(Uri baseUri, string conversationId)
        {
            try
            {
                await _client.CancelAsync(baseUri, conversationId, CancellationToken.None);
            }
            catch (Exception ex)
            {
                if (_uiAttached) AddMessageToChat("error", "Cancellation request failed: " + ex.Message);
            }
        }

        public async Task<DeleteConversationResult> DeleteConversationAsync()
        {
            GetConversation(out var baseUri, out var conversationId);
            if (baseUri == null || string.IsNullOrEmpty(conversationId))
                throw new InvalidOperationException("Prime conversation is not open.");
            var result = await _client.DeleteAsync(baseUri, conversationId, CancellationToken.None);
            lock (_lifetimeGate)
            {
                _deleted = true;
                _uiAttached = false;
            }
            return result;
        }

        protected override void OnClearRequested()
        {
            // Clear affects the disposable panel projection only. Prime retains
            // the authoritative conversation and presentation cache on disk.
        }

        public override void OnTabClosed()
        {
            Uri? baseUri;
            string? conversationId;
            bool deleted;
            lock (_lifetimeGate)
            {
                _uiAttached = false;
                if (!CloseWebSurface()) return;
                baseUri = _conversationBaseUri;
                conversationId = _conversationId;
                deleted = _deleted;
                _conversationBaseUri = null;
                _conversationId = null;
            }
            if (!deleted) QueueClose(baseUri, conversationId);
            if (_initializationCustody.Detach()) _client.Dispose();
        }

        private bool TryPublishConversation(ConversationView view)
        {
            if (view.BaseUri == null || string.IsNullOrEmpty(view.ConversationId))
                throw new InvalidOperationException("Prime conversation identity is unavailable.");
            lock (_lifetimeGate)
            {
                if (!_uiAttached) return false;
                _conversationBaseUri = view.BaseUri;
                _conversationId = view.ConversationId;
                return true;
            }
        }

        private void GetConversation(out Uri? baseUri, out string? conversationId)
        {
            lock (_lifetimeGate)
            {
                baseUri = _conversationBaseUri;
                conversationId = _conversationId;
            }
        }

        private void QueueClose(Uri? baseUri, string? conversationId)
        {
            if (baseUri == null || string.IsNullOrEmpty(conversationId)) return;
            _closeCoordinator.Enqueue(new ConversationCloseRequest(
                baseUri,
                conversationId,
                ChatServiceManager.Instance.SessionNonce));
        }

        private void RenderPresentationHistory(PresentationHistory history)
        {
            foreach (var message in PresentationHistoryFormatter.Format(history))
                AddMessageToChat(message.Role, message.Text);
        }

        private void ApplyConversationStatus(ConversationView view)
        {
            if (!_uiAttached || view.ConversationId != ConversationId) return;
            ApplyReportedSettings(view.EffectiveSettings);
            SetStatus(
                view.TargetAvailable ? "Prime ready" : "Prime ready; Rook target unavailable",
                view.TargetAvailable ? Colors.Green : Colors.Orange);
        }

        private void ShowRequestedSettings(string? model, string? reasoning)
        {
            _requestedModel = model;
            _requestedReasoning = reasoning;
            ApplyReportedSettings(null);
        }

        private void ApplyReportedSettings(ReportedEffectiveSettings? settings)
        {
            if (!_uiAttached) return;
            var parts = new List<string>();
            if (!string.IsNullOrEmpty(_requestedModel)) parts.Add("Requested model: " + _requestedModel);
            if (!string.IsNullOrEmpty(_requestedReasoning)) parts.Add("requested reasoning: " + _requestedReasoning);
            parts.Add("Last reported effective settings: " +
                (settings?.Provider == null && settings?.Model == null ? "unknown" :
                 (settings?.Provider ?? "unknown") + "/" + (settings?.Model ?? "unknown")));
            parts.Add("reasoning: " + (settings?.Reasoning ?? "unknown"));
            if (_effectiveSettingsLabel == null)
            {
                _effectiveSettingsLabel = new Label { TextColor = Colors.Gray, Wrap = WrapMode.Word };
                SetAuxiliaryRow(_effectiveSettingsLabel);
            }
            _effectiveSettingsLabel.Text = string.Join("; ", parts);
        }

        private static string? ReadPayloadString(JsonElement? payload, string propertyName)
        {
            if (!payload.HasValue || payload.Value.ValueKind != JsonValueKind.Object ||
                !payload.Value.TryGetProperty(propertyName, out var value) ||
                value.ValueKind != JsonValueKind.String)
                return null;
            return value.GetString();
        }
    }
}
