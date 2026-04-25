using System;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Outcome of <see cref="IVideoProvider.FetchResultAsync"/> — raw bytes
    /// from the provider, before any manager-side artifact write. The
    /// manager mints the artifact id; the provider only carries bytes.
    ///
    /// Constructed only via <see cref="Ok"/> or <see cref="Fail"/>;
    /// <c>Error == null ⇔ Bytes != null &amp;&amp; MimeType != null</c>.
    /// </summary>
    public sealed record ProviderFetchResult
    {
        public byte[]? Bytes { get; }
        public string? MimeType { get; }
        public VideoJobError? Error { get; }

        private ProviderFetchResult(
            byte[]? bytes, string? mimeType, VideoJobError? error)
        {
            Bytes = bytes;
            MimeType = mimeType;
            Error = error;
        }

        public static ProviderFetchResult Ok(byte[] bytes, string mimeType)
        {
            if (bytes is null)
                throw new ArgumentNullException(nameof(bytes));
            if (bytes.Length == 0)
                throw new ArgumentException(
                    "Bytes must be non-empty for Ok.", nameof(bytes));
            if (string.IsNullOrWhiteSpace(mimeType))
                throw new ArgumentException(
                    "MimeType must be non-empty for Ok.", nameof(mimeType));

            return new ProviderFetchResult(bytes, mimeType, error: null);
        }

        public static ProviderFetchResult Fail(VideoJobError error)
        {
            if (error is null)
                throw new ArgumentNullException(nameof(error));

            return new ProviderFetchResult(bytes: null, mimeType: null, error);
        }
    }
}
