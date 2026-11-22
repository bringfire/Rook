using System;
using System.Linq;
using System.Collections.Generic;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Fal.Models;
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
            IVertexAccessTokenSource? vertexAccessTokenSource = null,
            FalCatalogSnapshot? catalog = null, FalConfiguredExecutor? configuredExecutor = null, FalAdapterRegistry? adapters = null)
        {
            var registrations = new List<IImageProviderRegistration>
            {
                new GeminiImageProviderRegistration(new GeminiImageProvider(geminiKeyProvider)),
                new FalImageProviderRegistration(new FalImageProvider(falKeyProvider)),
                new ReplicateImageProviderRegistration(new ReplicateImageProvider(replicateTokenProvider)),
                new VertexImageProviderRegistration(new VertexImageProvider(vertexAccessTokenSource ?? UnavailableVertexAccessTokenSource.Instance)),
            };
            if (catalog != null)
            {
                var configuredAdapters = adapters ?? new FalAdapterRegistry();
                foreach (var model in catalog.Definitions.Where(m => m.Operations[0].Result.MimeFamily == "image"))
                    registrations.Add(new ConfiguredFalImageRegistration(model,
                        configuredExecutor ?? throw new ArgumentNullException(nameof(configuredExecutor)), configuredAdapters,
                        new FalDeclarativePricing().ForImage(model, configuredAdapters)));
            }
            return registrations.ToArray();
        }

        public static IVideoProviderRegistration[] CreateVideoRegistrations(
            Func<string?> geminiKeyProvider,
            Func<string?> falKeyProvider,
            IVertexAccessTokenSource? vertexAccessTokenSource = null,
            FalCatalogSnapshot? catalog = null, FalConfiguredExecutor? configuredExecutor = null, FalAdapterRegistry? adapters = null)
        {
            var fal = new FalVideoProvider(falKeyProvider);
            var registrations = new List<IVideoProviderRegistration> {
                new VeoProviderRegistration(new VeoProvider(geminiKeyProvider)),
                new FalVideoProviderRegistration(fal),
                new FalVeoProviderRegistration(fal, new FalVeoBindingCatalog()),
                new VertexVeoProviderRegistration(new VertexVeoProvider(vertexAccessTokenSource ?? UnavailableVertexAccessTokenSource.Instance)),
            };
            if (catalog != null)
            {
                var configuredAdapters = adapters ?? new FalAdapterRegistry();
                foreach (var model in catalog.Definitions.Where(m => m.Operations[0].Result.MimeFamily == "video"))
                    registrations.Add(new ConfiguredFalVideoRegistration(model,
                        configuredExecutor ?? throw new ArgumentNullException(nameof(configuredExecutor)), configuredAdapters,
                        new FalDeclarativePricing().ForVideo(model, configuredAdapters)));
            }
            return registrations.ToArray();
        }

        public static IReadOnlyCollection<string> GetLegacyModelIds() => Array.AsReadOnly(
            CreateImageRegistrations(() => null, () => null, () => null).SelectMany(r => r.Models.Keys)
                .Concat(CreateVideoRegistrations(() => null, () => null).SelectMany(r => r.Models.Keys))
                .Concat(GeminiImageCapabilities.ShortNameToId.Keys).Distinct(StringComparer.Ordinal).ToArray());

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
