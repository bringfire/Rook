using System;
using System.Linq;
using System.Reflection;
using Rook;
using Rook.Handlers;
using Rook.InternalBridge;
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
        public void ExpectedVisionOps_HasExactly15Ops()
        {
            // Pinned count: 8 image + 5 V2 video + 2 V4 video list ops.
            // If this drifts, either a new op landed (update both the
            // count and the per-op test above) or one was removed
            // (intentional retirement).
            Assert.Equal(15, NativeGhBridgeRegistrar.ExpectedVisionOps.Count);
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
        public void Registrar_VisionHandler_UsesSharedSecretStore()
        {
            // Pin: same VisionSecretStore instance across registrar
            // (native HTTP) + VisionWebSurface (tab bridge). Without
            // this, a user setting the API key in the tab is invisible
            // to the native HTTP path on its next provider call.
            var visionField = typeof(NativeGhBridgeRegistrar).GetField(
                "Vision",
                BindingFlags.Static | BindingFlags.NonPublic);
            Assert.NotNull(visionField);
            var vision = (VisionHandler)visionField!.GetValue(null)!;

            var secretsField = typeof(VisionHandler).GetField(
                "_secrets",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(secretsField);
            var actual = secretsField!.GetValue(vision);

            Assert.Same(RookSubsystemRoot.Instance.SharedSecretStore, actual);
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
