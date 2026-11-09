using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Fal;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed class ImageJobStartRequest
    {
        public ImageJobStartRequest(
            ImageGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
            IReadOnlyList<Guid> parentArtifactIds,
            ResolvedImageModel? resolvedModel = null,
            FalPricingSnapshot? configuredPricing = null,
            FalNormalizedRequest? configuredRequest = null,
            FalMediaSnapshot? configuredMedia = null,
            FalSubmitConfirmation? configuredConfirmation = null)
        {
            Request = request ?? throw new ArgumentNullException(nameof(request));
            ResolvedMedia = resolvedMedia
                ?? throw new ArgumentNullException(nameof(resolvedMedia));
            ParentArtifactIds = parentArtifactIds
                ?? throw new ArgumentNullException(nameof(parentArtifactIds));
            ResolvedModel = resolvedModel;
            ConfiguredPricing = configuredPricing;
            ConfiguredRequest = configuredRequest;
            ConfiguredMedia = configuredMedia;
            ConfiguredConfirmation = configuredConfirmation;
        }

        public ImageGenerationRequest Request { get; }
        public IReadOnlyDictionary<MediaRef, ResolvedMedia> ResolvedMedia { get; }
        public IReadOnlyList<Guid> ParentArtifactIds { get; }
        public ResolvedImageModel? ResolvedModel { get; }
        /// <summary>Compatibility input only; configured admission recomputes its own price.</summary>
        public FalPricingSnapshot? ConfiguredPricing { get; }
        public FalNormalizedRequest? ConfiguredRequest { get; }
        /// <summary>Ownership transfers on SubmitAsync, including all rejected admission paths.</summary>
        public FalMediaSnapshot? ConfiguredMedia { get; }
        public FalSubmitConfirmation? ConfiguredConfirmation { get; }
    }
}
