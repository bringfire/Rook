using System;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed record ImageJobCancelResult
    {
        public ImageJobState State { get; }
        public GenerationError? Error { get; }

        private ImageJobCancelResult(ImageJobState state, GenerationError? error)
        {
            State = state;
            Error = error;
        }

        public static ImageJobCancelResult Ok(ImageJobState state) =>
            new(state, error: null);

        public static ImageJobCancelResult Fail(GenerationError error)
        {
            if (error is null)
                throw new ArgumentNullException(nameof(error));

            return new ImageJobCancelResult(ImageJobState.Error, error);
        }
    }
}
