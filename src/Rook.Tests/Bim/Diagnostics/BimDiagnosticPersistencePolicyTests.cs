using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
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
                    BimDiagnostics.Observe(
                        scope.Context, stage, BimDiagnosticOutcome.Start, fields);
                    BimDiagnostics.Observe(
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
        public void Facade_RoutesFailureMilestonesExactlyOneTerminalAndRejectsPostSealObservation()
        {
            using var scope = TestDiagnostics.EnabledScope("list_categories");

            BimDiagnostics.Observe(
                scope.Context,
                BimDiagnosticStage.HandlerRuntime,
                BimDiagnosticOutcome.Start,
                BimDiagnosticFields.None);
            BimDiagnostics.Observe(
                scope.Context,
                BimDiagnosticStage.HandlerRuntime,
                BimDiagnosticOutcome.Success,
                BimDiagnosticFields.None);
            BimDiagnostics.ObserveException(
                scope.Context,
                BimDiagnosticStage.RevitCategoryName,
                new InvalidOperationException("private"),
                new BimDiagnosticFields(
                    BimDiagnosticDetailCode.None,
                    23,
                    BimDiagnosticFailureImpact.Production));

            BimDiagnostics.CompleteRequest(scope.Context, BimDiagnosticOutcome.Success);
            BimDiagnostics.CompleteRequest(scope.Context, BimDiagnosticOutcome.Failure);
            BimDiagnostics.Observe(
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

        [Fact]
        public void EveryStage_HasAnExplicitSparsePolicyAndEveryFailureIsPersisted()
        {
            using var scope = TestDiagnostics.EnabledScope("status");
            var policy = new Dictionary<BimDiagnosticStage, bool>
            {
                [BimDiagnosticStage.CoreInitialize] = true,
                [BimDiagnosticStage.ModuleResolve] = true,
                [BimDiagnosticStage.ModuleLoad] = true,
                [BimDiagnosticStage.ModuleActivate] = true,
                [BimDiagnosticStage.ModuleMetadata] = true,
                [BimDiagnosticStage.HandlerDeserialize] = true,
                [BimDiagnosticStage.HandlerRuntime] = true,
                [BimDiagnosticStage.HandlerSerialize] = true,
                [BimDiagnosticStage.HandlerTerminal] = false,
                [BimDiagnosticStage.RevitDispatchEnqueue] = true,
                [BimDiagnosticStage.RevitDispatchExecute] = true,
                [BimDiagnosticStage.RevitDocumentAcquire] = true,
                [BimDiagnosticStage.RevitViewActiveGraphical] = false,
                [BimDiagnosticStage.RevitDocumentCentralIsWorkshared] = false,
                [BimDiagnosticStage.RevitDocumentCentralGuid] = false,
                [BimDiagnosticStage.RevitDocumentTitle] = false,
                [BimDiagnosticStage.RevitDocumentPath] = false,
                [BimDiagnosticStage.RevitDocumentIsFamily] = false,
                [BimDiagnosticStage.RevitDocumentOutputIsWorkshared] = false,
                [BimDiagnosticStage.RevitDocumentIsModelInCloud] = false,
                [BimDiagnosticStage.RevitDocumentIsDetached] = false,
                [BimDiagnosticStage.RevitDocumentCentralModelPath] = false,
                [BimDiagnosticStage.RevitDocumentModelPathEmpty] = false,
                [BimDiagnosticStage.RevitDocumentModelPathServer] = false,
                [BimDiagnosticStage.RevitDocumentModelPathCloud] = false,
                [BimDiagnosticStage.RevitCategoriesSettings] = false,
                [BimDiagnosticStage.RevitCategoriesCollection] = false,
                [BimDiagnosticStage.RevitCategoriesIterator] = false,
                [BimDiagnosticStage.RevitCategoriesMoveNext] = false,
                [BimDiagnosticStage.RevitCategoriesCurrent] = false,
                [BimDiagnosticStage.RevitCategoriesIteratorDispose] = false,
                [BimDiagnosticStage.RevitCategoryId] = false,
                [BimDiagnosticStage.RevitCategoryName] = false,
                [BimDiagnosticStage.RevitCategoryBuiltIn] = false,
                [BimDiagnosticStage.RevitCategoryType] = false,
                [BimDiagnosticStage.SinkWriter] = false
            };
            var stages = Enum.GetValues(typeof(BimDiagnosticStage))
                .Cast<BimDiagnosticStage>()
                .ToArray();

            Assert.Equal(stages.Length, policy.Count);
            foreach (var stage in stages)
            {
                Assert.True(policy.TryGetValue(stage, out var persistsMilestones),
                    "Stage requires an explicit sparse-persistence decision: " + stage);
                var before = scope.Sink.Envelopes.Count;

                BimDiagnostics.Observe(
                    scope.Context, stage, BimDiagnosticOutcome.Start,
                    BimDiagnosticFields.None);
                BimDiagnostics.Observe(
                    scope.Context, stage, BimDiagnosticOutcome.Success,
                    BimDiagnosticFields.None);

                var afterMilestones = scope.Sink.Envelopes.Count;
                Assert.Equal(persistsMilestones ? before + 2 : before,
                    afterMilestones);

                BimDiagnostics.Observe(
                    scope.Context, stage, BimDiagnosticOutcome.Failure,
                    BimDiagnosticFields.None);

                Assert.Equal(afterMilestones + 1, scope.Sink.Envelopes.Count);
                Assert.Equal(BimDiagnosticRecordKind.Failure,
                    scope.Sink.Envelopes[scope.Sink.Envelopes.Count - 1].Kind);
            }
        }

        [Fact]
        public async Task InMemorySink_ConcurrentFacadeEnqueuesProduceAnExactSnapshot()
        {
            const int WorkerCount = 8;
            const int EnvelopesPerWorker = 5000;

            using var scope = TestDiagnostics.EnabledScope("concurrent_sink");
            using var start = new ManualResetEventSlim(false);
            var remaining = WorkerCount;
            var allReady = new TaskCompletionSource<bool>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            var contexts = Enumerable.Range(0, WorkerCount)
                .Select(worker => scope.Session.CreateContext(
                    "concurrent_sink_" + worker))
                .ToArray();
            var workers = contexts.Select(context => Task.Run(() =>
            {
                if (Interlocked.Decrement(ref remaining) == 0)
                {
                    allReady.TrySetResult(true);
                }

                start.Wait();
                for (var index = 0; index < EnvelopesPerWorker; index++)
                {
                    BimDiagnostics.Observe(
                        context,
                        BimDiagnosticStage.SinkWriter,
                        BimDiagnosticOutcome.Failure,
                        BimDiagnosticFields.None);
                }
            })).ToArray();

            await allReady.Task;
            start.Set();
            await Task.WhenAll(workers);

            var snapshot = scope.Sink.Envelopes;
            Assert.Equal(WorkerCount * EnvelopesPerWorker, snapshot.Count);
            Assert.All(snapshot, envelope =>
                Assert.Equal(BimDiagnosticRecordKind.Failure, envelope.Kind));
        }
    }
}
