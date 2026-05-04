using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Image.Jobs;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Jobs
{
    public class ImageJobLedgerRecordFactoryTests
    {
        [Fact]
        public void FromInitial_builds_operational_record_without_provider_job_id()
        {
            var now = DateTimeOffset.Parse("2026-05-04T12:00:00Z");
            var record = ImageJobLedgerRecordFactory.FromInitial(
                Guid.Parse("11111111-1111-1111-1111-111111111111"),
                GeminiImageCapabilities.ProviderName,
                GeminiImageCapabilities.DefaultModel,
                ImageJobState.Queued,
                now);

            Assert.Equal(ImageJobLedgerRecordFactory.CurrentSchemaVersion, record.SchemaVersion);
            Assert.Equal(ImageJobState.Queued, record.State);
            Assert.Equal("gemini", record.Provider);
            Assert.Equal(GeminiImageCapabilities.DefaultModel, record.Model);
            Assert.Null(record.ProviderJobId);
            Assert.Null(record.ResultArtifactId);
            Assert.Null(record.Error);
            Assert.Equal(now, record.CreatedAt);
            Assert.Equal(now, record.UpdatedAt);
        }

        [Fact]
        public void WithState_carries_forward_safe_fields_only()
        {
            var now = DateTimeOffset.Parse("2026-05-04T12:00:00Z");
            var later = now.AddSeconds(2);
            var initial = ImageJobLedgerRecordFactory.FromInitial(
                Guid.Parse("22222222-2222-2222-2222-222222222222"),
                "replicate",
                "black-forest-labs/flux-schnell",
                ImageJobState.Queued,
                now);

            var next = ImageJobLedgerRecordFactory.WithState(
                initial,
                ImageJobState.Polling,
                later,
                providerJobId: "prediction-123");

            Assert.Equal(initial.JobId, next.JobId);
            Assert.Equal(initial.CreatedAt, next.CreatedAt);
            Assert.Equal(later, next.UpdatedAt);
            Assert.Equal("prediction-123", next.ProviderJobId);
            Assert.Null(next.ResultArtifactId);
        }

        [Fact]
        public void WithState_redacts_unsafe_error_message_and_drops_provider_detail()
        {
            var initial = ImageJobLedgerRecordFactory.FromInitial(
                Guid.Parse("33333333-3333-3333-3333-333333333333"),
                "replicate",
                "black-forest-labs/flux-schnell",
                ImageJobState.Polling,
                DateTimeOffset.Parse("2026-05-04T12:00:00Z"));
            var error = new GenerationError(
                GenerationErrorCode.DependencyUnavailable,
                "Provider returned urls.get=https://api.replicate.com/v1/predictions/x and https://replicate.delivery/out.png",
                Retryable: false,
                Field: "provider",
                ProviderErrorCode: "E123",
                ProviderDetail: new System.Collections.Generic.Dictionary<string, JsonNode>
                {
                    ["raw"] = JsonValue.Create("secret-detail")!,
                });

            var next = ImageJobLedgerRecordFactory.WithState(
                initial,
                ImageJobState.Error,
                initial.UpdatedAt.AddSeconds(1),
                error: error);

            Assert.NotNull(next.Error);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, next.Error!.Code);
            Assert.Equal("Image job failed; provider details were redacted.", next.Error.Message);
            Assert.Equal("provider", next.Error.Field);
            Assert.Equal("E123", next.Error.ProviderErrorCode);
            Assert.Null(next.Error.ProviderDetail);
            Assert.DoesNotContain("urls.get", next.Error.Message);
            Assert.DoesNotContain("replicate.delivery", next.Error.Message);
            Assert.DoesNotContain("api.replicate.com", next.Error.Message);
        }

        [Fact]
        public void WithState_drops_long_provider_error_code()
        {
            var initial = ImageJobLedgerRecordFactory.FromInitial(
                Guid.Parse("44444444-4444-4444-4444-444444444444"),
                "replicate",
                "black-forest-labs/flux-schnell",
                ImageJobState.Polling,
                DateTimeOffset.Parse("2026-05-04T12:00:00Z"));
            var error = new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                "plain failure",
                Retryable: false,
                ProviderErrorCode: new string('x', 128));

            var next = ImageJobLedgerRecordFactory.WithState(
                initial,
                ImageJobState.Error,
                initial.UpdatedAt.AddSeconds(1),
                error: error);

            Assert.Null(next.Error!.ProviderErrorCode);
            Assert.Equal("plain failure", next.Error.Message);
        }
    }
}
