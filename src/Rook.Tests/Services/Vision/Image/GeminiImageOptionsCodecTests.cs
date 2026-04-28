using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Gemini;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public class GeminiImageOptionsCodecTests
    {
        private static ImageCapability NanoBanana2 =>
            GeminiImageCapabilities.Models[GeminiImageCapabilities.NanoBanana2];

        [Fact]
        public void Validate_accepts_default_gemini_shape()
        {
            var codec = new GeminiImageOptionsCodec();
            var request = Request(
                model: GeminiImageCapabilities.NanoBanana2,
                resolution: "1K",
                aspectRatio: "16:9",
                referenceCount: 1);

            var result = codec.Validate(request, request.Options, NanoBanana2);

            Assert.True(result.Success);
        }

        [Fact]
        public void Validate_rejects_512_for_nano_banana_pro()
        {
            var codec = new GeminiImageOptionsCodec();
            var request = Request(
                model: GeminiImageCapabilities.NanoBananaPro,
                resolution: "512",
                aspectRatio: "1:1",
                referenceCount: 0);

            var result = codec.Validate(
                request,
                request.Options,
                GeminiImageCapabilities.Models[GeminiImageCapabilities.NanoBananaPro]);

            Assert.False(result.Success);
            Assert.Equal("resolution", result.Field);
            Assert.Contains("resolution must be one of: 1K, 2K, 4K", result.Message);
        }

        [Fact]
        public void Validate_rejects_foreign_options_as_typed_error()
        {
            var codec = new GeminiImageOptionsCodec();
            var request = Request(
                model: GeminiImageCapabilities.NanoBanana2,
                resolution: "1K",
                aspectRatio: "1:1",
                referenceCount: 0) with
            {
                Options = new ForeignImageOptions(),
            };

            var result = codec.Validate(request, request.Options, NanoBanana2);

            Assert.False(result.Success);
            Assert.Equal("options", result.Field);
            Assert.Contains(nameof(GeminiImageOptions), result.Message);
        }

        [Fact]
        public void Serialize_and_deserialize_round_trip_empty_options()
        {
            var codec = new GeminiImageOptionsCodec();

            var json = codec.Serialize(new GeminiImageOptions());
            var decoded = codec.Deserialize(json);

            Assert.Empty(json);
            Assert.True(decoded.Success);
            Assert.IsType<GeminiImageOptions>(decoded.Options);
        }

        private static ImageGenerationRequest Request(
            string model,
            string resolution,
            string aspectRatio,
            int referenceCount)
        {
            var refs = new List<MediaRef>();
            for (int i = 0; i < referenceCount; i++)
                refs.Add(MediaRef.ForPath($"C:/tmp/ref-{i}.png", ImageMediaRoles.ReferenceImage));

            return new ImageGenerationRequest(
                Model: model,
                Prompt: "make this architectural rendering warmer",
                Resolution: resolution,
                AspectRatio: aspectRatio,
                NumberOfImages: 1,
                ReferenceImages: refs,
                Options: new GeminiImageOptions());
        }

        private sealed record ForeignImageOptions : ProviderOptions;
    }
}
