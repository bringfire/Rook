using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Artifacts;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionViewSetAssemblerTests : IDisposable
{
    private readonly List<string> _roots = new();

    public void Dispose()
    {
        foreach (var root in _roots)
        {
            if (Directory.Exists(root))
                Directory.Delete(root, recursive: true);
        }
    }

    // ─── Helpers ──────────────────────────────────────────────────────────────

    private ArtifactStore NewStore(out string root)
    {
        root = Path.Combine(Path.GetTempPath(), $"rook-viewset-asm-{Guid.NewGuid():N}");
        _roots.Add(root);
        return new ArtifactStore(root);
    }

    private static Artifact SeedImageArtifact(ArtifactStore store, string kind, string role = "image")
        => store.Create(
            kind,
            new[] { new BlobInput(role, new byte[] { 0xFF, 0xD8, 0xFF }, "png") });

    private static int CountArtifacts(ArtifactStore store) => store.List().Count;

    // ─── Happy path ───────────────────────────────────────────────────────────

    [Fact]
    public void Assemble_FourValidViews_Succeeds()
    {
        var store = NewStore(out _);
        var front = SeedImageArtifact(store, "generated_image");
        var left  = SeedImageArtifact(store, "generated_image");
        var right = SeedImageArtifact(store, "generated_image");
        var back  = SeedImageArtifact(store, "generated_image");

        var req = new ReconstructionViewSetRequest(null, new[]
        {
            new ViewBinding("front", front.Id, null, null),
            new ViewBinding("left",  left.Id,  null, null),
            new ViewBinding("right", right.Id, null, null),
            new ViewBinding("back",  back.Id,  null, null),
        }, null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.True(outcome.Success);
        Assert.Null(outcome.Failure);
        Assert.NotNull(outcome.Artifact);
        Assert.Equal(ReconstructionArtifactKinds.ViewSet, outcome.Artifact!.Kind);
        // four view_<slot> blobs
        Assert.Equal(4, outcome.Artifact.Files.Count);
        Assert.Contains(outcome.Artifact.Files, f => f.Role == "view_front");
        Assert.Contains(outcome.Artifact.Files, f => f.Role == "view_left");
        Assert.Contains(outcome.Artifact.Files, f => f.Role == "view_right");
        Assert.Contains(outcome.Artifact.Files, f => f.Role == "view_back");
        // parent ids are distinct source ids
        Assert.Equal(4, outcome.Artifact.ParentIds.Count);
        Assert.Contains(front.Id, outcome.Artifact.ParentIds);
        // slotsExpected defaults to canonical four
        Assert.Equal(new[] { "front", "left", "right", "back" }, outcome.SlotsExpected.ToArray());
        Assert.Equal(new[] { "front", "left", "right", "back" }, outcome.SlotsPresent.ToArray());
        Assert.True(outcome.Complete);
        Assert.Equal(4, outcome.Views.Count);
    }

    [Fact]
    public void Assemble_PartialViews_IncompleteAndNoBytesLost()
    {
        var store = NewStore(out _);
        var front = SeedImageArtifact(store, "generated_image");
        var left  = SeedImageArtifact(store, "generated_image");

        var req = new ReconstructionViewSetRequest(null, new[]
        {
            new ViewBinding("front", front.Id, null, null),
            new ViewBinding("left",  left.Id,  null, null),
        }, null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.True(outcome.Success);
        Assert.False(outcome.Complete);
        Assert.Equal(new[] { "front", "left" }, outcome.SlotsPresent.ToArray());
        Assert.Equal(new[] { "front", "left", "right", "back" }, outcome.SlotsExpected.ToArray());
        Assert.Equal(2, outcome.Artifact!.Files.Count);
    }

    [Fact]
    public void Assemble_ExplicitSlotsExpectedSubset_CompletionLogicWorks()
    {
        var store = NewStore(out _);
        var front = SeedImageArtifact(store, "generated_image");

        // Expect only "front" — having "front" view means complete
        var req = new ReconstructionViewSetRequest(
            new[] { "front" },
            new[] { new ViewBinding("front", front.Id, null, null) },
            null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.True(outcome.Success);
        Assert.True(outcome.Complete);
        Assert.Equal(new[] { "front" }, outcome.SlotsExpected.ToArray());
    }

    [Fact]
    public void Assemble_ExplicitSlotsExpectedSuperset_Incomplete()
    {
        var store = NewStore(out _);
        var front = SeedImageArtifact(store, "generated_image");

        // Expect front+back but only provide front => incomplete
        var req = new ReconstructionViewSetRequest(
            new[] { "front", "back" },
            new[] { new ViewBinding("front", front.Id, null, null) },
            null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.True(outcome.Success);
        Assert.False(outcome.Complete);
        Assert.Equal(new[] { "front", "back" }, outcome.SlotsExpected.ToArray());
    }

    // ─── Provenance round-trip ────────────────────────────────────────────────

    [Fact]
    public void Assemble_WithProvenance_RoundTripsIntoMetadataAndOutcomeViews()
    {
        var store = NewStore(out _);
        var src = SeedImageArtifact(store, "generated_image");
        var prov = JsonNode.Parse("""{"cam":"A","frame":42}""")!.AsObject();

        var req = new ReconstructionViewSetRequest(null, new[]
        {
            new ViewBinding("front", src.Id, null, (JsonObject)prov.DeepClone()),
        }, null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.True(outcome.Success);
        // Provenance in outcome.Views
        var viewRow = outcome.Views[0];
        Assert.True(viewRow.ContainsKey("provenance"));
        var provInView = viewRow["provenance"] as JsonObject;
        Assert.NotNull(provInView);
        Assert.Equal("A", provInView!["cam"]!.GetValue<string>());
        Assert.Equal(42, provInView["frame"]!.GetValue<int>());
        // Provenance in metadata views array
        var meta = outcome.Artifact!.Metadata;
        Assert.True(meta.ContainsKey("views"));
        var metaViews = meta["views"] as JsonArray;
        Assert.NotNull(metaViews);
        var firstMetaView = metaViews![0] as JsonObject;
        Assert.NotNull(firstMetaView);
        Assert.True(firstMetaView!.ContainsKey("provenance"));
    }

    [Fact]
    public void Assemble_NoProvenance_ProvenanceKeyAbsentFromViewRow()
    {
        var store = NewStore(out _);
        var src = SeedImageArtifact(store, "generated_image");

        var req = new ReconstructionViewSetRequest(null, new[]
        {
            new ViewBinding("front", src.Id, null, null),
        }, null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.True(outcome.Success);
        var viewRow = outcome.Views[0];
        Assert.False(viewRow.ContainsKey("provenance"));
    }

    // ─── method / note defaults ───────────────────────────────────────────────

    [Fact]
    public void Assemble_NoMethod_DefaultsToManualAssembly()
    {
        var store = NewStore(out _);
        var src = SeedImageArtifact(store, "generated_image");
        var req = new ReconstructionViewSetRequest(null,
            new[] { new ViewBinding("front", src.Id, null, null) }, null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.True(outcome.Success);
        Assert.Equal("manual_assembly", outcome.Artifact!.Metadata["method"]!.GetValue<string>());
    }

    [Fact]
    public void Assemble_WithMethod_UsesIt()
    {
        var store = NewStore(out _);
        var src = SeedImageArtifact(store, "generated_image");
        var req = new ReconstructionViewSetRequest(null,
            new[] { new ViewBinding("front", src.Id, null, null) }, "my_method", null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.True(outcome.Success);
        Assert.Equal("my_method", outcome.Artifact!.Metadata["method"]!.GetValue<string>());
    }

    [Fact]
    public void Assemble_NoNote_NoteKeyAbsentFromMetadata()
    {
        var store = NewStore(out _);
        var src = SeedImageArtifact(store, "generated_image");
        var req = new ReconstructionViewSetRequest(null,
            new[] { new ViewBinding("front", src.Id, null, null) }, null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.True(outcome.Success);
        Assert.False(outcome.Artifact!.Metadata.ContainsKey("note"));
    }

    [Fact]
    public void Assemble_WithNote_NoteInMetadata()
    {
        var store = NewStore(out _);
        var src = SeedImageArtifact(store, "generated_image");
        var req = new ReconstructionViewSetRequest(null,
            new[] { new ViewBinding("front", src.Id, null, null) }, null, "test note");

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.True(outcome.Success);
        Assert.Equal("test note", outcome.Artifact!.Metadata["note"]!.GetValue<string>());
    }

    // ─── Six-slot set ─────────────────────────────────────────────────────────

    [Fact]
    public void Assemble_SixSlots_IncludesTopAndThreeQuarter()
    {
        var store = NewStore(out _);
        var srcs = Enumerable.Range(0, 6)
            .Select(_ => SeedImageArtifact(store, "generated_image"))
            .ToArray();

        var slots = new[] { "front", "left", "right", "back", "top", "three_quarter" };
        var views = slots.Select((s, i) => new ViewBinding(s, srcs[i].Id, null, null)).ToArray();
        var req = new ReconstructionViewSetRequest(null, views, null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.True(outcome.Success);
        Assert.Equal(6, outcome.Artifact!.Files.Count);
        Assert.Contains(outcome.Artifact.Files, f => f.Role == "view_top");
        Assert.Contains(outcome.Artifact.Files, f => f.Role == "view_three_quarter");
    }

    // ─── Source lineage: sources unchanged ───────────────────────────────────

    [Fact]
    public void Assemble_SourceArtifactsUnchanged()
    {
        var store = NewStore(out _);
        var src = SeedImageArtifact(store, "generated_image");

        var req = new ReconstructionViewSetRequest(null,
            new[] { new ViewBinding("front", src.Id, null, null) }, null, null);

        new ReconstructionViewSetAssembler(store).Assemble(req);

        // Source still exists, still has only the original role
        var srcAfter = store.Get(src.Id)!;
        Assert.NotNull(srcAfter);
        Assert.Equal("generated_image", srcAfter.Kind);
        Assert.Single(srcAfter.Files);
        Assert.Equal("image", srcAfter.Files[0].Role);
    }

    // ─── Semantic rejects (valid DTOs) — all must write nothing ──────────────

    [Fact]
    public void Assemble_DuplicateSlot_RejectsAndWritesNothing()
    {
        var store = NewStore(out _);
        var src = SeedImageArtifact(store, "generated_image");
        var before = CountArtifacts(store);

        var req = new ReconstructionViewSetRequest(null, new[]
        {
            new ViewBinding("front", src.Id, null, null),
            new ViewBinding("front", src.Id, null, null),
        }, null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.False(outcome.Success);
        Assert.Equal("invalid_view_set", outcome.Failure!.Code);
        Assert.Equal("duplicate_slot", outcome.Failure.Details["reason"]);
        Assert.Equal(before, CountArtifacts(store));
    }

    [Fact]
    public void Assemble_UnknownSlot_RejectsAndWritesNothing()
    {
        var store = NewStore(out _);
        var src = SeedImageArtifact(store, "generated_image");
        var before = CountArtifacts(store);

        var req = new ReconstructionViewSetRequest(null, new[]
        {
            new ViewBinding("diagonal", src.Id, null, null),
        }, null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.False(outcome.Success);
        Assert.Equal("invalid_view_set", outcome.Failure!.Code);
        Assert.Equal(before, CountArtifacts(store));
    }

    [Fact]
    public void Assemble_UnknownSlotInSlotsExpected_RejectsAndWritesNothing()
    {
        var store = NewStore(out _);
        var src = SeedImageArtifact(store, "generated_image");
        var before = CountArtifacts(store);

        var req = new ReconstructionViewSetRequest(
            new[] { "front", "diagonal" },
            new[] { new ViewBinding("front", src.Id, null, null) },
            null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.False(outcome.Success);
        Assert.Equal("invalid_view_set", outcome.Failure!.Code);
        Assert.Equal(before, CountArtifacts(store));
    }

    [Fact]
    public void Assemble_DuplicateSlotInSlotsExpected_RejectsAndWritesNothing()
    {
        var store = NewStore(out _);
        var src = SeedImageArtifact(store, "generated_image");
        var before = CountArtifacts(store);

        var req = new ReconstructionViewSetRequest(
            new[] { "front", "front" },
            new[] { new ViewBinding("front", src.Id, null, null) },
            null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.False(outcome.Success);
        Assert.Equal("invalid_view_set", outcome.Failure!.Code);
        Assert.Equal(before, CountArtifacts(store));
    }

    [Fact]
    public void Assemble_MalformedRole_RejectsAndWritesNothing()
    {
        var store = NewStore(out _);
        var src = SeedImageArtifact(store, "generated_image");
        var before = CountArtifacts(store);

        var req = new ReconstructionViewSetRequest(null, new[]
        {
            new ViewBinding("front", src.Id, "BAD ROLE", null),
        }, null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.False(outcome.Success);
        Assert.Equal("invalid_source_role", outcome.Failure!.Code);
        Assert.Equal("invalid_role_format", outcome.Failure.Details["reason"]);
        Assert.Equal(before, CountArtifacts(store));
    }

    [Fact]
    public void Assemble_SourceNotFound_RejectsAndWritesNothing()
    {
        var store = NewStore(out _);
        var before = CountArtifacts(store);
        var fakeId = Guid.NewGuid();

        var req = new ReconstructionViewSetRequest(null, new[]
        {
            new ViewBinding("front", fakeId, null, null),
        }, null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.False(outcome.Success);
        Assert.Equal("invalid_source_artifact", outcome.Failure!.Code);
        Assert.Equal("source_not_found", outcome.Failure.Details["reason"]);
        Assert.Equal(before, CountArtifacts(store));
    }

    [Fact]
    public void Assemble_SourceKindNotImage_RejectsAndWritesNothing()
    {
        var store = NewStore(out _);
        // Seed a reconstruction_package — not an image-capable kind
        var pkg = store.Create("reconstruction_package",
            new[] { new BlobInput("image", new byte[] { 1 }, "png") });
        var before = CountArtifacts(store);

        var req = new ReconstructionViewSetRequest(null, new[]
        {
            new ViewBinding("front", pkg.Id, null, null),
        }, null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.False(outcome.Success);
        Assert.Equal("invalid_source_artifact", outcome.Failure!.Code);
        Assert.Equal("source_kind_not_image", outcome.Failure.Details["reason"]);
        Assert.Equal(before, CountArtifacts(store));
    }

    [Fact]
    public void Assemble_RoleNotPresentOnArtifact_RejectsAndWritesNothing()
    {
        var store = NewStore(out _);
        // Artifact has "image" role; request "thumbnail" which doesn't exist
        var src = SeedImageArtifact(store, "generated_image", "image");
        var before = CountArtifacts(store);

        var req = new ReconstructionViewSetRequest(null, new[]
        {
            new ViewBinding("front", src.Id, "thumbnail", null),
        }, null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.False(outcome.Success);
        Assert.Equal("invalid_source_role", outcome.Failure!.Code);
        Assert.Equal("role_not_present", outcome.Failure.Details["reason"]);
        Assert.Equal(before, CountArtifacts(store));
    }

    [Fact]
    public void Assemble_SourceBlobDeleted_RejectsAndWritesNothing()
    {
        var store = NewStore(out _);
        var src = SeedImageArtifact(store, "generated_image");
        // Delete the blob file to simulate an unreadable source
        var blobPath = store.GetBlobAbsolutePath(src.Id, "image");
        File.Delete(blobPath);
        var before = CountArtifacts(store);

        var req = new ReconstructionViewSetRequest(null, new[]
        {
            new ViewBinding("front", src.Id, null, null),
        }, null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.False(outcome.Success);
        Assert.Equal("invalid_source_artifact", outcome.Failure!.Code);
        Assert.Equal("source_blob_unreadable", outcome.Failure.Details["reason"]);
        Assert.Equal(before, CountArtifacts(store));
    }

    // ─── Source kinds: preprocessed_image is allowed ─────────────────────────

    [Fact]
    public void Assemble_PreprocessedImageSource_Succeeds()
    {
        var store = NewStore(out _);
        var src = SeedImageArtifact(store, "preprocessed_image");

        var req = new ReconstructionViewSetRequest(null, new[]
        {
            new ViewBinding("front", src.Id, null, null),
        }, null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.True(outcome.Success);
    }

    // ─── Parent IDs are distinct ──────────────────────────────────────────────

    [Fact]
    public void Assemble_SameSourceUsedTwice_DistinctParentId()
    {
        var store = NewStore(out _);
        var src = SeedImageArtifact(store, "generated_image");

        // Use same source for two different slots (allowed — dup slot check is by slot name)
        var req = new ReconstructionViewSetRequest(null, new[]
        {
            new ViewBinding("front", src.Id, null, null),
            new ViewBinding("left",  src.Id, null, null),
        }, null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.True(outcome.Success);
        // parent_ids = DISTINCT source artifact ids → only one entry
        Assert.Single(outcome.Artifact!.ParentIds);
        Assert.Equal(src.Id, outcome.Artifact.ParentIds[0]);
    }

    // ─── Views response/metadata cannot drift ────────────────────────────────

    [Fact]
    public void Assemble_ViewsInOutcomeMatchMetadata()
    {
        var store = NewStore(out _);
        var src = SeedImageArtifact(store, "generated_image");

        var req = new ReconstructionViewSetRequest(null, new[]
        {
            new ViewBinding("front", src.Id, null, null),
        }, null, null);

        var outcome = new ReconstructionViewSetAssembler(store).Assemble(req);

        Assert.True(outcome.Success);
        var viewRow = outcome.Views[0];
        Assert.Equal("front", viewRow["slot"]);
        Assert.Equal(src.Id.ToString("D"), viewRow["source_artifact_id"]);
        Assert.Equal("image", viewRow["source_role"]);   // null => "image"
        Assert.Equal("view_front", viewRow["view_role"]);
    }
}
