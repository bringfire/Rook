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

            // Defensive copy of the containers. Without this a caller's
            // List<>/Dictionary<> remains externally mutable behind the
            // IReadOnlyX interface — a Clear() would invalidate the
            // "at least one artifact" invariant after construction.
            // JsonNode values are NOT deep-copied (mutating a node value
            // doesn't change cardinality and deep-cloning JSON trees is
            // expensive); the container shape is what we lock down.
            var artifactsCopy = new ResultArtifact[Artifacts.Count];
            for (int i = 0; i < Artifacts.Count; i++)
            {
                if (Artifacts[i] is null)
                    throw new ArgumentException(
                        $"Artifacts[{i}] is null.", nameof(Artifacts));
                artifactsCopy[i] = Artifacts[i];
            }
            this.Artifacts = artifactsCopy;
            this.EnvelopeMetadata = CopyDictionary(EnvelopeMetadata);
        }

        // Dictionary<TKey,TValue> on net48 has no IReadOnlyDictionary
        // constructor overload — only IDictionary and
        // IEnumerable<KeyValuePair>. Explicit enumeration works on
        // every target without ambiguity.
        private static Dictionary<string, JsonNode> CopyDictionary(
            IReadOnlyDictionary<string, JsonNode> source)
        {
            var copy = new Dictionary<string, JsonNode>(source.Count);
            foreach (var kvp in source) copy[kvp.Key] = kvp.Value;
            return copy;
        }

        public IReadOnlyList<ResultArtifact> Artifacts { get; }
        public IReadOnlyDictionary<string, JsonNode> EnvelopeMetadata { get; }
    }
}
