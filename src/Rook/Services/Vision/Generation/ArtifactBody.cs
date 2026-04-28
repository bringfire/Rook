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
    public abstract record ArtifactBody
    {
        private protected ArtifactBody() { }
    }

    /// <summary>URL-referenced artifact. The manager fetches at
    /// materialization time. <see cref="SignedUrlTtl"/> is non-null when
    /// the provider exposes a TTL (fal signed URLs); the manager uses
    /// it to decide whether to re-fetch on cold-load.
    ///
    /// <para>Invariants enforced at construction:
    /// <list type="bullet">
    ///   <item><see cref="Url"/> must be absolute and use <c>http</c>
    ///         or <c>https</c> scheme.</item>
    ///   <item><see cref="SignedUrlTtl"/>, when non-null, must be
    ///         strictly positive. A zero or negative TTL means
    ///         "already expired" which is meaningless at submit
    ///         time.</item>
    /// </list></para></summary>
    public sealed record RemoteArtifactBody : ArtifactBody
    {
        public RemoteArtifactBody(Uri Url, TimeSpan? SignedUrlTtl = null)
        {
            if (Url is null) throw new ArgumentNullException(nameof(Url));
            if (!Url.IsAbsoluteUri)
                throw new ArgumentException(
                    $"RemoteArtifactBody.Url must be absolute; got '{Url}'.",
                    nameof(Url));
            if (Url.Scheme != Uri.UriSchemeHttp && Url.Scheme != Uri.UriSchemeHttps)
                throw new ArgumentException(
                    $"RemoteArtifactBody.Url must use http or https scheme; got '{Url.Scheme}'.",
                    nameof(Url));
            if (SignedUrlTtl is { } ttl && ttl <= TimeSpan.Zero)
                throw new ArgumentException(
                    $"SignedUrlTtl must be strictly positive when set; got {ttl}.",
                    nameof(SignedUrlTtl));

            this.Url = Url;
            this.SignedUrlTtl = SignedUrlTtl;
        }

        public Uri Url { get; init; }
        public TimeSpan? SignedUrlTtl { get; init; }
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
