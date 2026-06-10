using System;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace Rook.UI.Web
{
    /// <summary>
    /// Side-effect boundary for the reconciler. RookWebSurface implements
    /// this over WebView2; tests implement it as a scripted fake.
    /// All members are called on the serialized reconcile flow only.
    /// </summary>
    internal interface IPresentationHost
    {
        /// <summary>Structured visibility probe; never throws.</summary>
        Task<PresentationProbeReport> ProbeAsync();
        bool TrySetControllerVisible(bool visible);
        bool TrySetControllerBounds();
        void NotifyParentWindowPositionChanged();
        void ReloadWebView();
        /// <summary>Injectable delay (RepairGapMs etc.). Tests return completed task.</summary>
        Task DelayAsync(int milliseconds);
        void Record(string evt, string detail);   // diagnostics ring hook
    }

    internal enum ReconcileDisposition
    {
        NoOpHealthy,
        Repaired,              // includes recovered-after-reload
        DegradedHidden,        // persistent RendererHidden — NEVER reload
        DegradedUnresponsive,  // post-reload confirm still bad
        DurablyHidden,         // DesiredVisible=false → controller hidden
        SkippedInactive,       // queued for next activation
        AbortedStale,          // generation changed mid-flight
        CoalescedPending       // arrived mid-reconcile; latched, runs after
    }

    internal static class ReconcilerTiming
    {
        public const int RepairGapMs = 200;
        public const int ConfirmDelayMs = 500;
        public const int ProbeTimeoutMs = 2000;       // enforced by host impl
        public const int ReloadConfirmDelayMs = 3000;
        public const int MaxRepairAttemptsPerTrigger = 2;
        public const int MaxReloadsPerTrigger = 1;
    }
}

namespace Rook.UI.Web
{
    /// <summary>
    /// Level-triggered presentation reconciler (spec 2026-06-10). Single
    /// in-flight reconcile per surface; callers serialize on the UI thread.
    /// Owns NO host probing logic — IPresentationHost is the boundary.
    /// </summary>
    internal sealed class WebViewPresentationReconciler
    {
        private readonly IPresentationHost _host;
        private long _generation;
        private bool _reconciling;

        public WebViewPresentationReconciler(IPresentationHost host)
        {
            _host = host ?? throw new ArgumentNullException(nameof(host));
        }

        public bool DesiredVisible { get; private set; }
        public bool AppActive { get; private set; }
        public bool HasPendingInactiveRequest { get; private set; }
        public long Generation => _generation;

        public void SetDesiredVisible(bool visible, string reason)
        {
            if (DesiredVisible == visible) return;
            DesiredVisible = visible;
            _generation++;
            _host.Record("desired-visible", visible + ";" + reason);
        }

        public void SetAppActive(bool active)
        {
            if (AppActive == active) return;
            AppActive = active;
            _generation++;
        }

        /// <summary>App-activation entry point: updates state AND flushes
        /// any request that arrived while inactive.</summary>
        public async Task SetAppActiveAsync(bool active)
        {
            SetAppActive(active);
            if (active && HasPendingInactiveRequest)
            {
                HasPendingInactiveRequest = false;
                await ReconcileAsync("flush-inactive-request");
            }
        }

        private string? _pendingReason;

        public async Task<ReconcileDisposition> ReconcileAsync(string reason)
        {
            if (_reconciling)
            {
                // Latest-wins latch: never drop a trigger that lands while a
                // reconcile (e.g. a repair gap) is in flight.
                _pendingReason = reason;
                return ReconcileDisposition.CoalescedPending;
            }

            _reconciling = true;
            try
            {
                var disposition = await ReconcileCoreAsync(reason);
                while (_pendingReason != null)
                {
                    var next = _pendingReason;
                    _pendingReason = null;
                    disposition = await ReconcileCoreAsync(next);
                }
                return disposition;
            }
            finally
            {
                _reconciling = false;
                _pendingReason = null;
            }
        }

        private async Task<ReconcileDisposition> ReconcileCoreAsync(string reason)
        {
            if (!DesiredVisible)
            {
                _host.TrySetControllerVisible(false);
                _host.Record("durable-hide", reason);
                return ReconcileDisposition.DurablyHidden;
            }

            if (!AppActive)
            {
                HasPendingInactiveRequest = true;
                _host.Record("skip-inactive", reason);
                return ReconcileDisposition.SkippedInactive;
            }

            var gen = _generation;
            var report = await _host.ProbeAsync();
            _host.Record("probe", report.Outcome + ";" + report.PayloadJson);

            if (report.Outcome == ProbeOutcome.Healthy)
                return ReconcileDisposition.NoOpHealthy;

            if (report.Outcome == ProbeOutcome.RendererUnresponsive ||
                report.Outcome == ProbeOutcome.ProbeInvalid)
            {
                return await IssueReloadAsync(gen, reason);
            }

            // RendererHidden: bounded gapped-toggle repair.
            for (var attempt = 1; attempt <= ReconcilerTiming.MaxRepairAttemptsPerTrigger; attempt++)
            {
                var result = await RunGappedToggleAsync(gen, reason, attempt);
                if (result != null) return result.Value;

                await _host.DelayAsync(ReconcilerTiming.ConfirmDelayMs);
                if (IsStale(gen)) return ReconcileDisposition.AbortedStale;

                var confirm = await _host.ProbeAsync();
                _host.Record("confirm", attempt + ";" + confirm.Outcome);
                if (confirm.Outcome == ProbeOutcome.Healthy)
                    return ReconcileDisposition.Repaired;
                if (confirm.Outcome == ProbeOutcome.RendererUnresponsive ||
                    confirm.Outcome == ProbeOutcome.ProbeInvalid)
                    return await IssueReloadAsync(gen, reason);
            }

            // Persistent RendererHidden: legitimately-hidden hosts land here.
            // NEVER reload (spec review P1-2).
            _host.Record("degraded-hidden", reason);
            return ReconcileDisposition.DegradedHidden;
        }

        /// <returns>null to continue; a disposition to stop.</returns>
        private async Task<ReconcileDisposition?> RunGappedToggleAsync(
            long gen, string reason, int attempt)
        {
            _host.Record("repair-attempt", attempt + ";" + reason);
            _host.TrySetControllerVisible(false);
            await _host.DelayAsync(ReconcilerTiming.RepairGapMs);
            if (IsStale(gen))
            {
                _host.Record("repair-aborted-stale", attempt.ToString());
                return ReconcileDisposition.AbortedStale;
            }
            _host.TrySetControllerVisible(true);
            _host.TrySetControllerBounds();
            _host.NotifyParentWindowPositionChanged();
            return null;
        }

        /// <summary>
        /// One bounded reload, then an in-core confirmation that runs after
        /// ReloadConfirmDelayMs INDEPENDENT of DocumentLoaded (spec review
        /// P1: zero-event document rebuilds must still be confirmed).
        /// DocumentLoaded remains an additional external trigger.
        /// </summary>
        private async Task<ReconcileDisposition> IssueReloadAsync(long gen, string reason)
        {
            _host.Record("reload", reason);
            _host.ReloadWebView();
            await _host.DelayAsync(ReconcilerTiming.ReloadConfirmDelayMs);
            if (IsStale(gen)) return ReconcileDisposition.AbortedStale;

            var confirm = await _host.ProbeAsync();
            _host.Record("reload-confirm", confirm.Outcome.ToString());
            if (confirm.Outcome == ProbeOutcome.Healthy)
                return ReconcileDisposition.Repaired;

            _host.Record("degraded-unresponsive", reason);
            return ReconcileDisposition.DegradedUnresponsive;
        }

        private bool IsStale(long gen) => gen != _generation || !DesiredVisible;
    }
}
