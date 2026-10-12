using System;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed record ImageJobSubmitResult
    {
        public ImageJobState State { get; }
        public Guid? JobId { get; }
        public GenerationError? Error { get; }

        public string? Provider { get; private init; }
        public string? Model { get; private init; }
        public ImageRoutingContext? Routing { get; private init; }
        public ImageFalDispatchState? FalDispatchState { get; private init; }
        public ImageJobSubmitResult WithRouting(string provider, string model,
            ImageRoutingContext? routing, ImageFalDispatchState? falDispatchState = null) =>
            this with { Provider = provider, Model = model, Routing = routing, FalDispatchState = falDispatchState };

        private ImageJobSubmitResult(
            ImageJobState state, Guid? jobId, GenerationError? error)
        {
            State = state;
            JobId = jobId;
            Error = error;
        }

        public static ImageJobSubmitResult Ok(Guid jobId, ImageJobState state)
        {
            if (jobId == Guid.Empty)
                throw new ArgumentException(
                    "JobId must be non-empty for a successful submit.",
                    nameof(jobId));

            return new ImageJobSubmitResult(state, jobId, error: null);
        }

        public static ImageJobSubmitResult Fail(GenerationError error)
        {
            if (error is null)
                throw new ArgumentNullException(nameof(error));

            return new ImageJobSubmitResult(
                ImageJobState.Error, jobId: null, error);
        }
    }
}
