using System;
using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.InternalBridge
{
    public sealed class GhSolveReadinessCoordinatorTests
    {
        private sealed class FakeGhDocument
        {
            public static bool EnableSolutions { get; set; } = true;
            public bool Enabled { get; set; } = true;
            public event EventHandler? EnabledChanged;

            public void DisableThroughHost()
            {
                Enabled = false;
                EnabledChanged?.Invoke(this, EventArgs.Empty);
            }
        }

        [Fact]
        public void PrepareForPostMutationSolve_Standalone_DoesNotRepair()
        {
            FakeGhDocument.EnableSolutions = true;
            var document = new FakeGhDocument { Enabled = false };
            var coordinator = new GhSolveReadinessCoordinator(
                isRhinoInside: () => false,
                getActiveDocument: () => document,
                runOnUiThread: action => action());

            var result = coordinator.PrepareForPostMutationSolve(document, requestSolve: true, currentMutationIsRookDriven: true);

            Assert.False(result.RepairAttempted);
            Assert.False(document.Enabled);
            Assert.Equal("standalone", result.Reason);
        }

        [Fact]
        public void PrepareForPostMutationSolve_StaticSolverLock_DoesNotRepair()
        {
            FakeGhDocument.EnableSolutions = false;
            var document = new FakeGhDocument { Enabled = false };
            var coordinator = new GhSolveReadinessCoordinator(
                isRhinoInside: () => true,
                getActiveDocument: () => document,
                runOnUiThread: action => action());

            var result = coordinator.PrepareForPostMutationSolve(document, requestSolve: true, currentMutationIsRookDriven: true);

            Assert.False(result.RepairAttempted);
            Assert.False(document.Enabled);
            Assert.Equal("static_solver_disabled", result.Reason);

            FakeGhDocument.EnableSolutions = true;
        }

        [Fact]
        public void PrepareForPostMutationSolve_RirRookDrivenDisabledDocument_RepairsInstanceOnly()
        {
            FakeGhDocument.EnableSolutions = true;
            var document = new FakeGhDocument { Enabled = false };
            var coordinator = new GhSolveReadinessCoordinator(
                isRhinoInside: () => true,
                getActiveDocument: () => document,
                runOnUiThread: action => action());

            var result = coordinator.PrepareForPostMutationSolve(document, requestSolve: true, currentMutationIsRookDriven: true);

            Assert.True(result.RepairAttempted);
            Assert.True(result.RepairHeld);
            Assert.True(document.Enabled);
            Assert.True(FakeGhDocument.EnableSolutions);
        }

        [Fact]
        public void ArmDocumentTransitionRepair_RepairsOnceAndDisarms()
        {
            FakeGhDocument.EnableSolutions = true;
            var document = new FakeGhDocument { Enabled = true };
            var coordinator = new GhSolveReadinessCoordinator(
                isRhinoInside: () => true,
                getActiveDocument: () => document,
                runOnUiThread: action => action(),
                utcNow: () => new DateTimeOffset(2026, 6, 13, 12, 0, 0, TimeSpan.Zero));

            coordinator.MarkRookManagedDocument(document, "gh_document_new");

            document.DisableThroughHost();
            Assert.True(document.Enabled);
            Assert.True(coordinator.LatestTelemetry.RepairAttempted);

            document.DisableThroughHost();
            Assert.False(document.Enabled);
            Assert.Equal("transition_first_repair", coordinator.LatestTelemetry.Reason);
        }
    }
}
