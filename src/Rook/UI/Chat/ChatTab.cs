using System;
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
        // ─── Web surface (substrate) ──────────────────────────────────
        private readonly ChatWebSurface _webSurface;

        // ─── Eto controls ─────────────────────────────────────────────
        private TextArea _inputArea = null!;
        private Button _sendButton = null!;
        private Button _clearButton = null!;
        private Button _stopButton = null!;
        private Label _statusLabel = null!;

        // ─── Fallback chat (when WebView is unavailable) ──────────────
        private TextArea? _fallbackChat;

        // ─── State ────────────────────────────────────────────────────
        private bool _isProcessing;

        // ─── Public properties ────────────────────────────────────────

        /// <summary>
        /// Display name shown on the tab header.
        /// </summary>
        public string TabLabel { get; }

        /// <summary>
        /// Persona color for this tab (used in tab strip rendering).
        /// </summary>
        public Color TabColor { get; }

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
        /// Called when the tab is removed from the tab strip. Override to
        /// release resources. The default implementation does nothing.
        /// </summary>
        public virtual void OnTabClosed()
        {
        }

        /// <summary>
        /// Called when the Clear button is clicked, after the UI has been
        /// cleared. Override to reset conversation state in the subclass.
        /// The default implementation does nothing.
        /// </summary>
        protected virtual void OnClearRequested()
        {
        }

        // ─── Constructor ──────────────────────────────────────────────

        /// <summary>
        /// Create a new ChatTab.
        /// </summary>
        /// <param name="tabLabel">Display name for the tab header.</param>
        /// <param name="tabColor">Persona color for the tab.</param>
        protected ChatTab(string tabLabel, Color tabColor)
        {
            TabLabel = tabLabel;
            TabColor = tabColor;
            _webSurface = new ChatWebSurface(this);
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

            var layout = new TableLayout
            {
                Padding = new Padding(5),
                Spacing = new Size(5, 5),
                Rows =
                {
                    new TableRow(chatContainer) { ScaleHeight = true },

                    new TableRow(new TableLayout
                    {
                        Spacing = new Size(5, 0),
                        Rows = { new TableRow(_statusLabel, null) }
                    }),

                    new TableRow(_inputArea),

                    new TableRow(new TableLayout
                    {
                        Spacing = new Size(5, 0),
                        Rows = { new TableRow(_sendButton, _stopButton, _clearButton, null) }
                    })
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

        protected void SetProcessing(bool processing)
        {
            _isProcessing = processing;
            Application.Instance.Invoke(() =>
            {
                UpdateUIState();
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
        {
            var message = _inputArea.Text?.Trim();
            if (string.IsNullOrEmpty(message) || _isProcessing)
                return;

            _isProcessing = true;
            UpdateUIState();

            _inputArea.Text = "";

            AddMessageToChat("user", message);
            ShowTypingIndicator(true);

            SetStatus("Sending...", Colors.Blue);

            try
            {
                await OnSendMessage(message);
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
            _sendButton.Enabled = !_isProcessing;
            _stopButton.Enabled = _isProcessing;
            _inputArea.Enabled = !_isProcessing;
        }

        // ─── Chat-specific Web Surface ───────────────────────────────

        /// <summary>
        /// Chat-specific implementation of <see cref="RookWebSurface"/>.
        /// Declares the chat resource root, entry page, and fallback HTML.
        /// </summary>
        private class ChatWebSurface : RookWebSurface
        {
            private readonly ChatTab _owner;

            public ChatWebSurface(ChatTab owner) => _owner = owner;

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
            border-left: 3px solid var(--persona-color, #1d9bf0);
        }
        .agent-message .agent-avatar {
            display: inline-block;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background-color: var(--persona-color, #1d9bf0);
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
        var personaColor = '#1d9bf0';
        var personaInitial = 'A';

        window.chatAPI = {
            setPersona: function(color, initial) {
                personaColor = color || '#1d9bf0';
                personaInitial = initial || 'A';
                document.documentElement.style.setProperty('--persona-color', personaColor);
            },
            addMessage: function(role, content) {
                var div = document.createElement('div');
                if (role === 'agent') {
                    div.className = 'message assistant-message agent-message';
                    div.style.setProperty('--persona-color', personaColor);
                    div.innerHTML = '<span class=\'agent-avatar\' style=\'background-color:' + personaColor + '\'>' + personaInitial + '</span>' + content.replace(/\\n/g, '<br>');
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
                });
            }
        }
    }
}
