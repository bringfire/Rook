using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Sealed-record union for an artifact's payload. URL-xor-inline is
    /// enforced at the type level: a <see cref="ResultArtifact"/> carries
    /// exactly one of <see cref="RemoteArtifactBody"/> or
    /// <see cref="InlineArtifactBody"/>, never both.
    ///
    /// <para>Phase 0 evidence: fal and Replicate return URL-referenced
    /// artifacts on a CDN (<c>v3b.fal.media</c>,
    /// <c>replicate.delivery</c>); Gemini returns inline base64 bytes in
    /// the API response. Both delivery models must be supported from
    /// day one without forcing one shape into the other.</para>
    /// </summary>
    public abstract record ArtifactBody;

    /// <summary>URL-referenced artifact. The manager fetches at
    /// materialization time. <see cref="SignedUrlTtl"/> is non-null when
    /// the provider exposes a TTL (fal signed URLs); the manager uses
    /// it to decide whether to re-fetch on cold-load.</summary>
    public sealed record RemoteArtifactBody(Uri Url, TimeSpan? SignedUrlTtl = null) : ArtifactBody
    {
        public Uri Url { get; init; } = Url ?? throw new ArgumentNullException(nameof(Url));
    }

    /// <summary>Inline-bytes artifact. The provider already materialized
    /// the bytes (Gemini, Veo's downloaded payload). The manager goes
    /// directly to artifact-store write without a follow-up fetch.</summary>
    public sealed record InlineArtifactBody(byte[] Bytes) : ArtifactBody
    {
        public byte[] Bytes { get; init; } =
            Bytes is null ? throw new ArgumentNullException(nameof(Bytes))
            : Bytes.Length == 0 ? throw new ArgumentException(
                "Bytes must be non-empty for InlineArtifactBody.", nameof(Bytes))
            : Bytes;
    }
}
