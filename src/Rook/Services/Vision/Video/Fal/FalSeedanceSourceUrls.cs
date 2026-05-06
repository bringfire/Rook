using System;

namespace Rook.Services.Vision.Video.Fal
{
    internal sealed class FalSeedanceSourceUrls
    {
        public FalSeedanceSourceUrls(string imageUrl, string? endImageUrl)
        {
            if (string.IsNullOrWhiteSpace(imageUrl))
                throw new ArgumentException("Seedance image URL must be non-empty.", nameof(imageUrl));

            ImageUrl = imageUrl;
            EndImageUrl = endImageUrl;
        }

        public string ImageUrl { get; }
        public string? EndImageUrl { get; }
    }
}
