using System;
using System.Linq;
using Rook.Bim;
using Rook.Tests.Bim;
using Xunit;

namespace Rook.Tests.Bim.Diagnostics
{
    [Collection(RookBimRuntimeRegistryCollection.Name)]
    public sealed class BimDiagnosticPersistencePolicyTests
    {
        [Fact]
        public void CategorySuccessesRemainSparseWhileEveryObservationUpdatesTheRequest()
        {
            using var scope = TestDiagnostics.EnabledScope("list_categories");
            var stages = new[]
            {
                BimDiagnosticStage.RevitCategoriesMoveNext,
                BimDiagnosticStage.RevitCategoriesCurrent,
                BimDiagnosticStage.RevitCategoryId,
                BimDiagnosticStage.RevitCategoryName,
                BimDiagnosticStage.RevitCategoryBuiltIn,
                BimDiagnosticStage.RevitCategoryType
            };

            for (var index = 0; index < 500; index++)
            {
                foreach (var stage in stages)
                {
                    var fields = new BimDiagnosticFields(
                        BimDiagnosticDetailCode.None,
                        index,
                        BimDiagnosticFailureImpact.Production);
                    scope.Session.Observe(
                        scope.Context, stage, BimDiagnosticOutcome.Start, fields);
                    scope.Session.Observe(
                        scope.Context, stage, BimDiagnosticOutcome.Success, fields);
                }
            }

            Assert.Empty(scope.Sink.Envelopes);
            var snapshot = TestDiagnostics.Snapshot(scope.Context);
            Assert.Equal(499, snapshot.LastItemIndex);
            Assert.Equal(BimDiagnosticStage.RevitCategoryType, snapshot.LastStage);
            Assert.Equal(BimDiagnosticOutcome.Success, snapshot.LastOutcome);
        }

        [Fact]
        public void FailureMilestonesAndExactlyOneTerminalArePersisted()
        {
            using var scope = TestDiagnostics.EnabledScope("list_categories");

            scope.Session.Observe(
                scope.Context,
                BimDiagnosticStage.HandlerRuntime,
                BimDiagnosticOutcome.Start,
                BimDiagnosticFields.None);
            scope.Session.Observe(
                scope.Context,
                BimDiagnosticStage.HandlerRuntime,
                BimDiagnosticOutcome.Success,
                BimDiagnosticFields.None);
            scope.Session.ObserveException(
                scope.Context,
                BimDiagnosticStage.RevitCategoryName,
                new InvalidOperationException("private"),
                new BimDiagnosticFields(
                    BimDiagnosticDetailCode.None,
                    23,
                    BimDiagnosticFailureImpact.Production));

            scope.Session.CompleteRequest(scope.Context, BimDiagnosticOutcome.Success);
            scope.Session.CompleteRequest(scope.Context, BimDiagnosticOutcome.Failure);
            scope.Session.Observe(
                scope.Context,
                BimDiagnosticStage.HandlerSerialize,
                BimDiagnosticOutcome.Success,
                BimDiagnosticFields.None);

            Assert.Equal(4, scope.Sink.Envelopes.Count);
            Assert.Equal(2, scope.Sink.Envelopes.Count(envelope =>
                envelope.Kind == BimDiagnosticRecordKind.Milestone));
            Assert.Single(scope.Sink.Envelopes, envelope =>
                envelope.Kind == BimDiagnosticRecordKind.Failure);
            var terminal = Assert.Single(scope.Sink.Envelopes, envelope =>
                envelope.Kind == BimDiagnosticRecordKind.Terminal);
            Assert.Equal(BimDiagnosticStage.HandlerTerminal, terminal.Stage);
            Assert.Equal(BimDiagnosticOutcome.Success, terminal.Outcome);
            Assert.Same(scope.Context.Accumulator, terminal.Accumulator);

            var snapshot = TestDiagnostics.Snapshot(scope.Context);
            Assert.Equal(BimDiagnosticStage.RevitCategoryName,
                snapshot.FirstFailureStage);
            Assert.Equal(BimDiagnosticStage.RevitCategoryName, snapshot.LastStage);
            Assert.Equal(23, snapshot.LastItemIndex);
        }

        [Theory]
        [InlineData(BimDiagnosticStage.CoreInitialize)]
        [InlineData(BimDiagnosticStage.ModuleResolve)]
        [InlineData(BimDiagnosticStage.ModuleLoad)]
        [InlineData(BimDiagnosticStage.ModuleActivate)]
        [InlineData(BimDiagnosticStage.ModuleMetadata)]
        [InlineData(BimDiagnosticStage.HandlerDeserialize)]
        [InlineData(BimDiagnosticStage.HandlerRuntime)]
        [InlineData(BimDiagnosticStage.HandlerSerialize)]
        [InlineData(BimDiagnosticStage.RevitDispatchEnqueue)]
        [InlineData(BimDiagnosticStage.RevitDispatchExecute)]
        [InlineData(BimDiagnosticStage.RevitDocumentAcquire)]
        public void FixedCoarseStage_PersistsStartAndSuccess(BimDiagnosticStage stage)
        {
            using var scope = TestDiagnostics.EnabledScope("status");

            scope.Session.Observe(
                scope.Context, stage, BimDiagnosticOutcome.Start,
                BimDiagnosticFields.None);
            scope.Session.Observe(
                scope.Context, stage, BimDiagnosticOutcome.Success,
                BimDiagnosticFields.None);

            Assert.Equal(2, scope.Sink.Envelopes.Count);
            Assert.All(scope.Sink.Envelopes, envelope =>
                Assert.Equal(BimDiagnosticRecordKind.Milestone, envelope.Kind));
        }
    }
}
