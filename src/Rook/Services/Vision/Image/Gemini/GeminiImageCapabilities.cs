using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Gemini
{
    public static class GeminiImageCapabilities
    {
        public const string ProviderName = "gemini";
        public const string NanoBanana2 = "gemini-3.1-flash-image";
        public const string NanoBananaPro = "gemini-3-pro-image";
        public const string DefaultModel = NanoBanana2;
        public const string DefaultShortName = "nano-banana-2";

        public static readonly IReadOnlyDictionary<string, string> ShortNameToId =
            new Dictionary<string, string>(System.StringComparer.Ordinal)
            {
                ["nano-banana-2"] = NanoBanana2,
                ["nano-banana-pro"] = NanoBananaPro,
            };

        private static readonly string[] CommonAspectRatios =
        {
            "1:1", "1:4", "4:1", "1:8", "8:1",
            "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
            "9:16", "16:9", "21:9",
        };

        public static readonly IReadOnlyDictionary<string, ImageCapability> Models =
            new Dictionary<string, ImageCapability>(System.StringComparer.Ordinal)
            {
                [NanoBanana2] = new ImageCapability(
                    Id: NanoBanana2,
                    Name: "Nano Banana 2",
                    Status: "ga",
                    Resolutions: new[] { "512", "1K", "2K", "4K" },
                    AspectRatios: CommonAspectRatios,
                    MaxReferenceImages: 8,
                    SupportsImageToImage: true,
                    SupportsTextToImage: true),
                [NanoBananaPro] = new ImageCapability(
                    Id: NanoBananaPro,
                    Name: "Nano Banana Pro",
                    Status: "ga",
                    Resolutions: new[] { "1K", "2K", "4K" },
                    AspectRatios: CommonAspectRatios,
                    MaxReferenceImages: 8,
                    SupportsImageToImage: true,
                    SupportsTextToImage: true),
            };

        public static readonly IReadOnlyList<IReadOnlyDictionary<string, object?>> AvailableModels =
            new List<IReadOnlyDictionary<string, object?>>
            {
                new Dictionary<string, object?>
                {
                    ["short_name"] = "nano-banana-2",
                    ["label"] = "Nano Banana 2",
                    ["description"] = "Fast, high quality",
                    ["supported_resolutions"] = new[] { "512", "1K", "2K", "4K" },
                },
                new Dictionary<string, object?>
                {
                    ["short_name"] = "nano-banana-pro",
                    ["label"] = "Nano Banana Pro",
                    ["description"] = "Highest quality",
                    ["supported_resolutions"] = new[] { "1K", "2K", "4K" },
                },
            };

        public static string ResolveShortName(string? nameOrId)
        {
            if (string.IsNullOrEmpty(nameOrId)) return DefaultModel;
            return ShortNameToId.TryGetValue(nameOrId!, out var fullId)
                ? fullId
                : nameOrId!;
        }

        public static string ShortNameForMessage(string model)
        {
            if (string.Equals(model, NanoBananaPro, System.StringComparison.Ordinal))
                return "nano-banana-pro";
            if (string.Equals(model, NanoBanana2, System.StringComparison.Ordinal))
                return "nano-banana-2";
            return model;
        }

    }
}
