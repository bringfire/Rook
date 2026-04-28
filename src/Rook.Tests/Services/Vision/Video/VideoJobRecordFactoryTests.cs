using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    /// <summary>
    /// V1c factory contract: takes <see cref="ResolvedVideoModel"/> +
    /// already-computed <see cref="VideoCostEstimate"/>, produces a
    /// durable <see cref="VideoJobRecord"/> by:
    /// <list type="bullet">
    ///   <item><description>Provider name from <c>model.ProviderName</c></description></item>
    ///   <item><description>Provider options blob from <c>model.OptionsCodec.Serialize</c></description></item>
    ///   <item><description><see cref="VideoJobRecord.Pricing"/> copied verbatim
    ///     from <c>estimate.Pricing</c> (no recompute)</description></item>
    /// </list>
    /// </summary>
    public class VideoJobRecordFactoryTests
    {
        private static readonly DateTimeOffset T0 = new(2026, 4, 25, 12, 0, 0, TimeSpan.Zero);

        // Helpers — tests build a real estimator-produced estimate so the
        // pricing snapshot carried into the factory matches the production
        // single-pass flow. Avoids hand-fabricating a JobPricing.
        private static VideoCostEstimate EstimateFor(
            ResolvedVideoModel model, VideoGenerationRequest req)
        {
            var result = new VideoCostEstimator().Estimate(model, req);
            Assert.True(result.Success, $"Estimator failed: {result.Error?.Message}");
            return result.Estimate!;
        }

        // ─── Initial record shape ─────────────────────────────────────

        [Fact]
        public void From_initial_record_has_null_provider_job_id_and_null_token()
        {
            var jobId = Guid.NewGuid();
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();

            var rec = VideoJobRecordFactory.From(
                jobId, req, model, EstimateFor(model, req),
                VideoJobState.Queued, T0);

            Assert.Equal(jobId, rec.JobId);
            Assert.Null(rec.ProviderJobId);
            Assert.Null(rec.ProviderResultToken);
            Assert.Null(rec.ResultArtifactId);
            Assert.Null(rec.Error);
        }

        [Fact]
        public void From_provider_field_comes_from_resolved_model()
        {
            // Guardrail #3: Veo provider name pinned to "veo".
            var jobId = Guid.NewGuid();
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();

            var rec = VideoJobRecordFactory.From(
                jobId, req, model, EstimateFor(model, req),
                VideoJobState.Queued, T0);

            Assert.Equal("veo", rec.Provider);
        }

        [Fact]
        public void From_persists_neutral_request_shape()
        {
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();

            var rec = VideoJobRecordFactory.From(
                Guid.NewGuid(), req, model, EstimateFor(model, req),
                VideoJobState.Queued, T0);

            Assert.Equal(VideoMode.T2V, rec.NormalizedRequest.Mode);
            Assert.Equal(8, rec.NormalizedRequest.DurationSeconds);
            Assert.Equal("720p", rec.NormalizedRequest.Resolution);
            Assert.Equal("16:9", rec.NormalizedRequest.AspectRatio);
            Assert.Equal("a clip", rec.NormalizedRequest.Prompt);
            Assert.Equal(1, rec.NormalizedRequest.NumberOfVideos);
        }

        [Fact]
        public void From_provider_options_serialized_via_codec()
        {
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();

            var rec = VideoJobRecordFactory.From(
                Guid.NewGuid(), req, model, EstimateFor(model, req),
                VideoJobState.Queued, T0);

            Assert.NotNull(rec.ProviderOptions["person_generation"]);
            Assert.Equal("allow_all", rec.ProviderOptions["person_generation"]!.GetValue<string>());
        }

        [Fact]
        public void From_pricing_field_is_estimate_pricing_verbatim()
        {
            // Single-pass audit invariant: the factory copies
            // estimate.Pricing into VideoJobRecord.Pricing without
            // recomputing.
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();
            var estimate = EstimateFor(model, req);

            var rec = VideoJobRecordFactory.From(
                Guid.NewGuid(), req, model, estimate,
                VideoJobState.Queued, T0);

            Assert.Same(estimate.Pricing, rec.Pricing);
        }

        [Fact]
        public void From_pricing_for_veo_lite_t2v_8s_has_expected_per_second_values()
        {
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();

            var rec = VideoJobRecordFactory.From(
                Guid.NewGuid(), req, model, EstimateFor(model, req),
                VideoJobState.Queued, T0);

            Assert.Equal(PricingKind.PerSecond, rec.Pricing.Kind);
            Assert.Equal("USD", rec.Pricing.Currency);
            Assert.Equal(8, rec.Pricing.Quantity);
            Assert.Equal(0.40m, rec.Pricing.TotalUsd);
            Assert.Equal(0.05m, rec.Pricing.UnitPriceUsd);
            Assert.Equal("veo-rate-card-v1", rec.Pricing.PricingSource);
        }

        [Fact]
        public void From_includes_schema_version_and_timestamps()
        {
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();

            var rec = VideoJobRecordFactory.From(
                Guid.NewGuid(), req, model, EstimateFor(model, req),
                VideoJobState.Queued, T0);

            Assert.Equal(VideoJobRecordFactory.CurrentSchemaVersion, rec.SchemaVersion);
            Assert.Equal(T0, rec.CreatedAt);
            Assert.Equal(T0, rec.UpdatedAt);
        }

        // ─── WithState transitions ────────────────────────────────────

        [Fact]
        public void WithState_preserves_CreatedAt_and_advances_UpdatedAt()
        {
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();
            var initial = VideoJobRecordFactory.From(
                Guid.NewGuid(), req, model, EstimateFor(model, req),
                VideoJobState.Queued, T0);
            var t1 = T0.AddSeconds(30);

            var next = VideoJobRecordFactory.WithState(initial, VideoJobState.Submitting, t1);

            Assert.Equal(VideoJobState.Submitting, next.State);
            Assert.Equal(T0, next.CreatedAt);
            Assert.Equal(t1, next.UpdatedAt);
        }

        [Fact]
        public void WithState_threading_provider_job_id_persists_it()
        {
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();
            var initial = VideoJobRecordFactory.From(
                Guid.NewGuid(), req, model, EstimateFor(model, req),
                VideoJobState.Submitting, T0);

            var next = VideoJobRecordFactory.WithState(
                initial, VideoJobState.Polling, T0.AddSeconds(1),
                providerJobId: "operations/abc-123");

            Assert.Equal("operations/abc-123", next.ProviderJobId);
        }

        [Fact]
        public void WithState_threading_provider_result_token_persists_it()
        {
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();
            var initial = VideoJobRecordFactory.From(
                Guid.NewGuid(), req, model, EstimateFor(model, req),
                VideoJobState.Polling, T0);

            var next = VideoJobRecordFactory.WithState(
                initial, VideoJobState.Downloading, T0.AddSeconds(60),
                providerResultToken: "https://veo/result/xyz");

            Assert.Equal("https://veo/result/xyz", next.ProviderResultToken);
        }

        [Fact]
        public void WithState_plain_veo_handle_does_not_create_provider_handle_extension()
        {
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();
            var initial = VideoJobRecordFactory.From(
                Guid.NewGuid(), req, model, EstimateFor(model, req),
                VideoJobState.Submitting, T0);
            var handle = new ProviderJobHandle("operations/abc-123");

            var next = VideoJobRecordFactory.WithState(
                initial,
                VideoJobState.Polling,
                T0.AddSeconds(1),
                providerHandle: handle);

            Assert.Equal("operations/abc-123", next.ProviderJobId);
            Assert.Null(next.ProviderResultToken);
            Assert.Null(next.Extensions?["provider_handle"]);
        }

        [Fact]
        public void WithState_url_handle_creates_provider_handle_extension()
        {
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();
            var initial = VideoJobRecordFactory.From(
                Guid.NewGuid(), req, model, EstimateFor(model, req),
                VideoJobState.Submitting, T0);
            var metadata = new Dictionary<string, JsonNode>
            {
                ["queue_position"] = JsonValue.Create(4)!,
            };
            var handle = new ProviderJobHandle(
                providerJobId: "queue-123",
                statusUrl: new Uri("https://provider.test/status/queue-123"),
                responseUrl: new Uri("https://provider.test/result/queue-123"),
                cancelUrl: new Uri("https://provider.test/cancel/queue-123"),
                cancelHttpMethod: "put",
                providerMetadata: metadata);

            var next = VideoJobRecordFactory.WithState(
                initial,
                VideoJobState.Polling,
                T0.AddSeconds(1),
                providerHandle: handle);

            Assert.Equal("queue-123", next.ProviderJobId);
            var persistedHandle = Assert.IsType<JsonObject>(next.Extensions?["provider_handle"]);
            Assert.Equal(
                "https://provider.test/status/queue-123",
                persistedHandle["status_url"]!.GetValue<string>());
            Assert.Equal(
                "https://provider.test/result/queue-123",
                persistedHandle["response_url"]!.GetValue<string>());
            Assert.Equal(
                "https://provider.test/cancel/queue-123",
                persistedHandle["cancel_url"]!.GetValue<string>());
            Assert.Equal("PUT", persistedHandle["cancel_http_method"]!.GetValue<string>());
            Assert.Equal(4, persistedHandle["provider_metadata"]!["queue_position"]!.GetValue<int>());
        }

        [Fact]
        public void WithState_threading_result_artifact_id_persists_it()
        {
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();
            var initial = VideoJobRecordFactory.From(
                Guid.NewGuid(), req, model, EstimateFor(model, req),
                VideoJobState.Saving, T0);
            var artifactId = Guid.NewGuid();

            var next = VideoJobRecordFactory.WithState(
                initial, VideoJobState.Complete, T0.AddSeconds(120),
                resultArtifactId: artifactId);

            Assert.Equal(artifactId, next.ResultArtifactId);
            Assert.Equal(VideoJobState.Complete, next.State);
        }

        [Fact]
        public void WithState_error_accepts_generation_error()
        {
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();
            var initial = VideoJobRecordFactory.From(
                Guid.NewGuid(), req, model, EstimateFor(model, req),
                VideoJobState.Polling, T0);
            var error = new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                "provider failed",
                Retryable: true,
                ProviderDetail: new Dictionary<string, JsonNode>
                {
                    ["provider_message"] = JsonValue.Create("raw provider body")!,
                });

            var next = VideoJobRecordFactory.WithState(
                initial,
                VideoJobState.Error,
                T0.AddSeconds(2),
                error: error);

            Assert.Same(error, next.Error);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, next.Error!.Code);
        }

        // ─── Media ref normalization ──────────────────────────────────

        [Fact]
        public void From_with_media_refs_normalizes_to_NormalizedMediaRef()
        {
            var artId = Guid.NewGuid();
            var model = TestVideoFixtures.VeoLiteResolved(modelId: "veo-3.1-generate-preview");
            // Use full 3.1 (supports I2V) with AllowAdult per Veo rule
            var req = TestVideoFixtures.DefaultT2vRequest(
                model: "veo-3.1-generate-preview",
                mode: VideoMode.I2V,
                prompt: null,
                startFrame: VideoMediaRef.ForArtifact(artId, VideoMediaRoles.Image),
                personGeneration: PersonGenerationPolicy.AllowAdult);

            var rec = VideoJobRecordFactory.From(
                Guid.NewGuid(), req, model, EstimateFor(model, req),
                VideoJobState.Queued, T0);

            Assert.NotNull(rec.NormalizedRequest.StartFrame);
            Assert.Equal(VideoMediaRefKind.Artifact, rec.NormalizedRequest.StartFrame!.Kind);
            Assert.Equal(artId, rec.NormalizedRequest.StartFrame.ArtifactId);
            Assert.Equal("image", rec.NormalizedRequest.StartFrame.Role);
        }

        // ─── Argument validation ──────────────────────────────────────

        [Fact]
        public void From_rejects_empty_jobId()
        {
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();

            Assert.Throws<ArgumentException>(() =>
                VideoJobRecordFactory.From(
                    Guid.Empty, req, model, EstimateFor(model, req),
                    VideoJobState.Queued, T0));
        }

        [Fact]
        public void From_rejects_null_request()
        {
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();
            var estimate = EstimateFor(model, req);

            Assert.Throws<ArgumentNullException>(() =>
                VideoJobRecordFactory.From(
                    Guid.NewGuid(), null!, model, estimate,
                    VideoJobState.Queued, T0));
        }

        [Fact]
        public void From_rejects_null_model()
        {
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();
            var estimate = EstimateFor(model, req);

            Assert.Throws<ArgumentNullException>(() =>
                VideoJobRecordFactory.From(
                    Guid.NewGuid(), req, null!, estimate,
                    VideoJobState.Queued, T0));
        }

        [Fact]
        public void From_rejects_null_estimate()
        {
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();

            Assert.Throws<ArgumentNullException>(() =>
                VideoJobRecordFactory.From(
                    Guid.NewGuid(), req, model, estimate: null!,
                    VideoJobState.Queued, T0));
        }
    }
}
