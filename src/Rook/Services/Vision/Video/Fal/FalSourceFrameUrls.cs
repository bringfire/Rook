using System;

namespace Rook.Services.Vision.Video.Fal
{
    internal sealed class FalSourceFrameUrls
    {
        public FalSourceFrameUrls(string startImageUrl, string? endImageUrl)
        {
            if (string.IsNullOrWhiteSpace(startImageUrl))
                throw new ArgumentException("Start image URL must be non-empty.", nameof(startImageUrl));

            StartImageUrl = startImageUrl;
            EndImageUrl = endImageUrl;
        }

        public string StartImageUrl { get; }
        public string? EndImageUrl { get; }
    }
}
