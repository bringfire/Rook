using System;
using System.Collections.Generic;
using Eto.Forms;
using Rhino.UI;
using Rook.UI.Panels;
using Xunit;

namespace Rook.Tests.UI.Panels
{
    public class HostedPanelLifecycleAdapterTests
    {
        private sealed class FakeVisibilityQuery : IRhinoPanelVisibilityQuery
        {
            public bool Visible { get; set; } = true;
            public Type? LastPanelType { get; private set; }

            public bool IsSelectedPanelVisible(Type panelType)
            {
                LastPanelType = panelType;
                return Visible;
            }
        }

        private sealed class TestScheduler
        {
            private readonly Dictionary<string, Action> _pending = new();

            public int ScheduleCount { get; private set; }
            public int PendingCount => _pending.Count;

            public void Schedule(string surfaceId, Action action)
            {
                ScheduleCount++;
                _pending[surfaceId] = action;
            }

            public void Run(string surfaceId)
            {
                var action = _pending[surfaceId];
                _pending.Remove(surfaceId);
                action();
            }
        }

        private sealed class SequenceReadinessProvider
        {
            private readonly Queue<bool> _values = new();

            public SequenceReadinessProvider(params bool[] values)
            {
                foreach (var value in values)
                {
                    _values.Enqueue(value);
                }
            }

            public bool Next()
            {
                return _values.Count == 0 ? true : _values.Dequeue();
            }
        }

        [Fact]
        public void MapReason_HideOnDeactivate_MapsToHostedReason()
        {
            Assert.Equal(
                HostedPanelLifecycleReason.HideOnDeactivate,
                HostedPanelLifecycleAdapter.MapReasonForTest(ShowPanelReason.HideOnDeactivate));
        }

        [Fact]
        public void MapReason_ShowOnDeactivate_MapsToHostedReason()
        {
            Assert.Equal(
                HostedPanelLifecycleReason.ShowOnDeactivate,
                HostedPanelLifecycleAdapter.MapReasonForTest(ShowPanelReason.ShowOnDeactivate));
        }

        [Fact]
        public void Reconcile_UsesInjectedVisibilityQuery()
        {
            var visibility = new FakeVisibilityQuery { Visible = false };
            var adapter = new HostedPanelLifecycleAdapter(typeof(Form), visibility);
            var decisions = new List<HostedSurfaceDecision>();

            adapter.PanelShown(10, ShowPanelReason.Show);
            adapter.ReconcileForTest(
                "10:test:1",
                isSelectedTab: true,
                isHostReady: true,
                decisions.Add);

            Assert.Equal(typeof(Form), visibility.LastPanelType);
            Assert.Single(decisions);
            Assert.NotEqual(HostedSurfaceAction.Show, decisions[0].Action);
        }

        [Fact]
        public void PanelHidden_HideOnDeactivate_DoesNotHideOrCleanup()
        {
            var adapter = new HostedPanelLifecycleAdapter(typeof(Form), new FakeVisibilityQuery());
            var decisions = new List<HostedSurfaceDecision>();

            adapter.PanelHidden(10, ShowPanelReason.HideOnDeactivate);
            adapter.ReconcileForTest(
                "10:test:1",
                isSelectedTab: true,
                isHostReady: true,
                decisions.Add);

            Assert.Single(decisions);
            Assert.NotEqual(HostedSurfaceAction.Hide, decisions[0].Action);
            Assert.NotEqual(HostedSurfaceAction.Close, decisions[0].Action);
        }

        [Fact]
        public void PanelClosing_ClosesOnlyWhenSurfaceIsReconciled()
        {
            var adapter = new HostedPanelLifecycleAdapter(typeof(Form), new FakeVisibilityQuery());
            var decisions = new List<HostedSurfaceDecision>();

            adapter.PanelClosing(10, onCloseDocument: false);
            Assert.Empty(decisions);

            adapter.ReconcileForTest(
                "10:test:1",
                isSelectedTab: true,
                isHostReady: true,
                decisions.Add);

            Assert.Single(decisions);
            Assert.Equal(HostedSurfaceAction.Close, decisions[0].Action);
        }

        [Fact]
        public void Reconcile_Defer_CoalescesPendingRetryPerSurface()
        {
            var scheduler = new TestScheduler();
            var adapter = new HostedPanelLifecycleAdapter(
                typeof(Form),
                new FakeVisibilityQuery(),
                scheduler.Schedule);
            var decisions = new List<HostedSurfaceDecision>();

            adapter.PanelShown(10, ShowPanelReason.Show);
            adapter.ReconcileForTest(
                "10:test:1",
                isSelectedTab: true,
                readinessProvider: () => false,
                decisions.Add);
            adapter.ReconcileForTest(
                "10:test:1",
                isSelectedTab: true,
                readinessProvider: () => false,
                decisions.Add);

            Assert.Equal(1, scheduler.PendingCount);
            Assert.Equal(1, scheduler.ScheduleCount);
        }

        [Fact]
        public void Reconcile_DeferAttemptIncrementsWhenRetryExecutes()
        {
            var scheduler = new TestScheduler();
            var readiness = new SequenceReadinessProvider(false, false);
            var adapter = new HostedPanelLifecycleAdapter(
                typeof(Form),
                new FakeVisibilityQuery(),
                scheduler.Schedule);
            var decisions = new List<HostedSurfaceDecision>();

            adapter.PanelShown(10, ShowPanelReason.Show);
            adapter.ReconcileForTest(
                "10:test:1",
                isSelectedTab: true,
                readinessProvider: readiness.Next,
                decisions.Add);
            scheduler.Run("10:test:1");

            Assert.Contains(decisions, d =>
                d.Action == HostedSurfaceAction.Defer && d.DeferAttempt == 1);
        }

        [Fact]
        public void Reconcile_DeferredRetryRecapturesReadinessAndCanShow()
        {
            var scheduler = new TestScheduler();
            var readiness = new SequenceReadinessProvider(false, true);
            var adapter = new HostedPanelLifecycleAdapter(
                typeof(Form),
                new FakeVisibilityQuery(),
                scheduler.Schedule);
            var decisions = new List<HostedSurfaceDecision>();

            adapter.PanelShown(10, ShowPanelReason.Show);
            adapter.ReconcileForTest(
                "10:test:1",
                isSelectedTab: true,
                readinessProvider: readiness.Next,
                decisions.Add);
            scheduler.Run("10:test:1");

            Assert.Equal(HostedSurfaceAction.Defer, decisions[0].Action);
            Assert.Equal(HostedSurfaceAction.Show, decisions[1].Action);
        }

        [Fact]
        public void ForgetSurface_RemovesPendingRetryAndPreventsLaterApply()
        {
            var scheduler = new TestScheduler();
            var readiness = new SequenceReadinessProvider(false, true);
            var adapter = new HostedPanelLifecycleAdapter(
                typeof(Form),
                new FakeVisibilityQuery(),
                scheduler.Schedule);
            var decisions = new List<HostedSurfaceDecision>();

            adapter.PanelShown(10, ShowPanelReason.Show);
            adapter.ReconcileForTest(
                "10:test:1",
                isSelectedTab: true,
                readinessProvider: readiness.Next,
                decisions.Add);
            adapter.ForgetSurface("10:test:1");
            scheduler.Run("10:test:1");

            Assert.Single(decisions);
            Assert.Equal(HostedSurfaceAction.Defer, decisions[0].Action);
        }

        [Fact]
        public void Reconcile_LaterLifecycleEventResetsDeferBudget()
        {
            var scheduler = new TestScheduler();
            var adapter = new HostedPanelLifecycleAdapter(
                typeof(Form),
                new FakeVisibilityQuery(),
                scheduler.Schedule);
            var decisions = new List<HostedSurfaceDecision>();

            adapter.PanelShown(10, ShowPanelReason.Show);
            adapter.SetDeferAttemptForTest("10:test:1", HostedPanelLifecycleCoordinator.MaxDeferAttempts);
            adapter.PanelShown(10, ShowPanelReason.Show);
            adapter.ReconcileForTest(
                "10:test:1",
                isSelectedTab: true,
                readinessProvider: () => false,
                decisions.Add);

            var last = decisions[decisions.Count - 1];
            Assert.Equal(HostedSurfaceAction.Defer, last.Action);
            Assert.Equal(0, last.DeferAttempt);
        }

        [Fact]
        public void Trace_IsDisabledByDefault()
        {
            Assert.False(HostedPanelLifecycleTrace.IsEnabled());
        }
    }
}
