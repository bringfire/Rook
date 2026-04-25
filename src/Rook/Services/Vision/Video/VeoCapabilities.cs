using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Pure data table of Veo model capabilities + per-model pricing.
    /// V1c: renamed from V1b's <c>VideoCapabilities</c> (which was Veo-only
    /// despite the generic name); validation moved to
    /// <see cref="CapabilityValidator"/> (provider-neutral) and
    /// <see cref="VeoOptionsCodec"/> (Veo-specific PersonGeneration matrix).
    ///
    /// Sources:
    ///   - https://ai.google.dev/gemini-api/docs/video
    ///   - https://ai.google.dev/gemini-api/docs/pricing
    ///
    /// Conservative policy: features are marked supported only where
    /// primary Google documentation confirms them for the exact model id.
    /// </summary>
    public static class VeoCapabilities
    {
        public const string ProviderName = "veo";

        public const string DefaultModelId = "veo-3.1-lite-generate-preview";

        public const string PricingSource = "veo-rate-card-v1";

        public static IReadOnlyDictionary<string, (ModelCapability Capability, IPricingModel PricingModel)> Models { get; }
            = BuildModels();

        private static IReadOnlyDictionary<string, (ModelCapability, IPricingModel)> BuildModels()
        {
            var t2vI2vInterp = new[] { VideoMode.T2V, VideoMode.I2V, VideoMode.Interp };

            var dict = new Dictionary<string, (ModelCapability, IPricingModel)>(StringComparer.Ordinal);

            dict["veo-3.1-generate-preview"] = (
                new ModelCapability(
                    Id: "veo-3.1-generate-preview",
                    Name: "Veo 3.1",
                    Status: "preview",
                    Resolutions: new[] { "720p", "1080p", "4k" },
                    Durations: new[] { 4, 6, 8 },
                    AspectRatios: new[] { "16:9", "9:16" },
                    Modes: t2vI2vInterp,
                    SupportsReferenceImages: true,
                    MaxReferenceImages: 3,
                    Must8sWith: new[] { "1080p", "4k", "referenceImages" }),
                new PerSecondPricingModel(
                    ratesPerSecondUsd: new Dictionary<string, decimal>
                    {
                        ["720p"] = 0.40m,
                        ["1080p"] = 0.40m,
                        ["4k"] = 0.60m,
                    },
                    pricingSource: PricingSource));

            dict["veo-3.1-fast-generate-preview"] = (
                new ModelCapability(
                    Id: "veo-3.1-fast-generate-preview",
                    Name: "Veo 3.1 Fast",
                    Status: "preview",
                    Resolutions: new[] { "720p", "1080p", "4k" },
                    Durations: new[] { 4, 6, 8 },
                    AspectRatios: new[] { "16:9", "9:16" },
                    Modes: t2vI2vInterp,
                    SupportsReferenceImages: true,
                    MaxReferenceImages: 3,
                    Must8sWith: new[] { "1080p", "4k", "referenceImages" }),
                new PerSecondPricingModel(
                    ratesPerSecondUsd: new Dictionary<string, decimal>
                    {
                        ["720p"] = 0.10m,
                        ["1080p"] = 0.12m,
                        ["4k"] = 0.30m,
                    },
                    pricingSource: PricingSource));

            dict["veo-3.1-lite-generate-preview"] = (
                new ModelCapability(
                    Id: "veo-3.1-lite-generate-preview",
                    Name: "Veo 3.1 Lite",
                    Status: "preview",
                    Resolutions: new[] { "720p", "1080p" },
                    Durations: new[] { 4, 6, 8 },
                    AspectRatios: new[] { "16:9", "9:16" },
                    Modes: t2vI2vInterp,
                    SupportsReferenceImages: false,
                    MaxReferenceImages: 0,
                    Must8sWith: new[] { "1080p" }),
                new PerSecondPricingModel(
                    ratesPerSecondUsd: new Dictionary<string, decimal>
                    {
                        ["720p"] = 0.05m,
                        ["1080p"] = 0.08m,
                    },
                    pricingSource: PricingSource));

            dict["veo-3.0-generate-001"] = (
                new ModelCapability(
                    Id: "veo-3.0-generate-001",
                    Name: "Veo 3",
                    Status: "stable",
                    Resolutions: new[] { "720p", "1080p" },
                    Durations: new[] { 8 },
                    AspectRatios: new[] { "16:9" },
                    Modes: t2vI2vInterp,
                    SupportsReferenceImages: false,
                    MaxReferenceImages: 0,
                    Must8sWith: Array.Empty<string>()),
                new PerSecondPricingModel(
                    ratesPerSecondUsd: new Dictionary<string, decimal>
                    {
                        ["720p"] = 0.40m,
                        ["1080p"] = 0.40m,
                    },
                    pricingSource: PricingSource));

            dict["veo-3.0-fast-generate-001"] = (
                new ModelCapability(
                    Id: "veo-3.0-fast-generate-001",
                    Name: "Veo 3 Fast",
                    Status: "stable",
                    Resolutions: new[] { "720p", "1080p" },
                    Durations: new[] { 8 },
                    AspectRatios: new[] { "16:9" },
                    Modes: t2vI2vInterp,
                    SupportsReferenceImages: false,
                    MaxReferenceImages: 0,
                    Must8sWith: Array.Empty<string>()),
                new PerSecondPricingModel(
                    ratesPerSecondUsd: new Dictionary<string, decimal>
                    {
                        ["720p"] = 0.10m,
                        ["1080p"] = 0.12m,
                    },
                    pricingSource: PricingSource));

            dict["veo-2.0-generate-001"] = (
                new ModelCapability(
                    Id: "veo-2.0-generate-001",
                    Name: "Veo 2",
                    Status: "stable",
                    Resolutions: new[] { "720p" },
                    Durations: new[] { 5, 6, 8 },
                    AspectRatios: new[] { "16:9", "9:16" },
                    Modes: t2vI2vInterp,
                    SupportsReferenceImages: false,
                    MaxReferenceImages: 0,
                    Must8sWith: Array.Empty<string>()),
                new PerSecondPricingModel(
                    ratesPerSecondUsd: new Dictionary<string, decimal>
                    {
                        ["720p"] = 0.35m,
                    },
                    pricingSource: PricingSource));

            return dict;
        }
    }
}
