using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Eto.Forms;
using Eto.Drawing;
using Rhino;
#if NET7_0_OR_GREATER
using Microsoft.Web.WebView2.Core;
#endif

namespace Rook.UI.Web
{
    /// <summary>
    /// Reusable hardened WebView host for Rook WebUI surfaces.
    ///
    /// Provides:
    /// - WebView2 virtual host at <c>https://app.rook.invalid</c>
    /// - In-memory resource serving via <c>WebResourceRequested</c>
    /// - Content-Security-Policy on HTML responses
    /// - Session nonce injection via <c>AddScriptToExecuteOnDocumentCreated</c>
    /// - Graceful fallback to minimal inline HTML
    ///
    /// Subclasses declare their resource root and entry page.
    /// The substrate owns the security boundary; modules own the content.
    /// </summary>
    public abstract class RookWebSurface : IDisposable
    {
        // ─── Virtual host ─────────────────────────────────────────────
        internal const string VirtualHostName = "app.rook.invalid";
        internal static readonly string VirtualHostOrigin = $"https://{VirtualHostName}";

        // ─── Default CSP (overridable via ContentSecurityPolicy) ──────
        internal const string DefaultContentSecurityPolicy =
            "default-src 'none'; " +
            "script-src 'self' 'unsafe-inline'; " +
            "style-src 'self' 'unsafe-inline'; " +
            "connect-src https://" + VirtualHostName + " http://127.0.0.1:*; " +
            "img-src 'self' data:; " +
            "font-src 'self'";

        // ─── WebView state ────────────────────────────────────────────
        private WebView? _webView;
        private bool _webViewReady;
        private bool _disposed;
        private Action? _disposeWebView;
        private readonly List<string> _pendingScripts = new();

        // ─── Bridge state ─────────────────────────────────────────────
        private readonly BridgeDispatcher _dispatcher;
        private bool _bridgeUnavailableSignaled;
#if NET7_0_OR_GREATER
        private CoreWebView2? _coreWebView2;
        private object? _nativeControlWithInitHandler;
        private EventInfo? _initEvent;
        private EventHandler<CoreWebView2InitializationCompletedEventArgs>? _initHandler;
#endif

        // ─── Constructor ──────────────────────────────────────────────
        protected RookWebSurface()
        {
            _dispatcher = new BridgeDispatcher(msg => Log($"Rook: {msg}"));
        }

        /// <summary>
        /// Substrate logging hook. Defaults to <c>RhinoApp.WriteLine</c>;
        /// test surfaces override to capture or suppress.
        /// </summary>
        protected virtual void Log(string message)
        {
            try { RhinoApp.WriteLine(message); }
            catch { /* defensive: keep substrate functional outside Rhino */ }
        }

        // ─── Abstract surface contract ────────────────────────────────

        /// <summary>
        /// Embedded resource namespace prefix for this surface.
        /// e.g. "Rook.UI.Chat.Resources" or "Rook.UI.Knowledge.Resources"
        /// </summary>
        protected abstract string ResourceRoot { get; }

        /// <summary>
        /// Entry page filename loaded at navigation.
        /// e.g. "chat.html" or "knowledge-graph.html"
        /// </summary>
        protected abstract string EntryPage { get; }

        /// <summary>
        /// Self-contained HTML used when virtual host setup fails.
        /// Must have zero external dependencies (no relative URLs).
        /// </summary>
        protected abstract string MinimalFallbackHtml { get; }

        /// <summary>
        /// Called when the WebView finishes loading the document.
        /// Override to perform post-load initialization.
        /// </summary>
        protected virtual void OnWebViewReady() { }

        /// <summary>
        /// Additional JavaScript to inject before navigation via
        /// <c>AddScriptToExecuteOnDocumentCreated</c>.  Override to
        /// inject surface-specific bootstrap (e.g. service host/port).
        /// The session nonce is always injected by the substrate.
        /// </summary>
        protected virtual string? GetBootstrapScript() => null;

        /// <summary>
        /// Surface-specific Content-Security-Policy. Default keeps
        /// backwards compatibility with Pattern B surfaces (Knowledge
        /// Graph, Chat) by allowing connect to <c>127.0.0.1:*</c>.
        /// Pattern A surfaces (Vision) override to lock down further
        /// (e.g. <c>connect-src 'none'</c>).
        /// </summary>
        protected virtual string ContentSecurityPolicy => DefaultContentSecurityPolicy;

        /// <summary>
        /// Fires once after WebView2 setup completes if the bridge could
        /// not be brought up AND at least one bridge handler was registered.
        /// Override to render an explicit degraded state. Always also logged
        /// via RhinoApp.WriteLine — failures never go silent.
        /// </summary>
        protected virtual void OnBridgeUnavailable() { }

        /// <summary>
        /// Optional hook for subclasses to resolve <em>virtual</em> resources
        /// whose bytes are NOT embedded in the assembly — for example the
        /// Vision tab's <c>/blob/{artifact_id}/{role}</c> URIs that stream
        /// artifact files from disk so the Gallery can render thumbnails
        /// without the bridge's 1 MB buffer constraint.
        ///
        /// Called by the substrate on every <c>WebResourceRequested</c>
        /// event <em>before</em> the standard embedded-resource lookup.
        /// Return <c>null</c> to fall through to the embedded path; return a
        /// <see cref="VirtualResource"/> to serve the bytes directly.
        ///
        /// Security note: the subclass is responsible for path validation
        /// (canonicalization, directory-escape rejection, authorization).
        /// The substrate does NOT re-validate — a returned
        /// <see cref="VirtualResource"/> is handed straight to WebView2.
        /// </summary>
        protected virtual VirtualResource? TryResolveVirtualResource(Uri uri) => null;

        /// <summary>
        /// Ordered list of scripts injected via
        /// <c>AddScriptToExecuteOnDocumentCreatedAsync</c>, in this exact order:
        ///   1. Session nonce (substrate-owned, may be empty)
        ///   2. Bridge shim (substrate-owned, always present)
        ///   3. Surface bootstrap (subclass-owned, from <see cref="GetBootstrapScript"/>)
        /// Empty entries are filtered out, but order is preserved.
        /// Override to insert additional substrate-level scripts.
        /// </summary>
        protected virtual IReadOnlyList<string> ComposeDocumentScripts()
        {
            var scripts = new List<string>();

            // 1. Nonce
            string? nonce = null;
            try { nonce = Chat.ChatServiceManager.Instance.SessionNonce; }
            catch { /* chat service not available — bridge surfaces don't need it */ }
            if (!string.IsNullOrEmpty(nonce))
            {
                var escapedNonce = EscapeForJavaScript(nonce);
                scripts.Add($"window.__rookSessionNonce = '{escapedNonce}';");
            }

            // 2. Bridge shim — always present
            scripts.Add(BuildBridgeShimScript());

            // 3. Surface bootstrap
            var bootstrap = GetBootstrapScript();
            if (!string.IsNullOrEmpty(bootstrap))
            {
                scripts.Add(bootstrap!);
            }

            return scripts;
        }

        // ─── Public API ───────────────────────────────────────────────

        /// <summary>
        /// Whether the WebView has finished loading its document.
        /// </summary>
        public bool IsWebViewReady => _webViewReady;

        /// <summary>
        /// True after the surface has released WebView resources.
        /// </summary>
        public bool IsDisposed => _disposed;

        /// <summary>
        /// Whether the JS↔C# bridge is wired and operational. Set after
        /// WebView2 initialization completes (success or failure).
        /// Returns false on net48 fallback, on WebView2 init failure, and
        /// before initialization runs.
        /// </summary>
        public bool IsBridgeAvailable { get; private set; }

        internal enum ProcessFailureRecoveryAction
        {
            LogOnly,
            Reload,
            RecreateRequired,
        }

        internal static ProcessFailureRecoveryAction ClassifyProcessFailure(string processFailedKind)
        {
            return processFailedKind switch
            {
                "RenderProcessExited" => ProcessFailureRecoveryAction.Reload,
                "BrowserProcessExited" => ProcessFailureRecoveryAction.RecreateRequired,
                _ => ProcessFailureRecoveryAction.LogOnly,
            };
        }

        internal void ReloadAfterHostActivation(string reason)
        {
            if (_disposed)
                return;

            _webViewReady = false;

            try
            {
                Application.Instance.AsyncInvoke(() =>
                {
                    if (_disposed || _webView == null)
                        return;

                    try
                    {
#if NET7_0_OR_GREATER
                        if (_coreWebView2 != null)
                        {
                            _coreWebView2.Reload();
                        }
                        else
#endif
                        {
                            _webView.Reload();
                        }

                        Log($"Rook: WebView reload requested after host activation for surface " +
                            $"'{ResourceRoot}' (reason={reason})");
                    }
                    catch (Exception reloadEx)
                    {
                        Log($"Rook: WebView host-activation reload failed: {reloadEx.Message}");
#if NET7_0_OR_GREATER
                        if (_coreWebView2 != null)
                        {
                            TryRenavigateAfterReloadFailure(_coreWebView2);
                        }
#endif
                    }
                });
            }
            catch (Exception ex)
            {
                Log($"Rook: WebView host-activation reload dispatch failed: {ex.Message}");
            }
        }

        /// <summary>
        /// Register a typed bridge handler keyed on a method name. Stored
        /// immediately; only fires once the bridge comes up. Call from the
        /// subclass constructor; do NOT call from <see cref="OnWebViewReady"/>
        /// (handler lifetime should not depend on navigation timing).
        /// Duplicate method name throws <see cref="ArgumentException"/>.
        /// </summary>
        protected void RegisterBridgeHandler(
            string method, Func<JsonNode?, Task<JsonNode?>> handler)
            => _dispatcher.Register(method, handler);

        /// <summary>
        /// Create the WebView control with virtual host setup.
        /// Call this from the subclass layout to get the renderable control.
        /// </summary>
        public Control CreateWebContent()
        {
            if (_disposed)
                throw new ObjectDisposedException(GetType().Name);

            try
            {
                _webView = new WebView();
                _webView.DocumentLoaded += OnDocumentLoaded;
                _disposeWebView = DisposeWebView;

#if NET7_0_OR_GREATER
                if (TrySetupVirtualHost())
                {
                    return _webView;
                }
#endif
                _webView.LoadHtml(MinimalFallbackHtml);
                return _webView;
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"Rook: WebView creation failed: {ex.Message}");
                return CreateFallbackControl();
            }
        }

        /// <summary>
        /// Execute JavaScript in the WebView on the UI thread.
        /// If the WebView is not yet ready, the script is buffered and
        /// replayed automatically once the document finishes loading.
        /// </summary>
        public void ExecuteScript(string script)
        {
            if (_disposed || _webView == null)
                return;

            if (!_webViewReady)
            {
                _pendingScripts.Add(script);
                return;
            }

            try
            {
                Application.Instance.Invoke(() =>
                {
                    _webView.ExecuteScript(script);
                });
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"Rook: script error: {ex.Message}");
            }
        }

        /// <summary>
        /// Escape a string for safe embedding in a JavaScript string literal.
        /// </summary>
        public static string EscapeForJavaScript(string input)
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

        // ─── Private implementation ───────────────────────────────────

        private void OnDocumentLoaded(object? sender, WebViewLoadedEventArgs e)
        {
            if (_disposed) return;

            // Flush buffered scripts BEFORE marking ready, so any
            // ExecuteScript call arriving during the flush still queues
            // behind the buffer rather than overtaking it.
            if (_pendingScripts.Count > 0 && _webView != null)
            {
                Application.Instance.Invoke(() =>
                {
                    foreach (var script in _pendingScripts)
                    {
                        try { _webView.ExecuteScript(script); }
                        catch (Exception ex) { RhinoApp.WriteLine($"Rook: buffered script error: {ex.Message}"); }
                    }
                    _pendingScripts.Clear();
                });
            }

            _webViewReady = true;

            // Bridge availability finalized BEFORE OnWebViewReady so
            // subclasses can rely on IsBridgeAvailable in their override.
            SignalBridgeUnavailableIfNeeded();

            OnWebViewReady();
        }

        /// <summary>
        /// Idempotent bridge-unavailable signal. Fires the
        /// <see cref="OnBridgeUnavailable"/> hook AT MOST ONCE per surface
        /// instance, so reload, re-navigation, or repeat DocumentLoaded
        /// events don't duplicate the degraded-state signal.
        /// Internal for unit-testability via InternalsVisibleTo.
        /// </summary>
        internal void SignalBridgeUnavailableIfNeeded()
        {
            if (_bridgeUnavailableSignaled) return;
            if (_dispatcher.HandlerCount == 0) return;
            if (IsBridgeAvailable) return;

            _bridgeUnavailableSignaled = true;

            // Log first, then call hook — log lands even if hook throws.
            Log($"Rook: bridge unavailable for surface '{ResourceRoot}'; " +
                $"{_dispatcher.HandlerCount} handler(s) inert");
            try { OnBridgeUnavailable(); }
            catch (Exception ex)
            {
                Log($"Rook: OnBridgeUnavailable threw: {ex.Message}");
            }
        }

        private static Control CreateFallbackControl()
        {
            return new TextArea
            {
                ReadOnly = true,
                Wrap = true,
                Font = new Font("Consolas", 10),
                Text = "WebView unavailable. Restart Rhino to retry."
            };
        }

        // ─── Bridge JS shim ───────────────────────────────────────────
        //
        // Always injected before any surface bootstrap. Surfaces that
        // don't register handlers simply have an unused window.rookBridge.
        //
        // Wire format mirrors BridgeDispatcher exactly.
        private static string BuildBridgeShimScript() => @"(function() {
  if (!window.chrome || !window.chrome.webview) return;
  var nextId = 1;
  var pending = Object.create(null);
  window.rookBridge = {
    invoke: function(method, args) {
      return new Promise(function(resolve, reject) {
        var requestId = 'r' + (nextId++);
        pending[requestId] = { resolve: resolve, reject: reject };
        window.chrome.webview.postMessage({
          type: 'invoke',
          method: method,
          requestId: requestId,
          args: args === undefined ? null : args
        });
      });
    }
  };
  window.chrome.webview.addEventListener('message', function(event) {
    var msg = event.data;
    if (!msg || msg.type !== 'response') return;
    var p = pending[msg.requestId];
    if (!p) return;
    delete pending[msg.requestId];
    if (msg.ok) p.resolve(msg.result);
    else p.reject(new Error(msg.error || 'bridge error'));
  });
})();";

#if NET7_0_OR_GREATER

        private bool TrySetupVirtualHost()
        {
            try
            {
                var nativeControl = _webView?.ControlObject;
                if (nativeControl == null)
                    return false;

                // Set dark background immediately to prevent white flash when
                // the panel loses focus or during navigation.
                var bgProp = nativeControl.GetType().GetProperty("DefaultBackgroundColor");
                if (bgProp != null)
                {
                    try { bgProp.SetValue(nativeControl, System.Drawing.Color.FromArgb(30, 30, 30)); }
                    catch { /* best-effort — property may not exist on all platforms */ }
                }

                var coreWv2Property = nativeControl.GetType().GetProperty("CoreWebView2");
                if (coreWv2Property == null)
                    return false;

                var coreWv2 = coreWv2Property.GetValue(nativeControl) as CoreWebView2;
                if (coreWv2 != null)
                {
                    ConfigureVirtualHost(coreWv2);
                    return true;
                }

                var initEvent = nativeControl.GetType().GetEvent("CoreWebView2InitializationCompleted");
                if (initEvent == null)
                    return false;

                EventHandler<CoreWebView2InitializationCompletedEventArgs> handler = null!;
                handler = (sender, args) =>
                {
                    initEvent.RemoveEventHandler(nativeControl, handler);
                    if (ReferenceEquals(_initHandler, handler))
                    {
                        _initEvent = null;
                        _initHandler = null;
                        _nativeControlWithInitHandler = null;
                    }
                    if (_disposed) return;
                    if (args.IsSuccess)
                    {
                        coreWv2 = coreWv2Property.GetValue(nativeControl) as CoreWebView2;
                        if (coreWv2 != null)
                            ConfigureVirtualHost(coreWv2);
                    }
                    else
                    {
                        RhinoApp.WriteLine("Rook: WebView2 init failed, falling back to minimal HTML");
                        Application.Instance.Invoke(() => _webView?.LoadHtml(MinimalFallbackHtml));
                    }
                };
                _nativeControlWithInitHandler = nativeControl;
                _initEvent = initEvent;
                _initHandler = handler;
                initEvent.AddEventHandler(nativeControl, handler);

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

        private async void ConfigureVirtualHost(CoreWebView2 coreWebView2)
        {
            try
            {
                if (_disposed) return;

                coreWebView2.AddWebResourceRequestedFilter(
                    $"{VirtualHostOrigin}/*",
                    CoreWebView2WebResourceContext.All);
                coreWebView2.WebResourceRequested += OnWebResourceRequested;

                // Wire bridge BEFORE script injection so the shim's receiver
                // is connected before any page script can post.
                coreWebView2.WebMessageReceived += OnWebMessageReceived;
                coreWebView2.ProcessFailed += OnWebViewProcessFailed;
                _coreWebView2 = coreWebView2;

                // Inject document-creation scripts in the locked order:
                // nonce, bridge shim, surface bootstrap.
                foreach (var script in ComposeDocumentScripts())
                {
                    if (string.IsNullOrEmpty(script)) continue;
                    await coreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(script);
                    if (_disposed) return;
                }

                if (_disposed) return;

                // Bridge is operational. Settle the flag BEFORE Navigate so
                // any post-Navigate code paths see the correct state.
                IsBridgeAvailable = true;

                coreWebView2.Navigate($"{VirtualHostOrigin}/{EntryPage}");
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"Rook: virtual host navigation failed: {ex.Message}");
                IsBridgeAvailable = false;
                Application.Instance.Invoke(() => _webView?.LoadHtml(MinimalFallbackHtml));
            }
        }

        private void OnWebViewProcessFailed(object? sender, CoreWebView2ProcessFailedEventArgs e)
        {
            if (_disposed) return;

            var kind = e.ProcessFailedKind.ToString();
            var action = ClassifyProcessFailure(kind);
            Log("Rook: WebView2 process failure on surface " +
                $"'{ResourceRoot}': kind={kind}, reason={e.Reason}, " +
                $"exitCode={e.ExitCode}, description='{e.ProcessDescription}', " +
                $"recovery={action}");

            switch (action)
            {
                case ProcessFailureRecoveryAction.Reload:
                    ReloadAfterRendererExit(sender as CoreWebView2);
                    break;
                case ProcessFailureRecoveryAction.RecreateRequired:
                    _webViewReady = false;
                    IsBridgeAvailable = false;
                    Log("Rook: WebView2 browser process exited; close and reopen the " +
                        "Rook panel if the surface does not recover.");
                    break;
            }
        }

        private void ReloadAfterRendererExit(CoreWebView2? eventCore)
        {
            _webViewReady = false;

            try
            {
                Application.Instance.AsyncInvoke(() =>
                {
                    if (_disposed) return;

                    var core = eventCore ?? _coreWebView2;
                    if (core == null)
                    {
                        Log("Rook: WebView2 renderer reload skipped; CoreWebView2 is unavailable");
                        return;
                    }

                    try
                    {
                        core.Reload();
                        Log($"Rook: WebView2 renderer reload requested for surface '{ResourceRoot}'");
                    }
                    catch (Exception reloadEx)
                    {
                        Log($"Rook: WebView2 renderer reload failed: {reloadEx.Message}");
                        TryRenavigateAfterReloadFailure(core);
                    }
                });
            }
            catch (Exception ex)
            {
                Log($"Rook: WebView2 renderer reload dispatch failed: {ex.Message}");
            }
        }

        private void TryRenavigateAfterReloadFailure(CoreWebView2 core)
        {
            try
            {
                core.Navigate($"{VirtualHostOrigin}/{EntryPage}");
                Log($"Rook: WebView2 renderer re-navigation requested for surface '{ResourceRoot}'");
            }
            catch (Exception navEx)
            {
                Log("Rook: WebView2 renderer recovery failed; close and reopen the " +
                    $"Rook panel to recover. Details: {navEx.Message}");
            }
        }

        private async void OnWebMessageReceived(
            object? sender, CoreWebView2WebMessageReceivedEventArgs e)
        {
            if (_disposed) return;

            string? incomingJson;
            try { incomingJson = e.WebMessageAsJson; }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"Rook: bridge message read failed: {ex.Message}");
                return;
            }

            var responseJson = await _dispatcher.DispatchAsync(incomingJson);
            if (responseJson is null || _disposed) return;

            Application.Instance.Invoke(() =>
            {
                try { _coreWebView2?.PostWebMessageAsJson(responseJson); }
                catch (Exception ex)
                {
                    RhinoApp.WriteLine($"Rook: bridge response post failed: {ex.Message}");
                }
            });
        }

        private void OnWebResourceRequested(object? sender, CoreWebView2WebResourceRequestedEventArgs e)
        {
            if (_disposed) return;

            var uri = new Uri(e.Request.Uri);
            if (!uri.Host.Equals(VirtualHostName, StringComparison.OrdinalIgnoreCase))
                return;

            var coreWv2 = sender as CoreWebView2;

            // Give the subclass first crack at virtual resources
            // (on-disk blobs, bridge-synthesized content, etc.) BEFORE
            // falling back to embedded-resource lookup. Subclass is
            // responsible for path validation.
            VirtualResource? virtResource = null;
            try
            {
                virtResource = TryResolveVirtualResource(uri);
            }
            catch (Exception ex)
            {
                Log($"Rook: TryResolveVirtualResource threw for '{uri}': {ex.Message}");
                // Fall through to embedded-resource path; a surface-level
                // exception must not deny the caller a response.
            }

            if (virtResource != null)
            {
                if (coreWv2 != null)
                {
                    var virtHeaders = $"Content-Type: {virtResource.ContentType}";
                    if (!string.IsNullOrEmpty(virtResource.ExtraHeaders))
                    {
                        virtHeaders = virtHeaders + "\r\n" + virtResource.ExtraHeaders;
                    }
                    var reasonPhrase = virtResource.StatusCode == 200
                        ? "OK"
                        : (virtResource.StatusCode == 404 ? "Not Found" : "Error");
                    e.Response = coreWv2.Environment.CreateWebResourceResponse(
                        virtResource.Content,
                        virtResource.StatusCode,
                        reasonPhrase,
                        virtHeaders);
                }
                return;
            }

            var path = uri.AbsolutePath.TrimStart('/').Replace('/', '.');
            var resourceName = $"{ResourceRoot}.{path}";

            var assembly = Assembly.GetExecutingAssembly();
            var stream = assembly.GetManifestResourceStream(resourceName);
            if (stream == null)
            {
                // Return an explicit 404 so missing resources surface as clear
                // errors in the browser console rather than silent network failures.
                if (coreWv2 != null)
                {
                    e.Response = coreWv2.Environment.CreateWebResourceResponse(
                        null, 404, "Not Found",
                        $"Content-Type: text/plain\r\nX-Rook-Missing-Resource: {resourceName}");
                }
                return;
            }

            var headers = GetResponseHeaders(uri.AbsolutePath);
            if (coreWv2 != null)
            {
                e.Response = coreWv2.Environment.CreateWebResourceResponse(
                    stream, 200, "OK", headers);
            }
        }

        private string GetResponseHeaders(string path)
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
            if (path.EndsWith(".svg", StringComparison.OrdinalIgnoreCase)) return "image/svg+xml";
            return "application/octet-stream";
        }

#endif

        public void Dispose()
        {
            Dispose(true);
            GC.SuppressFinalize(this);
        }

        protected virtual void Dispose(bool disposing)
        {
            if (_disposed) return;
            _disposed = true;

            if (!disposing) return;

#if NET7_0_OR_GREATER
            if (_initEvent != null && _nativeControlWithInitHandler != null && _initHandler != null)
            {
                try { _initEvent.RemoveEventHandler(_nativeControlWithInitHandler, _initHandler); }
                catch { }
            }
            _initEvent = null;
            _initHandler = null;
            _nativeControlWithInitHandler = null;

            if (_coreWebView2 != null)
            {
                try { _coreWebView2.WebResourceRequested -= OnWebResourceRequested; }
                catch { }
                try { _coreWebView2.WebMessageReceived -= OnWebMessageReceived; }
                catch { }
                try { _coreWebView2.ProcessFailed -= OnWebViewProcessFailed; }
                catch { }
                _coreWebView2 = null;
            }
#endif

            var disposeWebView = _disposeWebView;
            _disposeWebView = null;
            disposeWebView?.Invoke();

            _pendingScripts.Clear();
            _webViewReady = false;
            IsBridgeAvailable = false;
        }

        private void DisposeWebView()
        {
            try { _webView!.DocumentLoaded -= OnDocumentLoaded; }
            catch { }
            try { _webView!.Dispose(); }
            catch { }
            _webView = null;
        }
    }
}
