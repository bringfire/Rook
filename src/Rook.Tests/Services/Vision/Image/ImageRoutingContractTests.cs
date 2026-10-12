using System;
using System.IO;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Jobs;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public sealed class ImageRoutingContractTests : IDisposable
    {
        private readonly string _root = Path.Combine(Path.GetTempPath(), "rook-routing-" + Guid.NewGuid().ToString("N"));
        public void Dispose() { if (Directory.Exists(_root)) Directory.Delete(_root, true); }
        private JsonlImageJobLedger Ledger() => new(Path.Combine(_root, "ledger.jsonl"));
        private static ImageRouteReceipt Route() => new(
            "gemini", "gemini-3.1-flash-image-preview", "fal", "fal-ai/nano-banana-2",
            "fal-ai/nano-banana-2/edit", ImageFallbackReason.GeminiKeyMissing,
            ImageExecutionPhase.Validation, false);
        private static ImageJobLedgerRecord Record(ImageRouteReceipt? route = null,
            ImageCredentialFailure? failure = null, ImageFalDispatchState? dispatch = null) => new(
                1, Guid.NewGuid(), "fal", "fal-ai/nano-banana-2", null,
                ImageJobState.Submitting, null, null, DateTimeOffset.UtcNow,
                DateTimeOffset.UtcNow, route, failure, dispatch);

        [Fact]
        public void RoutingRoundTrip_KeepsRequestedAndEffectiveRoute()
        {
            var ledger = Ledger();
            ledger.Append(Record(Route(), dispatch: ImageFalDispatchState.IntentRecorded));
            var read = new JsonlImageJobLedger(ledger.FilePath).ReadAll();
            Assert.Empty(read.Errors);
            var record = Assert.Single(read.Records);
            Assert.Equal("gemini", record.ImageRoute!.RequestedProvider);
            Assert.Equal("gemini-3.1-flash-image-preview", record.ImageRoute.RequestedModel);
            Assert.Equal("fal", record.Provider);
            Assert.Equal("fal-ai/nano-banana-2/edit", record.ImageRoute.ProviderEndpoint);
            Assert.Equal(1, record.SchemaVersion);
        }

        [Fact]
        public void LegacyV1_HasNoFabricatedReceipt()
        {
            var ledger = Ledger();
            ledger.Append(Record());
            var record = Assert.Single(ledger.ReadAll().Records);
            Assert.Null(record.ImageRoute);
            Assert.Null(record.CredentialFailure);
            Assert.Null(record.FalDispatchState);
        }

        [Theory]
        [InlineData(ImageCredentialFailureKind.Missing)]
        [InlineData(ImageCredentialFailureKind.Rejected)]
        public void DirectFalCredentialEvidence_RoundTripsWithoutReceipt(ImageCredentialFailureKind kind)
        {
            var ledger = Ledger();
            ledger.Append(Record(failure: new ImageCredentialFailure("fal", kind)));
            var read = ledger.ReadAll();
            Assert.Empty(read.Errors);
            var record = Assert.Single(read.Records);
            Assert.Null(record.ImageRoute);
            Assert.Equal("fal", record.CredentialFailure!.Provider);
            Assert.Equal(kind, record.CredentialFailure.Kind);
        }

        [Fact]
        public void DispatchIntent_RoundTripsWithoutClaimingSend()
        {
            var ledger = Ledger();
            ledger.Append(Record(Route(), dispatch: ImageFalDispatchState.IntentRecorded));
            var record = Assert.Single(ledger.ReadAll().Records);
            Assert.Equal(ImageFalDispatchState.IntentRecorded, record.FalDispatchState);
            Assert.False(record.ImageRoute!.GenerationDispatchAttempted);
        }

        [Theory]
        [InlineData("effective_provider", "gemini")]
        [InlineData("requested_provider", "unknown")]
        [InlineData("requested_model", "nano-banana-2")]
        [InlineData("effective_model", "fal-ai/nano-banana-pro")]
        [InlineData("provider_endpoint", "https://fal.run/fal-ai/nano-banana-2/edit")]
        [InlineData("fallback_reason", "timeout")]
        [InlineData("phase", "other")]
        [InlineData("secret", "fake-secret")]
        public void RoutingMismatchOrUnknownValue_IsReadError(string property, string value)
        {
            var ledger = Ledger();
            ledger.Append(Record(Route()));
            var obj = JsonNode.Parse(File.ReadAllText(ledger.FilePath))!.AsObject();
            obj["image_route"]![property] = value;
            File.WriteAllText(ledger.FilePath, obj.ToJsonString() + "\n");
            var result = ledger.ReadAll();
            Assert.Empty(result.Records);
            Assert.Single(result.Errors);
        }

        [Theory]
        [InlineData("\"bad\"")]
        [InlineData("42")]
        [InlineData("[]")]
        [InlineData("{\"provider\":\"gemini\",\"kind\":\"missing\"}")]
        [InlineData("{\"provider\":\"fal\",\"kind\":\"expired\"}")]
        [InlineData("{\"provider\":\"fal\",\"kind\":\"missing\",\"detail\":\"unsafe\"}")]
        public void MalformedOrWrongCredentialEvidence_IsReadError(string json)
        {
            var ledger = Ledger();
            ledger.Append(Record());
            var obj = JsonNode.Parse(File.ReadAllText(ledger.FilePath))!.AsObject();
            obj["credential_failure"] = JsonNode.Parse(json);
            File.WriteAllText(ledger.FilePath, obj.ToJsonString() + "\n");
            Assert.Empty(ledger.ReadAll().Records);
            Assert.Single(ledger.ReadAll().Errors);
        }

        [Theory]
        [InlineData("attempted", false)]
        [InlineData("not_started", true)]
        [InlineData("invented", false)]
        public void DispatchStateContradiction_IsReadError(string state, bool attempted)
        {
            var ledger = Ledger();
            ledger.Append(Record(Route()));
            var obj = JsonNode.Parse(File.ReadAllText(ledger.FilePath))!.AsObject();
            obj["fal_dispatch_state"] = state;
            obj["image_route"]!["generation_dispatch_attempted"] = attempted;
            File.WriteAllText(ledger.FilePath, obj.ToJsonString() + "\n");
            Assert.Empty(ledger.ReadAll().Records);
            Assert.Single(ledger.ReadAll().Errors);
        }

        [Fact]
        public void GenericFailure_ClearsPriorCredentialEvidenceAndRetainsIntent()
        {
            var prior = Record(Route(), new ImageCredentialFailure("fal", ImageCredentialFailureKind.Rejected),
                ImageFalDispatchState.IntentRecorded);
            var next = ImageJobLedgerRecordFactory.WithState(prior, ImageJobState.Interrupted,
                DateTimeOffset.UtcNow, routing: new ImageRoutingContext(prior.ImageRoute, null),
                falDispatchState: ImageFalDispatchState.NotStarted,
                error: new GenerationError(GenerationErrorCode.Interrupted, "Stopped.", false));
            Assert.Null(next.CredentialFailure);
            Assert.Equal(prior.ImageRoute, next.ImageRoute);
            Assert.Equal(ImageFalDispatchState.IntentRecorded, next.FalDispatchState);
        }

        [Fact]
        public void Serialization_DropsRawProviderDetailButKeepsSafeContext()
        {
            var ledger = Ledger();
            ledger.Append(Record(Route()) with { Error = new GenerationError(
                GenerationErrorCode.ExecutionFailed, "Failed.", false,
                ProviderDetail: new System.Collections.Generic.Dictionary<string, JsonNode>
                { ["prompt"] = JsonValue.Create("private-prompt")! }) });
            var text = File.ReadAllText(ledger.FilePath);
            Assert.DoesNotContain("private-prompt", text);
            Assert.DoesNotContain("provider_detail", text);
            Assert.Contains("\"requested_provider\":\"gemini\"", text);
        }

        [Fact]
        public void StatusProjection_RetainsDirectCredentialEvidenceWithoutReceipt()
        {
            var result = ImageJobStatusResult.Failed(ImageJobState.Error,
                new GenerationError(GenerationErrorCode.DependencyUnavailable, "Missing.", false))
                .WithRouting("fal", "fal-ai/nano-banana-2",
                    new ImageRoutingContext(null, new ImageCredentialFailure("fal", ImageCredentialFailureKind.Missing)),
                    ImageFalDispatchState.NotStarted);
            Assert.Equal("fal", result.Provider);
            Assert.Null(result.Routing!.Route);
            Assert.Equal(ImageCredentialFailureKind.Missing, result.Routing.CredentialFailure!.Kind);
        }

        [Fact]
        public void StaleRouteCannotRegressObservedDispatchOrPhase()
        {
            var prior = Record(Route() with { GenerationDispatchAttempted = true, Phase = ImageExecutionPhase.Materialization },
                dispatch: ImageFalDispatchState.Attempted);
            var next = ImageJobLedgerRecordFactory.WithState(prior, ImageJobState.Submitting, DateTimeOffset.UtcNow,
                routing: new ImageRoutingContext(Route(), null), falDispatchState: ImageFalDispatchState.NotStarted);
            Assert.True(next.ImageRoute!.GenerationDispatchAttempted);
            Assert.Equal(ImageExecutionPhase.Materialization, next.ImageRoute.Phase);
            Assert.Equal(ImageFalDispatchState.Attempted, next.FalDispatchState);
        }
    }
}
