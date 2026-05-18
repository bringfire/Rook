using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Image
{
    public enum ImageInputTransportKind
    {
        InlineDataUri = 0,
        ReplicateHostedFileUrl = 1,
        FalHostedFileUrl = 2,
        CallerProvidedHttpsUrl = 3,
        Unsupported = 4,
    }

    public enum ImageLimitProvenance
    {
        ProviderDocumented = 0,
        ProviderTransportDocumented = 1,
        RookGuardProviderUnverified = 2,
    }

    public sealed class ImageMediaPolicy
    {
        public ImageMediaPolicy(
            string modelId,
            string modelLabel,
            ImageModelInputPolicy model,
            ImageTransportPolicy transport,
            ImageRookSafetyPolicy safety)
        {
            if (string.IsNullOrWhiteSpace(modelId))
                throw new ArgumentException("Model id must be non-empty.", nameof(modelId));
            if (string.IsNullOrWhiteSpace(modelLabel))
                throw new ArgumentException("Model label must be non-empty.", nameof(modelLabel));

            ModelId = modelId;
            ModelLabel = modelLabel;
            Model = model ?? throw new ArgumentNullException(nameof(model));
            Transport = transport ?? throw new ArgumentNullException(nameof(transport));
            Safety = safety ?? throw new ArgumentNullException(nameof(safety));
        }

        public string ModelId { get; }
        public string ModelLabel { get; }
        public ImageModelInputPolicy Model { get; }
        public ImageTransportPolicy Transport { get; }
        public ImageRookSafetyPolicy Safety { get; }

        public ImagePolicyValidationResult ValidateInputSet(
            int mediaCount,
            long aggregatePixels,
            bool hasPrompt)
        {
            if (!hasPrompt)
            {
                return ImagePolicyValidationResult.Fail(
                    $"{ModelLabel} requires prompt input.",
                    "prompt");
            }

            if (mediaCount < 0)
            {
                return ImagePolicyValidationResult.Fail(
                    $"{ModelLabel} input image count must be non-negative.",
                    "input_images");
            }

            if (mediaCount > Model.MaxInputImages)
            {
                return ImagePolicyValidationResult.Fail(
                    $"{ModelLabel} accepts up to {Model.MaxInputImages} input images.",
                    "input_images");
            }

            if (aggregatePixels > Model.MaxAggregatePixels)
            {
                return ImagePolicyValidationResult.Fail(
                    $"{ModelLabel} input images must be {Model.MaxAggregatePixels / 1_000_000L} megapixels or less in aggregate.",
                    "input_images");
            }

            return ImagePolicyValidationResult.Ok();
        }
    }

    public sealed class ImageModelInputPolicy
    {
        public ImageModelInputPolicy(
            IReadOnlyList<string> allowedMimeTypes,
            int maxInputImages,
            long maxAggregatePixels,
            ImageLimitProvenance pixelLimitProvenance,
            DateTime providerReviewedOn,
            string providerSourceUrl)
        {
            if (allowedMimeTypes is null) throw new ArgumentNullException(nameof(allowedMimeTypes));
            if (maxInputImages < 0)
                throw new ArgumentOutOfRangeException(nameof(maxInputImages), maxInputImages, "Max input images must be non-negative.");
            if (maxAggregatePixels < 0)
                throw new ArgumentOutOfRangeException(nameof(maxAggregatePixels), maxAggregatePixels, "Max aggregate pixels must be non-negative.");
            if (string.IsNullOrWhiteSpace(providerSourceUrl))
                throw new ArgumentException("Provider source URL must be non-empty.", nameof(providerSourceUrl));

            AllowedMimeTypes = CopyReadOnly(allowedMimeTypes);
            MaxInputImages = maxInputImages;
            MaxAggregatePixels = maxAggregatePixels;
            PixelLimitProvenance = pixelLimitProvenance;
            ProviderReviewedOn = providerReviewedOn;
            ProviderSourceUrl = providerSourceUrl;
        }

        public IReadOnlyList<string> AllowedMimeTypes { get; }
        public int MaxInputImages { get; }
        public long MaxAggregatePixels { get; }
        public ImageLimitProvenance PixelLimitProvenance { get; }
        public DateTime ProviderReviewedOn { get; }
        public string ProviderSourceUrl { get; }

        private static IReadOnlyList<T> CopyReadOnly<T>(IReadOnlyList<T> source)
        {
            var copy = new T[source.Count];
            for (int i = 0; i < source.Count; i++) copy[i] = source[i];
            return Array.AsReadOnly(copy);
        }
    }

    public sealed class ImageTransportPolicy
    {
        public ImageTransportPolicy(
            ImageInputTransportKind kind,
            long maxSingleUploadBytes,
            ImageLimitProvenance byteLimitProvenance,
            DateTime providerReviewedOn,
            string sourceUrl)
        {
            if (maxSingleUploadBytes < 0)
                throw new ArgumentOutOfRangeException(nameof(maxSingleUploadBytes), maxSingleUploadBytes, "Max single upload bytes must be non-negative.");
            if (string.IsNullOrWhiteSpace(sourceUrl))
                throw new ArgumentException("Source URL must be non-empty.", nameof(sourceUrl));

            Kind = kind;
            MaxSingleUploadBytes = maxSingleUploadBytes;
            ByteLimitProvenance = byteLimitProvenance;
            ProviderReviewedOn = providerReviewedOn;
            SourceUrl = sourceUrl;
        }

        public ImageInputTransportKind Kind { get; }
        public long MaxSingleUploadBytes { get; }
        public ImageLimitProvenance ByteLimitProvenance { get; }
        public DateTime ProviderReviewedOn { get; }
        public string SourceUrl { get; }
    }

    public sealed class ImageRookSafetyPolicy
    {
        public ImageRookSafetyPolicy(long maxSingleReadBytes, long maxAggregateReadBytes)
        {
            if (maxSingleReadBytes < 0)
                throw new ArgumentOutOfRangeException(nameof(maxSingleReadBytes), maxSingleReadBytes, "Max single read bytes must be non-negative.");
            if (maxAggregateReadBytes < 0)
                throw new ArgumentOutOfRangeException(nameof(maxAggregateReadBytes), maxAggregateReadBytes, "Max aggregate read bytes must be non-negative.");

            MaxSingleReadBytes = maxSingleReadBytes;
            MaxAggregateReadBytes = maxAggregateReadBytes;
        }

        public long MaxSingleReadBytes { get; }
        public long MaxAggregateReadBytes { get; }
    }

    public sealed class ImagePolicyValidationResult
    {
        private ImagePolicyValidationResult(bool success, string? message, string? field)
        {
            Success = success;
            Message = message;
            Field = field;
        }

        public bool Success { get; }
        public string? Message { get; }
        public string? Field { get; }

        public static ImagePolicyValidationResult Ok()
        {
            return new ImagePolicyValidationResult(true, null, null);
        }

        public static ImagePolicyValidationResult Fail(string message, string field)
        {
            if (string.IsNullOrWhiteSpace(message))
                throw new ArgumentException("Message must be non-empty.", nameof(message));
            if (string.IsNullOrWhiteSpace(field))
                throw new ArgumentException("Field must be non-empty.", nameof(field));

            return new ImagePolicyValidationResult(false, message, field);
        }
    }
}
