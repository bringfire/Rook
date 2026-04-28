using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Closed discriminated union for an artifact's payload.
    /// URL-xor-inline is enforced at the type level: a
    /// <see cref="ResultArtifact"/> carries exactly one of
    /// <see cref="RemoteArtifactBody"/> or
    /// <see cref="InlineArtifactBody"/>, never both.
    ///
    /// <para>Closure: abstract class with <c>private protected</c>
    /// parameterless ctor — no compiler-generated copy constructor
    /// (which a record's <c>protected</c> copy ctor would otherwise
    /// expose to external derivation).</para>
    ///
    /// <para>Phase 0 evidence: fal and Replicate return URL-referenced
    /// artifacts on a CDN; Gemini returns inline base64 bytes in the
    /// API response. Both delivery models must be supported.</para>
    /// </summary>
    public abstract class ArtifactBody
    {
        private protected ArtifactBody() { }
    }

    /// <summary>URL-referenced artifact. The manager fetches at
    /// materialization time. <see cref="SignedUrlTtl"/> is non-null
    /// when the provider exposes a TTL.
    ///
    /// <para>Invariants enforced at construction:
    /// <list type="bullet">
    ///   <item><see cref="Url"/> must be absolute and use <c>http</c>
    ///         or <c>https</c>.</item>
    ///   <item><see cref="SignedUrlTtl"/>, when non-null, must be
    ///         strictly positive.</item>
    /// </list>
    /// Properties are read-only — no <c>init</c> setter — so the
    /// invariants cannot be bypassed via object initializers.</para></summary>
    public sealed class RemoteArtifactBody : ArtifactBody
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

        public Uri Url { get; }
        public TimeSpan? SignedUrlTtl { get; }
    }

    /// <summary>Inline-bytes artifact. The provider already
    /// materialized the bytes (Gemini, Veo's downloaded payload).
    /// The manager goes directly to artifact-store write without a
    /// follow-up fetch.</summary>
    public sealed class InlineArtifactBody : ArtifactBody
    {
        public InlineArtifactBody(byte[] Bytes)
        {
            if (Bytes is null) throw new ArgumentNullException(nameof(Bytes));
            if (Bytes.Length == 0)
                throw new ArgumentException(
                    "Bytes must be non-empty for InlineArtifactBody.", nameof(Bytes));

            this.Bytes = Bytes;
        }

        public byte[] Bytes { get; }
    }
}
