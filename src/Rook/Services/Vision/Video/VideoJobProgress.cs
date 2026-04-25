namespace Rook.Services.Vision.Video
{
    public sealed record VideoJobProgress(
        int? Pct,
        string? Stage,
        string? Message);
}
