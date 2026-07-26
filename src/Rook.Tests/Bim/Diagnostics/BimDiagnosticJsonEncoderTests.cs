using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim.Diagnostics
{
    public sealed class BimDiagnosticJsonEncoderTests
    {
        private static readonly string[] ExpectedKeys =
        {
            "schemaVersion", "recordKind", "sequence", "timestampUtc",
            "processId", "threadId", "correlationId", "operation", "stage",
            "outcome", "detailCode", "itemIndex", "failureImpact",
            "lastStage", "lastOutcome", "lastItemIndex", "firstFailureStage",
            "firstFailureExceptionType", "firstFailureHResult",
            "requestDroppedCount", "traceComplete", "coreVersion",
            "coreCommit", "moduleVersion", "moduleCommit", "exceptionType",
            "exceptionHResult", "exceptionStack", "innerExceptions", "truncated"
        };

        [Fact]
        public void Encode_ProducesOneParseablePhysicalLineWithFixedSchemaAndEscaping()
        {
            var controls = new string(
                Enumerable.Range(0, 32).Select(value => (char)value).ToArray());
            var stack = "quote=\" slash=\\" + controls + "\uD800X\uDC00";
            var expectedStack = "quote=\" slash=\\" + controls + "\uFFFDX\uFFFD";
            var exception = new BimDiagnosticExceptionInfo
            {
                TypeName = "Example.Outer",
                HResult = -2146233079,
                Stack = stack,
                InnerExceptions = new[]
                {
                    new BimDiagnosticExceptionInfo
                    {
                        TypeName = "Example.Inner",
                        HResult = 7,
                        Stack = "inner",
                        Truncated = false
                    }
                },
                Truncated = false
            };
            var record = CreateRecord(
                BimDiagnosticRecordKind.Failure,
                BimDiagnosticStage.RevitCategoryName,
                BimDiagnosticOutcome.Failure,
                new BimDiagnosticFields(
                    BimDiagnosticDetailCode.ProbeFailure,
                    17,
                    BimDiagnosticFailureImpact.Production),
                exception,
                "op\"\\\uD800Y\uDC00");

            var encoded = Assert.IsType<string>(
                BimDiagnosticJsonEncoder.Encode(record));

            Assert.EndsWith("\n", encoded, StringComparison.Ordinal);
            Assert.Equal(1, encoded.Count(character => character == '\n'));
            Assert.DoesNotContain('\r', encoded);
            using var document = JsonDocument.Parse(encoded);
            var root = document.RootElement;
            Assert.Equal(JsonValueKind.Object, root.ValueKind);
            Assert.Equal(ExpectedKeys,
                root.EnumerateObject().Select(property => property.Name).ToArray());
            Assert.Equal(1, root.GetProperty("schemaVersion").GetInt32());
            Assert.Equal(expectedStack,
                root.GetProperty("exceptionStack").GetString());
            Assert.Equal("op\"\\\uFFFDY\uFFFD",
                root.GetProperty("operation").GetString());
            Assert.Equal("Example.Inner",
                root.GetProperty("innerExceptions")[0]
                    .GetProperty("exceptionType").GetString());
        }

        [Theory]
        [MemberData(nameof(RecordKindCases))]
        public void ToWire_MapsEveryRecordKind(BimDiagnosticRecordKind value, string wire)
        {
            Assert.Equal(wire, BimDiagnosticJsonEncoder.ToWire(value));
        }

        [Theory]
        [MemberData(nameof(StageCases))]
        public void ToWire_MapsEveryStage(BimDiagnosticStage value, string wire)
        {
            Assert.Equal(wire, BimDiagnosticJsonEncoder.ToWire(value));
        }

        [Theory]
        [MemberData(nameof(OutcomeCases))]
        public void ToWire_MapsEveryOutcome(BimDiagnosticOutcome value, string wire)
        {
            Assert.Equal(wire, BimDiagnosticJsonEncoder.ToWire(value));
        }

        [Theory]
        [MemberData(nameof(DetailCodeCases))]
        public void ToWire_MapsEveryDetailCode(BimDiagnosticDetailCode value, string wire)
        {
            Assert.Equal(wire, BimDiagnosticJsonEncoder.ToWire(value));
        }

        [Theory]
        [MemberData(nameof(FailureImpactCases))]
        public void ToWire_MapsEveryFailureImpact(BimDiagnosticFailureImpact value, string wire)
        {
            Assert.Equal(wire, BimDiagnosticJsonEncoder.ToWire(value));
        }

        [Theory]
        [MemberData(nameof(SinkStateCases))]
        public void ToWire_MapsEverySinkState(BimDiagnosticSinkState value, string wire)
        {
            Assert.Equal(wire, BimDiagnosticJsonEncoder.ToWire(value));
        }

        [Theory]
        [MemberData(nameof(SinkFailureCases))]
        public void ToWire_MapsEverySinkFailureCode(
            BimDiagnosticSinkFailureCode value,
            string wire)
        {
            Assert.Equal(wire, BimDiagnosticJsonEncoder.ToWire(value));
        }

        [Fact]
        public void ToWire_RejectsEveryUndefinedEnumValue()
        {
            Assert.Throws<ArgumentOutOfRangeException>(() =>
                BimDiagnosticJsonEncoder.ToWire((BimDiagnosticRecordKind)999));
            Assert.Throws<ArgumentOutOfRangeException>(() =>
                BimDiagnosticJsonEncoder.ToWire((BimDiagnosticStage)999));
            Assert.Throws<ArgumentOutOfRangeException>(() =>
                BimDiagnosticJsonEncoder.ToWire((BimDiagnosticOutcome)999));
            Assert.Throws<ArgumentOutOfRangeException>(() =>
                BimDiagnosticJsonEncoder.ToWire((BimDiagnosticDetailCode)999));
            Assert.Throws<ArgumentOutOfRangeException>(() =>
                BimDiagnosticJsonEncoder.ToWire((BimDiagnosticFailureImpact)999));
            Assert.Throws<ArgumentOutOfRangeException>(() =>
                BimDiagnosticJsonEncoder.ToWire((BimDiagnosticSinkState)999));
            Assert.Throws<ArgumentOutOfRangeException>(() =>
                BimDiagnosticJsonEncoder.ToWire((BimDiagnosticSinkFailureCode)999));
        }

        [Fact]
        public void MappingCases_CoverEveryClosedEnumMember()
        {
            AssertCasesCoverEnum<BimDiagnosticRecordKind>(RecordKindCases);
            AssertCasesCoverEnum<BimDiagnosticStage>(StageCases);
            AssertCasesCoverEnum<BimDiagnosticOutcome>(OutcomeCases);
            AssertCasesCoverEnum<BimDiagnosticDetailCode>(DetailCodeCases);
            AssertCasesCoverEnum<BimDiagnosticFailureImpact>(FailureImpactCases);
            AssertCasesCoverEnum<BimDiagnosticSinkState>(SinkStateCases);
            AssertCasesCoverEnum<BimDiagnosticSinkFailureCode>(SinkFailureCases);
        }

        [Fact]
        public void Encode_ShrinksDeepestChildrenBeforeShallowChildrenOrRootStack()
        {
            var deepest = new BimDiagnosticExceptionInfo
            {
                TypeName = "Deepest",
                HResult = 3,
                Stack = new string('d', 8192)
            };
            var child = new BimDiagnosticExceptionInfo
            {
                TypeName = "Child",
                HResult = 2,
                Stack = new string('c', 4000),
                InnerExceptions = new[] { deepest }
            };
            var rootInfo = new BimDiagnosticExceptionInfo
            {
                TypeName = "Root",
                HResult = 1,
                Stack = new string('r', 4000),
                InnerExceptions = new[] { child }
            };
            var record = CreateRecord(exceptionInfo: rootInfo);

            var first = Assert.IsType<string>(BimDiagnosticJsonEncoder.Encode(record));
            var second = Assert.IsType<string>(BimDiagnosticJsonEncoder.Encode(record));

            Assert.Equal(first, second);
            Assert.True(Encoding.UTF8.GetByteCount(first) <= 16 * 1024);
            using var document = JsonDocument.Parse(first);
            var encodedRoot = document.RootElement;
            Assert.True(encodedRoot.GetProperty("truncated").GetBoolean());
            Assert.Equal(new string('r', 4000),
                encodedRoot.GetProperty("exceptionStack").GetString());
            var encodedChild = Assert.Single(
                encodedRoot.GetProperty("innerExceptions").EnumerateArray());
            Assert.Equal("Child",
                encodedChild.GetProperty("exceptionType").GetString());
            Assert.Empty(encodedChild.GetProperty("innerExceptions").EnumerateArray());
            Assert.Single(rootInfo.InnerExceptions);
            Assert.Single(rootInfo.InnerExceptions[0].InnerExceptions);
        }

        [Fact]
        public void Encode_HalvesEscapedRootStackUntilRecordFits()
        {
            var info = new BimDiagnosticExceptionInfo
            {
                TypeName = "Root",
                HResult = 1,
                Stack = new string('\u0001', 8192)
            };

            var encoded = Assert.IsType<string>(BimDiagnosticJsonEncoder.Encode(
                CreateRecord(exceptionInfo: info)));

            Assert.True(Encoding.UTF8.GetByteCount(encoded) <= 16 * 1024);
            using var document = JsonDocument.Parse(encoded);
            Assert.True(document.RootElement.GetProperty("truncated").GetBoolean());
            Assert.True(document.RootElement.GetProperty("exceptionStack")
                .GetString()?.Length < 8192);
            Assert.Equal(8192, info.Stack?.Length);
        }

        [Fact]
        public void Encode_DropsRecordWhenFixedMinimalFormCannotFit()
        {
            var record = CreateRecord(
                correlationId: new string('x', 20 * 1024));

            Assert.Null(BimDiagnosticJsonEncoder.Encode(record));
        }

        public static IEnumerable<object[]> RecordKindCases => Cases(
            (BimDiagnosticRecordKind.Milestone, "milestone"),
            (BimDiagnosticRecordKind.Failure, "failure"),
            (BimDiagnosticRecordKind.Terminal, "terminal"));

        public static IEnumerable<object[]> OutcomeCases => Cases(
            (BimDiagnosticOutcome.Start, "start"),
            (BimDiagnosticOutcome.Success, "success"),
            (BimDiagnosticOutcome.Failure, "failure"));

        public static IEnumerable<object[]> FailureImpactCases => Cases(
            (BimDiagnosticFailureImpact.None, "none"),
            (BimDiagnosticFailureImpact.Production, "production"),
            (BimDiagnosticFailureImpact.Auxiliary, "auxiliary"));

        public static IEnumerable<object[]> SinkStateCases => Cases(
            (BimDiagnosticSinkState.Disabled, "disabled"),
            (BimDiagnosticSinkState.Starting, "starting"),
            (BimDiagnosticSinkState.Ready, "ready"),
            (BimDiagnosticSinkState.Degraded, "degraded"),
            (BimDiagnosticSinkState.FileLimitReached, "file_limit_reached"),
            (BimDiagnosticSinkState.Failed, "failed"),
            (BimDiagnosticSinkState.Stopped, "stopped"));

        public static IEnumerable<object[]> SinkFailureCases => Cases(
            (BimDiagnosticSinkFailureCode.None, "none"),
            (BimDiagnosticSinkFailureCode.QueueFull, "queue_full"),
            (BimDiagnosticSinkFailureCode.QueueContention, "queue_contention"),
            (BimDiagnosticSinkFailureCode.PriorityEviction, "priority_eviction"),
            (BimDiagnosticSinkFailureCode.RecordInvalid, "record_invalid"),
            (BimDiagnosticSinkFailureCode.RecordOversize, "record_oversize"),
            (BimDiagnosticSinkFailureCode.FileLimitReached, "file_limit_reached"),
            (BimDiagnosticSinkFailureCode.DirectoryCreateFailure, "directory_create_failure"),
            (BimDiagnosticSinkFailureCode.FileOpenFailure, "file_open_failure"),
            (BimDiagnosticSinkFailureCode.FileWriteFailure, "file_write_failure"),
            (BimDiagnosticSinkFailureCode.FileFlushFailure, "file_flush_failure"),
            (BimDiagnosticSinkFailureCode.EncoderFailure, "encoder_failure"));

        public static IEnumerable<object[]> DetailCodeCases => Cases(
            (BimDiagnosticDetailCode.None, "none"),
            (BimDiagnosticDetailCode.True, "true"),
            (BimDiagnosticDetailCode.False, "false"),
            (BimDiagnosticDetailCode.Null, "null"),
            (BimDiagnosticDetailCode.NotApplicable, "not_applicable"),
            (BimDiagnosticDetailCode.NotWorkshared, "not_workshared"),
            (BimDiagnosticDetailCode.AlreadyInitialized, "already_initialized"),
            (BimDiagnosticDetailCode.NoActiveView, "no_active_view"),
            (BimDiagnosticDetailCode.Unsaved, "unsaved"),
            (BimDiagnosticDetailCode.File, "file"),
            (BimDiagnosticDetailCode.Server, "server"),
            (BimDiagnosticDetailCode.Cloud, "cloud"),
            (BimDiagnosticDetailCode.Detached, "detached"),
            (BimDiagnosticDetailCode.Unknown, "unknown"),
            (BimDiagnosticDetailCode.ProbeFailure, "probe_failure"),
            (BimDiagnosticDetailCode.NotDisposable, "not_disposable"),
            (BimDiagnosticDetailCode.Truncated, "truncated"),
            (BimDiagnosticDetailCode.SerializationFailure, "serialization_failure"),
            (BimDiagnosticDetailCode.ExceptionCaptureFailed, "exception_capture_failed"));

        public static IEnumerable<object[]> StageCases => Cases(
            (BimDiagnosticStage.CoreInitialize, "core.initialize"),
            (BimDiagnosticStage.ModuleResolve, "module.resolve"),
            (BimDiagnosticStage.ModuleLoad, "module.load"),
            (BimDiagnosticStage.ModuleActivate, "module.activate"),
            (BimDiagnosticStage.ModuleMetadata, "module.metadata"),
            (BimDiagnosticStage.HandlerDeserialize, "handler.deserialize"),
            (BimDiagnosticStage.HandlerRuntime, "handler.runtime"),
            (BimDiagnosticStage.HandlerSerialize, "handler.serialize"),
            (BimDiagnosticStage.HandlerTerminal, "handler.terminal"),
            (BimDiagnosticStage.RevitDispatchEnqueue, "revit.dispatch.enqueue"),
            (BimDiagnosticStage.RevitDispatchExecute, "revit.dispatch.execute"),
            (BimDiagnosticStage.RevitDocumentAcquire, "revit.document.acquire"),
            (BimDiagnosticStage.RevitViewActiveGraphical, "revit.view.active_graphical"),
            (BimDiagnosticStage.RevitDocumentCentralIsWorkshared, "revit.document.central_is_workshared"),
            (BimDiagnosticStage.RevitDocumentCentralGuid, "revit.document.central_guid"),
            (BimDiagnosticStage.RevitDocumentTitle, "revit.document.title"),
            (BimDiagnosticStage.RevitDocumentPath, "revit.document.path"),
            (BimDiagnosticStage.RevitDocumentIsFamily, "revit.document.is_family"),
            (BimDiagnosticStage.RevitDocumentOutputIsWorkshared, "revit.document.output_is_workshared"),
            (BimDiagnosticStage.RevitDocumentIsModelInCloud, "revit.document.is_model_in_cloud"),
            (BimDiagnosticStage.RevitDocumentIsDetached, "revit.document.is_detached"),
            (BimDiagnosticStage.RevitDocumentCentralModelPath, "revit.document.central_model_path"),
            (BimDiagnosticStage.RevitDocumentModelPathEmpty, "revit.document.model_path_empty"),
            (BimDiagnosticStage.RevitDocumentModelPathServer, "revit.document.model_path_server"),
            (BimDiagnosticStage.RevitDocumentModelPathCloud, "revit.document.model_path_cloud"),
            (BimDiagnosticStage.RevitCategoriesSettings, "revit.categories.settings"),
            (BimDiagnosticStage.RevitCategoriesCollection, "revit.categories.collection"),
            (BimDiagnosticStage.RevitCategoriesIterator, "revit.categories.iterator"),
            (BimDiagnosticStage.RevitCategoriesMoveNext, "revit.categories.move_next"),
            (BimDiagnosticStage.RevitCategoriesCurrent, "revit.categories.current"),
            (BimDiagnosticStage.RevitCategoriesIteratorDispose, "revit.categories.iterator_dispose"),
            (BimDiagnosticStage.RevitCategoryId, "revit.category.id"),
            (BimDiagnosticStage.RevitCategoryName, "revit.category.name"),
            (BimDiagnosticStage.RevitCategoryBuiltIn, "revit.category.built_in"),
            (BimDiagnosticStage.RevitCategoryType, "revit.category.type"),
            (BimDiagnosticStage.SinkWriter, "sink.writer"));

        private static BimDiagnosticRecord CreateRecord(
            BimDiagnosticRecordKind kind = BimDiagnosticRecordKind.Failure,
            BimDiagnosticStage stage = BimDiagnosticStage.HandlerSerialize,
            BimDiagnosticOutcome outcome = BimDiagnosticOutcome.Failure,
            BimDiagnosticFields fields = default,
            BimDiagnosticExceptionInfo? exceptionInfo = null,
            string operation = "status",
            string? correlationId = "11111111-2222-3333-4444-555555555555")
        {
            var accumulator = new BimDiagnosticOutcomeAccumulator();
            var envelope = new BimDiagnosticEnvelope(
                kind,
                42,
                new DateTime(2026, 7, 25, 12, 34, 56, DateTimeKind.Utc),
                100,
                7,
                correlationId,
                operation,
                stage,
                outcome,
                fields,
                exceptionInfo,
                accumulator);
            return new BimDiagnosticRecord(
                envelope,
                accumulator.Snapshot(),
                "1.5.16",
                "abc123",
                "unavailable",
                "unavailable");
        }

        private static IEnumerable<object[]> Cases<T>(
            params (T Value, string Wire)[] cases)
        {
            return cases.Select(item => new object[] { item.Value!, item.Wire });
        }

        private static void AssertCasesCoverEnum<T>(
            IEnumerable<object[]> cases)
            where T : struct, Enum
        {
            Assert.Equal(
                Enum.GetValues(typeof(T)).Cast<T>().OrderBy(value => value),
                cases.Select(item => (T)item[0]).OrderBy(value => value));
        }
    }
}
