using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Fal
{
    public sealed class FalImageOptionsCodecTests
    {
        private readonly FalImageOptionsCodec _codec = new();

        [Fact]
        public void Deserialize_EmptyJson_ReturnsFalOptions()
        {
            var result = _codec.Deserialize(new JsonObject());

            Assert.True(result.Success);
            Assert.IsType<FalImageOptions>(result.Options);
        }

        [Fact]
        public void Deserialize_NonEmptyJson_FailsInvalidRequest()
        {
            var result = _codec.Deserialize(new JsonObject
            {
                ["image_size"] = "square_hd",
            });

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error?.Code);
            Assert.Contains(
                "fal image options do not accept provider-specific fields",
                result.Error?.Message,
                StringComparison.Ordinal);
        }

        [Fact]
        public void Validate_NumberOfImagesOne_ReturnsSuccess()
        {
            var result = _codec.Validate(
                Request(numberOfImages: 1),
                new FalImageOptions(),
                Capability());

            Assert.True(result.Success);
        }

        [Theory]
        [InlineData(0)]
        [InlineData(2)]
        public void Validate_NumberOfImagesOtherThanOne_ReturnsFailure(int numberOfImages)
        {
            var result = _codec.Validate(
                Request(numberOfImages: numberOfImages),
                new FalImageOptions(),
                Capability());

            Assert.False(result.Success);
            Assert.Equal("number_of_images", result.Field);
        }

        [Fact]
        public void Validate_ReferenceImages_ReturnsFailure()
        {
            var result = _codec.Validate(
                Request(referenceImages: new[] { MediaRef.ForPath("input.png", "image") }),
                new FalImageOptions(),
                Capability());

            Assert.False(result.Success);
            Assert.Equal("reference_image_paths", result.Field);
        }

        [Theory]
        [InlineData("")]
        [InlineData(null)]
        [InlineData("1K")]
        public void Validate_SupportedResolution_ReturnsSuccess(string? resolution)
        {
            var result = _codec.Validate(
                Request(resolution: resolution),
                new FalImageOptions(),
                Capability());

            Assert.True(result.Success);
        }

        [Theory]
        [InlineData("512")]
        [InlineData("2K")]
        public void Validate_UnsupportedResolution_ReturnsFailure(string resolution)
        {
            var result = _codec.Validate(
                Request(resolution: resolution),
                new FalImageOptions(),
                Capability());

            Assert.False(result.Success);
            Assert.Equal("resolution", result.Field);
        }

        [Theory]
        [InlineData("")]
        [InlineData(null)]
        [InlineData("1:1")]
        [InlineData("4:3")]
        [InlineData("3:4")]
        [InlineData("16:9")]
        [InlineData("9:16")]
        public void Validate_SupportedAspectRatio_ReturnsSuccess(string? aspectRatio)
        {
            var result = _codec.Validate(
                Request(aspectRatio: aspectRatio),
                new FalImageOptions(),
                Capability());

            Assert.True(result.Success);
        }

        [Theory]
        [InlineData("21:9")]
        [InlineData("4:1")]
        public void Validate_UnsupportedAspectRatio_ReturnsFailure(string aspectRatio)
        {
            var result = _codec.Validate(
                Request(aspectRatio: aspectRatio),
                new FalImageOptions(),
                Capability());

            Assert.False(result.Success);
            Assert.Equal("aspect_ratio", result.Field);
        }

        [Fact]
        public void Validate_GptImage2Edit_accepts_auto_resolution_and_match_input_image()
        {
            var result = _codec.Validate(
                Request(
                    model: FalImageCapabilities.GptImage2Edit,
                    resolution: "auto",
                    aspectRatio: "match_input_image"),
                new FalImageOptions(),
                FalImageCapabilities.Models[FalImageCapabilities.GptImage2Edit]);

            Assert.True(result.Success);
        }

        [Fact]
        public void Validate_GptImage2Edit_rejects_references()
        {
            var result = _codec.Validate(
                Request(
                    model: FalImageCapabilities.GptImage2Edit,
                    resolution: "auto",
                    aspectRatio: "match_input_image",
                    referenceImages: new[]
                    {
                        MediaRef.ForPath(
                            "C:/tmp/ref.png",
                            ImageMediaRoles.ReferenceImage),
                    }),
                new FalImageOptions(),
                FalImageCapabilities.Models[FalImageCapabilities.GptImage2Edit]);

            Assert.False(result.Success);
            Assert.Equal("reference_image_paths", result.Field);
            Assert.Contains("GPT Image 2 Edit", result.Message);
        }

        [Theory]
        [InlineData("1K", "match_input_image", "resolution")]
        [InlineData("auto", "1:1", "aspect_ratio")]
        public void Validate_GptImage2Edit_rejects_unsupported_resolution_or_aspect(
            string resolution,
            string aspectRatio,
            string expectedField)
        {
            var result = _codec.Validate(
                Request(
                    model: FalImageCapabilities.GptImage2Edit,
                    resolution: resolution,
                    aspectRatio: aspectRatio),
                new FalImageOptions(),
                FalImageCapabilities.Models[FalImageCapabilities.GptImage2Edit]);

            Assert.False(result.Success);
            Assert.Equal(expectedField, result.Field);
        }

        [Theory]
        [InlineData(null, "landscape_4_3")]
        [InlineData("", "landscape_4_3")]
        [InlineData(" ", "landscape_4_3")]
        [InlineData("1:1", "square_hd")]
        [InlineData("4:3", "landscape_4_3")]
        [InlineData("3:4", "portrait_4_3")]
        [InlineData("16:9", "landscape_16_9")]
        [InlineData("9:16", "portrait_16_9")]
        public void ToFalImageSize_MapsSupportedAspectRatios(
            string? aspectRatio,
            string expected)
        {
            Assert.Equal(expected, FalImageOptionsCodec.ToFalImageSize(aspectRatio));
        }

        [Fact]
        public void ToFalImageSize_UnsupportedAspectRatio_Throws()
        {
            Assert.Throws<ArgumentException>(
                () => FalImageOptionsCodec.ToFalImageSize("21:9"));
        }

        private static ImageGenerationRequest Request(
            string? model = null,
            string? resolution = "1K",
            string? aspectRatio = "4:3",
            int numberOfImages = 1,
            IReadOnlyList<MediaRef>? referenceImages = null)
            => new(
                Model: model ?? FalImageCapabilities.FluxSchnell,
                Prompt: "test prompt",
                Resolution: resolution ?? string.Empty,
                AspectRatio: aspectRatio ?? string.Empty,
                NumberOfImages: numberOfImages,
                ReferenceImages: referenceImages,
                Options: new FalImageOptions());

        private static ImageCapability Capability()
            => FalImageCapabilities.Models[FalImageCapabilities.FluxSchnell];
    }
}
