using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    /// <summary>
    /// Defensive-copy proofs: callers cannot invalidate seam invariants
    /// by mutating the collections they passed in. The seam takes a
    /// snapshot of <c>IReadOnlyList</c>/<c>IReadOnlyDictionary</c>
    /// inputs at construction so post-construction <c>Clear</c> /
    /// <c>Add</c> on the caller's collection has no effect on the
    /// constructed instance.
    ///
    /// <para>JsonNode VALUES are not deep-cloned (mutating a value
    /// inside the dictionary doesn't change cardinality, and JSON-tree
    /// deep cloning is expensive). The CONTAINER shape is what we lock
    /// down — that is what the "at least one artifact" / "metadata
    /// bag is the shape the provider returned" contracts depend on.</para>
    /// </summary>
    public class PostConstructionMutationTests
    {
        private static ResultArtifact MakeArtifact(string role = "image") =>
            new(
                Role: role,
                Body: new InlineArtifactBody(new byte[] { 0x01 }),
                DeclaredMimeType: "image/png",
                ProviderMetadata: new Dictionary<string, JsonNode>());

        [Fact]
        public void ProviderResultEnvelope_artifact_list_is_snapshot_at_construction()
        {
            var mutableList = new List<ResultArtifact> { MakeArtifact() };
            var envelope = new ProviderResultEnvelope(
                Artifacts: mutableList,
                EnvelopeMetadata: new Dictionary<string, JsonNode>());

            mutableList.Clear();   // Caller mutation must not affect envelope
            mutableList.Add(MakeArtifact("video"));
            mutableList.Add(MakeArtifact("thumbnail"));

            Assert.Single(envelope.Artifacts);
            Assert.Equal("image", envelope.Artifacts[0].Role);
        }

        [Fact]
        public void ProviderResultEnvelope_envelope_metadata_is_snapshot_at_construction()
        {
            var meta = new Dictionary<string, JsonNode> { ["seed"] = 42 };
            var envelope = new ProviderResultEnvelope(
                Artifacts: new[] { MakeArtifact() },
                EnvelopeMetadata: meta);

            meta.Clear();
            meta["evil"] = "injected";

            Assert.Single(envelope.EnvelopeMetadata);
            Assert.True(envelope.EnvelopeMetadata.ContainsKey("seed"));
            Assert.False(envelope.EnvelopeMetadata.ContainsKey("evil"));
        }

        [Fact]
        public void ResultArtifact_provider_metadata_is_snapshot_at_construction()
        {
            var meta = new Dictionary<string, JsonNode> { ["width"] = 1024 };
            var artifact = new ResultArtifact(
                Role: "image",
                Body: new InlineArtifactBody(new byte[] { 0x01 }),
                DeclaredMimeType: "image/png",
                ProviderMetadata: meta);

            meta.Clear();
            meta["evil"] = "injected";

            Assert.Single(artifact.ProviderMetadata);
            Assert.True(artifact.ProviderMetadata.ContainsKey("width"));
            Assert.False(artifact.ProviderMetadata.ContainsKey("evil"));
        }

        [Fact]
        public void ProviderJobHandle_provider_metadata_is_snapshot_at_construction()
        {
            var meta = new Dictionary<string, JsonNode> { ["queue_position"] = 3 };
            var handle = new ProviderJobHandle(
                providerJobId: "j-1",
                providerMetadata: meta);

            meta.Clear();

            Assert.NotNull(handle.ProviderMetadata);
            Assert.Single(handle.ProviderMetadata!);
            Assert.True(handle.ProviderMetadata!.ContainsKey("queue_position"));
        }

        [Fact]
        public void ProviderResultEnvelope_rejects_null_artifact_in_list()
        {
            var listWithNull = new List<ResultArtifact?> { null }!;
            Assert.Throws<ArgumentException>(() => new ProviderResultEnvelope(
                Artifacts: (IReadOnlyList<ResultArtifact>)listWithNull,
                EnvelopeMetadata: new Dictionary<string, JsonNode>()));
        }
    }

    public class GenerationProgressNaNInfinityTests
    {
        [Fact]
        public void Rejects_NaN_percent_complete()
        {
            Assert.Throws<ArgumentException>(
                () => new GenerationProgress(PercentComplete: double.NaN));
        }

        [Fact]
        public void Rejects_positive_infinity_percent_complete()
        {
            Assert.Throws<ArgumentException>(
                () => new GenerationProgress(PercentComplete: double.PositiveInfinity));
        }

        [Fact]
        public void Rejects_negative_infinity_percent_complete()
        {
            Assert.Throws<ArgumentException>(
                () => new GenerationProgress(PercentComplete: double.NegativeInfinity));
        }
    }
}
