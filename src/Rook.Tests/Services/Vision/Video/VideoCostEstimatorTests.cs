using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    /// <summary>
    /// V1c estimator orchestration tests: takes
    /// <see cref="ResolvedVideoModel"/> + request, runs cap validation +
    /// codec validation + pricing in single-pass order, surfaces typed
    /// failures with correct error-code classification. Pricing math
    /// itself is covered by <see cref="PerSecondPricingModelTests"/>.
    /// </summary>
    public class VideoCostEstimatorTests
    {
        // ─── Happy path ───────────────────────────────────────────────

        [Fact]
        public void Estimate_lite_720p_8s_includes_pricing_snapshot_and_breakdown()
        {
            var estimator = new VideoCostEstimator();
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();

            var result = estimator.Estimate(model, req);

            Assert.True(result.Success);
            Assert.NotNull(result.Estimate);
            Assert.Equal(0.40m, result.Estimate!.DollarsUsd);  // 0.05 × 8
            Assert.Equal(0.40m, result.Estimate.Pricing.TotalUsd);
            Assert.Equal(8, result.Estimate.Pricing.Quantity);
            Assert.Equal("veo-rate-card-v1", result.Estimate.Pricing.PricingSource);
        }

        [Fact]
        public void Estimate_breakdown_sums_to_total_for_single_video()
        {
            var estimator = new VideoCostEstimator();
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();

            var result = estimator.Estimate(model, req);

            Assert.True(result.Success);
            var sum = result.Estimate!.Breakdown.Sum(b => b.DollarsUsd);
            Assert.Equal(result.Estimate.DollarsUsd, sum);
        }

        // ─── Failure classification ───────────────────────────────────

        [Fact]
        public void Estimate_unsupported_resolution_returns_UnsupportedMedia()
        {
            var estimator = new VideoCostEstimator();
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest(resolution: "8k");

            var result = estimator.Estimate(model, req);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.UnsupportedMedia, result.Error!.Code);
            Assert.Equal("Resolution", result.Error.Field);
        }

        [Fact]
        public void Estimate_NumberOfVideos_greater_than_one_returns_UnsupportedMedia()
        {
            var estimator = new VideoCostEstimator();
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest(numberOfVideos: 3);

            var result = estimator.Estimate(model, req);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.UnsupportedMedia, result.Error!.Code);
            Assert.Equal("NumberOfVideos", result.Error.Field);
        }

        [Fact]
        public void Estimate_invalid_PersonGeneration_returns_UnsupportedMedia()
        {
            // Veo 3.x T2V requires AllowAll; AllowAdult on T2V is rejected
            // by the codec — V1c bit-identity preservation requires this
            // surface as UnsupportedMedia (matches V1b).
            var estimator = new VideoCostEstimator();
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest(
                personGeneration: PersonGenerationPolicy.AllowAdult);

            var result = estimator.Estimate(model, req);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.UnsupportedMedia, result.Error!.Code);
            Assert.Equal("PersonGeneration", result.Error.Field);
        }

        [Fact]
        public void Estimate_t2v_without_prompt_returns_InvalidRequest()
        {
            // Prompt is a CapabilityValidator failure not classified as
            // UnsupportedMedia.
            var estimator = new VideoCostEstimator();
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest(prompt: null);

            var result = estimator.Estimate(model, req);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error!.Code);
            Assert.Equal("Prompt", result.Error.Field);
        }

        [Fact]
        public void Estimate_null_request_returns_typed_failure_no_throw()
        {
            var estimator = new VideoCostEstimator();
            var model = TestVideoFixtures.VeoLiteResolved();

            var result = estimator.Estimate(model, request: null!);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error!.Code);
        }

        [Fact]
        public void Estimate_null_model_returns_typed_failure_no_throw()
        {
            var estimator = new VideoCostEstimator();
            var req = TestVideoFixtures.DefaultT2vRequest();

            var result = estimator.Estimate(model: null!, req);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error!.Code);
        }

        // ─── F2 (review pass 2): model-id consistency guard ──────────

        [Fact]
        public void Estimate_rejects_mismatch_between_model_ModelId_and_request_Model()
        {
            // Public seam abuse: caller pairs model A's ResolvedVideoModel
            // with model B's request. The estimator MUST surface this as
            // typed InvalidRequest before validating/pricing — otherwise
            // it would validate against A's capability, price against A's
            // pricing model, and emit VideoCostEstimate.Model = B (data
            // poisoning).
            var estimator = new VideoCostEstimator();
            var liteModel = TestVideoFixtures.VeoLiteResolved();  // model A: lite
            var fullReq = TestVideoFixtures.DefaultT2vRequest(   // request B: full
                model: "veo-3.1-generate-preview");

            var result = estimator.Estimate(liteModel, fullReq);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error!.Code);
            Assert.Equal(nameof(VideoGenerationRequest.Model), result.Error.Field);
            Assert.Contains(liteModel.ModelId, result.Error.Message);
            Assert.Contains("veo-3.1-generate-preview", result.Error.Message);
        }

        [Fact]
        public void Estimate_accepts_consistent_model_id_pair()
        {
            // Sanity: the guard does not false-positive on consistent pairs.
            var estimator = new VideoCostEstimator();
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();  // default uses same model id

            var result = estimator.Estimate(model, req);

            Assert.True(result.Success);
            Assert.Equal(model.ModelId, result.Estimate!.Model);
        }

        // ─── Pricing single-pass invariant ────────────────────────────

        [Fact]
        public void Estimate_Pricing_field_matches_DollarsUsd_field()
        {
            // The audit invariant: VideoCostEstimate.Pricing is the same
            // dollar amount as VideoCostEstimate.DollarsUsd. Drift would
            // mean the estimator computed pricing twice with different
            // results.
            var estimator = new VideoCostEstimator();
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();

            var result = estimator.Estimate(model, req);

            Assert.True(result.Success);
            Assert.Equal(result.Estimate!.DollarsUsd, result.Estimate.Pricing.TotalUsd);
        }

        [Fact]
        public void Estimate_preserves_generic_pricing_error_without_legacy_downgrade()
        {
            var error = new GenerationError(
                GenerationErrorCode.QuotaExceeded,
                "Pricing quota exhausted.",
                Retryable: true,
                Field: "quota",
                ProviderErrorCode: "rate_limit_exceeded",
                ProviderDetail: new Dictionary<string, JsonNode>
                {
                    ["detail"] = JsonValue.Create("pricing detail")!,
                });
            var estimator = new VideoCostEstimator();
            var model = TestVideoFixtures.VeoLiteResolved() with
            {
                PricingModel = new FailingPricingModel(error),
            };
            var req = TestVideoFixtures.DefaultT2vRequest();

            var result = estimator.Estimate(model, req);

            Assert.False(result.Success);
            Assert.Same(error, result.Error);
            Assert.Equal(GenerationErrorCode.QuotaExceeded, result.Error!.Code);
            Assert.Equal("rate_limit_exceeded", result.Error.ProviderErrorCode);
            Assert.Equal("pricing detail",
                result.Error.ProviderDetail!["detail"]!.GetValue<string>());
        }

        private sealed class FailingPricingModel :
            Rook.Services.Vision.Generation.IPricingModel<VideoGenerationRequest, VideoCapability>
        {
            private readonly GenerationError _error;

            public FailingPricingModel(GenerationError error)
            {
                _error = error;
            }

            public string PricingSource => "test-pricing-source";

            public PricingMetadataLocation MetadataLocation =>
                PricingMetadataLocation.NotApplicable;

            public Rook.Services.Vision.Generation.PricingResult Estimate(
                VideoGenerationRequest request,
                VideoCapability capability) =>
                Rook.Services.Vision.Generation.PricingResult.Fail(_error);

            public Rook.Services.Vision.Generation.JobPricing? ExtractActualSpend(
                IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
                JsonNode? responseBody) =>
                null;
        }
    }
}
