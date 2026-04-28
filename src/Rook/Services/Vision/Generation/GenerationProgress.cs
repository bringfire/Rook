namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Optional progress signal exposed by providers that surface one.
    /// Veo emits operation-style progress; fal queue exposes
    /// <c>queue_position</c>; Replicate exposes streaming logs but no
    /// percentage. Providers populate the field they have signal for
    /// and leave the rest null.
    /// </summary>
    public sealed record GenerationProgress(
        double? PercentComplete = null,
        int? QueuePosition = null,
        string? Message = null);
}
