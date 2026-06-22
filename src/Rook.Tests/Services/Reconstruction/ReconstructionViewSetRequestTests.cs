using System;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionViewSetRequestTests
{
    // ─── Valid parses ────────────────────────────────────────────────────────

    [Fact]
    public void TryParse_FullBody_ParsesAllFields()
    {
        const string body = """
        {
            "views": [
                {
                    "slot": "front",
                    "artifact_id": "00000000-0000-0000-0000-000000000001",
                    "role": "image",
                    "provenance": {"source": "manual"}
                },
                {
                    "slot": "left",
                    "artifact_id": "00000000-0000-0000-0000-000000000002"
                }
            ],
            "slots_expected": ["front", "left"],
            "method": "my_method",
            "note": "some note"
        }
        """;

        var req = ReconstructionViewSetRequest.TryParse(body, out var failure);

        Assert.NotNull(req);
        Assert.Null(failure);
        Assert.Equal(2, req!.Views.Count);
        Assert.Equal("front", req.Views[0].Slot);
        Assert.Equal(new Guid("00000000-0000-0000-0000-000000000001"), req.Views[0].ArtifactId);
        Assert.Equal("image", req.Views[0].Role);
        Assert.NotNull(req.Views[0].Provenance);
        Assert.Equal("left", req.Views[1].Slot);
        Assert.Null(req.Views[1].Role);
        Assert.Null(req.Views[1].Provenance);
        Assert.NotNull(req.SlotsExpected);
        Assert.Equal(new[] { "front", "left" }, req.SlotsExpected);
        Assert.Equal("my_method", req.Method);
        Assert.Equal("some note", req.Note);
    }

    [Fact]
    public void TryParse_SlotsExpectedOmitted_IsNull()
    {
        const string body = """
        {
            "views": [{"slot": "front", "artifact_id": "00000000-0000-0000-0000-000000000001"}]
        }
        """;

        var req = ReconstructionViewSetRequest.TryParse(body, out var failure);

        Assert.NotNull(req);
        Assert.Null(failure);
        Assert.Null(req!.SlotsExpected);  // omitted => null, not empty
    }

    [Fact]
    public void TryParse_MethodAndNoteOmitted_AreNull()
    {
        const string body = """
        {"views":[{"slot":"front","artifact_id":"00000000-0000-0000-0000-000000000001"}]}
        """;

        var req = ReconstructionViewSetRequest.TryParse(body, out _);

        Assert.NotNull(req);
        Assert.Null(req!.Method);
        Assert.Null(req.Note);
    }

    [Fact]
    public void TryParse_ProvenanceJsonObject_RoundTrips()
    {
        const string body = """
        {
            "views": [{
                "slot": "front",
                "artifact_id": "00000000-0000-0000-0000-000000000001",
                "provenance": {"cam": "A", "frame": 42}
            }]
        }
        """;

        var req = ReconstructionViewSetRequest.TryParse(body, out _);

        Assert.NotNull(req);
        var prov = req!.Views[0].Provenance;
        Assert.NotNull(prov);
        Assert.Equal("A", prov!["cam"]!.GetValue<string>());
        Assert.Equal(42, prov["frame"]!.GetValue<int>());
    }

    // ─── Explicit empty slots_expected ──────────────────────────────────────

    [Fact]
    public void TryParse_ExplicitEmptySlotsExpected_Fails()
    {
        var req = ReconstructionViewSetRequest.TryParse(
            """{"views":[{"slot":"front","artifact_id":"00000000-0000-0000-0000-000000000001"}],"slots_expected":[]}""",
            out var failure);

        Assert.Null(req);
        Assert.Equal("invalid_view_set", failure!.Code);
        Assert.Equal("empty_slots_expected", failure.Details["reason"]);
    }

    // ─── Non-string method / note ────────────────────────────────────────────

    [Fact]
    public void TryParse_NonStringMethod_Fails()
    {
        var req = ReconstructionViewSetRequest.TryParse(
            """{"views":[{"slot":"front","artifact_id":"00000000-0000-0000-0000-000000000001"}],"method":42}""",
            out var failure);

        Assert.Null(req);
        Assert.Equal("invalid_view_set", failure!.Code);
        Assert.Equal("non_string_method", failure.Details["reason"]);
    }

    [Fact]
    public void TryParse_NonStringNote_Fails()
    {
        var req = ReconstructionViewSetRequest.TryParse(
            """{"views":[{"slot":"front","artifact_id":"00000000-0000-0000-0000-000000000001"}],"note":true}""",
            out var failure);

        Assert.Null(req);
        Assert.Equal("invalid_view_set", failure!.Code);
        Assert.Equal("non_string_note", failure.Details["reason"]);
    }

    // ─── Provenance must be a JSON object ───────────────────────────────────

    [Fact]
    public void TryParse_ProvenanceScalar_Fails()
    {
        var req = ReconstructionViewSetRequest.TryParse(
            """{"views":[{"slot":"front","artifact_id":"00000000-0000-0000-0000-000000000001","provenance":"not-an-object"}]}""",
            out var failure);

        Assert.Null(req);
        Assert.Equal("invalid_provenance", failure!.Code);
        Assert.Equal("provenance_not_object", failure.Details["reason"]);
    }

    [Fact]
    public void TryParse_ProvenanceArray_Fails()
    {
        var req = ReconstructionViewSetRequest.TryParse(
            """{"views":[{"slot":"front","artifact_id":"00000000-0000-0000-0000-000000000001","provenance":[1,2,3]}]}""",
            out var failure);

        Assert.Null(req);
        Assert.Equal("invalid_provenance", failure!.Code);
        Assert.Equal("provenance_not_object", failure.Details["reason"]);
    }

    // ─── Empty / missing views ───────────────────────────────────────────────

    [Fact]
    public void TryParse_MissingViews_Fails()
    {
        var req = ReconstructionViewSetRequest.TryParse(
            """{"slots_expected":["front"]}""",
            out var failure);

        Assert.Null(req);
        Assert.Equal("invalid_view_set", failure!.Code);
        Assert.Equal("empty_views", failure.Details["reason"]);
    }

    [Fact]
    public void TryParse_EmptyViewsArray_Fails()
    {
        var req = ReconstructionViewSetRequest.TryParse(
            """{"views":[]}""",
            out var failure);

        Assert.Null(req);
        Assert.Equal("invalid_view_set", failure!.Code);
        Assert.Equal("empty_views", failure.Details["reason"]);
    }

    // ─── Malformed artifact_id ──────────────────────────────────────────────

    [Fact]
    public void TryParse_NonGuidArtifactId_Fails()
    {
        var req = ReconstructionViewSetRequest.TryParse(
            """{"views":[{"slot":"front","artifact_id":"not-a-guid"}]}""",
            out var failure);

        Assert.Null(req);
        Assert.Equal("invalid_view_set", failure!.Code);
    }

    [Fact]
    public void TryParse_MissingArtifactId_Fails()
    {
        var req = ReconstructionViewSetRequest.TryParse(
            """{"views":[{"slot":"front"}]}""",
            out var failure);

        Assert.Null(req);
        Assert.Equal("invalid_view_set", failure!.Code);
    }

    // ─── Missing slot ────────────────────────────────────────────────────────

    [Fact]
    public void TryParse_MissingSlot_Fails()
    {
        var req = ReconstructionViewSetRequest.TryParse(
            """{"views":[{"artifact_id":"00000000-0000-0000-0000-000000000001"}]}""",
            out var failure);

        Assert.Null(req);
        Assert.Equal("invalid_view_set", failure!.Code);
    }

    // ─── Null / non-JSON body ────────────────────────────────────────────────

    [Fact]
    public void TryParse_NullBody_Fails()
    {
        var req = ReconstructionViewSetRequest.TryParse(null, out var failure);

        Assert.Null(req);
        Assert.NotNull(failure);
    }

    [Fact]
    public void TryParse_InvalidJson_Fails()
    {
        var req = ReconstructionViewSetRequest.TryParse("not json", out var failure);

        Assert.Null(req);
        Assert.NotNull(failure);
    }
}
