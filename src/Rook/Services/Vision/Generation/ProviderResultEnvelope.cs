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
    /// <para>The envelope holds an array because real provider
    /// responses do: fal sync image returns
    /// <c>images: [{url, ...}]</c>, Gemini returns <c>candidates: [...]</c>,
    /// Hunyuan returns multi-format variants. Single-artifact
    /// providers (Veo, fal queue video) wrap their one artifact in a
    /// one-element list so consumer code does not branch on
    /// cardinality.</para>
    ///
    /// <para><see cref="EnvelopeMetadata"/> round-trips envelope-level
    /// provider fields: <c>{seed, prompt, timings, has_nsfw_concepts}</c>
    /// for fal, <c>{modelVersion, responseId, usageMetadata}</c> for
    /// Gemini, <c>{metrics: {predict_time, total_time}}</c> for
    /// Replicate. Per-artifact fields go on
    /// <see cref="ResultArtifact.ProviderMetadata"/>.</para>
    /// </summary>
    public sealed record ProviderResultEnvelope(
        IReadOnlyList<ResultArtifact> Artifacts,
        IReadOnlyDictionary<string, JsonNode> EnvelopeMetadata)
    {
        public IReadOnlyList<ResultArtifact> Artifacts { get; init; } =
            Artifacts is null ? throw new ArgumentNullException(nameof(Artifacts))
            : Artifacts.Count == 0 ? throw new ArgumentException(
                "Artifacts must contain at least one ResultArtifact.", nameof(Artifacts))
            : Artifacts;

        public IReadOnlyDictionary<string, JsonNode> EnvelopeMetadata { get; init; } =
            EnvelopeMetadata ?? throw new ArgumentNullException(nameof(EnvelopeMetadata));
    }
}
