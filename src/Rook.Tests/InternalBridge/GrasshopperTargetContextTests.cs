using System;
using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.InternalBridge
{
    public class GrasshopperTargetContextTests
    {
        [Fact]
        public void CaptureAndRun_UsesOneCanvasLookupAndTheCapturedDocument()
        {
            var expectedId = Guid.NewGuid();
            var intendedDocument = new FakeDocument(expectedId);
            var decoyDocument = new FakeDocument(Guid.NewGuid());
            var intendedCanvas = new FakeCanvas(intendedDocument);
            var decoyCanvas = new FakeCanvas(decoyDocument);
            var lookups = 0;

            var observedDocument = GrasshopperRequestContext.CaptureAndRun(
                typeof(GrasshopperTargetContextTests).Assembly,
                () => ++lookups == 1 ? intendedCanvas : decoyCanvas,
                expectedId.ToString("D"),
                () => GrasshopperRequestContext.Current!.Document);

            Assert.Same(intendedDocument, observedDocument);
            Assert.Equal(1, lookups);
            Assert.Null(GrasshopperRequestContext.Current);
        }

        [Fact]
        public void CaptureAndRun_RefusesMissingCanvasBeforeOperation()
        {
            AssertRefused(
                () => null,
                Guid.NewGuid().ToString("D"),
                "active Grasshopper canvas");
        }

        [Fact]
        public void CaptureAndRun_RefusesMissingDocumentBeforeOperation()
        {
            AssertRefused(
                () => new FakeCanvas(null),
                Guid.NewGuid().ToString("D"),
                "active Grasshopper document");
        }

        [Fact]
        public void CaptureAndRun_RefusesEmptyDocumentIdBeforeOperation()
        {
            AssertRefused(
                () => new FakeCanvas(new FakeDocument(Guid.Empty)),
                Guid.NewGuid().ToString("D"),
                "nonempty DocumentID");
        }

        [Fact]
        public void CaptureAndRun_RefusesMalformedBoundIdBeforeCanvasLookup()
        {
            var lookups = 0;
            var invoked = false;

            var error = Assert.Throws<InvalidOperationException>(() =>
                GrasshopperRequestContext.CaptureAndRun(
                    typeof(GrasshopperTargetContextTests).Assembly,
                    () =>
                    {
                        lookups++;
                        return new FakeCanvas(new FakeDocument(Guid.NewGuid()));
                    },
                    "NOT-A-GUID",
                    () =>
                    {
                        invoked = true;
                        return true;
                    }));

            Assert.Contains("canonical", error.Message, StringComparison.OrdinalIgnoreCase);
            Assert.Equal(0, lookups);
            Assert.False(invoked);
        }

        [Fact]
        public void CaptureAndRun_RefusesMismatchedDocumentIdBeforeOperation()
        {
            AssertRefused(
                () => new FakeCanvas(new FakeDocument(Guid.NewGuid())),
                Guid.NewGuid().ToString("D"),
                "does not match");
        }

        [Fact]
        public void CaptureAndRun_RefusesClosedDocumentBeforeOperation()
        {
            var expectedId = Guid.NewGuid();
            AssertRefused(
                () => new FakeCanvas(new FakeDocument(expectedId) { IsClosed = true }),
                expectedId.ToString("D"),
                "closed");
        }

        private static void AssertRefused(
            Func<object?> activeCanvas,
            string boundDocumentId,
            string expectedMessage)
        {
            var invoked = false;

            var error = Assert.Throws<InvalidOperationException>(() =>
                GrasshopperRequestContext.CaptureAndRun(
                    typeof(GrasshopperTargetContextTests).Assembly,
                    activeCanvas,
                    boundDocumentId,
                    () =>
                    {
                        invoked = true;
                        return true;
                    }));

            Assert.Contains(expectedMessage, error.Message, StringComparison.OrdinalIgnoreCase);
            Assert.False(invoked);
            Assert.Null(GrasshopperRequestContext.Current);
        }

        private sealed class FakeCanvas
        {
            public FakeCanvas(object? document)
            {
                Document = document;
            }

            public object? Document { get; }
        }

        private sealed class FakeDocument
        {
            public FakeDocument(Guid documentId)
            {
                DocumentID = documentId;
            }

            public Guid DocumentID { get; }
            public bool IsClosed { get; set; }
        }
    }
}
