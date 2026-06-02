using System.Reflection;

namespace Rook.InternalBridge
{
    /// <summary>Reflected Grasshopper solver state, shared by the GH handler's
    /// safe-solve policy and gh_status. SolutionState is telemetry only and MUST
    /// NOT influence the enabled decision. See spec §5.4 / §7.
    /// Internal — visible to Rook.Tests via InternalsVisibleTo (Rook.csproj:25).</summary>
    internal static class GhSolverState
    {
        public readonly struct Result
        {
            public bool? Enabled { get; init; }     // null when unknown
            public bool Known { get; init; }
            public string? SolutionState { get; init; }
        }

        public static Result Inspect(object document)
        {
            bool known = false;
            bool enabled = true; // fail-open
            string? solutionState = null;
            if (document == null)
                return new Result { Enabled = null, Known = false, SolutionState = null };

            var t = document.GetType();
            try
            {
                var enableSolutions = t.GetProperty("EnableSolutions", BindingFlags.Public | BindingFlags.Static);
                if (enableSolutions?.GetValue(null) is bool es) { enabled &= es; known = true; }
            }
            catch { /* keep fail-open */ }
            try
            {
                var enabledProp = t.GetProperty("Enabled", BindingFlags.Public | BindingFlags.Instance);
                if (enabledProp?.GetValue(document) is bool en) { enabled &= en; known = true; }
            }
            catch { /* keep fail-open */ }
            try
            {
                var state = t.GetProperty("SolutionState", BindingFlags.Public | BindingFlags.Instance);
                solutionState = state?.GetValue(document)?.ToString();
            }
            catch { /* telemetry only */ }

            return new Result { Enabled = known ? enabled : (bool?)null, Known = known, SolutionState = solutionState };
        }
    }
}
