using System.Collections.Generic;
using Rook.Handlers;
using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class RequestPostMutationSolveTests
    {
        private sealed class FakeObj
        {
            public List<bool> Expire = new();
            public void ExpireSolution(bool recompute) => Expire.Add(recompute);
        }
        private sealed class FakeDoc
        {
            public static bool EnableSolutions { get; set; } = true;
            public bool Enabled { get; set; } = true;
            public List<int> Scheduled = new();
            public void ScheduleSolution(int ms) => Scheduled.Add(ms);
        }

        [Fact]
        public void Enabled_MarksDirtyFalse_AndSchedulesOnce()
        {
            var h = new GrasshopperHandler();
            var obj = new FakeObj();
            var doc = new FakeDoc { Enabled = true };

            var outcome = h.RequestPostMutationSolve(doc, obj, requestSolve: true);

            Assert.Equal(new[] { false }, obj.Expire);   // never true (no sync recompute)
            Assert.Single(doc.Scheduled);
            Assert.True(doc.Scheduled[0] >= 1);           // never 0
            Assert.True(outcome.SolveScheduled);
            Assert.False(outcome.VerificationDeferred);
        }

        [Fact]
        public void Locked_MarksDirtyFalse_AndDoesNotSchedule()
        {
            var h = new GrasshopperHandler();
            var obj = new FakeObj();
            var doc = new FakeDoc { Enabled = false };

            var outcome = h.RequestPostMutationSolve(doc, obj, requestSolve: true);

            Assert.Equal(new[] { false }, obj.Expire);
            Assert.Empty(doc.Scheduled);                  // suppressed while locked
            Assert.True(outcome.SolverLocked);
            Assert.True(outcome.VerificationDeferred);
        }

        private sealed class FakeDocNoSchedule { public bool Enabled { get; set; } = true; }

        [Fact]
        public void ScheduleMethodMissing_DoesNotClaimScheduled()
        {
            var h = new GrasshopperHandler();
            var obj = new FakeObj();
            var doc = new FakeDocNoSchedule();   // enabled, but NO ScheduleSolution method

            var outcome = h.RequestPostMutationSolve(doc, obj, requestSolve: true);

            Assert.Equal(new[] { false }, obj.Expire);
            Assert.False(outcome.SolveScheduled);   // reflection miss corrected — never over-claim scheduling
            Assert.True(outcome.VerificationDeferred);
        }

        [Fact]
        public void RequestPostMutationSolve_RirDisabledInstanceRepairsBeforeScheduling()
        {
            FakeDoc.EnableSolutions = true;
            var document = new FakeDoc { Enabled = false };
            var dirty = new FakeObj();
            var handler = CreateHandlerForRirRepair(
                isRhinoInside: () => true,
                getActiveDocument: () => document);

            var outcome = handler.RequestPostMutationSolve(document, new[] { dirty }, requestSolve: true, delayMs: 1);

            Assert.True(outcome.RirRepairAttempted);
            Assert.True(outcome.RirRepairHeld);
            Assert.True(document.Enabled);
            Assert.True(outcome.SolveScheduled);
            Assert.Single(document.Scheduled);
            Assert.Equal(new[] { false }, dirty.Expire);
        }

        [Fact]
        public void RequestPostMutationSolve_StaticSolverDisabledDoesNotRepairOrSchedule()
        {
            FakeDoc.EnableSolutions = false;
            var document = new FakeDoc { Enabled = false };
            var handler = CreateHandlerForRirRepair(
                isRhinoInside: () => true,
                getActiveDocument: () => document);

            var outcome = handler.RequestPostMutationSolve(document, System.Array.Empty<object>(), requestSolve: true, delayMs: 1);

            Assert.False(outcome.RirRepairAttempted);
            Assert.False(document.Enabled);
            Assert.False(outcome.SolveScheduled);
            Assert.True(outcome.SolverLocked);

            FakeDoc.EnableSolutions = true;
        }

        [Fact]
        public void RequestPostMutationSolve_StandaloneDisabledInstanceDoesNotRepair()
        {
            FakeDoc.EnableSolutions = true;
            var document = new FakeDoc { Enabled = false };
            var handler = CreateHandlerForRirRepair(
                isRhinoInside: () => false,
                getActiveDocument: () => document);

            var outcome = handler.RequestPostMutationSolve(document, System.Array.Empty<object>(), requestSolve: true, delayMs: 1);

            Assert.False(outcome.RirRepairAttempted);
            Assert.False(document.Enabled);
            Assert.False(outcome.SolveScheduled);
        }

        private static GrasshopperHandler CreateHandlerForRirRepair(System.Func<bool> isRhinoInside, System.Func<object?> getActiveDocument)
        {
            var coordinator = new GhSolveReadinessCoordinator(
                isRhinoInside: isRhinoInside,
                getActiveDocument: getActiveDocument,
                runOnUiThread: action => action());

            return new GrasshopperHandler(solveReadinessCoordinator: coordinator);
        }
    }
}
