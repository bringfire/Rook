using System;
using System.Collections.Generic;
using System.Linq;
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
        private DropDown? _modelDropDown;
        private Button? _applyModelButton;
        private bool _suppressModelSelectionEvents;
        private bool _modelListAvailable;
        private bool _modelSelectionDirty;

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
            BuildModelSelector();
        }

        private void BuildModelSelector()
        {
            _modelDropDown = new DropDown();
            _modelDropDown.SelectedValueChanged += (s, e) =>
            {
                if (_suppressModelSelectionEvents)
                    return;
                _modelSelectionDirty = !string.Equals(
                    _modelDropDown?.SelectedKey, _activeModelLabel, StringComparison.Ordinal);
                UpdateApplyEnabled();
            };

            _applyModelButton = new Button { Text = "Apply", Width = 70, Enabled = false };
            _applyModelButton.Click += OnApplyModelClicked;

            var label = new Label
            {
                Text = "Model:",
                VerticalAlignment = VerticalAlignment.Center,
            };

            var row = new StackLayout
            {
                Orientation = Orientation.Horizontal,
                Spacing = 5,
                VerticalContentAlignment = VerticalAlignment.Center,
                Items =
                {
                    new StackLayoutItem(label),
                    new StackLayoutItem(_modelDropDown, expand: true),
                    new StackLayoutItem(_applyModelButton),
                }
            };

            SetAuxiliaryRow(row);
        }

        private void PopulateModelSelector(List<string> allowed, string activeModel)
        {
            if (_modelDropDown == null)
                return;

            // Preserve a deliberate, still-valid user selection across refreshes
            // (e.g. a pending choice made while a turn was streaming).
            var previousSelectedKey = _modelDropDown.SelectedKey;

            // Items = allowed overrides, with the active model guaranteed present
            // (prepended) so the control always reflects the true active model.
            var items = new List<string>();
            if (!string.IsNullOrEmpty(activeModel))
                items.Add(activeModel);
            foreach (var m in allowed)
            {
                if (!string.IsNullOrEmpty(m) && !items.Contains(m))
                    items.Add(m);
            }

            _modelListAvailable = items.Count > 0;

            var preservePending =
                _modelSelectionDirty
                && !string.IsNullOrEmpty(previousSelectedKey)
                && items.Contains(previousSelectedKey!)
                && !string.Equals(previousSelectedKey, activeModel, StringComparison.Ordinal);

            var selectedKey = preservePending ? previousSelectedKey! : activeModel;
            if (!preservePending)
                _modelSelectionDirty = false;

            _suppressModelSelectionEvents = true;
            try
            {
                _modelDropDown.Items.Clear();
                foreach (var m in items)
                    _modelDropDown.Items.Add(new ListItem { Text = m, Key = m });
                _modelDropDown.SelectedKey = selectedKey;
            }
            finally
            {
                _suppressModelSelectionEvents = false;
            }

            UpdateApplyEnabled();
        }

        private void PopulateModelSelector(List<ModelOverrideOption> options, string activeModel)
        {
            if (_modelDropDown == null)
                return;

            var previousSelectedKey = _modelDropDown.SelectedKey;
            var eligible = EligibleOptions(options);
            var activeIsEligible = eligible.Any(
                o => string.Equals(o.Id, activeModel, StringComparison.Ordinal));

            _modelListAvailable = eligible.Count > 0;

            var preservePending =
                _modelSelectionDirty
                && !string.IsNullOrEmpty(previousSelectedKey)
                && eligible.Any(o => string.Equals(o.Id, previousSelectedKey, StringComparison.Ordinal))
                && !string.Equals(previousSelectedKey, activeModel, StringComparison.Ordinal);

            // Dropdown stays applyable-only: the active model is added/selected only when
            // it is itself eligible. An ineligible/unknown active model lives in the status
            // label (set by the caller), never as a selectable row.
            string? selectedKey = preservePending
                ? previousSelectedKey
                : (activeIsEligible ? activeModel : null);
            if (!preservePending)
                _modelSelectionDirty = false;

            _suppressModelSelectionEvents = true;
            try
            {
                _modelDropDown.Items.Clear();
                foreach (var o in eligible)
                    _modelDropDown.Items.Add(new ListItem { Text = BuildRowText(o), Key = o.Id });
                _modelDropDown.SelectedKey = selectedKey;
            }
            finally
            {
                _suppressModelSelectionEvents = false;
            }

            UpdateApplyEnabled();
        }

        private void UpdateApplyEnabled()
        {
            if (_applyModelButton == null || _modelDropDown == null)
                return;

            _applyModelButton.Enabled = ShouldEnableApply(
                hasConversation: !string.IsNullOrEmpty(_conversationId),
                isProcessing: IsProcessing,
                listAvailable: _modelListAvailable,
                selectedModel: _modelDropDown.SelectedKey,
                activeModel: _activeModelLabel);
        }

        /// <summary>
        /// Reset selector state when the conversation identity is cleared, so no
        /// stale models or enabled Apply linger from a prior conversation. Must
        /// run on the UI thread (touches Eto controls).
        /// </summary>
        private void ClearModelSelector()
        {
            _modelListAvailable = false;
            _activeModelLabel = null;
            _modelSelectionDirty = false;

            if (_modelDropDown != null)
            {
                _suppressModelSelectionEvents = true;
                try
                {
                    _modelDropDown.Items.Clear();
                }
                finally
                {
                    _suppressModelSelectionEvents = false;
                }
            }

            UpdateApplyEnabled();
        }

        protected override void OnUIStateUpdated()
        {
            UpdateApplyEnabled();
        }

        private async void OnApplyModelClicked(object? sender, EventArgs e)
        {
            var dropDown = _modelDropDown;
            var baseUri = _conversationBaseUri;
            var conversationId = _conversationId;
            if (dropDown == null || baseUri == null || string.IsNullOrEmpty(conversationId))
                return;

            var selected = dropDown.SelectedKey;
            if (string.IsNullOrEmpty(selected) || selected == _activeModelLabel || IsProcessing)
                return;

            if (_applyModelButton != null)
                _applyModelButton.Enabled = false;
            SetStatus($"Switching model to {selected}...", Colors.Blue);

            try
            {
                var result = await _client.SetModelAsync(baseUri, conversationId!, selected!, "panel selector");
                Application.Instance.Invoke(() =>
                {
                    if (!IsCurrentConversation(conversationId!))
                        return;

                    if (result.Success)
                    {
                        _ = RefreshModelStatusAsync(conversationId);
                    }
                    else if (result.StatusCode == 409 || result.ErrorCode == "conversation_processing")
                    {
                        SetStatus("Finish the current reply before changing models.",
                            Color.FromArgb(0xd9, 0x77, 0x06));
                        UpdateApplyEnabled();
                    }
                    else if (result.StatusCode == 400 || result.ErrorCode == "model_override_unavailable")
                    {
                        SetStatus("That model is no longer available — list refreshed.",
                            Color.FromArgb(0xd9, 0x77, 0x06));
                        _ = RefreshModelStatusAsync(conversationId);
                    }
                    else if (result.StatusCode == 404)
                    {
                        _conversationId = null;
                        _conversationBaseUri = null;
                        ClearModelSelector();
                        SetStatus("Conversation not found — restart chat.", Colors.Red);
                    }
                    else
                    {
                        SetStatus(string.IsNullOrEmpty(result.Message)
                            ? "Model switch failed." : result.Message!, Colors.Red);
                        UpdateApplyEnabled();
                    }
                });
            }
            catch (Exception ex)
            {
                Application.Instance.Invoke(() =>
                {
                    SetStatus($"Model switch failed: {ex.Message}", Colors.Red);
                    UpdateApplyEnabled();
                });
            }
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

            Application.Instance.Invoke(ClearModelSelector);

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
                var allowed = models.AllowedModelOverrides ?? new List<string>();
                var options = models.AllowedModelOverrideOptions ?? new List<ModelOverrideOption>();

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
                    if (options.Count > 0)
                        PopulateModelSelector(options, activeModel!);
                    else
                        PopulateModelSelector(allowed, activeModel!);
                });
            }
            catch (OperationCanceledException)
            {
                // Refresh cancelled (e.g. conversation teardown) — nothing to surface.
            }
            catch (Exception)
            {
                // /agent/chat/models failed (e.g. a stale or mismatched chat runtime
                // returning 404). Don't blank the selector silently: fall back to the
                // locally-known active model and surface that the override list is
                // unavailable, so a runtime mismatch can never look "healthy".
                Application.Instance.Invoke(() =>
                {
                    if (!IsCurrentConversation(currentConversationId))
                    {
                        return;
                    }

                    var active = _activeModelLabel;
                    if (!string.IsNullOrEmpty(active))
                    {
                        PopulateModelSelector(new List<string>(), active!);
                    }

                    SetStatus(
                        string.IsNullOrEmpty(active)
                            ? "Model list unavailable"
                            : $"Model: {active} (list unavailable)",
                        Color.FromArgb(0xd9, 0x77, 0x06));
                });
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
                        var toolStatus = EscapeForJavaScript(evt.ToolStatus ?? "");
                        ExecuteScript(
                            $"window.chatAPI.finalizeToolCard('{EscapeForJavaScript(evt.ToolCallId ?? "")}', {verified}, '{note}', '{EscapeForJavaScript(summary)}', '{toolStatus}')");
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
                        ShowTypingIndicator(false);
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
                        ShowTypingIndicator(false);
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
                return evt.ToolStatus == "failed" ? "Failed" : "Done";

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
                    if (success.ValueKind == JsonValueKind.False)
                    {
                        if (root.TryGetProperty("error", out var error) &&
                            error.ValueKind == JsonValueKind.String)
                            return error.GetString() ?? "Failed";
                        if (root.TryGetProperty("message", out var message) &&
                            message.ValueKind == JsonValueKind.String)
                            return message.GetString() ?? "Failed";
                        if (root.TryGetProperty("data", out var dataElement) &&
                            dataElement.ValueKind == JsonValueKind.String)
                            return dataElement.GetString() ?? "Failed";
                        if (root.TryGetProperty("data", out dataElement) &&
                            dataElement.ValueKind == JsonValueKind.Object)
                        {
                            if (dataElement.TryGetProperty("error", out var dataError) &&
                                dataError.ValueKind == JsonValueKind.String)
                                return dataError.GetString() ?? "Failed";
                            if (dataElement.TryGetProperty("message", out var dataMessage) &&
                                dataMessage.ValueKind == JsonValueKind.String)
                                return dataMessage.GetString() ?? "Failed";
                        }
                        return "Failed";
                    }

                    if (success.ValueKind == JsonValueKind.True)
                    {
                        if (TryReadToolSummaryString(root, "message", out var successMessage))
                            return successMessage;
                        if (TryReadToolSummaryString(root, "status", out var successStatus))
                            return successStatus;
                        return "Success";
                    }
                }
            }
            catch
            {
                // Not valid JSON or unexpected structure
                if (evt.ToolStatus == "failed")
                    return evt.Result ?? "Failed";
            }

            if (evt.ToolStatus == "failed")
                return "Failed";

            return "Done";
        }

        private static bool TryReadToolSummaryString(JsonElement element, string propertyName, out string value)
        {
            value = string.Empty;
            if (!element.TryGetProperty(propertyName, out var property) ||
                property.ValueKind != JsonValueKind.String)
                return false;

            var rawValue = property.GetString();
            if (string.IsNullOrWhiteSpace(rawValue))
                return false;

            value = rawValue!;
            return true;
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

        internal static List<ModelOverrideOption> EligibleOptions(
            IEnumerable<ModelOverrideOption> options)
        {
            return options
                .Where(o => string.Equals(o.Eligibility, "eligible", StringComparison.Ordinal))
                .ToList();
        }

        internal static string BuildOptionLabel(ModelOverrideOption option)
        {
            return string.IsNullOrEmpty(option.DisplayName) ? option.Id : option.DisplayName;
        }

        internal static string BuildSelectionDetail(ModelOverrideOption option)
        {
            var parts = new List<string>();
            if (option.ContextLength.HasValue)
                parts.Add($"{option.ContextLength.Value} ctx");
            if (string.Equals(option.MetadataState, "stale", StringComparison.Ordinal))
                parts.Add("metadata stale — refresh");
            return string.Join(" · ", parts);
        }

        // Dropdown row text = friendly label, plus selection detail (ctx / stale hint)
        // when available. Eto DropDown has no per-row tooltip, so detail rides in the
        // row text. Role/local rows have no detail -> label only.
        internal static string BuildRowText(ModelOverrideOption option)
        {
            var label = BuildOptionLabel(option);
            var detail = BuildSelectionDetail(option);
            return detail.Length == 0 ? label : $"{label} — {detail}";
        }

        /// <summary>
        /// Pure decision for whether the panel Apply button should be enabled.
        /// Pending model is intentionally not an input: panel Apply uses
        /// /agent/chat/model only while inactive and applies to the next turn,
        /// so "selected equals active" is the sole disqualifier beyond gating.
        /// </summary>
        internal static bool ShouldEnableApply(
            bool hasConversation,
            bool isProcessing,
            bool listAvailable,
            string? selectedModel,
            string? activeModel)
        {
            if (!hasConversation || isProcessing || !listAvailable)
                return false;
            if (string.IsNullOrEmpty(selectedModel))
                return false;
            return !string.Equals(selectedModel, activeModel, StringComparison.Ordinal);
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
            ClearModelSelector();
            _cts?.Cancel();
            _cts?.Dispose();
            _cts = null;
            _client.Dispose();
        }
    }
}
