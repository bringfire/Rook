using System;

namespace Rook.Handlers
{
    /// <summary>Result of the shared post-mutation safe-solve policy. See
    /// docs/superpowers/specs/2026-06-02-gh-locked-solver-crash-design.md §5.
    /// Internal — visible to Rook.Tests via InternalsVisibleTo (Rook.csproj:25).</summary>
    internal readonly struct GhSolveOutcome
    {
        public bool SolveScheduled { get; init; }
        public bool SolverLocked { get; init; }
        public bool SolverStateKnown { get; init; }
        public bool VerificationDeferred { get; init; }
        public string[] Warnings { get; init; }
    }

    /// <summary>Pure decision for post-mutation solve behavior. No Grasshopper
    /// dependency — fully unit-testable. The safety invariant (never a synchronous
    /// recompute) lives in the caller; this only decides whether to SCHEDULE.</summary>
    internal static class GhSolvePolicy
    {
        public static GhSolveOutcome Decide(bool requestSolve, bool solverEnabled, bool solverStateKnown)
        {
            if (!requestSolve)
            {
                return new GhSolveOutcome
                {
                    SolveScheduled = false,
                    SolverLocked = solverStateKnown && !solverEnabled,
                    SolverStateKnown = solverStateKnown,
                    VerificationDeferred = false,
                    Warnings = Array.Empty<string>(),
                };
            }

            if (!solverStateKnown)
            {
                return new GhSolveOutcome
                {
                    SolveScheduled = true,            // safe async; invariant guarantees no crash
                    SolverLocked = false,
                    SolverStateKnown = false,
                    VerificationDeferred = true,      // cannot confirm the solve ran
                    Warnings = new[] { "Grasshopper solver state could not be inspected; used safe async scheduling, verification not guaranteed." },
                };
            }

            if (solverEnabled)
            {
                return new GhSolveOutcome
                {
                    SolveScheduled = true,
                    SolverLocked = false,
                    SolverStateKnown = true,
                    VerificationDeferred = false,
                    Warnings = Array.Empty<string>(),
                };
            }

            return new GhSolveOutcome
            {
                SolveScheduled = false,
                SolverLocked = true,
                SolverStateKnown = true,
                VerificationDeferred = true,
                Warnings = new[] { "Grasshopper solver is locked; recompute deferred until unlock." },
            };
        }
    }
}
