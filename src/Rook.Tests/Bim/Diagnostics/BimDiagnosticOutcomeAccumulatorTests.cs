using System;
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim.Diagnostics
{
    public sealed class BimDiagnosticOutcomeAccumulatorTests
    {
        [Fact]
        public void Snapshot_UsesSequenceForFirstFailureLastStageAndLastIndexedItem()
        {
            var state = new BimDiagnosticOutcomeAccumulator();
            state.Observe(Failure(40, BimDiagnosticStage.RevitCategoryName, 9,
                BimDiagnosticFailureImpact.Production, typeof(InvalidOperationException), -3));
            state.Observe(Success(50, BimDiagnosticStage.HandlerSerialize));
            state.Observe(Failure(20, BimDiagnosticStage.RevitDocumentCentralGuid, 3,
                BimDiagnosticFailureImpact.Production, typeof(Exception), -1));
            state.Observe(Failure(10, BimDiagnosticStage.RevitDocumentCentralModelPath, null,
                BimDiagnosticFailureImpact.Auxiliary, typeof(Exception), -2));

            var result = state.Snapshot();
            Assert.Equal(BimDiagnosticStage.RevitDocumentCentralGuid, result.FirstFailureStage);
            Assert.Equal(BimDiagnosticStage.HandlerSerialize, result.LastStage);
            Assert.Equal(BimDiagnosticOutcome.Success, result.LastOutcome);
            Assert.Equal(9, result.LastItemIndex);
        }

        [Fact]
        public void Completion_RejectsFurtherObservationsWhileDelayedDropsRemainTrackedAndSaturate()
        {
            var state = new BimDiagnosticOutcomeAccumulator();

            Assert.True(state.TryRequestCompletion(
                BimDiagnosticOutcome.Success, out var terminalOutcome));
            Assert.Equal(BimDiagnosticOutcome.Success, terminalOutcome);
            Assert.False(state.TryRequestCompletion(
                BimDiagnosticOutcome.Failure, out terminalOutcome));
            Assert.Null(terminalOutcome);
            Assert.False(state.Observe(Success(1, BimDiagnosticStage.HandlerRuntime)));

            state.RecordDrop(long.MaxValue - 1);
            state.RecordDrop();
            state.RecordDrop();

            var result = state.Snapshot();
            Assert.Equal(long.MaxValue, result.RequestDroppedCount);
            Assert.False(result.TraceComplete);
        }

        private static BimDiagnosticObservation Failure(
            long sequence,
            BimDiagnosticStage stage,
            long? index,
            BimDiagnosticFailureImpact impact,
            Type type,
            int hresult)
        {
            return new BimDiagnosticObservation(
                sequence,
                stage,
                BimDiagnosticOutcome.Failure,
                new BimDiagnosticFields(BimDiagnosticDetailCode.None, index, impact),
                type.FullName,
                hresult);
        }

        private static BimDiagnosticObservation Success(long sequence, BimDiagnosticStage stage)
        {
            return new BimDiagnosticObservation(
                sequence,
                stage,
                BimDiagnosticOutcome.Success,
                BimDiagnosticFields.None,
                null,
                null);
        }
    }
}
