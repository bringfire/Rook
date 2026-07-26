using System;
using System.Collections.Generic;
using System.Linq;
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim.CreationGuidProbe
{
    public sealed class BimCreationGuidProbeSessionTests
    {
        [Fact]
        public void Capture_ReusesAliasesForEqualRawEvidenceAndSeparatesUnequalEvidence()
        {
            // Break caught: assigning aliases per capture instead of per raw equality value.
            var session = Begin();
            var initial = Capture(session, BimCreationGuidProbeCase.SavedProjectInitial,
                "11111111-1111-1111-1111-111111111111", @"c:\Models\Probe.rvt");
            var reopened = Capture(session, BimCreationGuidProbeCase.SavedProjectReopen,
                "11111111-1111-1111-1111-111111111111", @"C:\MODELS\PROBE.RVT");
            var replacement = Capture(session, BimCreationGuidProbeCase.ReplacementSamePath,
                "22222222-2222-2222-2222-222222222222", @"C:\Models\Probe.rvt");

            Assert.Equal("creation-001", initial.CreationGuidAlias);
            Assert.Equal("creation-001", reopened.CreationGuidAlias);
            Assert.Equal("path-001", initial.DocumentPathAlias);
            Assert.Equal("path-001", replacement.DocumentPathAlias);
            Assert.NotEqual(initial.CreationGuidAlias, replacement.CreationGuidAlias);
        }

        [Fact]
        public void Capture_RejectsDuplicateCaseWithClosedCode()
        {
            // Break caught: silently overwriting the evidence for a required matrix row.
            var session = Begin();
            Capture(session, BimCreationGuidProbeCase.SavedProjectInitial,
                "11111111-1111-1111-1111-111111111111", @"C:\A.rvt");

            var duplicate = session.Capture(Observation(
                BimCreationGuidProbeCase.SavedProjectInitial,
                "22222222-2222-2222-2222-222222222222", @"C:\B.rvt"));

            Assert.Equal(BimCreationGuidProbeSessionCode.DuplicateCase, duplicate.Code);
            Assert.Null(duplicate.Capture);
        }

        [Fact]
        public void Complete_ReturnsExactMissingCasesAndKeepsSessionActive()
        {
            // Break caught: sealing or clearing a partially captured session.
            var session = Begin();
            Capture(session, BimCreationGuidProbeCase.SavedProjectInitial,
                "11111111-1111-1111-1111-111111111111", @"C:\A.rvt");

            var completion = session.Complete();

            Assert.Equal(BimCreationGuidProbeSessionCode.MissingRequiredCases, completion.Code);
            Assert.Null(completion.Report);
            Assert.Equal(new[]
            {
                BimCreationGuidProbeCase.SavedProjectReopen,
                BimCreationGuidProbeCase.FileCentral,
                BimCreationGuidProbeCase.FileLocal,
                BimCreationGuidProbeCase.FileLocalReopen,
                BimCreationGuidProbeCase.CopiedCentral,
                BimCreationGuidProbeCase.Detached,
                BimCreationGuidProbeCase.SavedFamily,
                BimCreationGuidProbeCase.UnsavedProject,
                BimCreationGuidProbeCase.UnsavedFamily,
                BimCreationGuidProbeCase.ReplacementSamePath,
            }, completion.MissingCases);
            Assert.Equal(BimCreationGuidProbeSessionCode.Captured,
                session.Capture(Observation(BimCreationGuidProbeCase.SavedProjectReopen,
                    "11111111-1111-1111-1111-111111111111", @"C:\A.rvt")).Code);
        }

        [Fact]
        public void Complete_SealsSessionClearsRawStateAndPublishesFixedRelations()
        {
            // Break caught: retaining raw GUID/path state after constructing the report.
            var session = Begin();
            foreach (var caseId in Enum.GetValues(typeof(BimCreationGuidProbeCase))
                .Cast<BimCreationGuidProbeCase>())
            {
                var sameAsInitial = caseId == BimCreationGuidProbeCase.SavedProjectInitial ||
                    caseId == BimCreationGuidProbeCase.SavedProjectReopen ||
                    caseId == BimCreationGuidProbeCase.ReplacementSamePath;
                Capture(session, caseId,
                    sameAsInitial ? "11111111-1111-1111-1111-111111111111" :
                        "22222222-2222-2222-2222-222222222222",
                    caseId == BimCreationGuidProbeCase.SavedProjectInitial ||
                    caseId == BimCreationGuidProbeCase.ReplacementSamePath ? @"C:\Initial.rvt" :
                        @"C:\" + caseId + ".rvt");
            }

            var completion = session.Complete();

            Assert.Equal(BimCreationGuidProbeSessionCode.Completed, completion.Code);
            var report = Assert.IsType<BimCreationGuidProbeReport>(completion.Report);
            Assert.True(report.Complete);
            Assert.True(report.RawStateCleared);
            Assert.Equal(5, report.EqualityRelations.Count);
            Assert.Contains(report.EqualityRelations, relation =>
                relation.LeftCase == BimCreationGuidProbeCase.SavedProjectInitial &&
                relation.RightCase == BimCreationGuidProbeCase.ReplacementSamePath &&
                relation.SameCreationGuid == true && relation.SameDocumentPath == true &&
                relation.SameCentralPath == null && relation.Unavailable == true);
            Assert.Equal(BimCreationGuidProbeSessionCode.NotActive,
                session.Capture(Observation(BimCreationGuidProbeCase.SavedProjectInitial,
                    "33333333-3333-3333-3333-333333333333", @"C:\C.rvt")).Code);
        }

        [Fact]
        public void Abort_ClearsRawStateAndNewSessionRestartsAliases()
        {
            // Break caught: raw alias tables surviving an aborted report and linking reports.
            var session = Begin();
            Capture(session, BimCreationGuidProbeCase.SavedProjectInitial,
                "11111111-1111-1111-1111-111111111111", @"C:\A.rvt");

            var abort = session.Abort();
            var next = Begin();
            var capture = Capture(next, BimCreationGuidProbeCase.SavedProjectInitial,
                "99999999-9999-9999-9999-999999999999", @"C:\Z.rvt");

            Assert.Equal(BimCreationGuidProbeSessionCode.Aborted, abort.Code);
            Assert.True(abort.RawStateCleared);
            Assert.Equal(BimCreationGuidProbeSessionCode.NotActive,
                session.Capture(Observation(BimCreationGuidProbeCase.SavedProjectReopen,
                    "11111111-1111-1111-1111-111111111111", @"C:\A.rvt")).Code);
            Assert.Equal("creation-001", capture.CreationGuidAlias);
            Assert.Equal("path-001", capture.DocumentPathAlias);
        }

        private static BimCreationGuidProbeSession Begin()
        {
            return new BimCreationGuidProbeSession(new BimCreationGuidProbeProvenance
            {
                ProcessId = 36032,
                RevitVersion = "2024.3",
                RhinoVersion = "8.0",
                RhinoInsideRevitVersion = "1.0",
                CoreVersion = "1.5.16",
                ModuleVersion = "1.5.16",
            });
        }

        private static BimCreationGuidProbeCapture Capture(
            BimCreationGuidProbeSession session,
            BimCreationGuidProbeCase caseId,
            string creationGuid,
            string path)
        {
            var result = session.Capture(Observation(caseId, creationGuid, path));
            Assert.Equal(BimCreationGuidProbeSessionCode.Captured, result.Code);
            return Assert.IsType<BimCreationGuidProbeCapture>(result.Capture);
        }

        private static BimCreationGuidProbeObservation Observation(
            BimCreationGuidProbeCase caseId,
            string creationGuid,
            string path)
        {
            return new BimCreationGuidProbeObservation
            {
                CaseId = caseId,
                DocumentClass = BimCreationGuidProbeDocumentClass.SavedNonWorksharedProject,
                CreationGuidFirstStatus = BimCreationGuidProbeReadStatus.Success,
                CreationGuidSecondStatus = BimCreationGuidProbeReadStatus.Success,
                CreationGuid = Guid.Parse(creationGuid),
                CreationGuidNonEmpty = true,
                CreationGuidStable = true,
                DocumentPathStatus = BimCreationGuidProbeReadStatus.Success,
                CanonicalDocumentPath = path,
            };
        }
    }
}
