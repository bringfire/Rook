using System;
namespace Rook.Services.Vision.Image
{
    public sealed record ImageExecutionSnapshot(ImageGenerationRequest? EffectiveRequest,
        ResolvedImageModel? EffectiveModel, ImageRoutingContext? Routing, ImageFalDispatchState? FalDispatchState);

    /// <summary>One execution's safe attribution, also readable by a timeout boundary.</summary>
    public sealed class ImageExecutionContext
    {
        private readonly object _gate = new();
        private ImageExecutionSnapshot _snapshot = new(null, null, null, null);
        public ImageExecutionSnapshot Snapshot() { lock (_gate) return _snapshot; }
        public void Initialize(ImageGenerationRequest request, ResolvedImageModel model)
        {
            lock (_gate) _snapshot = new(request, model,
                model.ProviderName == "fal" && ImageRoutingCodec.IsFalModel(model.ModelId) ? new(null, null) : null,
                ImageRoutingCodec.IsAffected(model.ProviderName, model.ModelId) ? ImageFalDispatchState.NotStarted : null);
        }
        public void SelectFallbackTarget(ImageRouteReceipt route)
        { lock (_gate) _snapshot = new(null, null, new(route, null), ImageFalDispatchState.NotStarted); }
        public void SelectFallback(ImageGenerationRequest request, ResolvedImageModel model, ImageRouteReceipt route)
        { lock (_gate) _snapshot = new(request, model, new(route, null), ImageFalDispatchState.NotStarted); }
        public void SetPhase(ImageExecutionPhase phase)
        {
            lock (_gate)
                if (_snapshot.Routing?.Route is { } route)
                    _snapshot = _snapshot with { Routing = _snapshot.Routing with { Route = route with { Phase = phase } } };
        }
        public void MarkFalDispatchIntentRecorded()
        {
            lock (_gate)
                if (_snapshot.FalDispatchState == ImageFalDispatchState.NotStarted)
                    _snapshot = _snapshot with { FalDispatchState = ImageFalDispatchState.IntentRecorded };
        }
        public void MarkGenerationDispatchAttempted()
        {
            lock (_gate)
            {
                var route = _snapshot.Routing?.Route;
                _snapshot = _snapshot with
                {
                    FalDispatchState = ImageFalDispatchState.Attempted,
                    Routing = new(route == null ? null : route with
                        { GenerationDispatchAttempted = true, Phase = ImageExecutionPhase.Submission }, null)
                };
            }
        }
        public void SetCredentialFailure(ImageCredentialFailure? failure)
        {
            lock (_gate)
                _snapshot = _snapshot with { Routing = _snapshot.Routing == null && failure == null
                    ? null : new(_snapshot.Routing?.Route, failure) };
        }
    }
}
