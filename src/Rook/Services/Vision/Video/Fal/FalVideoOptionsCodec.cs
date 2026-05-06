using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    public sealed class FalVideoOptionsCodec
        : IProviderOptionsCodec<VideoGenerationRequest, VideoCapability>
    {
        public Rook.Services.Vision.Generation.ValidationResult Validate(
            VideoGenerationRequest request,
            ProviderOptions options,
            VideoCapability cap)
        {
            if (request is null)
                return Rook.Services.Vision.Generation.ValidationResult.Fail("Request is null.", "Request");

            if (cap is null)
                return Rook.Services.Vision.Generation.ValidationResult.Fail("Capability is null.", "Cap");

            if (options is not FalVideoOptions)
                return Rook.Services.Vision.Generation.ValidationResult.Fail(
                    $"fal video codec requires {nameof(FalVideoOptions)}; got {options?.GetType().Name ?? "null"}.",
                    nameof(VideoGenerationRequest.Options));

            if (string.Equals(cap.Id, FalVideoCapabilities.SeedanceI2v, StringComparison.Ordinal)
                && string.IsNullOrWhiteSpace(request.Prompt))
            {
                return Rook.Services.Vision.Generation.ValidationResult.Fail(
                    "Seedance 2.0 Image to Video requires prompt.",
                    nameof(VideoGenerationRequest.Prompt));
            }

            return Rook.Services.Vision.Generation.ValidationResult.Ok();
        }

        public JsonObject Serialize(ProviderOptions options)
        {
            if (options is not FalVideoOptions)
                throw new InvalidOperationException(
                    $"fal video codec cannot serialize {options?.GetType().Name ?? "null"}; expected {nameof(FalVideoOptions)}.");

            return new JsonObject();
        }

        public ProviderOptionsDecodeResult Deserialize(JsonObject json)
        {
            if (json is null)
                return ProviderOptionsDecodeResult.Fail(new GenerationError(
                    GenerationErrorCode.InvalidRequest,
                    "Provider options JSON is null.",
                    Retryable: false,
                    Field: "options"));

            foreach (var kvp in json)
            {
                return ProviderOptionsDecodeResult.Fail(new GenerationError(
                    GenerationErrorCode.InvalidRequest,
                    $"fal video options do not support field '{kvp.Key}' in PR-8.",
                    Retryable: false,
                    Field: kvp.Key));
            }

            return ProviderOptionsDecodeResult.Ok(new FalVideoOptions());
        }
    }
}
