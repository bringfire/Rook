using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim.CreationGuidProbe
{
    public sealed class BimCreationGuidProbeEvidenceClassifierTests
    {
        [Fact]
        public void Classify_FailedWorksharingReadDoesNotInferSavedProject()
        {
            var result = BimCreationGuidProbeEvidenceClassifier.Classify(
                isWorkshared: null,
                isDetached: false,
                isModelInCloud: false,
                isFamilyDocument: false,
                hasDocumentPath: true,
                hasCentralModelPath: false,
                serverPath: false,
                cloudPath: false,
                isCentral: false,
                isLocal: false);

            Assert.Equal(BimCreationGuidProbeDocumentClass.Unknown, result);
        }

        [Fact]
        public void Classify_FailedDetachedReadDoesNotInferNonDetachedClass()
        {
            var result = BimCreationGuidProbeEvidenceClassifier.Classify(
                isWorkshared: false,
                isDetached: null,
                isModelInCloud: false,
                isFamilyDocument: false,
                hasDocumentPath: true,
                hasCentralModelPath: false,
                serverPath: false,
                cloudPath: false,
                isCentral: false,
                isLocal: false);

            Assert.Equal(BimCreationGuidProbeDocumentClass.Unknown, result);
        }

        [Theory]
        [InlineData(null, false)]
        [InlineData(false, null)]
        [InlineData(null, null)]
        public void ModelPathKind_UnavailableKindReadDoesNotInferFile(bool? server, bool? cloud)
        {
            var result = BimCreationGuidProbeEvidenceClassifier.ModelPathKind(
                hasCentralModelPath: true,
                serverPath: server,
                cloudPath: cloud);

            Assert.Equal(BimCreationGuidProbeModelPathKind.Unknown, result);
        }

        [Fact]
        public void ModelPathKind_BothSuccessfulFalseProvesFile()
        {
            Assert.Equal(
                BimCreationGuidProbeModelPathKind.File,
                BimCreationGuidProbeEvidenceClassifier.ModelPathKind(true, false, false));
        }

        [Theory]
        [InlineData(true, false, BimCreationGuidProbeModelPathKind.Server)]
        [InlineData(false, true, BimCreationGuidProbeModelPathKind.Cloud)]
        public void ModelPathKind_StrongKindEvidenceWins(
            bool server, bool cloud, BimCreationGuidProbeModelPathKind expected)
        {
            Assert.Equal(expected,
                BimCreationGuidProbeEvidenceClassifier.ModelPathKind(true, server, cloud));
        }

        [Fact]
        public void Classify_FileWorksharedRequiresProvenFileModelPath()
        {
            var unknown = BimCreationGuidProbeEvidenceClassifier.Classify(
                true, false, false, false, true, true, null, false, true, false);
            var central = BimCreationGuidProbeEvidenceClassifier.Classify(
                true, false, false, false, true, true, false, false, true, false);

            Assert.Equal(BimCreationGuidProbeDocumentClass.Unknown, unknown);
            Assert.Equal(BimCreationGuidProbeDocumentClass.FileWorksharedCentral, central);
        }

        [Fact]
        public void Classify_DetachedSuccessfulEvidenceWinsOtherUnknowns()
        {
            Assert.Equal(BimCreationGuidProbeDocumentClass.Detached,
                BimCreationGuidProbeEvidenceClassifier.Classify(
                    null, true, null, null, null, null, null, null, null, null));
        }
    }
}
