using System;
using System.Reflection;
using Rhino;

namespace Rook.InternalBridge
{
    internal sealed class GhSolveReadinessCoordinator
    {
        private static readonly TimeSpan TransitionWindow = TimeSpan.FromSeconds(5);

        private readonly Func<bool> _isRhinoInside;
        private readonly Func<object?> _getActiveDocument;
        private readonly Action<Action> _runOnUiThread;
        private readonly Func<DateTimeOffset> _utcNow;
        private readonly object _sync = new();

        private object? _managedDocument;
        private object? _transitionDocument;
        private EventInfo? _transitionEnabledChangedEvent;
        private Delegate? _transitionEnabledChangedHandler;
        private DateTimeOffset _transitionExpiresAt;
        private bool _transitionRepairConsumed;
        private GhSolveReadinessTelemetry _latestTelemetry = GhSolveReadinessTelemetry.None;

        public GhSolveReadinessCoordinator(
            Func<bool>? isRhinoInside = null,
            Func<object?>? getActiveDocument = null,
            Action<Action>? runOnUiThread = null,
            Func<DateTimeOffset>? utcNow = null)
        {
            _isRhinoInside = isRhinoInside ?? (() => Rhino.Runtime.HostUtils.RunningAsRhinoInside);
            _getActiveDocument = getActiveDocument ?? GetGrasshopperActiveDocument;
            _runOnUiThread = runOnUiThread ?? RunOnRhinoUiThread;
            _utcNow = utcNow ?? (() => DateTimeOffset.UtcNow);
        }

        public GhSolveReadinessTelemetry LatestTelemetry
        {
            get
            {
                lock (_sync)
                {
                    return _latestTelemetry;
                }
            }
        }

        public GhSolveReadinessResult PrepareForPostMutationSolve(
            object? document,
            bool requestSolve,
            bool currentMutationIsRookDriven)
        {
            if (!_isRhinoInside())
            {
                return Record(GhSolveReadinessResult.NoAction("standalone"), "schedule_time");
            }

            GhSolveReadinessResult result = GhSolveReadinessResult.NoAction("not_run");
            _runOnUiThread(() => result = PrepareOnUiThread(document, requestSolve, currentMutationIsRookDriven));
            return result;
        }

        public void MarkRookManagedDocument(object? document, string reason)
        {
            if (!_isRhinoInside())
            {
                lock (_sync)
                {
                    _managedDocument = document;
                    _latestTelemetry = new GhSolveReadinessTelemetry(false, false, "standalone", reason, _utcNow());
                }

                return;
            }

            _runOnUiThread(() => MarkRookManagedDocumentOnUiThread(document, reason));
        }

        private GhSolveReadinessResult PrepareOnUiThread(object? document, bool requestSolve, bool currentMutationIsRookDriven)
        {
            if (!_isRhinoInside())
            {
                return Record(GhSolveReadinessResult.NoAction("standalone"), "schedule_time");
            }

            if (!requestSolve)
            {
                return Record(GhSolveReadinessResult.NoAction("solve_not_requested"), "schedule_time");
            }

            if (document is null)
            {
                return Record(GhSolveReadinessResult.NoAction("no_document"), "schedule_time");
            }

            var activeDocument = _getActiveDocument();
            if (!ReferenceEquals(document, activeDocument))
            {
                return Record(GhSolveReadinessResult.NoAction("not_active_document"), "schedule_time");
            }

            if (!currentMutationIsRookDriven && !ReferenceEquals(document, _managedDocument))
            {
                return Record(GhSolveReadinessResult.NoAction("not_rook_managed"), "schedule_time");
            }

            var state = GhSolverState.Inspect(document);
            if (state.GlobalEnableSolutions == false)
            {
                return Record(GhSolveReadinessResult.NoAction("static_solver_disabled"), "schedule_time");
            }

            if (state.DocumentEnabled != false)
            {
                return Record(GhSolveReadinessResult.NoAction("document_already_enabled"), "schedule_time");
            }

            if (!WriteInstanceEnabled(document, true))
            {
                return Record(GhSolveReadinessResult.Repaired(false, "instance_enabled_write_failed"), "schedule_time");
            }

            var after = GhSolverState.Inspect(_getActiveDocument());
            var held = ReferenceEquals(document, _getActiveDocument()) && after.DocumentEnabled == true;
            return Record(
                GhSolveReadinessResult.Repaired(held, held ? "schedule_time_repair_held" : "schedule_time_repair_did_not_hold"),
                "schedule_time");
        }

        private void MarkRookManagedDocumentOnUiThread(object? document, string reason)
        {
            TeardownTransitionSubscriptionOnUiThread("document_replaced");

            if (!_isRhinoInside() || document is null)
            {
                lock (_sync)
                {
                    _managedDocument = document;
                    _latestTelemetry = new GhSolveReadinessTelemetry(
                        false,
                        false,
                        _isRhinoInside() ? "no_document" : "standalone",
                        reason,
                        _utcNow());
                }

                return;
            }

            lock (_sync)
            {
                _managedDocument = document;
                _transitionDocument = document;
                _transitionExpiresAt = _utcNow().Add(TransitionWindow);
                _transitionRepairConsumed = false;
                _latestTelemetry = new GhSolveReadinessTelemetry(false, false, "transition_armed", reason, _utcNow());
            }

            SubscribeTransitionEnabledChangedOnUiThread(document);
        }

        private void SubscribeTransitionEnabledChangedOnUiThread(object document)
        {
            var enabledChanged = document.GetType().GetEvent("EnabledChanged", BindingFlags.Instance | BindingFlags.Public);
            if (enabledChanged is null || enabledChanged.EventHandlerType is null)
            {
                lock (_sync)
                {
                    _latestTelemetry = new GhSolveReadinessTelemetry(false, false, "enabled_changed_event_missing", "transition", _utcNow());
                }

                return;
            }

            try
            {
                EventHandler handler = (_, _) => OnTransitionEnabledChangedOnUiThread(document);
                var typedHandler = Delegate.CreateDelegate(enabledChanged.EventHandlerType, handler.Target, handler.Method);
                enabledChanged.AddEventHandler(document, typedHandler);

                lock (_sync)
                {
                    _transitionEnabledChangedEvent = enabledChanged;
                    _transitionEnabledChangedHandler = typedHandler;
                }
            }
            catch
            {
                lock (_sync)
                {
                    _latestTelemetry = new GhSolveReadinessTelemetry(false, false, "enabled_changed_subscribe_failed", "transition", _utcNow());
                }
            }
        }

        private void OnTransitionEnabledChangedOnUiThread(object document)
        {
            if (_utcNow() > _transitionExpiresAt)
            {
                TeardownTransitionSubscriptionOnUiThread("transition_window_expired");
                return;
            }

            if (_transitionRepairConsumed || !ReferenceEquals(document, _transitionDocument))
            {
                TeardownTransitionSubscriptionOnUiThread("transition_window_disarmed");
                return;
            }

            var activeDocument = _getActiveDocument();
            var state = GhSolverState.Inspect(activeDocument);
            if (!ReferenceEquals(document, activeDocument) || state.GlobalEnableSolutions == false || state.DocumentEnabled != false)
            {
                return;
            }

            _transitionRepairConsumed = true;
            var wrote = WriteInstanceEnabled(document, true);
            var after = GhSolverState.Inspect(_getActiveDocument());
            var held = wrote && ReferenceEquals(document, _getActiveDocument()) && after.DocumentEnabled == true;
            Record(
                GhSolveReadinessResult.Repaired(held, held ? "transition_repair_held" : "transition_repair_did_not_hold"),
                "transition");
            TeardownTransitionSubscriptionOnUiThread("transition_first_repair");
        }

        private void TeardownTransitionSubscriptionOnUiThread(string reason)
        {
            object? document;
            EventInfo? eventInfo;
            Delegate? handler;

            lock (_sync)
            {
                document = _transitionDocument;
                eventInfo = _transitionEnabledChangedEvent;
                handler = _transitionEnabledChangedHandler;
                _transitionDocument = null;
                _transitionEnabledChangedEvent = null;
                _transitionEnabledChangedHandler = null;
                _transitionRepairConsumed = false;
                _latestTelemetry = new GhSolveReadinessTelemetry(
                    _latestTelemetry.RepairAttempted,
                    _latestTelemetry.RepairHeld,
                    reason,
                    _latestTelemetry.Source,
                    _utcNow());
            }

            if (document is not null && eventInfo is not null && handler is not null)
            {
                eventInfo.RemoveEventHandler(document, handler);
            }
        }

        private GhSolveReadinessResult Record(GhSolveReadinessResult result, string source)
        {
            lock (_sync)
            {
                _latestTelemetry = new GhSolveReadinessTelemetry(result.RepairAttempted, result.RepairHeld, result.Reason, source, _utcNow());
            }

            return result;
        }

        private static bool WriteInstanceEnabled(object document, bool enabled)
        {
            try
            {
                var property = document.GetType().GetProperty("Enabled", BindingFlags.Instance | BindingFlags.Public);
                if (property is null || !property.CanWrite)
                {
                    return false;
                }

                property.SetValue(document, enabled);
                return true;
            }
            catch
            {
                return false;
            }
        }

        private static void RunOnRhinoUiThread(Action action)
        {
            try
            {
                RhinoApp.InvokeOnUiThread(new Action(action));
            }
            catch (DllNotFoundException)
            {
                action();
            }
            catch (EntryPointNotFoundException)
            {
                action();
            }
            catch (BadImageFormatException)
            {
                action();
            }
        }

        private static object? GetGrasshopperActiveDocument()
        {
            try
            {
                var instancesType = Type.GetType("Grasshopper.Instances, Grasshopper");
                var activeCanvas = instancesType?.GetProperty("ActiveCanvas", BindingFlags.Static | BindingFlags.Public)?.GetValue(null);
                return activeCanvas?.GetType().GetProperty("Document", BindingFlags.Instance | BindingFlags.Public)?.GetValue(activeCanvas);
            }
            catch
            {
                return null;
            }
        }
    }

    internal readonly record struct GhSolveReadinessResult(
        bool RepairAttempted,
        bool RepairHeld,
        string Reason)
    {
        public static GhSolveReadinessResult NoAction(string reason) => new(false, false, reason);
        public static GhSolveReadinessResult Repaired(bool held, string reason) => new(true, held, reason);
    }

    internal readonly record struct GhSolveReadinessTelemetry(
        bool RepairAttempted,
        bool RepairHeld,
        string Reason,
        string? Source,
        DateTimeOffset TimestampUtc)
    {
        public static GhSolveReadinessTelemetry None =>
            new(false, false, "none", null, DateTimeOffset.MinValue);
    }
}
