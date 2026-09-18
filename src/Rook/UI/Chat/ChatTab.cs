using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Eto.Forms;
using Eto.Drawing;
using Rhino;
using Rook.UI.Web;

namespace Rook.UI.Chat
{
    /// <summary>
    /// Abstract base class for tabbed chat panels. Provides WebView-based rich text
    /// rendering, input area, Send/Stop/Clear buttons, status label, and streaming
    /// support. Subclasses implement message sending and stop logic.
    ///
    /// Uses <see cref="RookWebSurface"/> for the hardened WebView host (virtual host,
    /// CSP, nonce injection, in-memory resource serving).
    /// </summary>
    public abstract class ChatTab : Panel
    {
        private static int s_nextHostedSurfaceId;

        // ─── Web surface (substrate) ──────────────────────────────────
        private readonly ChatWebSurface _webSurface;

        // ─── Eto controls ─────────────────────────────────────────────
        private TextArea _inputArea = null!;
        private Button _sendButton = null!;
        private Button? _secondaryActionButton;
        private Button _clearButton = null!;
        private Button _stopButton = null!;
        private TableLayout _actionButtonLayout = null!;
        private Label _statusLabel = null!;
        private StackLayout _statusStack = null!;

        // ─── Fallback chat (when WebView is unavailable) ──────────────
        private TextArea? _fallbackChat;

        // ─── State ────────────────────────────────────────────────────
        private bool _isProcessing;
        private bool _tabClosed;
        private bool _useWebComposer;
        private Func<string, Task>? _secondaryAction;

        // ─── Public properties ────────────────────────────────────────

        /// <summary>
        /// Display name shown on the tab header.
        /// </summary>
        public string TabLabel { get; }

        /// <summary>
        /// Accent color for this tab (used in tab strip rendering).
        /// </summary>
        public Color TabColor { get; }

        internal string HostedSurfaceId { get; }

        // ─── Abstract / virtual hooks ─────────────────────────────────

        /// <summary>
        /// Called when the user clicks Send (or presses Enter). Subclasses
        /// must implement the actual message dispatch.
        /// </summary>
        protected abstract Task OnSendMessage(string message);

        /// <summary>
        /// Called when the user clicks Stop. Subclasses must cancel any
        /// in-flight request.
        /// </summary>
        protected abstract void OnStopRequested();

        /// <summary>
        /// True when Stop requests cancellation but the active transport remains
        /// authoritative until it publishes its terminal outcome.
        /// </summary>
        protected virtual bool WaitForStopSettlement => false;

        /// <summary>
        /// Called when the tab is removed from the tab strip. Override to
        /// release resources. Safe to call multiple times.
        /// </summary>
        public virtual void OnTabClosed()
        {
            CloseWebSurface();
        }

        /// <summary>
        /// Called when the Clear button is clicked, after the UI has been
        /// cleared. Override to reset conversation state in the subclass.
        /// The default implementation does nothing.
        /// </summary>
        protected virtual void OnClearRequested()
        {
        }

        /// <summary>
        /// Receives the closed WebView composer envelope. AgentChat overrides this
        /// for image-capable ACP prompts; other tabs retain the Eto text composer.
        /// </summary>
        protected virtual Task OnWebSubmitAsync(string text, IReadOnlyList<ChatImageInput> images)
            => images.Count == 0 ? OnSendMessage(text) : Task.FromException(
                new InvalidOperationException("This chat does not accept images."));

        // ─── Constructor ──────────────────────────────────────────────

        /// <summary>
        /// Create a new ChatTab.
        /// </summary>
        /// <param name="tabLabel">Display name for the tab header.</param>
        /// <param name="tabColor">Accent color for the tab.</param>
        /// <param name="hostedSurfaceType">Stable type prefix for panel lifecycle reconciliation.</param>
        protected ChatTab(string tabLabel, Color tabColor, string hostedSurfaceType)
            : this(tabLabel, tabColor, hostedSurfaceType, initializePresentation: true)
        {
        }

        protected ChatTab(
            string tabLabel,
            Color tabColor,
            string hostedSurfaceType,
            bool initializePresentation)
        {
            TabLabel = tabLabel;
            TabColor = tabColor;
            HostedSurfaceId =
                hostedSurfaceType + ":" +
                Interlocked.Increment(ref s_nextHostedSurfaceId).ToString();
            _webSurface = new ChatWebSurface(this);
            if (!initializePresentation) return;
            InitializeComponents();
            LayoutControls();
            AttachEvents();
        }

        // ─── UI initialisation ───────────────────────────────────────

        private void InitializeComponents()
        {
            _statusLabel = new Label
            {
                Text = "Ready",
                TextColor = Colors.Gray
            };

            _inputArea = new TextArea
            {
                Height = 60,
                Wrap = true
            };

            _sendButton = new Button { Text = "Send", Width = 70 };
            _stopButton = new Button { Text = "Stop", Width = 70, Enabled = false };
            _clearButton = new Button { Text = "Clear", Width = 70 };
        }

        private void LayoutControls()
        {
            // Get the WebView (or fallback) from the substrate
            var chatContainer = _webSurface.CreateWebContent();

            // If CreateWebContent returned a TextArea fallback, capture it
            // so AddMessageToChat can append text in degraded mode.
            if (chatContainer is TextArea fallback)
                _fallbackChat = fallback;

            // Status cell is a vertical stack: the status label, plus an optional
            // auxiliary row that subclasses fill via SetAuxiliaryRow. With a single
            // item, StackLayout applies no inter-item spacing, so tabs that never
            // set an auxiliary row render identically to the original single-label
            // status row.
            _statusStack = new StackLayout
            {
                Orientation = Orientation.Vertical,
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
                Spacing = 5,
            };
            _statusStack.Items.Add(new StackLayoutItem(_statusLabel, HorizontalAlignment.Left));

            _actionButtonLayout = new TableLayout
            {
                Spacing = new Size(5, 0),
                Rows = { new TableRow(_sendButton, _stopButton, _clearButton, null) }
            };

            var layout = new TableLayout
            {
                Padding = new Padding(5),
                Spacing = new Size(5, 5),
                Rows =
                {
                    new TableRow(chatContainer) { ScaleHeight = true },

                    new TableRow(_statusStack),

                    new TableRow(_inputArea),

                    new TableRow(_actionButtonLayout)
                }
            };

            Content = layout;
        }

        // ─── JavaScript helpers ──────────────────────────────────────

        /// <summary>
        /// Execute JavaScript in the WebView on the UI thread.
        /// </summary>
        protected void ExecuteScript(string script)
        {
            _webSurface.ExecuteScript(script);
        }

        protected void EnableWebComposer()
        {
            _useWebComposer = true;
            ExecuteScript("window.chatAPI.setComposerEnabled(true, true)");
        }

        /// <summary>
        /// Releases the shared WebView substrate. Subclass close handlers
        /// call this before their own resource cleanup.
        /// </summary>
        protected bool CloseWebSurface()
        {
            if (_tabClosed) return false;
            _tabClosed = true;
            Content = null;
            _webSurface.Dispose();
            return true;
        }

        /// <summary>
        /// Durable per-tab desired-visibility forwarder. Chat's own
        /// TabControl selection is authoritative for hosted tabs —
        /// selected maps to true, unselected to false (reconciler spec
        /// 2026-06-10).
        /// </summary>
        internal void SetPresentationDesiredVisible(bool visible, string reason)
        {
            if (_tabClosed) return;
            _webSurface.SetPresentationDesiredVisible(visible, reason);
        }

        /// <summary>
        /// Level-triggered reconcile request forwarder, used on the
        /// selected tab.
        /// </summary>
        internal void RequestPresentationReconcile(string reason)
        {
            if (_tabClosed) return;
            _webSurface.RequestPresentationReconcile(reason);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                OnTabClosed();
            }
            base.Dispose(disposing);
        }

        /// <summary>
        /// Escape a string for safe embedding in a JavaScript string literal.
        /// </summary>
        protected static string EscapeForJavaScript(string input)
        {
            return RookWebSurface.EscapeForJavaScript(input);
        }

        // ─── Chat display methods ────────────────────────────────────

        /// <summary>
        /// Add a message bubble to the chat display.
        /// </summary>
        protected void AddMessageToChat(string role, string content)
        {
            if (_webSurface.IsWebViewReady)
            {
                var escapedContent = EscapeForJavaScript(content);
                ExecuteScript($"window.chatAPI.addMessage('{role}', '{escapedContent}')");
            }
            else if (_fallbackChat != null)
            {
                var prefix = role == "user" ? "You: " : role == "assistant" ? "Rook: " : $"[{role}]: ";
                _fallbackChat.Append($"{prefix}{content}\n\n");
            }
        }

        /// <summary>
        /// Update (or create) the currently-streaming assistant message.
        /// </summary>
        protected void UpdateStreamingChat(string content)
        {
            if (_webSurface.IsWebViewReady)
            {
                var escapedContent = EscapeForJavaScript(content);
                ExecuteScript($"window.chatAPI.updateStreamingMessage('{escapedContent}')");
            }
        }

        /// <summary>
        /// Show or hide the typing indicator dots.
        /// </summary>
        protected void ShowTypingIndicator(bool show)
        {
            if (_webSurface.IsWebViewReady)
            {
                ExecuteScript($"window.chatAPI.showTypingIndicator({(show ? "true" : "false")})");
            }
        }

        /// <summary>
        /// End the current streaming message.
        /// </summary>
        protected void FinalizeStreaming()
        {
            if (_webSurface.IsWebViewReady)
            {
                ExecuteScript("window.chatAPI.finalizeStreamingMessage()");
            }
        }

        /// <summary>
        /// Add a base64-encoded image to the chat display.
        /// </summary>
        protected void AddImageToChat(string base64Data)
        {
            if (_webSurface.IsWebViewReady)
            {
                ExecuteScript($"window.chatAPI.addImage('{base64Data}')");
            }
        }

        // ─── Status helpers ──────────────────────────────────────────

        protected void SetStatus(string text, Color color)
        {
            Application.Instance.Invoke(() =>
            {
                _statusLabel.Text = text;
                _statusLabel.TextColor = color;
            });
        }

        /// <summary>
        /// Set (or clear) an optional control shown directly beneath the status
        /// label. Passing null removes it, restoring the bare status row. The
        /// auxiliary control is only ever parented to the status stack, so this
        /// never re-parents shared controls. Neutral: the base attaches no
        /// meaning to the row's contents.
        /// </summary>
        protected void SetAuxiliaryRow(Control? row)
        {
            // Keep item 0 (the status label); drop any previously-set aux item.
            while (_statusStack.Items.Count > 1)
                _statusStack.Items.RemoveAt(_statusStack.Items.Count - 1);

            if (row != null)
                _statusStack.Items.Add(new StackLayoutItem(row, HorizontalAlignment.Left));
        }

        /// <summary>
        /// Read-only view of the chat-tab's processing state for subclasses
        /// that need to coordinate side-channel input (e.g. WebView UI block
        /// submissions) with the typed-message lifecycle. The base class
        /// already disables the input area / Send button while processing,
        /// but a WebView's Apply button is not gated by Eto controls and
        /// can fire while a typed message is in flight.
        /// </summary>
        protected bool IsProcessing => _isProcessing;

        internal static string? NormalizeSubmittedMessage(string? input)
            => input?.Trim();

        internal static bool CanSubmitMessage(string? acceptedIntent, bool isProcessing)
            => !isProcessing && !string.IsNullOrEmpty(acceptedIntent);

        internal static bool MessageActionsEnabled(bool isProcessing)
            => !isProcessing;

        protected void ConfigureSecondaryAction(string label, Func<string, Task> action)
        {
            if (string.IsNullOrWhiteSpace(label))
                throw new ArgumentException("Secondary action label is required.", nameof(label));
            _secondaryAction = action ?? throw new ArgumentNullException(nameof(action));
            _secondaryActionButton = new Button
            {
                Text = label,
                Width = 80,
                Enabled = MessageActionsEnabled(_isProcessing),
            };
            _secondaryActionButton.Click += OnSecondaryActionClicked;
            _actionButtonLayout.Rows.Clear();
            _actionButtonLayout.Rows.Add(
                new TableRow(_sendButton, _secondaryActionButton, _stopButton, _clearButton, null));
        }

        protected void SetProcessing(bool processing)
        {
            _isProcessing = processing;
            Application.Instance.Invoke(() =>
            {
                UpdateUIState();
                if (_useWebComposer)
                    ExecuteScript($"window.chatAPI.setComposerEnabled(true, {(processing ? "false" : "true")})");
            });
        }

        // ─── Event wiring ────────────────────────────────────────────

        private void AttachEvents()
        {
            _sendButton.Click += OnSendClicked;
            _stopButton.Click += OnStopClicked;
            _clearButton.Click += OnClearClicked;

            _inputArea.KeyDown += (s, e) =>
            {
                if (e.Key == Keys.Enter && !e.Modifiers.HasFlag(Keys.Shift))
                {
                    e.Handled = true;
                    OnSendClicked(s, e);
                }
            };
        }

        // ─── Button handlers ─────────────────────────────────────────

        private async void OnSendClicked(object? sender, EventArgs e)
            => await SubmitInputAsync(OnSendMessage);

        private async void OnSecondaryActionClicked(object? sender, EventArgs e)
        {
            var action = _secondaryAction;
            if (action == null)
                return;
            await SubmitInputAsync(action);
        }

        private async Task SubmitInputAsync(Func<string, Task> action)
        {
            var message = NormalizeSubmittedMessage(_inputArea.Text);
            if (!CanSubmitMessage(message, _isProcessing))
                return;
            var acceptedIntent = message!;

            _isProcessing = true;
            UpdateUIState();

            _inputArea.Text = "";

            AddMessageToChat("user", acceptedIntent);
            ShowTypingIndicator(true);

            SetStatus("Sending...", Colors.Blue);

            try
            {
                await action(acceptedIntent);
            }
            catch (Exception ex)
            {
                Application.Instance.Invoke(() =>
                {
                    ShowTypingIndicator(false);
                    AddMessageToChat("error", ex.Message);
                    _isProcessing = false;
                    UpdateUIState();
                    SetStatus("Error", Colors.Red);
                });
            }
        }

        private void OnStopClicked(object? sender, EventArgs e)
        {
            OnStopRequested();
            if (WaitForStopSettlement)
            {
                SetStatus("Stopping...", Colors.Orange);
                return;
            }
            ShowTypingIndicator(false);
            FinalizeStreaming();
            _isProcessing = false;
            UpdateUIState();
            SetStatus("Stopped", Colors.Orange);
        }

        private void OnClearClicked(object? sender, EventArgs e)
        {
            if (_webSurface.IsWebViewReady)
            {
                ExecuteScript("window.chatAPI.clearMessages()");
            }
            else if (_fallbackChat != null)
            {
                _fallbackChat.Text = "";
            }

            OnClearRequested();

            SetStatus("Chat cleared", Colors.Gray);
        }

        private void UpdateUIState()
        {
            var messageActionsEnabled = MessageActionsEnabled(_isProcessing);
            _sendButton.Enabled = messageActionsEnabled;
            if (_secondaryActionButton != null)
                _secondaryActionButton.Enabled = messageActionsEnabled;
            _stopButton.Enabled = _isProcessing;
            _inputArea.Enabled = !_isProcessing;
            OnUIStateUpdated();
        }

        /// <summary>
        /// Called at the end of UpdateUIState (a runtime method, never invoked
        /// during construction). Subclasses override to re-evaluate their own
        /// controls on processing-state transitions, including the base-owned
        /// Stop button. Default is a no-op.
        /// </summary>
        protected virtual void OnUIStateUpdated()
        {
        }

        // ─── Chat-specific Web Surface ───────────────────────────────

        /// <summary>
        /// Chat-specific implementation of <see cref="RookWebSurface"/>.
        /// Declares the chat resource root, entry page, and fallback HTML.
        /// </summary>
        private class ChatWebSurface : RookWebSurface
        {
            private readonly ChatTab _owner;

            public ChatWebSurface(ChatTab owner)
            {
                _owner = owner;
                RegisterBridgeHandler("submit", HandleSubmit);
            }

            private async Task<JsonNode?> HandleSubmit(JsonNode? args)
            {
                if (args is not JsonObject obj || obj.Count != 3 ||
                    obj["type"]?.GetValue<string>() != "submit" ||
                    obj["text"] is not JsonValue textValue ||
                    obj["images"] is not JsonArray imageArray)
                    throw new InvalidOperationException("Chat submission is invalid.");

                var text = ChatTab.NormalizeSubmittedMessage(textValue.GetValue<string>());
                if (string.IsNullOrEmpty(text) && imageArray.Count == 0)
                    return null;
                if (imageArray.Count > AgentChatClient.MaxImagesPerTurn)
                    throw new InvalidOperationException("Too many images were attached.");

                var images = new List<ChatImageInput>(imageArray.Count);
                foreach (var node in imageArray)
                {
                    if (node is not JsonObject image || image.Count != 3)
                        throw new InvalidOperationException("Image submission is invalid.");
                    var fileName = image["fileName"]?.GetValue<string>();
                    var mimeType = image["mimeType"]?.GetValue<string>();
                    var base64Data = image["base64Data"]?.GetValue<string>();
                    if (string.IsNullOrEmpty(fileName) || string.IsNullOrEmpty(mimeType) || base64Data == null)
                        throw new InvalidOperationException("Image submission is invalid.");
                    images.Add(new ChatImageInput(fileName!, mimeType!, base64Data));
                }

                await _owner.SubmitWebInputAsync(text ?? string.Empty, images);
                return null;
            }

            protected override string ResourceRoot => "Rook.UI.Chat.Resources";
            protected override string EntryPage => "chat.html";

            protected override string MinimalFallbackHtml => @"<!DOCTYPE html>
<html>
<head>
    <meta charset='UTF-8'>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-size: 14px;
            padding: 10px;
            background: #1e1e1e;
            color: #e0e0e0;
            height: 100vh;
            overflow: hidden;
        }
        #messages {
            height: calc(100vh - 20px);
            overflow-y: auto;
            padding-right: 5px;
        }
        #messages::-webkit-scrollbar { width: 8px; }
        #messages::-webkit-scrollbar-track { background: #2d2d2d; border-radius: 4px; }
        #messages::-webkit-scrollbar-thumb { background: #555; border-radius: 4px; }
        .message {
            margin: 8px 0;
            padding: 10px 14px;
            border-radius: 12px;
            max-width: 85%;
            word-wrap: break-word;
        }
        .user-message {
            background: #0e639c;
            color: white;
            margin-left: auto;
            border-bottom-right-radius: 4px;
        }
        .assistant-message {
            background: #3c3c3c;
            margin-right: auto;
            border-bottom-left-radius: 4px;
        }
        .error-message {
            background: #5a2a2a;
            color: #f5c6cb;
            border-left: 3px solid #dc3545;
        }
        .system-message {
            background: #2a4a5a;
            color: #bee5eb;
            text-align: center;
            margin: 0 auto;
            font-size: 13px;
        }
        .agent-message {
            border-left: 3px solid var(--accent-color, #1d9bf0);
        }
        .agent-message .agent-avatar {
            display: inline-block;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background-color: var(--accent-color, #1d9bf0);
            text-align: center;
            line-height: 20px;
            font-size: 11px;
            font-weight: 700;
            color: #fff;
            margin-right: 8px;
            vertical-align: middle;
        }
        pre {
            background: #2d2d2d;
            padding: 10px;
            border-radius: 6px;
            overflow-x: auto;
            margin: 8px 0;
        }
        code {
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 13px;
        }
        .typing-indicator {
            display: flex;
            gap: 4px;
            padding: 10px 14px;
            background: #3c3c3c;
            border-radius: 12px;
            width: fit-content;
            margin-bottom: 8px;
        }
        .typing-indicator.hidden { display: none; }
        .typing-dot {
            width: 8px;
            height: 8px;
            background: #888;
            border-radius: 50%;
            animation: typing 1.4s infinite;
        }
        .typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .typing-dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes typing {
            0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
            30% { transform: translateY(-4px); opacity: 1; }
        }
        img { max-width: 100%; border-radius: 8px; cursor: pointer; }
    </style>
</head>
<body>
    <div id='messages'></div>
    <div id='typing-indicator' class='typing-indicator hidden'>
        <div class='typing-dot'></div>
        <div class='typing-dot'></div>
        <div class='typing-dot'></div>
    </div>
    <script>
        var streamingDiv = null;
        var agentColor = '#1d9bf0';
        var agentInitial = 'P';

        window.chatAPI = {
            addMessage: function(role, content) {
                var div = document.createElement('div');
                if (role === 'agent') {
                    div.className = 'message assistant-message agent-message';
                    div.style.setProperty('--accent-color', agentColor);
                    div.innerHTML = '<span class=\'agent-avatar\' style=\'background-color:' + agentColor + '\'>' + agentInitial + '</span>' + content.replace(/\\n/g, '<br>');
                } else {
                    div.className = 'message ' + role + '-message';
                    div.innerHTML = content.replace(/\\n/g, '<br>');
                }
                document.getElementById('messages').appendChild(div);
                this.scrollToBottom();
                return div;
            },
            updateStreamingMessage: function(content) {
                if (!streamingDiv) {
                    streamingDiv = this.addMessage('assistant', '');
                }
                streamingDiv.innerHTML = content.replace(/\\n/g, '<br>');
                this.scrollToBottom();
            },
            finalizeStreamingMessage: function() {
                streamingDiv = null;
            },
            showTypingIndicator: function(show) {
                document.getElementById('typing-indicator').classList.toggle('hidden', !show);
                if (show) this.scrollToBottom();
            },
            clearMessages: function() {
                document.getElementById('messages').innerHTML = '';
                streamingDiv = null;
            },
            addImage: function(b64) {
                var div = document.createElement('div');
                div.className = 'message assistant-message';
                var img = document.createElement('img');
                img.src = 'data:image/png;base64,' + b64;
                img.onclick = function() { window.open(img.src); };
                div.appendChild(img);
                document.getElementById('messages').appendChild(div);
                this.scrollToBottom();
            },
            scrollToBottom: function() {
                var msgs = document.getElementById('messages');
                msgs.scrollTop = msgs.scrollHeight;
            }
        };
    </script>
</body>
</html>";

            protected override void OnWebViewReady()
            {
                Application.Instance.Invoke(() =>
                {
                    _owner.SetStatus("Ready", Colors.Green);
                    if (_owner._useWebComposer)
                    {
                        _owner._inputArea.Visible = false;
                        _owner._sendButton.Visible = false;
                        _owner._actionButtonLayout.Visible = true;
                        _owner.ExecuteScript("window.chatAPI.setComposerEnabled(true, true)");
                    }
                });
            }
        }

        private async Task SubmitWebInputAsync(string text, IReadOnlyList<ChatImageInput> images)
        {
            if (_isProcessing) return;
            _isProcessing = true;
            UpdateUIState();
            if (!string.IsNullOrEmpty(text)) AddMessageToChat("user", text);
            ShowTypingIndicator(true);
            SetStatus("Sending...", Colors.Blue);
            try
            {
                await OnWebSubmitAsync(text, images);
            }
            catch (Exception ex)
            {
                Application.Instance.Invoke(() =>
                {
                    ShowTypingIndicator(false);
                    AddMessageToChat("error", ex.Message);
                    _isProcessing = false;
                    UpdateUIState();
                    SetStatus("Error", Colors.Red);
                });
            }
        }
    }
}
