namespace Rook.Services.Vision.Video
{
    public sealed record ValidationResult(
        bool Success,
        string? Field,
        string? Message)
    {
        public static ValidationResult Ok() => new(true, null, null);

        public static ValidationResult Fail(string field, string message) =>
            new(false, field, message);
    }
}
