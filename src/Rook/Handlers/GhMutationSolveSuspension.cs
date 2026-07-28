using System.Reflection;
using Rook.InternalBridge;

namespace Rook.Handlers
{
    internal sealed class GhMutationSolveSuspension
    {
        private readonly object? _document;
        private readonly PropertyInfo? _enabledProperty;
        private bool _restoreAttempted;

        private GhMutationSolveSuspension(object? document, PropertyInfo? enabledProperty, bool active, GhSolverState.Result originalSolverState)
        {
            _document = document;
            _enabledProperty = enabledProperty;
            Active = active;
            OriginalSolverState = originalSolverState;
        }

        public bool Active { get; }
        public GhSolverState.Result OriginalSolverState { get; }

        public static GhMutationSolveSuspension Begin(object? document, bool runningAsRhinoInside)
        {
            var original = GhSolverState.Inspect(document);
            if (runningAsRhinoInside || document == null || original.Enabled != true || original.DocumentEnabled != true)
                return new GhMutationSolveSuspension(document, null, false, original);

            try
            {
                var enabledProperty = document.GetType().GetProperty("Enabled", BindingFlags.Instance | BindingFlags.Public);
                if (enabledProperty == null || !enabledProperty.CanWrite)
                    return new GhMutationSolveSuspension(document, null, false, original);

                // Once the setter invocation begins, retain restoration ownership:
                // a target setter can mutate the document and then throw.
                var suspension = new GhMutationSolveSuspension(document, enabledProperty, true, original);
                try { enabledProperty.SetValue(document, false); }
                catch { return suspension; }
                return suspension;
            }
            catch
            {
                return new GhMutationSolveSuspension(document, null, false, original);
            }
        }

        public GhSolverRestoreResult Restore()
        {
            if (!Active || _restoreAttempted)
                return new GhSolverRestoreResult { Attempted = false, Succeeded = true, ObservedDocumentEnabled = ReadDocumentEnabled() };

            _restoreAttempted = true;
            try
            {
                _enabledProperty!.SetValue(_document, true);
                var observed = ReadDocumentEnabled();
                if (observed == false)
                {
                    return FailedRestore(observed);
                }
                return new GhSolverRestoreResult { Attempted = true, Succeeded = true, ObservedDocumentEnabled = observed };
            }
            catch
            {
                return FailedRestore(ReadDocumentEnabled());
            }
        }

        private static GhSolverRestoreResult FailedRestore(bool? observed) => new GhSolverRestoreResult
        {
            Attempted = true,
            Succeeded = false,
            FailureCode = GhScheduleFailureCode.StandaloneSolverRestoreFailed,
            ObservedDocumentEnabled = observed,
        };

        private bool? ReadDocumentEnabled() => GhSolverState.Inspect(_document).DocumentEnabled;
    }
}
