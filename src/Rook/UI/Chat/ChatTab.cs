using System;
using System.IO;
using System.Reflection;
using System.Threading.Tasks;
using Eto.Forms;
using Eto.Drawing;
using Rhino;
#if NET7_0_OR_GREATER
using Microsoft.Web.WebView2.Core;
#endif

namespace Rook.UI.Chat
{
    /// <summary>
    /// Abstract base class for tabbed chat panels. Provides WebView-based rich text
    /// rendering, input area, Send/Stop/Clear buttons, status label, and streaming
    /// support. Subclasses implement message sending and stop logic.
    /// </summary>
    public abstract class ChatTab : Panel
    {
        // ─── WebView ──────────────────────────────────────────────────────
        private WebView? _webView;
        private bool _webViewReady;

        // ─── Eto controls ─────────────────────────────────────────────────
        private TextArea _inputArea = null!;
        private Button _sendButton = null!;
        private Button _clearButton = null!;
        private Button _stopButton = null!;
        private Label _statusLabel = null!;

        // ─── Fallback chat (when WebView is unavailable) ──────────────────
        private TextArea? _fallbackChat;

        // ─── State ────────────────────────────────────────────────────────
        private bool _isProcessing;

        // ─── Public properties ────────────────────────────────────────────

        /// <summary>
        /// Display name shown on the tab header.
        /// </summary>
        public string TabLabel { get; }

        /// <summary>
        /// Persona color for this tab (used in tab strip rendering).
        /// </summary>
        public Color TabColor { get; }

        // ─── Abstract / virtual hooks ─────────────────────────────────────

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

        // ─── Constructor ──────────────────────────────────────────────────

        /// <summary>
        /// Create a new ChatTab.
        /// </summary>
        /// <param name="tabLabel">Display name for the tab header.</param>
        /// <param name="tabColor">Persona color for the tab.</param>
        protected ChatTab(string tabLabel, Color tabColor)
        {
            TabLabel = tabLabel;
            TabColor = tabColor;
            InitializeComponents();
            LayoutControls();
            AttachEvents();
        }

        // ─── UI initialisation (extracted from RookChatPanel) ─────────────

        /// <summary>
        /// Create the status label, input area, and control buttons.
        /// </summary>
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

        /// <summary>
        /// Arrange controls using TableLayout.
        /// </summary>
        private void LayoutControls()
        {
            var chatContainer = CreateChatContainer();

            var layout = new TableLayout
            {
                Padding = new Padding(5),
                Spacing = new Size(5, 5),
                Rows =
                {
                    // Chat display area (WebView or fallback)
                    new TableRow(chatContainer) { ScaleHeight = true },

                    // Status bar
                    new TableRow(new TableLayout
                    {
                        Spacing = new Size(5, 0),
                        Rows = { new TableRow(_statusLabel, null) }
                    }),

                    // Input area
                    new TableRow(_inputArea),

                    // Button row (no Settings button -- that stays in the panel)
                    new TableRow(new TableLayout
                    {
                        Spacing = new Size(5, 0),
                        Rows = { new TableRow(_sendButton, _stopButton, _clearButton, null) }
                    })
                }
            };

            Content = layout;
        }

        /// <summary>
        /// The virtual host origin used for all chat WebUI surfaces.
        /// RFC 6761 reserves .invalid — it will never resolve externally.
        /// </summary>
        internal const string VirtualHostName = "app.rook.invalid";
        internal static readonly string VirtualHostOrigin = $"https://{VirtualHostName}";

        /// <summary>
        /// Create the chat container (WebView with TextArea fallback).
        /// </summary>
        private Control CreateChatContainer()
        {
            try
            {
                _webView = new WebView();
                _webView.DocumentLoaded += OnDocumentLoaded;

#if NET7_0_OR_GREATER
                if (TrySetupVirtualHost())
                {
                    // Virtual host model — navigation happens in the
                    // CoreWebView2InitializationCompleted handler.
                    return _webView;
                }
#endif
                // Fallback: self-contained minimal HTML when virtual host is
                // unavailable (net48, missing WebView2).  The full chat.html
                // references relative vendor/ paths that can't resolve under
                // LoadHtml, so use the minimal version which is self-contained.
                var html = GetMinimalChatHtml();
                _webView.LoadHtml(html);

                return _webView;
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"WebView creation failed: {ex.Message}");
                return CreateFallbackChat();
            }
        }

#if NET7_0_OR_GREATER
        /// <summary>
        /// Set up WebView2 virtual host mapping so HTML/JS/CSS load from
        /// <c>https://app.rook.invalid/</c> backed by extracted embedded
        /// resources. Returns false if WebView2 native control is unavailable.
        /// </summary>
        private bool TrySetupVirtualHost()
        {
            try
            {
                // Access the native WPF WebView2 control through Eto's abstraction
                var nativeControl = _webView?.ControlObject;
                if (nativeControl == null)
                    return false;

                // The native control should be Microsoft.Web.WebView2.Wpf.WebView2.
                // Use reflection to access CoreWebView2InitializationCompleted and
                // avoid a hard type dependency on the WPF assembly (Rhino might
                // update the handler in future versions).
                var coreWv2Property = nativeControl.GetType().GetProperty("CoreWebView2");
                if (coreWv2Property == null)
                    return false;

                // CoreWebView2 may already be initialized (unlikely at construction
                // time) or we need to wait for the initialization event.
                var coreWv2 = coreWv2Property.GetValue(nativeControl) as CoreWebView2;
                if (coreWv2 != null)
                {
                    ConfigureVirtualHost(coreWv2);
                    return true;
                }

                // Subscribe to initialization completed event
                var initEvent = nativeControl.GetType().GetEvent("CoreWebView2InitializationCompleted");
                if (initEvent == null)
                    return false;

                // Use a typed delegate that matches the event signature
                EventHandler<CoreWebView2InitializationCompletedEventArgs> handler = null!;
                handler = (sender, args) =>
                {
                    initEvent.RemoveEventHandler(nativeControl, handler);
                    if (args.IsSuccess)
                    {
                        coreWv2 = coreWv2Property.GetValue(nativeControl) as CoreWebView2;
                        if (coreWv2 != null)
                            ConfigureVirtualHost(coreWv2);
                    }
                    else
                    {
                        RhinoApp.WriteLine($"Rook: WebView2 init failed, falling back to minimal HTML");
                        FallbackToMinimalHtml();
                    }
                };
                initEvent.AddEventHandler(nativeControl, handler);

                // Trigger initialization if not already started
                var ensureMethod = nativeControl.GetType().GetMethod("EnsureCoreWebView2Async",
                    new[] { typeof(CoreWebView2Environment) });
                ensureMethod?.Invoke(nativeControl, new object?[] { null });

                return true;
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"Rook: virtual host setup failed: {ex.Message}");
                return false;
            }
        }

        /// <summary>
        /// Configure virtual host via WebResourceRequested (serves embedded
        /// resources in-memory — no temp files on disk) and navigate.
        /// Called once CoreWebView2 is initialized.
        /// </summary>
        private async void ConfigureVirtualHost(CoreWebView2 coreWebView2)
        {
            try
            {
                // Intercept all requests to the virtual host and serve from
                // embedded resources.  No temp folder = no local tampering.
                coreWebView2.AddWebResourceRequestedFilter(
                    $"{VirtualHostOrigin}/*",
                    CoreWebView2WebResourceContext.All);
                coreWebView2.WebResourceRequested += OnWebResourceRequested;

                // Inject session nonce BEFORE navigation.  Awaiting ensures
                // the script is registered before the first page load.
                var nonce = ChatServiceManager.Instance.SessionNonce;
                if (!string.IsNullOrEmpty(nonce))
                {
                    var escapedNonce = EscapeForJavaScript(nonce);
                    await coreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(
                        $"window.__rookSessionNonce = '{escapedNonce}';");
                }

                coreWebView2.Navigate($"{VirtualHostOrigin}/chat.html");
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"Rook: virtual host navigation failed: {ex.Message}");
                FallbackToMinimalHtml();
            }
        }

        /// <summary>
        /// Serve embedded resources for <c>https://app.rook.invalid/*</c>
        /// requests.  Maps URL paths to assembly resource names.
        /// </summary>
        private void OnWebResourceRequested(object? sender, CoreWebView2WebResourceRequestedEventArgs e)
        {
            var uri = new Uri(e.Request.Uri);
            if (!uri.Host.Equals(VirtualHostName, StringComparison.OrdinalIgnoreCase))
                return;

            // Convert URL path to embedded resource name:
            //   /chat.html          → Rook.UI.Chat.Resources.chat.html
            //   /vendor/marked.min.js → Rook.UI.Chat.Resources.vendor.marked.min.js
            var path = uri.AbsolutePath.TrimStart('/').Replace('/', '.');
            var resourceName = $"Rook.UI.Chat.Resources.{path}";

            var assembly = Assembly.GetExecutingAssembly();
            var stream = assembly.GetManifestResourceStream(resourceName);
            if (stream == null)
            {
                // 404 for unknown resources
                return;
            }

            var headers = GetResponseHeaders(uri.AbsolutePath);
            var coreWv2 = sender as CoreWebView2;
            if (coreWv2 != null)
            {
                e.Response = coreWv2.Environment.CreateWebResourceResponse(
                    stream, 200, "OK", headers);
            }
        }

        // Content-Security-Policy for HTML resources served from the virtual host.
        // - script-src 'self' 'unsafe-inline': chat.html has a large inline <script>
        //   block; extracting it to chat.js would allow removing 'unsafe-inline'.
        // - connect-src: the critical directive — restricts fetch() targets to the
        //   virtual host and the localhost chat server.
        // - img-src: data: is needed for base64-encoded viewport captures.
        private const string ContentSecurityPolicy =
            "default-src 'none'; " +
            "script-src 'self' 'unsafe-inline'; " +
            "style-src 'self' 'unsafe-inline'; " +
            $"connect-src https://{VirtualHostName} http://127.0.0.1:*; " +
            "img-src 'self' data:; " +
            "font-src 'self'";

        private static string GetResponseHeaders(string path)
        {
            var contentType = GuessContentType(path);
            if (path.EndsWith(".html", StringComparison.OrdinalIgnoreCase))
            {
                return $"Content-Type: {contentType}\r\n" +
                       $"Content-Security-Policy: {ContentSecurityPolicy}";
            }
            return $"Content-Type: {contentType}";
        }

        private static string GuessContentType(string path)
        {
            if (path.EndsWith(".html", StringComparison.OrdinalIgnoreCase)) return "text/html; charset=utf-8";
            if (path.EndsWith(".css", StringComparison.OrdinalIgnoreCase)) return "text/css; charset=utf-8";
            if (path.EndsWith(".js", StringComparison.OrdinalIgnoreCase)) return "application/javascript; charset=utf-8";
            if (path.EndsWith(".json", StringComparison.OrdinalIgnoreCase)) return "application/json; charset=utf-8";
            if (path.EndsWith(".woff2", StringComparison.OrdinalIgnoreCase)) return "font/woff2";
            return "application/octet-stream";
        }

        /// <summary>
        /// Fall back to the self-contained minimal HTML (no vendor dependencies).
        /// Used when virtual host setup fails or WebView2 init fails.
        /// </summary>
        private void FallbackToMinimalHtml()
        {
            Application.Instance.Invoke(() =>
            {
                var html = GetMinimalChatHtml();
                _webView?.LoadHtml(html);
            });
        }
#endif

        /// <summary>
        /// Create a fallback text-based chat display.
        /// </summary>
        private Control CreateFallbackChat()
        {
            _fallbackChat = new TextArea
            {
                ReadOnly = true,
                Wrap = true,
                Font = new Font("Consolas", 10)
            };
            return _fallbackChat;
        }

        /// <summary>
        /// Called when the WebView finishes loading the HTML document.
        /// </summary>
        private void OnDocumentLoaded(object? sender, WebViewLoadedEventArgs e)
        {
            _webViewReady = true;
            Application.Instance.Invoke(() =>
            {
                _statusLabel.Text = "Ready";
                _statusLabel.TextColor = Colors.Green;
            });
        }

        // ─── Chat HTML ───────────────────────────────────────────────────

        /// <summary>
        /// Load the chat HTML from embedded resources, inlining the CSS.
        /// Falls back to <see cref="GetMinimalChatHtml"/> on failure.
        /// </summary>
        private string GetChatHtml()
        {
            try
            {
                var assembly = Assembly.GetExecutingAssembly();
                var htmlResourceName = "Rook.UI.Chat.Resources.chat.html";
                var cssResourceName = "Rook.UI.Chat.Resources.chat.css";

                using var htmlStream = assembly.GetManifestResourceStream(htmlResourceName);
                if (htmlStream != null)
                {
                    using var reader = new StreamReader(htmlStream);
                    var html = reader.ReadToEnd();

                    // Inline the CSS
                    using var cssStream = assembly.GetManifestResourceStream(cssResourceName);
                    if (cssStream != null)
                    {
                        using var cssReader = new StreamReader(cssStream);
                        var css = cssReader.ReadToEnd();
                        html = html.Replace("<link rel=\"stylesheet\" href=\"chat.css\">",
                            $"<style>{css}</style>");
                    }

                    return html;
                }
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"Failed to load chat resources: {ex.Message}");
            }

            return GetMinimalChatHtml();
        }

        /// <summary>
        /// Minimal self-contained HTML used when embedded resources are unavailable.
        /// </summary>
        private string GetMinimalChatHtml()
        {
            return @"<!DOCTYPE html>
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
        }

        // ─── JavaScript helpers ──────────────────────────────────────────

        /// <summary>
        /// Execute JavaScript in the WebView on the UI thread.
        /// </summary>
        protected void ExecuteScript(string script)
        {
            if (_webView != null && _webViewReady)
            {
                try
                {
                    Application.Instance.Invoke(() =>
                    {
                        _webView.ExecuteScript(script);
                    });
                }
                catch (Exception ex)
                {
                    RhinoApp.WriteLine($"Script error: {ex.Message}");
                }
            }
        }

        /// <summary>
        /// Escape a string so it can be safely embedded in a JavaScript string literal.
        /// </summary>
        protected static string EscapeForJavaScript(string input)
        {
            if (string.IsNullOrEmpty(input)) return "";
            return input
                .Replace("\\", "\\\\")
                .Replace("'", "\\'")
                .Replace("\"", "\\\"")
                .Replace("\n", "\\n")
                .Replace("\r", "\\r")
                .Replace("\t", "\\t");
        }

        // ─── Chat display methods (protected so subclasses can call) ─────

        /// <summary>
        /// Add a message bubble to the chat display.
        /// </summary>
        /// <param name="role">
        /// One of "user", "assistant", "error", "system".
        /// </param>
        /// <param name="content">Message text.</param>
        protected void AddMessageToChat(string role, string content)
        {
            if (_webView != null && _webViewReady)
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
            if (_webView != null && _webViewReady)
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
            if (_webView != null && _webViewReady)
            {
                ExecuteScript($"window.chatAPI.showTypingIndicator({(show ? "true" : "false")})");
            }
        }

        /// <summary>
        /// End the current streaming message so the next call to
        /// <see cref="UpdateStreamingChat"/> starts a new bubble.
        /// </summary>
        protected void FinalizeStreaming()
        {
            if (_webView != null && _webViewReady)
            {
                ExecuteScript("window.chatAPI.finalizeStreamingMessage()");
            }
        }

        /// <summary>
        /// Add a base64-encoded image to the chat display.
        /// </summary>
        protected void AddImageToChat(string base64Data)
        {
            if (_webView != null && _webViewReady)
            {
                ExecuteScript($"window.chatAPI.addImage('{base64Data}')");
            }
        }

        // ─── Status helpers (for subclasses) ─────────────────────────────

        /// <summary>
        /// Update the status bar text and color.
        /// </summary>
        protected void SetStatus(string text, Color color)
        {
            Application.Instance.Invoke(() =>
            {
                _statusLabel.Text = text;
                _statusLabel.TextColor = color;
            });
        }

        /// <summary>
        /// Set the processing state and update button / input enabled states.
        /// </summary>
        protected void SetProcessing(bool processing)
        {
            _isProcessing = processing;
            Application.Instance.Invoke(() =>
            {
                UpdateUIState();
            });
        }

        // ─── Event wiring ────────────────────────────────────────────────

        /// <summary>
        /// Wire up button clicks and keyboard shortcuts.
        /// </summary>
        private void AttachEvents()
        {
            _sendButton.Click += OnSendClicked;
            _stopButton.Click += OnStopClicked;
            _clearButton.Click += OnClearClicked;

            // Enter sends, Shift+Enter inserts newline
            _inputArea.KeyDown += (s, e) =>
            {
                if (e.Key == Keys.Enter && !e.Modifiers.HasFlag(Keys.Shift))
                {
                    e.Handled = true;
                    OnSendClicked(s, e);
                }
            };
        }

        // ─── Button handlers ─────────────────────────────────────────────

        /// <summary>
        /// Send button click (or Enter key) handler. Validates input, updates
        /// the UI, then delegates to <see cref="OnSendMessage"/>.
        /// </summary>
        private async void OnSendClicked(object? sender, EventArgs e)
        {
            var message = _inputArea.Text?.Trim();
            if (string.IsNullOrEmpty(message) || _isProcessing)
                return;

            _isProcessing = true;
            UpdateUIState();

            // Clear input
            _inputArea.Text = "";

            // Show user message and typing indicator
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

        /// <summary>
        /// Stop button click handler. Resets streaming state and delegates
        /// to <see cref="OnStopRequested"/>.
        /// </summary>
        private void OnStopClicked(object? sender, EventArgs e)
        {
            OnStopRequested();
            ShowTypingIndicator(false);
            FinalizeStreaming();
            _isProcessing = false;
            UpdateUIState();
            SetStatus("Stopped", Colors.Orange);
        }

        /// <summary>
        /// Clear button click handler. Resets the WebView / fallback chat
        /// and calls <see cref="OnClearRequested"/> for subclass cleanup.
        /// </summary>
        private void OnClearClicked(object? sender, EventArgs e)
        {
            if (_webView != null && _webViewReady)
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

        // ─── Internal UI state ───────────────────────────────────────────

        /// <summary>
        /// Toggle Send / Stop / Input enabled states based on
        /// <see cref="_isProcessing"/>.
        /// </summary>
        private void UpdateUIState()
        {
            _sendButton.Enabled = !_isProcessing;
            _stopButton.Enabled = _isProcessing;
            _inputArea.Enabled = !_isProcessing;
        }
    }
}
