using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Replicate;
using Xunit;

namespace Rook.Tests.Services.Vision.Replicate
{
    public class ReplicateErrorMapperTests
    {
        [Theory]
        [InlineData(400, GenerationErrorCode.InvalidRequest, false)]
        [InlineData(422, GenerationErrorCode.InvalidRequest, false)]
        [InlineData(401, GenerationErrorCode.DependencyUnavailable, false)]
        [InlineData(403, GenerationErrorCode.DependencyUnavailable, false)]
        [InlineData(429, GenerationErrorCode.QuotaExceeded, true)]
        [InlineData(408, GenerationErrorCode.DependencyUnavailable, true)]
        [InlineData(500, GenerationErrorCode.DependencyUnavailable, true)]
        [InlineData(503, GenerationErrorCode.DependencyUnavailable, true)]
        [InlineData(418, GenerationErrorCode.ExecutionFailed, false)]
        public void MapHttpFailure_maps_status_code(
            int status,
            GenerationErrorCode code,
            bool retryable)
        {
            var error = ReplicateErrorMapper.MapHttpFailure(
                Response(status, "{\"detail\":\"bad\"}"));

            Assert.Equal(code, error.Code);
            Assert.Equal(retryable, error.Retryable);
            Assert.Equal(status.ToString(), error.ProviderErrorCode);
            Assert.NotNull(error.ProviderDetail);
        }

        [Fact]
        public void MissingToken_returns_dependency_unavailable_non_retryable()
        {
            var error = ReplicateErrorMapper.MissingToken();

            Assert.Equal(GenerationErrorCode.DependencyUnavailable, error.Code);
            Assert.False(error.Retryable);
            Assert.Contains("Replicate API token is not configured", error.Message);
        }

        [Theory]
        [InlineData("")]
        [InlineData("   ")]
        [InlineData("[]")]
        [InlineData("\"detail\"")]
        [InlineData("{not-json")]
        public void ProviderDetail_is_null_for_blank_non_object_or_malformed_json(
            string body)
        {
            var error = ReplicateErrorMapper.MapHttpFailure(Response(400, body));

            Assert.Null(error.ProviderDetail);
        }

        [Fact]
        public void ProviderDetail_preserves_json_null_fields()
        {
            var error = ReplicateErrorMapper.MapHttpFailure(
                Response(400, "{\"detail\":null}"));

            Assert.NotNull(error.ProviderDetail);
            Assert.True(error.ProviderDetail!.ContainsKey("detail"));
            Assert.Null(error.ProviderDetail["detail"]);
        }

        [Fact]
        public void ProviderDetail_returns_cloned_nodes_per_mapping()
        {
            var first = ReplicateErrorMapper.MapHttpFailure(
                Response(400, "{\"detail\":{\"message\":\"original\"}}"));
            var second = ReplicateErrorMapper.MapHttpFailure(
                Response(400, "{\"detail\":{\"message\":\"original\"}}"));

            var firstDetail = Assert.IsType<System.Text.Json.Nodes.JsonObject>(
                first.ProviderDetail!["detail"]);
            firstDetail["message"] = "mutated";

            Assert.Equal(
                "original",
                second.ProviderDetail!["detail"]!["message"]!.GetValue<string>());
        }

        [Fact]
        public void Message_is_sanitized_and_excludes_provider_detail()
        {
            var error = ReplicateErrorMapper.MapHttpFailure(
                Response(500, "{\"detail\":\"provider leaked internal detail\"}"));

            Assert.Equal("Replicate request failed with HTTP 500.", error.Message);
            Assert.DoesNotContain("provider leaked internal detail", error.Message);
            Assert.DoesNotContain("detail", error.Message);
        }

        private static ReplicateHttpResponse Response(int status, string body) =>
            new ReplicateHttpResponse(
                status,
                body,
                new Dictionary<string, IReadOnlyList<string>>());
    }
}
