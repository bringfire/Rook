using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Image.Fal
{
    public static class FalImageCapabilities
    {
        public const string ProviderName = "fal";
        public const string FluxSchnell = "fal-ai/flux/schnell";
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
            };
    }
}
