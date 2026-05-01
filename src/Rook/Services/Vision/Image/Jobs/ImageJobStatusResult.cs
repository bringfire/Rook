using System;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed record ImageJobStatusResult
    {
        public ImageJobState State { get; }
        public GenerationProgress? Progress { get; }
        public Guid? ResultArtifactId { get; }
        public GenerationError? Error { get; }

        private ImageJobStatusResult(
            ImageJobState state,
            GenerationProgress? progress,
            Guid? resultArtifactId,
            GenerationError? error)
        {
            State = state;
            Progress = progress;
            ResultArtifactId = resultArtifactId;
            Error = error;
        }

        public static ImageJobStatusResult InFlight(
            ImageJobState state, GenerationProgress? progress)
        {
            if (!IsInFlight(state))
                throw new ArgumentException(
                    $"InFlight requires a non-terminal state; got {state}.",
                    nameof(state));

            return new ImageJobStatusResult(
                state, progress, resultArtifactId: null, error: null);
        }

        public static ImageJobStatusResult Complete(Guid resultArtifactId)
        {
            if (resultArtifactId == Guid.Empty)
                throw new ArgumentException(
                    "ResultArtifactId must be non-empty for Complete.",
                    nameof(resultArtifactId));

            return new ImageJobStatusResult(
                ImageJobState.Complete,
                progress: null,
                resultArtifactId,
                error: null);
        }

        public static ImageJobStatusResult Failed(
            ImageJobState terminal, GenerationError error)
        {
            if (!IsTerminalFailure(terminal))
                throw new ArgumentException(
                    $"Failed requires a terminal failure state; got {terminal}.",
                    nameof(terminal));
            if (error is null)
                throw new ArgumentNullException(nameof(error));

            return new ImageJobStatusResult(
                terminal,
                progress: null,
                resultArtifactId: null,
                error);
        }

        private static bool IsInFlight(ImageJobState state) =>
            state is ImageJobState.Queued
              or ImageJobState.Submitting
              or ImageJobState.Polling
              or ImageJobState.Materializing;

        private static bool IsTerminalFailure(ImageJobState state) =>
            state is ImageJobState.Error
              or ImageJobState.Cancelled
              or ImageJobState.Interrupted;
    }
}
