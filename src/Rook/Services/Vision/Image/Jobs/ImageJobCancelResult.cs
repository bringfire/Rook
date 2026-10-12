using System;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed record ImageJobCancelResult
    {
        public ImageJobState State { get; }
        public GenerationError? Error { get; }

        public string? Provider { get; private init; }
        public string? Model { get; private init; }
        public ImageRoutingContext? Routing { get; private init; }
        public ImageFalDispatchState? FalDispatchState { get; private init; }
        public ImageJobCancelResult WithRouting(string provider, string model,
            ImageRoutingContext? routing, ImageFalDispatchState? falDispatchState = null) =>
            this with { Provider = provider, Model = model, Routing = routing, FalDispatchState = falDispatchState };

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
