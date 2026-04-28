using System;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    public sealed record VideoCostEstimateResult(
        bool Success,
        VideoCostEstimate? Estimate,
        GenerationError? Error)
    {
        public static VideoCostEstimateResult Ok(VideoCostEstimate estimate) =>
            new(true, estimate, null);

        public static VideoCostEstimateResult Fail(GenerationError error)
        {
            if (error is null) throw new ArgumentNullException(nameof(error));
            return new(false, null, error);
        }

        public static VideoCostEstimateResult Fail(VideoJobError error) =>
            Fail((GenerationError)error);
    }
}
