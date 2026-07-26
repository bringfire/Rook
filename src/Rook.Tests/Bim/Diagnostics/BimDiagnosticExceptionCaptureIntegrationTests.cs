using System;
using System.IO;
using System.Linq;
using System.Reflection;
using Rook.Bim;
using Rook.Tests.Bim;
using Xunit;

namespace Rook.Tests.Bim.Diagnostics
{
    [Collection(RookBimRuntimeRegistryCollection.Name)]
    public sealed class BimDiagnosticExceptionCaptureIntegrationTests
    {
        [Fact]
        public void ObserveException_CapturesBeforeEnvelope_AndRetainsNoRawException()
        {
            using var scope = TestDiagnostics.EnabledScope("list_categories");
            var raw = CaptureNestedFailure();

            scope.Session.ObserveException(
                scope.Context,
                BimDiagnosticStage.RevitCategoryName,
                raw,
                new BimDiagnosticFields(
                    BimDiagnosticDetailCode.None,
                    7,
                    BimDiagnosticFailureImpact.Production));

            var envelope = Assert.Single(scope.Sink.Envelopes);
            var captured = Assert.IsType<BimDiagnosticExceptionInfo>(
                envelope.ExceptionInfo);
            Assert.Equal(typeof(InvalidOperationException).FullName,
                captured.TypeName);
            Assert.Contains(nameof(CaptureNestedFailure), captured.Stack);
            Assert.Equal(typeof(ArgumentException).FullName,
                Assert.Single(captured.InnerExceptions).TypeName);

            AssertNoRawExceptionMembers(typeof(BimDiagnosticEnvelope));
            AssertNoRawExceptionMembers(typeof(BimDiagnosticRecord));
            AssertNoRawExceptionMembers(typeof(BimDiagnosticObservation));
            AssertNoRawExceptionMembers(typeof(BimDiagnosticExceptionInfo));
            AssertNoRawExceptionMembers(typeof(BimDiagnosticExceptionCaptureResult));
        }

        [Fact]
        public void ObserveException_CaptureFailureUsesClosedDetailAndStillEnqueuesRootEvidence()
        {
            using var scope = TestDiagnostics.EnabledScope("list_categories");

            scope.Session.ObserveException(
                scope.Context,
                BimDiagnosticStage.RevitCategoryName,
                new ThrowingStackException(),
                new BimDiagnosticFields(
                    BimDiagnosticDetailCode.None,
                    null,
                    BimDiagnosticFailureImpact.Production));

            var envelope = Assert.Single(scope.Sink.Envelopes);
            Assert.Equal(BimDiagnosticDetailCode.ExceptionCaptureFailed,
                envelope.Fields.DetailCode);
            Assert.Equal(typeof(ThrowingStackException).FullName,
                envelope.ExceptionInfo?.TypeName);
            Assert.Equal(typeof(ThrowingStackException).FullName,
                TestDiagnostics.Snapshot(scope.Context)
                    .FirstFailureExceptionType);
        }

        [Fact]
        public void RecordMaterialization_CopiesOnlyTheFixedExceptionNode()
        {
            using var scope = TestDiagnostics.EnabledScope("list_categories");
            scope.Session.ObserveException(
                scope.Context,
                BimDiagnosticStage.RevitCategoryName,
                CaptureNestedFailure(),
                BimDiagnosticFields.None);

            var envelope = Assert.Single(scope.Sink.Envelopes);
            var record = new BimDiagnosticRecord(
                envelope,
                TestDiagnostics.Snapshot(scope.Context),
                "1.2.3",
                "abc123",
                "unavailable",
                "unavailable");

            Assert.Same(envelope.ExceptionInfo, record.ExceptionInfo);
            Assert.Equal(envelope.ExceptionInfo?.TypeName,
                record.ExceptionInfo?.TypeName);
            Assert.Equal(envelope.ExceptionInfo?.HResult,
                record.ExceptionInfo?.HResult);
        }

        [Fact]
        public void ObserveExceptionSource_CapturesExactlyOnceBeforeEnqueue()
        {
            var source = ReadSourceFile(
                "src", "Rook", "Bim", "Diagnostics", "BimDiagnosticSession.cs");
            var method = Extract(
                source,
                "internal void ObserveException(",
                "internal void CompleteRequest(");
            const string CaptureCall =
                "BimDiagnosticExceptionCapture.Capture(exception)";

            var captureIndex = method.IndexOf(CaptureCall,
                StringComparison.Ordinal);
            var enqueueIndex = method.IndexOf("Enqueue(",
                StringComparison.Ordinal);

            Assert.True(captureIndex >= 0);
            Assert.Equal(captureIndex, method.LastIndexOf(CaptureCall,
                StringComparison.Ordinal));
            Assert.True(enqueueIndex > captureIndex);

            var constructor = Extract(
                source,
                "internal BimDiagnosticRecord(",
                "internal BimDiagnosticRecordKind Kind");
            Assert.Contains("ExceptionInfo = envelope.ExceptionInfo", constructor);
        }

        private static Exception CaptureNestedFailure()
        {
            try
            {
                throw new InvalidOperationException(
                    "private root message",
                    new ArgumentException("private inner message"));
            }
            catch (Exception exception)
            {
                return exception;
            }
        }

        private sealed class ThrowingStackException : Exception
        {
            public override string? StackTrace =>
                throw new InvalidOperationException("stack access failed");
        }

        private static void AssertNoRawExceptionMembers(Type type)
        {
            const BindingFlags Flags = BindingFlags.Instance |
                BindingFlags.Public | BindingFlags.NonPublic;
            var unsafeMember = type.GetFields(Flags)
                .Select(field => new { field.Name, MemberType = field.FieldType })
                .Concat(type.GetProperties(Flags).Select(property =>
                    new { property.Name, MemberType = property.PropertyType }))
                .FirstOrDefault(member =>
                    member.MemberType == typeof(object) ||
                    typeof(Exception).IsAssignableFrom(member.MemberType));

            Assert.True(unsafeMember == null,
                type.FullName + " retains unsafe member " + unsafeMember?.Name);
        }

        private static string Extract(
            string source,
            string startMarker,
            string endMarker)
        {
            var start = source.IndexOf(startMarker, StringComparison.Ordinal);
            var end = source.IndexOf(
                endMarker, start + startMarker.Length, StringComparison.Ordinal);
            Assert.True(start >= 0 && end > start);
            return source.Substring(start, end - start);
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory != null)
            {
                var candidate = Path.Combine(
                    new[] { directory.FullName }.Concat(pathParts).ToArray());
                if (File.Exists(candidate))
                {
                    return File.ReadAllText(candidate);
                }

                directory = directory.Parent;
            }

            throw new FileNotFoundException(string.Join("/", pathParts));
        }
    }
}
