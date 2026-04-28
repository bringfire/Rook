using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Bytes-resolved form of a <see cref="MediaRef"/>. The manager
    /// resolves all media refs in a request to bytes via
    /// <see cref="IMediaResolver"/> before invoking the provider's
    /// submit, keeping providers independent of artifact-storage
    /// layout.
    ///
    /// <para>Sealed class with read-only properties — invariants cannot
    /// be bypassed via <c>with</c> or object initializers.</para>
    /// </summary>
    public sealed class ResolvedMedia
    {
        public ResolvedMedia(byte[] Bytes, string MimeType)
        {
            if (Bytes is null) throw new ArgumentNullException(nameof(Bytes));
            if (Bytes.Length == 0)
                throw new ArgumentException("Bytes must be non-empty.", nameof(Bytes));
            if (string.IsNullOrWhiteSpace(MimeType))
                throw new ArgumentException("MimeType must be non-empty.", nameof(MimeType));

            this.Bytes = Bytes;
            this.MimeType = MimeType;
        }

        public byte[] Bytes { get; }
        public string MimeType { get; }
    }
}
