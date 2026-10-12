namespace Rook.Services.Vision.Image
{
    public enum ImageFallbackReason { GeminiKeyMissing, GeminiKeyRejected }
    public enum ImageExecutionPhase { Validation, Submission, Materialization, Publication, Interruption }
    public enum ImageCredentialFailureKind { Missing, Rejected }
    public enum ImageFalDispatchState { NotStarted, IntentRecorded, Attempted }

    public sealed record ImageRouteReceipt(
        string RequestedProvider, string RequestedModel, string EffectiveProvider,
        string EffectiveModel, string ProviderEndpoint, ImageFallbackReason FallbackReason,
        ImageExecutionPhase Phase, bool GenerationDispatchAttempted);
    public sealed record ImageCredentialFailure(string Provider, ImageCredentialFailureKind Kind);
    public sealed record ImageRoutingContext(ImageRouteReceipt? Route, ImageCredentialFailure? CredentialFailure);
}
