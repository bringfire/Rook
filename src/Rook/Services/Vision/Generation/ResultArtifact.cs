using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// A single artifact within a <see cref="ProviderResultEnvelope"/>.
    ///
    /// <para><see cref="DeclaredMimeType"/> is the provider-asserted
    /// MIME type and is <b>nullable</b>. fal sync image, Veo, fal queue
    /// video, and Gemini all populate it; Replicate's flat
    /// <c>output: [&lt;url&gt;]</c> list does not. The materializing
    /// manager resolves null MIME for URL-bodied artifacts by reading
    /// the fetch response's <c>Content-Type</c> header, falling back to
    /// magic-byte sniffing if the header is absent or
    /// <c>application/octet-stream</c>. Inline-bytes artifacts must
    /// arrive with declared MIME — a null is an unrecoverable provider
    /// contract violation, not a missing-MIME case.</para>
    ///
    /// <para><see cref="ProviderMetadata"/> round-trips provider-native
    /// per-artifact fields like
    /// <c>{has_nsfw_concepts, content_type, width, height}</c> for fal,
    /// <c>{thoughtSignature, finishReason}</c> for Gemini's per-candidate
    /// metadata. The bag is preserved through ledger / artifact-store
    /// metadata for audit + replay.</para>
    /// </summary>
    public sealed record ResultArtifact
    {
        public ResultArtifact(
            string Role,
            ArtifactBody Body,
            string? DeclaredMimeType,
            IReadOnlyDictionary<string, JsonNode> ProviderMetadata)
        {
            if (string.IsNullOrWhiteSpace(Role))
                throw new ArgumentException("Role must be non-empty.", nameof(Role));
            if (Body is null) throw new ArgumentNullException(nameof(Body));
            if (ProviderMetadata is null)
                throw new ArgumentNullException(nameof(ProviderMetadata));

            // InlineArtifactBody requires a declared MIME — the bytes
            // are already materialized; if the provider didn't tell us
            // what they are, the manager has no way to recover (no
            // Content-Type header to sniff, no fetch step). This is a
            // type-level invariant rather than a manager-side check
            // so providers cannot ship mismatched envelopes.
            if (Body is InlineArtifactBody && string.IsNullOrWhiteSpace(DeclaredMimeType))
            {
                throw new ArgumentException(
                    "InlineArtifactBody requires a non-empty DeclaredMimeType. " +
                    "Inline-bytes without MIME is an unrecoverable provider " +
                    "contract violation — there is no fetch step at which the " +
                    "manager could sniff it. URL-bodied artifacts may pass null " +
                    "MIME and let the manager resolve at fetch time.",
                    nameof(DeclaredMimeType));
            }

            this.Role = Role;
            this.Body = Body;
            this.DeclaredMimeType = DeclaredMimeType;
            this.ProviderMetadata = ProviderMetadata;
        }

        public string Role { get; init; }
        public ArtifactBody Body { get; init; }
        public string? DeclaredMimeType { get; init; }
        public IReadOnlyDictionary<string, JsonNode> ProviderMetadata { get; init; }
    }
}
