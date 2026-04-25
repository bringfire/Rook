namespace Rook.Services.Vision.Video
{
    public sealed record VideoJobError(
        VideoErrorCode Code,
        string Message,
        bool Retryable,
        string? ProviderMessage = null,
        string? Field = null);
}
