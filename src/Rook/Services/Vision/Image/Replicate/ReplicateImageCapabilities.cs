using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Image.Replicate
{
    public static class ReplicateImageCapabilities
    {
        public const string ProviderName = "replicate";
        public const string FluxSchnell = "black-forest-labs/flux-schnell";
        public const string Flux2Pro = "black-forest-labs/flux-2-pro";
        public const string DefaultModel = FluxSchnell;

        public static readonly IReadOnlyDictionary<string, ImageCapability> Models =
            new Dictionary<string, ImageCapability>(StringComparer.Ordinal)
            {
                [FluxSchnell] = new ImageCapability(
                    Id: FluxSchnell,
                    Name: "FLUX.1 Schnell",
                    Status: "available",
                    Resolutions: new[] { "1K" },
                    AspectRatios: new[] { "1:1", "4:3", "3:4", "16:9", "9:16" },
                    MaxReferenceImages: 0,
                    SupportsImageToImage: false,
                    SupportsTextToImage: true),
                [Flux2Pro] = new ImageCapability(
                    Id: Flux2Pro,
                    Name: "FLUX.2 Pro",
                    Status: "available",
                    Resolutions: new[] { "1MP" },
                    AspectRatios: new[] { "match_input_image" },
                    MaxReferenceImages: 0,
                    SupportsImageToImage: true,
                    SupportsTextToImage: false),
            };
    }
}
