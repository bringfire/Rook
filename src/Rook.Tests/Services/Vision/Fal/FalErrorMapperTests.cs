using System.Collections.Generic;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalErrorMapperTests
    {
        [Fact]
        public void Maps_401_to_dependency_unavailable_non_retryable()
        {
            var error = FalErrorMapper.MapHttpFailure(new FalHttpResponse(
                401,
                "{\"detail\":\"bad key\"}",
                new Dictionary<string, IReadOnlyList<string>>()));

            Assert.Equal(GenerationErrorCode.DependencyUnavailable, error.Code);
            Assert.False(error.Retryable);
            Assert.Equal("401", error.ProviderErrorCode);
        }

        [Fact]
        public void Maps_422_detail_array_to_invalid_request_with_provider_detail()
        {
            var error = FalErrorMapper.MapHttpFailure(new FalHttpResponse(
                422,
                "{\"detail\":[{\"loc\":[\"body\",\"image\"],\"msg\":\"field required\",\"type\":\"missing\"}]}",
                new Dictionary<string, IReadOnlyList<string>>()));

            Assert.Equal(GenerationErrorCode.InvalidRequest, error.Code);
            Assert.False(error.Retryable);
            Assert.NotNull(error.ProviderDetail);
            Assert.True(error.ProviderDetail!.ContainsKey("detail"));
        }

        [Fact]
        public void Preserves_json_null_provider_detail_fields()
        {
            var error = FalErrorMapper.MapHttpFailure(new FalHttpResponse(
                422,
                "{\"detail\":null}",
                new Dictionary<string, IReadOnlyList<string>>()));

            Assert.NotNull(error.ProviderDetail);
            Assert.True(error.ProviderDetail!.ContainsKey("detail"));
            Assert.Null(error.ProviderDetail["detail"]);
        }

        [Fact]
        public void Retry_header_controls_retryability()
        {
            var error = FalErrorMapper.MapHttpFailure(new FalHttpResponse(
                503,
                "{\"detail\":\"busy\"}",
                new Dictionary<string, IReadOnlyList<string>>
                {
                    ["x-fal-needs-retry"] = new[] { "true" },
                }));

            Assert.Equal(GenerationErrorCode.DependencyUnavailable, error.Code);
            Assert.True(error.Retryable);
        }

        [Fact]
        public void Message_is_sanitized_and_excludes_provider_detail()
        {
            var error = FalErrorMapper.MapHttpFailure(new FalHttpResponse(
                500,
                "{\"detail\":\"provider leaked internal detail\"}",
                new Dictionary<string, IReadOnlyList<string>>()));

            Assert.Equal("fal request failed with HTTP 500.", error.Message);
            Assert.DoesNotContain("provider leaked internal detail", error.Message);
            Assert.DoesNotContain("detail", error.Message);
        }

        [Fact]
        public void Maps_429_to_quota_exceeded_non_retryable_without_retry_signal()
        {
            var error = FalErrorMapper.MapHttpFailure(new FalHttpResponse(
                429,
                "{\"detail\":\"rate limited\"}",
                new Dictionary<string, IReadOnlyList<string>>()));

            Assert.Equal(GenerationErrorCode.QuotaExceeded, error.Code);
            Assert.False(error.Retryable);
            Assert.Equal("429", error.ProviderErrorCode);
        }

        [Fact]
        public void Maps_429_to_quota_exceeded_non_retryable_when_retry_signal_is_false()
        {
            var error = FalErrorMapper.MapHttpFailure(new FalHttpResponse(
                429,
                "{\"detail\":\"rate limited\"}",
                new Dictionary<string, IReadOnlyList<string>>
                {
                    ["x-fal-needs-retry"] = new[] { "false" },
                }));

            Assert.Equal(GenerationErrorCode.QuotaExceeded, error.Code);
            Assert.False(error.Retryable);
            Assert.Equal("429", error.ProviderErrorCode);
        }

        [Fact]
        public void Maps_429_to_quota_exceeded_retryable_when_retry_signal_is_true()
        {
            var error = FalErrorMapper.MapHttpFailure(new FalHttpResponse(
                429,
                "{\"detail\":\"rate limited\"}",
                new Dictionary<string, IReadOnlyList<string>>
                {
                    ["x-fal-needs-retry"] = new[] { "true" },
                }));

            Assert.Equal(GenerationErrorCode.QuotaExceeded, error.Code);
            Assert.True(error.Retryable);
            Assert.Equal("429", error.ProviderErrorCode);
        }
    }
}
