using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    /// <summary>
    /// Negative-test coverage for seam-level invariants. The seam
    /// rejects nonsense at construction so PR-2/PR-3 cannot persist
    /// invalid state through a "valid" type.
    /// </summary>
    public class CostEstimateInvariantTests
    {
        [Fact]
        public void Rejects_negative_min()
        {
            Assert.Throws<ArgumentOutOfRangeException>(() =>
                new CostEstimate(Min: -0.01m, Max: 1m, IsExact: false, Provenance: "p"));
        }

        [Fact]
        public void Rejects_max_less_than_min()
        {
            Assert.Throws<ArgumentOutOfRangeException>(() =>
                new CostEstimate(Min: 0.5m, Max: 0.4m, IsExact: false, Provenance: "p"));
        }

        [Fact]
        public void Rejects_isExact_true_with_unequal_min_max()
        {
            Assert.Throws<ArgumentException>(() =>
                new CostEstimate(Min: 0.1m, Max: 0.2m, IsExact: true, Provenance: "p"));
        }

        [Fact]
        public void Rejects_empty_provenance()
        {
            Assert.Throws<ArgumentException>(() =>
                new CostEstimate(Min: 0.1m, Max: 0.1m, IsExact: true, Provenance: ""));
            Assert.Throws<ArgumentException>(() =>
                new CostEstimate(Min: 0.1m, Max: 0.1m, IsExact: true, Provenance: "   "));
        }

        [Fact]
        public void Accepts_zero_cost_with_exact()
        {
            var ce = new CostEstimate(Min: 0m, Max: 0m, IsExact: true, Provenance: "free-tier");
            Assert.Equal(0m, ce.Min);
            Assert.True(ce.IsExact);
        }

        [Fact]
        public void Accepts_min_eq_max_with_isExact_false()
        {
            var ce = new CostEstimate(Min: 0.5m, Max: 0.5m, IsExact: false, Provenance: "stub");
            Assert.False(ce.IsExact);
        }
    }

    public class JobPricingInvariantTests
    {
        [Fact]
        public void Rejects_empty_currency()
        {
            Assert.Throws<ArgumentException>(() => new JobPricing(
                Currency: "", UnitPrice: 1m, Unit: "call", Quantity: 1m,
                TotalUsd: 1m, PricingSource: "src"));
        }

        [Fact]
        public void Rejects_empty_pricing_source()
        {
            Assert.Throws<ArgumentException>(() => new JobPricing(
                Currency: "USD", UnitPrice: 1m, Unit: "call", Quantity: 1m,
                TotalUsd: 1m, PricingSource: ""));
        }

        [Fact]
        public void Rejects_negative_unit_price()
        {
            Assert.Throws<ArgumentOutOfRangeException>(() => new JobPricing(
                Currency: "USD", UnitPrice: -0.001m, Unit: "mp", Quantity: 1m,
                TotalUsd: 0m, PricingSource: "src"));
        }

        [Fact]
        public void Rejects_negative_quantity()
        {
            Assert.Throws<ArgumentOutOfRangeException>(() => new JobPricing(
                Currency: "USD", UnitPrice: 1m, Unit: "mp", Quantity: -1m,
                TotalUsd: 0m, PricingSource: "src"));
        }

        [Fact]
        public void Rejects_negative_total()
        {
            Assert.Throws<ArgumentOutOfRangeException>(() => new JobPricing(
                Currency: "USD", UnitPrice: 1m, Unit: "mp", Quantity: 1m,
                TotalUsd: -0.01m, PricingSource: "src"));
        }

        [Fact]
        public void Allows_external_pricing_with_null_numerics()
        {
            var pricing = new JobPricing(
                Currency: "USD", UnitPrice: null, Unit: null,
                Quantity: null, TotalUsd: null, PricingSource: "subscription-bundled");
            Assert.Null(pricing.TotalUsd);
        }
    }

    public class RemoteArtifactBodyInvariantTests
    {
        [Fact]
        public void Rejects_relative_uri()
        {
            Assert.Throws<ArgumentException>(() =>
                new RemoteArtifactBody(new Uri("/relative/path", UriKind.Relative)));
        }

        [Fact]
        public void Rejects_file_scheme()
        {
            Assert.Throws<ArgumentException>(() =>
                new RemoteArtifactBody(new Uri("file:///c:/temp/x.png")));
        }

        [Theory]
        [InlineData("ftp://example.com/x")]
        [InlineData("data:image/png;base64,abc")]
        [InlineData("ws://example.com/x")]
        public void Rejects_non_http_schemes(string uri)
        {
            Assert.Throws<ArgumentException>(() =>
                new RemoteArtifactBody(new Uri(uri)));
        }

        [Theory]
        [InlineData("http://example.com/x.png")]
        [InlineData("https://v3b.fal.media/files/abc/output.jpg")]
        public void Accepts_http_and_https(string uri)
        {
            var body = new RemoteArtifactBody(new Uri(uri));
            Assert.Equal(uri, body.Url.ToString());
        }

        [Fact]
        public void Rejects_zero_signed_url_ttl()
        {
            Assert.Throws<ArgumentException>(() => new RemoteArtifactBody(
                new Uri("https://example.com/x"), SignedUrlTtl: TimeSpan.Zero));
        }

        [Fact]
        public void Rejects_negative_signed_url_ttl()
        {
            Assert.Throws<ArgumentException>(() => new RemoteArtifactBody(
                new Uri("https://example.com/x"), SignedUrlTtl: TimeSpan.FromMinutes(-1)));
        }

        [Fact]
        public void Accepts_positive_ttl()
        {
            var body = new RemoteArtifactBody(
                new Uri("https://example.com/x"), SignedUrlTtl: TimeSpan.FromHours(1));
            Assert.Equal(TimeSpan.FromHours(1), body.SignedUrlTtl);
        }
    }

    public class ProviderJobHandleInvariantTests
    {
        [Fact]
        public void Rejects_relative_status_url()
        {
            Assert.Throws<ArgumentException>(() => new ProviderJobHandle(
                providerJobId: "j",
                statusUrl: new Uri("/relative", UriKind.Relative)));
        }

        [Fact]
        public void Rejects_non_http_response_url()
        {
            Assert.Throws<ArgumentException>(() => new ProviderJobHandle(
                providerJobId: "j",
                responseUrl: new Uri("file:///x")));
        }

        [Fact]
        public void Rejects_non_http_cancel_url()
        {
            Assert.Throws<ArgumentException>(() => new ProviderJobHandle(
                providerJobId: "j",
                cancelUrl: new Uri("ftp://example.com/cancel")));
        }

        [Fact]
        public void Accepts_handle_with_only_required_job_id()
        {
            var handle = new ProviderJobHandle(providerJobId: "j-1");
            Assert.Equal("j-1", handle.ProviderJobId);
            Assert.Null(handle.StatusUrl);
        }
    }

    public class ResultArtifactInvariantTests
    {
        private static IReadOnlyDictionary<string, JsonNode> EmptyMeta() =>
            new Dictionary<string, JsonNode>();

        [Fact]
        public void InlineArtifactBody_requires_declared_mime_type()
        {
            Assert.Throws<ArgumentException>(() => new ResultArtifact(
                Role: "image",
                Body: new InlineArtifactBody(new byte[] { 0x01 }),
                DeclaredMimeType: null,
                ProviderMetadata: EmptyMeta()));
        }

        [Fact]
        public void InlineArtifactBody_rejects_empty_declared_mime_type()
        {
            Assert.Throws<ArgumentException>(() => new ResultArtifact(
                Role: "image",
                Body: new InlineArtifactBody(new byte[] { 0x01 }),
                DeclaredMimeType: "   ",
                ProviderMetadata: EmptyMeta()));
        }

        [Fact]
        public void RemoteArtifactBody_allows_null_declared_mime_type()
        {
            // Replicate's flat URL-list case: MIME unknown until fetch.
            var artifact = new ResultArtifact(
                Role: "image",
                Body: new RemoteArtifactBody(new Uri("https://example.com/x.png")),
                DeclaredMimeType: null,
                ProviderMetadata: EmptyMeta());
            Assert.Null(artifact.DeclaredMimeType);
        }

        [Fact]
        public void Rejects_empty_role()
        {
            Assert.Throws<ArgumentException>(() => new ResultArtifact(
                Role: "",
                Body: new InlineArtifactBody(new byte[] { 0x01 }),
                DeclaredMimeType: "image/png",
                ProviderMetadata: EmptyMeta()));
        }
    }
}
