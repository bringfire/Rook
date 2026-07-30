using System;
using System.Collections.Generic;
using Rook.Bim;
using Rook.Tests.Bim.Diagnostics;
using Xunit;

namespace Rook.Tests.Bim
{
    public sealed class BimDocumentIdentityPolicyTests
    {
        private const string ValidFileKey = "file-document-v1:50250fd46d4c96e14f57ff283d6fd21965d8525a34d638e5070eaf60df13a0ac";
        private const string ValidSavedKey = "saved-document-v1:f8068f0ccb7e520b278de67a1b167f880ecbc7ec9ff4ddba603407643fc3e250";

        [Theory]
        [MemberData(nameof(ExactReaderCases))]
        public void Capture_InvokesTheExactReaderSetForEachDocumentClass(
            BimDocumentIdentityPolicy.DocumentClass expectedClass,
            bool detached,
            bool workshared,
            bool cloud,
            bool family,
            string? documentPath,
            BimDocumentIdentityPolicy.CentralPath centralPath,
            int[] expectedCalls)
        {
            var calls = new Dictionary<string, int>(StringComparer.Ordinal);
            BimDocumentIdentityPolicy.ReadResult<T> Read<T>(string name, T value)
            {
                calls[name] = calls.TryGetValue(name, out var count) ? count + 1 : 1;
                return BimDocumentIdentityPolicy.ReadResult<T>.Success(value);
            }

            var evidence = BimDocumentIdentityPolicy.Capture(new BimDocumentIdentityPolicy.Readers(
                () => Read("detached", detached), () => Read("workshared", workshared),
                () => Read("cloud", cloud), () => Read("family", family),
                () => Read<string?>("path", documentPath), () => Read("central", centralPath),
                () => Read("creation", Guid.ParseExact("00112233-4455-6677-8899-aabbccddeeff", "D")),
                () => Read("server", Guid.ParseExact("00112233-4455-6677-8899-aabbccddeeff", "D"))));

            Assert.Equal(expectedClass, evidence.Class);
            AssertCalls(calls, expectedCalls);
        }

        public static IEnumerable<object[]> ExactReaderCases()
        {
            yield return new object[] { BimDocumentIdentityPolicy.DocumentClass.Detached, true, false, false, false, @"C:\LOCAL.RVT", new BimDocumentIdentityPolicy.CentralPath(BimDocumentIdentityPolicy.CentralPathKind.File, @"C:\MODELS\A.RVT"), new[] { 1, 1, 0, 0, 0, 0, 0, 0 } };
            yield return new object[] { BimDocumentIdentityPolicy.DocumentClass.FileWorkshared, false, true, false, false, @"C:\LOCAL.RVT", new BimDocumentIdentityPolicy.CentralPath(BimDocumentIdentityPolicy.CentralPathKind.File, @"C:\MODELS\A.RVT"), new[] { 1, 1, 1, 0, 0, 1, 1, 0 } };
            yield return new object[] { BimDocumentIdentityPolicy.DocumentClass.RevitServer, false, true, false, false, @"C:\LOCAL.RVT", new BimDocumentIdentityPolicy.CentralPath(BimDocumentIdentityPolicy.CentralPathKind.Server, null), new[] { 1, 1, 1, 0, 0, 1, 0, 1 } };
            yield return new object[] { BimDocumentIdentityPolicy.DocumentClass.CloudWorkshared, false, true, true, false, @"C:\LOCAL.RVT", new BimDocumentIdentityPolicy.CentralPath(BimDocumentIdentityPolicy.CentralPathKind.File, @"C:\MODELS\A.RVT"), new[] { 1, 1, 1, 0, 0, 0, 0, 0 } };
            yield return new object[] { BimDocumentIdentityPolicy.DocumentClass.SavedProject, false, false, false, false, @"C:\LOCAL.RVT", new BimDocumentIdentityPolicy.CentralPath(BimDocumentIdentityPolicy.CentralPathKind.File, @"C:\IGNORED.RVT"), new[] { 1, 1, 0, 1, 1, 0, 1, 0 } };
            yield return new object[] { BimDocumentIdentityPolicy.DocumentClass.SavedFamily, false, false, false, true, @"C:\LOCAL.RFA", new BimDocumentIdentityPolicy.CentralPath(BimDocumentIdentityPolicy.CentralPathKind.File, @"C:\IGNORED.RVT"), new[] { 1, 1, 0, 1, 0, 0, 0, 0 } };
            yield return new object[] { BimDocumentIdentityPolicy.DocumentClass.UnsavedProject, false, false, false, false, "", new BimDocumentIdentityPolicy.CentralPath(BimDocumentIdentityPolicy.CentralPathKind.File, @"C:\IGNORED.RVT"), new[] { 1, 1, 0, 1, 1, 0, 0, 0 } };
        }

        [Fact]
        public void Capture_RequiresBothBaseDiscriminatorsBeforeDetachedClassification()
        {
            var calls = new Dictionary<string, int>(StringComparer.Ordinal);
            BimDocumentIdentityPolicy.ReadResult<T> Read<T>(string name, BimDocumentIdentityPolicy.ReadResult<T> result)
            {
                calls[name] = calls.TryGetValue(name, out var count) ? count + 1 : 1;
                return result;
            }

            var evidence = BimDocumentIdentityPolicy.Capture(new BimDocumentIdentityPolicy.Readers(
                () => Read("detached", BimDocumentIdentityPolicy.ReadResult<bool>.Success(true)),
                () => Read("workshared", BimDocumentIdentityPolicy.ReadResult<bool>.Unavailable(BimDocumentIdentityPolicy.UnavailableReason.DiscriminatorUnavailable)),
                () => Read("cloud", BimDocumentIdentityPolicy.ReadResult<bool>.Success(false)),
                () => Read("family", BimDocumentIdentityPolicy.ReadResult<bool>.Success(false)),
                () => Read("path", BimDocumentIdentityPolicy.ReadResult<string?>.Success(@"C:\LOCAL.RVT")),
                () => Read("central", BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath>.Success(new BimDocumentIdentityPolicy.CentralPath(BimDocumentIdentityPolicy.CentralPathKind.File, @"C:\MODELS\A.RVT"))),
                () => Read("creation", BimDocumentIdentityPolicy.ReadResult<Guid>.Success(Guid.NewGuid())),
                () => Read("server", BimDocumentIdentityPolicy.ReadResult<Guid>.Success(Guid.NewGuid()))));

            Assert.Equal(BimDocumentIdentityPolicy.DocumentClass.Unknown, evidence.Class);
            Assert.Equal(BimDocumentIdentityPolicy.UnavailableReason.DiscriminatorUnavailable, evidence.Reason);
            AssertCalls(calls, new[] { 1, 1, 0, 0, 0, 0, 0, 0 });
        }

        [Fact]
        public void Capture_RejectsUnknownCentralPathKindWithoutReadingCreationGuid()
        {
            var calls = new Dictionary<string, int>(StringComparer.Ordinal);
            BimDocumentIdentityPolicy.ReadResult<T> Read<T>(string name, T value)
            {
                calls[name] = calls.TryGetValue(name, out var count) ? count + 1 : 1;
                return BimDocumentIdentityPolicy.ReadResult<T>.Success(value);
            }

            var evidence = BimDocumentIdentityPolicy.Capture(new BimDocumentIdentityPolicy.Readers(
                () => Read("detached", false), () => Read("workshared", true), () => Read("cloud", false), () => Read("family", false),
                () => Read<string?>("path", @"C:\LOCAL.RVT"), () => Read("central", new BimDocumentIdentityPolicy.CentralPath((BimDocumentIdentityPolicy.CentralPathKind)999, @"C:\MODELS\A.RVT")),
                () => Read("creation", Guid.NewGuid()), () => Read("server", Guid.NewGuid())));

            Assert.Equal(BimDocumentKeySource.Unavailable, evidence.DocumentKeySource);
            Assert.Equal(BimDocumentIdentityPolicy.UnavailableReason.UnsupportedClass, evidence.Reason);
            AssertCalls(calls, new[] { 1, 1, 1, 0, 0, 1, 0, 0 });
        }

        [Theory]
        [MemberData(nameof(CaptureCases))]
        public void Capture_UsesRequiredReadersOnly(string name, BimDocumentIdentityPolicy.DocumentClass expectedClass, bool detached, bool workshared, bool cloud, bool family, BimDocumentIdentityPolicy.CentralPath centralPath)
        {
            Assert.False(string.IsNullOrEmpty(name));
            var calls = new Dictionary<string, int>(StringComparer.Ordinal);
            BimDocumentIdentityPolicy.ReadResult<T> Read<T>(string reader, T value)
            {
                calls[reader] = calls.TryGetValue(reader, out var count) ? count + 1 : 1;
                return BimDocumentIdentityPolicy.ReadResult<T>.Success(value);
            }

            var evidence = BimDocumentIdentityPolicy.Capture(new BimDocumentIdentityPolicy.Readers(
                () => Read("detached", detached), () => Read("workshared", workshared),
                () => Read("cloud", cloud), () => Read("family", family),
                () => Read<string?>("path", @"C:\LOCAL.RVT"), () => Read("central", centralPath),
                () => Read("creation", Guid.ParseExact("00112233-4455-6677-8899-aabbccddeeff", "D")),
                () => Read("server", Guid.NewGuid())));

            Assert.Equal(expectedClass, evidence.Class);
            Assert.Equal(1, calls["detached"]);
            Assert.Equal(1, calls["workshared"]);
            if (expectedClass == BimDocumentIdentityPolicy.DocumentClass.FileWorkshared || expectedClass == BimDocumentIdentityPolicy.DocumentClass.RevitServer)
            {
                Assert.Equal(1, calls["cloud"]);
                Assert.Equal(1, calls["central"]);
                Assert.False(calls.ContainsKey("family"));
                Assert.False(calls.ContainsKey("path"));
            }
            if (expectedClass == BimDocumentIdentityPolicy.DocumentClass.FileWorkshared)
                Assert.False(calls.ContainsKey("server"));
            if (expectedClass == BimDocumentIdentityPolicy.DocumentClass.RevitServer)
                Assert.False(calls.ContainsKey("creation"));
            if (expectedClass == BimDocumentIdentityPolicy.DocumentClass.SavedProject)
            {
                Assert.Equal(1, calls["family"]);
                Assert.Equal(1, calls["path"]);
                Assert.Equal(1, calls["creation"]);
            }
        }

        public static IEnumerable<object[]> CaptureCases()
        {
            yield return new object[] { "file", BimDocumentIdentityPolicy.DocumentClass.FileWorkshared, false, true, false, false, new BimDocumentIdentityPolicy.CentralPath(BimDocumentIdentityPolicy.CentralPathKind.File, @"C:\MODELS\A.RVT") };
            yield return new object[] { "server", BimDocumentIdentityPolicy.DocumentClass.RevitServer, false, true, false, false, new BimDocumentIdentityPolicy.CentralPath(BimDocumentIdentityPolicy.CentralPathKind.Server, null) };
            yield return new object[] { "saved", BimDocumentIdentityPolicy.DocumentClass.SavedProject, false, false, false, false, new BimDocumentIdentityPolicy.CentralPath(BimDocumentIdentityPolicy.CentralPathKind.File, @"C:\IGNORED.RVT") };
        }

        [Theory]
        [InlineData("detached")]
        [InlineData("workshared")]
        [InlineData("cloud")]
        [InlineData("family")]
        [InlineData("central")]
        public void Capture_ClassificationReadFailureStopsIdentityReaders(string failedReader)
        {
            var calls = new Dictionary<string, int>(StringComparer.Ordinal);
            BimDocumentIdentityPolicy.ReadResult<T> Read<T>(string name, T value)
            {
                calls[name] = calls.TryGetValue(name, out var count) ? count + 1 : 1;
                return name == failedReader
                    ? BimDocumentIdentityPolicy.ReadResult<T>.Unavailable(BimDocumentIdentityPolicy.UnavailableReason.DiscriminatorUnavailable)
                    : BimDocumentIdentityPolicy.ReadResult<T>.Success(value);
            }

            var evidence = BimDocumentIdentityPolicy.Capture(new BimDocumentIdentityPolicy.Readers(
                () => Read("detached", false), () => Read("workshared", failedReader != "family"), () => Read("cloud", false), () => Read("family", false),
                () => Read<string?>("path", @"C:\LOCAL.RVT"), () => Read("central", new BimDocumentIdentityPolicy.CentralPath(BimDocumentIdentityPolicy.CentralPathKind.File, @"C:\MODELS\A.RVT")),
                () => Read("creation", Guid.NewGuid()), () => Read("server", Guid.NewGuid())));

            Assert.Equal(BimDocumentKeySource.Unavailable, evidence.DocumentKeySource);
            Assert.Equal(BimDocumentIdentityPolicy.UnavailableReason.DiscriminatorUnavailable, evidence.Reason);
            Assert.False(calls.ContainsKey("creation"));
            Assert.False(calls.ContainsKey("server"));
        }

        [Fact]
        public void CaptureRead_ContainsExpectedExceptionsWithoutRetainingThem()
        {
            var expected = new ExpectedReadException();
            var calls = 0;
            var result = BimDocumentIdentityPolicy.CaptureRead<int>(
                () => { calls++; throw expected; }, exception => exception is ExpectedReadException,
                BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable);

            Assert.Equal(1, calls);
            Assert.False(result.Available);
            Assert.Equal(BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable, result.Reason);
            Assert.Equal(0, result.Value);
        }

        [Fact]
        public void CaptureRead_RethrowsUnexpectedExceptionUnchanged()
        {
            var unexpected = new InvalidOperationException("unexpected");
            var thrown = Assert.Throws<InvalidOperationException>(() => BimDocumentIdentityPolicy.CaptureRead<int>(
                () => throw unexpected, _ => false, BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable));
            Assert.Same(unexpected, thrown);
        }

        [Fact]
        public void CaptureRead_HasTheSameClosedResultThroughEnabledDiagnostics()
        {
            Func<int> raw = () => 42;
            var direct = BimDocumentIdentityPolicy.CaptureRead(raw, _ => false, BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable);
            using var scope = TestDiagnostics.EnabledScope("identity_policy");
            Func<int> observed = () => BimDiagnosticProbe.Production(scope.Context, BimDiagnosticStage.RevitDocumentAcquire, raw, BimDiagnosticFields.None);
            var enabled = BimDocumentIdentityPolicy.CaptureRead(observed, _ => false, BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable);
            Assert.Equal(direct.Available, enabled.Available);
            Assert.Equal(direct.Value, enabled.Value);
            Assert.Equal(direct.Reason, enabled.Reason);
        }

        [Fact]
        public void CaptureRead_ContainsExpectedFailureTheSameWayThroughEnabledDiagnostics()
        {
            Func<int> raw = () => throw new ExpectedReadException();
            var direct = BimDocumentIdentityPolicy.CaptureRead(raw, exception => exception is ExpectedReadException, BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable);
            using var scope = TestDiagnostics.EnabledScope("identity_policy");
            Func<int> observed = () => BimDiagnosticProbe.Production(scope.Context, BimDiagnosticStage.RevitDocumentAcquire, raw, BimDiagnosticFields.None);
            var enabled = BimDocumentIdentityPolicy.CaptureRead(observed, exception => exception is ExpectedReadException, BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable);
            Assert.Equal(direct.Available, enabled.Available);
            Assert.Equal(direct.Value, enabled.Value);
            Assert.Equal(direct.Reason, enabled.Reason);
        }

        [Theory]
        [InlineData(null, BimDocumentKeySource.RevitCreationGuidCentralPathV1)]
        [InlineData("", BimDocumentKeySource.RevitCreationGuidCentralPathV1)]
        [InlineData("   ", BimDocumentKeySource.RevitCreationGuidCentralPathV1)]
        [InlineData("file-document-v1:bad", BimDocumentKeySource.RevitCreationGuidCentralPathV1)]
        [InlineData(ValidFileKey, BimDocumentKeySource.Unavailable)]
        public void Compare_IncoherentStrongEvidence_IsInvalid(string? key, BimDocumentKeySource source)
        {
            Assert.Equal(BimDocumentIdentityPolicy.Comparison.InvalidEvidence,
                BimDocumentIdentityPolicy.Compare(ActiveFileEvidence(), Claim(key, source)));
        }

        [Theory]
        [InlineData("00112233-4455-6677-8899-aabbccddeeff", true)]
        [InlineData("00112233-4455-6677-8899-AABBCCDDEEFF", true)]
        [InlineData("{00112233-4455-6677-8899-aabbccddeeff}", false)]
        [InlineData("00112233445566778899aabbccddeeff", false)]
        [InlineData(" 00112233-4455-6677-8899-aabbccddeeff", false)]
        [InlineData("00112233-4455-6677-8899-aabbccddeeff ", false)]
        [InlineData("not-a-guid", false)]
        [InlineData("00000000-0000-0000-0000-000000000000", false)]
        public void Compare_ValidatesLegacyGuidInExactDForm(string value, bool valid)
        {
            var claim = new BimDocumentIdentityPolicy.Claim("revit", null, BimDocumentKeySource.Unavailable, value,
                BimDocumentGuidSource.RevitPersistentGuid, false, null, null, null, null, null, "element-1", 1);
            var comparison = BimDocumentIdentityPolicy.Compare(ServerEvidence(), claim);
            Assert.Equal(valid ? BimDocumentIdentityPolicy.Comparison.Match : BimDocumentIdentityPolicy.Comparison.InvalidEvidence, comparison);
        }

        [Fact]
        public void Compare_PathFallbackIsTransportCompatibleButUnavailable()
        {
            var claim = new BimDocumentIdentityPolicy.Claim("revit", null, BimDocumentKeySource.Unavailable, "C:\\OLD.RVT",
                BimDocumentGuidSource.PathFallback, false, null, null, null, null, null, "element-1", 1);
            Assert.Equal(BimDocumentIdentityPolicy.Comparison.Unavailable,
                BimDocumentIdentityPolicy.Compare(ActiveFileEvidence(), claim));
        }

        [Theory]
        [MemberData(nameof(ComparisonCases))]
        public void Compare_ImplementsTheNormativeCoherenceAndComparisonTable(
            BimDocumentIdentityPolicy.Evidence active,
            BimDocumentIdentityPolicy.Claim incoming,
            BimDocumentIdentityPolicy.Comparison expected)
        {
            Assert.Equal(expected, BimDocumentIdentityPolicy.Compare(active, incoming));
        }

        public static IEnumerable<object[]> ComparisonCases()
        {
            yield return new object[] { ActiveFileEvidence(), new BimDocumentIdentityPolicy.Claim("other", ValidFileKey, BimDocumentKeySource.RevitCreationGuidCentralPathV1, null, BimDocumentGuidSource.Unavailable, false, null, null, null, null, null, "element-1", 1), BimDocumentIdentityPolicy.Comparison.InvalidEvidence };
            yield return new object[] { ActiveFileEvidence(), Claim(null, BimDocumentKeySource.RevitCreationGuidCentralPathV1), BimDocumentIdentityPolicy.Comparison.InvalidEvidence };
            yield return new object[] { ActiveFileEvidence(), Claim(ValidFileKey, BimDocumentKeySource.Unavailable), BimDocumentIdentityPolicy.Comparison.InvalidEvidence };
            yield return new object[] { ActiveFileEvidence(), new BimDocumentIdentityPolicy.Claim("revit", ValidFileKey, BimDocumentKeySource.RevitCreationGuidCentralPathV1, "00112233-4455-6677-8899-aabbccddeeff", BimDocumentGuidSource.RevitPersistentGuid, false, null, null, null, null, null, "element-1", 1), BimDocumentIdentityPolicy.Comparison.InvalidEvidence };
            yield return new object[] { ActiveFileEvidence(), Claim(null, BimDocumentKeySource.Unavailable), BimDocumentIdentityPolicy.Comparison.Unavailable };
            yield return new object[] { ActiveFileEvidence(), new BimDocumentIdentityPolicy.Claim("revit", null, BimDocumentKeySource.Unavailable, null, BimDocumentGuidSource.PathFallback, false, null, null, null, null, null, "element-1", 1), BimDocumentIdentityPolicy.Comparison.InvalidEvidence };
            yield return new object[] { ActiveFileEvidence(), new BimDocumentIdentityPolicy.Claim("revit", null, BimDocumentKeySource.Unavailable, "00112233-4455-6677-8899-aabbccddeeff", BimDocumentGuidSource.Unavailable, false, null, null, null, null, null, "element-1", 1), BimDocumentIdentityPolicy.Comparison.InvalidEvidence };
            yield return new object[] { ActiveFileEvidence(), Claim("file-document-v1:00250fd46d4c96e14f57ff283d6fd21965d8525a34d638e5070eaf60df13a0ac", BimDocumentKeySource.RevitCreationGuidCentralPathV1), BimDocumentIdentityPolicy.Comparison.Mismatch };
            yield return new object[] { ActiveFileEvidence(), Claim(ValidSavedKey, BimDocumentKeySource.RevitCreationGuidDocumentPathV1), BimDocumentIdentityPolicy.Comparison.Mismatch };
            yield return new object[] { UnavailableFileEvidence(), Claim(ValidFileKey, BimDocumentKeySource.RevitCreationGuidCentralPathV1), BimDocumentIdentityPolicy.Comparison.Unavailable };
            yield return new object[] { ServerEvidence(), LegacyClaim("00112233-4455-6677-8899-aabbccddeeff"), BimDocumentIdentityPolicy.Comparison.Match };
            yield return new object[] { ServerEvidence(), LegacyClaim("00112233-4455-6677-8899-aabbccddeeff".ToUpperInvariant()), BimDocumentIdentityPolicy.Comparison.Match };
            yield return new object[] { ServerEvidence(), LegacyClaim("11112233-4455-6677-8899-aabbccddeeff"), BimDocumentIdentityPolicy.Comparison.Mismatch };
            yield return new object[] { ActiveFileEvidence(), LegacyClaim("00112233-4455-6677-8899-aabbccddeeff"), BimDocumentIdentityPolicy.Comparison.Mismatch };
            yield return new object[] { UnknownEvidence(), LegacyClaim("00112233-4455-6677-8899-aabbccddeeff"), BimDocumentIdentityPolicy.Comparison.Unavailable };
            yield return new object[] { UnavailableServerEvidence(), LegacyClaim("00112233-4455-6677-8899-aabbccddeeff"), BimDocumentIdentityPolicy.Comparison.Unavailable };
        }

        [Fact]
        public void PreflightBatch_ReturnsFirstFailureAfterAnEarlierValidEntry()
        {
            var valid = Claim(ValidFileKey, BimDocumentKeySource.RevitCreationGuidCentralPathV1);
            var invalid = Claim("file-document-v1:bad", BimDocumentKeySource.RevitCreationGuidCentralPathV1);
            var result = BimDocumentIdentityPolicy.PreflightBatch(ActiveFileEvidence(), new BimDocumentIdentityPolicy.Claim?[] { valid, invalid });
            Assert.Equal(BimDocumentIdentityPolicy.PreflightOutcome.InvalidEvidence, result.Outcome);
            Assert.Equal(1, result.ItemIndex);
        }

        [Theory]
        [MemberData(nameof(PreflightPrecedenceCases))]
        public void PreflightBatch_UsesNormativeValidationOrder(BimDocumentIdentityPolicy.Claim? claim, BimDocumentIdentityPolicy.PreflightOutcome expected)
        {
            var result = BimDocumentIdentityPolicy.PreflightBatch(ActiveFileEvidence(), new[] { claim });
            Assert.Equal(expected, result.Outcome);
            Assert.Equal(0, result.ItemIndex);
        }

        public static IEnumerable<object[]> PreflightPrecedenceCases()
        {
            yield return new object[] { null!, BimDocumentIdentityPolicy.PreflightOutcome.InvalidEvidence };
            yield return new object[] { new BimDocumentIdentityPolicy.Claim("wrong", ValidFileKey, BimDocumentKeySource.RevitCreationGuidCentralPathV1, null, BimDocumentGuidSource.Unavailable, true, null, null, null, null, null, "element-1", 1), BimDocumentIdentityPolicy.PreflightOutcome.LinkedElementUnsupported };
            yield return new object[] { new BimDocumentIdentityPolicy.Claim("wrong", ValidFileKey, BimDocumentKeySource.RevitCreationGuidCentralPathV1, null, BimDocumentGuidSource.Unavailable, false, null, "", null, null, null, "element-1", 1), BimDocumentIdentityPolicy.PreflightOutcome.LinkedElementUnsupported };
            yield return new object[] { Claim("file-document-v1:bad", BimDocumentKeySource.RevitCreationGuidCentralPathV1), BimDocumentIdentityPolicy.PreflightOutcome.InvalidEvidence };
            yield return new object[] { Claim(ValidFileKey, BimDocumentKeySource.RevitCreationGuidCentralPathV1, uniqueId: null, elementId: null), BimDocumentIdentityPolicy.PreflightOutcome.ElementLocatorInvalid };
        }

        private static BimDocumentIdentityPolicy.Evidence ActiveFileEvidence()
        {
            return BimDocumentIdentityPolicy.Capture(new BimDocumentIdentityPolicy.Readers(
                () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false),
                () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(true),
                () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false),
                () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false),
                () => BimDocumentIdentityPolicy.ReadResult<string?>.Success(@"C:\LOCAL.RVT"),
                () => BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath>.Success(new BimDocumentIdentityPolicy.CentralPath(BimDocumentIdentityPolicy.CentralPathKind.File, @"C:\MODELS\A.RVT")),
                () => BimDocumentIdentityPolicy.ReadResult<Guid>.Success(Guid.ParseExact("00112233-4455-6677-8899-aabbccddeeff", "D")),
                () => BimDocumentIdentityPolicy.ReadResult<Guid>.Unavailable(BimDocumentIdentityPolicy.UnavailableReason.UnsupportedClass)));
        }

        private static BimDocumentIdentityPolicy.Evidence ServerEvidence()
        {
            return BimDocumentIdentityPolicy.Capture(new BimDocumentIdentityPolicy.Readers(
                () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false),
                () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(true),
                () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false),
                () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false),
                () => BimDocumentIdentityPolicy.ReadResult<string?>.Success(@"C:\LOCAL.RVT"),
                () => BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath>.Success(new BimDocumentIdentityPolicy.CentralPath(BimDocumentIdentityPolicy.CentralPathKind.Server, null)),
                () => BimDocumentIdentityPolicy.ReadResult<Guid>.Unavailable(BimDocumentIdentityPolicy.UnavailableReason.UnsupportedClass),
                () => BimDocumentIdentityPolicy.ReadResult<Guid>.Success(Guid.ParseExact("00112233-4455-6677-8899-aabbccddeeff", "D"))));
        }

        private static BimDocumentIdentityPolicy.Evidence UnavailableFileEvidence()
        {
            return BimDocumentIdentityPolicy.Capture(new BimDocumentIdentityPolicy.Readers(
                () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false), () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(true),
                () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false), () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false),
                () => BimDocumentIdentityPolicy.ReadResult<string?>.Success(@"C:\LOCAL.RVT"),
                () => BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath>.Success(new BimDocumentIdentityPolicy.CentralPath(BimDocumentIdentityPolicy.CentralPathKind.File, @"C:\MODELS\A.RVT")),
                () => BimDocumentIdentityPolicy.ReadResult<Guid>.Unavailable(BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable),
                () => BimDocumentIdentityPolicy.ReadResult<Guid>.Unavailable(BimDocumentIdentityPolicy.UnavailableReason.UnsupportedClass)));
        }

        private static BimDocumentIdentityPolicy.Evidence UnknownEvidence()
        {
            return BimDocumentIdentityPolicy.Capture(new BimDocumentIdentityPolicy.Readers(
                () => BimDocumentIdentityPolicy.ReadResult<bool>.Unavailable(BimDocumentIdentityPolicy.UnavailableReason.DiscriminatorUnavailable),
                () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false), () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false), () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false),
                () => BimDocumentIdentityPolicy.ReadResult<string?>.Success(@"C:\LOCAL.RVT"),
                () => BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath>.Success(new BimDocumentIdentityPolicy.CentralPath(BimDocumentIdentityPolicy.CentralPathKind.File, @"C:\MODELS\A.RVT")),
                () => BimDocumentIdentityPolicy.ReadResult<Guid>.Success(Guid.NewGuid()), () => BimDocumentIdentityPolicy.ReadResult<Guid>.Success(Guid.NewGuid())));
        }

        private static BimDocumentIdentityPolicy.Evidence UnavailableServerEvidence()
        {
            return BimDocumentIdentityPolicy.Capture(new BimDocumentIdentityPolicy.Readers(
                () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false), () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(true),
                () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false), () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false),
                () => BimDocumentIdentityPolicy.ReadResult<string?>.Success(@"C:\LOCAL.RVT"),
                () => BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath>.Success(new BimDocumentIdentityPolicy.CentralPath(BimDocumentIdentityPolicy.CentralPathKind.Server, null)),
                () => BimDocumentIdentityPolicy.ReadResult<Guid>.Unavailable(BimDocumentIdentityPolicy.UnavailableReason.UnsupportedClass),
                () => BimDocumentIdentityPolicy.ReadResult<Guid>.Unavailable(BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable)));
        }

        private static BimDocumentIdentityPolicy.Claim LegacyClaim(string value)
        {
            return new BimDocumentIdentityPolicy.Claim("revit", null, BimDocumentKeySource.Unavailable, value, BimDocumentGuidSource.RevitPersistentGuid,
                false, null, null, null, null, null, "element-1", 1);
        }

        private static void AssertCalls(IReadOnlyDictionary<string, int> calls, IReadOnlyList<int> expected)
        {
            var names = new[] { "detached", "workshared", "cloud", "family", "path", "central", "creation", "server" };
            Assert.Equal(names.Length, expected.Count);
            for (var index = 0; index < names.Length; index++)
            {
                Assert.Equal(expected[index], calls.TryGetValue(names[index], out var count) ? count : 0);
            }
        }

        private static BimDocumentIdentityPolicy.Claim Claim(string? key, BimDocumentKeySource source, string? uniqueId = "element-1", int? elementId = 1)
        {
            return new BimDocumentIdentityPolicy.Claim("revit", key, source, null, BimDocumentGuidSource.Unavailable,
                false, null, null, null, null, null, uniqueId, elementId);
        }

        private sealed class ExpectedReadException : Exception { }
    }
}
