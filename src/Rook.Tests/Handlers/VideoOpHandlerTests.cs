using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Vision;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Handlers
{
    /// <summary>
    /// Unit tests for the V2 video handler. Covers per-op happy paths,
    /// the per-error HTTP-status mapping (the load-bearing piece for
    /// native HTTP semantics), and the path-kind rejection at the
    /// adapter boundary. The full E2E story (native trampoline →
    /// vision_dispatch → handler) lands in step 8; these tests pin
    /// handler-level invariants in isolation against a stub manager.
    /// </summary>
    public class VideoOpHandlerTests
    {
        private static readonly Guid SampleArtifactId =
            Guid.Parse("11111111-1111-1111-1111-111111111111");
        private static readonly Guid SampleJobId =
            Guid.Parse("22222222-2222-2222-2222-222222222222");
        private static readonly Guid SampleResultArtifactId =
            Guid.Parse("33333333-3333-3333-3333-333333333333");

        // ─── DispatchAsync error-path tests ──────────────────────────────

        [Fact]
        public async Task DispatchAsync_NullBody_FailsInvalidRequest()
        {
            var handler = NewHandler();
            var resp = await handler.DispatchAsync(null);

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
        }

        [Fact]
        public async Task DispatchAsync_EmptyBody_FailsInvalidRequest_MissingOp()
        {
            var handler = NewHandler();
            var resp = await handler.DispatchAsync("{}");

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertMessageContains(resp, "op");
        }

        [Fact]
        public async Task DispatchAsync_MalformedJson_FailsInvalidRequest()
        {
            var handler = NewHandler();
            var resp = await handler.DispatchAsync("{not json");

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
        }

        [Fact]
        public async Task DispatchAsync_UnknownOp_FailsInvalidRequest()
        {
            var handler = NewHandler();
            var resp = await handler.DispatchAsync("""{"op":"frobnicate"}""");

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertMessageContains(resp, "frobnicate");
        }

        [Theory]
        [InlineData("get_video_job")]
        [InlineData("get_video_job_result")]
        [InlineData("estimate_video_job")]
        public async Task DispatchAsync_OffUiOps_RejectedAsWrongDispatcher(string op)
        {
            var handler = NewHandler();
            var resp = await handler.DispatchAsync($$"""{"op":"{{op}}"}""");

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertMessageContains(resp, "off-UI");
        }

        // ─── DispatchOffUi error-path tests ──────────────────────────────

        [Theory]
        [InlineData("submit_video_job")]
        [InlineData("cancel_video_job")]
        public void DispatchOffUi_AsyncOps_RejectedAsWrongDispatcher(string op)
        {
            var handler = NewHandler();
            var resp = handler.DispatchOffUi($$"""{"op":"{{op}}"}""");

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertMessageContains(resp, "async");
        }

        [Fact]
        public void DispatchOffUi_UnknownOp_FailsInvalidRequest()
        {
            var handler = NewHandler();
            var resp = handler.DispatchOffUi("""{"op":"unknown_video_op"}""");

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
        }

        // ─── Submit ──────────────────────────────────────────────────────

        [Fact]
        public async Task Submit_HappyPath_ReturnsJobIdAndState()
        {
            var stub = new StubManager
            {
                SubmitImpl = (_, _) => JobSubmitResult.Ok(SampleJobId, VideoJobState.Queued),
            };
            var handler = NewHandler(stub);

            var resp = await handler.DispatchAsync(BuildSubmitBody());

            AssertOk(resp, expectedHttp: 200);
            var data = AssertDataDict(resp);
            Assert.Equal(SampleJobId.ToString("D"), data["job_id"]);
            Assert.Equal("queued", data["state"]);
        }

        [Fact]
        public async Task Submit_PathKindMediaRef_RejectedAtAdapter()
        {
            // V2 boundary: HTTP submit accepts artifact_id only. A path-
            // kind ref MUST be rejected before reaching the manager —
            // unauthenticated native HTTP cannot accept arbitrary
            // local paths. Per scope v3 §4 the rejection error MUST
            // surface field:"kind" exactly (not dotted) so caller
            // diagnostics match the contract.
            var stub = new StubManager(); // never called
            var handler = NewHandler(stub);

            var body = """
                {
                  "op": "submit_video_job",
                  "model": "veo-3.1-lite-generate-preview",
                  "mode": "i2v",
                  "duration_seconds": 8,
                  "resolution": "720p",
                  "aspect_ratio": "16:9",
                  "prompt": "x",
                  "start_frame": { "kind": "path", "path": "C:\\image.png", "role": "image" },
                  "options": { "person_generation": "allow_all" },
                  "number_of_videos": 1
                }
                """;

            var resp = await handler.DispatchAsync(body);

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertFieldEquals(resp, "kind");
            AssertMessageContains(resp, "Path media refs are not supported");
            Assert.Equal(0, stub.SubmitCallCount);
        }

        [Fact]
        public void Estimate_PathKindMediaRef_RejectedAtAdapter()
        {
            // Mirror of the submit-side rejection. Estimate also rejects
            // path refs at the same boundary; the contract is symmetric
            // per v3 (both submit and estimate route through the same
            // ParseGenerationRequest).
            var registry = TestVideoFixtures.RegistryWithVeo();
            var handler = new VideoOpHandler(
                manager: new StubManager(),
                registry: registry,
                estimator: new VideoCostEstimator());

            var body = """
                {
                  "op": "estimate_video_job",
                  "model": "veo-3.1-lite-generate-preview",
                  "mode": "i2v",
                  "duration_seconds": 8,
                  "resolution": "720p",
                  "aspect_ratio": "16:9",
                  "prompt": "x",
                  "start_frame": { "kind": "path", "path": "C:\\frame.png", "role": "image" },
                  "options": { "person_generation": "allow_all" },
                  "number_of_videos": 1
                }
                """;

            var resp = handler.DispatchOffUi(body);

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertFieldEquals(resp, "kind");
            AssertMessageContains(resp, "Path media refs are not supported");
        }

        [Fact]
        public async Task Submit_UnknownMediaKind_Rejected()
        {
            var handler = NewHandler();
            var body = """
                {
                  "op": "submit_video_job",
                  "model": "veo-3.1-lite-generate-preview",
                  "mode": "t2v",
                  "duration_seconds": 8,
                  "resolution": "720p",
                  "aspect_ratio": "16:9",
                  "prompt": "x",
                  "start_frame": { "kind": "url", "artifact_id": "https://x", "role": "image" },
                  "options": { "person_generation": "allow_all" },
                  "number_of_videos": 1
                }
                """;

            var resp = await handler.DispatchAsync(body);

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertFieldEquals(resp, "start_frame.kind");
        }

        [Fact]
        public async Task Submit_StartFrameArtifactRef_HappyPath()
        {
            // v3 contract shape: {kind:"artifact_id", artifact_id:"<uuid>",
            // role:"<role>"}. Pin the artifact id round-trips through
            // ParseMediaRef into a real VideoMediaRef.ForArtifact(...)
            // call by checking the manager observed it.
            VideoGenerationRequest? captured = null;
            var stub = new StubManager
            {
                SubmitImpl = (req, _) =>
                {
                    captured = req;
                    return JobSubmitResult.Ok(SampleJobId, VideoJobState.Queued);
                },
            };
            var handler = NewHandler(stub);

            var body = $$"""
                {
                  "op": "submit_video_job",
                  "model": "veo-3.1-lite-generate-preview",
                  "mode": "i2v",
                  "duration_seconds": 8,
                  "resolution": "720p",
                  "aspect_ratio": "16:9",
                  "prompt": "x",
                  "start_frame": {
                    "kind": "artifact_id",
                    "artifact_id": "{{SampleArtifactId:D}}",
                    "role": "image"
                  },
                  "options": { "person_generation": "allow_all" },
                  "number_of_videos": 1
                }
                """;

            var resp = await handler.DispatchAsync(body);

            AssertOk(resp, expectedHttp: 200);
            Assert.NotNull(captured);
            Assert.NotNull(captured!.StartFrame);
            Assert.Equal(VideoMediaRefKind.Artifact, captured.StartFrame!.Kind);
            Assert.Equal(SampleArtifactId, captured.StartFrame.ArtifactId);
            Assert.Equal("image", captured.StartFrame.Role);
        }

        [Fact]
        public async Task Submit_EndFrameArtifactRef_HappyPath()
        {
            // Same shape, end_frame slot. Interp mode requires both
            // start_frame and end_frame, so this also pins the
            // capability validator can see both refs together.
            VideoGenerationRequest? captured = null;
            var endId = Guid.Parse("44444444-4444-4444-4444-444444444444");
            var stub = new StubManager
            {
                SubmitImpl = (req, _) =>
                {
                    captured = req;
                    return JobSubmitResult.Ok(SampleJobId, VideoJobState.Queued);
                },
            };
            var handler = NewHandler(stub);

            var body = $$"""
                {
                  "op": "submit_video_job",
                  "model": "veo-3.1-lite-generate-preview",
                  "mode": "interp",
                  "duration_seconds": 8,
                  "resolution": "720p",
                  "aspect_ratio": "16:9",
                  "prompt": "x",
                  "start_frame": {
                    "kind": "artifact_id",
                    "artifact_id": "{{SampleArtifactId:D}}"
                  },
                  "end_frame": {
                    "kind": "artifact_id",
                    "artifact_id": "{{endId:D}}",
                    "role": "image"
                  },
                  "options": { "person_generation": "allow_all" },
                  "number_of_videos": 1
                }
                """;

            var resp = await handler.DispatchAsync(body);

            AssertOk(resp, expectedHttp: 200);
            Assert.NotNull(captured);
            Assert.Equal(SampleArtifactId, captured!.StartFrame!.ArtifactId);
            Assert.Equal(endId, captured.EndFrame!.ArtifactId);
        }

        [Fact]
        public async Task Submit_ReferenceFramesArtifactRefs_HappyPath()
        {
            // Reference frames are an array of media refs. This fixture
            // uses the veo-3.1-generate-preview model which supports
            // reference images (the lite model does not).
            VideoGenerationRequest? captured = null;
            var refA = Guid.Parse("55555555-5555-5555-5555-555555555555");
            var refB = Guid.Parse("66666666-6666-6666-6666-666666666666");
            var stub = new StubManager
            {
                SubmitImpl = (req, _) =>
                {
                    captured = req;
                    return JobSubmitResult.Ok(SampleJobId, VideoJobState.Queued);
                },
            };
            var handler = NewHandler(stub);

            var body = $$"""
                {
                  "op": "submit_video_job",
                  "model": "veo-3.1-generate-preview",
                  "mode": "t2v",
                  "duration_seconds": 8,
                  "resolution": "720p",
                  "aspect_ratio": "16:9",
                  "prompt": "x",
                  "reference_frames": [
                    { "kind": "artifact_id", "artifact_id": "{{refA:D}}", "role": "reference" },
                    { "kind": "artifact_id", "artifact_id": "{{refB:D}}", "role": "reference" }
                  ],
                  "options": { "person_generation": "allow_all" },
                  "number_of_videos": 1
                }
                """;

            var resp = await handler.DispatchAsync(body);

            AssertOk(resp, expectedHttp: 200);
            Assert.NotNull(captured);
            Assert.Equal(2, captured!.ReferenceFrames!.Count);
            Assert.Equal(refA, captured.ReferenceFrames[0].ArtifactId);
            Assert.Equal(refB, captured.ReferenceFrames[1].ArtifactId);
        }

        [Fact]
        public async Task Submit_ArtifactRefMissingArtifactIdField_Rejected()
        {
            // Wire shape requires an artifact_id field; if missing or
            // not a GUID, surface InvalidRequest with field path
            // pointing at the bad subfield.
            var handler = NewHandler();
            var body = """
                {
                  "op": "submit_video_job",
                  "model": "veo-3.1-lite-generate-preview",
                  "mode": "i2v",
                  "duration_seconds": 8,
                  "resolution": "720p",
                  "aspect_ratio": "16:9",
                  "prompt": "x",
                  "start_frame": { "kind": "artifact_id", "role": "image" },
                  "options": { "person_generation": "allow_all" },
                  "number_of_videos": 1
                }
                """;

            var resp = await handler.DispatchAsync(body);

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertFieldEquals(resp, "start_frame.artifact_id");
        }

        [Fact]
        public async Task Submit_StartFrameWrongType_Rejected()
        {
            // Codex review: TryGetObject previously silent-skipped
            // wrong-type values. A string where an object is expected
            // MUST surface InvalidRequest, not be treated as absent.
            var handler = NewHandler();
            var body = """
                {
                  "op": "submit_video_job",
                  "model": "veo-3.1-lite-generate-preview",
                  "mode": "t2v",
                  "duration_seconds": 8,
                  "resolution": "720p",
                  "aspect_ratio": "16:9",
                  "prompt": "x",
                  "start_frame": "not-an-object",
                  "options": { "person_generation": "allow_all" },
                  "number_of_videos": 1
                }
                """;

            var resp = await handler.DispatchAsync(body);

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertFieldEquals(resp, "start_frame");
        }

        [Fact]
        public async Task Submit_ReferenceFramesWrongType_Rejected()
        {
            // Same wrong-type discipline for arrays. An object where
            // an array is expected MUST surface InvalidRequest.
            var handler = NewHandler();
            var body = """
                {
                  "op": "submit_video_job",
                  "model": "veo-3.1-lite-generate-preview",
                  "mode": "t2v",
                  "duration_seconds": 8,
                  "resolution": "720p",
                  "aspect_ratio": "16:9",
                  "prompt": "x",
                  "reference_frames": { "not": "an array" },
                  "options": { "person_generation": "allow_all" },
                  "number_of_videos": 1
                }
                """;

            var resp = await handler.DispatchAsync(body);

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertFieldEquals(resp, "reference_frames");
        }

        [Fact]
        public async Task Submit_NullOptionalMediaFields_TreatedAsAbsent()
        {
            // Explicit JSON null on optional fields is a legitimate
            // "no value" shape and must NOT be treated as wrong-type.
            // T2V ignores start_frame/end_frame; the request still
            // reaches the manager.
            var stub = new StubManager
            {
                SubmitImpl = (_, _) => JobSubmitResult.Ok(SampleJobId, VideoJobState.Queued),
            };
            var handler = NewHandler(stub);

            var body = """
                {
                  "op": "submit_video_job",
                  "model": "veo-3.1-lite-generate-preview",
                  "mode": "t2v",
                  "duration_seconds": 8,
                  "resolution": "720p",
                  "aspect_ratio": "16:9",
                  "prompt": "x",
                  "start_frame": null,
                  "end_frame": null,
                  "reference_frames": null,
                  "options": { "person_generation": "allow_all" },
                  "number_of_videos": 1
                }
                """;

            var resp = await handler.DispatchAsync(body);

            AssertOk(resp, expectedHttp: 200);
        }

        [Fact]
        public async Task Submit_MissingModel_Rejected()
        {
            var handler = NewHandler();
            var resp = await handler.DispatchAsync("""
                {"op":"submit_video_job","mode":"t2v","duration_seconds":8,
                 "resolution":"720p","aspect_ratio":"16:9",
                 "options":{"person_generation":"allow_all"},"number_of_videos":1}
                """);

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertFieldEquals(resp, "model");
        }

        [Fact]
        public async Task Submit_MissingOptions_Rejected()
        {
            var handler = NewHandler();
            var resp = await handler.DispatchAsync("""
                {"op":"submit_video_job","model":"veo-3.1-lite-generate-preview",
                 "mode":"t2v","duration_seconds":8,
                 "resolution":"720p","aspect_ratio":"16:9","number_of_videos":1}
                """);

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertFieldEquals(resp, "options");
        }

        [Fact]
        public async Task Submit_ManagerReturnsUnsupportedMedia_Maps415()
        {
            var stub = new StubManager
            {
                SubmitImpl = (_, _) => JobSubmitResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.UnsupportedMedia,
                    Message: "MIME not supported.",
                    Retryable: false,
                    Field: "MediaRef")),
            };
            var handler = NewHandler(stub);

            var resp = await handler.DispatchAsync(BuildSubmitBody());

            AssertFail(resp, VideoErrorCode.UnsupportedMedia, expectedHttp: 415);
        }

        [Fact]
        public async Task Submit_ManagerReturnsDependencyUnavailable_Maps503()
        {
            var stub = new StubManager
            {
                SubmitImpl = (_, _) => JobSubmitResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.DependencyUnavailable,
                    Message: "Veo unreachable.",
                    Retryable: true)),
            };
            var handler = NewHandler(stub);

            var resp = await handler.DispatchAsync(BuildSubmitBody());

            AssertFail(resp, VideoErrorCode.DependencyUnavailable, expectedHttp: 503);
        }

        [Fact]
        public async Task Submit_ManagerReturnsExecutionFailed_Maps500_EvenWhenRetryable()
        {
            // Status is determined by code, not by retryable —
            // ExecutionFailed is always 500 even when the caller may
            // legitimately retry (a transient Veo 5xx, for example).
            var stub = new StubManager
            {
                SubmitImpl = (_, _) => JobSubmitResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.ExecutionFailed,
                    Message: "Provider returned 503.",
                    Retryable: true)),
            };
            var handler = NewHandler(stub);

            var resp = await handler.DispatchAsync(BuildSubmitBody());

            AssertFail(resp, VideoErrorCode.ExecutionFailed, expectedHttp: 500);
            Assert.Equal(true, AssertDataDict(resp)["retryable"]);
        }

        // ─── Cancel ──────────────────────────────────────────────────────

        [Fact]
        public async Task Cancel_HappyPath_ReturnsCancelledState()
        {
            var stub = new StubManager
            {
                CancelImpl = (_, _) => JobCancelResult.Ok(VideoJobState.Cancelled),
            };
            var handler = NewHandler(stub);

            var body = $$"""{"op":"cancel_video_job","job_id":"{{SampleJobId:D}}"}""";
            var resp = await handler.DispatchAsync(body);

            AssertOk(resp, expectedHttp: 200);
            var data = AssertDataDict(resp);
            Assert.Equal(SampleJobId.ToString("D"), data["job_id"]);
            Assert.Equal("cancelled", data["state"]);
        }

        [Fact]
        public async Task Cancel_MissingJobId_Rejected()
        {
            var handler = NewHandler();
            var resp = await handler.DispatchAsync("""{"op":"cancel_video_job"}""");

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertFieldEquals(resp, "job_id");
        }

        [Fact]
        public async Task Cancel_MalformedJobId_Rejected()
        {
            var handler = NewHandler();
            var resp = await handler.DispatchAsync(
                """{"op":"cancel_video_job","job_id":"not-a-guid"}""");

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertFieldEquals(resp, "job_id");
        }

        [Fact]
        public async Task Cancel_ProviderRejected_PreservesStatusCode()
        {
            var stub = new StubManager
            {
                CancelImpl = (_, _) => JobCancelResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.DependencyUnavailable,
                    Message: "Veo cancel HTTP failed.",
                    Retryable: true)),
            };
            var handler = NewHandler(stub);

            var body = $$"""{"op":"cancel_video_job","job_id":"{{SampleJobId:D}}"}""";
            var resp = await handler.DispatchAsync(body);

            AssertFail(resp, VideoErrorCode.DependencyUnavailable, expectedHttp: 503);
        }

        // ─── Status ──────────────────────────────────────────────────────

        [Fact]
        public void Status_InFlight_ReturnsStateAndProgress()
        {
            var stub = new StubManager
            {
                StatusImpl = _ => JobStatusResult.InFlight(
                    VideoJobState.Polling,
                    new VideoJobProgress(Pct: 42, Stage: "polling", Message: null)),
            };
            var handler = NewHandler(stub);

            var resp = handler.DispatchOffUi(StatusBody());

            AssertOk(resp, expectedHttp: 200);
            var data = AssertDataDict(resp);
            Assert.Equal("polling", data["state"]);
            Assert.Null(data["error"]);
            var progress = (Dictionary<string, object?>)data["progress"]!;
            Assert.Equal(42, progress["pct"]);
            Assert.Equal("polling", progress["stage"]);
        }

        [Fact]
        public void Status_Complete_ReturnsResultArtifactId()
        {
            var stub = new StubManager
            {
                StatusImpl = _ => JobStatusResult.Complete(SampleResultArtifactId),
            };
            var handler = NewHandler(stub);

            var resp = handler.DispatchOffUi(StatusBody());

            AssertOk(resp, expectedHttp: 200);
            var data = AssertDataDict(resp);
            Assert.Equal("complete", data["state"]);
            Assert.Equal(SampleResultArtifactId.ToString("D"), data["result_artifact_id"]);
        }

        [Fact]
        public void Status_TerminalCancelledRead_IsSuccessNot400()
        {
            // Terminal-state read of a cancelled job: outer envelope
            // success=true, http=200, error info nested in data. The
            // caller asked for state and got it — that's a successful
            // read even though the job ended in a non-Complete terminal.
            var stub = new StubManager
            {
                StatusImpl = _ => JobStatusResult.Failed(
                    VideoJobState.Cancelled,
                    new VideoJobError(
                        Code: VideoErrorCode.Cancelled,
                        Message: "Job cancelled.",
                        Retryable: false)),
            };
            var handler = NewHandler(stub);

            var resp = handler.DispatchOffUi(StatusBody());

            AssertOk(resp, expectedHttp: 200);
            var data = AssertDataDict(resp);
            Assert.Equal("cancelled", data["state"]);
            Assert.NotNull(data["error"]);
            var err = (Dictionary<string, object?>)data["error"]!;
            Assert.Equal("cancelled", err["code"]);
        }

        [Fact]
        public void Status_UnknownJobId_ReturnsInvalidRequest400()
        {
            // The manager surfaces unknown jobId as Failed(Error,
            // {InvalidRequest, ...}). VideoOpHandler treats an
            // InvalidRequest code at the status level as an outer
            // failure (operation failed) rather than a successful
            // terminal-state read.
            var stub = new StubManager
            {
                StatusImpl = _ => JobStatusResult.Failed(
                    VideoJobState.Error,
                    new VideoJobError(
                        Code: VideoErrorCode.InvalidRequest,
                        Message: "Unknown jobId.",
                        Retryable: false,
                        Field: "jobId")),
            };
            var handler = NewHandler(stub);

            var resp = handler.DispatchOffUi(StatusBody());

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
        }

        // ─── Result ──────────────────────────────────────────────────────

        [Fact]
        public void Result_HappyPath_ReturnsArtifactAndFiles()
        {
            var stub = new StubManager
            {
                FetchImpl = _ => JobFetchResult.Complete(
                    SampleResultArtifactId,
                    new[] { new JobResultFile("video", @"C:\out\video.mp4") }),
            };
            var handler = NewHandler(stub);

            var resp = handler.DispatchOffUi(ResultBody());

            AssertOk(resp, expectedHttp: 200);
            var data = AssertDataDict(resp);
            Assert.Equal("complete", data["state"]);
            Assert.Equal(SampleResultArtifactId.ToString("D"), data["result_artifact_id"]);
            var files = (List<Dictionary<string, object?>>)data["files"]!;
            Assert.Single(files);
            Assert.Equal("video", files[0]["role"]);
        }

        [Fact]
        public void Result_NotComplete_FailsExecution500()
        {
            var stub = new StubManager
            {
                FetchImpl = _ => JobFetchResult.Failed(
                    VideoJobState.Polling,
                    new VideoJobError(
                        Code: VideoErrorCode.ExecutionFailed,
                        Message: "Job not complete (state=Polling).",
                        Retryable: false)),
            };
            var handler = NewHandler(stub);

            var resp = handler.DispatchOffUi(ResultBody());

            AssertFail(resp, VideoErrorCode.ExecutionFailed, expectedHttp: 500);
        }

        // ─── Estimate ────────────────────────────────────────────────────

        [Fact]
        public void Estimate_HappyPath_AgainstRealRegistryAndEstimator()
        {
            // Wire the real Veo registry + estimator (no provider HTTP —
            // estimator is pure-CPU dictionary lookup + arithmetic).
            // Pin the response shape including the pricing snapshot.
            var registry = TestVideoFixtures.RegistryWithVeo();
            var handler = new VideoOpHandler(
                manager: new StubManager(),
                registry: registry,
                estimator: new VideoCostEstimator());

            var resp = handler.DispatchOffUi(BuildEstimateBody());

            AssertOk(resp, expectedHttp: 200);
            var data = AssertDataDict(resp);
            Assert.Equal("veo-3.1-lite-generate-preview", data["model"]);
            Assert.Equal(8, data["duration_seconds"]);
            Assert.True((decimal)data["dollars_usd"]! > 0m);
            Assert.NotNull(data["pricing"]);
            var pricing = (Dictionary<string, object?>)data["pricing"]!;
            Assert.Equal("per_second", pricing["kind"]);
            Assert.Equal("USD", pricing["currency"]);
        }

        [Fact]
        public void Estimate_UnknownModel_FailsInvalidRequest400()
        {
            var registry = TestVideoFixtures.RegistryWithVeo();
            var handler = new VideoOpHandler(
                manager: new StubManager(),
                registry: registry,
                estimator: new VideoCostEstimator());

            var body = """
                {
                  "op": "estimate_video_job",
                  "model": "veo-imaginary",
                  "mode": "t2v",
                  "duration_seconds": 8,
                  "resolution": "720p",
                  "aspect_ratio": "16:9",
                  "options": { "person_generation": "allow_all" },
                  "number_of_videos": 1
                }
                """;

            var resp = handler.DispatchOffUi(body);

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertFieldEquals(resp, "Model");
        }

        // ─── MapStatusFromCode pinning ───────────────────────────────────

        [Theory]
        [InlineData(VideoErrorCode.InvalidRequest, 400)]
        [InlineData(VideoErrorCode.UnsupportedMedia, 415)]
        [InlineData(VideoErrorCode.DependencyUnavailable, 503)]
        [InlineData(VideoErrorCode.ExecutionFailed, 500)]
        [InlineData(VideoErrorCode.Cancelled, 200)]
        [InlineData(VideoErrorCode.Interrupted, 200)]
        public void MapStatusFromCode_PinsTableExactly(VideoErrorCode code, int expectedHttp)
        {
            // Table lives in v2 scope §6 + v3 sign-off. Pin every code.
            Assert.Equal(expectedHttp, VideoOpHandler.MapStatusFromCode(code));
        }

        [Theory]
        [InlineData(GenerationErrorCode.InvalidRequest, 400, "invalid_request")]
        [InlineData(GenerationErrorCode.UnsupportedMedia, 415, "unsupported_media")]
        [InlineData(GenerationErrorCode.DependencyUnavailable, 503, "dependency_unavailable")]
        [InlineData(GenerationErrorCode.ExecutionFailed, 500, "execution_failed")]
        [InlineData(GenerationErrorCode.Cancelled, 200, "cancelled")]
        [InlineData(GenerationErrorCode.Interrupted, 200, "interrupted")]
        [InlineData(GenerationErrorCode.QuotaExceeded, 429, "quota_exceeded")]
        [InlineData(GenerationErrorCode.ContentPolicy, 422, "content_policy")]
        public void MapStatusFromCode_GenerationPinsTableExactly(
            GenerationErrorCode code,
            int expectedHttp,
            string expectedWireCode)
        {
            Assert.Equal(expectedHttp, VideoOpHandler.MapStatusFromCode(code));
            Assert.Equal(expectedWireCode, CodeString(code));
        }

        [Fact]
        public void Estimate_QuotaExceeded_Maps429AndDoesNotLeakProviderDetail()
        {
            var estimator = new StubEstimator(new GenerationError(
                Code: GenerationErrorCode.QuotaExceeded,
                Message: "Provider quota exhausted.",
                Retryable: true,
                Field: "quota",
                ProviderErrorCode: "rate_limit_exceeded",
                ProviderDetail: new Dictionary<string, JsonNode>
                {
                    ["detail"] = JsonValue.Create("internal provider detail")!,
                }));
            var handler = NewHandler(estimator: estimator);

            var resp = handler.DispatchOffUi(BuildEstimateBody());

            AssertFail(resp, GenerationErrorCode.QuotaExceeded, expectedHttp: 429);
            var data = AssertDataDict(resp);
            Assert.False(data.ContainsKey("provider_error_code"));
            Assert.False(data.ContainsKey("provider_detail"));
            Assert.False(data.ContainsKey("provider_message"));
        }

        [Fact]
        public void Estimate_ContentPolicy_Maps422()
        {
            var estimator = new StubEstimator(new GenerationError(
                Code: GenerationErrorCode.ContentPolicy,
                Message: "Provider rejected the prompt.",
                Retryable: false,
                Field: "prompt"));
            var handler = NewHandler(estimator: estimator);

            var resp = handler.DispatchOffUi(BuildEstimateBody());

            AssertFail(resp, GenerationErrorCode.ContentPolicy, expectedHttp: 422);
        }

        // ─── ListJobs (PR-V3) ────────────────────────────────────────────

        [Fact]
        public void ListJobs_AbsentLimit_DefaultsTo50()
        {
            var stub = new StubManager
            {
                ListImpl = limit => new JobListResult(
                    Array.Empty<JobListEntry>(),
                    Array.Empty<LedgerWarning>(),
                    AppliedLimit: limit),
            };
            var handler = NewHandler(stub);

            var resp = handler.DispatchOffUi("""{"op":"list_video_jobs"}""");

            AssertOk(resp, expectedHttp: 200);
            Assert.Equal(50, stub.LastListLimit);
            var data = AssertDataDict(resp);
            Assert.Equal(50, data["applied_limit"]);
        }

        [Theory]
        [InlineData(@"{""op"":""list_video_jobs"",""limit"":""50""}")]
        [InlineData(@"{""op"":""list_video_jobs"",""limit"":-1}")]
        [InlineData(@"{""op"":""list_video_jobs"",""limit"":0}")]
        [InlineData(@"{""op"":""list_video_jobs"",""limit"":1.5}")]
        [InlineData(@"{""op"":""list_video_jobs"",""limit"":true}")]
        // PR-V3 implementation review: explicit null is a present-but-
        // empty value; the v3 contract says only ABSENT defaults, every
        // other shape rejects. Pin the rejection.
        [InlineData(@"{""op"":""list_video_jobs"",""limit"":null}")]
        public void ListJobs_BadLimit_RejectedAsInvalidRequest(string body)
        {
            var stub = new StubManager();
            var handler = NewHandler(stub);

            var resp = handler.DispatchOffUi(body);

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertFieldEquals(resp, "limit");
            // Manager must NOT be called for any rejected limit shape.
            Assert.Equal(0, stub.ListCallCount);
        }

        [Fact]
        public void ListJobs_ValidLimit_PassedThrough()
        {
            var stub = new StubManager();
            var handler = NewHandler(stub);

            handler.DispatchOffUi("""{"op":"list_video_jobs","limit":25}""");

            Assert.Equal(25, stub.LastListLimit);
        }

        [Fact]
        public void ListJobs_EmptyManager_ReturnsEmptyArrays()
        {
            var stub = new StubManager(); // ListImpl null → returns empty result
            var handler = NewHandler(stub);

            var resp = handler.DispatchOffUi("""{"op":"list_video_jobs"}""");

            AssertOk(resp, expectedHttp: 200);
            var data = AssertDataDict(resp);
            var jobs = Assert.IsType<List<Dictionary<string, object?>>>(data["jobs"]);
            var warnings = Assert.IsType<List<Dictionary<string, object?>>>(data["warnings"]);
            Assert.Empty(jobs);
            Assert.Empty(warnings);
        }

        [Fact]
        public void ListJobs_ProjectsEntriesAsSnakeCase()
        {
            var jobId = SampleJobId;
            var resultArtifactId = SampleResultArtifactId;
            var updatedAt = new DateTimeOffset(
                2026, 4, 25, 12, 0, 0, TimeSpan.FromHours(-7));

            var entry = new JobListEntry(
                JobId: jobId,
                State: VideoJobState.Polling,
                UpdatedAt: updatedAt,
                Summary: new JobRequestSummary(
                    Model: "veo-3.1-lite-generate-preview",
                    Mode: VideoMode.T2V,
                    DurationSeconds: 8,
                    Resolution: "720p",
                    AspectRatio: "16:9"),
                ResultArtifactId: resultArtifactId,
                Error: null);

            var stub = new StubManager
            {
                ListImpl = limit => new JobListResult(
                    new[] { entry }, Array.Empty<LedgerWarning>(), AppliedLimit: limit),
            };
            var handler = NewHandler(stub);

            var resp = handler.DispatchOffUi("""{"op":"list_video_jobs"}""");

            AssertOk(resp, expectedHttp: 200);
            var data = AssertDataDict(resp);
            var jobs = (List<Dictionary<string, object?>>)data["jobs"]!;
            var row = Assert.Single(jobs);

            Assert.Equal(jobId.ToString("D"), row["job_id"]);
            Assert.Equal("polling", row["state"]);
            Assert.Equal(resultArtifactId.ToString("D"), row["result_artifact_id"]);
            Assert.Null(row["error"]);

            // ISO 8601 round-trip with explicit offset preserved.
            var updatedStr = Assert.IsType<string>(row["updated_at"]);
            var roundTripped = DateTimeOffset.Parse(
                updatedStr, System.Globalization.CultureInfo.InvariantCulture,
                System.Globalization.DateTimeStyles.RoundtripKind);
            Assert.Equal(updatedAt, roundTripped);

            var summary = Assert.IsType<Dictionary<string, object?>>(row["request_summary"]);
            Assert.Equal("veo-3.1-lite-generate-preview", summary["model"]);
            Assert.Equal("t2v", summary["mode"]);
            Assert.Equal(8, summary["duration_seconds"]);
            Assert.Equal("720p", summary["resolution"]);
            Assert.Equal("16:9", summary["aspect_ratio"]);
        }

        [Fact]
        public void ListJobs_WarningWireShape_MatchesScopeContract()
        {
            // PR-V3 signed-off scope: each warning is {line, reason, field}.
            // Drop the synthesized message field, drop raw_line_excerpt
            // and offending_value — both can carry user-supplied content.
            // Reason is the typed snake_case enum that encodes the same
            // information the message would.
            var stub = new StubManager
            {
                ListImpl = limit => new JobListResult(
                    Array.Empty<JobListEntry>(),
                    new[]
                    {
                        new LedgerWarning(
                            LineNumber: 7,
                            Reason: LedgerReadErrorReason.MalformedJson,
                            Message: "Ledger line could not be parsed as JSON.",
                            FieldPath: "pricing.kind"),
                    },
                    AppliedLimit: limit),
            };
            var handler = NewHandler(stub);

            var resp = handler.DispatchOffUi("""{"op":"list_video_jobs"}""");

            AssertOk(resp, expectedHttp: 200);
            var data = AssertDataDict(resp);
            var warnings = (List<Dictionary<string, object?>>)data["warnings"]!;
            var w = Assert.Single(warnings);

            // Wire-shape pin: scope-mandated keys present.
            Assert.Equal(7, w["line"]);
            Assert.Equal("malformed_json", w["reason"]);
            Assert.Equal("pricing.kind", w["field"]);

            // Wire-shape pin: drift / leak-prone keys absent.
            Assert.False(w.ContainsKey("line_number"));
            Assert.False(w.ContainsKey("field_path"));
            Assert.False(w.ContainsKey("message"));
            Assert.False(w.ContainsKey("raw_line_excerpt"));
            Assert.False(w.ContainsKey("offending_value"));
        }

        [Fact]
        public void ListJobs_ReportsAppliedLimitFromManager()
        {
            // The manager is the authority on applied_limit — it does the
            // clamping. Handler trusts and forwards it. Pin: handler echoes
            // whatever the manager returns.
            var stub = new StubManager
            {
                ListImpl = _ => new JobListResult(
                    Array.Empty<JobListEntry>(),
                    Array.Empty<LedgerWarning>(),
                    AppliedLimit: 200),
            };
            var handler = NewHandler(stub);

            var resp = handler.DispatchOffUi("""{"op":"list_video_jobs","limit":500}""");

            AssertOk(resp, expectedHttp: 200);
            var data = AssertDataDict(resp);
            Assert.Equal(200, data["applied_limit"]);
        }

        // ─── ListModels (PR-V3) ──────────────────────────────────────────

        [Fact]
        public void ListModels_ReturnsRegisteredModels_AsSnakeCase()
        {
            // Uses the real production registry fixture (TestVideoFixtures
            // → DefaultVideoProviderRegistry over VeoProviderRegistration)
            // so this test asserts against the actual capability matrix
            // and catches drift between the catalog and the projection.
            var handler = NewHandler();

            var resp = handler.DispatchOffUi("""{"op":"list_video_models"}""");

            AssertOk(resp, expectedHttp: 200);
            var data = AssertDataDict(resp);
            var models = Assert.IsType<List<Dictionary<string, object?>>>(data["models"]);
            Assert.NotEmpty(models);

            // Pick the default Veo Lite entry that the test fixture
            // pins as DefaultModelId. Capability shape comes from the
            // real VeoCapabilities table — the test asserts shape, not
            // example text. If the real capability flips
            // SupportsReferenceImages, this test still passes because it
            // doesn't hardcode the boolean — it just asserts the field
            // is present and is a bool.
            var lite = models.Find(m =>
                (string?)m["model_id"] == TestVideoFixtures.DefaultModelId);
            Assert.NotNull(lite);

            Assert.Equal(TestVideoFixtures.VeoProviderName, lite!["provider_name"]);
            Assert.IsType<string>(lite["pricing_kind"]);
            Assert.IsType<string>(lite["pricing_source"]);

            var cap = Assert.IsType<Dictionary<string, object?>>(lite["capability"]);
            Assert.IsType<string>(cap["id"]);
            Assert.IsType<string>(cap["name"]);
            Assert.IsType<string>(cap["status"]);
            Assert.IsAssignableFrom<System.Collections.IEnumerable>(cap["resolutions"]);
            Assert.IsAssignableFrom<System.Collections.IEnumerable>(cap["durations"]);
            Assert.IsAssignableFrom<System.Collections.IEnumerable>(cap["aspect_ratios"]);
            Assert.IsAssignableFrom<System.Collections.IEnumerable>(cap["modes"]);
            Assert.IsType<bool>(cap["supports_reference_images"]);
            Assert.IsType<int>(cap["max_reference_images"]);
            Assert.IsAssignableFrom<System.Collections.IEnumerable>(cap["must_8s_with"]);
        }

        [Fact]
        public void ListModels_ProjectsModesAsSnakeCaseStrings()
        {
            var handler = NewHandler();
            var resp = handler.DispatchOffUi("""{"op":"list_video_models"}""");

            AssertOk(resp, expectedHttp: 200);
            var data = AssertDataDict(resp);
            var models = (List<Dictionary<string, object?>>)data["models"]!;
            foreach (var m in models)
            {
                var cap = (Dictionary<string, object?>)m["capability"]!;
                var modes = (System.Collections.IEnumerable)cap["modes"]!;
                foreach (var mode in modes)
                {
                    var s = Assert.IsType<string>(mode);
                    // Snake-case lower; one of the known VideoMode values.
                    Assert.Contains(s, new[] { "t2v", "i2v", "interp" });
                }
            }
        }

        [Fact]
        public async Task ListJobs_RejectedOnAsyncDispatcher()
        {
            // Defense: dispatcher fork must reject list ops if they
            // arrive on the async path. (VisionWebSurface.OpRoutes routes
            // them OffUi, but a future trampoline change shouldn't be
            // able to silently land them on the async path either.)
            var handler = NewHandler();
            var resp = await handler.DispatchAsync("""{"op":"list_video_jobs"}""");

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertMessageContains(resp, "off-UI");
        }

        [Fact]
        public async Task ListModels_RejectedOnAsyncDispatcher()
        {
            var handler = NewHandler();
            var resp = await handler.DispatchAsync("""{"op":"list_video_models"}""");

            AssertFail(resp, VideoErrorCode.InvalidRequest, expectedHttp: 400);
            AssertMessageContains(resp, "off-UI");
        }

        // ─── Helpers ─────────────────────────────────────────────────────

        private static VideoOpHandler NewHandler(
            IVideoJobManager? manager = null,
            IVideoCostEstimator? estimator = null)
        {
            // Real registry/estimator — only the manager is faked. The
            // estimator path tests can substitute, but for ops that
            // don't touch the registry/estimator, real instances are
            // harmless.
            return new VideoOpHandler(
                manager: manager ?? new StubManager(),
                registry: TestVideoFixtures.RegistryWithVeo(),
                estimator: estimator ?? new VideoCostEstimator());
        }

        private static string BuildSubmitBody() => $$"""
            {
              "op": "submit_video_job",
              "model": "veo-3.1-lite-generate-preview",
              "mode": "t2v",
              "duration_seconds": 8,
              "resolution": "720p",
              "aspect_ratio": "16:9",
              "prompt": "a clip",
              "options": { "person_generation": "allow_all" },
              "number_of_videos": 1
            }
            """;

        private static string BuildEstimateBody() => """
            {
              "op": "estimate_video_job",
              "model": "veo-3.1-lite-generate-preview",
              "mode": "t2v",
              "duration_seconds": 8,
              "resolution": "720p",
              "aspect_ratio": "16:9",
              "prompt": "a clip",
              "options": { "person_generation": "allow_all" },
              "number_of_videos": 1
            }
            """;

        private static string StatusBody() =>
            $$"""{"op":"get_video_job","job_id":"{{SampleJobId:D}}"}""";

        private static string ResultBody() =>
            $$"""{"op":"get_video_job_result","job_id":"{{SampleJobId:D}}"}""";

        private static void AssertOk(ApiResponse resp, int expectedHttp)
        {
            Assert.True(resp.Success,
                "expected success=true; data: " + JsonSerializer.Serialize(resp.Data));
            Assert.Equal(expectedHttp, resp.HttpStatus);
        }

        private static void AssertFail(
            ApiResponse resp, VideoErrorCode expectedCode, int expectedHttp)
        {
            Assert.False(resp.Success,
                "expected success=false; data: " + JsonSerializer.Serialize(resp.Data));
            Assert.Equal(expectedHttp, resp.HttpStatus);
            var data = AssertDataDict(resp);
            Assert.Equal(CodeString(expectedCode), data["code"]);
        }

        private static void AssertFail(
            ApiResponse resp, GenerationErrorCode expectedCode, int expectedHttp)
        {
            Assert.False(resp.Success,
                "expected success=false; data: " + JsonSerializer.Serialize(resp.Data));
            Assert.Equal(expectedHttp, resp.HttpStatus);
            var data = AssertDataDict(resp);
            Assert.Equal(CodeString(expectedCode), data["code"]);
        }

        private static Dictionary<string, object?> AssertDataDict(ApiResponse resp)
        {
            Assert.NotNull(resp.Data);
            var dict = resp.Data as Dictionary<string, object?>;
            Assert.NotNull(dict);
            return dict!;
        }

        private static void AssertMessageContains(ApiResponse resp, string fragment)
        {
            var data = AssertDataDict(resp);
            var msg = data["message"] as string ?? string.Empty;
            Assert.Contains(fragment, msg, StringComparison.OrdinalIgnoreCase);
        }

        private static void AssertFieldEquals(ApiResponse resp, string field)
        {
            var data = AssertDataDict(resp);
            Assert.Equal(field, data["field"]);
        }

        private static string CodeString(VideoErrorCode code) => code switch
        {
            VideoErrorCode.InvalidRequest => "invalid_request",
            VideoErrorCode.UnsupportedMedia => "unsupported_media",
            VideoErrorCode.DependencyUnavailable => "dependency_unavailable",
            VideoErrorCode.ExecutionFailed => "execution_failed",
            VideoErrorCode.Cancelled => "cancelled",
            VideoErrorCode.Interrupted => "interrupted",
            _ => code.ToString().ToLowerInvariant(),
        };

        private static string CodeString(GenerationErrorCode code) => code switch
        {
            GenerationErrorCode.InvalidRequest => "invalid_request",
            GenerationErrorCode.UnsupportedMedia => "unsupported_media",
            GenerationErrorCode.DependencyUnavailable => "dependency_unavailable",
            GenerationErrorCode.ExecutionFailed => "execution_failed",
            GenerationErrorCode.Cancelled => "cancelled",
            GenerationErrorCode.Interrupted => "interrupted",
            GenerationErrorCode.QuotaExceeded => "quota_exceeded",
            GenerationErrorCode.ContentPolicy => "content_policy",
            _ => code.ToString().ToLowerInvariant(),
        };

        private sealed class StubEstimator : IVideoCostEstimator
        {
            private readonly GenerationError _error;

            public StubEstimator(GenerationError error)
            {
                _error = error;
            }

            public VideoCostEstimateResult Estimate(
                ResolvedVideoModel model,
                VideoGenerationRequest request) =>
                VideoCostEstimateResult.Fail(_error);
        }

        // ─── Stub manager ────────────────────────────────────────────────

        private sealed class StubManager : IVideoJobManager
        {
            public Func<VideoGenerationRequest, CancellationToken, JobSubmitResult>? SubmitImpl { get; set; }
            public Func<Guid, JobStatusResult>? StatusImpl { get; set; }
            public Func<Guid, CancellationToken, JobCancelResult>? CancelImpl { get; set; }
            public Func<Guid, JobFetchResult>? FetchImpl { get; set; }
            public Func<int, JobListResult>? ListImpl { get; set; }

            public int SubmitCallCount;
            public int StatusCallCount;
            public int CancelCallCount;
            public int FetchCallCount;
            public int ListCallCount;
            public int LastListLimit;

            public Task<JobSubmitResult> SubmitAsync(
                VideoGenerationRequest request, CancellationToken ct)
            {
                Interlocked.Increment(ref SubmitCallCount);
                return Task.FromResult(SubmitImpl?.Invoke(request, ct)
                    ?? JobSubmitResult.Fail(new VideoJobError(
                        Code: VideoErrorCode.ExecutionFailed,
                        Message: "Stub: SubmitImpl not configured.",
                        Retryable: false)));
            }

            public Task<JobStatusResult> GetStatusAsync(Guid jobId, CancellationToken ct)
            {
                Interlocked.Increment(ref StatusCallCount);
                return Task.FromResult(StatusImpl?.Invoke(jobId)
                    ?? JobStatusResult.Failed(
                        VideoJobState.Error,
                        new VideoJobError(
                            Code: VideoErrorCode.ExecutionFailed,
                            Message: "Stub: StatusImpl not configured.",
                            Retryable: false)));
            }

            public Task<JobCancelResult> CancelAsync(Guid jobId, CancellationToken ct)
            {
                Interlocked.Increment(ref CancelCallCount);
                return Task.FromResult(CancelImpl?.Invoke(jobId, ct)
                    ?? JobCancelResult.Fail(new VideoJobError(
                        Code: VideoErrorCode.ExecutionFailed,
                        Message: "Stub: CancelImpl not configured.",
                        Retryable: false)));
            }

            public Task<JobFetchResult> FetchResultAsync(Guid jobId, CancellationToken ct)
            {
                Interlocked.Increment(ref FetchCallCount);
                return Task.FromResult(FetchImpl?.Invoke(jobId)
                    ?? JobFetchResult.Failed(
                        VideoJobState.Error,
                        new VideoJobError(
                            Code: VideoErrorCode.ExecutionFailed,
                            Message: "Stub: FetchImpl not configured.",
                            Retryable: false)));
            }

            public Task<JobListResult> ListJobsAsync(int limit, CancellationToken ct)
            {
                Interlocked.Increment(ref ListCallCount);
                LastListLimit = limit;
                return Task.FromResult(ListImpl?.Invoke(limit)
                    ?? new JobListResult(
                        Array.Empty<JobListEntry>(),
                        Array.Empty<LedgerWarning>(),
                        AppliedLimit: limit));
            }

            public void ReconcileInterruptedJobs() { }
        }
    }
}
