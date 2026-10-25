using System.Threading;
using System.Threading.Tasks;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalConfiguredLifecycleTests
    {
        [Fact]
        public void Accepted_handle_contains_only_validated_lifecycle_authority()
        {
            using var run = new ConfiguredRun(); var body = JsonNode.Parse(ConfiguredRun.QueueBody())!.AsObject();
            body["status"] = new JsonObject { ["source"] = "https://v3.fal.media/files/private-source.png" };
            body["queue_position"] = new JsonObject { ["api_key"] = "must-not-persist" };
            Assert.Null(FalConfiguredLifecycle.ParseSubmitHandle(run.Request.Binding, body).ProviderMetadata);
        }
        [Fact]
        public async Task Unrecognized_status_does_not_echo_provider_content_into_history()
        {
            using var run = new ConfiguredRun(); run.Body = "{\"status\":\"https://v3.fal.media/files/private-source.png\"}";
            var failed = Assert.IsType<FailedStatusOutcome>(await run.Executor.GetStatusAsync(run.Request.Binding, ConfiguredRun.Handle(), CancellationToken.None));
            Assert.DoesNotContain("private-source", failed.Error.Message); Assert.Null(failed.Error.ProviderErrorCode); Assert.Null(failed.Error.ProviderDetail);
        }
        [Fact]
        public async Task Queue_uses_validated_returned_urls()
        {
            using var run = new ConfiguredRun(); run.Body = "{\"status\":\"IN_PROGRESS\"}";
            Assert.IsType<InFlightStatusOutcome>(await run.Executor.GetStatusAsync(run.Request.Binding, ConfiguredRun.Handle(), CancellationToken.None));
            Assert.Equal(ConfiguredRun.Root + "/status", run.LastUrl);
        }
        [Theory]
        [InlineData("https://evil.example/fal-ai/synthetic/requests/job-1/status")]
        [InlineData("https://other.fal.run/fal-ai/synthetic/requests/job-1/status")]
        [InlineData("https://queue.fal.run/other/requests/job-1/status")]
        [InlineData("https://queue.fal.run/fal-ai/synthetic/requests/job-2/status")]
        [InlineData("https://queue.fal.run/fal-ai/synthetic/requests/job-1/cancel")]
        [InlineData("https://key@queue.fal.run/fal-ai/synthetic/requests/job-1/status")]
        [InlineData("https://queue.fal.run/fal-ai/synthetic/requests/job-1/status#fragment")]
        [InlineData("https://queue.fal.run/fal-ai/synthetic/requests/job-1/status?url=evil")]
        [InlineData("https://queue.fal.run:8443/fal-ai/synthetic/requests/job-1/status")]
        [InlineData("https://queue.fal.run/fal-ai/synthetic/requests/job-1/../job-1/status")]
        [InlineData("https://queue.fal.run/fal-ai/synthetic/requests/job-1/%2e%2e/job-1/status")]
        public async Task Malformed_lifecycle_urls_never_call_transport(string url)
        {
            using var run = new ConfiguredRun();
            Assert.IsType<FailedStatusOutcome>(await run.Executor.GetStatusAsync(run.Request.Binding, ConfiguredRun.Handle(status: url), CancellationToken.None));
            Assert.Null(run.LastUrl);
        }
        [Theory]
        [InlineData("lifecycle_timeout")]
        [InlineData("lifecycle_network")]
        public async Task Lifecycle_transport_failure_can_retry_without_resubmitting(string failure)
        {
            using var run = new ConfiguredRun(); run.Failure = failure;
            Assert.True(Assert.IsType<FailedStatusOutcome>(await run.Executor.GetStatusAsync(run.Request.Binding, ConfiguredRun.Handle(), CancellationToken.None)).Error.Retryable);
            Assert.True(Assert.IsType<FailedResultOutcome>(await run.Executor.FetchResultAsync(run.Request.Binding, ConfiguredRun.Handle(), CancellationToken.None)).Error.Retryable);
            Assert.True(Assert.IsType<FailedCancelOutcome>(await run.Executor.CancelAsync(run.Request.Binding, ConfiguredRun.Handle(), CancellationToken.None)).Error.Retryable);
            Assert.Empty(run.Events);
        }
        [Fact]
        public async Task Invalid_result_and_cancel_urls_are_rejected_before_HTTP()
        {
            using var run = new ConfiguredRun();
            Assert.IsType<FailedResultOutcome>(await run.Executor.FetchResultAsync(run.Request.Binding, ConfiguredRun.Handle(result: ConfiguredRun.Root + "/status"), CancellationToken.None));
            Assert.IsType<FailedCancelOutcome>(await run.Executor.CancelAsync(run.Request.Binding, ConfiguredRun.Handle(cancel: ConfiguredRun.Root + "/status"), CancellationToken.None));
            Assert.Null(run.LastUrl);
        }
        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task Completed_status_requires_a_validated_image_or_video_result(bool video)
        {
            using var run = new ConfiguredRun(video: video); run.Body = "{\"status\":\"COMPLETED\"}";
            Assert.IsType<ProviderCompleteStatusOutcome>(await run.Executor.GetStatusAsync(run.Request.Binding, ConfiguredRun.Handle(), CancellationToken.None));
            run.Body = video ? "{\"video\":{\"url\":\"https://fal.media/result.mp4\"}}" : "{\"images\":[{\"url\":\"https://fal.media/result.png\"}]}";
            Assert.IsType<SuccessResultOutcome>(await run.Executor.FetchResultAsync(run.Request.Binding, ConfiguredRun.Handle(), CancellationToken.None));
        }
        [Theory]
        [InlineData(200, "OK", "canceled")]
        [InlineData(202, "CANCELLATION_REQUESTED", "pending")]
        [InlineData(400, "ALREADY_COMPLETED", "completed")]
        [InlineData(404, "NOT_FOUND", "failed")]
        [InlineData(200, "CANCELLATION_REQUESTED", "failed")]
        [InlineData(202, "OK", "failed")]
        public async Task Cancellation_preserves_remote_outcome(int status, string response, string expected)
        {
            using var run = new ConfiguredRun(); run.Status = status; run.Body = "{\"status\":\"" + response + "\"}";
            var outcome = await run.Executor.CancelAsync(run.Request.Binding, ConfiguredRun.Handle(), CancellationToken.None);
            if (expected == "canceled") Assert.IsType<CanceledOutcome>(outcome);
            else if (expected == "completed") Assert.IsType<AlreadyTerminalOutcome>(outcome);
            else Assert.IsType<FailedCancelOutcome>(outcome);
        }
        [Theory]
        [InlineData(503, "{}")]
        [InlineData(200, "garbage")]
        [InlineData(200, "{\"status\":\"COMPLETED\",\"error\":\"failed\"}")]
        public async Task Invalid_status_is_a_failure(int status, string body)
        { using var run = new ConfiguredRun(); run.Status = status; run.Body = body; Assert.IsType<FailedStatusOutcome>(await run.Executor.GetStatusAsync(run.Request.Binding, ConfiguredRun.Handle(), CancellationToken.None)); }
        [Theory]
        [InlineData(503, "{}")]
        [InlineData(200, "garbage")]
        [InlineData(200, "{\"images\":[]}")]
        public async Task Result_validation_precedes_success(int status, string body)
        { using var run = new ConfiguredRun(); run.Status = status; run.Body = body; Assert.IsType<FailedResultOutcome>(await run.Executor.FetchResultAsync(run.Request.Binding, ConfiguredRun.Handle(), CancellationToken.None)); }
    }
}
