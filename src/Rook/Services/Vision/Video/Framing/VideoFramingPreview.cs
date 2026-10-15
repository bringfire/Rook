using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Framing
{
    internal sealed record VideoFramingSourceSlot(string Role, MediaRef Ref);
    internal sealed record VideoFramingPreviewRequest(string Model, VideoMode Mode, IReadOnlyList<VideoFramingSourceSlot> Sources, string Resolution, string AspectRatio);
    internal sealed record VideoFramingPreviewSlot(string Role, Guid PreviewId, string Sha256, int Width, int Height, int OriginalWidth, int OriginalHeight, bool Upscaled);
    internal sealed record VideoFramingPreviewVariant(IReadOnlyList<VideoFramingPreviewSlot> Slots, GenerationError? Error)
    { public bool Success => Error == null; }
    internal sealed record VideoFramingPreviewResult(VideoFramingPreviewVariant? Fit, VideoFramingPreviewVariant? Fill, GenerationError? Error);
}
