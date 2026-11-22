using System.Text.Json;
using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal.Models;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalDeclarativePricingTests
    {
        internal static FalNormalizedRequest Normalize(CatalogFiles files, JsonObject? fields = null, JsonObject? options = null)
        {
            files.Save();
            var catalog = files.Compile(); Assert.Empty(catalog.Diagnostics);
            var normalized = new FalModelNormalizer().Normalize(catalog.Catalog!.Definitions[0].Operations[0], new FalModelInput(fields ?? new JsonObject { ["prompt"] = "draw" }, options));
            Assert.True(normalized.Success); return normalized.Request!;
        }
        internal static CatalogFiles Seconds(decimal rate = .2m)
        {
            var files = new CatalogFiles(CatalogFiles.VideoJson);
            files.Operation["operation_id"] = "text_to_video"; files.Operation["media"] = new JsonArray();
            var f = files.Operation["fields"]![0]!; f["type"] = "number"; f["min"] = .5m; f["default"] = 1.5m; f["payload"]!["conversion"] = "identity";
            files.Operation["pricing"]!["rates"]![0]!["rate_usd"] = rate;
            return files;
        }
        [Fact]
        public void Price_uses_effective_options_and_decimal_quantities()
        {
            using var files = Seconds();
            var r = new FalDeclarativePricing().Estimate(Normalize(files, new JsonObject()));
            Assert.True(r.Available); Assert.Equal(1.5m, r.Pricing!.QuantityMax); Assert.Equal(.30m, r.Pricing.EstimateMaxUsd); Assert.Equal("second", r.Pricing.Unit);
            using var image = new CatalogFiles();
            image.Operation["pricing"]!["rates"] = JsonNode.Parse("[{\"selectors\":{\"options.audio\":false},\"rate_usd\":0.3}]");
            var chosen = new FalDeclarativePricing().Estimate(Normalize(image, new JsonObject { ["prompt"] = "draw", ["resolution"] = "large" }));
            Assert.True(chosen.Success); Assert.Equal(.3m, chosen.Pricing!.EstimateMaxUsd); Assert.False(chosen.RateSelectors!["options.audio"]!.GetValue<bool>());
        }
        [Theory]
        [InlineData("none", 1.5, 1.5)] [InlineData("ceil_unit", 2, 2)]
        public void Megapixels_follow_declared_dimensions_and_rounding(string rounding, double min, double max)
        {
            using var files = new CatalogFiles(); var p = files.Operation["pricing"]!;
            p["strategy"] = "per_output_megapixel"; p["unit"] = "megapixel"; p["rounding"] = rounding;
            p["dimensions"] = JsonNode.Parse("{\"field\":\"request.resolution\",\"values\":{\"small\":{\"width\":1000,\"height\":1500},\"large\":{\"width\":2000,\"height\":3000}}}");
            var r = new FalDeclarativePricing().Estimate(Normalize(files));
            Assert.Equal((decimal)min, r.Pricing!.QuantityMin); Assert.Equal((decimal)max, r.Pricing.QuantityMax);
        }
        [Fact]
        public void Conservative_megapixels_are_bounded_and_missing_dimensions_fail_closed()
        {
            using var files = new CatalogFiles(); var p = files.Operation["pricing"]!;
            p["strategy"] = "per_output_megapixel"; p["unit"] = "megapixel"; p["max_megapixels"] = 2.5m;
            var r = new FalDeclarativePricing().Estimate(Normalize(files));
            Assert.True(r.Available); Assert.Equal(0, r.Pricing!.QuantityMin); Assert.Equal(2.5m, r.Pricing.QuantityMax);
            p.AsObject().Remove("max_megapixels"); files.Save(); Assert.NotEmpty(files.Compile().Diagnostics);
        }
        [Fact]
        public void Rate_selector_gaps_and_missing_pricing_are_unavailable_not_free()
        {
            using var files = new CatalogFiles();
            files.Operation["pricing"]!["rates"] = JsonNode.Parse("[{\"selectors\":{\"request.resolution\":\"large\"},\"rate_usd\":0.3}]");
            Assert.False(new FalDeclarativePricing().Estimate(Normalize(files)).Success);
            files.Operation.Remove("pricing");
            var missing = new FalDeclarativePricing().Estimate(Normalize(files)); Assert.False(missing.Success); Assert.Null(missing.Pricing); Assert.Equal("pricing_unavailable", missing.Error!.ProviderErrorCode);
        }
        [Theory]
        [InlineData("-1", "none", "second")] [InlineData("0.2", "nearest", "second")] [InlineData("0.2", "none", "output")]
        public void Invalid_rates_rounding_and_units_are_rejected(string rate, string rounding, string unit)
        {
            using var files = Seconds(); var p = files.Operation["pricing"]!;
            p["rates"]![0]!["rate_usd"] = JsonNode.Parse(rate); p["rounding"] = rounding; p["unit"] = unit; files.Save();
            Assert.NotEmpty(files.Compile().Diagnostics);
        }
        [Fact]
        public void Overflow_and_unrepresentable_confirmation_cost_disable_pricing()
        {
            using var files = Seconds(decimal.MaxValue);
            Assert.False(new FalDeclarativePricing().Estimate(Normalize(files, new JsonObject { ["duration_seconds"] = 10 })).Success);
            files.Operation["pricing"]!["rates"]![0]!["rate_usd"] = 1000000000m;
            Assert.False(new FalDeclarativePricing().Estimate(Normalize(files, new JsonObject { ["duration_seconds"] = 10 })).Success);
        }
        [Fact]
        public void Positive_rates_that_underflow_decimal_never_become_free_estimates()
        {
            using var files = Seconds(.0000000000000000000000000001m);
            var result = new FalDeclarativePricing().Estimate(Normalize(files, new JsonObject { ["duration_seconds"] = .5m }));
            Assert.False(result.Success); Assert.Null(result.Pricing);
        }
        [Fact]
        public void Actual_spend_remains_unknown_without_qualified_billing_evidence()
        {
            using var files = new CatalogFiles(); var model = files.Compile().Catalog!.Definitions[0];
            var strategy = new FalDeclarativePricing().ForImage(model, new FalAdapterRegistry());
            Assert.Null(strategy.ExtractActualSpend(new System.Collections.Generic.Dictionary<string, System.Collections.Generic.IReadOnlyList<string>>
                { ["x-fal-billable-units"] = new[] { "1" } }, new JsonObject()));
        }
        [Fact]
        public void Descriptor_preserves_precise_rate_as_invariant_text()
        {
            using var files = new CatalogFiles();
            files.Operation["pricing"]!["rates"]![0]!["rate_usd"] = .00000001m; files.Save();
            var binding = files.Compile().Catalog!.Definitions[0].Operations[0];
            var rate = new FalDescriptorProjector().Describe(binding, null).ToJson()["pricing"]!["rates"]![0]!["rate_usd"]!;
            Assert.Equal(JsonValueKind.String, rate.GetValueKind());
            Assert.Equal("0.00000001", rate.GetValue<string>());
        }
    }
}
