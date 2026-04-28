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
    /// Replicate-prediction-shape fake: terminal poll embeds the result
    /// URL in <see cref="ProviderJobHandle.ProviderResultToken"/>;
    /// <see cref="ProviderJobHandle.ResponseUrl"/> is null because no
    /// separate fetch endpoint exists. <see cref="FetchResultAsync"/>
    /// uses the token directly.
    ///
    /// Phase 0 evidence: Replicate uses lowercase state names; terminal
    /// poll body INCLUDES <c>output: [&lt;url&gt;]</c>. Pricing rides
    /// in the body via <c>metrics.predict_time</c>.
    /// </summary>
    public class ReplicatePredictionShapeProviderFake
    {
        private sealed class Fake : IGenerationProvider<TestGenerationRequest, TestCapability>
        {
            public string ProviderName => "replicate-fake";

            private int _statusCallCount;

            public Task<ProviderSubmitOutcome> SubmitAsync(
                TestGenerationRequest request,
                IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
                CancellationToken ct) =>
                Task.FromResult<ProviderSubmitOutcome>(new QueuedSubmitOutcome(
                    new ProviderJobHandle(
                        providerJobId: "replicate-prediction-zzz",
                        statusUrl: new Uri("https://api.replicate.com/v1/predictions/zzz"),
                        cancelUrl: new Uri("https://api.replicate.com/v1/predictions/zzz/cancel"),
                        cancelHttpMethod: "POST")));

            public Task<ProviderStatusOutcome> GetStatusAsync(
                ProviderJobHandle handle, CancellationToken ct)
            {
                _statusCallCount++;
                if (_statusCallCount < 2)
                {
                    return Task.FromResult<ProviderStatusOutcome>(
                        new InFlightStatusOutcome(GenerationLifecycleState.Running, null));
                }

                // Terminal: stamp the embedded output URL onto an
                // updated handle. ResponseUrl stays null — Replicate
                // has no separate fetch endpoint.
                var updated = handle with
                {
                    ProviderResultToken = "https://replicate.delivery/pbxt/zzz/output.png",
                };
                return Task.FromResult<ProviderStatusOutcome>(
                    new ProviderCompleteStatusOutcome(updated));
            }

            public Task<ProviderCancelOutcome> CancelAsync(
                ProviderJobHandle handle, CancellationToken ct) =>
                Task.FromResult<ProviderCancelOutcome>(new CanceledOutcome());

            public Task<ProviderResultOutcome> FetchResultAsync(
                ProviderJobHandle handle, CancellationToken ct)
            {
                Assert.NotNull(handle.ProviderResultToken);

                var artifact = new ResultArtifact(
                    Role: "image",
                    Body: new RemoteArtifactBody(new Uri(handle.ProviderResultToken!)),
                    DeclaredMimeType: null,                                     // flat URL list — no MIME at submit
                    ProviderMetadata: new Dictionary<string, JsonNode>());
                var envelope = new ProviderResultEnvelope(
                    Artifacts: new[] { artifact },
                    EnvelopeMetadata: new Dictionary<string, JsonNode>
                    {
                        ["metrics"] = new JsonObject
                        {
                            ["predict_time"] = 0.507,
                            ["total_time"] = 0.543,
                        },
                    });
                return Task.FromResult<ProviderResultOutcome>(new SuccessResultOutcome(envelope));
            }
        }

        [Fact]
        public async Task Terminal_poll_stamps_token_and_response_url_remains_null()
        {
            var fake = new Fake();
            var request = new TestGenerationRequest("test-model", new TestProviderOptions());

            var submit = await fake.SubmitAsync(
                request, new Dictionary<MediaRef, ResolvedMedia>(), CancellationToken.None);
            var handle = ((QueuedSubmitOutcome)submit).Handle;
            Assert.Null(handle.ResponseUrl);
            Assert.Null(handle.ProviderResultToken);

            await fake.GetStatusAsync(handle, CancellationToken.None);
            var status = await fake.GetStatusAsync(handle, CancellationToken.None);
            var complete = Assert.IsType<ProviderCompleteStatusOutcome>(status);

            Assert.Null(complete.UpdatedHandle.ResponseUrl);
            Assert.NotNull(complete.UpdatedHandle.ProviderResultToken);

            var fetch = await fake.FetchResultAsync(complete.UpdatedHandle, CancellationToken.None);
            var success = Assert.IsType<SuccessResultOutcome>(fetch);
            Assert.IsType<RemoteArtifactBody>(success.Envelope.Artifacts[0].Body);
            Assert.Null(success.Envelope.Artifacts[0].DeclaredMimeType);   // manager will sniff at fetch
        }
    }
}
