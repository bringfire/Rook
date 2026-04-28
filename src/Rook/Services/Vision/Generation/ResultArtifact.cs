using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// A single artifact within a <see cref="ProviderResultEnvelope"/>.
    /// Sealed class with read-only properties: invariants (non-empty
    /// Role, non-null Body, inline-bytes-require-MIME) cannot be
    /// bypassed via <c>with</c> or object initializers.
    ///
    /// <para><see cref="DeclaredMimeType"/> is the provider-asserted
    /// MIME and is <b>nullable</b>. Replicate's flat
    /// <c>output: [&lt;url&gt;]</c> list does not declare MIME at
    /// submit. The materializing manager resolves null MIME for
    /// URL-bodied artifacts at fetch time. Inline-bytes artifacts
    /// MUST arrive with declared MIME — null MIME on
    /// <see cref="InlineArtifactBody"/> is a contract violation
    /// rejected at construction.</para>
    /// </summary>
    public sealed class ResultArtifact
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

            if (Body is InlineArtifactBody && string.IsNullOrWhiteSpace(DeclaredMimeType))
            {
                throw new ArgumentException(
                    "InlineArtifactBody requires a non-empty DeclaredMimeType. " +
                    "Inline-bytes without MIME is an unrecoverable provider " +
                    "contract violation — there is no fetch step at which the " +
                    "manager could sniff it.",
                    nameof(DeclaredMimeType));
            }

            this.Role = Role;
            this.Body = Body;
            this.DeclaredMimeType = DeclaredMimeType;
            this.ProviderMetadata = ProviderMetadata;
        }

        public string Role { get; }
        public ArtifactBody Body { get; }
        public string? DeclaredMimeType { get; }
        public IReadOnlyDictionary<string, JsonNode> ProviderMetadata { get; }
    }
}
