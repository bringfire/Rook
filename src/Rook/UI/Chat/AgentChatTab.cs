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
        private bool _promptOutcomeUnconfirmed;
        private PromptState? _activePrompt;
        private StringBuilder? _assistantBuffer;

        /// <summary>
        /// Per-request outcome truth (Contract 1). One instance per RunPromptAsync so a
        /// later request can never reset an earlier request's terminal flag while that
        /// request's continuation is still pending.
        /// </summary>
        private sealed class PromptState
        {
            public PromptState(int requestId) => RequestId = requestId;
            public int RequestId { get; }
            public volatile bool TerminalSeen;
        }
        internal const int MaxToolCardPayloadBytes = 8 * 1024;
        private Label? _effectiveSettingsLabel;
        private string? _requestedModel;
        private string? _requestedReasoning;
        private bool _hasReportedModel, _hasCompletedTurn;
        internal bool IsReopenedConversation => _reopenAssociation != null;
        internal bool HasEstablishedSettings => _hasReportedModel || _hasCompletedTurn;
        internal event Action? GuidanceContextChanged;

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
        protected override string? SubmissionBlockReason => _promptOutcomeUnconfirmed
            ? "Request outcome is unconfirmed. Another request is blocked because the previous one may still be running."
            : null;

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
                    ? "Conversation connected. This conversation becomes durable after its first completed turn."
                    : "Conversation reopened.");
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

            // Request truth (Contract 1): reader-owned, synchronous, never queued, and
            // scoped to this request. Settlement of request N can re-enable the composer
            // before this method resumes from its await; a request N+1 started in that
            // window must not be able to reset N's outcome.
            var state = new PromptState(ActiveRequestId);
            lock (_promptGate) _activePrompt = state;
            // TurnStart: the assistant buffer is reset on the UI thread in queue order,
            // behind any pending presentation of the previous turn.
            EnqueueContent("turn:start", () => { lock (_promptGate) _assistantBuffer = new StringBuilder(); }, emitsScripts: false);

            var dispatched = false;
            try
            {
                // Explicit background boundary (plan §4): the read loop and every
                // onEvent run on the thread pool whether or not reads complete
                // synchronously, so no UI work ever nests inside a read.
                await Task.Run(() => RunOwnedPromptAsync(
                    _client,
                    baseUri,
                    conversationId,
                    text,
                    images,
                    evt => HandlePromptEvent(state, evt),
                    CancellationToken.None,
                    onDispatch: () => dispatched = true));
            }
            catch (Exception ex)
            {
                lock (_promptGate)
                {
                    if (dispatched && !state.TerminalSeen &&
                        !(ex is AgentChatHttpException http && http.PromptNotAdmitted))
                        _promptOutcomeUnconfirmed = true;
                }
                throw;
            }

            if (!state.TerminalSeen)
                throw new InvalidOperationException("Prime prompt ended without a terminal outcome.");
        }

        internal static async Task RunOwnedPromptAsync(
            AgentChatClient client,
            Uri baseUri,
            string conversationId,
            string text,
            IReadOnlyList<ChatImageInput> images,
            Action<ChatEvent> onEvent,
            CancellationToken ct,
            Action? onDispatch = null)
        {
            try
            {
                await client.PromptAsync(baseUri, conversationId, text, images, onEvent, ct, onDispatch);
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

        /// <summary>
        /// Runs on the reader (thread-pool) thread. Every effect is a queued
        /// presentation item; nothing here touches the UI or blocks. Request truth
        /// (<c>_terminalSeen</c>) is recorded inline before its visual is queued.
        /// </summary>
        private void HandleChatEvent(ChatEvent evt)
        {
            // Diagnostic / test entry: attribute the event to the current request.
            PromptState? state;
            lock (_promptGate) state = _activePrompt;
            HandlePromptEvent(state ?? new PromptState(ActiveRequestId), evt);
        }

        private void HandlePromptEvent(PromptState state, ChatEvent evt)
        {
            if (!_uiAttached) return;
            var requestId = state.RequestId;
            switch (evt.Type)
            {
                case "session_status":
                    EnqueueControl(requestId, "session_status",
                        () => { if (_uiAttached) ApplyReportedSettings(evt.EffectiveSettings); },
                        emitsScripts: false);
                    break;
                case "text_delta":
                    EnqueueTextDelta(evt.Text ?? string.Empty);
                    break;
                case "thought_delta":
                    EnqueueThought("Prime is reasoning...");
                    break;
                case "tool_update":
                    HandleToolUpdate(evt);
                    break;
                case "terminal":
                    state.TerminalSeen = true;
                    // End marker (Contract 3): TranscriptFinalize (history) then
                    // ControlSettle (active request only). Neither invalidates anything.
                    ShowTypingIndicator(false);
                    FinalizeStreaming();
                    EnqueueControl(requestId, "settle:terminal", () => ApplyTerminalControls(evt));
                    break;
            }
        }

        /// <summary>The assistant buffer follows the queue order (UI thread).</summary>
        protected override void OnStreamingTextApplied(string mergedDelta)
        {
            lock (_promptGate) _assistantBuffer?.Append(mergedDelta);
        }

        private void HandleToolUpdate(ChatEvent evt)
        {
            // ACP tool cards are presentation only. They never certify a Rook
            // mutation; authentic Rook receipts and evidence retain that authority.
            var presentationOnly = !evt.CertifiesMutation;
            if (!presentationOnly || !_uiAttached) return;

            var id = EscapeForJavaScript(evt.MessageId ?? string.Empty);
            var name = EscapeForJavaScript(evt.Text ?? evt.Kind ?? "Tool");
            var status = ReadPayloadString(evt.Payload, "status");
            if (status == "completed" || status == "failed")
            {
                // Finalization keeps the active text bubble (today's behaviour).
                var summary = EscapeForJavaScript(evt.Text ?? status);
                var badge = EscapeForJavaScript(status == "completed" ? "success" : "failed");
                EnqueueContent("tool:finalize", () =>
                    PostContentScript($"window.chatAPI.finalizeToolCard('{id}', null, null, '{summary}', '{badge}')"));
            }
            else
            {
                // A rendered card finalizes the current bubble; subsequent text starts a
                // new segment. The buffer clear is itself an ordered item, so a delta
                // that arrives after this event can never be wiped by it.
                var payload = BoundToolCardPayload(evt.Payload);
                EnqueueContent("segment-break", () => { lock (_promptGate) _assistantBuffer?.Clear(); }, emitsScripts: false);
                EnqueueContent("tool:card", () =>
                    PostContentScript($"window.chatAPI.renderToolCard('{name}', {payload}, '{id}')"));
            }
        }

        /// <summary>
        /// Tool cards show at most three keys, so payloads over
        /// <see cref="MaxToolCardPayloadBytes"/> are summarized before they become a
        /// script literal (a 65 KB catalog was one synchronous script before this).
        /// </summary>
        internal static string BoundToolCardPayload(JsonElement? payload)
        {
            var raw = payload?.GetRawText() ?? "{}";
            if (raw.Length <= MaxToolCardPayloadBytes) return raw;
            var keys = new List<string>();
            if (payload.HasValue && payload.Value.ValueKind == JsonValueKind.Object)
            {
                foreach (var property in payload.Value.EnumerateObject())
                {
                    keys.Add(property.Name);
                    if (keys.Count == 3) break;
                }
            }
            return JsonSerializer.Serialize(new { truncated = true, bytes = raw.Length, keys });
        }

        /// <summary>
        /// Apply a terminal presentation immediately from the UI thread: the history
        /// half (typing off, finalize) followed by the control half. The stream path
        /// queues these as separate items via <see cref="HandleChatEvent"/>; this
        /// entry exists for callers that already hold the UI thread and for tests.
        /// </summary>
        private void ApplyTerminal(ChatEvent evt)
        {
            ShowTypingIndicator(false);
            FinalizeStreaming();
            ApplyTerminalControls(evt);
        }

        /// <summary>Control half of the end marker: applied only while its request is active. UI thread.</summary>
        private void ApplyTerminalControls(ChatEvent evt)
        {
            if (!_uiAttached) return;
            SetProcessingUi(false);
            var status = evt.Outcome switch
            {
                "settled" => "Ready",
                "cancelled" => "Cancelled",
                "incomplete" => "Prime turn incomplete",
                "refused" => "Prime refused the request",
                _ => evt.PresentationOutcome == "stream_failed"
                    ? "Request failed; live presentation failed."
                    : evt.ErrorCode switch
                    {
                        "conversation_busy" => "Another request is active. Wait for it to finish.",
                        "conversation_not_open" => "Conversation is not open. Open or reopen a conversation from the conversation list.",
                        "target_unavailable" => "Rhino document unavailable. Check the bound document.",
                        "runtime_unavailable" => "The conversation runtime is unavailable.",
                        _ => "Request failed; the cause was not reported.",
                    },
            };
            if (evt.PresentationOutcome == "stream_failed" && !status.Contains("live presentation failed"))
                status += " (live presentation failed)";
            SetStatusUi(status, evt.Outcome == "settled" ? Colors.Green : Colors.Orange);
            if (evt.Outcome == "settled")
            {
                _hasCompletedTurn = true;
                GuidanceContextChanged?.Invoke();
            }
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
                SubmissionBlockReason ?? (view.TargetAvailable ? "Conversation connected" : "Conversation connected; Rhino document unavailable"),
                SubmissionBlockReason == null && view.TargetAvailable ? Colors.Green : Colors.Orange);
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
            _hasReportedModel = !string.IsNullOrEmpty(settings?.Model);
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
            GuidanceContextChanged?.Invoke();
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
