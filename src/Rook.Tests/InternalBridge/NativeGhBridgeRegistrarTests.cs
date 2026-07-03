using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.RegularExpressions;
using Rook;
using Rook.Handlers;
using Rook.InternalBridge;
using Rook.Services.Vision;
using Xunit;

namespace Rook.Tests.InternalBridge
{
    public class NativeGhBridgeRegistrarTests
    {
        [Fact]
        public void MapBridgeStatus_NullHttpStatus_SuccessTrue_FallsBackTo200()
        {
            var result = new ApiResponse { Success = true, Data = "ok", HttpStatus = null };
            Assert.Equal(200, NativeGhBridgeRegistrar.MapBridgeStatus(result));
        }

        [Fact]
        public void MapBridgeStatus_NullHttpStatus_SuccessFalse_FallsBackTo400()
        {
            var result = new ApiResponse { Success = false, Data = "bad", HttpStatus = null };
            Assert.Equal(400, NativeGhBridgeRegistrar.MapBridgeStatus(result));
        }

        [Fact]
        public void MapBridgeStatus_DefaultApiResponse_FallsBackTo400()
        {
            // Brand-new ApiResponse: Success defaults to false, HttpStatus
            // defaults to null. This is the legacy contract image-side
            // handlers depend on; pinned so it cannot regress.
            Assert.Equal(400, NativeGhBridgeRegistrar.MapBridgeStatus(new ApiResponse()));
        }

        [Fact]
        public void QueryDocumentForBridge_NotReady_ReturnsStructuredFailure()
        {
            var result = NativeGhBridgeRegistrar.QueryDocumentForBridge("{}");

            AssertGrasshopperNotReady(result, "gh_query");
        }

        [Fact]
        public void DocumentForBridge_NotReady_DoesNotCreateDocument()
        {
            var result = NativeGhBridgeRegistrar.DocumentForBridge("{}");

            AssertGrasshopperNotReady(result, "gh_document");
        }

        [Fact]
        public void ErrorsForBridge_NotReady_ReturnsStructuredFailure()
        {
            var result = NativeGhBridgeRegistrar.ErrorsForBridge("{}");

            AssertGrasshopperNotReady(result, "gh_errors");
        }

        [Fact]
        public void CreatePanelForBridge_NotReady_ReturnsStructuredFailure()
        {
            var result = NativeGhBridgeRegistrar.CreatePanelForBridge("{}");

            AssertGrasshopperNotReady(result, "gh_create_panel");
        }

        [Fact]
        public void CreateSliderForBridge_NotReady_ReturnsStructuredFailure()
        {
            var result = NativeGhBridgeRegistrar.CreateSliderForBridge("{}");

            AssertGrasshopperNotReady(result, "gh_create_slider");
        }

        [Fact]
        public void ConnectForBridge_NotReady_ReturnsStructuredFailure()
        {
            var result = NativeGhBridgeRegistrar.ConnectForBridge("{}");

            AssertGrasshopperNotReady(result, "gh_connect");
        }

        [Fact]
        public void SetValueForBridge_NotReady_ReturnsStructuredFailure()
        {
            var result = NativeGhBridgeRegistrar.SetValueForBridge("{}");

            AssertGrasshopperNotReady(result, "gh_set_value");
        }

        [Fact]
        public void GrasshopperHandler_BareGetGrasshopperCalls_AreLimitedToLifecycleRoutes()
        {
            var sourcePath = Path.GetFullPath(Path.Combine(
                AppContext.BaseDirectory,
                "..",
                "..",
                "..",
                "..",
                "Rook",
                "Handlers",
                "GrasshopperHandler.cs"));
            var source = File.ReadAllText(sourcePath);
            var bareCalls = Regex.Matches(source, @"GetGrasshopper\(\)")
                .Cast<Match>()
                .Select(match => new
                {
                    Method = FindContainingMethodName(source, match.Index),
                    Line = source.Take(match.Index).Count(ch => ch == '\n') + 1,
                })
                .ToArray();

            var actualMethods = bareCalls.Select(call => call.Method).ToHashSet();
            var expectedMethods = new[] { "OpenDocument", "NewDocument" }.ToHashSet();
            var callSummary = string.Join(
                ", ",
                bareCalls.Select(call => $"{call.Method}:L{call.Line}"));

            Assert.True(
                expectedMethods.SetEquals(actualMethods),
                $"Bare GetGrasshopper() calls must stay limited to lifecycle routes. Found: {callSummary}");
        }

        private static void AssertGrasshopperNotReady(ApiResponse result, string operation)
        {
            Assert.False(result.Success);
            Assert.NotNull(result.Data);

            var dataType = result.Data!.GetType();
            Assert.Equal(
                "grasshopper_not_ready",
                dataType.GetProperty("error")?.GetValue(result.Data));
            Assert.Equal(
                false,
                dataType.GetProperty("ready_for_edit")?.GetValue(result.Data));
            Assert.Equal(
                false,
                dataType.GetProperty("verified")?.GetValue(result.Data));
            Assert.Equal(
                operation,
                dataType.GetProperty("operation")?.GetValue(result.Data));
            Assert.NotNull(dataType.GetProperty("errors")?.GetValue(result.Data));
            Assert.NotNull(dataType.GetProperty("message")?.GetValue(result.Data));
            Assert.NotNull(dataType.GetProperty("verification_note")?.GetValue(result.Data));
            Assert.NotNull(dataType.GetProperty("status")?.GetValue(result.Data));
        }

        private static string FindContainingMethodName(string source, int index)
        {
            var beforeCall = source.Substring(0, index);
            var matches = Regex.Matches(
                beforeCall,
                @"(?:public|private|internal)\s+[^\r\n{;=]+?\s+(?<name>[A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*\{",
                RegexOptions.Singleline);

            return matches.Count == 0
                ? "<unknown>"
                : matches[matches.Count - 1].Groups["name"].Value;
        }

        private static string FindRepoRoot()
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir is not null)
            {
                if (File.Exists(Path.Combine(dir.FullName, "Rook.sln")))
                    return dir.FullName;
                dir = dir.Parent;
            }
            throw new DirectoryNotFoundException("Could not locate Rook.sln from test output directory.");
        }

        private static string ExtractSwitchArm(string source, string caseLabel)
        {
            var caseIndex = source.IndexOf(caseLabel, StringComparison.Ordinal);
            Assert.True(caseIndex >= 0, $"Could not find switch case: {caseLabel}");

            var nextCaseIndex = source.IndexOf("\n                case ", caseIndex + caseLabel.Length, StringComparison.Ordinal);
            Assert.True(nextCaseIndex > caseIndex, $"Could not find switch case after: {caseLabel}");

            return source.Substring(caseIndex, nextCaseIndex - caseIndex);
        }

        [Theory]
        [InlineData(415)]
        [InlineData(500)]
        [InlineData(503)]
        public void MapBridgeStatus_FailureWithExplicitStatus_HonorsHttpStatus(int explicitStatus)
        {
            var result = new ApiResponse
            {
                Success = false,
                Data = "typed error",
                HttpStatus = explicitStatus,
            };
            Assert.Equal(explicitStatus, NativeGhBridgeRegistrar.MapBridgeStatus(result));
        }

        [Theory]
        [InlineData(200)]
        [InlineData(202)]
        public void MapBridgeStatus_SuccessWithExplicitStatus_HonorsHttpStatus(int explicitStatus)
        {
            // Video Cancelled / Interrupted are terminal-state reads that
            // return Success=true with state metadata in Data. The typed
            // override path must work in either direction (success and
            // failure) so a future caller setting a non-200 success code
            // is not silently downgraded.
            var result = new ApiResponse
            {
                Success = true,
                Data = "ok with explicit status",
                HttpStatus = explicitStatus,
            };
            Assert.Equal(explicitStatus, NativeGhBridgeRegistrar.MapBridgeStatus(result));
        }

        // (Step 8 cleanup) Removed MapBridgeStatus_NullResponse_Returns500.
        // The helper's defensive null guard was unreachable: production
        // callers (the async and off-UI executors) read result.Success
        // for the JSON envelope before invoking the helper. The helper
        // is now tightened; a regression that introduces a null path
        // would NRE earlier and surface as a generic 500 via the
        // executors' outer exception handler.

        // ─── ExpectedVisionOps ───────────────────────────────────────────

        [Theory]
        [InlineData("capture_depth")]
        [InlineData("generate")]
        [InlineData("enhance_prompt")]
        [InlineData("list_artifacts")]
        [InlineData("get_artifact")]
        [InlineData("approve_artifact")]
        [InlineData("delete_artifact")]
        [InlineData("consume_approved")]
        public void ExpectedVisionOps_ContainsAllImageOps(string op)
        {
            // Regression — image ops must continue to route after V2.
            Assert.Contains(op, NativeGhBridgeRegistrar.ExpectedVisionOps);
        }

        [Theory]
        [InlineData(VideoOpHandler.OpSubmit)]
        [InlineData(VideoOpHandler.OpStatus)]
        [InlineData(VideoOpHandler.OpCancel)]
        [InlineData(VideoOpHandler.OpResult)]
        [InlineData(VideoOpHandler.OpEstimate)]
        public void ExpectedVisionOps_ContainsAllV2VideoOps(string op)
        {
            // Pin the five V2 video ops are wired in. If the trampoline
            // switch adds a video op without updating ExpectedVisionOps,
            // the unknown-op rejection message would silently omit it
            // (and an integration test would catch it later, expensively).
            Assert.Contains(op, NativeGhBridgeRegistrar.ExpectedVisionOps);
        }

        [Theory]
        [InlineData(VideoOpHandler.OpListJobs)]
        [InlineData(VideoOpHandler.OpListModels)]
        public void ExpectedVisionOps_ContainsV4VideoListOps(string op)
        {
            // V4 promoted the two list ops from bridge-only (V3) to
            // native HTTP. They route through DispatchOffUi alongside
            // status/result/estimate. If a future PR removes them
            // without updating this test, agent-direct + curl access
            // would silently break.
            Assert.Contains(op, NativeGhBridgeRegistrar.ExpectedVisionOps);
        }

        [Fact]
        public void ExpectedVisionOps_ContainsDirectorPublishVideo()
        {
            Assert.Contains("publish_director_video", NativeGhBridgeRegistrar.ExpectedVisionOps);
        }

        [Theory]
        [InlineData("get_presentation_diagnostics")]
        [InlineData("repair_presentation")]
        public void ExpectedVisionOps_ContainsPresentationOps(string op)
        {
            // Presentation reconciler (spec 2026-06-10): typed dump/repair
            // ops reachable via POST /vision/presentation. Native
            // constructs the op bodies itself; the trampoline routes both
            // through the UI-thread dispatcher alongside capture_depth.
            Assert.Contains(op, NativeGhBridgeRegistrar.ExpectedVisionOps);
        }

        [Fact]
        public void ExpectedVisionOps_HasExactly18Ops()
        {
            // Pinned count: 8 image + 1 Director publish + 5 V2 video
            // + 2 V4 video list ops + 2 presentation ops.
            // If this drifts, either a new op landed (update both the
            // count and the per-op test above) or one was removed
            // (intentional retirement).
            Assert.Equal(18, NativeGhBridgeRegistrar.ExpectedVisionOps.Count);
        }

        [Fact]
        public void VisionDispatch_RoutesDirectorPublishVideoThroughOffUi()
        {
            var source = File.ReadAllText(Path.Combine(FindRepoRoot(), "src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs"));
            var publishArm = ExtractSwitchArm(source, "case \"publish_director_video\":");

            Assert.Contains("return ExecuteOffUiApiResponseCallback(", publishArm);
            Assert.Contains("reqJson => Vision.DispatchOffUi(reqJson)", publishArm);
            Assert.Contains("timeoutSeconds: 180", publishArm);
            Assert.DoesNotContain("_videoOpHandler", publishArm);
            Assert.DoesNotContain("ExecuteAsyncApiResponseCallback", publishArm);
        }

        [Fact]
        public void Registrar_DeclaresCanvasDirectorDispatchCallback()
        {
            var source = File.ReadAllText(Path.Combine(FindRepoRoot(), "src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs"));

            Assert.Contains("CanvasDirectorDispatchCallback", source);
            Assert.Contains("HandleCanvasDirectorDispatch", source);
            Assert.Contains("public IntPtr CanvasDirectorDispatch;", source);
            Assert.Contains("CanvasDirectorDispatch = Marshal.GetFunctionPointerForDelegate(CanvasDirectorDispatchCallback)", source);

            var syncStart = source.IndexOf("private static int ExecuteApiResponseCallback", StringComparison.Ordinal);
            var nextFunction = source.IndexOf("private static uint? ParseDocumentSerialNumber", syncStart, StringComparison.Ordinal);
            var syncExecutor = source.Substring(syncStart, nextFunction - syncStart);
            Assert.Contains("statusCode = MapBridgeStatus(result);", syncExecutor);
            Assert.DoesNotContain("statusCode = result.Success ? 200 : 400;", syncExecutor);
            Assert.Contains("timeoutErrorCode", syncExecutor);
            Assert.Contains("solve_timeout", source);
        }

        [Theory]
        [InlineData("set_provider_secret")]
        [InlineData("test_provider_secret")]
        [InlineData("clear_provider_secret")]
        [InlineData("list_image_models")]
        public void ExpectedVisionOps_DoesNotExposeProviderSettingsOps(string op)
        {
            Assert.DoesNotContain(op, NativeGhBridgeRegistrar.ExpectedVisionOps);
        }

        // ─── BuildUnknownOpMessage ───────────────────────────────────────

        [Fact]
        public void BuildUnknownOpMessage_NullOp_ReturnsMissingDiscriminator()
        {
            var msg = NativeGhBridgeRegistrar.BuildUnknownOpMessage(null);
            Assert.Contains("missing required 'op'", msg);
        }

        [Fact]
        public void BuildUnknownOpMessage_EmptyOp_ReturnsMissingDiscriminator()
        {
            var msg = NativeGhBridgeRegistrar.BuildUnknownOpMessage(string.Empty);
            Assert.Contains("missing required 'op'", msg);
        }

        [Fact]
        public void BuildUnknownOpMessage_UnknownOp_QuotesOpAndListsAllExpected()
        {
            var msg = NativeGhBridgeRegistrar.BuildUnknownOpMessage("frobnicate");

            Assert.Contains("'frobnicate'", msg);
            // Every expected op must appear in the message — the rule
            // that prevents drift between the switch and the rejection
            // message. The message is sorted ordinal so its content is
            // deterministic regardless of HashSet iteration order.
            foreach (var expected in NativeGhBridgeRegistrar.ExpectedVisionOps)
            {
                Assert.Contains($"'{expected}'", msg);
            }
        }

        // ─── Shared-singleton wiring (Codex step 7 follow-up) ────────────

        [Fact]
        public void Registrar_VisionHandler_UsesSharedArtifactStore()
        {
            // Mirrors VisionWebSurface's reflection pin. The native HTTP
            // image-side path (vision_dispatch → Vision.Dispatch /
            // DispatchAsync / DispatchOffUi) MUST go through the same
            // ArtifactStore instance as the tab and the V2 video
            // subsystem. A regression to fresh stores would silently
            // split in-memory artifact state across the two transports.
            var visionField = typeof(NativeGhBridgeRegistrar).GetField(
                "Vision",
                BindingFlags.Static | BindingFlags.NonPublic);
            Assert.NotNull(visionField);
            var vision = (VisionHandler)visionField!.GetValue(null)!;
            Assert.NotNull(vision);

            var artifactStoreField = typeof(VisionHandler).GetField(
                "_artifactStore",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(artifactStoreField);
            var actual = artifactStoreField!.GetValue(vision);

            Assert.Same(RookSubsystemRoot.Instance.SharedArtifactStore, actual);
        }

        [Fact]
        public void Registrar_VisionHandler_UsesSecretStoreShimBackedBySharedGenerationSecretStore()
        {
            // VisionSecretStore remains as the compatibility facade for
            // prompt/settings code, but the shared identity now lives in
            // the keyed IGenerationSecretStore under the shim.
            var visionField = typeof(NativeGhBridgeRegistrar).GetField(
                "Vision",
                BindingFlags.Static | BindingFlags.NonPublic);
            Assert.NotNull(visionField);
            var vision = (VisionHandler)visionField!.GetValue(null)!;

            var secretsField = typeof(VisionHandler).GetField(
                "_secrets",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(secretsField);
            var shim = Assert.IsType<VisionSecretStore>(secretsField!.GetValue(vision));
            var generationField = typeof(VisionSecretStore).GetField(
                "_generationSecrets",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(generationField);

            Assert.Same(
                RookSubsystemRoot.Instance.SharedGenerationSecretStore,
                generationField!.GetValue(shim));
        }

        [Fact]
        public void Registrar_VisionHandler_UsesSharedGenerationSecretStore()
        {
            // Same invariant as the legacy VisionSecretStore pin, now
            // retargeted to the PR-4 keyed secret store. Native HTTP and
            // the tab must share this exact instance so set/test/use
            // paths see one credential source.
            var visionField = typeof(NativeGhBridgeRegistrar).GetField(
                "Vision",
                BindingFlags.Static | BindingFlags.NonPublic);
            Assert.NotNull(visionField);
            var vision = (VisionHandler)visionField!.GetValue(null)!;

            var secretsField = typeof(VisionHandler).GetField(
                "_generationSecrets",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(secretsField);
            var actual = secretsField!.GetValue(vision);

            Assert.Same(RookSubsystemRoot.Instance.SharedGenerationSecretStore, actual);
        }

        [Fact]
        public void BuildUnknownOpMessage_ListsExpectedOpsInOrdinalOrder()
        {
            // The message orders the expected list ordinal-ascending so
            // the output is stable for snapshotting / diffing. Pin the
            // ordering rule explicitly.
            var msg = NativeGhBridgeRegistrar.BuildUnknownOpMessage("x");

            var ordered = NativeGhBridgeRegistrar.ExpectedVisionOps
                .OrderBy(s => s, System.StringComparer.Ordinal)
                .ToArray();

            int lastIdx = -1;
            foreach (var op in ordered)
            {
                var idx = msg.IndexOf($"'{op}'", System.StringComparison.Ordinal);
                Assert.True(idx > lastIdx,
                    $"op '{op}' should appear after '{ordered[System.Math.Max(0, System.Array.IndexOf(ordered, op) - 1)]}'");
                lastIdx = idx;
            }
        }
    }
}
