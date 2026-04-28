using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Bytes-resolved form of a <see cref="MediaRef"/>. The manager
    /// resolves all media refs in a request to bytes via
    /// <see cref="IMediaResolver"/> before invoking the provider's
    /// submit, keeping providers independent of artifact-storage
    /// layout.
    /// </summary>
    public sealed record ResolvedMedia(byte[] Bytes, string MimeType)
    {
        public byte[] Bytes { get; init; } =
            Bytes is null ? throw new ArgumentNullException(nameof(Bytes))
            : Bytes.Length == 0 ? throw new ArgumentException(
                "Bytes must be non-empty.", nameof(Bytes))
            : Bytes;

        public string MimeType { get; init; } =
            string.IsNullOrWhiteSpace(MimeType)
                ? throw new ArgumentException("MimeType must be non-empty.", nameof(MimeType))
                : MimeType;
    }
}
