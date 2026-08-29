using System;
using Rook;
using Xunit;

namespace Rook.Tests
{
    public sealed class DocumentContextTests
    {
        [Fact]
        public void Required_document_refuses_missing_serial_before_operation()
        {
            var operationCalled = false;

            Assert.Throws<InvalidOperationException>(() =>
                DocumentContext.WithRequiredDocument(
                    42,
                    _ => null,
                    () =>
                    {
                        operationCalled = true;
                        return 1;
                    }));

            Assert.False(operationCalled);
        }

        [Fact]
        public void Required_document_failure_restores_prior_legacy_context()
        {
            DocumentContext.TargetDocumentSerialNumber = 7;
            try
            {
                Assert.Throws<InvalidOperationException>(() =>
                    DocumentContext.WithRequiredDocument(
                        42,
                        _ => null,
                        () => 1));

                Assert.Equal(7u, DocumentContext.TargetDocumentSerialNumber);
            }
            finally
            {
                DocumentContext.TargetDocumentSerialNumber = null;
            }
        }
    }
}
