using System;
using System.Diagnostics;
using System.Threading;

namespace Rook.Bim
{
    internal interface IBimDiagnosticEnvelopeSink
    {
        bool TryEnqueue(BimDiagnosticEnvelope envelope);
    }

    internal sealed class BimDiagnosticEnvelope
    {
        internal BimDiagnosticEnvelope(
            BimDiagnosticRecordKind kind,
            long sequence,
            DateTime timestampUtc,
            int processId,
            int threadId,
            string? correlationId,
            string operation,
            BimDiagnosticStage stage,
            BimDiagnosticOutcome outcome,
            BimDiagnosticFields fields,
            BimDiagnosticExceptionInfo? exceptionInfo,
            BimDiagnosticOutcomeAccumulator? accumulator)
        {
            BimDiagnosticContracts.ValidateRecordKind(kind);
            BimDiagnosticContracts.ValidateStage(stage);
            BimDiagnosticContracts.ValidateOutcome(outcome);
            BimDiagnosticContracts.ValidateFields(fields);

            Kind = kind;
            Sequence = sequence;
            TimestampUtc = timestampUtc;
            ProcessId = processId;
            ThreadId = threadId;
            CorrelationId = correlationId;
            Operation = operation;
            Stage = stage;
            Outcome = outcome;
            Fields = fields;
            ExceptionInfo = exceptionInfo;
            Accumulator = accumulator;
        }

        internal BimDiagnosticRecordKind Kind { get; }

        internal long Sequence { get; }

        internal DateTime TimestampUtc { get; }

        internal int ProcessId { get; }

        internal int ThreadId { get; }

        internal string? CorrelationId { get; }

        internal string Operation { get; }

        internal BimDiagnosticStage Stage { get; }

        internal BimDiagnosticOutcome Outcome { get; }

        internal BimDiagnosticFields Fields { get; }

        internal BimDiagnosticExceptionInfo? ExceptionInfo { get; }

        internal string? ExceptionTypeName
        {
            get { return ExceptionInfo?.TypeName; }
        }

        internal int? ExceptionHResult
        {
            get { return ExceptionInfo == null ? (int?)null : ExceptionInfo.HResult; }
        }

        internal BimDiagnosticOutcomeAccumulator? Accumulator { get; }
    }

    internal sealed class BimDiagnosticRecord
    {
        internal BimDiagnosticRecord(
            BimDiagnosticEnvelope envelope,
            BimDiagnosticRequestSnapshot snapshot,
            string? coreVersion,
            string? coreCommit,
            string? moduleVersion,
            string? moduleCommit)
        {
            if (envelope == null)
            {
                throw new ArgumentNullException(nameof(envelope));
            }

            if (snapshot == null)
            {
                throw new ArgumentNullException(nameof(snapshot));
            }

            Kind = envelope.Kind;
            Sequence = envelope.Sequence;
            TimestampUtc = envelope.TimestampUtc;
            ProcessId = envelope.ProcessId;
            ThreadId = envelope.ThreadId;
            CorrelationId = envelope.CorrelationId;
            Operation = envelope.Operation;
            Stage = envelope.Stage;
            Outcome = envelope.Outcome;
            Fields = envelope.Fields;
            var terminal = envelope.Kind == BimDiagnosticRecordKind.Terminal;
            LastStage = terminal ? snapshot.LastStage : null;
            LastOutcome = terminal ? snapshot.LastOutcome : null;
            LastItemIndex = terminal ? snapshot.LastItemIndex : null;
            FirstFailureStage = terminal ? snapshot.FirstFailureStage : null;
            FirstFailureExceptionType = terminal
                ? snapshot.FirstFailureExceptionType
                : null;
            FirstFailureHResult = terminal ? snapshot.FirstFailureHResult : null;
            RequestDroppedCount = snapshot.RequestDroppedCount;
            CoreVersion = BimDiagnosticContracts.BoundProvenance(coreVersion);
            CoreCommit = BimDiagnosticContracts.BoundProvenance(coreCommit);
            ModuleVersion = BimDiagnosticContracts.BoundProvenance(moduleVersion);
            ModuleCommit = BimDiagnosticContracts.BoundProvenance(moduleCommit);
            ExceptionInfo = envelope.ExceptionInfo;
        }

        internal BimDiagnosticRecordKind Kind { get; }
        internal long Sequence { get; }
        internal DateTime TimestampUtc { get; }
        internal int ProcessId { get; }
        internal int ThreadId { get; }
        internal string? CorrelationId { get; }
        internal string Operation { get; }
        internal BimDiagnosticStage Stage { get; }
        internal BimDiagnosticOutcome Outcome { get; }
        internal BimDiagnosticFields Fields { get; }
        internal BimDiagnosticStage? LastStage { get; }
        internal BimDiagnosticOutcome? LastOutcome { get; }
        internal long? LastItemIndex { get; }
        internal BimDiagnosticStage? FirstFailureStage { get; }
        internal string? FirstFailureExceptionType { get; }
        internal int? FirstFailureHResult { get; }
        internal long RequestDroppedCount { get; }
        internal bool TraceComplete { get { return RequestDroppedCount == 0; } }
        internal string CoreVersion { get; }
        internal string CoreCommit { get; }
        internal string ModuleVersion { get; }
        internal string ModuleCommit { get; }
        internal BimDiagnosticExceptionInfo? ExceptionInfo { get; }
        internal string? ExceptionTypeName { get { return ExceptionInfo?.TypeName; } }
        internal int? ExceptionHResult
        {
            get { return ExceptionInfo == null ? (int?)null : ExceptionInfo.HResult; }
        }
    }

    internal sealed class BimDiagnosticSession
    {
        private static long nextSequence;
        private readonly bool enabled;
        private readonly IBimDiagnosticEnvelopeSink? sink;

        internal BimDiagnosticSession(bool enabled, IBimDiagnosticEnvelopeSink? sink)
        {
            this.enabled = enabled;
            this.sink = sink;
        }

        internal BimDiagnosticContext CreateContext(string operation)
        {
            return enabled
                ? BimDiagnosticContext.CreateEnabled(operation)
                : BimDiagnosticContext.Disabled;
        }

        internal void Observe(
            BimDiagnosticContext context,
            BimDiagnosticStage stage,
            BimDiagnosticOutcome outcome,
            BimDiagnosticFields fields)
        {
            if (!TryGetAccumulator(context, out var accumulator))
            {
                return;
            }

            var sequence = NextSequence();
            var timestampUtc = DateTime.UtcNow;
            var observation = new BimDiagnosticObservation(
                sequence,
                stage,
                outcome,
                fields,
                null,
                null);
            if (!accumulator.Observe(observation))
            {
                return;
            }

            if (outcome == BimDiagnosticOutcome.Failure)
            {
                Enqueue(context, accumulator, BimDiagnosticRecordKind.Failure,
                    observation, timestampUtc);
            }
            else if (IsPersistentMilestone(stage))
            {
                Enqueue(context, accumulator, BimDiagnosticRecordKind.Milestone,
                    observation, timestampUtc);
            }
        }

        internal void ObserveException(
            BimDiagnosticContext context,
            BimDiagnosticStage stage,
            Exception exception,
            BimDiagnosticFields fields)
        {
            if (exception == null)
            {
                throw new ArgumentNullException(nameof(exception));
            }

            if (!TryGetAccumulator(context, out var accumulator))
            {
                return;
            }

            using (var admission = accumulator.TryBeginObservation())
            {
                if (admission == null)
                {
                    return;
                }

                var capture = BimDiagnosticExceptionCapture.Capture(exception);
                var root = capture.Root;
                var effectiveFields = capture.DetailCode ==
                    BimDiagnosticDetailCode.ExceptionCaptureFailed
                    ? new BimDiagnosticFields(
                        BimDiagnosticDetailCode.ExceptionCaptureFailed,
                        fields.ItemIndex,
                        fields.FailureImpact)
                    : fields;
                var sequence = NextSequence();
                var timestampUtc = DateTime.UtcNow;
                var observation = new BimDiagnosticObservation(
                    sequence,
                    stage,
                    BimDiagnosticOutcome.Failure,
                    effectiveFields,
                    root?.TypeName,
                    root == null ? (int?)null : root.HResult);
                admission.Observe(observation);

                Enqueue(context, accumulator, BimDiagnosticRecordKind.Failure,
                    observation, timestampUtc, root);
            }
        }

        internal void CompleteRequest(
            BimDiagnosticContext context,
            BimDiagnosticOutcome routeOutcome)
        {
            if (!TryGetAccumulator(context, out var accumulator) ||
                !accumulator.TrySeal())
            {
                return;
            }

            BimDiagnosticContracts.ValidateOutcome(routeOutcome);
            if (routeOutcome == BimDiagnosticOutcome.Start)
            {
                throw new ArgumentOutOfRangeException(nameof(routeOutcome));
            }

            var sequence = NextSequence();
            var envelope = new BimDiagnosticEnvelope(
                BimDiagnosticRecordKind.Terminal,
                sequence,
                DateTime.UtcNow,
                CurrentProcessId(),
                Thread.CurrentThread.ManagedThreadId,
                context.CorrelationId,
                context.Operation,
                BimDiagnosticStage.HandlerTerminal,
                routeOutcome,
                BimDiagnosticFields.None,
                null,
                accumulator);
            Offer(envelope, accumulator);
        }

        private static bool TryGetAccumulator(
            BimDiagnosticContext context,
            out BimDiagnosticOutcomeAccumulator accumulator)
        {
            if (context == null)
            {
                throw new ArgumentNullException(nameof(context));
            }

            if (!context.Enabled || context.Accumulator == null)
            {
                accumulator = null!;
                return false;
            }

            accumulator = context.Accumulator;
            return true;
        }

        private void Enqueue(
            BimDiagnosticContext context,
            BimDiagnosticOutcomeAccumulator accumulator,
            BimDiagnosticRecordKind kind,
            BimDiagnosticObservation observation,
            DateTime timestampUtc,
            BimDiagnosticExceptionInfo? exceptionInfo = null)
        {
            var envelope = new BimDiagnosticEnvelope(
                kind,
                observation.Sequence,
                timestampUtc,
                CurrentProcessId(),
                Thread.CurrentThread.ManagedThreadId,
                context.CorrelationId,
                context.Operation,
                observation.Stage,
                observation.Outcome,
                observation.Fields,
                exceptionInfo,
                accumulator);
            Offer(envelope, accumulator);
        }

        private void Offer(
            BimDiagnosticEnvelope envelope,
            BimDiagnosticOutcomeAccumulator accumulator)
        {
            if (sink == null || !sink.TryEnqueue(envelope))
            {
                accumulator.RecordDrop();
            }
        }

        private static long NextSequence()
        {
            return Interlocked.Increment(ref nextSequence);
        }

        private static int CurrentProcessId()
        {
            using (var process = Process.GetCurrentProcess())
            {
                return process.Id;
            }
        }

        private static bool IsPersistentMilestone(BimDiagnosticStage stage)
        {
            switch (stage)
            {
                case BimDiagnosticStage.CoreInitialize:
                case BimDiagnosticStage.ModuleResolve:
                case BimDiagnosticStage.ModuleLoad:
                case BimDiagnosticStage.ModuleActivate:
                case BimDiagnosticStage.ModuleMetadata:
                case BimDiagnosticStage.HandlerDeserialize:
                case BimDiagnosticStage.HandlerRuntime:
                case BimDiagnosticStage.HandlerSerialize:
                case BimDiagnosticStage.RevitDispatchEnqueue:
                case BimDiagnosticStage.RevitDispatchExecute:
                case BimDiagnosticStage.RevitDocumentAcquire:
                    return true;
                default:
                    return false;
            }
        }
    }
}
