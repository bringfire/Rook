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
        public const long Flux2ProMaxAggregatePixels = 9_000_000L;
        public const long ReplicateFileUploadMaxBytes = 100L * 1024L * 1024L;

        public static readonly ImageMediaPolicy Flux2ProMediaPolicy =
            new ImageMediaPolicy(
                modelId: Flux2Pro,
                modelLabel: "Flux 2 Pro",
                model: new ImageModelInputPolicy(
                    allowedMimeTypes: new[] { "image/jpeg", "image/png", "image/gif", "image/webp" },
                    maxInputImages: 8,
                    maxAggregatePixels: Flux2ProMaxAggregatePixels,
                    pixelLimitProvenance: ImageLimitProvenance.ProviderDocumented,
                    providerReviewedOn: new DateTime(2026, 5, 18),
                    providerSourceUrl: "https://replicate.com/black-forest-labs/flux-2-pro/versions/f558a59a8bf126d892ab219846966674f6acc616940c17841aeb242e245952ff/api"),
                transport: new ImageTransportPolicy(
                    kind: ImageInputTransportKind.ReplicateHostedFileUrl,
                    maxSingleUploadBytes: ReplicateFileUploadMaxBytes,
                    byteLimitProvenance: ImageLimitProvenance.ProviderTransportDocumented,
                    providerReviewedOn: new DateTime(2026, 5, 18),
                    sourceUrl: "https://replicate.com/docs/topics/predictions/input-files"),
                safety: new ImageRookSafetyPolicy(
                    maxSingleReadBytes: ReplicateFileUploadMaxBytes,
                    maxAggregateReadBytes: ReplicateFileUploadMaxBytes));

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
