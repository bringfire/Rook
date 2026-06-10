# WebView Presentation Reconciler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the probe-gated WebView2 presentation coordinator with a level-triggered, generation-guarded presentation reconciler shared by all `RookWebSurface` panels, per the approved spec `docs/superpowers/specs/2026-06-10-webview-presentation-reconciler-design.md` (commits `5d95e60` + `f28db78`).

**Architecture:** A pure `WebViewPresentationReconciler` (decision logic against an injected `IPresentationHost`) is built TDD-first, then wired into `RookWebSurface` (probe = `ExecuteScriptAsync` of `document.visibilityState` payload; repair = gapped `IsVisible` toggle). Durable desired-visible mapping is a pure per-surface policy. The old coordinator stack is deleted only after the new path and the typed dump/repair route are proven.

**Tech Stack:** C# (net48 + net8.0 multi-target `Rook.rhp`), xunit (`Rook.Tests`, net48, `InternalsVisibleTo` already present), Rhino 8 / Eto-WPF / WebView2, Python MCP server (`mcp_server/src/rook/server.py`).

**Conventions:** branch `fix/webview-presentation-reconciler`; frequent small commits; squash-merge PR at the end; live smoke before PR open. Tests run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -v minimal`.

---

### Task 0: Branch

- [ ] **Step 0.1:** `git checkout -b fix/webview-presentation-reconciler` (from current `main`, which already contains the spec commits).

---

### Task 1: Live checkpoint A — does dock-tab reselect emit `PanelShown`? (NO CODE YET)

Spec dependency: the trigger table assumes reselecting a tabbed-behind dedicated panel fires `PanelShown`. Verify in live Rhino BEFORE building, so trigger coverage is designed on facts. (Codex planning note 1.)

**Files:** none (uses existing `HostedPanelLifecycleTrace`).

- [ ] **Step 1.1:** Launch Rhino with tracing:
```powershell
$env:ROOK_PANEL_LIFECYCLE_TRACE='1'; & "C:\Program Files\Rhino 8\System\Rhino.exe"
```
- [ ] **Step 1.2:** In Rhino: open RookVision and Knowledge Graph, dock them into ONE tab group. Select Knowledge (Vision tabbed behind), wait 2s, reselect Vision. Repeat 3×. Also repeat once with the group floating.
- [ ] **Step 1.3:** Read the trace:
```powershell
Get-Content "$env:APPDATA\Rook\logs\panel-lifecycle.log" -Tail 60
```
Expected: the trace records `event=Reconcile` / `event=DeferredRetry` lines (NOT a literal `PanelShown` event). A reselect that flowed through `PanelShown` appears as `panel=RookVisionPanel ... event=Reconcile ... reason=Show` (or `ShowOnDeactivate`) at the reselect timestamp. Correlate timestamps with your reselect actions.
- [ ] **Step 1.4:** Record the verdict at the END of this plan file under "Checkpoint A verdict". If `PanelShown` does NOT fire on reselect: Task 7 must additionally subscribe Eto `Shown` and rely on `GotFocus`/`SizeChanged` (already in the trigger table) — note which events DID appear in the trace at reselect and list them in the verdict so Task 7 wires them.
- [ ] **Step 1.5:** Close Rhino; clear the env var (`Remove-Item Env:ROOK_PANEL_LIFECYCLE_TRACE`).

---

### Task 2: Probe report parser (pure, TDD)

WebView2 `ExecuteScriptAsync` returns a JSON-encoded *string* containing JSON — double-decode required (spec P2 finding).

**Files:**
- Create: `src/Rook/UI/Web/PresentationProbeReport.cs`
- Test: `src/Rook.Tests/UI/Web/PresentationProbeReportTests.cs`

- [ ] **Step 2.1: Write failing tests**
```csharp
using Rook.UI.Web;
using Xunit;

namespace Rook.Tests.UI.Web
{
    public class PresentationProbeReportTests
    {
        // ExecuteScriptAsync wraps the JSON.stringify result in ANOTHER layer
        // of JSON string encoding: "\"{\\\"visibilityState\\\":...}\""
        private static string Wrap(string inner) =>
            System.Text.Json.JsonSerializer.Serialize(inner);

        [Fact]
        public void Visible_ParsesHealthy()
        {
            var raw = Wrap("{\"visibilityState\":\"visible\",\"hidden\":false,\"readyState\":\"complete\",\"hasRoot\":true,\"viewport\":[100,50],\"appRect\":null}");
            var report = PresentationProbeReport.Parse(raw);
            Assert.Equal(ProbeOutcome.Healthy, report.Outcome);
        }

        [Fact]
        public void Hidden_ParsesRendererHidden()
        {
            var raw = Wrap("{\"visibilityState\":\"hidden\",\"hidden\":true,\"readyState\":\"complete\",\"hasRoot\":true,\"viewport\":[100,50],\"appRect\":null}");
            Assert.Equal(ProbeOutcome.RendererHidden, PresentationProbeReport.Parse(raw).Outcome);
        }

        [Fact]
        public void SingleEncoded_StillParses()
        {
            // Defensive: some hosts hand back the inner JSON directly.
            var raw = "{\"visibilityState\":\"visible\"}";
            Assert.Equal(ProbeOutcome.Healthy, PresentationProbeReport.Parse(raw).Outcome);
        }

        [Theory]
        [InlineData(null)]
        [InlineData("")]
        [InlineData("null")]
        [InlineData("\"null\"")]
        [InlineData("not json at all")]
        [InlineData("\"{\\\"visibilityState\\\":42}\"")]
        public void Malformed_IsProbeInvalid(string raw)
        {
            Assert.Equal(ProbeOutcome.ProbeInvalid, PresentationProbeReport.Parse(raw).Outcome);
        }

        [Fact]
        public void RawPayloadPreservedForDiagnostics()
        {
            var raw = Wrap("{\"visibilityState\":\"hidden\"}");
            Assert.Contains("hidden", PresentationProbeReport.Parse(raw).PayloadJson);
        }
    }
}
```
- [ ] **Step 2.2:** Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter PresentationProbeReportTests -v minimal` — Expected: FAIL (types missing).
- [ ] **Step 2.3: Implement**
```csharp
using System.Text.Json;

namespace Rook.UI.Web
{
    internal enum ProbeOutcome
    {
        Healthy,
        RendererHidden,
        RendererUnresponsive,
        ProbeInvalid
    }

    internal sealed record PresentationProbeReport(
        ProbeOutcome Outcome,
        string PayloadJson)
    {
        public static PresentationProbeReport Unresponsive(string detail) =>
            new(ProbeOutcome.RendererUnresponsive, detail);

        /// <summary>
        /// Parses an ExecuteScriptAsync result. WebView2 returns the script
        /// result JSON-encoded (a JSON string containing JSON), so this
        /// unquotes one layer when present, then parses the payload.
        /// Anything undecodable is ProbeInvalid, never an exception.
        /// </summary>
        public static PresentationProbeReport Parse(string? raw)
        {
            if (string.IsNullOrWhiteSpace(raw) || raw == "null")
                return new PresentationProbeReport(ProbeOutcome.ProbeInvalid, raw ?? "");

            var payload = raw!;
            try
            {
                // Unwrap the outer JSON-string layer if present.
                if (payload.Length > 0 && payload[0] == '"')
                {
                    var inner = JsonSerializer.Deserialize<string>(payload);
                    if (inner == null)
                        return new PresentationProbeReport(ProbeOutcome.ProbeInvalid, payload);
                    payload = inner;
                }

                using var doc = JsonDocument.Parse(payload);
                if (doc.RootElement.ValueKind != JsonValueKind.Object ||
                    !doc.RootElement.TryGetProperty("visibilityState", out var vis) ||
                    vis.ValueKind != JsonValueKind.String)
                {
                    return new PresentationProbeReport(ProbeOutcome.ProbeInvalid, payload);
                }

                var outcome = vis.GetString() == "visible"
                    ? ProbeOutcome.Healthy
                    : ProbeOutcome.RendererHidden;
                return new PresentationProbeReport(outcome, payload);
            }
            catch (JsonException)
            {
                return new PresentationProbeReport(ProbeOutcome.ProbeInvalid, payload);
            }
        }
    }
}
```
- [ ] **Step 2.4:** Run same filter — Expected: PASS (note: `"null"` literal parses to JSON null → ValueKind not Object → ProbeInvalid; `"\"null\""` unwraps to string "null" → JsonException path or non-object → ProbeInvalid).
- [ ] **Step 2.5:** `git add -A; git commit -m "feat: presentation probe report parser"`

---

### Task 3: Pure reconciler with decision-table tests (TDD)

**Files:**
- Create: `src/Rook/UI/Web/WebViewPresentationReconciler.cs`
- Test: `src/Rook.Tests/UI/Web/WebViewPresentationReconcilerTests.cs`

The reconciler is async but fully deterministic in tests: the host fake controls probe answers and delays complete synchronously.

- [ ] **Step 3.1: Write the host contract (compiles first — tests reference it)**

In `WebViewPresentationReconciler.cs`:
```csharp
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
```

- [ ] **Step 3.2: Write failing tests**
```csharp
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
            public void Record(string evt, string detail) { }
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
        public async Task RendererHiddenNeverChangesDesiredVisible()
        {
            var (r, h) = Make();
            for (var i = 0; i < 3; i++) h.ProbeAnswers.Enqueue(Hidden());
            await r.ReconcileAsync("test");
            Assert.True(r.DesiredVisible);
        }
    }
}
```
- [ ] **Step 3.3:** Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter WebViewPresentationReconcilerTests -v minimal` — Expected: FAIL (reconciler class missing).
- [ ] **Step 3.4: Implement the reconciler** (append to `WebViewPresentationReconciler.cs`)
```csharp
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
```
- [ ] **Step 3.5:** Run filter — Expected: PASS. (If `GenerationBumpDuringGap` fails: `SetDesiredVisible(false)` both bumps generation AND flips desired — `IsStale` covers both.)
- [ ] **Step 3.6:** Commit: `git add -A; git commit -m "feat: pure webview presentation reconciler"`

---

### Task 4: Desired-visible mapping policy (pure, TDD)

Implements the spec's per-surface table. Dedicated panels: probe-driven hide is never durable.

**Files:**
- Create: `src/Rook/UI/Web/PanelDesiredVisibilityPolicy.cs`
- Test: `src/Rook.Tests/UI/Web/PanelDesiredVisibilityPolicyTests.cs`

- [ ] **Step 4.1: Failing tests**
```csharp
using Rhino.UI;
using Rook.UI.Web;
using Xunit;

namespace Rook.Tests.UI.Web
{
    public class PanelDesiredVisibilityPolicyTests
    {
        [Fact]
        public void PanelClosing_IsDurableHide() =>
            Assert.Equal(DesiredVisibilityChange.DurablyHidden,
                PanelDesiredVisibilityPolicy.OnPanelClosing());

        [Theory]
        [InlineData(ShowPanelReason.Show)]
        [InlineData(ShowPanelReason.ShowOnDeactivate)]
        public void PanelShown_IsVisible(ShowPanelReason reason) =>
            Assert.Equal(DesiredVisibilityChange.Visible,
                PanelDesiredVisibilityPolicy.OnPanelShown(reason));

        [Fact]
        public void HideOnDeactivate_NeverDurable() =>
            Assert.Equal(DesiredVisibilityChange.NoChange,
                PanelDesiredVisibilityPolicy.OnPanelHidden(
                    ShowPanelReason.HideOnDeactivate, visibleAnyTab: false));

        [Fact]
        public void Hide_WhileStillVisibleAnywhere_NotDurable() =>
            Assert.Equal(DesiredVisibilityChange.NoChange,
                PanelDesiredVisibilityPolicy.OnPanelHidden(
                    ShowPanelReason.Hide, visibleAnyTab: true));

        [Fact]
        public void Hide_NotVisibleAnywhere_IsDurable() =>
            Assert.Equal(DesiredVisibilityChange.DurablyHidden,
                PanelDesiredVisibilityPolicy.OnPanelHidden(
                    ShowPanelReason.Hide, visibleAnyTab: false));
    }
}
```
- [ ] **Step 4.2:** Run filter `PanelDesiredVisibilityPolicyTests` — Expected: FAIL.
- [ ] **Step 4.3: Implement**
```csharp
using Rhino.UI;

namespace Rook.UI.Web
{
    internal enum DesiredVisibilityChange { NoChange, Visible, DurablyHidden }

    /// <summary>
    /// Per-surface durable desired-visible mapping (spec table, f28db78).
    /// Dedicated panels only — Chat internal tabs are governed by Chat's
    /// own TabControl.SelectedIndex, not by this policy.
    /// Probe-driven/selected-tab/HWND readings NEVER reach this policy.
    /// </summary>
    internal static class PanelDesiredVisibilityPolicy
    {
        public static DesiredVisibilityChange OnPanelShown(ShowPanelReason reason)
            => DesiredVisibilityChange.Visible;

        public static DesiredVisibilityChange OnPanelHidden(
            ShowPanelReason reason, bool visibleAnyTab)
        {
            if (reason == ShowPanelReason.HideOnDeactivate)
                return DesiredVisibilityChange.NoChange;
            return visibleAnyTab
                ? DesiredVisibilityChange.NoChange
                : DesiredVisibilityChange.DurablyHidden;
        }

        public static DesiredVisibilityChange OnPanelClosing()
            => DesiredVisibilityChange.DurablyHidden;
    }
}
```
- [ ] **Step 4.4:** Run filter — Expected: PASS.
- [ ] **Step 4.5:** Commit: `git add -A; git commit -m "feat: per-surface desired-visible policy"`

---

### Task 5: Typed dump/repair ops (BEFORE deleting anything)

Adds `get_presentation_diagnostics` and `repair_presentation` as vision-dispatch ops, reachable END-TO-END: MCP tool → NEW native C++ route → P/Invoke `vision_dispatch` → managed handler → **all-surface registry** (not Vision-only). `repair_presentation` runs the gapped toggle REGARDLESS of probe result (operator-forced path).

**Files:**
- Create: `src/Rook/UI/Web/WebSurfacePresentationRegistry.cs` (substrate-level registry — spec requires Chat/Knowledge coverage, so Vision-only static enumeration is insufficient)
- Modify: `src/Rook/UI/Web/RookWebSurface.cs` (assign `SurfaceId = ResourceRoot + ":" + counter`; `Register` in `CreateWebContent`, `Deregister` in `Dispose`)
- Modify: `src/Rook/UI/Vision/VisionWebSurface.cs` (OpRoutes ~line 176; both new ops `VisionOpRoute.Ui`)
- Modify: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs` (`ExpectedVisionOps` set ~line 73; switch ~line 1625 → UI-thread branch, same as `capture_depth`)
- Modify: `src/Rook/Handlers/VisionHandler.cs` (two new ops on the Ui dispatch path; **use the file's existing `Ok(...)`/`Fail(...)` envelope helpers — do NOT invent new helper names; follow whatever the surrounding op cases use**)
- Modify: `src/RookNative/RookServer.cpp` (~line 1026, next to the `/vision/artifacts` registrations): register `POST /vision/presentation` with a STRICT `{"action":"dump"|"repair"}` contract — the native handler constructs the managed op body itself and forwards only the two known op JSONs through the `vision_dispatch` trampoline (mirror `HandleVisionGetArtifact`'s forwarding mechanics); any other action → HTTP 400; no user-controlled bytes pass through
- Modify: `mcp_server/src/rook/server.py` (new MCP tool `rhino_vision_presentation`, pattern-matched to `rhino_vision_artifacts` ~line 12046: `action` arg `dump|repair` → `call_rhino("/vision/presentation", method="POST", body={"op": ...})`; there is NO pre-existing generic `/vision/dispatch` HTTP route — the new native route above is what makes this reachable)
- Test: `src/Rook.Tests/Handlers/VisionHandlerTests.cs` (extend), `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs` (extend), `src/Rook.Tests/UI/Web/WebSurfacePresentationRegistryTests.cs` (create)

- [ ] **Step 5.0: Registry (TDD).** Failing tests first in `WebSurfacePresentationRegistryTests.cs`: register two fake surfaces (test subclass of `RookWebSurface` as used by existing surface tests) → `DumpAll()` JSON contains both surface ids; dispose one → `DumpAll()` contains only the survivor; `RepairAll("test")` returns one `surfaceId:disposition` segment per live surface. Implementation:
```csharp
using System.Collections.Generic;
using System.Text.Json;

namespace Rook.UI.Web
{
    /// <summary>All live web surfaces, for substrate-wide diagnostics and
    /// operator repair. Weak registration is unnecessary: surfaces
    /// deterministically deregister in Dispose.</summary>
    internal static class WebSurfacePresentationRegistry
    {
        private static readonly object s_lock = new();
        private static readonly List<RookWebSurface> s_surfaces = new();

        public static void Register(RookWebSurface surface)
        { lock (s_lock) { if (!s_surfaces.Contains(surface)) s_surfaces.Add(surface); } }

        public static void Deregister(RookWebSurface surface)
        { lock (s_lock) { s_surfaces.Remove(surface); } }

        public static string DumpAll()
        {
            lock (s_lock)
            {
                var dump = new List<object>();
                foreach (var s in s_surfaces)
                    dump.Add(new
                    {
                        surfaceId = s.SurfaceId,
                        disposed = s.IsDisposed,
                        entries = s.GetHostPresentationDiagnosticEntries()
                    });
                return JsonSerializer.Serialize(dump,
                    new JsonSerializerOptions { WriteIndented = true });
            }
        }

        /// <summary>
        /// Fire-and-forget: schedules an async forced repair per surface on
        /// the UI thread and returns immediately. NEVER blocks on the gapped
        /// toggle (200ms gap) — outcomes land in each surface's diagnostics
        /// ring and are read via a follow-up DumpAll().
        /// </summary>
        public static string ScheduleRepairAll(string reason)
        {
            RookWebSurface[] snapshot;
            lock (s_lock) { snapshot = s_surfaces.ToArray(); }
            foreach (var s in snapshot)
                s.SchedulePresentationRepair(reason);
            return "scheduled:" + snapshot.Length;
        }
    }
}
```
(`SchedulePresentationRepair` lands on `RookWebSurface` in Step 5.4: `Application.Instance.AsyncInvoke(async () => await _reconciler.ForceRepairAsync(reason))` in try/catch — fully async, no `Invoke`, no `.Result`/`.Wait()`, no UI-thread blocking during the gap. Registry test asserts `ScheduleRepairAll` returns `scheduled:<liveCount>` and that each fake surface received exactly one scheduled-repair request.)

- [ ] **Step 5.1:** Write failing test in `VisionWebSurfaceTests.cs`: assert `VisionWebSurface.OpRoutes` contains `get_presentation_diagnostics` and `repair_presentation` mapped to `VisionOpRoute.Ui`:
```csharp
[Theory]
[InlineData("get_presentation_diagnostics")]
[InlineData("repair_presentation")]
public void PresentationOps_AreUiRouted(string op)
{
    Assert.True(VisionWebSurface.OpRoutes.TryGetValue(op, out var route));
    Assert.Equal(VisionOpRoute.Ui, route);
}
```
- [ ] **Step 5.2:** Run — FAIL. Then add both ops to `OpRoutes` (`VisionOpRoute.Ui`), to `ExpectedVisionOps` in `NativeGhBridgeRegistrar`, and to the bridge switch routing them to `Vision.Dispatch(reqJson)` (UI-thread branch, same as `capture_depth`).
- [ ] **Step 5.3:** Implement the two ops in `VisionHandler.Dispatch`'s op switch, **using the file's existing `Ok(...)`/`Fail(...)` helpers** (match the exact shape of neighboring op cases — do not introduce a new envelope helper):
```csharp
case "get_presentation_diagnostics":
    return Ok(WebSurfacePresentationRegistry.DumpAll());
case "repair_presentation":
    // Accepted-and-scheduled semantics: returns immediately; the async
    // gapped toggle runs fire-and-forget on the UI thread; outcomes are
    // recorded in the ring and read via a follow-up dump.
    return Ok(WebSurfacePresentationRegistry.ScheduleRepairAll("operator-repair"));
```
- [ ] **Step 5.4:** Implement `ForceRepairAsync` on the reconciler now (gapped toggle WITHOUT the probe gate, same generation guards, then one confirmation probe; returns the disposition; records `forced-repair` + disposition in the ring via `_host.Record`) plus a unit test mirroring `Hidden_RunsGappedToggleInExactOrder` minus the leading probe. Add `RookWebSurface.SchedulePresentationRepair(string reason)` → `Application.Instance.AsyncInvoke(async () => { try { await _reconciler.ForceRepairAsync(reason); } catch (Exception ex) { Log(...); } })`. **No synchronous `Invoke`, `.Result`, or `.Wait()` anywhere on the repair path** — the dump op is the result channel.
- [ ] **Step 5.5:** Update `RookDumpVisionPresentationStateCommand`: dump now comes from `WebSurfacePresentationRegistry.DumpAll()` (all surfaces — spec generalization); add a Rhino toggle option `Repair` (default No) via `Rhino.Input.Custom.GetOption`; when Yes, call `WebSurfacePresentationRegistry.ScheduleRepairAll("command-repair")` and print "repair scheduled (N surfaces) — run the command again to see outcomes in the dump".
- [ ] **Step 5.6 (native route):** In `src/RookNative/RookServer.cpp` register `POST /vision/presentation` next to the existing `/vision/artifacts` registrations (~line 1026). **The HTTP contract is `{"action":"dump"|"repair"}` — NOT a pass-through.** The native handler parses `action`, rejects anything else with HTTP 400, and CONSTRUCTS the managed op body itself: `action=="dump"` → forwards exactly `{"op":"get_presentation_diagnostics"}`; `action=="repair"` → forwards exactly `{"op":"repair_presentation"}` — through the same vision_dispatch forwarding mechanics as `HandleVisionGetArtifact` (response/status propagated back). No user-controlled bytes reach `vision_dispatch`; the route cannot invoke any other Vision op. Build C++: `cmd /c scripts\build-native.bat`. Expected: clean build.
- [ ] **Step 5.7 (MCP tool):** Add `rhino_vision_presentation` in `server.py`, following the `rhino_vision_artifacts` registration pattern (~line 12046): one required arg `action` (`"dump" | "repair"`), handler does `call_rhino("/vision/presentation", method="POST", body={"action": action}, port=port)`. Description: "Dump or schedule-repair WebView panel presentation state (dark-panel diagnostics); repair returns scheduled:<n> — dump again to see outcomes."
- [ ] **Step 5.8:** Run all C# tests: `dotnet test src/Rook.Tests/Rook.Tests.csproj -v minimal` — Expected: PASS. Run Python tests if present for tool registry: `python -m pytest mcp_server/tests -k vision -q`.
- [ ] **Step 5.9:** Commit: `git add -A; git commit -m "feat: typed dump/repair presentation route, registry, MCP tool"`

---

### Task 6: RookWebSurface host wiring (replace, not yet delete)

**Files:**
- Modify: `src/Rook/UI/Web/RookWebSurface.cs`

- [ ] **Step 6.1:** Add reconciler members + `IPresentationHost` implementation in an inner class `SurfacePresentationHost` next to the existing reflection helpers:
  - `ProbeAsync()` → `_coreWebView2.ExecuteScriptAsync(ProbeScript)` raced against `Task.Delay(ReconcilerTiming.ProbeTimeoutMs)` (use `Task.WhenAny`; timeout/fault/disposed → `PresentationProbeReport.Unresponsive(...)`; otherwise `PresentationProbeReport.Parse(raw)`). `ProbeScript` is the exact spec payload (visibilityState, hidden, readyState, hasRoot, viewport, appRect).
  - `TrySetControllerVisible(bool)` → existing `SetControllerVisible(controller, visible, reason)` via `TryGetCoreWebView2Controller()`.
  - `TrySetControllerBounds()` → existing `TryBuildControllerTargetBounds()` + `SetControllerBounds(...)`.
  - `NotifyParentWindowPositionChanged()` → existing private method.
  - `ReloadWebView()` → `_coreWebView2?.Reload()` in try/catch only — the post-reload confirmation lives INSIDE the reconciler (`IssueReloadAsync`, Task 3) and is unit-tested there; no host-side scheduling needed. `DocumentLoaded` remains an additional external trigger.
  - `DelayAsync(ms)` → `Task.Delay(ms)`.
  - `Record(evt, detail)` → enqueue into the existing `_hostPresentationDiagnostics` ring (reuse `WebViewHostPresentationDiagnosticEntry` with probe payload in `ActionResult`/`Reason` fields, or extend the entry record with `ProbePayload`).
- [ ] **Step 6.2:** Public surface API: `internal void RequestPresentationReconcile(string reason)` (fire-and-forget `Application.Instance.AsyncInvoke(async () => await _reconciler.ReconcileAsync(reason))`), `internal void SetPresentationDesiredVisible(bool visible, string reason)`, `internal string ForceRepairPresentation(string reason)`.
- [ ] **Step 6.3:** Wire triggers inside `RookWebSurface` (these exist already — repoint them):
  - `OnWebViewGotFocus` → `RequestPresentationReconcile("GotFocus")` (for ALL surfaces — delete the `UseHostPresentationCoordinator` early-return).
  - `OnWebViewShown` → `RequestPresentationReconcile("WebViewShown")`.
  - `OnWebViewSizeChanged` → `RequestPresentationReconcile("SizeChanged")`.
  - `OnApplicationIsActiveChanged` → `Application.Instance.AsyncInvoke(async () => await _reconciler.SetAppActiveAsync(Application.Instance.IsActive))`; when becoming active also schedule ONE one-shot `RhinoApp.Idle` confirmation reconcile (reuse the existing one-shot subscribe/unsubscribe shape from `OnHostPresentationIdle`, renamed `OnActivationIdleConfirm`).
  - `OnDocumentLoaded` → `RequestPresentationReconcile("DocumentLoaded")`.
- [ ] **Step 6.4:** Build only (no behavior tests at this layer — host code is thin adapters over tested pieces): `dotnet build src/Rook/Rook.csproj -v minimal` — Expected: success with old coordinator paths still compiling (they are unplugged in Task 7, deleted in Task 8).
- [ ] **Step 6.5:** Commit: `git add -A; git commit -m "feat: wire presentation reconciler into RookWebSurface"`

---

### Task 7: Panel wiring (Vision, Knowledge, Chat)

**Files:**
- Modify: `src/Rook/UI/Vision/RookVisionPanel.cs`
- Modify: `src/Rook/UI/Knowledge/KnowledgeGraphPanel.cs`
- Modify: `src/Rook/UI/Chat/RookChatPanel.cs` (lines ~217–290)
- Modify: `src/Rook/UI/Vision/VisionWebSurface.cs` (remove `UseHostPresentationCoordinator` override + facts refresher)
- Test: `src/Rook.Tests/UI/Vision/RookVisionPanelHostTests.cs` (rewrite to the new mapping)

- [ ] **Step 7.1:** `RookVisionPanel`: delete `VisionPanelPresentationState` usage, probes-into-facts plumbing, and `OnApplicationIsActiveChanged` (surface owns it now). `PanelShown` → `_lifecycle.PanelShown(...)`; apply `PanelDesiredVisibilityPolicy.OnPanelShown` → `_surface.SetPresentationDesiredVisible(true, ...)` + `_surface.RequestPresentationReconcile("PanelShown:" + reason)`; `PanelHidden` → policy with `visibleAnyTab` probed via existing `_visibilityQuery.IsPanelVisibleAnyTab(...)` in try/catch (probe failure → `NoChange`, never durable hide); `PanelClosing` → durable hide + close. Lifecycle adapter `Show` decision → `RequestPresentationReconcile`; `Hide` decision → ring annotation only (call `_surface.RecordPresentationAnnotation("lifecycle-hide", decision.Reason)` — add that thin method to `RookWebSurface`); `Close` decision → `CloseSurface()`. If Checkpoint A found `PanelShown` does NOT fire on reselect, also forward Eto `Shown` on the panel `Content` to `RequestPresentationReconcile("ContentShown")`.
- [ ] **Step 7.2:** `KnowledgeGraphPanel`: same mapping (it is simpler — replace `ApplyDecision`'s `ReconcileHostVisibility(true/false)` with `RequestPresentationReconcile` / annotation per the dedicated-panel table; `PanelClosing`/dispose → durable hide).
- [ ] **Step 7.3:** `RookChatPanel` (`ReconcileHostedWebSurfaces`, line ~224): selected tab (`i == tabControl.SelectedIndex`) → desired visible true + reconcile; unselected → desired visible false (per spec: Chat's own tab control is authoritative — durable per-tab). **Do not assume a `tab.Surface` property exists** — `ChatTab`/`VisionTab` currently expose `ReconcileHostVisibility(bool, string)` forwarding methods (call sites at lines 260/263/280/283). Replace those forwarding methods on the tab classes with `SetPresentationDesiredVisible(bool, string)` + `RequestPresentationReconcile(string)` forwarders to their internal surface (same forwarding pattern the tab classes already use), then update the four call sites.
- [ ] **Step 7.4:** Rewrite `RookVisionPanelHostTests` to assert: shown→desired-visible true; hidden(HideOnDeactivate)→no change; hidden(Hide)+visibleAnyTab→no change; hidden(Hide)+not visible→durable; closing→durable; probe exception→no change.
- [ ] **Step 7.5:** `dotnet test src/Rook.Tests/Rook.Tests.csproj -v minimal` — Expected: PASS except old coordinator tests (they go in Task 8). If old tests fail because plumbing was unplugged, proceed to Task 8 in the same sitting — Tasks 7+8 land as consecutive commits, the suite is green at the end of Task 8.
- [ ] **Step 7.6:** Commit: `git add -A; git commit -m "feat: panels map lifecycle to reconciler desired state"`

---

### Task 8: Delete the old coordinator stack

**Files (delete):**
- `src/Rook/UI/Web/WebViewHostPresentationCoordinator.cs`
- `src/Rook/UI/Web/WebViewHostPresentationIdleGate.cs`
- `src/Rook/UI/Vision/VisionPanelPresentationState.cs`
- `src/Rook.Tests/UI/Web/WebViewHostPresentationCoordinatorTests.cs`
- `src/Rook.Tests/UI/Web/WebViewHostPresentationIdleGateTests.cs`
- `src/Rook.Tests/UI/Vision/VisionPanelPresentationStateTests.cs`

**Files (modify):**
- `src/Rook/UI/Web/RookWebSurface.cs`: remove `WebViewHostVisibilityCoordinator` class + `_hostVisibility` + `ReconcileHostVisibility` + `RequestHostVisibleRefresh` + `ScheduleHostVisibilityReconcile`/`RunHostVisibilityReconcile` + `ReconcileHostPresentation` + `_latestPresentationFacts`/`_hostPresentationQueued`/idle-gate fields + `UseHostPresentationCoordinator` + `RefreshHostPresentationFacts` + `CaptureHostPresentationProbe`/snapshot building. KEEP: diagnostics ring, reflection helpers (`TryGetCoreWebView2Controller`, `SetControllerVisible`, `SetControllerBounds`, `NotifyParentWindowPositionChanged`, HWND probe helpers — HWND helpers now feed ring annotations only).
- `src/Rook/UI/Web/WebViewHostPanelPresentationFacts.cs`: delete if no remaining references (diagnostic entry record may need trimming — keep `WebViewHostPresentationDiagnosticEntry` shape compiling).

- [ ] **Step 8.1:** Delete files, fix compilation, ensure `grep -r "UseHostPresentationCoordinator\|VisionPanelPresentationState\|ReconcileHostVisibility" src/` returns nothing.
- [ ] **Step 8.2:** Full suite: `dotnet test src/Rook.Tests/Rook.Tests.csproj -v minimal` — Expected: PASS, zero references to deleted types.
- [ ] **Step 8.3:** Commit: `git add -A; git commit -m "refactor: remove probe-gated presentation coordinator stack"`

---

### Task 9: Build, deploy, live checkpoints, full matrix

- [ ] **Step 9.1:** Build + deploy per project convention: `cmd /c scripts\build-native.bat` then `cmd /c scripts\deploy-native.bat` (confirm the C# `Rook.rhp` is copied to `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\`; if deploy script only handles `RookNative.rhp`, copy `src/Rook/bin/Release/net8.0/Rook.rhp` there manually). **Confirm throwaway-safe Rhino state with the user before launching** (per `feedback_destructive_fixtures` discipline this is non-destructive, but the user pulls the trigger on live sessions).
- [ ] **Step 9.2: MCP reachability check (mandatory acceptance criterion):** with Rhino running, call the new `rhino_vision_presentation` tool with `action=dump` (expect ring entries for ALL live surfaces), then `action=repair` (expect immediate `scheduled:<n>`), then `action=dump` again ~3s later (expect `forced-repair` ring entries with dispositions per surface). Also verify an invalid action returns HTTP 400 from the native route.
- [ ] **Step 9.3: Live checkpoint B (Codex planning note 2):** dock Vision tabbed-behind Knowledge, keep Rhino ACTIVE. Trigger reconciles (resize the dock group, click around) for 2 minutes. Expected: ring shows bounded repair attempts ending `DegradedHidden`, NO reload, and — critically — full Rhino responsiveness (command line accepts input, panels close/reopen, no resize smear: the #192 wedge symptoms). If Rhino wedges: STOP, record ring dump, revisit whether repair attempts must be suppressed when lifecycle annotations say tab-unselected (spec permits adding that guard without architecture change).
- [ ] **Step 9.4: Full matrix** (each scenario → note result + capture `rhino_vision_presentation action=dump`):
  1. Floating Vision on monitor above primary; alt-tab storms (10+ cycles).
  2. Artifact reveal/open-folder → Explorer; return via panel click / viewport click / alt-tab.
  3. Artifact reveal while a video element is loaded/playing in the modal.
  4. Docked tab away/return without app refocus.
  5. Undock/redock during and after any dark state.
  6. Resize while Rhino inactive, then return.
  7. Chat + Knowledge co-resident, same sequences.
  8. Multi-document open/close.
  9. Click-into-dark-panel heals (if any dark state is caught live).
  Expected: zero persistent dark states; any transient dark heals on next return edge; no wedge symptoms anywhere.
- [ ] **Step 9.5:** Update the spec's "Checkpoint A verdict" + matrix results into the PR description draft.

---

### Task 10: PR

- [ ] **Step 10.1:** `git push -u origin fix/webview-presentation-reconciler`
- [ ] **Step 10.2:** Open PR titled `fix: level-triggered WebView presentation reconciler (#233)` with: spec link, evidence summary (ring #8 defect, stuck-hidden capture, live toggle proof), matrix results table, and the rollout gate statement (all three surfaces passed). Body ends with the standard generated-with footer.
- [ ] **Step 10.3:** Codex review round(s); address; user squash-merges via `gh pr merge --squash --delete-branch`.

---

## Checkpoint A verdict

(filled in by Task 1)

## Self-review notes

- Spec coverage: probe contract (T2), reconciler ladder incl. no-reload-on-persistent-hidden, in-core post-reload confirm independent of DocumentLoaded, and latest-wins coalescing (T3), desired-visible table (T4, T7), all-surface registry + native `/vision/presentation` route + MCP tool + Repair option (T5), trigger table (T6.3, T7.1), deletions (T8), wedge checkpoint + video case + matrix (T9), rollout gate (T9/T10).
- Persistent `RendererHidden` never reloads: enforced in T3 ladder + tested.
- Coalescing: pending-reason latch, tested via trigger-during-repair-gap.
- Post-reload confirm: in-core (`IssueReloadAsync`), unit-tested both outcomes.
- `ExecuteScriptAsync` double-decode: T2 tests.
- Plan review round 2 (Codex): MCP end-to-end via new native route (no generic `/vision/dispatch` HTTP route exists); registry replaces Vision-only enumeration; trace-format expectation corrected for Checkpoint A; `Ok`/`Fail` helper names; no invented `tab.Surface` member.
