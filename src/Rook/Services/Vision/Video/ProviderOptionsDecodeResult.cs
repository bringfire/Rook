using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Envelope for <see cref="IProviderOptionsCodec.Deserialize"/>.
    /// Failure carries the offending field path + message so callers
    /// (replay, diagnostics, cache-key derivation) surface a typed
    /// <see cref="VideoJobError"/> instead of dropping malformed records
    /// silently.
    /// </summary>
    public sealed record ProviderOptionsDecodeResult(
        bool Success,
        ProviderOptions? Options,
        string? Field,
        string? Message)
    {
        public static ProviderOptionsDecodeResult Ok(ProviderOptions options) =>
            new(true, options, null, null);

        public static ProviderOptionsDecodeResult Fail(string field, string message) =>
            new(false, null, field, message);
    }
}
