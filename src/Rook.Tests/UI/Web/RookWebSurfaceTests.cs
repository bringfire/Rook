using System;
using System.Collections.Generic;
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
    }
}
