using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using System.Text.Json.Nodes;
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
                "list_views", "open_image_picker",
                "list_artifacts", "get_artifact", "approve_artifact",
                "delete_artifact", "consume_approved",
                "set_api_key", "get_settings_overview",
                "set_provider_secret", "test_provider_secret",
                "clear_provider_secret", "list_image_models",
                "open_artifacts_folder", "reveal_artifact_file",
                // V2 video — bridge mirrors of the native HTTP routes.
                "submit_video_job", "cancel_video_job",
                "get_video_job", "get_video_job_result",
                "estimate_video_job",
                // V3 video — bridge-only (NOT in native trampoline).
                "list_video_jobs", "list_video_models",
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
        [InlineData("open_image_picker", "Ui")]
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
        [InlineData("/x/y/foo.webm", "video/webm")]
        // Case-insensitive on the extension (the helper lowercases).
        [InlineData("/x/y/FOO.MP4", "video/mp4")]
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
    }
}
