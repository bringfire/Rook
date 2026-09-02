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
    /// <summary>
    /// One Prime ACP conversation projected through the Python product service.
    /// The tab owns presentation only; the service owns ACP settlement and Prime.
    /// </summary>
    public sealed class AgentChatTab : ChatTab
    {
        private static readonly Color PrimeAccent = Color.FromArgb(0x25, 0x63, 0xeb);

        private readonly AgentChatClient _client;
        private readonly ConversationCloseCoordinator _closeCoordinator;
        private readonly CreateConversationRequest? _createRequest;
        private readonly ConversationSummary? _reopenAssociation;
        private readonly SemaphoreSlim _initializeGate = new(1, 1);
        private readonly object _promptGate = new();
        private readonly object _lifetimeGate = new();

        private string? _conversationId;
        private Uri? _conversationBaseUri;
        private volatile bool _uiAttached = true;
        private bool _deleted;
        private bool _terminalSeen;
        private StringBuilder? _assistantBuffer;

        public AgentChatTab(
            CreateConversationRequest createRequest,
            AgentChatClient? client = null,
            ConversationCloseCoordinator? closeCoordinator = null)
            : base("Prime", PrimeAccent, "agent-chat")
        {
            _createRequest = createRequest ?? throw new ArgumentNullException(nameof(createRequest));
            _client = client ?? new AgentChatClient();
            _closeCoordinator = closeCoordinator ?? ConversationCloseCoordinator.Instance;
            EnableWebComposer();
            ShowRequestedSettings(createRequest.Model, createRequest.Reasoning);
        }

        public AgentChatTab(
            ConversationSummary association,
            AgentChatClient? client = null,
            ConversationCloseCoordinator? closeCoordinator = null)
            : base("Prime", PrimeAccent, "agent-chat")
        {
            _reopenAssociation = association ?? throw new ArgumentNullException(nameof(association));
            _client = client ?? new AgentChatClient();
            _closeCoordinator = closeCoordinator ?? ConversationCloseCoordinator.Instance;
            EnableWebComposer();
            ShowRequestedSettings(association.RequestedInitialModel, association.RequestedInitialReasoning);
        }

        public string? ConversationId => _conversationId ?? _reopenAssociation?.ConversationId;

        protected override bool WaitForStopSettlement => true;

        public async Task InitializeAsync()
        {
            await _initializeGate.WaitAsync();
            try
            {
                var health = await _client.GetHealthAsync(startIfNeeded: true);
                if (!health.ServiceAvailable)
                    throw new InvalidOperationException(health.ServiceMessage);
                if (!health.RuntimeAvailable)
                    throw new InvalidOperationException("The installed Prime ACP runtime is unavailable.");

                _client.SetSessionNonce(ChatServiceManager.Instance.SessionNonce);
                ConversationView view;
                if (_reopenAssociation != null)
                {
                    view = await _client.ReopenAsync(_reopenAssociation.ConversationId);
                    if (!TryPublishConversation(view))
                    {
                        QueueClose(view.BaseUri, view.ConversationId);
                        return;
                    }
                    var history = await _client.GetHistoryAsync(
                        view.BaseUri ?? throw new InvalidOperationException("Prime conversation URI is unavailable."),
                        view.ConversationId,
                        CancellationToken.None);
                    RenderPresentationHistory(history);
                }
                else
                {
                    view = await _client.CreateAsync(_createRequest!);
                    if (!TryPublishConversation(view))
                    {
                        QueueClose(view.BaseUri, view.ConversationId);
                        return;
                    }
                }

                ApplyConversationStatus(view);
                AddMessageToChat("system", _reopenAssociation == null
                    ? "Prime is ready. This conversation becomes durable after its first completed turn."
                    : "Prime conversation reopened.");
            }
            catch (Exception ex)
            {
                SetStatus("Conversation unavailable", Colors.Red);
                AddMessageToChat("error", ex.Message);
            }
            finally
            {
                _initializeGate.Release();
            }
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

            await _client.PromptAsync(
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

        private void HandleChatEvent(ChatEvent evt)
        {
            if (!_uiAttached) return;
            switch (evt.Type)
            {
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
            if (result.AssociationRemoved)
            {
                lock (_lifetimeGate)
                {
                    _deleted = true;
                    _uiAttached = false;
                }
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
            if (!CloseWebSurface()) return;
            Uri? baseUri;
            string? conversationId;
            bool deleted;
            lock (_lifetimeGate)
            {
                _uiAttached = false;
                baseUri = _conversationBaseUri;
                conversationId = _conversationId;
                deleted = _deleted;
                _conversationBaseUri = null;
                _conversationId = null;
            }
            if (!deleted) QueueClose(baseUri, conversationId);
            _client.Dispose();
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
            if (!history.Available)
            {
                AddMessageToChat("system", history.Message ?? "Presentation history unavailable.");
                return;
            }
            if (history.EarlierHistoryOmitted)
                AddMessageToChat("system", history.Message ?? "Earlier presentation history was omitted. Prime retains the authoritative conversation state.");
            foreach (var turn in history.Turns)
            {
                if (turn.Fallback)
                {
                    AddMessageToChat("system", turn.Message ?? "A bounded presentation projection was unavailable for this turn.");
                    continue;
                }
                if (!string.IsNullOrEmpty(turn.UserText)) AddMessageToChat("user", turn.UserText);
                foreach (var image in turn.Images)
                    AddMessageToChat("system", $"Image preview unavailable after reopen: {image.FileName} ({image.MimeType}, {image.BinaryByteCount} bytes).");
                if (!string.IsNullOrEmpty(turn.AssistantText)) AddMessageToChat("assistant", turn.AssistantText);
                if (turn.ToolCards.Count > 0)
                    AddMessageToChat("system", $"{turn.ToolCards.Count} bounded tool update{(turn.ToolCards.Count == 1 ? "" : "s")} recorded for this turn.");
            }
        }

        private void ApplyConversationStatus(ConversationView view)
        {
            SetStatus(
                view.TargetAvailable ? "Prime ready" : "Prime ready; Rook target unavailable",
                view.TargetAvailable ? Colors.Green : Colors.Orange);
        }

        private void ShowRequestedSettings(string? model, string? reasoning)
        {
            if (string.IsNullOrEmpty(model) && string.IsNullOrEmpty(reasoning)) return;
            var parts = new List<string>();
            if (!string.IsNullOrEmpty(model)) parts.Add("Requested model: " + model);
            if (!string.IsNullOrEmpty(reasoning)) parts.Add("reasoning: " + reasoning);
            SetAuxiliaryRow(new Label { Text = string.Join("; ", parts), TextColor = Colors.Gray });
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
