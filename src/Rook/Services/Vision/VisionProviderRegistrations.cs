using System;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Fal;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Image.Replicate;
using Rook.Services.Vision.Image.Vertex;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Rook.Services.Vision.Video.Vertex;

namespace Rook.Services.Vision
{
    internal static class VisionProviderRegistrations
    {
        public static IImageProviderRegistration[] CreateImageRegistrations(
            Func<string?> geminiKeyProvider,
            Func<string?> falKeyProvider,
            Func<string?> replicateTokenProvider,
            IVertexAccessTokenSource? vertexAccessTokenSource = null)
            => new IImageProviderRegistration[]
            {
                new GeminiImageProviderRegistration(new GeminiImageProvider(geminiKeyProvider)),
                new FalImageProviderRegistration(new FalImageProvider(falKeyProvider)),
                new ReplicateImageProviderRegistration(new ReplicateImageProvider(replicateTokenProvider)),
                new VertexImageProviderRegistration(new VertexImageProvider(vertexAccessTokenSource ?? UnavailableVertexAccessTokenSource.Instance)),
            };

        public static IVideoProviderRegistration[] CreateVideoRegistrations(
            Func<string?> geminiKeyProvider,
            Func<string?> falKeyProvider,
            IVertexAccessTokenSource? vertexAccessTokenSource = null)
            => new IVideoProviderRegistration[]
            {
                new VeoProviderRegistration(new VeoProvider(geminiKeyProvider)),
                new FalVideoProviderRegistration(new FalVideoProvider(falKeyProvider)),
                new VertexVeoProviderRegistration(new VertexVeoProvider(vertexAccessTokenSource ?? UnavailableVertexAccessTokenSource.Instance)),
            };

        public static ProviderCredentialMetadataCatalog CreateCredentialMetadata()
        {
            return ProviderCredentialMetadataCatalog.FromProviders(new[]
            {
                new ProviderCredentialMetadata(
                    GeminiImageCapabilities.ProviderName,
                    Array.AsReadOnly(new[]
                    {
                        new ProviderSecretRequirement(
                            GenerationSecretKeys.GeminiApiKey,
                            "Gemini API key",
                            isRequired: true),
                    })),
                new ProviderCredentialMetadata(
                    FalImageCapabilities.ProviderName,
                    Array.AsReadOnly(new[]
                    {
                        new ProviderSecretRequirement(
                            GenerationSecretKeys.FalApiKey,
                            "fal.ai API key",
                            isRequired: true),
                    })),
                new ProviderCredentialMetadata(
                    ReplicateImageCapabilities.ProviderName,
                    Array.AsReadOnly(new[]
                    {
                        new ProviderSecretRequirement(
                            GenerationSecretKeys.ReplicateApiToken,
                            "Replicate API token",
                            isRequired: true),
                    })),
            });
        }
    }
}
