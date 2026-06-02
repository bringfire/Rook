using System.Collections.Generic;
using Rook.Handlers;
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
    }
}
