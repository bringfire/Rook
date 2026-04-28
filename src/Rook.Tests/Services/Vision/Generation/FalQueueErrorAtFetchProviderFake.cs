using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    /// <summary>
    /// fal-queue terminal-not-success fake: lifecycle reaches
    /// <see cref="ProviderCompleteStatusOutcome"/> but the fetch step
    /// returns <see cref="FailedResultOutcome"/> with FastAPI-style
    /// <c>detail</c> array preserved in
    /// <see cref="GenerationError.ProviderDetail"/>.
    ///
    /// Phase 0 evidence: fal queue's <c>COMPLETED</c> state is terminal,
    /// not success. P4_validation_rejection captured a
    /// <c>COMPLETED</c> lifecycle whose <c>response_url</c> then
    /// returned HTTP 422. Success vs failure is discriminated at the
    /// fetch step, not by reading the lifecycle state alone.
    /// </summary>
    public class FalQueueErrorAtFetchProviderFake
    {
        private sealed class Fake : IGenerationProvider<TestGenerationRequest, TestCapability>
        {
            public string ProviderName => "fal-queue-error-fake";

            public Task<ProviderSubmitOutcome> SubmitAsync(
                TestGenerationRequest request,
                IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
                CancellationToken ct) =>
                Task.FromResult<ProviderSubmitOutcome>(new QueuedSubmitOutcome(
                    new ProviderJobHandle(
                        providerJobId: "fal-err-job-xyz",
                        responseUrl: new Uri("https://queue.fal.run/response/xyz"))));

            public Task<ProviderStatusOutcome> GetStatusAsync(
                ProviderJobHandle handle, CancellationToken ct) =>
                Task.FromResult<ProviderStatusOutcome>(new ProviderCompleteStatusOutcome(handle));

            public Task<ProviderCancelOutcome> CancelAsync(
                ProviderJobHandle handle, CancellationToken ct) =>
                Task.FromResult<ProviderCancelOutcome>(new AlreadyTerminalOutcome(
                    GenerationLifecycleState.Failed));

            public Task<ProviderResultOutcome> FetchResultAsync(
                ProviderJobHandle handle, CancellationToken ct)
            {
                var detailItem = new JsonObject
                {
                    ["loc"] = new JsonArray("body", "input_image_url"),
                    ["msg"] = "Image must be at least 128x128 pixels",
                    ["type"] = "value_error",
                    ["url"] = "https://errors.pydantic.dev/2.5/v/value_error",
                };
                var providerDetail = new Dictionary<string, JsonNode>
                {
                    ["detail"] = new JsonArray(detailItem),
                    ["http_status"] = 422,
                };
                var error = new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "Image must be at least 128x128 pixels",
                    Retryable: false,
                    Field: "input_image_url",
                    ProviderErrorCode: "value_error",
                    ProviderDetail: providerDetail);
                return Task.FromResult<ProviderResultOutcome>(new FailedResultOutcome(error));
            }
        }

        [Fact]
        public async Task Lifecycle_reaches_complete_but_fetch_returns_failed()
        {
            var fake = new Fake();
            var request = new TestGenerationRequest("test-model", new TestProviderOptions());

            var submit = await fake.SubmitAsync(
                request, new Dictionary<MediaRef, ResolvedMedia>(), CancellationToken.None);
            var status = await fake.GetStatusAsync(
                ((QueuedSubmitOutcome)submit).Handle, CancellationToken.None);
            var complete = Assert.IsType<ProviderCompleteStatusOutcome>(status);

            var fetch = await fake.FetchResultAsync(complete.UpdatedHandle, CancellationToken.None);

            var failed = Assert.IsType<FailedResultOutcome>(fetch);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("value_error", failed.Error.ProviderErrorCode);
            Assert.NotNull(failed.Error.ProviderDetail);
            Assert.True(failed.Error.ProviderDetail!.ContainsKey("detail"));
        }
    }
}
