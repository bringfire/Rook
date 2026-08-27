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
    /// Gemini-sync-shape fake: <see cref="SyncSubmitOutcome"/> with the
    /// full result inline at submit. No job handle, no poll, no fetch.
    /// The inner <see cref="SuccessResultOutcome"/> carries
    /// <see cref="InlineArtifactBody"/> (Gemini returns base64 in the
    /// API response).
    ///
    /// Phase 0 evidence (B1): Gemini's
    /// <c>gemini-3.1-flash-image</c> returns
    /// <c>candidates[0].content.parts[0].inlineData.data</c> as base64,
    /// no follow-up fetch.
    /// </summary>
    public class GeminiSyncShapeProviderFake
    {
        private sealed class Fake : IGenerationProvider<TestGenerationRequest, TestCapability>
        {
            public string ProviderName => "gemini-fake";

            public Task<ProviderSubmitOutcome> SubmitAsync(
                TestGenerationRequest request,
                IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
                CancellationToken ct)
            {
                var artifact = new ResultArtifact(
                    Role: "image",
                    Body: new InlineArtifactBody(new byte[] { 0x89, 0x50, 0x4E, 0x47 }),
                    DeclaredMimeType: "image/png",
                    ProviderMetadata: new Dictionary<string, JsonNode>
                    {
                        ["finishReason"] = "STOP",
                        ["thoughtSignature"] = "abc",
                    });
                var envelope = new ProviderResultEnvelope(
                    Artifacts: new[] { artifact },
                    EnvelopeMetadata: new Dictionary<string, JsonNode>
                    {
                        ["modelVersion"] = "gemini-3.1-flash-image",
                        ["responseId"] = "resp-xyz",
                        ["usageMetadata"] = new JsonObject
                        {
                            ["promptTokenCount"] = 12,
                            ["candidatesTokenCount"] = 1290,
                        },
                    });
                return Task.FromResult<ProviderSubmitOutcome>(
                    new SyncSubmitOutcome(new SuccessResultOutcome(envelope)));
            }

            public Task<ProviderStatusOutcome> GetStatusAsync(
                ProviderJobHandle handle, CancellationToken ct) =>
                throw new InvalidOperationException("Sync provider has no status step.");

            public Task<ProviderCancelOutcome> CancelAsync(
                ProviderJobHandle handle, CancellationToken ct) =>
                throw new InvalidOperationException("Sync provider has no cancel step.");

            public Task<ProviderResultOutcome> FetchResultAsync(
                ProviderJobHandle handle, CancellationToken ct) =>
                throw new InvalidOperationException("Sync provider has no fetch step.");
        }

        [Fact]
        public async Task Submit_returns_sync_outcome_with_inline_envelope()
        {
            var fake = new Fake();
            var request = new TestGenerationRequest("test-model", new TestProviderOptions());

            var outcome = await fake.SubmitAsync(
                request, new Dictionary<MediaRef, ResolvedMedia>(), CancellationToken.None);

            var sync = Assert.IsType<SyncSubmitOutcome>(outcome);
            var success = Assert.IsType<SuccessResultOutcome>(sync.Result);
            Assert.Single(success.Envelope.Artifacts);
            Assert.IsType<InlineArtifactBody>(success.Envelope.Artifacts[0].Body);
            Assert.Equal("image/png", success.Envelope.Artifacts[0].DeclaredMimeType);
            Assert.True(success.Envelope.EnvelopeMetadata.ContainsKey("usageMetadata"));
        }
    }
}
