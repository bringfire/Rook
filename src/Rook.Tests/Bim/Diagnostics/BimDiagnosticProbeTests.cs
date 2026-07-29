using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.RegularExpressions;
using Rook.Bim;
using Rook.Tests.Bim;
using Xunit;

namespace Rook.Tests.Bim.Diagnostics
{
    [Collection(RookBimRuntimeRegistryCollection.Name)]
    public sealed class BimDiagnosticProbeTests
    {
        [Fact]
        public void Production_RethrowsSameExceptionAndAuxiliaryReturnsUnknown()
        {
            using var scope = TestDiagnostics.EnabledScope("list_categories");
            var expected = new InvalidOperationException("never persist this message");
            var actual = Assert.Throws<InvalidOperationException>(() =>
                BimDiagnosticProbe.Production<int>(
                    scope.Context,
                    BimDiagnosticStage.RevitCategoryId,
                    () => throw expected,
                    new BimDiagnosticFields(
                        BimDiagnosticDetailCode.None,
                        7,
                        BimDiagnosticFailureImpact.Production)));

            Assert.Same(expected, actual);
            var productionFailure = Assert.Single(scope.Sink.Envelopes);
            Assert.Equal(BimDiagnosticRecordKind.Failure, productionFailure.Kind);
            Assert.Equal(typeof(InvalidOperationException).FullName,
                productionFailure.ExceptionTypeName);
            Assert.Equal(expected.HResult, productionFailure.ExceptionHResult);

            var auxiliary = BimDiagnosticProbe.Auxiliary<int>(
                scope.Context,
                BimDiagnosticStage.RevitDocumentCentralModelPath,
                () => throw new InvalidOperationException("ignored"));

            Assert.False(auxiliary.Known);
            Assert.Equal(2, scope.Sink.Envelopes.Count);
            var auxiliaryFailure = scope.Sink.Envelopes[1];
            Assert.Equal(BimDiagnosticDetailCode.ProbeFailure,
                auxiliaryFailure.Fields.DetailCode);
            Assert.Equal(BimDiagnosticFailureImpact.Auxiliary,
                auxiliaryFailure.Fields.FailureImpact);
        }

        [Fact]
        public void Disabled_ProductionReadsOnceAndAuxiliaryDoesNotInvokeItsDelegate()
        {
            var productionReads = 0;
            var auxiliaryReads = 0;

            var production = BimDiagnosticProbe.Production(
                BimDiagnosticContext.Disabled,
                BimDiagnosticStage.RevitCategoryName,
                () =>
                {
                    productionReads++;
                    return "Walls";
                },
                BimDiagnosticFields.None);
            var auxiliary = BimDiagnosticProbe.Auxiliary(
                BimDiagnosticContext.Disabled,
                BimDiagnosticStage.RevitDocumentIsDetached,
                () =>
                {
                    auxiliaryReads++;
                    return true;
                });

            Assert.Equal("Walls", production);
            Assert.Equal(1, productionReads);
            Assert.False(auxiliary.Known);
            Assert.Equal(0, auxiliaryReads);
        }

        [Fact]
        public void DetailSelectorFailure_FallsBackToNoneWithoutChangingProbeResult()
        {
            using var scope = TestDiagnostics.EnabledScope("active_document");

            var result = BimDiagnosticProbe.Production(
                scope.Context,
                BimDiagnosticStage.RevitDocumentIsFamily,
                () => true,
                BimDiagnosticFields.None,
                _ => throw new InvalidOperationException("selector"));
            var auxiliary = BimDiagnosticProbe.Auxiliary(
                scope.Context,
                BimDiagnosticStage.RevitDocumentIsDetached,
                () => false,
                _ => throw new InvalidOperationException("selector"));

            Assert.True(result);
            Assert.True(auxiliary.Known);
            Assert.False(auxiliary.Value);
            var snapshot = TestDiagnostics.Snapshot(scope.Context);
            Assert.Equal(BimDiagnosticOutcome.Success, snapshot.LastOutcome);
            Assert.Empty(scope.Sink.Envelopes);
        }

        [Fact]
        public void ProductionSource_ObservesExceptionBeforeBareRethrow()
        {
            var source = ReadSourceFile(
                "src", "Rook", "Bim", "Diagnostics", "BimDiagnosticProbe.cs");
            var production = ExtractMethod(source, "public static T Production<T>(", "public static BimAuxiliaryProbeResult<T> Auxiliary<T>(");

            var observeIndex = production.IndexOf(
                "BimDiagnostics.ObserveException", StringComparison.Ordinal);
            var throwIndex = production.IndexOf("throw;", StringComparison.Ordinal);

            Assert.True(observeIndex >= 0);
            Assert.True(throwIndex > observeIndex);
            Assert.Matches(new Regex(@"catch\s*\([^)]*\)\s*\{[\s\S]*?BimDiagnostics\.ObserveException[\s\S]*?throw\s*;"), production);
            Assert.DoesNotContain("throw ex;", production);
            Assert.DoesNotContain("throw exception;", production);
        }

        [Fact]
        public void DiagnosticStateShapes_RetainNoRawExceptionOrObjectMembers()
        {
            AssertNoRawExceptionOrObjectMembers(typeof(BimDiagnosticContext));
            AssertNoRawExceptionOrObjectMembers(typeof(BimDiagnosticObservation));
            AssertNoRawExceptionOrObjectMembers(typeof(BimDiagnosticEnvelope));
            AssertNoRawExceptionOrObjectMembers(typeof(BimDiagnosticSession));
            AssertNoRawExceptionOrObjectMembers(typeof(BimDiagnosticRecord));
        }

        private static void AssertNoRawExceptionOrObjectMembers(Type type)
        {
            const BindingFlags Flags = BindingFlags.Instance |
                BindingFlags.Public | BindingFlags.NonPublic;

            var unsafeMember = type.GetFields(Flags)
                .Select(field => new { field.Name, MemberType = field.FieldType })
                .Concat(type.GetProperties(Flags)
                    .Select(property => new { property.Name, MemberType = property.PropertyType }))
                .FirstOrDefault(member =>
                    member.MemberType == typeof(object) ||
                    typeof(Exception).IsAssignableFrom(member.MemberType));

            Assert.True(unsafeMember == null,
                type.FullName + " retains unsafe member " + unsafeMember?.Name);
        }

        private static string ExtractMethod(string source, string startMarker, string endMarker)
        {
            var start = source.IndexOf(startMarker, StringComparison.Ordinal);
            var end = source.IndexOf(endMarker, start + startMarker.Length,
                StringComparison.Ordinal);
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
