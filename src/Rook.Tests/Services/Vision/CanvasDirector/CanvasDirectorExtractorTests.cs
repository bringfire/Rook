using System;
using System.Collections.Generic;
using System.Text.Json;
using Rook.Services.Vision.CanvasDirector;
using Xunit;

namespace Rook.Tests.Services.Vision.CanvasDirector
{
    public class CanvasDirectorExtractorTests
    {
        [Fact]
        public void ValidateSolveMode_RejectsMissingFreshnessTokenForReuse()
        {
            var ex = Assert.Throws<CanvasDirectorException>(
                () => CanvasDirectorExtractor.ValidateSolveMode(
                    "reuse_verified_solution",
                    null,
                    supportsReuseVerification: true));

            Assert.Equal("freshness_token_required", ex.Code);
        }

        [Fact]
        public void ValidateSolveMode_RejectsUnsupportedReuseVerification()
        {
            var ex = Assert.Throws<CanvasDirectorException>(
                () => CanvasDirectorExtractor.ValidateSolveMode(
                    "reuse_verified_solution",
                    "serial-1",
                    supportsReuseVerification: false));

            Assert.Equal("unsupported_solve_mode", ex.Code);
        }

        [Fact]
        public void RequireFreshSolve_InvokesNewSolutionAndAdvancesToken()
        {
            var document = new AdvancingGhDocument();

            CanvasDirectorExtractor.RequireFreshSolve(document);

            Assert.Equal(1, document.NewSolutionCalls);
            Assert.True(document.ExpireAllObjects);
            Assert.Equal(TimeSpan.FromMilliseconds(1), document.SolutionSpan);
            Assert.Contains(TimeSpan.FromMilliseconds(1), document.SolutionHistory);
        }

        [Fact]
        public void RequireFreshSolve_FailsWhenSolutionTokenDoesNotAdvance()
        {
            var ex = Assert.Throws<CanvasDirectorException>(
                () => CanvasDirectorExtractor.RequireFreshSolve(new StaleGhDocument()));

            Assert.Equal("solution_stale", ex.Code);
        }

        [Fact]
        public void ValidateDocumentIdentity_RejectsWrongDocumentId()
        {
            var request = new CanvasDirectorExtractRequest
            {
                DocumentId = "expected-document",
            };

            var ex = Assert.Throws<CanvasDirectorException>(
                () => CanvasDirectorExtractor.ValidateDocumentIdentity(
                    new IdentityGhDocument { DocumentID = "actual-document" },
                    request));

            Assert.Equal("document_mismatch", ex.Code);
        }

        [Fact]
        public void ParseExportPayload_RequiresDeclaredMarker()
        {
            var ex = Assert.Throws<CanvasDirectorException>(
                () => CanvasDirectorExtractor.ParseExportPayload("{\"schema_version\":1}"));

            Assert.Equal("export_schema_mismatch", ex.Code);
        }

        [Fact]
        public void ParseExportPayload_ReturnsEnvelopeForDeclaredPayload()
        {
            var envelope = CanvasDirectorExtractor.ParseExportPayload(
                "{\"metadata_kind\":\"rook.canvas_director.export\",\"schema_version\":1,\"export_id\":\"export-1\",\"proposal_id\":\"proposal-1\",\"template_id\":\"template-1\",\"template_version\":\"0.1.0\",\"payload\":{\"timeline\":{\"fps\":24,\"frame_count\":3}}}");

            Assert.True(envelope.ReadOnly);
            Assert.NotEmpty(envelope.CanvasExportStateSha256);
            Assert.Equal("export-1", envelope.CanvasExportState.GetProperty("export_id").GetString());
            Assert.Equal(
                "rook.canvas_director.export",
                envelope.CanvasExportState.GetProperty("metadata_kind").GetString());
        }

        [Fact]
        public void ParseExportPayload_RejectsWrongProposalId()
        {
            var request = new CanvasDirectorExtractRequest
            {
                ProposalId = "proposal-expected",
            };

            var ex = Assert.Throws<CanvasDirectorException>(
                () => CanvasDirectorExtractor.ParseExportPayload(
                    "{\"metadata_kind\":\"rook.canvas_director.export\",\"schema_version\":1,\"export_id\":\"export-1\",\"proposal_id\":\"proposal-actual\",\"template_id\":\"template-1\",\"template_version\":\"0.1.0\",\"payload\":{\"timeline\":[]}}",
                    request));

            Assert.Equal("document_mismatch", ex.Code);
        }

        private sealed class AdvancingGhDocument
        {
            public List<TimeSpan> SolutionHistory { get; } = new();
            public TimeSpan SolutionSpan { get; private set; }
            public int NewSolutionCalls { get; private set; }
            public bool ExpireAllObjects { get; private set; }

            public void NewSolution(bool expireAllObjects)
            {
                NewSolutionCalls++;
                ExpireAllObjects = expireAllObjects;
                SolutionSpan = TimeSpan.FromMilliseconds(NewSolutionCalls);
                SolutionHistory.Add(SolutionSpan);
            }
        }

        private sealed class StaleGhDocument
        {
            public List<TimeSpan> SolutionHistory { get; } = new() { TimeSpan.FromMilliseconds(10) };
            public TimeSpan SolutionSpan { get; } = TimeSpan.FromMilliseconds(10);

            public void NewSolution(bool expireAllObjects)
            {
            }
        }

        private sealed class IdentityGhDocument
        {
            public string? DocumentID { get; init; }
        }
    }
}
