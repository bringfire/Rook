using System;
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
            public Result(
                bool? enabled,
                bool known,
                string? solutionState,
                bool? globalEnableSolutions,
                bool? documentEnabled)
            {
                Enabled = enabled;
                Known = known;
                SolutionState = solutionState;
                GlobalEnableSolutions = globalEnableSolutions;
                DocumentEnabled = documentEnabled;
            }

            public bool? Enabled { get; }     // null when unknown
            public bool Known { get; }
            public string? SolutionState { get; }
            public bool? GlobalEnableSolutions { get; }
            public bool? DocumentEnabled { get; }
        }

        public static Result Inspect(object? document)
        {
            if (document == null)
                return new Result(null, false, null, null, null);

            var t = document.GetType();
            bool? globalEnableSolutions = null;
            bool? documentEnabled = null;
            string? solutionState = null;

            try
            {
                globalEnableSolutions = ReadStaticBoolean(t, "EnableSolutions");
            }
            catch { /* keep fail-open */ }
            try
            {
                documentEnabled = ReadInstanceBoolean(document, "Enabled");
            }
            catch { /* keep fail-open */ }
            try
            {
                solutionState = ReadSolutionState(document);
            }
            catch { /* telemetry only */ }

            var enabled = CombineSolverFlags(globalEnableSolutions, documentEnabled);
            return new Result(
                enabled,
                enabled.HasValue,
                solutionState,
                globalEnableSolutions,
                documentEnabled);
        }

        private static bool? ReadStaticBoolean(Type type, string propertyName)
        {
            var prop = type.GetProperty(propertyName, BindingFlags.Public | BindingFlags.Static);
            return prop?.GetValue(null) is bool value ? value : null;
        }

        private static bool? ReadInstanceBoolean(object instance, string propertyName)
        {
            var prop = instance.GetType().GetProperty(propertyName, BindingFlags.Public | BindingFlags.Instance);
            return prop?.GetValue(instance) is bool value ? value : null;
        }

        private static string? ReadSolutionState(object document)
        {
            var state = document.GetType().GetProperty("SolutionState", BindingFlags.Public | BindingFlags.Instance);
            return state?.GetValue(document)?.ToString();
        }

        private static bool? CombineSolverFlags(bool? globalEnableSolutions, bool? documentEnabled)
        {
            if (globalEnableSolutions.HasValue && documentEnabled.HasValue)
                return globalEnableSolutions.Value && documentEnabled.Value;

            if (globalEnableSolutions == false || documentEnabled == false)
                return false;

            if (globalEnableSolutions == true || documentEnabled == true)
                return true;

            return null;
        }
    }
}
