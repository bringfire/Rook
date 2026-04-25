using System;
using System.Linq;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoJobRecordFactoryTests
    {
        private static readonly DateTimeOffset T0 = new(2026, 4, 25, 12, 0, 0, TimeSpan.Zero);

        private static VideoGenerationRequest BasicRequest() => new(
            Model: "veo-3.1-lite-generate-preview",
            Mode: VideoMode.T2V,
            DurationSeconds: 8,
            Resolution: "720p",
            AspectRatio: "16:9",
            Prompt: "a clip",
            StartFrame: null,
            EndFrame: null,
            ReferenceFrames: null,
            Seed: null,
            PersonGeneration: PersonGenerationPolicy.AllowAll,
            NumberOfVideos: 1);

        private static VideoCostEstimate BasicEstimate() => new(
            DollarsUsd: 0.40m,
            Model: "veo-3.1-lite-generate-preview",
            Resolution: "720p",
            DurationSeconds: 8,
            NumberOfVideos: 1,
            Breakdown: new[] { new CostBreakdownComponent("test", 0.40m) });

        [Fact]
        public void From_initial_record_has_null_provider_job_id_and_null_token()
        {
            var jobId = Guid.NewGuid();

            var rec = VideoJobRecordFactory.From(
                jobId, BasicRequest(), "veo", BasicEstimate(),
                VideoJobState.Queued, T0);

            Assert.Equal(jobId, rec.JobId);
            Assert.Null(rec.ProviderJobId);
            Assert.Null(rec.ProviderResultToken);
            Assert.Null(rec.ResultArtifactId);
            Assert.Null(rec.Error);
        }

        [Fact]
        public void From_persists_neutral_request_shape()
        {
            var rec = VideoJobRecordFactory.From(
                Guid.NewGuid(), BasicRequest(), "veo", BasicEstimate(),
                VideoJobState.Queued, T0);

            Assert.Equal(VideoMode.T2V, rec.NormalizedRequest.Mode);
            Assert.Equal(8, rec.NormalizedRequest.DurationSeconds);
            Assert.Equal("720p", rec.NormalizedRequest.Resolution);
            Assert.Equal("16:9", rec.NormalizedRequest.AspectRatio);
            Assert.Equal("a clip", rec.NormalizedRequest.Prompt);
            Assert.Equal(1, rec.NormalizedRequest.NumberOfVideos);
        }

        [Fact]
        public void From_puts_PersonGeneration_in_provider_options_not_normalized_request()
        {
            var rec = VideoJobRecordFactory.From(
                Guid.NewGuid(), BasicRequest(), "veo", BasicEstimate(),
                VideoJobState.Queued, T0);

            // Provider-specific field lives in provider_options.
            Assert.NotNull(rec.ProviderOptions["person_generation"]);
            Assert.Equal("allow_all", rec.ProviderOptions["person_generation"]!.GetValue<string>());
        }

        [Fact]
        public void From_pricing_for_veo_is_per_second_with_correct_quantity()
        {
            var req = BasicRequest() with { DurationSeconds = 8, NumberOfVideos = 1 };

            var rec = VideoJobRecordFactory.From(
                Guid.NewGuid(), req, "veo", BasicEstimate(),
                VideoJobState.Queued, T0);

            Assert.Equal(PricingKind.PerSecond, rec.Pricing.Kind);
            Assert.Equal("USD", rec.Pricing.Currency);
            Assert.Equal(8, rec.Pricing.Quantity);  // duration × count
            Assert.Equal(0.40m, rec.Pricing.TotalUsd);
            Assert.Equal(0.05m, rec.Pricing.UnitPriceUsd);
            Assert.Equal("veo-rate-card-v1", rec.Pricing.PricingSource);
        }

        [Fact]
        public void From_includes_schema_version_and_timestamps()
        {
            var rec = VideoJobRecordFactory.From(
                Guid.NewGuid(), BasicRequest(), "veo", BasicEstimate(),
                VideoJobState.Queued, T0);

            Assert.Equal(VideoJobRecordFactory.CurrentSchemaVersion, rec.SchemaVersion);
            Assert.Equal(T0, rec.CreatedAt);
            Assert.Equal(T0, rec.UpdatedAt);
        }

        [Fact]
        public void WithState_preserves_CreatedAt_and_advances_UpdatedAt()
        {
            var initial = VideoJobRecordFactory.From(
                Guid.NewGuid(), BasicRequest(), "veo", BasicEstimate(),
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
            var initial = VideoJobRecordFactory.From(
                Guid.NewGuid(), BasicRequest(), "veo", BasicEstimate(),
                VideoJobState.Submitting, T0);

            var next = VideoJobRecordFactory.WithState(
                initial, VideoJobState.Polling, T0.AddSeconds(1),
                providerJobId: "operations/abc-123");

            Assert.Equal("operations/abc-123", next.ProviderJobId);
        }

        [Fact]
        public void WithState_threading_provider_result_token_persists_it()
        {
            var initial = VideoJobRecordFactory.From(
                Guid.NewGuid(), BasicRequest(), "veo", BasicEstimate(),
                VideoJobState.Polling, T0);

            var next = VideoJobRecordFactory.WithState(
                initial, VideoJobState.Downloading, T0.AddSeconds(60),
                providerResultToken: "https://veo/result/xyz");

            Assert.Equal("https://veo/result/xyz", next.ProviderResultToken);
        }

        [Fact]
        public void WithState_threading_result_artifact_id_persists_it()
        {
            var initial = VideoJobRecordFactory.From(
                Guid.NewGuid(), BasicRequest(), "veo", BasicEstimate(),
                VideoJobState.Saving, T0);
            var artifactId = Guid.NewGuid();

            var next = VideoJobRecordFactory.WithState(
                initial, VideoJobState.Complete, T0.AddSeconds(120),
                resultArtifactId: artifactId);

            Assert.Equal(artifactId, next.ResultArtifactId);
            Assert.Equal(VideoJobState.Complete, next.State);
        }

        [Fact]
        public void From_with_media_refs_normalizes_to_NormalizedMediaRef()
        {
            var artId = Guid.NewGuid();
            var req = BasicRequest() with
            {
                Mode = VideoMode.I2V,
                StartFrame = VideoMediaRef.ForArtifact(artId, VideoMediaRoles.Image),
                PersonGeneration = PersonGenerationPolicy.AllowAdult,
            };

            var rec = VideoJobRecordFactory.From(
                Guid.NewGuid(), req, "veo", BasicEstimate(),
                VideoJobState.Queued, T0);

            Assert.NotNull(rec.NormalizedRequest.StartFrame);
            Assert.Equal(VideoMediaRefKind.Artifact, rec.NormalizedRequest.StartFrame!.Kind);
            Assert.Equal(artId, rec.NormalizedRequest.StartFrame.ArtifactId);
            Assert.Equal("image", rec.NormalizedRequest.StartFrame.Role);
        }

        [Fact]
        public void From_with_unknown_provider_uses_external_pricing_kind()
        {
            var rec = VideoJobRecordFactory.From(
                Guid.NewGuid(), BasicRequest(), "future-provider", BasicEstimate(),
                VideoJobState.Queued, T0);

            Assert.Equal(PricingKind.External, rec.Pricing.Kind);
            Assert.Null(rec.Pricing.UnitPriceUsd);
        }

        [Fact]
        public void From_rejects_empty_jobId()
        {
            Assert.Throws<ArgumentException>(() =>
                VideoJobRecordFactory.From(
                    Guid.Empty, BasicRequest(), "veo", BasicEstimate(),
                    VideoJobState.Queued, T0));
        }
    }
}
