using System;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Replicate;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public class ImageMediaPolicyTests
    {
        [Fact]
        public void Flux2Pro_policy_models_provider_input_limits_and_provenance()
        {
            var policy = ReplicateImageCapabilities.Flux2ProMediaPolicy;

            Assert.Equal(ReplicateImageCapabilities.Flux2Pro, policy.ModelId);
            Assert.Equal("Flux 2 Pro", policy.ModelLabel);
            Assert.Equal(
                new[] { "image/jpeg", "image/png", "image/gif", "image/webp" },
                policy.Model.AllowedMimeTypes);
            Assert.Equal(8, policy.Model.MaxInputImages);
            Assert.Equal(ReplicateImageCapabilities.Flux2ProMaxAggregatePixels, policy.Model.MaxAggregatePixels);
            Assert.Equal(ImageLimitProvenance.ProviderDocumented, policy.Model.PixelLimitProvenance);
            Assert.Equal(new DateTime(2026, 5, 18), policy.Model.ProviderReviewedOn);
            Assert.Contains("flux-2-pro", policy.Model.ProviderSourceUrl);

            Assert.Equal(ImageInputTransportKind.ReplicateHostedFileUrl, policy.Transport.Kind);
            Assert.Equal(
                ReplicateImageCapabilities.ReplicateFileUploadMaxBytes,
                policy.Transport.MaxSingleUploadBytes);
            Assert.Equal(
                ImageLimitProvenance.ProviderTransportDocumented,
                policy.Transport.ByteLimitProvenance);
            Assert.Equal(new DateTime(2026, 5, 18), policy.Transport.ProviderReviewedOn);
            Assert.Equal(
                "https://replicate.com/docs/topics/predictions/input-files",
                policy.Transport.SourceUrl);

            Assert.Equal(
                ReplicateImageCapabilities.ReplicateFileUploadMaxBytes,
                policy.Safety.MaxSingleReadBytes);
            Assert.Equal(
                ReplicateImageCapabilities.ReplicateFileUploadMaxBytes,
                policy.Safety.MaxAggregateReadBytes);
        }

        [Fact]
        public void Flux2Pro_policy_accepts_prompt_only_without_media_transport()
        {
            var result = ReplicateImageCapabilities.Flux2ProMediaPolicy.ValidateInputSet(
                mediaCount: 0,
                aggregatePixels: 0,
                hasPrompt: true);

            Assert.True(result.Success);
            Assert.Null(result.Message);
            Assert.Null(result.Field);
        }

        [Fact]
        public void Flux2Pro_policy_rejects_missing_prompt()
        {
            var result = ReplicateImageCapabilities.Flux2ProMediaPolicy.ValidateInputSet(
                mediaCount: 1,
                aggregatePixels: 1024,
                hasPrompt: false);

            Assert.False(result.Success);
            Assert.Equal("prompt", result.Field);
            Assert.Contains("requires prompt", result.Message);
        }

        [Fact]
        public void Flux2Pro_policy_rejects_more_than_eight_images_at_policy_level()
        {
            var result = ReplicateImageCapabilities.Flux2ProMediaPolicy.ValidateInputSet(
                mediaCount: 9,
                aggregatePixels: 1024,
                hasPrompt: true);

            Assert.False(result.Success);
            Assert.Equal("input_images", result.Field);
            Assert.Contains("Flux 2 Pro", result.Message);
            Assert.Contains("up to 8 input images", result.Message);
        }

        [Fact]
        public void Flux2Pro_policy_rejects_aggregate_pixels_over_nine_megapixels()
        {
            var result = ReplicateImageCapabilities.Flux2ProMediaPolicy.ValidateInputSet(
                mediaCount: 1,
                aggregatePixels: ReplicateImageCapabilities.Flux2ProMaxAggregatePixels + 1,
                hasPrompt: true);

            Assert.False(result.Success);
            Assert.Equal("input_images", result.Field);
            Assert.Contains("Flux 2 Pro", result.Message);
            Assert.Contains("9 megapixels or less", result.Message);
        }
    }
}
