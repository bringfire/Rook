using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
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
    public abstract class RookWebSurface
    {
        // ─── Virtual host ─────────────────────────────────────────────
        internal const string VirtualHostName = "app.rook.invalid";
        internal static readonly string VirtualHostOrigin = $"https://{VirtualHostName}";

        // ─── WebView state ────────────────────────────────────────────
        private WebView? _webView;
        private bool _webViewReady;
        private readonly List<string> _pendingScripts = new();

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

        // ─── Public API ───────────────────────────────────────────────

        /// <summary>
        /// Whether the WebView has finished loading its document.
        /// </summary>
        public bool IsWebViewReady => _webViewReady;

        /// <summary>
        /// Create the WebView control with virtual host setup.
        /// Call this from the subclass layout to get the renderable control.
        /// </summary>
        public Control CreateWebContent()
        {
            try
            {
                _webView = new WebView();
                _webView.DocumentLoaded += OnDocumentLoaded;

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
            if (_webView == null)
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
            OnWebViewReady();
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
                coreWebView2.AddWebResourceRequestedFilter(
                    $"{VirtualHostOrigin}/*",
                    CoreWebView2WebResourceContext.All);
                coreWebView2.WebResourceRequested += OnWebResourceRequested;

                // Inject session nonce BEFORE navigation.
                var nonce = Chat.ChatServiceManager.Instance.SessionNonce;
                if (!string.IsNullOrEmpty(nonce))
                {
                    var escapedNonce = EscapeForJavaScript(nonce);
                    await coreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(
                        $"window.__rookSessionNonce = '{escapedNonce}';");
                }

                // Inject surface-specific bootstrap script.
                var bootstrap = GetBootstrapScript();
                if (!string.IsNullOrEmpty(bootstrap))
                {
                    await coreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(bootstrap);
                }

                coreWebView2.Navigate($"{VirtualHostOrigin}/{EntryPage}");
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"Rook: virtual host navigation failed: {ex.Message}");
                Application.Instance.Invoke(() => _webView?.LoadHtml(MinimalFallbackHtml));
            }
        }

        private void OnWebResourceRequested(object? sender, CoreWebView2WebResourceRequestedEventArgs e)
        {
            var uri = new Uri(e.Request.Uri);
            if (!uri.Host.Equals(VirtualHostName, StringComparison.OrdinalIgnoreCase))
                return;

            var path = uri.AbsolutePath.TrimStart('/').Replace('/', '.');
            var resourceName = $"{ResourceRoot}.{path}";

            var assembly = Assembly.GetExecutingAssembly();
            var stream = assembly.GetManifestResourceStream(resourceName);
            if (stream == null)
            {
                // Return an explicit 404 so missing resources surface as clear
                // errors in the browser console rather than silent network failures.
                var coreWv2For404 = sender as CoreWebView2;
                if (coreWv2For404 != null)
                {
                    e.Response = coreWv2For404.Environment.CreateWebResourceResponse(
                        null, 404, "Not Found",
                        $"Content-Type: text/plain\r\nX-Rook-Missing-Resource: {resourceName}");
                }
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

        // ─── CSP + headers ────────────────────────────────────────────

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

#endif
    }
}
