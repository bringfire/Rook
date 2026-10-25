using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalExecutionSnapshotTests
    {
        [Theory]
        [InlineData("confirmed_cancelled", null)]
        [InlineData("cancellation_requested", null)]
        [InlineData("already_completed", GenerationLifecycleState.Completed)]
        [InlineData("failed", null)]
        [InlineData("unavailable", null)]
        public void Cancellation_evidence_roundtrips_and_survives_later_dispatch_updates(string disposition, GenerationLifecycleState? terminal)
        {
            var snapshot = Snapshot().WithCancellation(new FalCancellationSnapshot(true, disposition, true, terminal))
                .WithDispatchState("unknown", Snapshot().Handle);
            var read = FalExecutionSnapshotCodec.Deserialize(FalExecutionSnapshotCodec.Serialize(snapshot));
            Assert.Null(read.Diagnostic);
            var evidence = read.Snapshot!.Cancellation!;
            Assert.True(evidence.LocalStopped); Assert.True(evidence.Automatic);
            Assert.Equal(disposition, evidence.RemoteDisposition); Assert.Equal(terminal, evidence.RemoteTerminalState);
            Assert.Equal(disposition == "confirmed_cancelled", evidence.RemoteCancellationConfirmed);
        }

        [Theory]
        [InlineData("unknown_disposition")]
        [InlineData("missing_completed_state")]
        [InlineData("nonterminal_state")]
        [InlineData("extra_property")]
        public void Corrupt_cancellation_evidence_is_unavailable(string corruption)
        {
            var json = FalExecutionSnapshotCodec.Serialize(Snapshot().WithCancellation(new FalCancellationSnapshot(true, "already_completed", false, GenerationLifecycleState.Completed)));
            var evidence = json["cancellation"]!;
            switch (corruption)
            {
                case "unknown_disposition": evidence["remote_disposition"] = "cancelled_maybe"; break;
                case "missing_completed_state": evidence["remote_terminal_state"] = null; break;
                case "nonterminal_state": evidence["remote_terminal_state"] = "Running"; break;
                default: evidence["unexpected"] = true; break;
            }
            var read = FalExecutionSnapshotCodec.Deserialize(json);
            Assert.Null(read.Snapshot); Assert.NotNull(read.Diagnostic); Assert.False(read.CleanupAvailable);
        }

        [Fact]
        public void Older_snapshot_without_cancellation_metadata_remains_readable()
        {
            var json = FalExecutionSnapshotCodec.Serialize(Snapshot()); json.Remove("cancellation");
            var read = FalExecutionSnapshotCodec.Deserialize(json);
            Assert.NotNull(read.Snapshot); Assert.Null(read.Snapshot!.Cancellation); Assert.True(read.CleanupAvailable);
        }

        [Fact]
        public void Valid_large_controls_roundtrip_within_bounded_snapshot_envelope()
        {
            using var files = new CatalogFiles(); files.Operation["fields"]![0]!["max_length"] = 1048576; files.Save();
            var binding = files.Compile().Catalog!.GetOperation("synthetic/image", "text_to_image");
            var request = new FalModelNormalizer().Normalize(binding, new FalModelInput(new JsonObject { ["prompt"] = new string('x', 600000) })).Request!;
            using var media = FalMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia>(), new Rook.Services.Vision.Video.Framing.VideoPreparationResources());
            var json = FalExecutionSnapshotCodec.Serialize(FalExecutionSnapshot.Create(request, media));
            Assert.NotNull(FalExecutionSnapshotCodec.Deserialize(json).Snapshot);
        }
        [Fact]
        public void Roundtrip_preserves_original_hash_and_effective_controls_without_catalog()
        {
            using var files = new CatalogFiles();
            var other = files.Operation.DeepClone(); other["operation_id"] = "image_to_image";
            other["media"] = JsonNode.Parse("""[{"role":"primary_image","min_count":1,"max_count":1,"ordered":false,"preparation":"validated_original","transport":"data_uri","payload":{"pointer":"/input_image","conversion":"identity"}}]""");
            files.Definition["operations"]!.AsArray().Add(other); files.Save();
            var binding = files.Compile().Catalog!.GetOperation("synthetic/image", "text_to_image");
            var request = new FalModelNormalizer().Normalize(binding, new FalModelInput(new JsonObject { ["prompt"] = "draw", ["seed"] = 9007199254740991L })).Request!;
            using var media = FalMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia>());
            var snapshot = FalExecutionSnapshot.Create(request, media, new FalPricingSnapshot("output", "price-1", "source", 1m, 1m, .01m, .01m, .01m));
            var json = FalExecutionSnapshotCodec.Serialize(snapshot);
            files.Dispose();
            var read = FalExecutionSnapshotCodec.Deserialize(json);
            Assert.Null(read.Diagnostic);
            Assert.Equal(binding.DefinitionHash, read.Snapshot!.Binding.DefinitionHash);
            Assert.Equal(9007199254740991L, read.Snapshot.Request.EffectiveRequestFields["seed"]!.GetValue<long>());
            Assert.Equal("small", read.Snapshot.Request.EffectiveRequestFields["resolution"]!.GetValue<string>());
            Assert.Equal(.01m, read.Snapshot.Pricing!.EstimateMaxUsd);
            json["effective_request"]!["seed"] = 2;
            Assert.Equal(9007199254740991L, read.Snapshot.Request.EffectiveRequestFields["seed"]!.GetValue<long>());
        }

        [Theory]
        [InlineData("version")]
        [InlineData("hash")]
        [InlineData("binding")]
        [InlineData("controls")]
        [InlineData("handle")]
        [InlineData("adapter")]
        [InlineData("binding_shape")]
        public void Unsupported_or_corrupt_snapshot_has_explicit_diagnostic(string change)
        {
            var json = FalExecutionSnapshotCodec.Serialize(Snapshot());
            switch (change)
            {
                case "version": json["version"] = 99; break;
                case "hash": json["definition_hash"] = "invalid"; break;
                case "binding": json["binding"]!["operations"]![0]!["endpoint_id"] = "fal-ai/replacement"; break;
                case "controls": json["effective_request"]!["seed"] = 17; break;
                case "handle": json["handle"]!["cancel_url"] = "https://queue.fal.run/other/requests/id/cancel"; break;
                case "adapter": json["binding"]!["operations"]![0]!["adapter"]!["version"] = 99; json["binding_digest"] = FalCanonicalJson.Hash(json["binding"]!); break;
                case "binding_shape": json["binding"]!["operations"]![0]!["headers"] = new JsonObject(); json["binding_digest"] = FalCanonicalJson.Hash(json["binding"]!); break;
            }
            var read = FalExecutionSnapshotCodec.Deserialize(json);
            Assert.Null(read.Snapshot); Assert.NotNull(read.Diagnostic); Assert.False(read.CleanupAvailable);
        }

        [Fact]
        public void Snapshot_strips_provider_metadata_and_does_not_alias_json()
        {
            var snapshot = Snapshot();
            var json = FalExecutionSnapshotCodec.Serialize(snapshot);
            Assert.DoesNotContain("fal.media", json.ToJsonString());
            json["dispatch_state"] = "unknown";
            Assert.Equal("accepted", snapshot.DispatchState);
            Assert.Equal("PUT", snapshot.Handle!.CancelHttpMethod);
        }

        [Fact]
        public void Media_provenance_preserves_artifact_identity_semantic_role_digest_and_order()
        {
            using var files = new CatalogFiles(CatalogFiles.VideoJson);
            var binding = files.Compile().Catalog!.GetOperation("synthetic/video", "first_last_frame_to_video");
            var first = MediaRef.ForArtifact(Guid.NewGuid(), "image"); var last = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = new FalModelNormalizer().Normalize(binding, new FalModelInput(media: new[] { new FalMediaInput("start_frame", 0, first), new FalMediaInput("end_frame", 0, last) })).Request!;
            var bytes = new byte[] { 137, 80, 78, 71, 13, 10, 26, 10 };
            var resolved = new Dictionary<MediaRef, ResolvedMedia> { [first] = new ResolvedMedia(bytes, "image/png"), [last] = new ResolvedMedia(bytes, "image/png") };
            using var media = FalMediaSnapshot.Capture(request, resolved, new Rook.Services.Vision.Video.Framing.VideoPreparationResources());
            var snapshot = FalExecutionSnapshot.Create(request, media);
            var read = FalExecutionSnapshotCodec.Deserialize(FalExecutionSnapshotCodec.Serialize(snapshot));
            Assert.Null(read.Diagnostic); Assert.Equal(2, read.Snapshot!.Request.Media.Count);
            Assert.Contains(read.Snapshot.Request.Media, m => m.Role == "start_frame" && m.Input.Source.ArtifactId == first.ArtifactId);
            Assert.Contains(read.Snapshot.Request.Media, m => m.Role == "end_frame" && m.Input.Source.ArtifactId == last.ArtifactId);
            Assert.All(read.Snapshot.MediaProvenance, s => Assert.Equal(media.Slots[0].Sha256, s!["sha256"]!.GetValue<string>()));
            var exported = read.Snapshot.MediaProvenance; exported[0]!["sha256"] = "changed";
            Assert.NotEqual("changed", read.Snapshot.MediaProvenance[0]!["sha256"]!.GetValue<string>());
        }

        internal static FalExecutionSnapshot Snapshot()
        {
            using var files = new CatalogFiles();
            files.Operation["invocation"] = "queue"; files.Operation["lifecycle_root"] = "fal-ai/synthetic"; files.Save();
            var binding = files.Compile().Catalog!.GetOperation("synthetic/image", "text_to_image");
            var request = new FalModelNormalizer().Normalize(binding, new FalModelInput(new JsonObject { ["prompt"] = "draw" })).Request!;
            using var media = FalMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia>());
            return FalExecutionSnapshot.Create(request, media).WithDispatchState("accepted", new ProviderJobHandle("id",
                new Uri("https://queue.fal.run/fal-ai/synthetic/requests/id/status"), new Uri("https://queue.fal.run/fal-ai/synthetic/requests/id"),
                new Uri("https://queue.fal.run/fal-ai/synthetic/requests/id/cancel"), "PUT", providerMetadata: new Dictionary<string, JsonNode> { ["upload"] = JsonValue.Create("https://fal.media/private")! }));
        }
    }
}
