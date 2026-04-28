using System.Text.Json;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fixtures
{
    /// <summary>
    /// Captures the V1c <see cref="VideoCostEstimateResult"/> JSON
    /// projection for a representative Veo request. Pure call; no HTTP.
    /// Pinned post-retrofit by commit 6's parity tests so the
    /// <c>estimate_video_job</c> route's wire shape (model, resolution,
    /// duration, count, breakdown[].label/dollars, pricing.kind/quantity/
    /// unit_price/total/source) is byte-identical pre/post.
    /// </summary>
    public class VeoCostEstimateCaptureTests
    {
        [Fact]
        public void Golden_10_cost_estimate_veo_3_1_1080p_8s()
        {
            // Veo 3.1 full @ 1080p × 8s × 1 video — exercises the
            // PerSecondPricingModel via VideoCostEstimator end-to-end.
            // The lookup table at VeoCapabilities lists 1080p = $0.40/s,
            // so the captured Total is the audit-snapshot of that rate.
            var resolved = TestVideoFixtures.VeoLiteResolved(
                modelId: "veo-3.1-generate-preview");
            var request = TestVideoFixtures.DefaultT2vRequest(
                model: "veo-3.1-generate-preview",
                duration: 8,
                resolution: "1080p",
                personGeneration: PersonGenerationPolicy.AllowAll);

            var estimator = new VideoCostEstimator();
            var result = estimator.Estimate(resolved, request);

            Assert.True(result.Success, result.Error?.Message);

            var json = ProjectEstimateToJson(result);
            VeoBehaviorParityFixture.AssertOrCapture(
                "10_cost_estimate_veo_3_1_1080p_8s.json", json);
        }

        // Mirror the public estimate-route projection by hand. The
        // captured shape pins both the field set and ordering as the
        // V1c VideoOpHandler.Estimate currently produces. Commit 5's
        // VideoOpHandler retarget reuses these exact keys.
        private static string ProjectEstimateToJson(VideoCostEstimateResult result)
        {
            var est = result.Estimate!;
            var pricing = est.Pricing;

            var breakdown = new JsonArray();
            foreach (var c in est.Breakdown)
            {
                breakdown.Add(new JsonObject
                {
                    ["label"] = c.Label,
                    ["dollars_usd"] = c.DollarsUsd,
                });
            }

            var obj = new JsonObject
            {
                ["dollars_usd"] = est.DollarsUsd,
                ["model"] = est.Model,
                ["resolution"] = est.Resolution,
                ["duration_seconds"] = est.DurationSeconds,
                ["number_of_videos"] = est.NumberOfVideos,
                ["breakdown"] = breakdown,
                ["pricing"] = new JsonObject
                {
                    ["kind"] = pricing.Kind switch
                    {
                        PricingKind.PerSecond => "per_second",
                        PricingKind.PerGeneration => "per_generation",
                        PricingKind.External => "external",
                        _ => pricing.Kind.ToString().ToLowerInvariant(),
                    },
                    ["currency"] = pricing.Currency,
                    ["quantity"] = pricing.Quantity,
                    ["unit_price_usd"] = pricing.UnitPriceUsd,
                    ["total_usd"] = pricing.TotalUsd,
                    ["pricing_source"] = pricing.PricingSource,
                },
            };

            return obj.ToJsonString(new JsonSerializerOptions { WriteIndented = false });
        }
    }
}
