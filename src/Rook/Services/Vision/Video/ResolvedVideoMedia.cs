using System;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Resolved bytes for a <see cref="VideoMediaRef"/>, ready for a
    /// provider to consume. The manager runs all media resolution before
    /// calling <see cref="IVideoProvider.SubmitAsync"/>, so providers
    /// never touch the artifact store or path validation directly.
    /// </summary>
    public sealed record ResolvedVideoMedia
    {
        public byte[] Bytes { get; }
        public string MimeType { get; }

        /// <summary>
        /// Human-readable description of where the bytes came from
        /// (e.g., "artifact:&lt;guid&gt; role:image"). Diagnostic only;
        /// do not include in cache keys or content hashes.
        /// </summary>
        public string SourceDescription { get; }

        public ResolvedVideoMedia(byte[] bytes, string mimeType, string sourceDescription)
        {
            if (bytes is null) throw new ArgumentNullException(nameof(bytes));
            if (bytes.Length == 0)
                throw new ArgumentException(
                    "Bytes must be non-empty.", nameof(bytes));
            if (string.IsNullOrWhiteSpace(mimeType))
                throw new ArgumentException(
                    "MimeType must be non-empty.", nameof(mimeType));
            if (string.IsNullOrWhiteSpace(sourceDescription))
                throw new ArgumentException(
                    "SourceDescription must be non-empty.", nameof(sourceDescription));

            Bytes = bytes;
            MimeType = mimeType;
            SourceDescription = sourceDescription;
        }
    }
}
