using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Replicate;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Replicate
{
    public class ReplicateImageOptionsCodecTests
    {
        private readonly ReplicateImageOptionsCodec _codec = new();
        private readonly ImageCapability _cap = ReplicateImageCapabilities.Models[ReplicateImageCapabilities.FluxSchnell];
        private readonly ImageCapability _flux2Cap = ReplicateImageCapabilities.Models[ReplicateImageCapabilities.Flux2Pro];

        [Fact]
        public void Validate_accepts_default_text_to_image_request()
        {
            var result = _codec.Validate(Request(), new ReplicateImageOptions(), _cap);

            Assert.True(result.Success);
        }

        [Fact]
        public void Validate_rejects_reference_images_before_submit()
        {
            var result = _codec.Validate(
                Request(referenceImages: new[]
                {
                    MediaRef.ForPath("C:/tmp/ref.png", ImageMediaRoles.ReferenceImage),
                }),
                new ReplicateImageOptions(),
                _cap);

            Assert.False(result.Success);
            Assert.Equal("reference_image_paths", result.Field);
            Assert.Contains("not supported", result.Message);
        }

        [Fact]
        public void Validate_rejects_number_of_images_other_than_one()
        {
            var result = _codec.Validate(
                Request(numberOfImages: 2),
                new ReplicateImageOptions(),
                _cap);

            Assert.False(result.Success);
            Assert.Equal("number_of_images", result.Field);
        }

        [Theory]
        [InlineData("1:1")]
        [InlineData("4:3")]
        [InlineData("3:4")]
        [InlineData("16:9")]
        [InlineData("9:16")]
        [InlineData("")]
        public void Validate_accepts_supported_aspect_ratios_and_blank_default(string aspectRatio)
        {
            var result = _codec.Validate(
                Request(aspectRatio: aspectRatio),
                new ReplicateImageOptions(),
                _cap);

            Assert.True(result.Success);
        }

        [Fact]
        public void Validate_rejects_unsupported_aspect_ratio()
        {
            var result = _codec.Validate(
                Request(aspectRatio: "21:9"),
                new ReplicateImageOptions(),
                _cap);

            Assert.False(result.Success);
            Assert.Equal("aspect_ratio", result.Field);
        }

        [Fact]
        public void Validate_rejects_unsupported_resolution()
        {
            var result = _codec.Validate(
                Request(resolution: "2K"),
                new ReplicateImageOptions(),
                _cap);

            Assert.False(result.Success);
            Assert.Equal("resolution", result.Field);
        }

        [Theory]
        [InlineData("1 MP")]
        [InlineData("2 MP")]
        [InlineData("4 MP")]
        public void Validate_flux2_accepts_provider_shaped_resolutions(string resolution)
        {
            var result = _codec.Validate(
                Flux2Request(resolution: resolution),
                new ReplicateImageOptions(),
                _flux2Cap);

            Assert.True(result.Success);
        }

        [Fact]
        public void Validate_flux2_accepts_legacy_1mp_alias()
        {
            var result = _codec.Validate(
                Flux2Request(resolution: "1MP"),
                new ReplicateImageOptions(),
                _flux2Cap);

            Assert.True(result.Success);
        }

        [Theory]
        [InlineData("2MP")]
        [InlineData("4MP")]
        public void Validate_flux2_rejects_compact_resolution_aliases_other_than_legacy_1mp(string resolution)
        {
            var result = _codec.Validate(
                Flux2Request(resolution: resolution),
                new ReplicateImageOptions(),
                _flux2Cap);

            Assert.False(result.Success);
            Assert.Equal("resolution", result.Field);
            Assert.Contains("1 MP, 2 MP, 4 MP", result.Message);
        }

        [Fact]
        public void Serialize_returns_empty_object()
        {
            var json = _codec.Serialize(new ReplicateImageOptions());

            Assert.Empty(json);
        }

        [Fact]
        public void Deserialize_accepts_empty_object()
        {
            var result = _codec.Deserialize(new JsonObject());

            Assert.True(result.Success);
            Assert.IsType<ReplicateImageOptions>(result.Options);
        }

        [Fact]
        public void Deserialize_rejects_provider_specific_fields()
        {
            var result = _codec.Deserialize(new JsonObject
            {
                ["seed"] = JsonValue.Create(123),
            });

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error!.Code);
            Assert.Equal("options", result.Error.Field);
        }

        private static ImageGenerationRequest Request(
            string resolution = "1K",
            string aspectRatio = "1:1",
            int numberOfImages = 1,
            System.Collections.Generic.IReadOnlyList<MediaRef>? referenceImages = null) =>
            new(
                Model: ReplicateImageCapabilities.FluxSchnell,
                Prompt: "sunlit massing study",
                Resolution: resolution,
                AspectRatio: aspectRatio,
                NumberOfImages: numberOfImages,
                ReferenceImages: referenceImages,
                Options: new ReplicateImageOptions());

        private static ImageGenerationRequest Flux2Request(
            string resolution = "1 MP",
            string aspectRatio = "1:1",
            int numberOfImages = 1,
            System.Collections.Generic.IReadOnlyList<MediaRef>? referenceImages = null) =>
            new(
                Model: ReplicateImageCapabilities.Flux2Pro,
                Prompt: "sunlit massing study",
                Resolution: resolution,
                AspectRatio: aspectRatio,
                NumberOfImages: numberOfImages,
                ReferenceImages: referenceImages,
                Options: new ReplicateImageOptions());
    }
}
