using System;
using System.Collections.Generic;
using System.Linq;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VeoCostEstimatorTests
    {
        private static VideoGenerationRequest Req(
            string model = "veo-3.1-lite-generate-preview",
            VideoMode mode = VideoMode.T2V,
            int duration = 8,
            string resolution = "720p",
            string aspect = "16:9",
            string? prompt = "a clip",
            int numberOfVideos = 1) =>
            new(
                Model: model,
                Mode: mode,
                DurationSeconds: duration,
                Resolution: resolution,
                AspectRatio: aspect,
                Prompt: prompt,
                StartFrame: null,
                EndFrame: null,
                ReferenceFrames: null,
                Seed: null,
                PersonGeneration: PersonGenerationPolicy.AllowAll,
                NumberOfVideos: numberOfVideos);

        // ─── Happy paths: per-model pricing math (NumberOfVideos == 1) ─

        [Fact]
        public void Estimate_lite_720p_8s()
        {
            var estimator = new VeoCostEstimator(VideoCapabilities.Default);

            var result = estimator.Estimate(Req(
                model: "veo-3.1-lite-generate-preview",
                resolution: "720p",
                duration: 8));

            Assert.True(result.Success);
            Assert.NotNull(result.Estimate);
            Assert.Equal(0.40m, result.Estimate!.DollarsUsd); // 0.05 * 8
        }

        [Fact]
        public void Estimate_full_3_1_4k_8s()
        {
            var estimator = new VeoCostEstimator(VideoCapabilities.Default);

            var result = estimator.Estimate(Req(
                model: "veo-3.1-generate-preview",
                resolution: "4k",
                duration: 8));

            Assert.True(result.Success);
            Assert.Equal(4.80m, result.Estimate!.DollarsUsd); // 0.60 * 8
        }

        [Fact]
        public void Estimate_breakdown_sums_to_total()
        {
            var estimator = new VeoCostEstimator(VideoCapabilities.Default);

            var result = estimator.Estimate(Req(
                model: "veo-3.1-fast-generate-preview",
                resolution: "1080p",
                duration: 8));

            Assert.True(result.Success);
            var sum = result.Estimate!.Breakdown.Sum(b => b.DollarsUsd);
            Assert.Equal(result.Estimate.DollarsUsd, sum);
        }

        // ─── Fail-closed paths ────────────────────────────────────────

        [Fact]
        public void Estimate_unknown_model_returns_failure_not_throws()
        {
            var estimator = new VeoCostEstimator(VideoCapabilities.Default);

            var result = estimator.Estimate(Req(model: "veo-9000"));

            Assert.False(result.Success);
            Assert.Null(result.Estimate);
            Assert.NotNull(result.Error);
            Assert.Equal(VideoErrorCode.InvalidRequest, result.Error!.Code);
            Assert.Equal("Model", result.Error.Field);
            Assert.False(result.Error.Retryable);
        }

        [Fact]
        public void Estimate_NumberOfVideos_greater_than_one_returns_failure_no_estimate()
        {
            // v1 policy: NumberOfVideos > 1 is rejected at validation,
            // estimator never returns a cost estimate for an invalid
            // request. This pins the contract Codex required: no "raw
            // pricing math" surface for unsupported counts.
            var estimator = new VeoCostEstimator(VideoCapabilities.Default);

            var result = estimator.Estimate(Req(numberOfVideos: 3));

            Assert.False(result.Success);
            Assert.Null(result.Estimate);
            Assert.Equal(VideoErrorCode.UnsupportedMedia, result.Error!.Code);
            Assert.Equal("NumberOfVideos", result.Error.Field);
        }

        [Fact]
        public void Estimate_unsupported_resolution_returns_failure()
        {
            var estimator = new VeoCostEstimator(VideoCapabilities.Default);

            var result = estimator.Estimate(Req(resolution: "8k"));

            Assert.False(result.Success);
            Assert.Equal(VideoErrorCode.UnsupportedMedia, result.Error!.Code);
            Assert.Equal("Resolution", result.Error.Field);
        }

        [Fact]
        public void Estimate_invalid_PersonGeneration_returns_UnsupportedMedia()
        {
            // Veo 3.x T2V requires AllowAll; AllowAdult is rejected by
            // the catalog. Estimator must surface this as UnsupportedMedia
            // (capability shape mismatch), not InvalidRequest.
            var estimator = new VeoCostEstimator(VideoCapabilities.Default);
            var req = new VideoGenerationRequest(
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
                PersonGeneration: PersonGenerationPolicy.AllowAdult,
                NumberOfVideos: 1);

            var result = estimator.Estimate(req);

            Assert.False(result.Success);
            Assert.Equal(VideoErrorCode.UnsupportedMedia, result.Error!.Code);
            Assert.Equal("PersonGeneration", result.Error.Field);
        }

        [Fact]
        public void Estimate_null_request_returns_failure_not_throws()
        {
            var estimator = new VeoCostEstimator(VideoCapabilities.Default);

            var result = estimator.Estimate(null!);

            Assert.False(result.Success);
            Assert.Equal(VideoErrorCode.InvalidRequest, result.Error!.Code);
        }

        // ─── Injected catalog is honoured ─────────────────────────────

        [Fact]
        public void Estimate_uses_injected_catalog_not_default()
        {
            // A tiny catalog with one made-up cheap model. If the
            // estimator silently consulted VideoCapabilities.Default
            // it would reject this model as unknown.
            var tiny = new VideoCapabilities(new Dictionary<string, ModelCapability>
            {
                ["test-model-x"] = new ModelCapability(
                    Id: "test-model-x",
                    Name: "Test X",
                    Status: "preview",
                    Resolutions: new[] { "720p" },
                    Durations: new[] { 4 },
                    AspectRatios: new[] { "16:9" },
                    Modes: new[] { VideoMode.T2V },
                    SupportsReferenceImages: false,
                    MaxReferenceImages: 0,
                    Must8sWith: Array.Empty<string>(),
                    PricePerSecondUsd: new Dictionary<string, decimal>
                    {
                        ["720p"] = 0.01m,
                    }),
            });

            var estimator = new VeoCostEstimator(tiny);

            var result = estimator.Estimate(Req(
                model: "test-model-x",
                resolution: "720p",
                duration: 4));

            Assert.True(result.Success);
            Assert.Equal(0.04m, result.Estimate!.DollarsUsd);
        }

        [Fact]
        public void Estimator_constructor_rejects_null_catalog()
        {
            Assert.Throws<ArgumentNullException>(() =>
                new VeoCostEstimator(null!));
        }
    }
}
