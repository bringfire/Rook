using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalVideoOptionsCodecTests
    {
        private readonly FalVideoOptionsCodec _codec = new();

        [Fact]
        public void Deserialize_empty_object_returns_fal_options()
        {
            var result = _codec.Deserialize(new JsonObject());

            Assert.True(result.Success);
            Assert.IsType<FalVideoOptions>(result.Options);
            Assert.Null(result.Error);
        }

        [Theory]
        [InlineData("negative_prompt")]
        [InlineData("enable_prompt_expansion")]
        [InlineData("audio_url")]
        [InlineData("future_field")]
        public void Deserialize_unknown_or_deferred_fields_fail(string field)
        {
            var json = new JsonObject { [field] = "x" };

            var result = _codec.Deserialize(json);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error!.Code);
            Assert.Equal(field, result.Error.Field);
        }

        [Theory]
        [InlineData("multi_prompt")]
        [InlineData("elements")]
        [InlineData("negative_prompt")]
        [InlineData("cfg_scale")]
        [InlineData("generate_audio")]
        public void Deserialize_kling_deferred_provider_fields_fail(string field)
        {
            var json = new JsonObject { [field] = "x" };

            var result = _codec.Deserialize(json);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error!.Code);
            Assert.Equal(field, result.Error.Field);
        }

        [Fact]
        public void Serialize_fal_options_returns_empty_object()
        {
            var json = _codec.Serialize(new FalVideoOptions());

            Assert.Empty(json);
        }

        [Fact]
        public void Validate_accepts_fal_options_for_t2v()
        {
            var request = Request(new FalVideoOptions());

            var result = _codec.Validate(
                request,
                request.Options,
                FalVideoCapabilities.Models[FalVideoCapabilities.WanT2v].Capability);

            Assert.True(result.Success);
        }

        [Fact]
        public void Validate_rejects_missing_prompt_for_kling()
        {
            var request = KlingRequest(prompt: " ");

            var result = _codec.Validate(
                request,
                request.Options,
                FalVideoCapabilities.Models[FalVideoCapabilities.KlingV3StandardI2v].Capability);

            Assert.False(result.Success);
            Assert.Equal(nameof(VideoGenerationRequest.Prompt), result.Field);
            Assert.Contains("Kling", result.Message);
        }

        [Fact]
        public void Validate_accepts_prompt_for_kling()
        {
            var request = KlingRequest(prompt: "camera glides around the model");

            var result = _codec.Validate(
                request,
                request.Options,
                FalVideoCapabilities.Models[FalVideoCapabilities.KlingV3StandardI2v].Capability);

            Assert.True(result.Success);
        }

        [Fact]
        public void Validate_rejects_mismatched_options_type()
        {
            var request = Request(new VeoOptions(PersonGenerationPolicy.AllowAll));

            var result = _codec.Validate(
                request,
                request.Options,
                FalVideoCapabilities.Models[FalVideoCapabilities.WanT2v].Capability);

            Assert.False(result.Success);
            Assert.Equal(nameof(VideoGenerationRequest.Options), result.Field);
        }

        private static VideoGenerationRequest Request(ProviderOptions options) =>
            new(
                Model: FalVideoCapabilities.WanT2v,
                Mode: VideoMode.T2V,
                DurationSeconds: 2,
                Resolution: "720p",
                AspectRatio: "16:9",
                Prompt: "a small architectural massing animation",
                StartFrame: null,
                EndFrame: null,
                ReferenceFrames: null,
                Seed: null,
                Options: options,
                NumberOfVideos: 1);

        private static VideoGenerationRequest KlingRequest(string? prompt) =>
            new(
                Model: FalVideoCapabilities.KlingV3StandardI2v,
                Mode: VideoMode.I2V,
                DurationSeconds: 5,
                Resolution: "auto",
                AspectRatio: "auto",
                Prompt: prompt,
                StartFrame: MediaRef.ForArtifact(System.Guid.NewGuid(), VideoMediaRoles.StartFrame),
                EndFrame: null,
                ReferenceFrames: null,
                Seed: null,
                Options: new FalVideoOptions(),
                NumberOfVideos: 1);
    }
}
