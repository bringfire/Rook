using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed class ImageJobStartRequest
    {
        public ImageJobStartRequest(
            ImageGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
            IReadOnlyList<Guid> parentArtifactIds)
        {
            Request = request ?? throw new ArgumentNullException(nameof(request));
            ResolvedMedia = resolvedMedia
                ?? throw new ArgumentNullException(nameof(resolvedMedia));
            ParentArtifactIds = parentArtifactIds
                ?? throw new ArgumentNullException(nameof(parentArtifactIds));
        }

        public ImageGenerationRequest Request { get; }
        public IReadOnlyDictionary<MediaRef, ResolvedMedia> ResolvedMedia { get; }
        public IReadOnlyList<Guid> ParentArtifactIds { get; }
    }
}
