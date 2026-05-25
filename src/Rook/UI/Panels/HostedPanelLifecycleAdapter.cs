using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Eto.Forms;
using Rhino.UI;

namespace Rook.UI.Panels
{
    internal sealed class HostedPanelLifecycleAdapter
    {
        private readonly Type _panelType;
        private readonly IRhinoPanelVisibilityQuery _visibilityQuery;
        private readonly Action<string, Action> _schedule;
        private readonly HostedPanelLifecycleCoordinator _coordinator = new();
        private readonly Dictionary<string, SurfaceState> _surfaces = new();
        private uint _documentSerialNumber;
        private bool _panelReportedVisible;
        private bool _closing;
        private HostedPanelLifecycleReason _lastReason = HostedPanelLifecycleReason.Unknown;
        private int _transitionVersion;

        public HostedPanelLifecycleAdapter(Type panelType)
            : this(panelType, new RhinoPanelVisibilityQuery())
        {
        }

        internal HostedPanelLifecycleAdapter(
            Type panelType,
            IRhinoPanelVisibilityQuery visibilityQuery)
            : this(panelType, visibilityQuery, ScheduleOnUiThread)
        {
        }

        internal HostedPanelLifecycleAdapter(
            Type panelType,
            IRhinoPanelVisibilityQuery visibilityQuery,
            Action<string, Action> schedule)
        {
            _panelType = panelType ?? throw new ArgumentNullException(nameof(panelType));
            _visibilityQuery = visibilityQuery ?? throw new ArgumentNullException(nameof(visibilityQuery));
            _schedule = schedule ?? throw new ArgumentNullException(nameof(schedule));
        }

        public void PanelShown(uint documentSerialNumber, ShowPanelReason reason)
        {
            _documentSerialNumber = documentSerialNumber;
            _panelReportedVisible = true;
            _closing = false;
            _lastReason = MapReason(reason);
            BeginNewTransition();
        }

        public void PanelHidden(uint documentSerialNumber, ShowPanelReason reason)
        {
            _documentSerialNumber = documentSerialNumber;
            _lastReason = MapReason(reason);
            if (_lastReason != HostedPanelLifecycleReason.HideOnDeactivate)
            {
                _panelReportedVisible = false;
            }

            BeginNewTransition();
        }

        public void PanelClosing(uint documentSerialNumber, bool onCloseDocument)
        {
            _ = onCloseDocument;
            _documentSerialNumber = documentSerialNumber;
            _closing = true;
            BeginNewTransition();
        }

        public void Reconcile(
            string surfaceId,
            bool isSelectedTab,
            Control hostControl,
            Action<HostedSurfaceDecision> apply)
        {
            if (apply == null)
            {
                throw new ArgumentNullException(nameof(apply));
            }

            Reconcile(
                surfaceId,
                isSelectedTab,
                hostControl,
                (decision, _) => apply(decision));
        }

        public void Reconcile(
            string surfaceId,
            bool isSelectedTab,
            Control hostControl,
            Action<HostedSurfaceDecision, PanelLifecycleFacts> apply)
        {
            if (hostControl == null)
            {
                throw new ArgumentNullException(nameof(hostControl));
            }

            ReconcileCore(
                surfaceId,
                isSelectedTab,
                () => CaptureHostReadiness(hostControl),
                apply,
                eventName: "Reconcile");
        }

        internal void ReconcileForTest(
            string surfaceId,
            bool isSelectedTab,
            bool isHostReady,
            Action<HostedSurfaceDecision> apply)
        {
            if (apply == null)
            {
                throw new ArgumentNullException(nameof(apply));
            }

            ReconcileForTest(
                surfaceId,
                isSelectedTab,
                () => isHostReady,
                (decision, _) => apply(decision));
        }

        internal void ReconcileForTest(
            string surfaceId,
            bool isSelectedTab,
            bool isHostReady,
            Action<HostedSurfaceDecision, PanelLifecycleFacts> apply)
        {
            ReconcileCore(
                surfaceId,
                isSelectedTab,
                () => HostReadiness.ForTest(isHostReady),
                apply,
                eventName: "ReconcileForTest");
        }

        internal void ReconcileForTest(
            string surfaceId,
            bool isSelectedTab,
            Func<bool> readinessProvider,
            Action<HostedSurfaceDecision> apply)
        {
            if (apply == null)
            {
                throw new ArgumentNullException(nameof(apply));
            }

            ReconcileForTest(
                surfaceId,
                isSelectedTab,
                readinessProvider,
                (decision, _) => apply(decision));
        }

        internal void ReconcileForTest(
            string surfaceId,
            bool isSelectedTab,
            Func<bool> readinessProvider,
            Action<HostedSurfaceDecision, PanelLifecycleFacts> apply)
        {
            ReconcileCore(
                surfaceId,
                isSelectedTab,
                () => HostReadiness.ForTest(readinessProvider()),
                apply,
                eventName: "ReconcileForTest");
        }

        public void ForgetSurface(string surfaceId)
        {
            if (string.IsNullOrWhiteSpace(surfaceId))
            {
                return;
            }

            _surfaces.Remove(surfaceId);
        }

        internal void SetDeferAttemptForTest(string surfaceId, int deferAttempt)
        {
            GetState(surfaceId).DeferAttempt = deferAttempt;
        }

        internal static HostedPanelLifecycleReason MapReasonForTest(ShowPanelReason reason)
        {
            return MapReason(reason);
        }

        private void ReconcileCore(
            string surfaceId,
            bool isSelectedTab,
            Func<HostReadiness> readinessProvider,
            Action<HostedSurfaceDecision, PanelLifecycleFacts> apply,
            string eventName)
        {
            if (string.IsNullOrWhiteSpace(surfaceId))
            {
                throw new ArgumentException("Surface id is required.", nameof(surfaceId));
            }

            if (apply == null)
            {
                throw new ArgumentNullException(nameof(apply));
            }

            if (readinessProvider == null)
            {
                throw new ArgumentNullException(nameof(readinessProvider));
            }

            var state = GetState(surfaceId);
            state.LastSelectedTab = isSelectedTab;
            state.LastReadinessProvider = readinessProvider;
            state.LastApply = apply;
            state.LastEventName = eventName;
            state.TransitionVersion = _transitionVersion;

            var readiness = state.LastReadinessProvider();
            var facts = CaptureFacts(state, readiness);
            var decision = _coordinator.Decide(facts);
            HostedPanelLifecycleTrace.Record(
                _panelType.Name,
                _documentSerialNumber,
                surfaceId,
                eventName,
                facts,
                decision,
                readiness.ToTraceDetail());

            if (decision.Action == HostedSurfaceAction.Defer)
            {
                ScheduleDeferred(surfaceId, state);
                apply(decision, facts);
                return;
            }

            state.PendingRetry = false;
            apply(decision, facts);
        }

        private PanelLifecycleFacts CaptureFacts(
            SurfaceState state,
            HostReadiness readiness)
        {
            return new PanelLifecycleFacts
            {
                PanelReportedVisible = _panelReportedVisible,
                LastReason = _lastReason,
                IsSelectedTab = state.LastSelectedTab,
                IsRhinoSelectedPanelVisible = _visibilityQuery.IsSelectedPanelVisible(_panelType),
                IsHostReady = readiness.IsReady,
                IsClosing = _closing,
                DeferAttempt = state.DeferAttempt
            };
        }

        private void ScheduleDeferred(string surfaceId, SurfaceState state)
        {
            if (state.PendingRetry)
            {
                return;
            }

            state.PendingRetry = true;
            var transitionVersion = _transitionVersion;

            _schedule(surfaceId, () =>
            {
                if (!_surfaces.TryGetValue(surfaceId, out var currentState) ||
                    !ReferenceEquals(currentState, state))
                {
                    return;
                }

                currentState.PendingRetry = false;
                if (currentState.TransitionVersion != transitionVersion)
                {
                    return;
                }

                currentState.DeferAttempt++;
                if (currentState.LastApply == null)
                {
                    return;
                }

                ReconcileCore(
                    surfaceId,
                    currentState.LastSelectedTab,
                    currentState.LastReadinessProvider,
                    currentState.LastApply,
                    "DeferredRetry");
            });
        }

        private void BeginNewTransition()
        {
            _transitionVersion++;
            foreach (var state in _surfaces.Values)
            {
                state.DeferAttempt = 0;
                state.PendingRetry = false;
                state.TransitionVersion = _transitionVersion;
            }
        }

        private SurfaceState GetState(string surfaceId)
        {
            if (!_surfaces.TryGetValue(surfaceId, out var state))
            {
                state = new SurfaceState
                {
                    TransitionVersion = _transitionVersion
                };
                _surfaces.Add(surfaceId, state);
            }

            return state;
        }

        private static HostReadiness CaptureHostReadiness(Control control)
        {
            var size = control.Size;
            var bounds = control.Bounds.Size;
            var sizeReady =
                (size.Width > 0 && size.Height > 0) ||
                (bounds.Width > 0 && bounds.Height > 0);

            return new HostReadiness(
                loaded: control.Loaded,
                hasParent: control.Parent != null,
                hasVisualParent: control.VisualParent != null,
                hasParentWindow: control.ParentWindow != null,
                hasNonZeroHostSize: sizeReady,
                sizeWidth: size.Width,
                sizeHeight: size.Height,
                boundsWidth: bounds.Width,
                boundsHeight: bounds.Height);
        }

        private static HostedPanelLifecycleReason MapReason(ShowPanelReason reason)
        {
            return reason switch
            {
                ShowPanelReason.Show => HostedPanelLifecycleReason.Show,
                ShowPanelReason.Hide => HostedPanelLifecycleReason.Hide,
                ShowPanelReason.HideOnDeactivate => HostedPanelLifecycleReason.HideOnDeactivate,
                ShowPanelReason.ShowOnDeactivate => HostedPanelLifecycleReason.ShowOnDeactivate,
                _ => HostedPanelLifecycleReason.Unknown
            };
        }

        private static void ScheduleOnUiThread(string surfaceId, Action action)
        {
            _ = surfaceId;
            Task.Delay(75).ContinueWith(_ =>
            {
                try
                {
                    Application.Instance.AsyncInvoke(action);
                }
                catch
                {
                    action();
                }
            }, TaskScheduler.Default);
        }

        private sealed class SurfaceState
        {
            public bool LastSelectedTab { get; set; }
            public Func<HostReadiness> LastReadinessProvider { get; set; } =
                () => HostReadiness.ForTest(false);
            public Action<HostedSurfaceDecision, PanelLifecycleFacts>? LastApply { get; set; }
            public string LastEventName { get; set; } = "";
            public int DeferAttempt { get; set; }
            public bool PendingRetry { get; set; }
            public int TransitionVersion { get; set; }
        }

        private readonly struct HostReadiness
        {
            public HostReadiness(
                bool loaded,
                bool hasParent,
                bool hasVisualParent,
                bool hasParentWindow,
                bool hasNonZeroHostSize,
                int sizeWidth,
                int sizeHeight,
                int boundsWidth,
                int boundsHeight)
            {
                Loaded = loaded;
                HasParent = hasParent;
                HasVisualParent = hasVisualParent;
                HasParentWindow = hasParentWindow;
                HasNonZeroHostSize = hasNonZeroHostSize;
                SizeWidth = sizeWidth;
                SizeHeight = sizeHeight;
                BoundsWidth = boundsWidth;
                BoundsHeight = boundsHeight;
            }

            public bool Loaded { get; }
            public bool HasParent { get; }
            public bool HasVisualParent { get; }
            public bool HasParentWindow { get; }
            public bool HasNonZeroHostSize { get; }
            public int SizeWidth { get; }
            public int SizeHeight { get; }
            public int BoundsWidth { get; }
            public int BoundsHeight { get; }

            public bool IsReady =>
                Loaded &&
                (HasParent || HasVisualParent || HasParentWindow) &&
                HasNonZeroHostSize;

            public static HostReadiness ForTest(bool ready)
            {
                return new HostReadiness(
                    loaded: ready,
                    hasParent: ready,
                    hasVisualParent: ready,
                    hasParentWindow: ready,
                    hasNonZeroHostSize: ready,
                    sizeWidth: ready ? 100 : 0,
                    sizeHeight: ready ? 100 : 0,
                    boundsWidth: ready ? 100 : 0,
                    boundsHeight: ready ? 100 : 0);
            }

            public string ToTraceDetail()
            {
                return
                    "loaded=" + Loaded +
                    ";parent=" + HasParent +
                    ";visualParent=" + HasVisualParent +
                    ";parentWindow=" + HasParentWindow +
                    ";hostSize=" + HasNonZeroHostSize +
                    ";size=" + SizeWidth + "x" + SizeHeight +
                    ";bounds=" + BoundsWidth + "x" + BoundsHeight;
            }
        }
    }
}
