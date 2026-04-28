using System;
using System.Text.Json;
using System.Threading.Tasks;
using Rook.Handlers;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fixtures
{
    /// <summary>
    /// Captures byte-identity goldens for the public V1c
    /// <see cref="VideoOpHandler"/> error response wire shape across the
    /// snake-case <c>code</c> mapping and the four typed HTTP status
    /// arms (400 / 415 / 500 / 503). Drives the handler through its
    /// public <c>DispatchAsync</c> / <c>DispatchOffUi</c> entry points
    /// with a scripted <see cref="FakeVideoJobManager"/> so the captured
    /// <see cref="ApiResponse"/> is the same one a native HTTP route
    /// would emit.
    ///
    /// <para>Goldens #11–#16 freeze the wire contract that PR-2's
    /// commit 5 retargets when <c>VideoErrorCode</c> migrates to
    /// <c>GenerationErrorCode</c>. The legacy six error codes must
    /// emit byte-identical JSON post-retrofit.</para>
    /// </summary>
    public class VeoHttpErrorShapeCaptureTests
    {
        // ─── Helpers ─────────────────────────────────────────────────

        private static VideoOpHandler HandlerWithSubmitError(VideoJobError err)
        {
            var manager = new FakeVideoJobManager
            {
                OnSubmit = _ => Task.FromResult(JobSubmitResult.Fail(err)),
            };
            return new VideoOpHandler(
                manager,
                TestVideoFixtures.RegistryWithVeo(),
                new VideoCostEstimator());
        }

        private static VideoOpHandler HandlerWithStatus(JobStatusResult status)
        {
            var manager = new FakeVideoJobManager
            {
                OnGetStatus = _ => Task.FromResult(status),
            };
            return new VideoOpHandler(
                manager,
                TestVideoFixtures.RegistryWithVeo(),
                new VideoCostEstimator());
        }

        // Valid submit body shape — used when the test wants the
        // handler's parser to accept the request and reach the manager
        // (so the manager-injected error is what the response reflects,
        // not a parser-level rejection).
        private static string ValidSubmitBody() =>
            JsonSerializer.Serialize(new
            {
                op = VideoOpHandler.OpSubmit,
                model = "veo-3.1-generate-preview",
                mode = "t2v",
                duration_seconds = 8,
                resolution = "720p",
                aspect_ratio = "16:9",
                prompt = "fixture",
                options = new { person_generation = "allow_all" },
                number_of_videos = 1,
            });

        // ─── #11 — submit auth fail (401 → dependency_unavailable / 503) ──

        [Fact]
        public async Task Golden_11_http_submit_auth_fail()
        {
            // VeoErrorMapper.MapStartFailure(401, body) produces
            // DependencyUnavailable (Retryable=false). The HTTP handler
            // maps DependencyUnavailable → 503 via MapStatusFromCode.
            // ProviderMessage is dropped from the HTTP shape (V1c
            // contract: HTTP boundary surfaces only code/message/
            // retryable/field).
            var err = new VideoJobError(
                Code: VideoErrorCode.DependencyUnavailable,
                Message: "Veo submit rejected: authentication failed (401). " +
                         "{\"error\":\"unauthenticated\"}",
                Retryable: false,
                ProviderMessage: "{\"error\":\"unauthenticated\"}");

            var handler = HandlerWithSubmitError(err);
            var response = await handler.DispatchAsync(ValidSubmitBody());

            VeoBehaviorParityFixture.AssertOrCapture(
                "11_http_submit_auth_fail.json",
                ApiResponseSerializer.ToJson(response));
        }

        // ─── #12 — submit invalid request (400 → invalid_request / 400) ──

        [Fact]
        public async Task Golden_12_http_submit_invalid_request()
        {
            var err = new VideoJobError(
                Code: VideoErrorCode.InvalidRequest,
                Message: "Veo submit rejected as invalid (400). " +
                         "{\"error\":\"durationSeconds must be a number\"}",
                Retryable: false,
                Field: "duration_seconds",
                ProviderMessage: "{\"error\":\"durationSeconds must be a number\"}");

            var handler = HandlerWithSubmitError(err);
            var response = await handler.DispatchAsync(ValidSubmitBody());

            VeoBehaviorParityFixture.AssertOrCapture(
                "12_http_submit_invalid_request.json",
                ApiResponseSerializer.ToJson(response));
        }

        // ─── #13 — submit backend 5xx (execution_failed / 500) ──

        [Fact]
        public async Task Golden_13_http_submit_backend_5xx()
        {
            var err = new VideoJobError(
                Code: VideoErrorCode.ExecutionFailed,
                Message: "Veo submit backend error (503). {\"error\":\"unavailable\"}",
                Retryable: true,
                ProviderMessage: "{\"error\":\"unavailable\"}");

            var handler = HandlerWithSubmitError(err);
            var response = await handler.DispatchAsync(ValidSubmitBody());

            VeoBehaviorParityFixture.AssertOrCapture(
                "13_http_submit_backend_5xx.json",
                ApiResponseSerializer.ToJson(response));
        }

        // ─── #14 — STATUS reports terminal Error after a poll 5xx ──
        //
        // This case exercises the GetStatus path, where the handler
        // wraps the terminal error inside a successful response (per
        // VideoOpHandler.GetStatus's "outer-failure semantics" note —
        // only InvalidRequest at this level returns a Fail envelope).
        // Captured separately from #13 because the wire shape differs:
        // #13 = error-style envelope (success=false, code at top of
        // data); #14 = success-style envelope (success=true, error
        // nested inside data alongside state).
        [Fact]
        public void Golden_14_http_status_terminal_error()
        {
            var jobId = Guid.Parse("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");
            var status = JobStatusResult.Failed(
                VideoJobState.Error,
                new VideoJobError(
                    Code: VideoErrorCode.ExecutionFailed,
                    Message: "Veo poll backend error (503). {\"error\":\"unavailable\"}",
                    Retryable: true,
                    ProviderMessage: "{\"error\":\"unavailable\"}"));

            var handler = HandlerWithStatus(status);
            var body = JsonSerializer.Serialize(new
            {
                op = VideoOpHandler.OpStatus,
                job_id = jobId.ToString("D"),
            });

            var response = handler.DispatchOffUi(body);

            VeoBehaviorParityFixture.AssertOrCapture(
                "14_http_status_terminal_error.json",
                ApiResponseSerializer.ToJson(response));
        }

        // ─── #15 — cancel with malformed jobId (parser-level reject) ──

        [Fact]
        public async Task Golden_15_http_cancel_malformed_jobid()
        {
            // Parser-level rejection — never reaches the manager. Tests
            // the failure shape for InvalidRequest at the boundary.
            var manager = new FakeVideoJobManager();  // OnCancel intentionally unset
            var handler = new VideoOpHandler(
                manager,
                TestVideoFixtures.RegistryWithVeo(),
                new VideoCostEstimator());

            var body = JsonSerializer.Serialize(new
            {
                op = VideoOpHandler.OpCancel,
                job_id = "not-a-guid",
            });

            var response = await handler.DispatchAsync(body);

            VeoBehaviorParityFixture.AssertOrCapture(
                "15_http_cancel_malformed_jobid.json",
                ApiResponseSerializer.ToJson(response));
        }

        // ─── #16 — submit, no API key configured ──

        [Fact]
        public async Task Golden_16_http_submit_no_api_key()
        {
            // VeoErrorMapper.MissingApiKey() is the canonical shape for
            // "user has not configured the Veo key." The Message string
            // is byte-identical to V1c's
            // "Veo API key not configured. Set it via the Vision tab
            //  Settings panel."
            var err = VeoErrorMapper.MissingApiKey();

            var handler = HandlerWithSubmitError(err);
            var response = await handler.DispatchAsync(ValidSubmitBody());

            VeoBehaviorParityFixture.AssertOrCapture(
                "16_http_submit_no_api_key.json",
                ApiResponseSerializer.ToJson(response));
        }
    }
}
