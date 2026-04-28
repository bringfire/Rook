namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Outcome of a capability or options-codec validation pass.
    /// <see cref="Field"/> is the name of the offending field for
    /// downstream error classification (so a generic message like
    /// "value out of range" can still be classified as
    /// <see cref="GenerationErrorCode.UnsupportedMedia"/> vs
    /// <see cref="GenerationErrorCode.InvalidRequest"/> based on which
    /// field triggered).
    /// </summary>
    public sealed record ValidationResult(
        bool Success,
        string? Message = null,
        string? Field = null)
    {
        public static ValidationResult Ok() => new(Success: true);

        public static ValidationResult Fail(string message, string? field = null) =>
            new(Success: false, Message: message, Field: field);
    }
}
