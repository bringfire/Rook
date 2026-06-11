using System.Collections.Generic;
using System.Threading.Tasks;
using Rook.UI.Web;
using Xunit;

namespace Rook.Tests.UI.Web
{
    public class WebViewPresentationReconcilerTests
    {
        private sealed class FakeHost : IPresentationHost
        {
            public Queue<PresentationProbeReport> ProbeAnswers { get; } = new();
            public List<string> Actions { get; } = new();
            public WebViewPresentationReconciler? Reconciler; // for mid-gap mutation
            public System.Action? OnDelay;

            public Task<PresentationProbeReport> ProbeAsync()
            {
                Actions.Add("probe");
                var answer = ProbeAnswers.Count > 0
                    ? ProbeAnswers.Dequeue()
                    : new PresentationProbeReport(ProbeOutcome.Healthy, "{}");
                return Task.FromResult(answer);
            }
            public bool TrySetControllerVisible(bool visible)
            { Actions.Add("visible=" + visible); return true; }
            public bool TrySetControllerBounds()
            { Actions.Add("bounds"); return true; }
            public void NotifyParentWindowPositionChanged()
            { Actions.Add("notify"); }
            public void ReloadWebView()
            { Actions.Add("reload"); }
            public Task DelayAsync(int ms)
            { Actions.Add("delay=" + ms); OnDelay?.Invoke(); return Task.CompletedTask; }
            public List<string> Records { get; } = new();
            public void Record(string evt, string detail)
            { Records.Add(evt + ";" + detail); }
        }

        private static PresentationProbeReport Hidden() =>
            new(ProbeOutcome.RendererHidden, "{\"visibilityState\":\"hidden\"}");
        private static PresentationProbeReport Healthy() =>
            new(ProbeOutcome.Healthy, "{\"visibilityState\":\"visible\"}");
        private static PresentationProbeReport Unresponsive() =>
            PresentationProbeReport.Unresponsive("timeout");

        private static (WebViewPresentationReconciler r, FakeHost h) Make(
            bool appActive = true, bool desiredVisible = true)
        {
            var host = new FakeHost();
            var r = new WebViewPresentationReconciler(host);
            host.Reconciler = r;
            r.SetAppActive(appActive);
            r.SetDesiredVisible(desiredVisible, "test-setup");
            return (r, host);
        }

        [Fact]
        public async Task Healthy_NoSideEffects()
        {
            var (r, h) = Make();
            h.ProbeAnswers.Enqueue(Healthy());
            var d = await r.ReconcileAsync("test");
            Assert.Equal(ReconcileDisposition.NoOpHealthy, d);
            Assert.Equal(new[] { "probe" }, h.Actions);
        }

        [Fact]
        public async Task Hidden_RunsGappedToggleInExactOrder_ThenConfirms()
        {
            var (r, h) = Make();
            h.ProbeAnswers.Enqueue(Hidden());
            h.ProbeAnswers.Enqueue(Healthy()); // confirmation
            var d = await r.ReconcileAsync("test");
            Assert.Equal(ReconcileDisposition.Repaired, d);
            Assert.Equal(new[]
            {
                "probe",
                "visible=False", "delay=200", "visible=True", "bounds", "notify",
                "delay=500", "probe"
            }, h.Actions);
        }

        [Fact]
        public async Task PersistentHidden_TwoAttemptsThenDegraded_NeverReload()
        {
            var (r, h) = Make();
            for (var i = 0; i < 3; i++) h.ProbeAnswers.Enqueue(Hidden());
            var d = await r.ReconcileAsync("test");
            Assert.Equal(ReconcileDisposition.DegradedHidden, d);
            Assert.DoesNotContain("reload", h.Actions);
            Assert.Equal(2, h.Actions.FindAll(a => a == "visible=False").Count);
        }

        [Fact]
        public async Task Unresponsive_Reloads_ThenConfirmsHealthy_IsRepaired()
        {
            var (r, h) = Make();
            h.ProbeAnswers.Enqueue(Unresponsive());
            h.ProbeAnswers.Enqueue(Healthy()); // post-reload confirmation probe
            var d = await r.ReconcileAsync("test");
            Assert.Equal(ReconcileDisposition.Repaired, d);
            Assert.Equal(1, h.Actions.FindAll(a => a == "reload").Count);
            Assert.Contains("delay=3000", h.Actions); // ReloadConfirmDelayMs, no DocumentLoaded needed
        }

        [Fact]
        public async Task Unresponsive_ReloadConfirmStillBad_DegradedOneReloadOnly()
        {
            var (r, h) = Make();
            h.ProbeAnswers.Enqueue(Unresponsive());
            h.ProbeAnswers.Enqueue(Unresponsive()); // post-reload confirm also bad
            var d = await r.ReconcileAsync("test");
            Assert.Equal(ReconcileDisposition.DegradedUnresponsive, d);
            Assert.Equal(1, h.Actions.FindAll(a => a == "reload").Count); // never two
        }

        [Fact]
        public async Task ProbeInvalid_TakesReloadPath()
        {
            var (r, h) = Make();
            h.ProbeAnswers.Enqueue(new PresentationProbeReport(ProbeOutcome.ProbeInvalid, "junk"));
            h.ProbeAnswers.Enqueue(Healthy());
            Assert.Equal(ReconcileDisposition.Repaired, await r.ReconcileAsync("test"));
            Assert.Contains("reload", h.Actions);
        }

        [Fact]
        public async Task TriggerDuringRepairGap_CoalescesAndRunsAfter()
        {
            var (r, h) = Make();
            h.ProbeAnswers.Enqueue(Hidden());   // first reconcile: needs repair
            h.ProbeAnswers.Enqueue(Healthy());  // first reconcile: confirm
            h.ProbeAnswers.Enqueue(Healthy());  // coalesced second reconcile: probe
            var fired = false;
            h.OnDelay = () =>
            {
                if (fired) return;
                fired = true;
                // A trigger lands mid-gap: must NOT be dropped.
                var d2 = r.ReconcileAsync("second-trigger").Result;
                Assert.Equal(ReconcileDisposition.CoalescedPending, d2);
            };
            await r.ReconcileAsync("first-trigger");
            // Three probes total: first, confirm, and the coalesced re-run.
            Assert.Equal(3, h.Actions.FindAll(a => a == "probe").Count);
        }

        [Fact]
        public async Task GenerationBumpDuringGap_AbortsBeforeReShow()
        {
            var (r, h) = Make();
            h.ProbeAnswers.Enqueue(Hidden());
            h.OnDelay = () => r.SetDesiredVisible(false, "closed-mid-gap");
            var d = await r.ReconcileAsync("test");
            Assert.Equal(ReconcileDisposition.AbortedStale, d);
            Assert.Contains("visible=False", h.Actions);
            Assert.DoesNotContain("visible=True", h.Actions); // never re-shown
        }

        [Fact]
        public async Task DurableHide_HidesControllerWithoutProbeOrToggle()
        {
            var (r, h) = Make(desiredVisible: false);
            var d = await r.ReconcileAsync("test");
            Assert.Equal(ReconcileDisposition.DurablyHidden, d);
            Assert.Equal(new[] { "visible=False" }, h.Actions); // no probe
        }

        [Fact]
        public async Task InactiveApp_SkipsAndRunsOnNextActivation()
        {
            var (r, h) = Make(appActive: false);
            var d = await r.ReconcileAsync("while-inactive");
            Assert.Equal(ReconcileDisposition.SkippedInactive, d);
            Assert.Empty(h.Actions);
            Assert.True(r.HasPendingInactiveRequest);

            h.ProbeAnswers.Enqueue(Healthy());
            await r.SetAppActiveAsync(true); // flush
            Assert.Contains("probe", h.Actions);
            Assert.False(r.HasPendingInactiveRequest);
        }

        [Fact]
        public async Task ForceRepair_RunsGappedToggleWithoutProbeGate_ThenConfirms()
        {
            // Mirrors Hidden_RunsGappedToggleInExactOrder_ThenConfirms
            // minus the leading probe: forced repair never probe-gates.
            var (r, h) = Make();
            h.ProbeAnswers.Enqueue(Healthy()); // confirmation probe only
            var d = await r.ForceRepairAsync("operator-repair");
            Assert.Equal(ReconcileDisposition.Repaired, d);
            Assert.Equal(new[]
            {
                "visible=False", "delay=200", "visible=True", "bounds", "notify",
                "delay=500", "probe"
            }, h.Actions);
            Assert.Contains("forced-repair;operator-repair", h.Records);
            Assert.Contains("forced-repair-disposition;Repaired", h.Records);
        }

        [Fact]
        public async Task ForceRepair_GenerationBumpDuringGap_AbortsBeforeReShow()
        {
            var (r, h) = Make();
            h.OnDelay = () => r.SetDesiredVisible(false, "closed-mid-gap");
            var d = await r.ForceRepairAsync("operator-repair");
            Assert.Equal(ReconcileDisposition.AbortedStale, d);
            Assert.Contains("visible=False", h.Actions);
            Assert.DoesNotContain("visible=True", h.Actions); // never re-shown
        }

        [Fact]
        public async Task RendererHiddenNeverChangesDesiredVisible()
        {
            var (r, h) = Make();
            for (var i = 0; i < 3; i++) h.ProbeAnswers.Enqueue(Hidden());
            await r.ReconcileAsync("test");
            Assert.True(r.DesiredVisible);
        }

        [Fact]
        public async Task ForceRepairDuringReconcile_CoalescesButRunsForcedToggleAfter()
        {
            var (r, h) = Make();
            h.ProbeAnswers.Enqueue(Hidden());   // first reconcile: enters repair
            h.ProbeAnswers.Enqueue(Healthy());  // first reconcile: confirm -> Repaired
            h.ProbeAnswers.Enqueue(Healthy());  // forced pass: confirmation probe
            var fired = false;
            h.OnDelay = () =>
            {
                if (fired) return;
                fired = true;
                // Operator repair lands mid-flight: must latch as FORCED,
                // not degrade into a normal probe-gated reconcile.
                var d2 = r.ForceRepairAsync("operator-mid-flight").Result;
                Assert.Equal(ReconcileDisposition.CoalescedPending, d2);
            };
            var d = await r.ReconcileAsync("first");
            Assert.Equal(ReconcileDisposition.Repaired, d);
            // Forced toggle ran after the first pass: two hide/show toggles
            // total (first repair attempt + forced repair), and the forced
            // pass has NO leading probe (3 probes: initial, confirm, forced
            // confirm — a downgraded normal pass would have probed first
            // and no-opped on Healthy with only a single toggle).
            Assert.Equal(2, h.Actions.FindAll(a => a == "visible=False").Count);
            Assert.Equal(3, h.Actions.FindAll(a => a == "probe").Count);
        }

        [Fact]
        public async Task TriggerDuringForcedRepair_RunsNormalReconcileAfter()
        {
            var (r, h) = Make();
            h.ProbeAnswers.Enqueue(Healthy());  // forced pass: confirmation probe
            h.ProbeAnswers.Enqueue(Healthy());  // queued normal reconcile: probe
            var fired = false;
            h.OnDelay = () =>
            {
                if (fired) return;
                fired = true;
                // A normal trigger landing during a forced repair must not
                // be dropped on completion.
                var d2 = r.ReconcileAsync("trigger-mid-forced").Result;
                Assert.Equal(ReconcileDisposition.CoalescedPending, d2);
            };
            var d = await r.ForceRepairAsync("operator");
            Assert.Equal(ReconcileDisposition.NoOpHealthy, d);
            Assert.Equal(2, h.Actions.FindAll(a => a == "probe").Count);
        }
    }
}
