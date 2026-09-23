using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
#if ROOK_WEBVIEW2
using System.Runtime.InteropServices;
#endif
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Eto.Forms;
using Eto.Drawing;
using Rhino;
#if ROOK_WEBVIEW2
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
    public abstract class RookWebSurface : IDisposable, IScriptBackpressure
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

        // ─── Script admission (S4) ────────────────────────────────────
        // UI thread only: readiness, both queues, the slot count and the display
        // generation are touched only from UI-marshaled callbacks, so no locking.
        // PostScript marshals first, whatever thread calls it.
        public const int MaxInFlightScripts = 16;
        public const int ScriptResumeThreshold = 8;
        private readonly List<ScriptRequest> _pendingScripts = new();
        private readonly Queue<ScriptRequest> _scriptQueue = new();
        private int _inFlightScripts;
        private int _displayGeneration;
        private Action<Action> _uiScheduler = action => Application.Instance.AsyncInvoke(action);

        // ─── Bridge state ─────────────────────────────────────────────
        private readonly BridgeDispatcher _dispatcher;
        private bool _bridgeUnavailableSignaled;
#if ROOK_WEBVIEW2
        private CoreWebView2? _coreWebView2;
        private object? _nativeControlWithInitHandler;
        private EventInfo? _initEvent;
        private EventHandler<CoreWebView2InitializationCompletedEventArgs>? _initHandler;
        private bool _activationIdleConfirmPending;
        private const int MaxHostPresentationDiagnosticEntries = 64;
        private readonly Queue<WebViewHostPresentationDiagnosticEntry> _hostPresentationDiagnostics = new();
        private int _hostPresentationDiagnosticSequence;
#endif

        // ─── Presentation reconciler (spec 2026-06-10) ────────────────
        private static int s_surfaceIdCounter;
        private readonly int _surfaceIdOrdinal =
            System.Threading.Interlocked.Increment(ref s_surfaceIdCounter);
        private readonly WebViewPresentationReconciler _reconciler;

        /// <summary>
        /// Process-unique surface identity for registry dumps:
        /// ResourceRoot plus a per-process creation ordinal.
        /// </summary>
        internal string SurfaceId => ResourceRoot + ":" + _surfaceIdOrdinal;

        // ─── Constructor ──────────────────────────────────────────────
        protected RookWebSurface()
        {
            _dispatcher = new BridgeDispatcher(msg => Log($"Rook: {msg}"));
            _reconciler = new WebViewPresentationReconciler(
                new SurfacePresentationHost(this));
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
        ///   3. Focus diagnostics (substrate-owned)
        ///   4. Surface bootstrap (subclass-owned, from <see cref="GetBootstrapScript"/>)
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

            // 3. Focus diagnostics
#if ROOK_WEBVIEW2
            if (IsWebViewFocusDiagnosticsEnabled())
                scripts.Add(BuildFocusProbeScript());
#endif

            // 4. Surface bootstrap
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
        /// Returns false on WebView2 init failure, and
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

        internal string DumpHostPresentationDiagnostics()
        {
#if ROOK_WEBVIEW2
            return JsonSerializer.Serialize(
                GetHostPresentationDiagnosticEntries(),
                new JsonSerializerOptions { WriteIndented = true });
#else
            return "[]";
#endif
        }

        internal WebViewHostPresentationDiagnosticEntry[] GetHostPresentationDiagnosticEntries()
        {
#if ROOK_WEBVIEW2
            return _hostPresentationDiagnostics.ToArray();
#else
            return Array.Empty<WebViewHostPresentationDiagnosticEntry>();
#endif
        }

        /// <summary>
        /// Operator-forced repair: accepted-and-scheduled. Returns
        /// immediately; the async gapped toggle runs fire-and-forget on
        /// the UI thread and outcomes land in the diagnostics ring (read
        /// via a follow-up dump). No synchronous Invoke / .Result /
        /// .Wait() anywhere on this path. Virtual so test surfaces can
        /// record scheduling without an Eto application loop.
        /// </summary>
        internal virtual void SchedulePresentationRepair(string reason)
        {
            if (_disposed)
                return;

            try
            {
                Application.Instance.AsyncInvoke(async () =>
                {
                    try
                    {
                        await _reconciler.ForceRepairAsync(reason);
                    }
                    catch (Exception ex)
                    {
                        Log($"Rook: presentation forced repair failed for surface " +
                            $"'{SurfaceId}' (reason={reason}): {ex.Message}");
                    }
                });
            }
            catch (Exception ex)
            {
                Log($"Rook: presentation repair scheduling failed for surface " +
                    $"'{SurfaceId}' (reason={reason}): {ex.Message}");
            }
        }

        /// <summary>
        /// Fire-and-forget level-triggered reconcile request. All external
        /// triggers (focus, shown, resize, document load, panel lifecycle)
        /// funnel through here; the reconciler serializes and coalesces.
        /// No synchronous Invoke / .Result / .Wait() on this path.
        /// </summary>
        internal void RequestPresentationReconcile(string reason)
        {
            if (_disposed)
                return;

            try
            {
                Application.Instance.AsyncInvoke(async () =>
                {
                    try
                    {
                        await _reconciler.ReconcileAsync(reason);
                    }
                    catch (Exception ex)
                    {
                        Log($"Rook: presentation reconcile failed for surface " +
                            $"'{SurfaceId}' (reason={reason}): {ex.Message}");
                    }
                });
            }
            catch (Exception ex)
            {
                Log($"Rook: presentation reconcile scheduling failed for surface " +
                    $"'{SurfaceId}' (reason={reason}): {ex.Message}");
            }
        }

        /// <summary>
        /// Durable desired-visibility intent (panel lifecycle authority),
        /// followed by an immediate reconcile toward that state.
        /// </summary>
        internal void SetPresentationDesiredVisible(bool visible, string reason)
        {
            _reconciler.SetDesiredVisible(visible, reason);
            RequestPresentationReconcile(reason);
        }

        /// <summary>
        /// Thin annotation hook for panel lifecycle decisions that take no
        /// action (e.g. lifecycle-hide) but must remain visible in the
        /// diagnostics ring dump.
        /// </summary>
        internal void RecordPresentationAnnotation(string evt, string detail)
            => RecordReconcilerDiagnostic(evt, detail);

        /// <summary>
        /// Reconciler diagnostics hook: minimal ring entries (event in
        /// <c>Reason</c>, detail/probe payload in <c>ActionResult</c>)
        /// reusing the existing bounded host-presentation ring so the
        /// registry dump is the single diagnostics read surface.
        /// </summary>
        private void RecordReconcilerDiagnostic(string evt, string detail)
        {
#if ROOK_WEBVIEW2
            _hostPresentationDiagnostics.Enqueue(new WebViewHostPresentationDiagnosticEntry
            {
                Sequence = ++_hostPresentationDiagnosticSequence,
                TimestampUtc = DateTimeOffset.UtcNow,
                Surface = ResourceRoot,
                Reason = evt,
                ActionResult = detail
            });

            while (_hostPresentationDiagnostics.Count > MaxHostPresentationDiagnosticEntries)
                _hostPresentationDiagnostics.Dequeue();
#else
            _ = evt;
            _ = detail;
#endif
        }

        /// <summary>
        /// Minimal <see cref="IPresentationHost"/> over this surface's
        /// WebView2 state. The probe is real (<c>ExecuteScriptAsync</c>
        /// raced against <see cref="ReconcilerTiming.ProbeTimeoutMs"/>);
        /// the controller members reuse the existing reflection helpers.
        /// Full trigger wiring is the reconciler-cutover task.
        /// </summary>
        private sealed class SurfacePresentationHost : IPresentationHost
        {
            // Exact spec probe payload (visibilityState, hidden,
            // readyState, hasRoot, viewport, appRect).
            private const string ProbeScript =
                "JSON.stringify({" +
                "visibilityState:document.visibilityState," +
                "hidden:document.hidden," +
                "readyState:document.readyState," +
                "hasRoot:!!document.body," +
                "viewport:[window.innerWidth,window.innerHeight]," +
                "appRect:document.body?(document.body.getBoundingClientRect().toJSON" +
                "?document.body.getBoundingClientRect().toJSON():null):null" +
                "})";

            private readonly RookWebSurface _surface;

            public SurfacePresentationHost(RookWebSurface surface)
            {
                _surface = surface;
            }

            public Task<PresentationProbeReport> ProbeAsync()
            {
#if ROOK_WEBVIEW2
                return ProbeCoreAsync();
#else
                return Task.FromResult(
                    PresentationProbeReport.Unresponsive("webview2-unavailable"));
#endif
            }

#if ROOK_WEBVIEW2
            private async Task<PresentationProbeReport> ProbeCoreAsync()
            {
                var core = _surface._coreWebView2;
                if (core == null || _surface._disposed)
                    return PresentationProbeReport.Unresponsive("webview2-unavailable");

                try
                {
                    var probe = core.ExecuteScriptAsync(ProbeScript);
                    var completed = await Task.WhenAny(
                        probe,
                        Task.Delay(ReconcilerTiming.ProbeTimeoutMs));
                    if (!ReferenceEquals(completed, probe))
                        return PresentationProbeReport.Unresponsive("probe-timeout");
                    return PresentationProbeReport.Parse(await probe);
                }
                catch (Exception ex)
                {
                    return PresentationProbeReport.Unresponsive(
                        "probe-fault:" + ex.Message);
                }
            }
#endif

            public bool TrySetControllerVisible(bool visible)
            {
#if ROOK_WEBVIEW2
                var controller = _surface.TryGetCoreWebView2Controller();
                if (controller == null)
                    return false;
                return _surface.SetControllerVisible(
                    controller, visible, "presentation-reconciler");
#else
                _ = visible;
                return false;
#endif
            }

            public bool TrySetControllerBounds()
            {
#if ROOK_WEBVIEW2
                var controller = _surface.TryGetCoreWebView2Controller();
                if (controller == null)
                    return false;
                var bounds = _surface.TryBuildControllerTargetBounds();
                if (bounds == null)
                    return false;
                return _surface.SetControllerBounds(
                    controller, bounds, "presentation-reconciler");
#else
                return false;
#endif
            }

            public void NotifyParentWindowPositionChanged()
            {
#if ROOK_WEBVIEW2
                var controller = _surface.TryGetCoreWebView2Controller();
                if (controller == null)
                    return;
                _surface.NotifyParentWindowPositionChanged(
                    controller, "presentation-reconciler");
#endif
            }

            public void ReloadWebView()
            {
#if ROOK_WEBVIEW2
                try
                {
                    _surface._coreWebView2?.Reload();
                }
                catch (Exception ex)
                {
                    _surface.Log($"Rook: WebView2 reload failed for surface " +
                        $"'{_surface.SurfaceId}': {ex.Message}");
                }
#endif
            }

            public Task DelayAsync(int milliseconds) => Task.Delay(milliseconds);

            public void Record(string evt, string detail)
                => _surface.RecordReconcilerDiagnostic(evt, detail);
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
                WebSurfacePresentationRegistry.Register(this);

#if ROOK_WEBVIEW2
                // Rhino panels can be shown, hidden, floated, docked, and
                // reparented without recreating the panel instance. Keep
                // WebView2's controller visibility synchronized with that
                // host lifecycle so the live document keeps presenting.
                _webView.GotFocus += OnWebViewGotFocus;
                _webView.Shown += OnWebViewShown;
                _webView.SizeChanged += OnWebViewSizeChanged;
                Application.Instance.IsActiveChanged += OnApplicationIsActiveChanged;
                // Seed initial app-active state: the reconciler defaults to
                // inactive, and without this the first reconciles
                // (WebView2Configured, DocumentLoaded, PanelShown) would all
                // skip as inactive until Rhino emits an activation edge.
                try { _reconciler.SetAppActive(Application.Instance?.IsActive == true); }
                catch { /* defensive: keep substrate functional outside Eto */ }
                TraceWebViewFocus("create-web-content");

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

#if ROOK_WEBVIEW2
        // Controller property readers below are reflection helpers shared by
        // the presentation reconciler host and diagnostics; some are
        // currently diagnostic-only.
        private static bool TryGetControllerVisible(object controller, out bool visible)
        {
            visible = false;
            var prop = GetInstanceProperty(controller.GetType(), "IsVisible");
            if (prop == null || !prop.CanRead)
                return false;

            try
            {
                visible = prop.GetValue(controller) is bool b && b;
                return true;
            }
            catch
            {
                return false;
            }
        }

        private static bool TryGetControllerParentWindow(object controller, out IntPtr hwnd)
        {
            hwnd = IntPtr.Zero;
            var prop = GetInstanceProperty(controller.GetType(), "ParentWindow");
            if (prop == null || !prop.CanRead)
                return false;

            try
            {
                var value = prop.GetValue(controller);
                if (value is IntPtr ptr)
                {
                    hwnd = ptr;
                    return true;
                }

                return false;
            }
            catch
            {
                return false;
            }
        }

        private object? TryBuildControllerTargetBounds()
        {
            var webView = _webView;
            if (webView == null)
                return null;

            var size = webView.Size;
            if (size.Width <= 0 || size.Height <= 0)
                return null;

            return new System.Drawing.Rectangle(0, 0, size.Width, size.Height);
        }

        private static bool TryControllerBoundsMatch(object controller, object targetBounds)
        {
            var prop = GetInstanceProperty(controller.GetType(), "Bounds");
            if (prop == null || !prop.CanRead)
                return true;

            try
            {
                return Equals(prop.GetValue(controller), targetBounds);
            }
            catch
            {
                return true;
            }
        }

        private bool SetControllerBounds(object controller, object bounds, string reason)
        {
            var prop = GetInstanceProperty(controller.GetType(), "Bounds");
            if (prop == null || !prop.CanWrite)
                return false;

            try
            {
                prop.SetValue(controller, bounds);
                return true;
            }
            catch (Exception ex)
            {
                Log($"Rook: WebView2 bounds set failed for surface '{ResourceRoot}' " +
                    $"(reason={reason}): {ex.Message}");
                return false;
            }
        }

        private bool NotifyParentWindowPositionChangedWithResult(
            object controller,
            string reason)
        {
            var notifyMethod = controller.GetType().GetMethod(
                "NotifyParentWindowPositionChanged",
                Type.EmptyTypes);
            if (notifyMethod == null)
                return false;

            try
            {
                notifyMethod.Invoke(controller, null);
                return true;
            }
            catch (Exception ex)
            {
                Log($"Rook: WebView2 parent-position notification failed for surface " +
                    $"'{ResourceRoot}' (reason={reason}): {ex.Message}");
                return false;
            }
        }

        [DllImport("user32.dll")]
        private static extern IntPtr GetParent(IntPtr hWnd);

        [DllImport("user32.dll")]
        private static extern bool IsWindowVisible(IntPtr hWnd);

        [DllImport("user32.dll")]
        private static extern bool GetClientRect(IntPtr hWnd, out NativeRect lpRect);

        [DllImport("user32.dll")]
        private static extern bool GetWindowRect(IntPtr hWnd, out NativeRect lpRect);

        private struct NativeRect
        {
            public int Left;
            public int Top;
            public int Right;
            public int Bottom;
        }

        // HWND probe helpers: diagnostic-only since the level-triggered
        // reconciler cutover (spec 2026-06-10) — retained to feed ring
        // annotations / future probes, not consulted for decisions.
        private bool IsHostHwndChainVisible()
        {
            var hwnd = TryGetHostHwnd();
            if (hwnd == IntPtr.Zero)
                return false;

            var guard = 0;
            while (hwnd != IntPtr.Zero && guard++ < 32)
            {
                if (!IsWindowVisible(hwnd))
                    return false;
                hwnd = GetParent(hwnd);
            }

            return true;
        }

        private bool IsHostHwndClientRectNonZero()
        {
            var hwnd = TryGetHostHwnd();
            if (hwnd == IntPtr.Zero)
                return false;

            var guard = 0;
            while (hwnd != IntPtr.Zero && guard++ < 32)
            {
                if (!HasNonZeroRect(hwnd))
                    return false;
                hwnd = GetParent(hwnd);
            }

            return true;
        }

        private IntPtr TryGetHostHwnd()
        {
            var nativeControl = _webView?.ControlObject;
            if (nativeControl == null)
                return IntPtr.Zero;

            if (TryReadHandle(nativeControl, out var hwnd))
                return hwnd;

            var webView2 = GetWebView2NativeControl(nativeControl);
            if (webView2 != null && !ReferenceEquals(webView2, nativeControl) &&
                TryReadHandle(webView2, out hwnd))
            {
                return hwnd;
            }

            return IntPtr.Zero;
        }

        private static bool TryReadHandle(object target, out IntPtr hwnd)
        {
            hwnd = IntPtr.Zero;
            var handleProp = GetInstanceProperty(target.GetType(), "Handle");
            if (handleProp == null || !handleProp.CanRead)
                return false;

            try
            {
                var value = handleProp.GetValue(target);
                if (value is IntPtr ptr)
                {
                    hwnd = ptr;
                    return hwnd != IntPtr.Zero;
                }

                return false;
            }
            catch
            {
                return false;
            }
        }

        private static bool HasNonZeroRect(IntPtr hwnd)
        {
            if (GetClientRect(hwnd, out var client) &&
                client.Right > client.Left &&
                client.Bottom > client.Top)
            {
                return true;
            }

            if (GetWindowRect(hwnd, out var window) &&
                window.Right > window.Left &&
                window.Bottom > window.Top)
            {
                return true;
            }

            return false;
        }

        private bool SetControllerVisible(object controller, bool visible, string reason)
        {
            var isVisibleProp = GetInstanceProperty(controller.GetType(), "IsVisible");
            if (isVisibleProp == null || !isVisibleProp.CanWrite)
            {
                TraceWebViewFocus("host-visibility-reconcile-skip",
                    $"controller-isvisible-unavailable;{visible};{reason}");
                return false;
            }

            try
            {
                isVisibleProp.SetValue(controller, visible);
                TraceWebViewFocus("host-controller-visible-set", $"{visible};{reason}");
                return true;
            }
            catch (Exception ex)
            {
                TraceWebViewFocus("host-visibility-reconcile-failed",
                    $"set-visible;{visible};{reason};{ex.Message}");
                Log($"Rook: WebView2 controller visibility set failed for surface " +
                    $"'{ResourceRoot}' (reason={reason}): {ex.Message}");
                return false;
            }
        }

        private void NotifyParentWindowPositionChanged(object controller, string reason)
        {
            var notifyMethod = controller.GetType().GetMethod(
                "NotifyParentWindowPositionChanged",
                Type.EmptyTypes);

            if (notifyMethod == null)
            {
                TraceWebViewFocus("host-visibility-reconcile-skip",
                    $"notify-parent-unavailable;{reason}");
                return;
            }

            try
            {
                notifyMethod.Invoke(controller, null);
                TraceWebViewFocus("host-controller-position-notified", reason);
            }
            catch (Exception ex)
            {
                TraceWebViewFocus("host-visibility-reconcile-failed",
                    $"notify-parent;{reason};{ex.Message}");
                Log($"Rook: WebView2 parent-position notification failed for surface " +
                    $"'{ResourceRoot}' (reason={reason}): {ex.Message}");
            }
        }

        private void OnWebViewGotFocus(object? sender, EventArgs e)
        {
            TraceWebViewFocus("webview-got-focus");
            RequestPresentationReconcile("GotFocus");
        }

        private void OnWebViewShown(object? sender, EventArgs e)
        {
            TraceWebViewFocus("webview-shown");
            RequestPresentationReconcile("WebViewShown");
        }

        private void OnWebViewSizeChanged(object? sender, EventArgs e)
        {
            TraceWebViewFocus("webview-size-changed");
            RequestPresentationReconcile("SizeChanged");
        }

        private void OnApplicationIsActiveChanged(object? sender, EventArgs e)
        {
            var active = Application.Instance.IsActive;
            TraceWebViewFocus("app-active-changed", active ? "active" : "inactive");

            // Suspect-cycle mark (spec addendum 2026-06-10 evening): a
            // repair run during activation churn can renderer-succeed and
            // compositor-fail, so deactivation marks the surface suspect;
            // the activation idle confirm runs one forced gapped toggle.
            // No WebView mutation here (no-present-side-effects-while-
            // inactive invariant) — just the flag + ring entry.
            if (!active)
                _reconciler.MarkSuspect("AppDeactivated");

            try
            {
                Application.Instance.AsyncInvoke(async () =>
                {
                    try
                    {
                        await _reconciler.SetAppActiveAsync(
                            Application.Instance.IsActive);
                    }
                    catch (Exception ex)
                    {
                        Log($"Rook: presentation app-active update failed for " +
                            $"surface '{SurfaceId}': {ex.Message}");
                    }
                });
            }
            catch (Exception ex)
            {
                Log($"Rook: presentation app-active dispatch failed for surface " +
                    $"'{SurfaceId}': {ex.Message}");
            }

            if (active)
                ScheduleActivationIdleConfirm();
        }

        /// <summary>
        /// One-shot RhinoApp.Idle confirmation after app activation: Rhino's
        /// window/dock state settles after the activation event, so a single
        /// idle-time reconcile catches presentation facts that were still
        /// mid-transition at activation. Guarded against double-subscribe.
        /// </summary>
        private void ScheduleActivationIdleConfirm()
        {
            if (_disposed || _activationIdleConfirmPending)
                return;

            _activationIdleConfirmPending = true;
            RhinoApp.Idle += OnActivationIdleConfirm;
        }

        private void OnActivationIdleConfirm(object? sender, EventArgs e)
        {
            RhinoApp.Idle -= OnActivationIdleConfirm;
            _activationIdleConfirmPending = false;

            if (_disposed)
                return;

            // Routes through the reconciler's activation-idle entry point
            // so a pending suspect-cycle runs its forced toggle; otherwise
            // it falls through to a normal probe-gated reconcile.
            try
            {
                Application.Instance.AsyncInvoke(async () =>
                {
                    try
                    {
                        await _reconciler.RunActivationIdleConfirmAsync();
                    }
                    catch (Exception ex)
                    {
                        Log($"Rook: activation idle confirm failed for surface " +
                            $"'{SurfaceId}': {ex.Message}");
                    }
                });
            }
            catch (Exception ex)
            {
                Log($"Rook: activation idle confirm scheduling failed for " +
                    $"surface '{SurfaceId}': {ex.Message}");
            }
        }

        private void ClearActivationIdleConfirm()
        {
            try { RhinoApp.Idle -= OnActivationIdleConfirm; }
            catch { }

            _activationIdleConfirmPending = false;
        }

        private object? TryGetCoreWebView2Controller()
        {
            var nativeControl = _webView?.ControlObject;
            if (nativeControl == null)
            {
                TraceWebViewFocus("host-visibility-reconcile-skip", "native-control-null");
                return null;
            }

            var webView2Control = GetWebView2NativeControl(nativeControl);
            if (webView2Control == null)
            {
                TraceWebViewFocus("host-visibility-reconcile-skip", "webview2-control-null");
                return null;
            }

            var controllerProp = GetInstanceProperty(
                webView2Control.GetType(),
                "CoreWebView2Controller");
            if (controllerProp == null)
            {
                TraceWebViewFocus("host-visibility-reconcile-skip", "controller-prop-null");
                return null;
            }

            try { return controllerProp.GetValue(webView2Control); }
            catch (Exception ex)
            {
                TraceWebViewFocus("host-visibility-reconcile-failed",
                    "controller-read;" + ex.Message);
                Log($"Rook: WebView2 controller lookup failed for surface " +
                    $"'{ResourceRoot}': {ex.Message}");
                return null;
            }
        }

        private static object? GetWebView2NativeControl(object nativeControl)
        {
            var type = nativeControl.GetType();
            if (GetInstanceProperty(type, "CoreWebView2Controller") != null ||
                GetInstanceProperty(type, "DefaultBackgroundColor") != null)
            {
                return nativeControl;
            }

            var control = GetInstanceProperty(type, "Control")?.GetValue(nativeControl);
            return control ?? nativeControl;
        }

        private static object? GetCoreWebView2ReflectionHost(object nativeControl)
        {
            if (GetInstanceProperty(nativeControl.GetType(), "CoreWebView2") != null)
                return nativeControl;

            var webView2Control = GetWebView2NativeControl(nativeControl);
            if (webView2Control != null &&
                GetInstanceProperty(webView2Control.GetType(), "CoreWebView2") != null)
                return webView2Control;

            return null;
        }

        private static void TrySetDefaultBackgroundColor(object nativeControl)
        {
            var bgProp = GetInstanceProperty(nativeControl.GetType(), "DefaultBackgroundColor");
            if (bgProp == null)
                return;

            try { bgProp.SetValue(nativeControl, System.Drawing.Color.FromArgb(30, 30, 30)); }
            catch { /* best-effort — property may not exist on all platforms */ }
        }

        private void TraceWebViewFocus(string evt, string? detail = null)
        {
            if (!IsWebViewFocusDiagnosticsEnabled())
                return;

            try
            {
                var nativeControl = _webView?.ControlObject;
                var webView2Control = nativeControl == null ? null : GetWebView2NativeControl(nativeControl);
                var coreHost = nativeControl == null ? null : GetCoreWebView2ReflectionHost(nativeControl);
                var core = coreHost == null
                    ? null
                    : GetInstanceProperty(coreHost.GetType(), "CoreWebView2")?.GetValue(coreHost) as CoreWebView2;

                string controllerState = "controller=null";
                if (webView2Control != null)
                {
                    var controller = GetInstanceProperty(
                            webView2Control.GetType(),
                            "CoreWebView2Controller")
                        ?.GetValue(webView2Control);
                    if (controller != null)
                    {
                        var isVisible = GetInstanceProperty(controller.GetType(), "IsVisible")
                            ?.GetValue(controller);
                        controllerState = "controller=" + controller.GetType().FullName +
                            ";isVisible=" + (isVisible?.ToString() ?? "null");
                    }
                }

                var logDir = Path.Combine(Path.GetTempPath(), "rook");
                Directory.CreateDirectory(logDir);
                var line =
                    DateTimeOffset.Now.ToString("O") +
                    "\tsurface=" + ResourceRoot +
                    "\tevent=" + evt +
                    "\tdetail=" + (detail ?? "") +
                    "\tappActive=" + SafeBool(() => Application.Instance.IsActive) +
                    "\tready=" + _webViewReady +
                    "\tbridge=" + IsBridgeAvailable +
                    "\tdisposed=" + _disposed +
                    "\twebViewVisible=" + SafeBool(() => _webView?.Visible == true) +
                    "\tnative=" + (nativeControl?.GetType().FullName ?? "null") +
                    "\twebView2=" + (webView2Control?.GetType().FullName ?? "null") +
                    "\tcoreHost=" + (coreHost?.GetType().FullName ?? "null") +
                    "\tcoreSource=" + (core?.Source ?? "null") +
                    "\t" + controllerState +
                    Environment.NewLine;
                File.AppendAllText(Path.Combine(logDir, "webview-focus.log"), line);
            }
            catch
            {
                // Diagnostics must never affect panel rendering.
            }
        }

        private static string SafeBool(Func<bool> read)
        {
            try { return read() ? "true" : "false"; }
            catch { return "unknown"; }
        }

        private static bool IsWebViewFocusDiagnosticsEnabled()
            => string.Equals(
                Environment.GetEnvironmentVariable("ROOK_ENABLE_WEBVIEW_FOCUS_DIAGNOSTICS"),
                "1",
                StringComparison.Ordinal);

        private static PropertyInfo? GetInstanceProperty(Type type, string name)
            => type.GetProperty(
                name,
                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
#endif

        /// <summary>
        /// Execute JavaScript in the WebView synchronously on the UI thread and wait
        /// for it (Eto pumps a nested message loop while waiting). Never call this from
        /// a stream or event path: every chat presentation goes through
        /// <see cref="PostScript"/>. Retained for callers that need the synchronous
        /// contract (knowledge graph panel). If the WebView is not yet ready, the
        /// script is buffered as a control script and replayed once the document
        /// finishes loading.
        /// </summary>
        public void ExecuteScript(string script)
        {
            if (_disposed || _webView == null)
                return;

            if (!_webViewReady)
            {
                _pendingScripts.Add(ScriptRequest.ForControl(script));
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

        // ─── Script admission (S4, plan §1) ───────────────────────────

        /// <summary>
        /// UI-thread marshaling used by script admission. Production: Eto's
        /// AsyncInvoke. Tests inject a recording scheduler so admission can be
        /// driven deterministically without a dispatcher.
        /// </summary>
        internal Action<Action> UiScheduler
        {
            get => _uiScheduler;
            set => _uiScheduler = value ?? throw new ArgumentNullException(nameof(value));
        }

        /// <summary>Current display generation. Content scripts from an older generation are dropped.</summary>
        public int DisplayGeneration => _displayGeneration;

        /// <summary>
        /// Invalidate all content posted so far (Clear, close). UI thread. Returns the
        /// new generation. Control scripts are unaffected; in-flight scripts run to
        /// completion; queued and buffered content of older generations is dropped at
        /// its next checkpoint.
        /// </summary>
        public int InvalidateDisplay() => ++_displayGeneration;

        /// <summary>Queued plus in-flight scripts.</summary>
        public int Backlog => _scriptQueue.Count + _inFlightScripts;

        /// <summary>Raised on the UI thread whenever the backlog is below <see cref="ScriptResumeThreshold"/> after admission progress.</summary>
        public event Action? BacklogDrained;

        internal int InFlightScripts => _inFlightScripts;
        internal int QueuedScripts => _scriptQueue.Count;
        internal int BufferedScripts => _pendingScripts.Count;

        /// <summary>
        /// Post a script without ever blocking the caller or the UI thread. Always
        /// marshals to the UI thread first; there it is dropped if the surface is
        /// disposed or (for content) its generation is stale, buffered if the document
        /// is not ready, or queued for execution in submission order behind at most
        /// <see cref="MaxInFlightScripts"/> concurrently executing scripts.
        /// </summary>
        public void PostScript(ScriptRequest request)
        {
            if (request == null) throw new ArgumentNullException(nameof(request));
            _uiScheduler(() =>
            {
                if (_disposed || _webView == null) return;
                if (!request.IsValidFor(_displayGeneration)) return;
                if (!_webViewReady)
                {
                    _pendingScripts.Add(request);
                    return;
                }
                _scriptQueue.Enqueue(request);
                TryStartScripts();
            });
        }

        private bool _startingScripts;

        private void TryStartScripts()
        {
            // The executor (CoreWebView2.ExecuteScriptAsync) may pump messages before it
            // returns, so UI callbacks can re-enter here from inside the call. Two
            // rules keep the limit exact under that re-entry: the slot is reserved
            // BEFORE the executor is called, and a nested call does not admit at all;
            // the outer loop observes any work queued meanwhile once the executor
            // returns.
            if (_startingScripts) return;
            _startingScripts = true;
            try
            {
                while (!_disposed && _webView != null && _webViewReady &&
                       _inFlightScripts < MaxInFlightScripts && _scriptQueue.Count > 0)
                {
                    var request = _scriptQueue.Dequeue();
                    if (!request.IsValidFor(_displayGeneration)) continue;
                    _inFlightScripts++;
                    Task<string> task;
                    try
                    {
                        task = ExecuteScriptAsyncCore(request.Script);
                    }
                    catch (Exception ex)
                    {
                        ReleaseReservedSlot();
                        Log($"Rook: script error: {ex.Message}");
                        continue;
                    }
                    if (task.IsCompleted)
                    {
                        ReleaseReservedSlot();
                        LogScriptFault(task);
                        continue;
                    }
                    task.ContinueWith(
                        completed => _uiScheduler(() => OnScriptCompleted(completed)),
                        TaskContinuationOptions.ExecuteSynchronously);
                }
            }
            finally
            {
                _startingScripts = false;
            }
            NotifyBacklogTransition();
        }

        /// <summary>
        /// Release a slot reserved before the executor call. Dispose can run inside
        /// that call (the executor may pump messages) and resets the counter, so the
        /// release must never take it below zero.
        /// </summary>
        private void ReleaseReservedSlot()
        {
            if (_inFlightScripts > 0) _inFlightScripts--;
        }

        private bool _backlogAboveResume;

        /// <summary>
        /// BacklogDrained is a transition event: it fires once each time the backlog
        /// falls back below <see cref="ScriptResumeThreshold"/> after having reached it,
        /// never on every admission.
        /// </summary>
        private void NotifyBacklogTransition()
        {
            var backlog = Backlog;
            if (backlog >= ScriptResumeThreshold)
            {
                _backlogAboveResume = true;
                return;
            }
            if (!_backlogAboveResume) return;
            _backlogAboveResume = false;
            BacklogDrained?.Invoke();
        }

        private void OnScriptCompleted(Task<string> task)
        {
            if (_inFlightScripts > 0) _inFlightScripts--;
            LogScriptFault(task);
            if (_disposed) return;
            TryStartScripts();
        }

        private void LogScriptFault(Task<string> task)
        {
            if (task.IsFaulted)
                Log($"Rook: script error: {task.Exception?.GetBaseException().Message}");
        }

        private Task<string> ExecuteScriptAsyncCore(string script)
        {
#if ROOK_WEBVIEW2
            if (_coreWebView2 != null) return _coreWebView2.ExecuteScriptAsync(script);
#endif
            return _webView!.ExecuteScriptAsync(script);
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

#if ROOK_WEBVIEW2
            TraceWebViewFocus("document-loaded", e.Uri?.ToString());
#endif

            // Move buffered scripts into the admission queue BEFORE marking ready,
            // so any PostScript arriving during the replay queues behind them
            // rather than overtaking them. Stale content (an invalidated display
            // generation) is dropped here; control scripts always replay. This
            // recovers pending work only: content already executed in a previous
            // document is not rebuilt (plan §1 reload limits).
            if (_pendingScripts.Count > 0 && _webView != null)
            {
                foreach (var request in _pendingScripts)
                    if (request.IsValidFor(_displayGeneration)) _scriptQueue.Enqueue(request);
                _pendingScripts.Clear();
            }

            _webViewReady = true;
            TryStartScripts();

            // Bridge availability finalized BEFORE OnWebViewReady so
            // subclasses can rely on IsBridgeAvailable in their override.
            SignalBridgeUnavailableIfNeeded();

            OnWebViewReady();

            // Document (re)load is a presentation edge: it is also the
            // external confirmation trigger after a reconciler-issued reload.
            RequestPresentationReconcile("DocumentLoaded");
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

        private static string BuildFocusProbeScript() => @"(function() {
  if (!window.chrome || !window.chrome.webview || window.__rookFocusProbeInstalled) return;
  window.__rookFocusProbeInstalled = true;
  function clean(value) {
    if (value === undefined || value === null) return '';
    return String(value).replace(/[\r\n\t]+/g, ' ').slice(0, 500);
  }
  function rectText(el) {
    try {
      if (!el || !el.getBoundingClientRect) return '';
      var r = el.getBoundingClientRect();
      return Math.round(r.left) + ',' + Math.round(r.top) + ',' +
        Math.round(r.width) + 'x' + Math.round(r.height);
    } catch (_) { return ''; }
  }
  function layoutSnapshot() {
    var de = document.documentElement;
    var body = document.body;
    var app = document.getElementById('app') ||
      document.querySelector('.app-shell') ||
      document.querySelector('main');
    return {
      viewport: window.innerWidth + 'x' + window.innerHeight,
      docClient: de ? de.clientWidth + 'x' + de.clientHeight : '',
      docScroll: de ? de.scrollWidth + 'x' + de.scrollHeight : '',
      bodyClient: body ? body.clientWidth + 'x' + body.clientHeight : '',
      bodyScroll: body ? body.scrollWidth + 'x' + body.scrollHeight : '',
      appRect: rectText(app),
      activeElement: document.activeElement ? clean(document.activeElement.tagName) : ''
    };
  }
  function post(eventName, extra) {
    try {
      var payload = {
        type: 'rook_focus_probe',
        event: eventName,
        hidden: document.hidden,
        visibilityState: document.visibilityState,
        hasFocus: document.hasFocus ? document.hasFocus() : null,
        readyState: document.readyState,
        href: window.location ? String(window.location.href) : '',
        time: Date.now()
      };
      var layout = layoutSnapshot();
      for (var key in layout) payload[key] = layout[key];
      if (extra) {
        for (var extraKey in extra) payload[extraKey] = clean(extra[extraKey]);
      }
      window.chrome.webview.postMessage(payload);
    } catch (_) { }
  }
  function postLayout(reason) { post('layout-snapshot', { reason: reason }); }
  document.addEventListener('visibilitychange', function() {
    post('visibilitychange');
    postLayout('visibilitychange');
  });
  document.addEventListener('DOMContentLoaded', function() { post('domcontentloaded'); });
  window.addEventListener('focus', function() { post('window-focus'); });
  window.addEventListener('blur', function() { post('window-blur'); });
  window.addEventListener('load', function() { post('window-load'); });
  window.addEventListener('pageshow', function() {
    post('pageshow');
    setTimeout(function() { postLayout('pageshow+250ms'); }, 250);
  });
  window.addEventListener('pagehide', function() { post('pagehide'); });
  window.addEventListener('error', function(e) {
    var target = e.target || e.srcElement;
    if (target && target !== window && target.tagName) {
      post('resource-error', {
        tag: target.tagName,
        target: target.currentSrc || target.src || target.href || target.id || ''
      });
      return;
    }
    post('js-error', {
      message: e.message || '',
      filename: e.filename || '',
      lineno: e.lineno || '',
      colno: e.colno || '',
      errorName: e.error && e.error.name ? e.error.name : '',
      stack: e.error && e.error.stack ? e.error.stack : ''
    });
  }, true);
  window.addEventListener('unhandledrejection', function(e) {
    var reason = e.reason || '';
    post('js-unhandledrejection', {
      reason: reason && reason.message ? reason.message : reason,
      errorName: reason && reason.name ? reason.name : '',
      stack: reason && reason.stack ? reason.stack : ''
    });
  });
  setInterval(function() { post('heartbeat'); }, 30000);
  post('installed');
  setTimeout(function() { postLayout('installed+500ms'); }, 500);
})();";

#if ROOK_WEBVIEW2

        private bool TrySetupVirtualHost()
        {
            try
            {
                var nativeControl = _webView?.ControlObject;
                if (nativeControl == null)
                {
                    TraceWebViewFocus("setup-skip", "native-control-null");
                    return false;
                }

                // Set dark background immediately to prevent white flash when
                // the panel loses focus or during navigation.
                TraceWebViewFocus("setup-start");
                var webView2Control = GetWebView2NativeControl(nativeControl);
                if (webView2Control != null)
                    TrySetDefaultBackgroundColor(webView2Control);

                var coreHost = GetCoreWebView2ReflectionHost(nativeControl);
                if (coreHost == null)
                {
                    TraceWebViewFocus("setup-skip", "core-host-null");
                    return false;
                }

                var coreWv2Property = GetInstanceProperty(coreHost.GetType(), "CoreWebView2");
                if (coreWv2Property == null)
                {
                    TraceWebViewFocus("setup-skip", "core-webview2-prop-null");
                    return false;
                }

                var coreWv2 = coreWv2Property.GetValue(coreHost) as CoreWebView2;
                if (coreWv2 != null)
                {
                    TraceWebViewFocus("setup-existing-core");
                    ConfigureVirtualHost(coreWv2);
                    return true;
                }

                var initEvent = coreHost.GetType().GetEvent(
                    "CoreWebView2InitializationCompleted",
                    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                if (initEvent == null)
                {
                    TraceWebViewFocus("setup-skip", "init-event-null");
                    return false;
                }

                EventHandler<CoreWebView2InitializationCompletedEventArgs> handler = null!;
                handler = (sender, args) =>
                {
                    initEvent.RemoveEventHandler(coreHost, handler);
                    if (ReferenceEquals(_initHandler, handler))
                    {
                        _initEvent = null;
                        _initHandler = null;
                        _nativeControlWithInitHandler = null;
                    }
                    if (_disposed) return;
                    if (args.IsSuccess)
                    {
                        TraceWebViewFocus("setup-init-success");
                        coreWv2 = coreWv2Property.GetValue(coreHost) as CoreWebView2;
                        if (coreWv2 != null)
                            ConfigureVirtualHost(coreWv2);
                    }
                    else
                    {
                        TraceWebViewFocus("setup-init-failed", args.InitializationException?.Message);
                        RhinoApp.WriteLine("Rook: WebView2 init failed, falling back to minimal HTML");
                        Application.Instance.Invoke(() => _webView?.LoadHtml(MinimalFallbackHtml));
                    }
                };
                _nativeControlWithInitHandler = coreHost;
                _initEvent = initEvent;
                _initHandler = handler;
                initEvent.AddEventHandler(coreHost, handler);

                var ensureMethod = coreHost.GetType().GetMethod(
                    "EnsureCoreWebView2Async",
                    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance,
                    binder: null,
                    types: new[] { typeof(CoreWebView2Environment) },
                    modifiers: null);
                ensureMethod?.Invoke(coreHost, new object?[] { null });
                TraceWebViewFocus("setup-ensure-core");

                return true;
            }
            catch (Exception ex)
            {
                TraceWebViewFocus("setup-failed", ex.Message);
                RhinoApp.WriteLine($"Rook: virtual host setup failed: {ex.Message}");
                return false;
            }
        }

        private async void ConfigureVirtualHost(CoreWebView2 coreWebView2)
        {
            try
            {
                if (_disposed) return;
                TraceWebViewFocus("configure-start");

                coreWebView2.AddWebResourceRequestedFilter(
                    $"{VirtualHostOrigin}/*",
                    CoreWebView2WebResourceContext.All);
                coreWebView2.WebResourceRequested += OnWebResourceRequested;

                // Wire bridge BEFORE script injection so the shim's receiver
                // is connected before any page script can post.
                coreWebView2.WebMessageReceived += OnWebMessageReceived;
                coreWebView2.ProcessFailed += OnWebViewProcessFailed;
                coreWebView2.NavigationStarting += OnNavigationStarting;
                coreWebView2.NavigationCompleted += OnNavigationCompleted;
                _coreWebView2 = coreWebView2;
                RequestPresentationReconcile("WebView2Configured");

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

                TraceWebViewFocus("navigate", $"{VirtualHostOrigin}/{EntryPage}");
                coreWebView2.Navigate($"{VirtualHostOrigin}/{EntryPage}");
            }
            catch (Exception ex)
            {
                TraceWebViewFocus("configure-failed", ex.Message);
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
            TraceWebViewFocus("process-failed",
                $"kind={kind};reason={e.Reason};exitCode={e.ExitCode};description={e.ProcessDescription};recovery={action}");
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

        private void OnNavigationStarting(object? sender, CoreWebView2NavigationStartingEventArgs e)
        {
            if (_disposed) return;

            TraceWebViewFocus("navigation-starting",
                $"id={e.NavigationId};uri={e.Uri};redirected={e.IsRedirected};" +
                $"userInitiated={e.IsUserInitiated};cancel={e.Cancel}");
        }

        private void OnNavigationCompleted(object? sender, CoreWebView2NavigationCompletedEventArgs e)
        {
            if (_disposed) return;

            TraceWebViewFocus("navigation-completed",
                $"id={e.NavigationId};success={e.IsSuccess};status={e.HttpStatusCode};" +
                $"webError={e.WebErrorStatus}");
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

        private void OnWebMessageReceived(
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

            var eventCore = sender as CoreWebView2;
            if (eventCore == null || !ReferenceEquals(_coreWebView2, eventCore)) return;
            TraceFocusProbeMessage(incomingJson);
            QueueBridgeMessage(incomingJson,
                action => Application.Instance.AsyncInvoke(action),
                () => ReferenceEquals(_coreWebView2, eventCore),
                response => eventCore.PostWebMessageAsJson(response));
        }

        internal void QueueBridgeMessage(string? incomingJson, Action<Action> postToUi,
            Func<bool> isCurrentView, Action<string> postResponse)
        {
            // Eto's synchronous script execution pumps messages. Leave the native
            // WebView callback before any handler can render back into that view.
            try { postToUi(Dispatch); }
            catch (Exception ex) { Log($"Rook: bridge dispatch post failed: {ex.Message}"); }

            async void Dispatch()
            {
                try
                {
                    if (_disposed || !isCurrentView()) return;
                    var response = await _dispatcher.DispatchAsync(incomingJson);
                    if (response == null || _disposed || !isCurrentView()) return;
                    postToUi(() =>
                    {
                        try
                        {
                            if (_disposed || !isCurrentView()) return;
                            postResponse(response);
                        }
                        catch (Exception ex) { Log($"Rook: bridge response post failed: {ex.Message}"); }
                    });
                }
                catch (Exception ex) { Log($"Rook: deferred bridge dispatch failed: {ex.Message}"); }
            }
        }

        private void TraceFocusProbeMessage(string? incomingJson)
        {
            if (!IsWebViewFocusDiagnosticsEnabled())
                return;

            if (string.IsNullOrEmpty(incomingJson) ||
                incomingJson.IndexOf("rook_focus_probe", StringComparison.Ordinal) < 0)
            {
                return;
            }

            try
            {
                var root = JsonNode.Parse(incomingJson) as JsonObject;
                if (root?["type"]?.GetValue<string>() != "rook_focus_probe")
                    return;

                var evt = root["event"]?.GetValue<string>() ?? "";
                var parts = new List<string>
                {
                    "hidden=" + (root["hidden"]?.ToString() ?? ""),
                    "visibility=" + JsonFieldForLog(root, "visibilityState"),
                    "hasFocus=" + (root["hasFocus"]?.ToString() ?? ""),
                    "readyState=" + JsonFieldForLog(root, "readyState"),
                    "href=" + JsonFieldForLog(root, "href"),
                };
                AppendProbeField(parts, root, "viewport");
                AppendProbeField(parts, root, "docClient");
                AppendProbeField(parts, root, "docScroll");
                AppendProbeField(parts, root, "bodyClient");
                AppendProbeField(parts, root, "bodyScroll");
                AppendProbeField(parts, root, "appRect");
                AppendProbeField(parts, root, "activeElement");
                AppendProbeField(parts, root, "reason");
                AppendProbeField(parts, root, "message");
                AppendProbeField(parts, root, "filename");
                AppendProbeField(parts, root, "lineno");
                AppendProbeField(parts, root, "colno");
                AppendProbeField(parts, root, "tag");
                AppendProbeField(parts, root, "target");
                AppendProbeField(parts, root, "errorName");
                AppendProbeField(parts, root, "stack");

                var detail = string.Join(";", parts);
                TraceWebViewFocus("js-" + evt, detail);
            }
            catch (Exception ex)
            {
                TraceWebViewFocus("js-probe-parse-failed", ex.Message);
            }
        }

        private static void AppendProbeField(List<string> parts, JsonObject root, string name)
        {
            var value = JsonFieldForLog(root, name);
            if (!string.IsNullOrEmpty(value))
                parts.Add(name + "=" + value);
        }

        private static string JsonFieldForLog(JsonObject root, string name)
        {
            try
            {
                var node = root[name];
                if (node == null)
                    return "";

                string value;
                try { value = node.GetValue<string>(); }
                catch { value = node.ToJsonString(); }

                value = value.Replace('\r', ' ').Replace('\n', ' ').Replace('\t', ' ');
                return value.Length <= 500 ? value : value.Substring(0, 500);
            }
            catch
            {
                return "";
            }
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
                TraceWebViewFocus("resource-resolver-failed", $"{uri.AbsolutePath};error={ex.Message}");
                Log($"Rook: TryResolveVirtualResource threw for '{uri}': {ex.Message}");
                // Fall through to embedded-resource path; a surface-level
                // exception must not deny the caller a response.
            }

            if (virtResource != null)
            {
                if (virtResource.StatusCode >= 400)
                {
                    TraceWebViewFocus("resource-virtual-error",
                        $"{uri.AbsolutePath};status={virtResource.StatusCode};type={virtResource.ContentType}");
                }
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
                TraceWebViewFocus("resource-missing", $"{uri.AbsolutePath};resource={resourceName}");
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

            WebSurfacePresentationRegistry.Deregister(this);

            if (!disposing) return;

#if ROOK_WEBVIEW2
            ClearActivationIdleConfirm();

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
                try { _coreWebView2.NavigationStarting -= OnNavigationStarting; }
                catch { }
                try { _coreWebView2.NavigationCompleted -= OnNavigationCompleted; }
                catch { }
                _coreWebView2 = null;
            }
#endif

            var disposeWebView = _disposeWebView;
            _disposeWebView = null;
            disposeWebView?.Invoke();

            _pendingScripts.Clear();
            _scriptQueue.Clear();
            _inFlightScripts = 0;
            _webViewReady = false;
            IsBridgeAvailable = false;
        }

        private void DisposeWebView()
        {
            try { _webView!.DocumentLoaded -= OnDocumentLoaded; }
            catch { }
#if ROOK_WEBVIEW2
            // Match the subscriptions added in CreateWebContent so the
            // surface doesn't leak handlers across tab close / open
            // cycles.
            try { _webView!.GotFocus -= OnWebViewGotFocus; }
            catch { }
            try { _webView!.Shown -= OnWebViewShown; }
            catch { }
            try { _webView!.SizeChanged -= OnWebViewSizeChanged; }
            catch { }
            try { RhinoApp.Idle -= OnActivationIdleConfirm; }
            catch { }
            try { Application.Instance.IsActiveChanged -= OnApplicationIsActiveChanged; }
            catch { }
#endif
            try { _webView!.Dispose(); }
            catch { }
            _webView = null;
        }
    }
}
