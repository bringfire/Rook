using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Rook.UI.Web;
using Xunit;

namespace Rook.Tests.UI.Web
{
    /// <summary>
    /// Tests for net48-reachable substrate behavior:
    ///   - ContentSecurityPolicy virtual property defaults + override
    ///   - ComposeDocumentScripts ordering invariant
    ///   - IsBridgeAvailable initial state
    ///   - RegisterBridgeHandler delegation to BridgeDispatcher
    ///
    /// End-to-end WebView2 wiring is not net48-testable; that's covered
    /// by manual smoke in Rhino 8.
    /// </summary>
    public class RookWebSurfaceTests
    {
        private sealed class DefaultSurface : RookWebSurface
        {
            protected override string ResourceRoot => "Rook.Tests.Surfaces";
            protected override string EntryPage => "test.html";
            protected override string MinimalFallbackHtml => "<html></html>";

            public string CspForTest => ContentSecurityPolicy;
            public IReadOnlyList<string> ComposeForTest() => ComposeDocumentScripts();
            public void RegisterForTest(string method, Func<JsonNode?, Task<JsonNode?>> handler)
                => RegisterBridgeHandler(method, handler);
        }

        private sealed class StrictCspSurface : RookWebSurface
        {
            protected override string ResourceRoot => "Rook.Tests.Surfaces";
            protected override string EntryPage => "test.html";
            protected override string MinimalFallbackHtml => "<html></html>";
            protected override string ContentSecurityPolicy =>
                "default-src 'none'; script-src 'self'; connect-src 'none'";

            public string CspForTest => ContentSecurityPolicy;
        }

        private sealed class WithBootstrapSurface : RookWebSurface
        {
            protected override string ResourceRoot => "Rook.Tests.Surfaces";
            protected override string EntryPage => "test.html";
            protected override string MinimalFallbackHtml => "<html></html>";
            protected override string? GetBootstrapScript() => "window.__surfaceBoot = true;";

            public IReadOnlyList<string> ComposeForTest() => ComposeDocumentScripts();
        }

        // ─── CSP virtual property ────────────────────────────────────

        [Fact]
        public void WebMessageCallback_DefersDispatchAndBindsTheOriginatingView()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");
            var callback = ExtractMethod(source, "private void OnWebMessageReceived(");
            Assert.NotEmpty(callback);
            Assert.DoesNotContain("_dispatcher.DispatchAsync", callback);
            Assert.Contains("QueueBridgeMessage(", callback);
            Assert.Contains("Application.Instance.AsyncInvoke", callback);
            Assert.Contains("ReferenceEquals(_coreWebView2, eventCore)", callback);
            Assert.Contains("eventCore.PostWebMessageAsJson", callback);
        }

        [Fact]
        public void ContentSecurityPolicy_Default_KeepsBackwardsCompatForPatternB()
        {
            var s = new DefaultSurface();

            Assert.Equal(RookWebSurface.DefaultContentSecurityPolicy, s.CspForTest);
            Assert.Contains("connect-src https://app.rook.invalid http://127.0.0.1:*", s.CspForTest);
        }

        [Fact]
        public void ContentSecurityPolicy_Override_PropagatesToSurface()
        {
            var s = new StrictCspSurface();

            Assert.Contains("connect-src 'none'", s.CspForTest);
            Assert.DoesNotContain("127.0.0.1", s.CspForTest);
        }

        [Fact]
        public void DefaultContentSecurityPolicy_KnowledgeGraphRegressionPin()
        {
            // KG and Chat depend on these EXACT directives. Tightening the
            // default would silently break Pattern B surfaces.
            var csp = RookWebSurface.DefaultContentSecurityPolicy;

            Assert.Contains("default-src 'none'", csp);
            Assert.Contains("script-src 'self' 'unsafe-inline'", csp);
            Assert.Contains("style-src 'self' 'unsafe-inline'", csp);
            Assert.Contains("connect-src https://app.rook.invalid http://127.0.0.1:*", csp);
            Assert.Contains("img-src 'self' data:", csp);
            Assert.Contains("font-src 'self'", csp);
        }

        // ─── ComposeDocumentScripts ordering ─────────────────────────

        [Fact]
        public void ComposeDocumentScripts_DefaultSurface_IncludesBridgeShim()
        {
            var s = new DefaultSurface();

            var scripts = s.ComposeForTest();

            // Bridge shim is always present, even when no handlers registered.
            Assert.Contains(scripts, s2 => s2.Contains("window.rookBridge"));
        }

        [Fact]
        public void ComposeDocumentScripts_BridgeShimPrecedesBootstrap()
        {
            var s = new WithBootstrapSurface();

            var scripts = s.ComposeForTest();

            int shimIndex = -1;
            int bootIndex = -1;
            for (int i = 0; i < scripts.Count; i++)
            {
                if (scripts[i].Contains("window.rookBridge")) shimIndex = i;
                if (scripts[i].Contains("__surfaceBoot")) bootIndex = i;
            }

            Assert.NotEqual(-1, shimIndex);
            Assert.NotEqual(-1, bootIndex);
            Assert.True(shimIndex < bootIndex,
                "bridge shim must precede surface bootstrap so window.rookBridge is " +
                "available before any page script runs");
        }

        [Fact]
        public void ComposeDocumentScripts_NonceIfPresentPrecedesBridge()
        {
            // ChatServiceManager.Instance.SessionNonce may or may not be set in
            // the test process. We can only assert the *relative* ordering: if
            // a nonce script appears, it must come before the bridge shim.
            var s = new DefaultSurface();
            var scripts = s.ComposeForTest();

            int nonceIndex = -1;
            int shimIndex = -1;
            for (int i = 0; i < scripts.Count; i++)
            {
                if (scripts[i].Contains("__rookSessionNonce")) nonceIndex = i;
                if (scripts[i].Contains("window.rookBridge")) shimIndex = i;
            }

            Assert.NotEqual(-1, shimIndex);
            if (nonceIndex != -1)
            {
                Assert.True(nonceIndex < shimIndex,
                    "nonce must precede bridge shim per the locked composition order");
            }
        }

        // ─── OnBridgeUnavailable one-shot ────────────────────────────

        private sealed class CountingSurface : RookWebSurface
        {
            protected override string ResourceRoot => "Rook.Tests.Surfaces";
            protected override string EntryPage => "test.html";
            protected override string MinimalFallbackHtml => "<html></html>";

            public int UnavailableCallCount { get; private set; }
            public bool ThrowOnUnavailable { get; set; }
            public List<string> Logs { get; } = new();

            protected override void Log(string message) => Logs.Add(message);

            protected override void OnBridgeUnavailable()
            {
                UnavailableCallCount++;
                if (ThrowOnUnavailable)
                    throw new InvalidOperationException("test-throw");
            }

            public void RegisterForTest(string method, Func<JsonNode?, Task<JsonNode?>> handler)
                => RegisterBridgeHandler(method, handler);
        }

        [Fact]
        public void SignalBridgeUnavailableIfNeeded_FiresAtMostOnce()
        {
            var s = new CountingSurface();
            s.RegisterForTest("m", args => Task.FromResult<JsonNode?>(null));

            s.SignalBridgeUnavailableIfNeeded();
            s.SignalBridgeUnavailableIfNeeded();
            s.SignalBridgeUnavailableIfNeeded();

            Assert.Equal(1, s.UnavailableCallCount);
        }

        [Fact]
        public void SignalBridgeUnavailableIfNeeded_NoHandlers_DoesNotFire()
        {
            var s = new CountingSurface();
            // No handlers registered.

            s.SignalBridgeUnavailableIfNeeded();

            Assert.Equal(0, s.UnavailableCallCount);
        }

        [Fact]
        public void SignalBridgeUnavailableIfNeeded_HookThrows_StillCountedOnce()
        {
            // Hook exception is caught + logged; the one-shot flag is still
            // set so a retry doesn't re-invoke a known-broken hook.
            var s = new CountingSurface { ThrowOnUnavailable = true };
            s.RegisterForTest("m", args => Task.FromResult<JsonNode?>(null));

            s.SignalBridgeUnavailableIfNeeded();
            s.SignalBridgeUnavailableIfNeeded();

            Assert.Equal(1, s.UnavailableCallCount);
        }

        // ─── IsBridgeAvailable ───────────────────────────────────────

        [Fact]
        public void IsBridgeAvailable_BeforeWebViewSetup_IsFalse()
        {
            var s = new DefaultSurface();

            // Test harness never calls CreateWebContent, so bridge stays down.
            Assert.False(s.IsBridgeAvailable);
        }

        // ─── WebView2 process-failure recovery ──────────────────────

        [Theory]
        [InlineData("RenderProcessExited", "Reload")]
        [InlineData("RenderProcessUnresponsive", "LogOnly")]
        [InlineData("BrowserProcessExited", "RecreateRequired")]
        [InlineData("FrameRenderProcessExited", "LogOnly")]
        [InlineData("GpuProcessExited", "LogOnly")]
        [InlineData("UtilityProcessExited", "LogOnly")]
        [InlineData("UnknownProcessExited", "LogOnly")]
        public void ClassifyProcessFailure_MapsWebView2KindsToRecoveryAction(
            string processFailedKind,
            string expectedName)
        {
            var expected = (RookWebSurface.ProcessFailureRecoveryAction)Enum.Parse(
                typeof(RookWebSurface.ProcessFailureRecoveryAction),
                expectedName);

            Assert.Equal(expected, RookWebSurface.ClassifyProcessFailure(processFailedKind));
        }

        // ─── Disposal contract ───────────────────────────────────────

        [Fact]
        public void RookWebSurface_ImplementsDisposable()
        {
            var s = new DefaultSurface();

            Assert.IsAssignableFrom<IDisposable>(s);
        }

        [Fact]
        public void Dispose_IsIdempotent_AndMarksSurfaceDisposed()
        {
            var s = new DefaultSurface();
            Assert.False(s.IsDisposed);

            s.Dispose();
            s.Dispose();

            Assert.True(s.IsDisposed);
        }

        // ─── RegisterBridgeHandler delegation ────────────────────────

        [Fact]
        public void RegisterBridgeHandler_Duplicate_Throws()
        {
            var s = new DefaultSurface();
            s.RegisterForTest("m", args => Task.FromResult<JsonNode?>(null));

            Assert.Throws<ArgumentException>(
                () => s.RegisterForTest("m", args => Task.FromResult<JsonNode?>(null)));
        }

        [Fact]
        public void RegisterBridgeHandler_BeforeWebViewSetup_DoesNotThrow()
        {
            // Per the locked contract, registration always succeeds. The
            // OnBridgeUnavailable hook fires later if the bridge never came
            // up. This test pins the no-throw posture.
            var s = new DefaultSurface();

            s.RegisterForTest("m", args => Task.FromResult<JsonNode?>(null));
            // No exception = pass.
        }

        [Fact]
        public void WebViewHostVisibilitySynchronization_CoversFocusLossAndHostRecovery()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");

            Assert.Contains("_webView.GotFocus += OnWebViewGotFocus;", source);
            Assert.Contains("_webView.Shown += OnWebViewShown;", source);
            Assert.Contains("Application.Instance.IsActiveChanged += OnApplicationIsActiveChanged;", source);
            Assert.Contains("Application.Instance.IsActiveChanged -= OnApplicationIsActiveChanged;", source);
            Assert.DoesNotContain("_webView.LostFocus += OnWebViewLostFocus;", source);
            Assert.Contains("NotifyParentWindowPositionChanged", source);
            Assert.DoesNotContain("ROOK_ENABLE_WEBVIEW_REPAINT_WORKAROUND", source);
            Assert.DoesNotContain("request-repaint-skip", source);
            Assert.Contains("ROOK_ENABLE_WEBVIEW_FOCUS_DIAGNOSTICS", source);
            Assert.Contains("if (IsWebViewFocusDiagnosticsEnabled())", source);
            Assert.Contains("if (!IsWebViewFocusDiagnosticsEnabled())", source);
        }

        [Fact]
        public void WebView2Setup_IsNotGatedOutOfNet48Runtime()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");

            Assert.Contains("#if ROOK_WEBVIEW2", source);
            Assert.DoesNotContain("#if NET7_0_OR_GREATER", source);
        }

        [Fact]
        public void RookProject_WebView2CompileReference_AppliesToNet48()
        {
            var source = ReadSourceFile("src", "Rook", "Rook.csproj");

            Assert.Contains("Microsoft.Web.WebView2", source);
            Assert.DoesNotContain(
                "Microsoft.Web.WebView2\" Version=\"1.0.1938.49\" ExcludeAssets=\"runtime\" Condition=\"'$(TargetFramework)' == 'net8.0' Or '$(TargetFramework)' == 'net7.0'\"",
                source);
        }

        [Fact]
        public void RookWebSurface_DoesNotOwnRhinoPanelLifecycleReasons()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");

            Assert.DoesNotContain("ShowPanelReason", source);
            Assert.DoesNotContain("HideOnDeactivate", source);
            Assert.DoesNotContain("ShowOnDeactivate", source);
        }

        [Fact]
        public void WebViewHostVisibilitySynchronization_UsesLifecycleLogs()
        {
            // Trace strings emitted by the kept reflection helpers
            // (controller lookup, visible-set, parent-position notify).
            var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");

            Assert.Contains("host-controller-visible-set", source);
            Assert.Contains("host-controller-position-notified", source);
            Assert.Contains("host-visibility-reconcile-skip", source);
            Assert.Contains("host-visibility-reconcile-failed", source);
        }

        [Fact]
        public void WebViewFocusDiagnostics_CapturesNavigationResourcesJsAndLayout()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");

            Assert.Contains("NavigationStarting += OnNavigationStarting", source);
            Assert.Contains("NavigationCompleted += OnNavigationCompleted", source);
            Assert.Contains("NavigationStarting -= OnNavigationStarting", source);
            Assert.Contains("NavigationCompleted -= OnNavigationCompleted", source);
            Assert.Contains("navigation-starting", source);
            Assert.Contains("navigation-completed", source);
            Assert.Contains("resource-missing", source);
            Assert.Contains("resource-virtual-error", source);
            Assert.Contains("resource-resolver-failed", source);
            Assert.Contains("js-error", source);
            Assert.Contains("js-unhandledrejection", source);
            Assert.Contains("resource-error", source);
            Assert.Contains("layout-snapshot", source);
            Assert.Contains("appRect", source);
            Assert.DoesNotContain("host-activation-reload", source);
        }

        [Fact]
        public void WebViewHostVisibilitySynchronization_ResolvesNestedWebView2Control()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");

            Assert.Contains("GetWebView2NativeControl", source);
            Assert.Contains("CoreWebView2Controller", source);
            Assert.Contains("DefaultBackgroundColor", source);
            Assert.Contains("GetInstanceProperty(type, \"Control\")", source);
            Assert.Contains("BindingFlags.NonPublic", source);
        }

        // ─── Presentation diagnostics ring (reconciler Record path) ──

        [Fact]
        public void PresentationDiagnosticsRing_IsBoundedAndMemoryOnly()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");
            var diagnostic = ReadSourceFile(
                "src",
                "Rook",
                "UI",
                "Web",
                "WebViewHostPresentationDiagnosticEntry.cs");
            var record = ExtractMethod(
                source,
                "private void RecordReconcilerDiagnostic");
            var dump = ExtractMemberBlock(
                source,
                "internal string DumpHostPresentationDiagnostics(");

            Assert.Contains("MaxHostPresentationDiagnosticEntries = 64", source);
            Assert.Contains("Queue<WebViewHostPresentationDiagnosticEntry>", source);
            Assert.Contains(
                "while (_hostPresentationDiagnostics.Count > MaxHostPresentationDiagnosticEntries)",
                record);
            Assert.Contains("Reason = evt", record);
            Assert.Contains("ActionResult = detail", record);
            Assert.Contains("JsonSerializer.Serialize", dump);
            Assert.DoesNotContain("File.", record + dump);
            Assert.DoesNotContain("object", diagnostic);
            Assert.DoesNotContain("IntPtr", diagnostic);
            Assert.DoesNotContain("Exception", diagnostic);
        }

        // ─── TryResolveVirtualResource hook (PR-7a) ──────────────────

        /// <summary>
        /// Exposes the protected hook so a test can invoke the default
        /// implementation without subclassing to override it — catches any
        /// future behavioral drift on the default.
        /// </summary>
        private sealed class DefaultResolverSurface : RookWebSurface
        {
            protected override string ResourceRoot => "Rook.Tests.Surfaces";
            protected override string EntryPage => "test.html";
            protected override string MinimalFallbackHtml => "<html></html>";

            public VirtualResource? TryResolveForTest(Uri uri) => TryResolveVirtualResource(uri);
        }

        /// <summary>
        /// Example subclass that resolves a single virtual URI path to a
        /// canned payload. Used to verify the subclass-override contract.
        /// </summary>
        private sealed class OverridingResolverSurface : RookWebSurface
        {
            protected override string ResourceRoot => "Rook.Tests.Surfaces";
            protected override string EntryPage => "test.html";
            protected override string MinimalFallbackHtml => "<html></html>";

            public int CallCount { get; private set; }

            protected override VirtualResource? TryResolveVirtualResource(Uri uri)
            {
                CallCount++;
                if (uri.AbsolutePath == "/virtual/ok.txt")
                {
                    return new VirtualResource(
                        new MemoryStream(Encoding.UTF8.GetBytes("hello")),
                        "text/plain",
                        200,
                        "X-Rook-Virtual: 1");
                }
                return null;
            }

            public VirtualResource? TryResolveForTest(Uri uri) => TryResolveVirtualResource(uri);
        }

        [Fact]
        public void TryResolveVirtualResource_DefaultImplementation_ReturnsNull()
        {
            // The default is a no-op so existing consumers (Chat, Knowledge
            // Graph) see zero behavioral change — embedded-resource serving
            // and the 404 fall-through path stay authoritative.
            var s = new DefaultResolverSurface();
            var uri = new Uri("https://app.rook.invalid/virtual/anything.png");

            var result = s.TryResolveForTest(uri);

            Assert.Null(result);
        }

        [Fact]
        public void CreateWebContent_SeedsInitialAppActiveState()
        {
            // The reconciler defaults to app-inactive; without seeding the
            // real activation state at content creation, every initial
            // reconcile (WebView2Configured, DocumentLoaded, PanelShown)
            // would skip as inactive until Rhino emits an activation edge —
            // exactly the timing-gap class this architecture removes.
            var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");
            var method = ExtractMethod(source, "public Control CreateWebContent()");

            Assert.Contains("_reconciler.SetAppActive(", method);
            Assert.Contains("Application.Instance?.IsActive == true", method);
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = Path.Combine(dir.FullName, Path.Combine(pathParts));
                if (File.Exists(candidate))
                    return File.ReadAllText(candidate);
                dir = dir.Parent;
            }

            throw new FileNotFoundException(
                "Could not locate source file " + string.Join("/", pathParts));
        }

        private static string ExtractMethod(string source, string signature)
        {
            var start = source.IndexOf(signature, StringComparison.Ordinal);
            if (start < 0)
                return string.Empty;

            var brace = source.IndexOf('{', start);
            if (brace < 0)
                return source.Substring(start);

            var depth = 0;
            for (var i = brace; i < source.Length; i++)
            {
                if (source[i] == '{')
                    depth++;
                else if (source[i] == '}')
                    depth--;

                if (depth == 0)
                    return source.Substring(start, i - start + 1);
            }

            return source.Substring(start);
        }

        private static string ExtractMemberBlock(string source, string signature)
        {
            var start = source.IndexOf(signature, StringComparison.Ordinal);
            Assert.True(start >= 0, "Missing source member: " + signature);

            var brace = source.IndexOf('{', start);
            Assert.True(brace >= 0, "Missing member body: " + signature);

            var depth = 0;
            for (var i = brace; i < source.Length; i++)
            {
                if (source[i] == '{')
                    depth++;
                else if (source[i] == '}')
                {
                    depth--;
                    if (depth == 0)
                        return source.Substring(start, i - start + 1);
                }
            }

            throw new InvalidOperationException(
                "Unterminated source member: " + signature);
        }

        [Fact]
        public void TryResolveVirtualResource_Override_ReturnedForMatchingPath()
        {
            var s = new OverridingResolverSurface();
            var uri = new Uri("https://app.rook.invalid/virtual/ok.txt");

            var result = s.TryResolveForTest(uri);

            Assert.NotNull(result);
            Assert.Equal("text/plain", result!.ContentType);
            Assert.Equal(200, result.StatusCode);
            Assert.Contains("X-Rook-Virtual", result.ExtraHeaders ?? "");
            Assert.Equal(1, s.CallCount);
        }

        [Fact]
        public void TryResolveVirtualResource_Override_NullForUnknownPath()
        {
            // Subclass returns null for unrecognized paths; the substrate
            // falls through to embedded-resource lookup.
            var s = new OverridingResolverSurface();
            var uri = new Uri("https://app.rook.invalid/virtual/not-handled.png");

            var result = s.TryResolveForTest(uri);

            Assert.Null(result);
            Assert.Equal(1, s.CallCount); // still invoked, just returned null
        }

        [Fact]
        public void VirtualResource_Ctor_SetsAllFields()
        {
            using var stream = new MemoryStream(new byte[] { 1, 2, 3 });

            var r = new VirtualResource(stream, "image/png", 200, "X-Foo: bar");

            Assert.Same(stream, r.Content);
            Assert.Equal("image/png", r.ContentType);
            Assert.Equal(200, r.StatusCode);
            Assert.Equal("X-Foo: bar", r.ExtraHeaders);
        }

        [Fact]
        public void VirtualResource_Ctor_DefaultStatusAndHeaders()
        {
            using var stream = new MemoryStream();

            var r = new VirtualResource(stream, "text/plain");

            Assert.Equal(200, r.StatusCode);
            Assert.Null(r.ExtraHeaders);
        }

        [Fact]
        public void VirtualResource_NonSuccessStatus_Preserved()
        {
            // Subclasses returning a 404 (resource not found) should see
            // the status propagate — the substrate maps 404 to "Not Found"
            // in the reason phrase.
            using var stream = new MemoryStream();

            var r = new VirtualResource(stream, "text/plain", 404);

            Assert.Equal(404, r.StatusCode);
        }
    }
}
