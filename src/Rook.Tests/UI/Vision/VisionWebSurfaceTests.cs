using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Rook;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Vision;
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
        public void ContentSecurityPolicy_Pinned_v3()
        {
            // PR-V3: media-src 'self' added so generated_video blobs
            // play through <video src="/blob/{id}/video">. Without this
            // directive media-src defaults to default-src ('none') under
            // CSP3 and <video>/<audio> are blocked even when the blob
            // would resolve.
            const string expected =
                "default-src 'none'; " +
                "script-src 'self'; " +
                "style-src 'self' 'unsafe-inline'; " +
                "font-src 'self'; " +
                "img-src 'self' data:; " +
                "media-src 'self'; " +
                "connect-src 'none';";
            Assert.Equal(expected, VisionWebSurface.VisionContentSecurityPolicy);
        }

        [Fact]
        public void ContentSecurityPolicy_AllowsSelfMediaSrc_ForVideoPlayback()
        {
            // Regression: PR-V3 added media-src 'self' for the video
            // queue/result panels. Pin so a future tightening doesn't
            // silently break <video> playback.
            Assert.Contains("media-src 'self'", VisionWebSurface.VisionContentSecurityPolicy);
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
                // Image (PR-5a/5b)
                "generate", "enhance_prompt", "test_api_key",
                "capture_depth", "capture_viewport", "preview_viewport",
                "list_views",
                "list_artifacts", "get_artifact", "approve_artifact",
                "delete_artifact", "consume_approved",
                "set_api_key", "get_settings_overview",
                "set_provider_secret", "test_provider_secret",
                "clear_provider_secret", "list_image_models",
                "open_artifacts_folder", "reveal_artifact_file",
                // Hidden image job ops — bridge-only, not native HTTP.
                "image_generate_start", "image_job_cancel",
                "image_job_status", "image_job_result", "image_jobs",
                // Media gallery import ops — bridge-only, not native HTTP.
                "start_media_import", "get_media_import_job",
                "list_media_import_jobs",
                // V2 video — bridge mirrors of the native HTTP routes.
                "submit_video_job", "cancel_video_job",
                "get_video_job", "get_video_job_result",
                "estimate_video_job",
                // V3 video — bridge-only (NOT in native trampoline).
                "list_video_jobs", "list_video_models",
                // Presentation reconciler (spec 2026-06-10) — substrate-
                // wide dump + operator-forced repair.
                "get_presentation_diagnostics", "repair_presentation",
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
        [InlineData("test_provider_secret", "Async")]
        [InlineData("capture_depth", "Ui")]
        [InlineData("capture_viewport", "Ui")]
        [InlineData("preview_viewport", "Ui")]
        [InlineData("list_views", "Ui")]
        [InlineData("list_artifacts", "OffUi")]
        [InlineData("get_artifact", "OffUi")]
        [InlineData("approve_artifact", "OffUi")]
        [InlineData("delete_artifact", "OffUi")]
        [InlineData("consume_approved", "OffUi")]
        [InlineData("set_api_key", "OffUi")]
        [InlineData("get_settings_overview", "OffUi")]
        [InlineData("set_provider_secret", "OffUi")]
        [InlineData("clear_provider_secret", "OffUi")]
        [InlineData("list_image_models", "OffUi")]
        [InlineData("open_artifacts_folder", "OffUi")]
        [InlineData("reveal_artifact_file", "OffUi")]
        // Hidden image jobs — start/cancel can call providers; reads are off-UI.
        [InlineData("image_generate_start", "Async")]
        [InlineData("image_job_cancel", "Async")]
        [InlineData("image_job_status", "OffUi")]
        [InlineData("image_job_result", "OffUi")]
        [InlineData("image_jobs", "OffUi")]
        // Media gallery import — picker on UI; job reads off-UI.
        [InlineData("start_media_import", "Ui")]
        [InlineData("get_media_import_job", "OffUi")]
        [InlineData("list_media_import_jobs", "OffUi")]
        // V2 video ops — submit/cancel are async (provider HTTP via
        // manager); status/result/estimate are off-UI sync.
        [InlineData("submit_video_job", "Async")]
        [InlineData("cancel_video_job", "Async")]
        [InlineData("get_video_job", "OffUi")]
        [InlineData("get_video_job_result", "OffUi")]
        [InlineData("estimate_video_job", "OffUi")]
        // V3 video — both off-UI: ledger reads + registry enumeration.
        [InlineData("list_video_jobs", "OffUi")]
        [InlineData("list_video_models", "OffUi")]
        // Presentation reconciler — UI-thread (touches the WebView2
        // controller and the Eto async-invoke scheduler).
        [InlineData("get_presentation_diagnostics", "Ui")]
        [InlineData("repair_presentation", "Ui")]
        public void OpRoutes_Map_To_Correct_Dispatchers(string op, string expectedRouteName)
        {
            var expected = (VisionWebSurface.VisionOpRoute)Enum.Parse(
                typeof(VisionWebSurface.VisionOpRoute), expectedRouteName);
            Assert.Equal(expected, VisionWebSurface.OpRoutes[op]);
        }

        [Theory]
        [InlineData("submit_video_job")]
        [InlineData("cancel_video_job")]
        [InlineData("get_video_job")]
        [InlineData("get_video_job_result")]
        [InlineData("estimate_video_job")]
        [InlineData("list_video_jobs")]
        [InlineData("list_video_models")]
        public void VideoOps_Set_Tracks_VideoOpHandler_Constants(string op)
        {
            // Pin: bridge-side video op set is wired to VideoOpHandler's
            // canonical op constants (the same names native uses, where
            // applicable). If either drifts, this trips. PR-V3 expanded
            // the set with two bridge-only read ops.
            Assert.Contains(op, VisionWebSurface.VideoOps);
        }

        [Fact]
        public void VideoOps_Set_HasExactly7Entries()
        {
            // Defensive count pin — no drift between OpRoutes-side video
            // entries and VideoOps-side membership.
            //   5 V2 ops (submit/cancel/status/result/estimate)
            // + 2 V3 bridge-only ops (list_video_jobs, list_video_models)
            Assert.Equal(7, VisionWebSurface.VideoOps.Count);
        }

        [Theory]
        [InlineData("generate")]
        [InlineData("capture_depth")]
        [InlineData("list_artifacts")]
        public void VideoOps_Set_DoesNotContainImageOps(string op)
        {
            // Negative pin — image ops MUST NOT route to VideoOpHandler.
            Assert.DoesNotContain(op, VisionWebSurface.VideoOps);
        }

        [Theory]
        [InlineData("image_generate_start")]
        [InlineData("image_job_cancel")]
        [InlineData("image_job_status")]
        [InlineData("image_job_result")]
        [InlineData("image_jobs")]
        [InlineData("start_media_import")]
        [InlineData("get_media_import_job")]
        [InlineData("list_media_import_jobs")]
        public void ImageJobOps_AreNotVideoOps(string op)
        {
            Assert.DoesNotContain(op, VisionWebSurface.VideoOps);
        }

        [Theory]
        [InlineData("start_media_import")]
        [InlineData("get_media_import_job")]
        [InlineData("list_media_import_jobs")]
        public void MediaImportOps_Set_Tracks_MediaImportOpHandler_Constants(string op)
        {
            Assert.Contains(op, VisionWebSurface.MediaImportOps);
        }

        [Fact]
        public void MediaImportOps_Set_HasExactly3Entries()
        {
            Assert.Equal(3, VisionWebSurface.MediaImportOps.Count);
        }

        [Fact]
        public async Task MediaImportOp_WithNullMediaImportHandler_ReturnsStructuredFailure()
        {
            var surface = NewSurface();
            var response = await InvokeVisionBridgeAsync(
                surface,
                new JsonObject
                {
                    ["op"] = "get_media_import_job",
                    ["job_id"] = Guid.NewGuid().ToString("D"),
                });

            Assert.NotNull(response);
            Assert.False(response!["success"]!.GetValue<bool>());
            var message = response["data"]!.GetValue<string>();
            Assert.Contains(
                "Media import subsystem unavailable in this surface.",
                message);
        }

        [Fact]
        public async Task ImageJobOp_WithNullImageJobHandler_ReturnsStructuredFailure()
        {
            var surface = NewSurface();
            var response = await InvokeVisionBridgeAsync(
                surface,
                new JsonObject
                {
                    ["op"] = "image_job_status",
                    ["job_id"] = Guid.NewGuid().ToString("D"),
                });

            Assert.NotNull(response);
            Assert.False(response!["success"]!.GetValue<bool>());
            var message = response["data"]!.GetValue<string>();
            Assert.Contains(
                "Image job subsystem unavailable in this surface.",
                message);
        }

        [Fact]
        public void BuildSharedVisionHandler_UsesSharedArtifactStore()
        {
            // Codex review of step 6 caught that the production ctor
            // was building VisionHandler() with its parameterless
            // default — which spawns a FRESH ArtifactStore instance
            // even though the surface field uses the shared one. Pin
            // the fix: the helper must thread the shared singleton
            // through. Reflection over the private _artifactStore
            // field is the only mechanism short of a public getter,
            // and a regression here would silently revert the layering
            // discipline the v2 scope locked.
            var handler = InvokeBuildSharedVisionHandler();
            var fieldInfo = typeof(VisionHandler).GetField(
                "_artifactStore",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(fieldInfo);
            var actual = fieldInfo!.GetValue(handler);

            Assert.Same(RookSubsystemRoot.Instance.SharedArtifactStore, actual);
        }

        [Fact]
        public void BuildSharedVisionHandler_UsesSecretStoreShimBackedBySharedGenerationSecretStore()
        {
            // VisionSecretStore remains as the enhance_prompt/settings
            // compatibility facade, but PR-4 retargets identity to the
            // underlying keyed IGenerationSecretStore.
            var handler = InvokeBuildSharedVisionHandler();
            var fieldInfo = typeof(VisionHandler).GetField(
                "_secrets",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(fieldInfo);
            var shim = Assert.IsType<VisionSecretStore>(fieldInfo!.GetValue(handler));
            var generationField = typeof(VisionSecretStore).GetField(
                "_generationSecrets",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(generationField);

            Assert.Same(
                RookSubsystemRoot.Instance.SharedGenerationSecretStore,
                generationField!.GetValue(shim));
        }

        [Fact]
        public void BuildSharedVisionHandler_UsesSharedGenerationSecretStore()
        {
            // PR-4 widens the secret keyspace behind
            // IGenerationSecretStore. The VisionSecretStore shim may
            // remain for enhance_prompt compatibility, but provider
            // construction must read the shared keyed store directly.
            var handler = InvokeBuildSharedVisionHandler();
            var fieldInfo = typeof(VisionHandler).GetField(
                "_generationSecrets",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(fieldInfo);
            var actual = fieldInfo!.GetValue(handler);

            Assert.Same(RookSubsystemRoot.Instance.SharedGenerationSecretStore, actual);
        }

        [Fact]
        public void BuildSharedVisionHandler_UsesSharedImageProviderRegistry()
        {
            var handler = InvokeBuildSharedVisionHandler();
            var fieldInfo = typeof(VisionHandler).GetField(
                "_imageProviderRegistry",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(fieldInfo);

            Assert.Same(
                RookSubsystemRoot.Instance.ImageJobs.Registry,
                fieldInfo!.GetValue(handler));
        }

        private static VisionHandler InvokeBuildSharedVisionHandler()
        {
            var method = typeof(VisionWebSurface).GetMethod(
                "BuildSharedVisionHandler",
                BindingFlags.Static | BindingFlags.NonPublic);
            Assert.NotNull(method);
            var result = method!.Invoke(null, Array.Empty<object?>());
            Assert.NotNull(result);
            return (VisionHandler)result!;
        }

        private static async Task<JsonNode?> InvokeVisionBridgeAsync(
            VisionWebSurface surface,
            JsonNode? args)
        {
            var method = typeof(VisionWebSurface).GetMethod(
                "HandleVisionBridgeCallAsync",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(method);
            var result = method!.Invoke(surface, new object?[] { args });
            var task = Assert.IsAssignableFrom<Task<JsonNode?>>(result);
            return await task.ConfigureAwait(false);
        }

        [Theory]
        [InlineData("get_presentation_diagnostics")]
        [InlineData("repair_presentation")]
        public void PresentationOps_AreUiRouted(string op)
        {
            Assert.True(VisionWebSurface.OpRoutes.TryGetValue(op, out var route));
            Assert.Equal(VisionWebSurface.VisionOpRoute.Ui, route);
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

        // ─── Embedded Vision resources ────────────────────────────────

        [Fact]
        public void IndexHtml_AspectDropdowns_DefaultToAutoAndExposeApiRatios()
        {
            var html = ReadVisionResource("index.html");
            Assert.True(
                CountOccurrences(html, "<option value=\"auto\" selected>Auto</option>") >= 2,
                "Generate and Studio aspect dropdowns should both default to Auto.");

            foreach (var ratio in new[]
            {
                "1:1", "1:4", "4:1", "1:8", "8:1",
                "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
                "9:16", "16:9", "21:9",
            })
            {
                Assert.Contains($"<option value=\"{ratio}\">{ratio}</option>", html);
            }
        }

        [Fact]
        public void IndexHtml_DefaultResolutionDropdowns_Expose512ForDefaultModelFallback()
        {
            var html = ReadVisionResource("index.html");
            Assert.True(
                CountOccurrences(html, "<option value=\"512\">512</option>") >= 2,
                "Generate and Studio fallback resolution dropdowns should expose 512 for the embedded default model.");
            Assert.True(
                CountOccurrences(html, "<option value=\"1K\" selected>1K</option>") >= 2,
                "512 should be optional, not the static fallback default.");
        }

        [Fact]
        public void IndexHtml_SettingsOverview_HasArtifactBreakdownRows()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("Generated images", html);
            Assert.Contains("id=\"overview-generated-image-count\"", html);
            Assert.Contains("Viewport captures", html);
            Assert.Contains("id=\"overview-captured-viewport-count\"", html);
            Assert.Contains("Prompt enhancements", html);
            Assert.Contains("id=\"overview-enhanced-prompt-count\"", html);
            Assert.Contains("Depth maps", html);
            Assert.Contains("id=\"overview-depth-map-count\"", html);
            Assert.Contains("Total artifacts", html);
        }

        [Fact]
        public void IndexHtml_Settings_UsesProviderCredentialsContainer()
        {
            var html = ReadVisionResource("index.html");

            Assert.Contains("id=\"provider-credentials\"", html);
            Assert.DoesNotContain("id=\"save-api-key\"", html);
        }

        [Fact]
        public void IndexHtml_ApproveButtons_ExplainDownstreamUse()
        {
            var html = ReadVisionResource("index.html");
            const string tooltip =
                "Mark this image as approved so Rook can use it as the selected concept for downstream workflows.";
            Assert.Equal(3, CountOccurrences(html, $"title=\"{tooltip}\""));
            Assert.Equal(3, CountOccurrences(html, $"aria-label=\"{tooltip}\""));
        }

        [Fact]
        public void IndexHtml_GalleryToolbar_ExposesArtifactsFolderButton()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"open-artifacts-folder\"", html);
            Assert.Contains("title=\"Open artifacts folder\"", html);
            Assert.Contains("aria-label=\"Open artifacts folder\"", html);
        }

        [Fact]
        public void IndexHtml_GalleryToolbar_ExposesAddMediaButton()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"add-media-gallery\"", html);
            Assert.Contains("title=\"Add media to Gallery\"", html);
            Assert.Contains("Add Media to Gallery", html);
        }

        [Fact]
        public void IndexHtml_Modal_ExposesRevealButtonBetweenApproveAndDelete()
        {
            var html = ReadVisionResource("index.html");
            var approveIndex = html.IndexOf("id=\"modal-approve-btn\"", StringComparison.Ordinal);
            var revealIndex = html.IndexOf("id=\"modal-reveal-btn\"", StringComparison.Ordinal);
            var deleteIndex = html.IndexOf("id=\"modal-delete-btn\"", StringComparison.Ordinal);

            Assert.True(approveIndex >= 0, "modal approve button is missing.");
            Assert.True(revealIndex >= 0, "modal reveal button is missing.");
            Assert.True(deleteIndex >= 0, "modal delete button is missing.");
            Assert.True(approveIndex < revealIndex, "reveal button should come after approve.");
            Assert.True(revealIndex < deleteIndex, "reveal button should come before delete.");
            Assert.Contains("Show in Folder", html);
            Assert.Contains("title=\"Show this image file in its artifact folder\"", html);
            Assert.Contains("aria-label=\"Show this image file in its artifact folder\"", html);
        }

        [Fact]
        public void StylesCss_ModalActions_CanWrap()
        {
            // Scoped check — substring-only would false-positive against
            // unrelated `flex-wrap: wrap;` in `.reference-area` /
            // `.reference-preview`. Regex pins the property inside the
            // `.modal-actions` rule body specifically.
            var css = ReadVisionResource("styles.css");
            Assert.Matches(
                @"\.modal-actions\s*\{[^}]*flex-wrap:\s*wrap;",
                css);
        }

        [Fact]
        public void AppJs_AutoAspect_OmitsAspectRatioFromGeneratePayload()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("function selectedAspectRatio", js);
            Assert.Contains("if (aspectRatio) args.aspect_ratio = aspectRatio;", js);
            Assert.DoesNotContain("aspect_ratio: el.aspectSelect.value", js);
            Assert.DoesNotContain("aspect_ratio: el.studioAspectSelect.value", js);
        }

        [Fact]
        public void AppJs_SettingsOverview_RendersArtifactBreakdown()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("const artifactCounts = data.artifact_counts_by_kind || {};", js);
            Assert.Contains("el.overviewGeneratedImageCount.textContent = formatCount(artifactCounts.generated_image);", js);
            Assert.Contains("el.overviewCapturedViewportCount.textContent = formatCount(artifactCounts.captured_viewport);", js);
            Assert.Contains("el.overviewEnhancedPromptCount.textContent = formatCount(artifactCounts.enhanced_prompt);", js);
            Assert.Contains("el.overviewDepthMapCount.textContent = formatCount(artifactCounts.depth_map);", js);
        }

        [Fact]
        public void AppJs_RendersProviderCredentialCardsAndUsesProviderOps()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("function renderProviderCredentials", js);
            Assert.Contains("bridgeCall(\"set_provider_secret\"", js);
            Assert.Contains("bridgeCall(\"test_provider_secret\"", js);
            Assert.Contains("bridgeCall(\"clear_provider_secret\"", js);
            Assert.Contains("sessionValidationBySecret", js);
        }

        [Fact]
        public void AppJs_RemovesOrGuardsLegacyApiKeyControls()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("if (el.providerCredentials)", js);
            Assert.Contains("if (el.toggleKeyBtn && el.apiKey)", js);
            Assert.Contains("if (el.saveApiKeyBtn && el.apiKey)", js);
            Assert.Contains("if (el.testApiKeyBtn && el.apiKey)", js);
        }

        [Fact]
        public void AppJs_ImageCatalog_PrefersListImageModelsWithAvailableModelsFallback()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("bridgeCall(\"list_image_models\"", js);
            Assert.Contains("function normalizeImageModelDescriptor", js);
            Assert.Contains("data.available_models", js);
        }

        [Fact]
        public void AppJs_ConsumesSubmissionModeFromImageCatalog()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("submission_mode", js);
            Assert.Contains("function isAsyncImageJobModel", js);
            Assert.Contains("m.submission_mode || \"sync\"", js);
        }

        [Fact]
        public void AppJs_GenerateRoutesAsyncModelsThroughImageJobOps()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("async function generateImageJob", js);
            Assert.Contains("bridgeCall(\"image_generate_start\"", js);
            Assert.Contains("bridgeCall(\"image_job_status\"", js);
            Assert.Contains("bridgeCall(\"image_job_result\"", js);
            Assert.Contains("Image job did not return a job id.", js);
            Assert.Contains("Image job returned an invalid status.", js);
            Assert.Contains("Image job completed without an artifact.", js);
            Assert.Contains("state === \"materializing\"", js);
            Assert.DoesNotContain("provider_name === \"replicate\"", js);
        }

        [Fact]
        public void AppJs_BuildsFalVideoOptionsWithoutVeoPersonGeneration()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("function buildProviderOptions", js);
            Assert.Contains("m.provider_name === \"fal\"", js);
            Assert.Contains("return {};", js);
            Assert.Contains("person_generation: ve.personGenSelect.value", js);
            Assert.DoesNotContain("bytedance/seedance-2.0/image-to-video", js);
        }

        [Fact]
        public void AppJs_RequiresPromptForFalVideoModels()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("function isPromptRequiredForVideo", js);
            Assert.Contains("mode === \"t2v\" || !!(m && m.provider_name === \"fal\")", js);
            Assert.Contains(
                "isPromptRequiredForVideo(currentModel(), mode) && !ve.prompt.value.trim()",
                js);
            Assert.Contains("Required for this fal model.", js);
            Assert.DoesNotContain("bytedance/seedance-2.0/image-to-video", js);
        }

        [Fact]
        public void AppJs_GenerateRoutesSourceImageAsyncModelsWithInputImagePath()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("function isSourceImageAsyncImageModel", js);
            Assert.Contains("function shouldSubmitPromptOnlyAsyncImageJob", js);
            Assert.Contains("const sourcePath = capturedViewport && capturedViewport.file_path;", js);
            Assert.Contains("await generateImageJob(prompt, model, sourcePath);", js);
            Assert.Contains("if (sourcePath && isSourceImageAsyncImageModel(model)) args.input_image_path = sourcePath;", js);
            Assert.Contains("if (sourcePath && isSourceImageAsyncImageModel(model)) args.aspect_ratio = \"match_input_image\";", js);
            Assert.Contains("if (shouldSubmitPromptOnlyAsyncImageJob(model, sourcePath))", js);

            var jobStart = js.IndexOf("async function generateImageJob", StringComparison.Ordinal);
            var jobEnd = js.IndexOf("function showImageJobStatus", StringComparison.Ordinal);
            Assert.True(jobStart >= 0);
            Assert.True(jobEnd > jobStart);
            var jobBody = js.Substring(jobStart, jobEnd - jobStart);
            Assert.DoesNotContain("reference_image_paths", jobBody);
        }

        [Fact]
        public void AppJs_GenerateAllowsPromptOnlyForDualCapabilityAsyncModelsWithoutSource()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("function canRunPromptOnlyAsyncImageJob", js);
            Assert.Contains("model.supports_text_to_image !== false", js);
            Assert.Contains("function shouldSubmitPromptOnlyAsyncImageJob", js);
            Assert.Contains("&& (!sourcePath || model.supports_image_to_image === false);", js);

            var validateStart = js.IndexOf("function validateGenerateModelForSubmit", StringComparison.Ordinal);
            var validateEnd = js.IndexOf("function validateStudioModelForSubmit", validateStart, StringComparison.Ordinal);
            Assert.True(validateStart >= 0, "Generate validation helper must exist.");
            Assert.True(validateEnd > validateStart, "Generate validation helper body must be bounded.");
            var validateBody = js.Substring(validateStart, validateEnd - validateStart);
            Assert.Contains("!canRunPromptOnlyAsyncImageJob(model)", validateBody);
            Assert.DoesNotContain("!isPromptOnlyAsyncImageModel(model)", validateBody);
        }

        [Fact]
        public void AppJs_StudioRoutesAsyncModelsThroughImageJobOps()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("async function studioGenerateImageJob", js);
            Assert.Contains("await studioGenerateImageJob(args, model);", js);
            Assert.Contains("bridgeCall(\"image_generate_start\", args)", js);
            Assert.Contains("bridgeCall(\"image_job_status\"", js);
            Assert.Contains("bridgeCall(\"image_job_result\"", js);
            Assert.Contains("showStudioImageJobStatus", js);
        }

        [Fact]
        public void AppJs_SourceImageAsyncRoutingIsProviderNeutralForFalGptImage2Edit()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("function isSourceImageAsyncImageModel", js);
            Assert.Contains("model.submission_mode === \"async_image_job\"", js);
            Assert.Contains("model.supports_image_to_image !== false", js);
            Assert.Contains("await generateImageJob(prompt, model, sourcePath);", js);
            Assert.Contains("await studioGenerateImageJob(args, model);", js);
            Assert.DoesNotContain("provider_name === \"replicate\"", js);
            Assert.DoesNotContain("openai/gpt-image-2/edit", js);
        }

        [Fact]
        public void AppJs_DisablesGenerateSourceControlsForTextToImageOnlyAsyncModels()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("function updateGenerateInputMode", js);
            Assert.Contains("generate-input-disabled", js);
            Assert.Contains("let isCapturingViewport = false;", js);
            Assert.Contains("promptOnlyAsync || isCapturingViewport", js);
            Assert.Contains("el.captureBtn.disabled = disableCaptureControls", js);
            Assert.Contains("el.addReferenceBtn.disabled = disableReferenceControls", js);
            Assert.Contains("generateReferences = [];", js);
        }

        [Fact]
        public void AppJs_ResolutionSelectFallsBackToFirstSupportedModelResolution()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("function populateResolutionSelect", js);
            Assert.Contains("const fallback = values.length > 0 ? values[0] : \"\";", js);
            Assert.Contains("selectEl.value = values.includes(previous) ? previous : fallback;", js);
            Assert.DoesNotContain("selectEl.value = values.includes(previous) ? previous : \"1K\";", js);
        }

        [Fact]
        public void AppJs_DisablesGenerateReferencesForModelsWithZeroReferenceLimit()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("const maxReferences = model ? Number(model.max_reference_images || 0) : 0;", js);
            Assert.Contains("const disableReferenceControls = promptOnlyAsync || maxReferences === 0;", js);
            Assert.Contains("el.addReferenceBtn.disabled = disableReferenceControls", js);
            Assert.Contains("el.clearReferencesBtn.disabled = disableReferenceControls", js);
            Assert.Contains("if (disableReferenceControls && generateReferences.length > 0) {", js);
            Assert.Contains("generateReferences = [];", js);
            Assert.Contains("renderReferencePreview(generateReferences, el.referencePreview);", js);
        }

        [Fact]
        public void AppJs_DisablesStudioReferencesForModelsWithZeroReferenceLimit()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("function updateStudioInputMode", js);
            Assert.Contains("const maxReferences = model ? Number(model.max_reference_images || 0) : 0;", js);
            Assert.Contains("const disableReferenceControls = maxReferences === 0;", js);
            Assert.Contains("el.studioAddReferenceBtn.disabled = disableReferenceControls", js);
            Assert.Contains("el.studioClearReferencesBtn.disabled = disableReferenceControls", js);
            Assert.Contains("if (disableReferenceControls && studioReferences.length > 0) {", js);
            Assert.Contains("studioReferences = [];", js);
            Assert.Contains("renderReferencePreview(studioReferences, el.studioReferencePreview);", js);
            Assert.Contains("updateStudioInputMode();", js);
        }

        [Fact]
        public void AppJs_StudioOmitsReferencesForZeroReferenceModelsBeforeSubmit()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("const model = selectedImageModel(el.studioModelSelect);", js);
            Assert.Contains("if (modelMaxReferenceImages(model) > 0 && studioReferences.length > 0) {", js);
            Assert.Contains("if (artifactRefs.length > 0 && pathRefs.length > 0) {", js);
            Assert.Contains("Reference images must come from the same source type", js);
            Assert.Contains("args.reference_images = artifactRefs;", js);
            Assert.Contains("args.reference_image_paths = pathRefs;", js);
        }

        [Fact]
        public void AppJs_MediaImportGuardsLaunchAndForegroundPolling()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("let isStartingMediaImport = false;", js);

            var startBegin = js.IndexOf("async function startMediaImport()", StringComparison.Ordinal);
            var startEnd = js.IndexOf("async function loadMediaImportJobs()", startBegin, StringComparison.Ordinal);
            Assert.True(startBegin >= 0, "startMediaImport must exist.");
            Assert.True(startEnd > startBegin, "startMediaImport body must be bounded.");
            var startBody = js.Substring(startBegin, startEnd - startBegin);
            Assert.Contains("if (isStartingMediaImport) return;", startBody);
            Assert.Contains("isStartingMediaImport = true;", startBody);
            Assert.Contains("el.addMediaGalleryBtn.disabled = true;", startBody);
            Assert.Contains("isStartingMediaImport = false;", startBody);
            Assert.Contains("el.addMediaGalleryBtn.disabled = false;", startBody);

            var awaitBegin = js.IndexOf("async function awaitMediaImportJob(jobId)", StringComparison.Ordinal);
            var awaitEnd = js.IndexOf("function pollMediaImportJob(jobId)", awaitBegin, StringComparison.Ordinal);
            Assert.True(awaitBegin >= 0, "awaitMediaImportJob must exist.");
            Assert.True(awaitEnd > awaitBegin, "awaitMediaImportJob body must be bounded.");
            var awaitBody = js.Substring(awaitBegin, awaitEnd - awaitBegin);
            Assert.Contains("const reservedPollerSlot = jobId && !mediaImportPollers.has(jobId);", awaitBody);
            Assert.Contains("mediaImportPollers.set(jobId, null);", awaitBody);
            Assert.Contains("mediaImportPollers.delete(jobId);", awaitBody);
        }

        [Fact]
        public void AppJs_ReferencePickerImportsArtifactRefsAndDoesNotExposePaths()
        {
            var js = ReadVisionResource("app.js");

            var pickerStart = js.IndexOf("async function pickReferenceImages(", StringComparison.Ordinal);
            var pickerEnd = js.IndexOf("function referenceFromImportedImage(file)", pickerStart, StringComparison.Ordinal);
            Assert.True(pickerStart >= 0, "Reference picker helper must exist.");
            Assert.True(pickerEnd > pickerStart, "Reference picker helper body must be bounded.");
            var pickerBody = js.Substring(pickerStart, pickerEnd - pickerStart);
            Assert.Contains("bridgeCall(\"start_media_import\", {", pickerBody);
            Assert.Contains("picker_mode: multi ? \"image_multi\" : \"image_single\"", pickerBody);
            Assert.Contains("await awaitMediaImportJob(job.job_id)", pickerBody);
            Assert.Contains("file.artifact_kind === \"imported_image\" && file.artifact_id", pickerBody);
            Assert.Contains(".map(referenceFromImportedImage)", pickerBody);
            Assert.DoesNotContain("open_image_picker", pickerBody);

            var refStart = pickerEnd;
            var refEnd = js.IndexOf("function renderReferencePreview", refStart, StringComparison.Ordinal);
            Assert.True(refEnd > refStart, "Imported reference helper body must be bounded.");
            var refBody = js.Substring(refStart, refEnd - refStart);
            Assert.Contains("source: \"artifact\"", refBody);
            Assert.Contains("artifact_id: file.artifact_id", refBody);
            Assert.Contains("role: \"image\"", refBody);

            var renderEnd = js.IndexOf("// \u2500\u2500\u2500 Framing helpers", refEnd, StringComparison.Ordinal);
            Assert.True(renderEnd > refEnd, "Reference preview body must be bounded.");
            var renderBody = js.Substring(refEnd, renderEnd - refEnd);
            Assert.Contains("const label = ref.label || basename(ref.path) || \"reference image\";", renderBody);
            Assert.Contains("title=\"${escapeAttr(label)}\"", renderBody);
            Assert.DoesNotContain("title=\"${escapeAttr(ref.path", renderBody);

            var syncStart = js.IndexOf("async function generateSyncImage", StringComparison.Ordinal);
            var syncEnd = js.IndexOf("function renderGeneratedArtifact", syncStart, StringComparison.Ordinal);
            Assert.True(syncStart >= 0, "Generate sync helper must exist.");
            Assert.True(syncEnd > syncStart, "Generate sync helper body must be bounded.");
            var syncBody = js.Substring(syncStart, syncEnd - syncStart);
            Assert.Contains("applyImageReferenceArgs(args, generateReferences);", syncBody);
            Assert.DoesNotContain("reference_image_paths = generateReferences.map", syncBody);

            var asyncStart = js.IndexOf("async function generateImageJob", StringComparison.Ordinal);
            var asyncEnd = js.IndexOf("async function awaitImageJobResult", asyncStart, StringComparison.Ordinal);
            Assert.True(asyncStart >= 0, "Generate async job helper must exist.");
            Assert.True(asyncEnd > asyncStart, "Generate async job helper body must be bounded.");
            var asyncBody = js.Substring(asyncStart, asyncEnd - asyncStart);
            Assert.Contains("applyImageReferenceArgs(args, generateReferences);", asyncBody);
            Assert.DoesNotContain("reference_image_paths = generateReferences.map", asyncBody);
        }

        [Fact]
        public void AppJs_StudioUsesImageArtifactRefsForSelectedSource()
        {
            var js = ReadVisionResource("app.js");

            var loadStart = js.IndexOf("async function studioLoadImage()", StringComparison.Ordinal);
            var loadEnd = js.IndexOf("async function studioCaptureDepth()", loadStart, StringComparison.Ordinal);
            Assert.True(loadStart >= 0, "Studio Load Image handler must exist.");
            Assert.True(loadEnd > loadStart, "Studio Load Image handler body must be bounded.");
            var loadBody = js.Substring(loadStart, loadEnd - loadStart);

            Assert.Contains("bridgeCall(\"start_media_import\", {", loadBody);
            Assert.Contains("picker_mode: \"image_single\"", loadBody);
            Assert.Contains("await awaitMediaImportJob(job.job_id)", loadBody);
            Assert.DoesNotContain("open_image_picker", loadBody);
            Assert.Contains("file.artifact_kind === \"imported_image\" && file.artifact_id", loadBody);
            Assert.Contains("source: \"artifact\"", loadBody);
            Assert.Contains("artifact_id: imported.artifact_id", loadBody);
            Assert.Contains("role: \"image\"", loadBody);

            var refStart = js.IndexOf("function artifactImageRef(src)", StringComparison.Ordinal);
            var refEnd = js.IndexOf("function applyStudioSourceArgs(args)", refStart, StringComparison.Ordinal);
            Assert.True(refStart >= 0, "Artifact image ref helper must exist.");
            Assert.True(refEnd > refStart, "Artifact image ref helper body must be bounded.");
            var refBody = js.Substring(refStart, refEnd - refStart);
            Assert.Contains("kind: \"artifact_id\"", refBody);
            Assert.Contains("artifact_id: src.artifact_id", refBody);
            Assert.Contains("role: src.role || \"image\"", refBody);

            var sourceStart = refEnd;
            var sourceEnd = js.IndexOf("function applyStudioReferenceArgs(args)", sourceStart, StringComparison.Ordinal);
            Assert.True(sourceEnd > sourceStart, "Studio source args helper body must be bounded.");
            var sourceBody = js.Substring(sourceStart, sourceEnd - sourceStart);
            Assert.Contains("if (studioSource.source === \"artifact\" && studioSource.artifact_id)", sourceBody);
            Assert.Contains("Object.assign(args, { input_image: artifactImageRef(studioSource) });", sourceBody);
            Assert.Contains("args.input_image_path = studioSource.path;", sourceBody);

            var refsEnd = js.IndexOf("async function loadGallery()", sourceEnd, StringComparison.Ordinal);
            Assert.True(refsEnd > sourceEnd, "Studio reference args helper body must be bounded.");
            var refsBody = js.Substring(sourceEnd, refsEnd - sourceEnd);
            Assert.Contains("args.reference_images = artifactRefs;", refsBody);
            Assert.Contains("args.reference_image_paths = pathRefs;", refsBody);
        }

        [Fact]
        public void AppJs_GenerateSyncRequiresCapturedViewportFilePath()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("capturedViewport && capturedViewport.file_path", js);
            Assert.Contains("if (!sourcePath) {", js);
            Assert.Contains("input_image_path: sourcePath", js);
        }

        [Fact]
        public void AppJs_ReconstructTexturedOptionsRequireSelectedModelPbrSupport()
        {
            var js = ReadVisionResource("app.js");
            var compact = Regex.Replace(js, @"\s+", " ");

            Assert.Contains("function selectedModel()", js);
            Assert.Contains("const model = selectedModel();", js);
            Assert.Contains("return model && model.supports_pbr ? { enable_pbr: true } : {};", compact);
        }

        [Fact]
        public void AppJs_StudioKeepsTextToImageOnlyModelsIncompatible()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("function validateStudioModelForSubmit", js);
            Assert.Contains("Selected model is incompatible with Studio", js);
        }

        [Fact]
        public void AppJs_InvalidCredentialWarningDoesNotDisableSubmit()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("function effectiveCredentialAvailability", js);
            Assert.Contains("function markProviderCredentialInvalid", js);
            Assert.Contains("sessionValidationBySecret.get", js);
            Assert.Contains("invalid_credential", js);
            Assert.DoesNotContain("availability === \"invalid_credential\" && option.disabled", js);
        }

        [Fact]
        public void AppJs_MissingRequiredSecretWinsOverSessionValidationOverlay()
        {
            var js = ReadVisionResource("app.js");

            var missingCheck = js.IndexOf(
                "if (base === \"missing_required_secret\") return base;",
                StringComparison.Ordinal);
            var overlayRead = js.IndexOf(
                "const overlay = sessionValidationBySecret.get",
                StringComparison.Ordinal);

            Assert.True(missingCheck >= 0, "Missing required secrets must remain deterministic blockers.");
            Assert.True(overlayRead >= 0, "Session validation overlay should still be read for non-missing secrets.");
            Assert.True(missingCheck < overlayRead, "Missing persisted credentials must not be overridden by candidate validation overlays.");
        }

        [Fact]
        public void AppJs_CredentialInputClearsOverlayAndRefreshesPickerLabels()
        {
            var js = ReadVisionResource("app.js");

            var handlerStart = js.IndexOf("function handleProviderCredentialInput", StringComparison.Ordinal);
            var handlerEnd = js.IndexOf("function handleProviderCredentialClick", handlerStart, StringComparison.Ordinal);
            var handlerBody = handlerEnd > handlerStart
                ? js.Substring(handlerStart, handlerEnd - handlerStart)
                : string.Empty;
            var clearOverlay = handlerBody.IndexOf("clearSecretOverlay(ctx.providerName, ctx.secretKey);", StringComparison.Ordinal);
            var refreshPicker = handlerBody.IndexOf("populateImageModelDropdowns(modelCatalog);", StringComparison.Ordinal);

            Assert.True(handlerStart >= 0, "Credential input handler must exist.");
            Assert.True(clearOverlay >= 0, "Editing a credential must clear its session overlay.");
            Assert.True(refreshPicker > clearOverlay, "Editing a credential must refresh picker warning labels after clearing overlay state.");
        }

        [Fact]
        public void AppJs_PopulateImageModelsPreservesCurrentSelectableValues()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("function restoreSelectValueIfSelectable", js);
            Assert.Contains("const generateModelValue = el.modelSelect && el.modelSelect.value;", js);
            Assert.Contains("const studioModelValue = el.studioModelSelect && el.studioModelSelect.value;", js);
            Assert.Contains("restoreSelectValueIfSelectable(el.modelSelect, generateModelValue);", js);
            Assert.Contains("restoreSelectValueIfSelectable(el.studioModelSelect, studioModelValue);", js);
        }

        [Fact]
        public void AppJs_GalleryToolbar_OpensArtifactsFolder()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("async function openArtifactsFolder()", js);
            Assert.Contains("bridgeCall(\"open_artifacts_folder\", {})", js);
            Assert.Contains("el.openArtifactsFolderBtn.addEventListener(\"click\", openArtifactsFolder);", js);
        }

        [Fact]
        public void AppJs_ModalRevealButton_RevealsCurrentArtifactRole()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("let modalDisplayRole = null;", js);
            Assert.Contains("modalDisplayRole = pickDisplayRole(modalArtifact);", js);
            Assert.Contains("async function revealCurrentArtifact()", js);
            Assert.Contains("bridgeCall(\"reveal_artifact_file\"", js);
            Assert.Contains("role: modalDisplayRole", js);
            Assert.Contains("el.modalRevealBtn = $(\"modal-reveal-btn\");", js);
            Assert.Contains("el.modalRevealBtn.addEventListener(\"click\", revealCurrentArtifact);", js);
        }

        [Fact]
        public void AppJs_PreventsDefaultImageContextMenu()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("document.addEventListener(\"contextmenu\"", js);
            Assert.Contains("e.target.closest(\"img\")", js);
            Assert.Contains("e.preventDefault();", js);
        }

        [Fact]
        public void AppJs_UpdatesPreviewFrameFromImageAndAspectSelection()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("function applyImageAspect", js);
            Assert.Contains("function applySelectedOutputAspect", js);
            Assert.Contains("function parseRatio", js);
            Assert.Contains("--preview-width-cap", js);
            Assert.Contains("removeProperty(\"--preview-width-cap\")", js);
        }

        [Fact]
        public void AppJs_CaptureViewport_TracksSelectedViewDimensions()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("viewportOptionsByValue.set", js);
            Assert.Contains("const selectedViewport = viewportOptionsByValue.get(selectedKey)", js);
            Assert.Contains("width: Number(v.width)", js);
            Assert.Contains("height: Number(v.height)", js);
            Assert.DoesNotContain("args.width = selectedViewport.width;", js);
            Assert.DoesNotContain("args.height = selectedViewport.height;", js);
        }

        [Fact]
        public void AppJs_CaptureViewport_UsesOpenViewIdsForViewportOptions()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("const optionValue = `view:${v.id}`;", js);
            Assert.Contains("viewId: v.id", js);
            Assert.Contains("if (selectedViewport.viewId) args.view_id = selectedViewport.viewId;", js);
            Assert.Contains("if (selectedViewport.viewName) args.view_name = selectedViewport.viewName;", js);
            Assert.DoesNotContain("if (viewName) args.view_name = viewName;", js);
        }

        [Fact]
        public void AppJs_CaptureViewport_UsesTransientPreviewOp()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("bridgeCall(\"preview_viewport\", args)", js);
            Assert.Contains("capture.preview_url", js);
            Assert.DoesNotContain("bridgeCall(\"capture_viewport\", args)", js);
        }

        [Fact]
        public void AppJs_CaptureViewport_StoresEachOpenViewportOwnDimensions()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("width: Number(v.width)", js);
            Assert.Contains("height: Number(v.height)", js);
            Assert.DoesNotContain("viewportOptionsByValue.set(v.name || \"\", activeCaptureSize)", js);
        }

        [Fact]
        public void AppJs_GeneratePreview_DoesNotResizeContainingBoxToImageAspect()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("Generate preview box stays fixed", js);
            Assert.DoesNotContain("applyImageAspect(el.previewContainer, el.previewImage)", js);
        }

        [Fact]
        public void StylesCss_StudioPreviewFrame_AllowsExtremeRatios()
        {
            var css = ReadVisionResource("styles.css");
            Assert.Contains("max-width: min(100%, var(--preview-width-cap, 100%));", css);
            Assert.DoesNotContain("max-height: 520px;", css);
            Assert.DoesNotContain("min-height: 300px;\r\n    display: flex;\r\n    align-items: center;\r\n    justify-content: center;\r\n}", css);
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

        // ─── GuessBlobContentType (PR-V3 MIME map) ────────────────────

        [Theory]
        [InlineData("/x/y/foo.png", "image/png")]
        [InlineData("/x/y/foo.jpg", "image/jpeg")]
        [InlineData("/x/y/foo.jpeg", "image/jpeg")]
        [InlineData("/x/y/foo.webp", "image/webp")]
        [InlineData("/x/y/foo.gif", "image/gif")]
        [InlineData("/x/y/foo.bmp", "image/bmp")]
        // PR-V3 additions — without these, generated_video blobs would
        // be served as application/octet-stream and <video> would refuse
        // to play them even with media-src 'self' in the CSP.
        [InlineData("/x/y/foo.mp4", "video/mp4")]
        [InlineData("/x/y/foo.mov", "video/quicktime")]
        [InlineData("/x/y/foo.webm", "video/webm")]
        // Case-insensitive on the extension (the helper lowercases).
        [InlineData("/x/y/FOO.MP4", "video/mp4")]
        [InlineData("/x/y/FOO.MOV", "video/quicktime")]
        [InlineData("/x/y/Foo.WebM", "video/webm")]
        [InlineData("/x/y/foo.json", "application/json; charset=utf-8")]
        [InlineData("/x/y/foo.txt", "text/plain; charset=utf-8")]
        [InlineData("/x/y/foo.bin", "application/octet-stream")]
        [InlineData("/x/y/no-extension", "application/octet-stream")]
        public void GuessBlobContentType_MapsExtensionsCorrectly(string path, string expected)
        {
            Assert.Equal(expected, VisionWebSurface.GuessBlobContentType(path));
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

        [Theory]
        [InlineData("https://app.rook.invalid/viewport-preview/viewport_20260424_101501_123.png", true)]
        [InlineData("https://app.rook.invalid/viewport-preview", true)]
        [InlineData("https://app.rook.invalid/viewport-preview/", true)]
        [InlineData("https://app.rook.invalid/viewport-preview/../x.png", false)]
        [InlineData("https://app.rook.invalid/viewport-previews/viewport_20260424_101501_123.png", false)]
        public void IsViewportPreviewPath_DetectsShape(string url, bool expected)
        {
            Assert.Equal(expected, VisionWebSurface.IsViewportPreviewPath(new Uri(url)));
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

        [Fact]
        public void TryParseViewportPreviewUri_ValidShape_ReturnsFilename()
        {
            var ok = VisionWebSurface.TryParseViewportPreviewUri(
                new Uri("https://app.rook.invalid/viewport-preview/viewport_20260424_101501_123.png"),
                out var fileName);

            Assert.True(ok);
            Assert.Equal("viewport_20260424_101501_123.png", fileName);
        }

        [Theory]
        [InlineData("https://app.rook.invalid/viewport-preview")]
        [InlineData("https://app.rook.invalid/viewport-preview/not-a-viewport.png")]
        [InlineData("https://app.rook.invalid/viewport-preview/viewport_20260424_101501_123.jpg")]
        [InlineData("https://app.rook.invalid/viewport-preview/../viewport_20260424_101501_123.png")]
        public void TryParseViewportPreviewUri_InvalidShape_Fails(string url)
        {
            Assert.False(VisionWebSurface.TryParseViewportPreviewUri(
                new Uri(url), out _));
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
        [InlineData("foo.mov", "video/quicktime")]
        [InlineData("foo.MOV", "video/quicktime")]
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

        private static string ReadVisionResource(string fileName)
        {
            var asm = typeof(VisionWebSurface).Assembly;
            var resourceName = "Rook.UI.Vision.Resources." + fileName;
            using var stream = asm.GetManifestResourceStream(resourceName);
            Assert.NotNull(stream);
            using var reader = new StreamReader(stream!);
            return reader.ReadToEnd();
        }

        private static int CountOccurrences(string haystack, string needle)
        {
            int count = 0;
            int index = 0;
            while ((index = haystack.IndexOf(needle, index, StringComparison.Ordinal)) >= 0)
            {
                count++;
                index += needle.Length;
            }
            return count;
        }

        private static string RepoRoot
            => Path.GetFullPath(Path.Combine(System.AppContext.BaseDirectory, "..", "..", "..", "..", ".."));

        [Fact]
        public void ReconstructionAsyncOps_AreExactly_Submit_Status_Cancel_Import_RemoveBackground()
        {
            // import_package loops back to the native importer; it MUST be async/off-UI
            // (the deadlock invariant) on this surface. remove_background is a network-bound
            // Fal job submit and is routed through the same async/timeout wrapper as submit_job.
            Assert.Equal(
                new[] { "cancel_job", "import_package", "job_status", "remove_background", "submit_job" },
                VisionWebSurface.ReconstructionAsyncOps.OrderBy(o => o, StringComparer.Ordinal).ToArray());
        }

        [Fact]
        public void ReconstructionAsyncOps_ExcludeOffUiOps()
        {
            Assert.DoesNotContain("models", VisionWebSurface.ReconstructionAsyncOps);
            Assert.DoesNotContain("list_jobs", VisionWebSurface.ReconstructionAsyncOps);
            Assert.DoesNotContain("job_result", VisionWebSurface.ReconstructionAsyncOps);
        }

        [Fact]
        public void HandleReconstructionBridge_RoutesAsyncOpsThroughTimeoutWrapper()
        {
            // The set must actually drive the timeout wrapper — pin the wiring in
            // source so a future edit that bypasses ReconstructionAsyncOps or
            // DispatchWithTimeoutAsync fails here, not silently in production.
            var source = File.ReadAllText(Path.Combine(
                RepoRoot, "src", "Rook", "UI", "Vision", "VisionWebSurface.cs"));
            // Anchor on the method DEFINITION, not the earlier
            // RegisterBridgeHandler(...) reference to the same name.
            var start = source.IndexOf(
                "private async Task<JsonNode?> HandleReconstructionBridgeCallAsync",
                StringComparison.Ordinal);
            Assert.True(start >= 0, "HandleReconstructionBridgeCallAsync definition not found.");
            var bodyStart = source.IndexOf('{', start);
            var next = source.IndexOf("\n        private ", bodyStart, StringComparison.Ordinal);
            var method = next > bodyStart
                ? source.Substring(bodyStart, next - bodyStart)
                : source.Substring(bodyStart);

            Assert.Contains("ReconstructionAsyncOps.Contains(op)", method);
            Assert.Contains("DispatchWithTimeoutAsync(", method);
            Assert.Contains("domainLabel: \"Reconstruction\"", method);
        }

        [Fact]
        public async Task DispatchWithTimeout_ReconstructionLabel_EmitsReconstructionTimeoutMessage()
        {
            var response = await VisionWebSurface.DispatchWithTimeoutAsync(
                "submit_job",
                TimeSpan.FromMilliseconds(30),
                async token =>
                {
                    await Task.Delay(TimeSpan.FromSeconds(2), token).ConfigureAwait(false);
                    return new ApiResponse { Success = true };
                },
                domainLabel: "Reconstruction");

            Assert.False(response.Success);
            var message = Assert.IsType<string>(response.Data);
            Assert.Contains("Reconstruction op 'submit_job' timed out", message, StringComparison.Ordinal);
            Assert.DoesNotContain("Vision op", message);
        }
    }
}
