namespace Rook.Bim
{
    internal sealed class BimDiagnosticOutcomeAccumulator
    {
        private readonly object gate = new object();
        private bool sealedForObservations;
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

                if (!hasLastObservation || observation.Sequence > lastObservationSequence)
                {
                    hasLastObservation = true;
                    lastObservationSequence = observation.Sequence;
                    lastStage = observation.Stage;
                    lastOutcome = observation.Outcome;
                }

                if (observation.Fields.ItemIndex.HasValue &&
                    (!hasLastIndexedObservation || observation.Sequence > lastIndexedObservationSequence))
                {
                    hasLastIndexedObservation = true;
                    lastIndexedObservationSequence = observation.Sequence;
                    lastItemIndex = observation.Fields.ItemIndex;
                }

                if (observation.Outcome == BimDiagnosticOutcome.Failure &&
                    observation.Fields.FailureImpact == BimDiagnosticFailureImpact.Production &&
                    (!hasFirstProductionFailure || observation.Sequence < firstProductionFailureSequence))
                {
                    hasFirstProductionFailure = true;
                    firstProductionFailureSequence = observation.Sequence;
                    firstFailureStage = observation.Stage;
                    firstFailureExceptionType = BimDiagnosticContracts.BoundExceptionTypeName(observation.ExceptionTypeName);
                    firstFailureHResult = observation.ExceptionHResult;
                }

                return true;
            }
        }

        internal bool TrySeal()
        {
            lock (gate)
            {
                if (sealedForObservations)
                {
                    return false;
                }

                sealedForObservations = true;
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
    }
}
