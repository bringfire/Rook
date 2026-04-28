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
    /// fal-queue-shape fake: <see cref="QueuedSubmitOutcome"/> →
    /// <see cref="InFlightStatusOutcome"/>(Pending) →
    /// <see cref="InFlightStatusOutcome"/>(Running) →
    /// <see cref="ProviderCompleteStatusOutcome"/> →
    /// <see cref="SuccessResultOutcome"/>. The result lives at
    /// <see cref="ProviderJobHandle.ResponseUrl"/>; the manager fetches
    /// from there in production. In this fake the bytes ride inline so
    /// the test can observe envelope shape without HTTP.
    ///
    /// Phase 0 evidence: fal queue uses UPPERCASE state names + separate
    /// <c>response_url</c> fetch step.
    /// </summary>
    public class FalQueueShapeProviderFake
    {
        private sealed class Fake : IGenerationProvider<TestGenerationRequest, TestCapability>
        {
            public string ProviderName => "fal-queue-fake";

            private int _statusCallCount;

            public Task<ProviderSubmitOutcome> SubmitAsync(
                TestGenerationRequest request,
                IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
                CancellationToken ct)
            {
                var handle = new ProviderJobHandle(
                    providerJobId: "fal-job-abc123",
                    statusUrl: new Uri("https://queue.fal.run/status/abc123"),
                    responseUrl: new Uri("https://queue.fal.run/response/abc123"),
                    cancelUrl: new Uri("https://queue.fal.run/cancel/abc123"),
                    cancelHttpMethod: "PUT");
                return Task.FromResult<ProviderSubmitOutcome>(new QueuedSubmitOutcome(handle));
            }

            public Task<ProviderStatusOutcome> GetStatusAsync(
                ProviderJobHandle handle, CancellationToken ct)
            {
                _statusCallCount++;
                return _statusCallCount switch
                {
                    1 => Task.FromResult<ProviderStatusOutcome>(
                        new InFlightStatusOutcome(GenerationLifecycleState.Pending,
                            new GenerationProgress(QueuePosition: 3))),
                    2 => Task.FromResult<ProviderStatusOutcome>(
                        new InFlightStatusOutcome(GenerationLifecycleState.Running, null)),
                    _ => Task.FromResult<ProviderStatusOutcome>(
                        new ProviderCompleteStatusOutcome(handle)),
                };
            }

            public Task<ProviderCancelOutcome> CancelAsync(
                ProviderJobHandle handle, CancellationToken ct) =>
                Task.FromResult<ProviderCancelOutcome>(new CanceledOutcome());

            public Task<ProviderResultOutcome> FetchResultAsync(
                ProviderJobHandle handle, CancellationToken ct)
            {
                var artifact = new ResultArtifact(
                    Role: "image",
                    Body: new InlineArtifactBody(new byte[] { 0xFF, 0xD8, 0xFF }),
                    DeclaredMimeType: "image/jpeg",
                    ProviderMetadata: new Dictionary<string, JsonNode>
                    {
                        ["width"] = 1024,
                        ["height"] = 1024,
                    });
                var envelope = new ProviderResultEnvelope(
                    Artifacts: new[] { artifact },
                    EnvelopeMetadata: new Dictionary<string, JsonNode>
                    {
                        ["seed"] = 42,
                    });
                return Task.FromResult<ProviderResultOutcome>(new SuccessResultOutcome(envelope));
            }
        }

        [Fact]
        public async Task Submit_yields_queued_with_full_handle()
        {
            var fake = new Fake();
            var request = new TestGenerationRequest("test-model", new TestProviderOptions());

            var outcome = await fake.SubmitAsync(
                request,
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("fal-job-abc123", queued.Handle.ProviderJobId);
            Assert.NotNull(queued.Handle.StatusUrl);
            Assert.NotNull(queued.Handle.ResponseUrl);
            Assert.NotNull(queued.Handle.CancelUrl);
            Assert.Equal("PUT", queued.Handle.CancelHttpMethod);
        }

        [Fact]
        public async Task Status_then_complete_then_fetch_round_trips_envelope()
        {
            var fake = new Fake();
            var request = new TestGenerationRequest("test-model", new TestProviderOptions());
            var submit = await fake.SubmitAsync(
                request, new Dictionary<MediaRef, ResolvedMedia>(), CancellationToken.None);
            var handle = ((QueuedSubmitOutcome)submit).Handle;

            var s1 = await fake.GetStatusAsync(handle, CancellationToken.None);
            var s2 = await fake.GetStatusAsync(handle, CancellationToken.None);
            var s3 = await fake.GetStatusAsync(handle, CancellationToken.None);

            Assert.Equal(GenerationLifecycleState.Pending, ((InFlightStatusOutcome)s1).State);
            Assert.Equal(GenerationLifecycleState.Running, ((InFlightStatusOutcome)s2).State);
            var complete = Assert.IsType<ProviderCompleteStatusOutcome>(s3);

            var fetch = await fake.FetchResultAsync(complete.UpdatedHandle, CancellationToken.None);
            var success = Assert.IsType<SuccessResultOutcome>(fetch);
            Assert.Single(success.Envelope.Artifacts);
            Assert.Equal("image", success.Envelope.Artifacts[0].Role);
            Assert.IsType<InlineArtifactBody>(success.Envelope.Artifacts[0].Body);
        }
    }
}
