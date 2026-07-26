using System;

namespace Rook.Bim.Diagnostics
{
    public enum BimDiagnosticStage
    {
        CoreInitialize,
        ModuleResolve,
        ModuleLoad,
        ModuleActivate,
        ModuleMetadata,
        HandlerDeserialize,
        HandlerRuntime,
        HandlerSerialize,
        HandlerTerminal,
        RevitDispatchEnqueue,
        RevitDispatchExecute,
        RevitDocumentAcquire,
        RevitViewActiveGraphical,
        RevitDocumentCentralIsWorkshared,
        RevitDocumentCentralGuid,
        RevitDocumentTitle,
        RevitDocumentPath,
        RevitDocumentIsFamily,
        RevitDocumentOutputIsWorkshared,
        RevitDocumentIsModelInCloud,
        RevitDocumentIsDetached,
        RevitDocumentCentralModelPath,
        RevitDocumentModelPathEmpty,
        RevitDocumentModelPathServer,
        RevitDocumentModelPathCloud,
        RevitCategoriesSettings,
        RevitCategoriesCollection,
        RevitCategoriesIterator,
        RevitCategoriesMoveNext,
        RevitCategoriesCurrent,
        RevitCategoriesIteratorDispose,
        RevitCategoryId,
        RevitCategoryName,
        RevitCategoryBuiltIn,
        RevitCategoryType,
        SinkWriter
    }

    public enum BimDiagnosticOutcome
    {
        Start,
        Success,
        Failure
    }

    public enum BimDiagnosticRecordKind
    {
        Milestone,
        Failure,
        Terminal
    }

    public enum BimDiagnosticDetailCode
    {
        None,
        True,
        False,
        Null,
        NotApplicable,
        NotWorkshared,
        AlreadyInitialized,
        NoActiveView,
        Unsaved,
        File,
        Server,
        Cloud,
        Detached,
        Unknown,
        ProbeFailure,
        NotDisposable,
        Truncated,
        SerializationFailure,
        ExceptionCaptureFailed
    }

    public enum BimDiagnosticFailureImpact
    {
        None,
        Production,
        Auxiliary
    }

    public enum BimDiagnosticSinkState
    {
        Disabled,
        Starting,
        Ready,
        Degraded,
        FileLimitReached,
        Failed,
        Stopped
    }

    public enum BimDiagnosticSinkFailureCode
    {
        None,
        QueueFull,
        QueueContention,
        PriorityEviction,
        RecordInvalid,
        RecordOversize,
        FileLimitReached,
        DirectoryCreateFailure,
        FileOpenFailure,
        FileWriteFailure,
        FileFlushFailure,
        EncoderFailure
    }

    public readonly struct BimDiagnosticFields
    {
        public BimDiagnosticFields(
            BimDiagnosticDetailCode detailCode,
            long? itemIndex,
            BimDiagnosticFailureImpact failureImpact)
        {
            DetailCode = detailCode;
            ItemIndex = itemIndex;
            FailureImpact = failureImpact;
        }

        public BimDiagnosticDetailCode DetailCode { get; }

        public long? ItemIndex { get; }

        public BimDiagnosticFailureImpact FailureImpact { get; }

        public static BimDiagnosticFields None => default;
    }

    public sealed class BimDiagnosticContext
    {
        private static readonly BimDiagnosticContext DisabledContext =
            new BimDiagnosticContext(false, null, string.Empty, null);

        internal readonly BimDiagnosticOutcomeAccumulator? Accumulator;

        private BimDiagnosticContext(
            bool enabled,
            string? correlationId,
            string operation,
            BimDiagnosticOutcomeAccumulator? accumulator)
        {
            Enabled = enabled;
            CorrelationId = correlationId;
            Operation = operation;
            Accumulator = accumulator;
        }

        public bool Enabled { get; }

        public string? CorrelationId { get; }

        public string Operation { get; }

        public static BimDiagnosticContext Disabled
        {
            get { return DisabledContext; }
        }

        internal static BimDiagnosticContext CreateEnabled(string operation)
        {
            BimDiagnosticContracts.ValidateOperation(operation);
            return new BimDiagnosticContext(
                true,
                Guid.NewGuid().ToString("D"),
                operation,
                new BimDiagnosticOutcomeAccumulator());
        }
    }

    internal sealed class BimDiagnosticObservation
    {
        internal BimDiagnosticObservation(
            long sequence,
            BimDiagnosticStage stage,
            BimDiagnosticOutcome outcome,
            BimDiagnosticFields fields,
            string? exceptionTypeName,
            int? exceptionHResult)
        {
            if (sequence < 1)
            {
                throw new ArgumentOutOfRangeException(nameof(sequence));
            }

            BimDiagnosticContracts.ValidateStage(stage);
            BimDiagnosticContracts.ValidateOutcome(outcome);
            BimDiagnosticContracts.ValidateFields(fields);

            Sequence = sequence;
            Stage = stage;
            Outcome = outcome;
            Fields = fields;
            ExceptionTypeName = BimDiagnosticContracts.BoundExceptionTypeName(exceptionTypeName);
            ExceptionHResult = exceptionHResult;
        }

        internal long Sequence { get; }

        internal BimDiagnosticStage Stage { get; }

        internal BimDiagnosticOutcome Outcome { get; }

        internal BimDiagnosticFields Fields { get; }

        internal string? ExceptionTypeName { get; }

        internal int? ExceptionHResult { get; }
    }

    internal sealed class BimDiagnosticRequestSnapshot
    {
        internal BimDiagnosticRequestSnapshot(
            BimDiagnosticStage? lastStage,
            BimDiagnosticOutcome? lastOutcome,
            long? lastItemIndex,
            BimDiagnosticStage? firstFailureStage,
            string? firstFailureExceptionType,
            int? firstFailureHResult,
            long requestDroppedCount)
        {
            LastStage = lastStage;
            LastOutcome = lastOutcome;
            LastItemIndex = lastItemIndex;
            FirstFailureStage = firstFailureStage;
            FirstFailureExceptionType = BimDiagnosticContracts.BoundExceptionTypeName(firstFailureExceptionType);
            FirstFailureHResult = firstFailureHResult;
            RequestDroppedCount = requestDroppedCount;
        }

        internal BimDiagnosticStage? LastStage { get; }

        internal BimDiagnosticOutcome? LastOutcome { get; }

        internal long? LastItemIndex { get; }

        internal BimDiagnosticStage? FirstFailureStage { get; }

        internal string? FirstFailureExceptionType { get; }

        internal int? FirstFailureHResult { get; }

        internal long RequestDroppedCount { get; }

        internal bool TraceComplete
        {
            get { return RequestDroppedCount == 0; }
        }
    }

    internal sealed class BimDiagnosticStatusSnapshot
    {
        internal BimDiagnosticStatusSnapshot(
            bool enabled,
            BimDiagnosticSinkState sinkState,
            BimDiagnosticSinkFailureCode failureCode,
            long droppedCount,
            string? coreVersion,
            string? coreCommit,
            string? moduleVersion,
            string? moduleCommit)
        {
            BimDiagnosticContracts.ValidateSinkState(sinkState);
            BimDiagnosticContracts.ValidateSinkFailureCode(failureCode);

            Enabled = enabled;
            SinkState = sinkState;
            FailureCode = failureCode;
            DroppedCount = droppedCount < 0 ? 0 : droppedCount;
            CoreVersion = BimDiagnosticContracts.BoundProvenance(coreVersion);
            CoreCommit = BimDiagnosticContracts.BoundProvenance(coreCommit);
            ModuleVersion = BimDiagnosticContracts.BoundProvenance(moduleVersion);
            ModuleCommit = BimDiagnosticContracts.BoundProvenance(moduleCommit);
        }

        internal bool Enabled { get; }

        internal BimDiagnosticSinkState SinkState { get; }

        internal BimDiagnosticSinkFailureCode FailureCode { get; }

        internal long DroppedCount { get; }

        internal string CoreVersion { get; }

        internal string CoreCommit { get; }

        internal string ModuleVersion { get; }

        internal string ModuleCommit { get; }
    }

    internal static class BimDiagnosticContracts
    {
        internal const int MaximumOperationLength = 128;
        internal const int MaximumProvenanceLength = 128;
        internal const int MaximumExceptionTypeNameLength = 512;

        internal static void ValidateOperation(string operation)
        {
            if (string.IsNullOrWhiteSpace(operation) || operation.Length > MaximumOperationLength)
            {
                throw new ArgumentException(
                    "The diagnostic operation must be non-empty and at most 128 characters.",
                    nameof(operation));
            }
        }

        internal static string BoundProvenance(string? value)
        {
            return Bound(value, MaximumProvenanceLength);
        }

        internal static string? BoundExceptionTypeName(string? value)
        {
            return value == null ? null : Bound(value, MaximumExceptionTypeNameLength);
        }

        internal static string ToWire(BimDiagnosticSinkFailureCode code)
        {
            switch (code)
            {
                case BimDiagnosticSinkFailureCode.None:
                    return "none";
                case BimDiagnosticSinkFailureCode.QueueFull:
                    return "queue_full";
                case BimDiagnosticSinkFailureCode.QueueContention:
                    return "queue_contention";
                case BimDiagnosticSinkFailureCode.PriorityEviction:
                    return "priority_eviction";
                case BimDiagnosticSinkFailureCode.RecordInvalid:
                    return "record_invalid";
                case BimDiagnosticSinkFailureCode.RecordOversize:
                    return "record_oversize";
                case BimDiagnosticSinkFailureCode.FileLimitReached:
                    return "file_limit_reached";
                case BimDiagnosticSinkFailureCode.DirectoryCreateFailure:
                    return "directory_create_failure";
                case BimDiagnosticSinkFailureCode.FileOpenFailure:
                    return "file_open_failure";
                case BimDiagnosticSinkFailureCode.FileWriteFailure:
                    return "file_write_failure";
                case BimDiagnosticSinkFailureCode.FileFlushFailure:
                    return "file_flush_failure";
                case BimDiagnosticSinkFailureCode.EncoderFailure:
                    return "encoder_failure";
                default:
                    throw new ArgumentOutOfRangeException(nameof(code));
            }
        }

        internal static void ValidateStage(BimDiagnosticStage value)
        {
            ValidateDefined(value, nameof(value));
        }

        internal static void ValidateOutcome(BimDiagnosticOutcome value)
        {
            ValidateDefined(value, nameof(value));
        }

        internal static void ValidateRecordKind(BimDiagnosticRecordKind value)
        {
            ValidateDefined(value, nameof(value));
        }

        internal static void ValidateDetailCode(BimDiagnosticDetailCode value)
        {
            ValidateDefined(value, nameof(value));
        }

        internal static void ValidateFailureImpact(BimDiagnosticFailureImpact value)
        {
            ValidateDefined(value, nameof(value));
        }

        internal static void ValidateSinkState(BimDiagnosticSinkState value)
        {
            ValidateDefined(value, nameof(value));
        }

        internal static void ValidateSinkFailureCode(BimDiagnosticSinkFailureCode value)
        {
            ValidateDefined(value, nameof(value));
        }

        internal static void ValidateFields(BimDiagnosticFields fields)
        {
            ValidateDetailCode(fields.DetailCode);
            ValidateFailureImpact(fields.FailureImpact);
        }

        private static string Bound(string? value, int maximumLength)
        {
            if (value == null || value.Length == 0)
            {
                return string.Empty;
            }

            return value.Length <= maximumLength ? value : value.Substring(0, maximumLength);
        }

        private static void ValidateDefined<T>(T value, string parameterName)
            where T : struct, Enum
        {
            if (!Enum.IsDefined(typeof(T), value))
            {
                throw new ArgumentOutOfRangeException(parameterName);
            }
        }
    }
}
