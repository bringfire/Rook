using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Success-only result envelope. The error path lives on the
    /// outer <see cref="FailedResultOutcome"/>, NOT a nullable error
    /// field on this record — keeping success and failure in
    /// type-distinct branches.
    ///
    /// <para>Sealed class with read-only properties — the
    /// "at least one artifact" invariant cannot be bypassed via
    /// <c>with</c> or object initializers.</para>
    ///
    /// <para>The envelope holds an array because real provider
    /// responses do (fal sync image, Gemini candidates, Hunyuan
    /// multi-format variants). Single-artifact providers (Veo, fal
    /// queue video) wrap their one artifact in a one-element list so
    /// consumer code does not branch on cardinality.</para>
    ///
    /// <para><see cref="EnvelopeMetadata"/> round-trips envelope-level
    /// provider fields (fal seed/prompt/timings, Gemini
    /// modelVersion/responseId/usageMetadata, Replicate metrics).</para>
    /// </summary>
    public sealed class ProviderResultEnvelope
    {
        public ProviderResultEnvelope(
            IReadOnlyList<ResultArtifact> Artifacts,
            IReadOnlyDictionary<string, JsonNode> EnvelopeMetadata)
        {
            if (Artifacts is null) throw new ArgumentNullException(nameof(Artifacts));
            if (Artifacts.Count == 0)
                throw new ArgumentException(
                    "Artifacts must contain at least one ResultArtifact.",
                    nameof(Artifacts));
            if (EnvelopeMetadata is null)
                throw new ArgumentNullException(nameof(EnvelopeMetadata));

            this.Artifacts = Artifacts;
            this.EnvelopeMetadata = EnvelopeMetadata;
        }

        public IReadOnlyList<ResultArtifact> Artifacts { get; }
        public IReadOnlyDictionary<string, JsonNode> EnvelopeMetadata { get; }
    }
}
