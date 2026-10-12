using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Image.Fal
{
    public static class FalImageCapabilities
    {
        public const string ProviderName = "fal";
        public const string FluxSchnell = "fal-ai/flux/schnell";
        public const string GptImage2Edit = "openai/gpt-image-2/edit";
        public const string DefaultModel = FluxSchnell;
        public const string NanoBanana2 = "fal-ai/nano-banana-2";
        public const string NanoBananaPro = "fal-ai/nano-banana-pro";

        public static readonly IReadOnlyDictionary<string, ImageCapability> Models =
            new Dictionary<string, ImageCapability>(StringComparer.Ordinal)
            {
                [NanoBanana2] = new ImageCapability(NanoBanana2, "Nano Banana 2 (fal.ai)", "available",
                    new[] { "0.5K", "1K", "2K", "4K" },
                    new[] { "1:1", "1:4", "4:1", "1:8", "8:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9" },
                    8, true, true),
                [NanoBananaPro] = new ImageCapability(NanoBananaPro, "Nano Banana Pro (fal.ai)", "available",
                    new[] { "1K", "2K", "4K" },
                    new[] { "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9" },
                    8, true, true),
                [FluxSchnell] = new ImageCapability(
                    Id: FluxSchnell,
                    Name: "FLUX.1 Schnell",
                    Status: "available",
                    Resolutions: new[] { "1K" },
                    AspectRatios: new[] { "1:1", "4:3", "3:4", "16:9", "9:16" },
                    MaxReferenceImages: 0,
                    SupportsImageToImage: false,
                    SupportsTextToImage: true),

                [GptImage2Edit] = new ImageCapability(
                    Id: GptImage2Edit,
                    Name: "GPT Image 2 Edit",
                    Status: "available",
                    Resolutions: new[] { "auto" },
                    AspectRatios: new[] { "match_input_image" },
                    MaxReferenceImages: 0,
                    SupportsImageToImage: true,
                    SupportsTextToImage: false),
            };
    }
}
