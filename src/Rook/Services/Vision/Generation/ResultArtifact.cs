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
    public sealed record ResultArtifact(
        string Role,                                                    // "image" | "video" | "thumbnail" | "depth" | etc.
        ArtifactBody Body,
        string? DeclaredMimeType,
        IReadOnlyDictionary<string, JsonNode> ProviderMetadata)
    {
        public string Role { get; init; } =
            string.IsNullOrWhiteSpace(Role)
                ? throw new ArgumentException("Role must be non-empty.", nameof(Role))
                : Role;

        public ArtifactBody Body { get; init; } = Body ?? throw new ArgumentNullException(nameof(Body));

        public IReadOnlyDictionary<string, JsonNode> ProviderMetadata { get; init; } =
            ProviderMetadata ?? throw new ArgumentNullException(nameof(ProviderMetadata));
    }
}
