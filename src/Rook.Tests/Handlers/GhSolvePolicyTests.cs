using Rook.Handlers;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class GhSolvePolicyTests
    {
        [Fact]
        public void KnownEnabled_RequestSolve_SchedulesAndDoesNotDefer()
        {
            var o = GhSolvePolicy.Decide(requestSolve: true, solverEnabled: true, solverStateKnown: true);
            Assert.True(o.SolveScheduled);
            Assert.False(o.SolverLocked);
            Assert.True(o.SolverStateKnown);
            Assert.False(o.VerificationDeferred);
        }

        [Fact]
        public void KnownLocked_RequestSolve_DoesNotScheduleAndDefers()
        {
            var o = GhSolvePolicy.Decide(requestSolve: true, solverEnabled: false, solverStateKnown: true);
            Assert.False(o.SolveScheduled);
            Assert.True(o.SolverLocked);
            Assert.True(o.SolverStateKnown);
            Assert.True(o.VerificationDeferred);
            Assert.NotEmpty(o.Warnings);
        }

        [Fact]
        public void Unknown_RequestSolve_SchedulesButDefersConservatively()
        {
            var o = GhSolvePolicy.Decide(requestSolve: true, solverEnabled: true, solverStateKnown: false);
            Assert.True(o.SolveScheduled);
            Assert.False(o.SolverLocked);
            Assert.False(o.SolverStateKnown);
            Assert.True(o.VerificationDeferred);  // can't confirm the solve ran
            Assert.NotEmpty(o.Warnings);
        }

        [Fact]
        public void NoRequestSolve_NeverSchedules()
        {
            var o = GhSolvePolicy.Decide(requestSolve: false, solverEnabled: true, solverStateKnown: true);
            Assert.False(o.SolveScheduled);
            Assert.False(o.VerificationDeferred);
        }
    }
}
