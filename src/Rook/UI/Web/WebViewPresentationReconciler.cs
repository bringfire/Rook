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

        // Suspect-cycle forced repair (spec addendum 2026-06-10 evening):
        // app deactivation marks the surface suspect; the next valid
        // activation idle runs ONE probe-independent forced toggle. The
        // desired-visible generation is tracked separately from
        // _generation because app-active flips bump _generation on every
        // deactivate/activate cycle — the exact cycle the suspect mark
        // must survive. Only a desired-visible change invalidates a mark.
        private bool _suspect;
        private long _desiredGeneration;
        private long _suspectDesiredGeneration = -1;

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
            _desiredGeneration++;
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

        // Typed pending latch: a trigger landing mid-reconcile is never
        // dropped, and a pending FORCED repair is never downgraded to a
        // normal probe-gated pass by a later normal trigger.
        private string? _pendingReason;
        private bool _pendingForced;

        public Task<ReconcileDisposition> ReconcileAsync(string reason)
            => RunSerializedAsync(reason, forced: false);

        /// <summary>
        /// Operator-forced repair (typed repair op / command path): runs
        /// the gapped toggle WITHOUT the probe gate, under the same
        /// generation guards as the trigger-driven repair sequence, then
        /// one confirmation probe. Accepted-and-scheduled callers read the
        /// outcome from the diagnostics ring (the dump op is the result
        /// channel); the disposition is also returned for direct callers.
        /// If a reconcile is already in flight, the forced request latches
        /// and the FORCED pass (not a normal one) runs after it completes.
        /// </summary>
        public Task<ReconcileDisposition> ForceRepairAsync(string reason)
        {
            _host.Record("forced-repair", reason);
            return RunSerializedAsync(reason, forced: true);
        }

        /// <summary>
        /// Marks the surface suspect after an app deactivation: a repair
        /// executed during host churn can renderer-succeed and
        /// compositor-fail, so the next valid activation idle runs one
        /// probe-independent forced toggle. NO side effects beyond the
        /// flag and a ring entry; callable while inactive; idempotent
        /// (a bool — repeated marks never accumulate extra toggles).
        /// </summary>
        public void MarkSuspect(string reason)
        {
            _suspect = true;
            _suspectDesiredGeneration = _desiredGeneration;
            _host.Record("suspect-cycle", reason);
        }

        /// <summary>
        /// Activation-idle entry point. If the surface is suspect and the
        /// cycle is still valid (app active, desired visible, no
        /// desired-visible flip since the mark): clear the suspect flag
        /// and run the forced gapped toggle via
        /// <see cref="ForceRepairAsync"/> (which emits the standard
        /// forced-repair ring entries and serialized generation guards).
        /// Suspect-but-inactive KEEPS the flag (the toggle runs on the
        /// next valid activation idle); suspect-but-durably-hidden or a
        /// stale desired generation clears it and takes the normal
        /// probe-gated path.
        /// </summary>
        public Task<ReconcileDisposition> RunActivationIdleConfirmAsync()
        {
            if (_suspect && AppActive)
            {
                var stale = _suspectDesiredGeneration != _desiredGeneration;
                _suspect = false;
                if (DesiredVisible && !stale)
                {
                    _host.Record("suspect-cycle-forced-repair", "ActivationIdleConfirm");
                    return ForceRepairAsync("ActivationIdleConfirm");
                }
            }

            return ReconcileAsync("ActivationIdleConfirm");
        }

        private async Task<ReconcileDisposition> RunSerializedAsync(string reason, bool forced)
        {
            if (_reconciling)
            {
                // Latest-wins latch: never drop a trigger that lands while a
                // reconcile (e.g. a repair gap) is in flight. Forced intent
                // is sticky: a normal trigger cannot downgrade it.
                _pendingReason = reason;
                _pendingForced = _pendingForced || forced;
                return ReconcileDisposition.CoalescedPending;
            }

            _reconciling = true;
            try
            {
                var disposition = forced
                    ? await RunForcedCoreWithRecordAsync(reason)
                    : await ReconcileCoreAsync(reason);
                while (_pendingReason != null)
                {
                    var next = _pendingReason;
                    var nextForced = _pendingForced;
                    _pendingReason = null;
                    _pendingForced = false;
                    disposition = nextForced
                        ? await RunForcedCoreWithRecordAsync(next)
                        : await ReconcileCoreAsync(next);
                }
                return disposition;
            }
            finally
            {
                _reconciling = false;
                _pendingReason = null;
                _pendingForced = false;
            }
        }

        private async Task<ReconcileDisposition> RunForcedCoreWithRecordAsync(string reason)
        {
            var disposition = await ForceRepairCoreAsync(reason);
            _host.Record("forced-repair-disposition", disposition.ToString());
            return disposition;
        }

        private async Task<ReconcileDisposition> ForceRepairCoreAsync(string reason)
        {
            var gen = _generation;
            var result = await RunGappedToggleAsync(gen, reason, attempt: 1);
            if (result != null) return result.Value;

            await _host.DelayAsync(ReconcilerTiming.ConfirmDelayMs);
            if (IsStale(gen)) return ReconcileDisposition.AbortedStale;

            var confirm = await _host.ProbeAsync();
            _host.Record("confirm", "forced;" + confirm.Outcome);
            if (confirm.Outcome == ProbeOutcome.Healthy)
                return ReconcileDisposition.Repaired;
            if (confirm.Outcome == ProbeOutcome.RendererHidden)
                return ReconcileDisposition.DegradedHidden;
            return ReconcileDisposition.DegradedUnresponsive;
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
