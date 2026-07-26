using System;
using System.Threading;

namespace Rook.Bim
{
    internal sealed class BimDiagnosticObservationAdmission : IDisposable
    {
        private BimDiagnosticOutcomeAccumulator? owner;
        private bool observed;

        internal BimDiagnosticObservationAdmission(
            BimDiagnosticOutcomeAccumulator owner)
        {
            this.owner = owner;
        }

        internal void Observe(BimDiagnosticObservation observation)
        {
            if (observation == null)
            {
                throw new ArgumentNullException(nameof(observation));
            }

            var current = owner;
            if (current == null || observed)
            {
                throw new InvalidOperationException(
                    "The diagnostic observation admission is no longer active.");
            }

            current.ObserveAdmitted(observation);
            observed = true;
        }

        internal BimDiagnosticOutcome? Release()
        {
            var current = Interlocked.Exchange(ref owner, null);
            return current?.ReleaseObservationAdmission();
        }

        public void Dispose()
        {
            Release();
        }
    }

    internal struct BimDiagnosticDeferredCompletionState
    {
        internal bool Requested;
        internal bool Claimed;
        internal BimDiagnosticOutcome Outcome;
    }

    internal sealed class BimDiagnosticOutcomeAccumulator
    {
        private readonly object gate = new object();
        private bool sealedForObservations;
        private int activeObservationAdmissions;
        private BimDiagnosticDeferredCompletionState deferredCompletion;
        private bool hasLastObservation;
        private long lastObservationSequence;
        private BimDiagnosticStage lastStage;
        private BimDiagnosticOutcome lastOutcome;
        private bool hasLastIndexedObservation;
        private long lastIndexedObservationSequence;
        private long? lastItemIndex;
        private bool hasFirstProductionFailure;
        private long firstProductionFailureSequence;
        private BimDiagnosticStage firstFailureStage;
        private string? firstFailureExceptionType;
        private int? firstFailureHResult;
        private long requestDroppedCount;

        internal bool Observe(BimDiagnosticObservation observation)
        {
            if (observation == null)
            {
                throw new System.ArgumentNullException(nameof(observation));
            }

            lock (gate)
            {
                if (sealedForObservations)
                {
                    return false;
                }

                ApplyObservation(observation);
                return true;
            }
        }

        internal BimDiagnosticObservationAdmission? TryBeginObservation()
        {
            lock (gate)
            {
                if (sealedForObservations)
                {
                    return null;
                }

                var admission = new BimDiagnosticObservationAdmission(this);
                activeObservationAdmissions++;
                return admission;
            }
        }

        internal void ObserveAdmitted(BimDiagnosticObservation observation)
        {
            lock (gate)
            {
                ApplyObservation(observation);
            }
        }

        internal BimDiagnosticOutcome? ReleaseObservationAdmission()
        {
            lock (gate)
            {
                if (activeObservationAdmissions <= 0)
                {
                    return null;
                }

                activeObservationAdmissions--;
                if (activeObservationAdmissions == 0 &&
                    deferredCompletion.Requested &&
                    !deferredCompletion.Claimed)
                {
                    deferredCompletion.Claimed = true;
                    return deferredCompletion.Outcome;
                }

                return null;
            }
        }

        internal bool TryRequestCompletion(
            BimDiagnosticOutcome routeOutcome,
            out BimDiagnosticOutcome? terminalOutcome)
        {
            lock (gate)
            {
                terminalOutcome = null;
                if (sealedForObservations)
                {
                    return false;
                }

                BimDiagnosticContracts.ValidateOutcome(routeOutcome);
                if (routeOutcome == BimDiagnosticOutcome.Start)
                {
                    throw new ArgumentOutOfRangeException(nameof(routeOutcome));
                }

                sealedForObservations = true;
                deferredCompletion.Requested = true;
                deferredCompletion.Outcome = routeOutcome;
                if (activeObservationAdmissions == 0)
                {
                    deferredCompletion.Claimed = true;
                    terminalOutcome = routeOutcome;
                }

                return true;
            }
        }

        internal void RecordDrop(long increment = 1)
        {
            if (increment <= 0)
            {
                return;
            }

            lock (gate)
            {
                if (requestDroppedCount >= long.MaxValue - increment)
                {
                    requestDroppedCount = long.MaxValue;
                }
                else
                {
                    requestDroppedCount += increment;
                }
            }
        }

        internal BimDiagnosticRequestSnapshot Snapshot()
        {
            lock (gate)
            {
                return new BimDiagnosticRequestSnapshot(
                    hasLastObservation ? lastStage : (BimDiagnosticStage?)null,
                    hasLastObservation ? lastOutcome : (BimDiagnosticOutcome?)null,
                    hasLastIndexedObservation ? lastItemIndex : null,
                    hasFirstProductionFailure ? firstFailureStage : (BimDiagnosticStage?)null,
                    hasFirstProductionFailure ? firstFailureExceptionType : null,
                    hasFirstProductionFailure ? firstFailureHResult : null,
                requestDroppedCount);
            }
        }

        private void ApplyObservation(BimDiagnosticObservation observation)
        {
            if (!hasLastObservation || observation.Sequence > lastObservationSequence)
            {
                hasLastObservation = true;
                lastObservationSequence = observation.Sequence;
                lastStage = observation.Stage;
                lastOutcome = observation.Outcome;
            }

            if (observation.Fields.ItemIndex.HasValue &&
                (!hasLastIndexedObservation ||
                 observation.Sequence > lastIndexedObservationSequence))
            {
                hasLastIndexedObservation = true;
                lastIndexedObservationSequence = observation.Sequence;
                lastItemIndex = observation.Fields.ItemIndex;
            }

            if (observation.Outcome == BimDiagnosticOutcome.Failure &&
                observation.Fields.FailureImpact ==
                    BimDiagnosticFailureImpact.Production &&
                (!hasFirstProductionFailure ||
                 observation.Sequence < firstProductionFailureSequence))
            {
                hasFirstProductionFailure = true;
                firstProductionFailureSequence = observation.Sequence;
                firstFailureStage = observation.Stage;
                firstFailureExceptionType =
                    BimDiagnosticContracts.BoundExceptionTypeName(
                        observation.ExceptionTypeName);
                firstFailureHResult = observation.ExceptionHResult;
            }
        }
    }
}
