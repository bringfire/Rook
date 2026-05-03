using System;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Fal;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Image.Replicate;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;

namespace Rook.Services.Vision
{
    internal static class VisionProviderRegistrations
    {
        public static IImageProviderRegistration[] CreateImageRegistrations(
            Func<string?> geminiKeyProvider,
            Func<string?> falKeyProvider,
            Func<string?> replicateTokenProvider)
            => new IImageProviderRegistration[]
            {
                new GeminiImageProviderRegistration(new GeminiImageProvider(geminiKeyProvider)),
                new FalImageProviderRegistration(new FalImageProvider(falKeyProvider)),
                new ReplicateImageProviderRegistration(new ReplicateImageProvider(replicateTokenProvider)),
            };

        public static IVideoProviderRegistration[] CreateVideoRegistrations(
            Func<string?> geminiKeyProvider,
            Func<string?> falKeyProvider)
            => new IVideoProviderRegistration[]
            {
                new VeoProviderRegistration(new VeoProvider(geminiKeyProvider)),
                new FalVideoProviderRegistration(new FalVideoProvider(falKeyProvider)),
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
