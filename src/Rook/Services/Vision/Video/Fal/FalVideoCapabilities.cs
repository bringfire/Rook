using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    public static class FalVideoCapabilities
    {
        public const string ProviderName = "fal";
        public const string WanT2v = "fal-ai/wan/v2.7/text-to-video";

        public static IReadOnlyDictionary<string, (VideoCapability Capability, IPricingModel<VideoGenerationRequest, VideoCapability> PricingModel)> Models { get; }
            = BuildModels();

        private static IReadOnlyDictionary<string, (VideoCapability, IPricingModel<VideoGenerationRequest, VideoCapability>)> BuildModels()
        {
            var dict = new Dictionary<string, (VideoCapability, IPricingModel<VideoGenerationRequest, VideoCapability>)>(StringComparer.Ordinal)
            {
                [WanT2v] = (
                    new VideoCapability(
                        Id: WanT2v,
                        Name: "Wan 2.7 Text to Video",
                        Status: "preview",
                        Resolutions: new[] { "720p", "1080p" },
                        Durations: new[] { 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 },
                        AspectRatios: new[] { "16:9", "9:16", "1:1", "4:3", "3:4" },
                        Modes: new[] { VideoMode.T2V },
                        SupportsReferenceImages: false,
                        MaxReferenceImages: 0,
                        Must8sWith: Array.Empty<string>()),
                    new FalWanT2vPricingModel()),
            };

            return dict;
        }
    }
}
