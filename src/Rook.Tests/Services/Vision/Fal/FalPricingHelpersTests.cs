using System.Collections.Generic;
using System.Globalization;
using Rook.Services.Vision.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalPricingHelpersTests
    {
        [Theory]
        [InlineData("x-fal-billable-units")]
        [InlineData("X-Fal-Billable-Units")]
        [InlineData("X-FAL-BILLABLE-UNITS")]
        public void TryGetBillableUnits_is_case_insensitive(string headerName)
        {
            var headers = new Dictionary<string, IReadOnlyList<string>>
            {
                [headerName] = new[] { "2.5" },
            };

            Assert.True(FalPricingHelpers.TryGetBillableUnits(headers, out var units));
            Assert.Equal(2.5m, units);
        }

        [Fact]
        public void TryGetBillableUnits_returns_false_when_missing_or_invalid()
        {
            Assert.False(FalPricingHelpers.TryGetBillableUnits(
                new Dictionary<string, IReadOnlyList<string>>(),
                out _));

            Assert.False(FalPricingHelpers.TryGetBillableUnits(
                new Dictionary<string, IReadOnlyList<string>>
                {
                    ["x-fal-billable-units"] = new[] { "not-a-number" },
                },
                out _));
        }

        [Theory]
        [InlineData("1,25")]
        [InlineData("-1")]
        public void TryGetBillableUnits_rejects_malformed_or_negative_values(string value)
        {
            var headers = new Dictionary<string, IReadOnlyList<string>>
            {
                ["x-fal-billable-units"] = new[] { value },
            };

            Assert.False(FalPricingHelpers.TryGetBillableUnits(headers, out var units));
            Assert.Equal(0m, units);
        }

        [Fact]
        public void TryGetBillableUnits_allows_surrounding_whitespace()
        {
            var headers = new Dictionary<string, IReadOnlyList<string>>
            {
                ["x-fal-billable-units"] = new[] { " 2.5 " },
            };

            Assert.True(FalPricingHelpers.TryGetBillableUnits(headers, out var units));
            Assert.Equal(2.5m, units);
        }

        [Fact]
        public void TryGetBillableUnits_uses_invariant_culture()
        {
            var previousCulture = CultureInfo.CurrentCulture;
            CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo("fr-FR");
            try
            {
                var headers = new Dictionary<string, IReadOnlyList<string>>
                {
                    ["x-fal-billable-units"] = new[] { "2.5" },
                };

                Assert.True(FalPricingHelpers.TryGetBillableUnits(headers, out var units));
                Assert.Equal(2.5m, units);
            }
            finally
            {
                CultureInfo.CurrentCulture = previousCulture;
            }
        }
    }
}
