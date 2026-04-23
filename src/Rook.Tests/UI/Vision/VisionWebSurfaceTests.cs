using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.UI.Vision;
using Xunit;

namespace Rook.Tests.UI.Vision
{
    /// <summary>
    /// Unit coverage for <see cref="VisionWebSurface"/>'s pure logic and
    /// its virtual-resource resolver for <c>/blob/{artifact_id}/{role}</c>.
    ///
    /// End-to-end WebView2 wiring, bridge lifecycle, and CSP header
    /// emission on real HTTP responses live outside net48 — those are
    /// manual-smoke in Rhino 8. Here we pin:
    ///   - The CSP override string — silent drift on Pattern A would
    ///     reintroduce network affordances the boundary exists to block.
    ///   - The op-routing table — any add/remove must surface here
    ///     rather than silently changing the dispatcher target.
    ///   - URI parsing helpers — path-traversal and GUID/role validation
    ///     cover the security envelope (store also validates, but we
    ///     reject in the surface so bad callers never reach the store).
    ///   - Virtual-resource dispatch — success, 404 paths, and the
    ///     fall-through-vs-404 decision for malformed blob URIs.
    /// </summary>
    public class VisionWebSurfaceTests : IDisposable
    {
        private readonly string _artifactsRoot;
        private readonly ArtifactStore _store;

        public VisionWebSurfaceTests()
        {
            _artifactsRoot = Path.Combine(
                Path.GetTempPath(), $"rook-vision-web-test-{Guid.NewGuid():N}");
            _store = new ArtifactStore(_artifactsRoot);
        }

        public void Dispose()
        {
            if (Directory.Exists(_artifactsRoot))
            {
                try { Directory.Delete(_artifactsRoot, recursive: true); }
                catch { /* best-effort cleanup */ }
            }
        }

        private VisionWebSurface NewSurface()
            => new VisionWebSurface(new VisionHandler(), _store);

        // ─── CSP override pin ─────────────────────────────────────────

        [Fact]
        public void ContentSecurityPolicy_Pinned_v1()
        {
            const string expected =
                "default-src 'none'; " +
                "script-src 'self'; " +
                "style-src 'self' 'unsafe-inline'; " +
                "font-src 'self'; " +
                "img-src 'self' data:; " +
                "connect-src 'none';";
            Assert.Equal(expected, VisionWebSurface.VisionContentSecurityPolicy);
        }

        [Fact]
        public void ContentSecurityPolicy_Forbids_ConnectSrc()
        {
            // Regression: Pattern A boundary requires no fetch/XHR path out.
            Assert.Contains("connect-src 'none'", VisionWebSurface.VisionContentSecurityPolicy);
        }

        [Fact]
        public void ContentSecurityPolicy_Forbids_UnsafeInline_InScripts()
        {
            // Regression: script-src must not grant 'unsafe-inline'. The
            // default RookWebSurface CSP did for the Chat/Knowledge Graph
            // surfaces; Vision must tighten.
            Assert.DoesNotContain("script-src 'self' 'unsafe-inline'",
                VisionWebSurface.VisionContentSecurityPolicy);
        }

        // ─── Async op timeout ─────────────────────────────────────────

        [Fact]
        public void AsyncOpTimeout_MatchesNativeTrampoline()
        {
            // The native `vision_dispatch` path in NativeGhBridgeRegistrar
            // caps async ops at 180 s (generate / enhance_prompt). The
            // JS-bridge path must use the same ceiling so both entry
            // points have symmetric cancellation behavior — otherwise a
            // UI-initiated generate could outlast its agent-path twin.
            Assert.Equal(180, VisionWebSurface.AsyncOpTimeout.TotalSeconds);
        }

        // ─── Async op timeout — behavioral coverage ───────────────────

        [Fact]
        public async Task DispatchWithTimeout_HappyPath_PassesResponseThrough()
        {
            var expected = new ApiResponse
            {
                Success = true,
                Data = new Dictionary<string, object?> { ["x"] = 1 },
            };
            var actual = await VisionWebSurface.DispatchWithTimeoutAsync(
                "generate",
                TimeSpan.FromSeconds(5),
                _ => Task.FromResult(expected));
            Assert.True(actual.Success);
            Assert.Same(expected.Data, actual.Data);
        }

        [Fact]
        public async Task DispatchWithTimeout_ObservedCancellation_EmitsTimeoutEnvelope()
        {
            // Simulates a well-behaved dispatcher that honors the token
            // and throws OperationCanceledException when the CTS fires.
            var response = await VisionWebSurface.DispatchWithTimeoutAsync(
                "generate",
                TimeSpan.FromMilliseconds(30),
                async token =>
                {
                    await Task.Delay(TimeSpan.FromSeconds(2), token).ConfigureAwait(false);
                    return new ApiResponse { Success = true };
                });

            Assert.False(response.Success);
            var message = Assert.IsType<string>(response.Data);
            Assert.Contains("timed out", message, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("'generate'", message);
            Assert.Contains("0s", message); // 30 ms rounds to 0s under F0.
        }

        [Fact]
        public async Task DispatchWithTimeout_SwallowedCancellation_RewritesDataField()
        {
            // Simulates VisionHandler's outer catch: the dispatcher
            // swallows OperationCanceledException and returns its own
            // `{Success=false, Data="... failed ..."}` envelope. The
            // wrapper must detect the CTS state and rewrite Data so the
            // UI sees the timeout cause, not the generic fallback.
            var response = await VisionWebSurface.DispatchWithTimeoutAsync(
                "enhance_prompt",
                TimeSpan.FromMilliseconds(30),
                async token =>
                {
                    try
                    {
                        await Task.Delay(TimeSpan.FromSeconds(2), token).ConfigureAwait(false);
                    }
                    catch (Exception)
                    {
                        // Mimics the production handler's catch-all.
                    }
                    return new ApiResponse
                    {
                        Success = false,
                        Data = "Vision op 'enhance_prompt' failed. See Rhino command line for details.",
                    };
                });

            Assert.False(response.Success);
            var message = Assert.IsType<string>(response.Data);
            Assert.Contains("timed out", message, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("'enhance_prompt'", message);
            Assert.DoesNotContain("See Rhino command line", message);
        }

        [Fact]
        public async Task DispatchWithTimeout_FailureWithoutTimeout_PassesThrough()
        {
            // A dispatcher that fails WITHOUT cancellation must not
            // trigger the rewrite — the original failure message is
            // the UI's signal about the real cause.
            var response = await VisionWebSurface.DispatchWithTimeoutAsync(
                "generate",
                TimeSpan.FromSeconds(5),
                _ => Task.FromResult(new ApiResponse
                {
                    Success = false,
                    Data = "API key invalid.",
                }));

            Assert.False(response.Success);
            Assert.Equal("API key invalid.", response.Data);
        }

        [Fact]
        public async Task DispatchWithTimeout_NonCancellationException_Propagates()
        {
            // Exceptions that are NOT OperationCanceledException must
            // flow up to the bridge handler's outer catch unchanged.
            // Otherwise we'd bury real bugs behind a misleading
            // "timed out" envelope.
            await Assert.ThrowsAsync<InvalidOperationException>(() =>
                VisionWebSurface.DispatchWithTimeoutAsync(
                    "generate",
                    TimeSpan.FromSeconds(5),
                    _ => throw new InvalidOperationException("boom")));
        }

        // ─── OpRoutes table ───────────────────────────────────────────

        [Fact]
        public void OpRoutes_Contains_All_Expected_Ops()
        {
            var expected = new[]
            {
                "generate", "enhance_prompt", "test_api_key",
                "capture_depth", "capture_viewport", "list_views", "open_image_picker",
                "list_artifacts", "get_artifact", "approve_artifact",
                "delete_artifact", "consume_approved",
                "set_api_key", "get_settings_overview",
            };
            foreach (var op in expected)
            {
                Assert.True(VisionWebSurface.OpRoutes.ContainsKey(op),
                    $"OpRoutes missing '{op}'");
            }
            // And no extras that a forgotten cleanup left behind.
            Assert.Equal(expected.Length, VisionWebSurface.OpRoutes.Count);
        }

        [Theory]
        // Route names kept as strings so the [Theory] method can stay
        // public while VisionOpRoute is internal — xUnit requires
        // InlineData argument types to be as visible as the test
        // method.
        [InlineData("generate", "Async")]
        [InlineData("enhance_prompt", "Async")]
        [InlineData("test_api_key", "Async")]
        [InlineData("capture_depth", "Ui")]
        [InlineData("capture_viewport", "Ui")]
        [InlineData("list_views", "Ui")]
        [InlineData("open_image_picker", "Ui")]
        [InlineData("list_artifacts", "OffUi")]
        [InlineData("get_artifact", "OffUi")]
        [InlineData("approve_artifact", "OffUi")]
        [InlineData("delete_artifact", "OffUi")]
        [InlineData("consume_approved", "OffUi")]
        [InlineData("set_api_key", "OffUi")]
        [InlineData("get_settings_overview", "OffUi")]
        public void OpRoutes_Map_To_Correct_Dispatchers(string op, string expectedRouteName)
        {
            var expected = (VisionWebSurface.VisionOpRoute)Enum.Parse(
                typeof(VisionWebSurface.VisionOpRoute), expectedRouteName);
            Assert.Equal(expected, VisionWebSurface.OpRoutes[op]);
        }

        [Fact]
        public void OpRoutes_UnknownOp_NotPresent()
        {
            Assert.False(VisionWebSurface.OpRoutes.ContainsKey("definitely_not_an_op"));
            // Also guard against capitalization drift — the dictionary is
            // case-sensitive and snake_case is load-bearing.
            Assert.False(VisionWebSurface.OpRoutes.ContainsKey("Generate"));
            Assert.False(VisionWebSurface.OpRoutes.ContainsKey("GENERATE"));
        }

        // ─── PeekOp ───────────────────────────────────────────────────

        [Fact]
        public void PeekOp_ReturnsNull_ForEmpty()
        {
            Assert.Null(VisionWebSurface.PeekOp(null));
            Assert.Null(VisionWebSurface.PeekOp(""));
        }

        [Fact]
        public void PeekOp_ReturnsNull_ForNonObject()
        {
            Assert.Null(VisionWebSurface.PeekOp("[]"));
            Assert.Null(VisionWebSurface.PeekOp("\"string\""));
            Assert.Null(VisionWebSurface.PeekOp("42"));
        }

        [Fact]
        public void PeekOp_ReturnsNull_ForMissingOp()
        {
            Assert.Null(VisionWebSurface.PeekOp("{\"x\": 1}"));
        }

        [Fact]
        public void PeekOp_ReturnsNull_ForNonStringOp()
        {
            Assert.Null(VisionWebSurface.PeekOp("{\"op\": 42}"));
        }

        [Fact]
        public void PeekOp_ReturnsOpString()
        {
            Assert.Equal("generate", VisionWebSurface.PeekOp("{\"op\":\"generate\"}"));
            Assert.Equal("list_artifacts",
                VisionWebSurface.PeekOp("{\"op\":\"list_artifacts\",\"extra\":true}"));
        }

        [Fact]
        public void PeekOp_ReturnsNull_ForMalformedJson()
        {
            Assert.Null(VisionWebSurface.PeekOp("{bogus"));
        }

        // ─── IsBlobPath / TryParseBlobUri / IsValidRole ───────────────

        [Theory]
        [InlineData("https://app.rook.invalid/blob/abc/def", true)]
        [InlineData("https://app.rook.invalid/blob", true)]
        [InlineData("https://app.rook.invalid/blob/", true)]
        [InlineData("https://app.rook.invalid/index.html", false)]
        [InlineData("https://app.rook.invalid/blobotron/ic", false)]
        [InlineData("https://app.rook.invalid/knowledge/graph", false)]
        public void IsBlobPath_DetectsShape(string url, bool expected)
        {
            Assert.Equal(expected, VisionWebSurface.IsBlobPath(new Uri(url)));
        }

        [Fact]
        public void TryParseBlobUri_ValidShape_ReturnsIdAndRole()
        {
            var id = Guid.NewGuid();
            var url = $"https://app.rook.invalid/blob/{id:D}/image";
            var ok = VisionWebSurface.TryParseBlobUri(new Uri(url), out var parsedId, out var role);
            Assert.True(ok);
            Assert.Equal(id, parsedId);
            Assert.Equal("image", role);
        }

        [Fact]
        public void TryParseBlobUri_WrongPrefix_Fails()
        {
            var id = Guid.NewGuid();
            var url = $"https://app.rook.invalid/bloc/{id:D}/image";
            Assert.False(VisionWebSurface.TryParseBlobUri(new Uri(url), out _, out _));
        }

        [Fact]
        public void TryParseBlobUri_WrongSegmentCount_Fails()
        {
            Assert.False(VisionWebSurface.TryParseBlobUri(
                new Uri("https://app.rook.invalid/blob"), out _, out _));
            Assert.False(VisionWebSurface.TryParseBlobUri(
                new Uri("https://app.rook.invalid/blob/" + Guid.NewGuid().ToString("D")),
                out _, out _));
            Assert.False(VisionWebSurface.TryParseBlobUri(
                new Uri("https://app.rook.invalid/blob/a/b/c"), out _, out _));
        }

        [Fact]
        public void TryParseBlobUri_InvalidGuid_Fails()
        {
            Assert.False(VisionWebSurface.TryParseBlobUri(
                new Uri("https://app.rook.invalid/blob/not-a-guid/image"),
                out _, out _));
        }

        [Theory]
        [InlineData("image", true)]
        [InlineData("thumbnail", true)]
        [InlineData("image1", true)]
        [InlineData("a-b_c", true)]
        [InlineData("0abc", true)]
        [InlineData("", false)]
        [InlineData("IMAGE", false)]              // uppercase not allowed
        [InlineData("-abc", false)]               // cannot start with dash
        [InlineData("_abc", false)]               // cannot start with underscore
        [InlineData("a.b", false)]                // dots forbidden
        [InlineData("a/b", false)]                // slash forbidden
        [InlineData("a b", false)]                // space forbidden
        [InlineData("..", false)]                 // directory traversal
        public void IsValidRole_PatternCheck(string role, bool expected)
        {
            Assert.Equal(expected, VisionWebSurface.IsValidRole(role));
        }

        [Fact]
        public void IsValidRole_LongRoleRejected()
        {
            // Defensive upper bound — 65 chars exceeds the 64-char cap.
            var role = new string('a', 65);
            Assert.False(VisionWebSurface.IsValidRole(role));
        }

        // ─── GuessBlobContentType ─────────────────────────────────────

        [Theory]
        [InlineData("foo.png", "image/png")]
        [InlineData("foo.PNG", "image/png")]
        [InlineData("foo.jpg", "image/jpeg")]
        [InlineData("foo.jpeg", "image/jpeg")]
        [InlineData("foo.webp", "image/webp")]
        [InlineData("foo.gif", "image/gif")]
        [InlineData("foo.bmp", "image/bmp")]
        [InlineData("foo.json", "application/json; charset=utf-8")]
        [InlineData("foo.txt", "text/plain; charset=utf-8")]
        [InlineData("foo.unknown", "application/octet-stream")]
        [InlineData("foo", "application/octet-stream")]
        public void GuessBlobContentType_MapsExtensions(string path, string expected)
        {
            Assert.Equal(expected, VisionWebSurface.GuessBlobContentType(path));
        }

        // ─── ApiResponseToJsonNode ────────────────────────────────────

        [Fact]
        public void ApiResponseToJsonNode_SuccessWithDictData_Roundtrips()
        {
            var resp = new ApiResponse
            {
                Success = true,
                Data = new Dictionary<string, object?>
                {
                    ["artifact_id"] = "abc",
                    ["count"] = 3,
                },
            };
            var node = VisionWebSurface.ApiResponseToJsonNode(resp);
            Assert.NotNull(node);
            Assert.True(node["success"]!.GetValue<bool>());
            Assert.Equal("abc", node["data"]!["artifact_id"]!.GetValue<string>());
            Assert.Equal(3, node["data"]!["count"]!.GetValue<int>());
        }

        [Fact]
        public void ApiResponseToJsonNode_FailureWithStringData_Roundtrips()
        {
            var resp = new ApiResponse { Success = false, Data = "boom" };
            var node = VisionWebSurface.ApiResponseToJsonNode(resp);
            Assert.False(node["success"]!.GetValue<bool>());
            Assert.Equal("boom", node["data"]!.GetValue<string>());
        }

        [Fact]
        public void ApiResponseToJsonNode_NullData_SerializesAsNull()
        {
            var resp = new ApiResponse { Success = true, Data = null };
            var node = VisionWebSurface.ApiResponseToJsonNode(resp);
            Assert.True(node["success"]!.GetValue<bool>());
            Assert.Null(node["data"]);
        }

        [Fact]
        public void BuildFailure_ShapesAsStructuredEnvelope()
        {
            var node = VisionWebSurface.BuildFailure("nope");
            Assert.False(node["success"]!.GetValue<bool>());
            Assert.Equal("nope", node["data"]!.GetValue<string>());
        }

        // ─── TryResolveVirtualResource — full happy path ──────────────

        [Fact]
        public void ResolveVirtualResource_Blob_ServesStream_OnMatch()
        {
            // Arrange: create an artifact with a known id and image blob.
            var bytes = Encoding.UTF8.GetBytes("fake-png-content");
            var artifact = _store.Create(
                kind: "generated_image",
                blobs: new[] { new BlobInput("image", bytes, "png") });

            var surface = NewSurface();
            var uri = new Uri($"https://app.rook.invalid/blob/{artifact.Id:D}/image");

            // Act
            var resource = surface.ResolveVirtualResourceForTest(uri);

            // Assert
            Assert.NotNull(resource);
            Assert.Equal(200, resource!.StatusCode);
            Assert.Equal("image/png", resource.ContentType);
            Assert.NotNull(resource.Content);
            using var reader = new StreamReader(resource.Content);
            Assert.Equal("fake-png-content", reader.ReadToEnd());
            Assert.Contains("Cache-Control: no-store", resource.ExtraHeaders ?? "");
        }

        [Fact]
        public void ResolveVirtualResource_NonBlobPath_FallsThrough()
        {
            var surface = NewSurface();
            Assert.Null(surface.ResolveVirtualResourceForTest(
                new Uri("https://app.rook.invalid/index.html")));
            Assert.Null(surface.ResolveVirtualResourceForTest(
                new Uri("https://app.rook.invalid/styles.css")));
        }

        [Fact]
        public void ResolveVirtualResource_MalformedBlobUri_Returns404()
        {
            var surface = NewSurface();
            var resource = surface.ResolveVirtualResourceForTest(
                new Uri("https://app.rook.invalid/blob/not-a-guid/image"));
            Assert.NotNull(resource);
            Assert.Equal(404, resource!.StatusCode);
        }

        [Fact]
        public void ResolveVirtualResource_NonexistentArtifact_Returns404()
        {
            var surface = NewSurface();
            var missingId = Guid.NewGuid();
            var resource = surface.ResolveVirtualResourceForTest(
                new Uri($"https://app.rook.invalid/blob/{missingId:D}/image"));
            Assert.NotNull(resource);
            Assert.Equal(404, resource!.StatusCode);
        }

        [Fact]
        public void ResolveVirtualResource_WrongRole_Returns404()
        {
            var bytes = Encoding.UTF8.GetBytes("content");
            var artifact = _store.Create(
                kind: "generated_image",
                blobs: new[] { new BlobInput("image", bytes, "png") });

            var surface = NewSurface();
            var resource = surface.ResolveVirtualResourceForTest(
                new Uri($"https://app.rook.invalid/blob/{artifact.Id:D}/prompt"));
            Assert.NotNull(resource);
            Assert.Equal(404, resource!.StatusCode);
        }

        [Fact]
        public void ResolveVirtualResource_TraversalAttempt_Returns404()
        {
            // "%2E%2E" decodes to ".." and would land in the path segment.
            // The canonical `Uri.AbsolutePath` normalizes `/blob/../etc`
            // to `/etc`, which fails the `blob/` prefix and falls
            // through (null) — still safe. Here we test an explicit
            // dot-segment that survives canonicalization: a role
            // containing "..".
            var surface = NewSurface();
            var id = Guid.NewGuid().ToString("D");
            var resource = surface.ResolveVirtualResourceForTest(
                new Uri($"https://app.rook.invalid/blob/{id}/.."));
            Assert.NotNull(resource);
            Assert.Equal(404, resource!.StatusCode);
        }

        [Fact]
        public void ResolveVirtualResource_UppercaseRole_Returns404()
        {
            // Role pattern is lowercase-only — same invariant as the
            // artifact store's RolePattern. Hard-reject at the surface
            // so store lookups never run with a mismatched key.
            var bytes = Encoding.UTF8.GetBytes("content");
            var artifact = _store.Create(
                kind: "generated_image",
                blobs: new[] { new BlobInput("image", bytes, "png") });

            var surface = NewSurface();
            var resource = surface.ResolveVirtualResourceForTest(
                new Uri($"https://app.rook.invalid/blob/{artifact.Id:D}/IMAGE"));
            Assert.NotNull(resource);
            Assert.Equal(404, resource!.StatusCode);
        }
    }
}
