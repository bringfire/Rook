using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.Remoting.Messaging;
using System.Runtime.Remoting.Proxies;
using System.Runtime.Serialization;
using System.Threading.Tasks;
using Eto.Forms;
using Rook.UI.Web;
using Xunit;

namespace Rook.Tests.UI.Web
{
    /// <summary>
    /// Script admission at the execution boundary (plan §1): at most
    /// MaxInFlightScripts executing, submission order preserved, slots released on
    /// success, fault and cancellation, backlog counts queued work, stale content
    /// dropped at admission / start / replay while control scripts survive.
    /// </summary>
    [Collection(EtoUiCollection.Name)]
    public sealed class RookWebSurfaceScriptAdmissionTests
    {
        private sealed class TestSurface : RookWebSurface
        {
            protected override string ResourceRoot => "Rook.Tests.Admission";
            protected override string EntryPage => "index.html";
            protected override string MinimalFallbackHtml => "<html></html>";
            protected override void Log(string message) { }
        }

        private sealed class Harness
        {
            public readonly TestSurface Surface = new();
            public readonly List<string> Started = new();
            public readonly List<TaskCompletionSource<string>> Held = new();
            public readonly ConcurrentQueue<Action> Scheduler = new();
            public int DrainedEvents;

            public Harness(bool ready = true)
            {
                EtoTestPlatform.Ensure();
                var view = (WebView)FormatterServices.GetUninitializedObject(typeof(WebView));
                Set(view, typeof(Eto.Widget), "_handler", new Executor(this).GetTransparentProxy());
                Set(Surface, typeof(RookWebSurface), "_webView", view);
                Set(Surface, typeof(RookWebSurface), "_webViewReady", ready);
                Surface.UiScheduler = action => Scheduler.Enqueue(action);
                Surface.BacklogDrained += () => DrainedEvents++;
            }

            /// <summary>Runs inside the executor before it returns its task, like a
            /// CoreWebView2.ExecuteScriptAsync call that pumps messages (#581).</summary>
            public Action? BeforeReturn;

            public Task<string> Execute(string script)
            {
                Started.Add(script);
                var tcs = new TaskCompletionSource<string>();
                Held.Add(tcs);
                BeforeReturn?.Invoke();
                return tcs.Task;
            }

            public void Pump()
            {
                var guard = 0;
                while (Scheduler.TryDequeue(out var action)) { action(); Assert.True(++guard < 100_000); }
            }

            public void Complete(int index, string? faultMessage = null, bool cancel = false)
            {
                var tcs = Held[index];
                if (cancel) tcs.TrySetCanceled();
                else if (faultMessage != null) tcs.TrySetException(new InvalidOperationException(faultMessage));
                else tcs.TrySetResult(string.Empty);
                Pump();
            }

            public void Post(int generation, string script) => Surface.PostScript(ScriptRequest.ForContent(generation, script));
            public void PostControl(string script) => Surface.PostScript(ScriptRequest.ForControl(script));
            public int InFlight => (int)Prop("InFlightScripts");
            public int Queued => (int)Prop("QueuedScripts");
            public int Buffered => (int)Prop("BufferedScripts");
            private object Prop(string name) => typeof(RookWebSurface).GetProperty(name, BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(Surface);
            public void DocumentLoaded()
            {
                typeof(RookWebSurface).GetMethod("OnDocumentLoaded", BindingFlags.Instance | BindingFlags.NonPublic)!
                    .Invoke(Surface, new object?[] { null, new WebViewLoadedEventArgs(new Uri("https://app.rook.invalid/index.html")) });
            }
        }

        [Fact]
        public void At_most_sixteen_scripts_execute_and_order_is_preserved_across_success_fault_and_cancel()
        {
            var h = new Harness();
            var scripts = Enumerable.Range(0, 40).Select(i => "s" + i).ToList();
            foreach (var s in scripts) h.Post(0, s);
            Assert.Empty(h.Started);                         // nothing runs before marshaling
            h.Pump();
            Assert.Equal(RookWebSurface.MaxInFlightScripts, h.Started.Count);
            Assert.Equal(RookWebSurface.MaxInFlightScripts, h.InFlight);
            Assert.Equal(40 - RookWebSurface.MaxInFlightScripts, h.Queued);
            Assert.Equal(40, h.Surface.Backlog);
            Assert.Equal(0, h.DrainedEvents);

            h.Complete(0);
            Assert.Equal(17, h.Started.Count);               // one slot released → one more started
            Assert.Equal(RookWebSurface.MaxInFlightScripts, h.InFlight);
            h.Complete(1, faultMessage: "boom");             // faulted still releases its slot
            h.Complete(2, cancel: true);                     // cancelled still releases its slot
            Assert.Equal(19, h.Started.Count);
            for (var i = 3; i < 40; i++) h.Complete(i);
            Assert.Equal(scripts, h.Started);                // execution order == submission order
            Assert.Equal(0, h.Surface.Backlog);
            Assert.True(h.DrainedEvents > 0);                // fired once the backlog fell below the resume threshold
        }

        [Fact]
        public void Admission_limit_holds_when_the_executor_pumps_callbacks_before_returning()
        {
            // Review finding: the slot used to be reserved only after the executor
            // returned. If the executor pumps UI callbacks first (as ExecuteScriptAsync
            // can), a nested PostScript -> TryStartScripts saw an unreserved slot:
            // 17 started, 17 in flight, limit 16.
            var h = new Harness();
            var maxStartedInsideExecutor = 0;
            var maxInFlightInsideExecutor = 0;
            var nestedCalls = 0;
            h.BeforeReturn = () =>
            {
                nestedCalls++;
                h.Pump();                                    // marshaled PostScript / completion callbacks run here
                maxStartedInsideExecutor = Math.Max(maxStartedInsideExecutor, h.Started.Count);
                maxInFlightInsideExecutor = Math.Max(maxInFlightInsideExecutor, h.InFlight);
            };
            var scripts = Enumerable.Range(0, 40).Select(i => "s" + i).ToList();
            foreach (var s in scripts) h.Post(0, s);
            h.Pump();

            Assert.True(nestedCalls >= RookWebSurface.MaxInFlightScripts);
            Assert.Equal(RookWebSurface.MaxInFlightScripts, h.Started.Count);
            Assert.Equal(RookWebSurface.MaxInFlightScripts, h.InFlight);
            Assert.True(maxStartedInsideExecutor <= RookWebSurface.MaxInFlightScripts,
                $"{maxStartedInsideExecutor} scripts started while the executor was still inside a call");
            Assert.True(maxInFlightInsideExecutor <= RookWebSurface.MaxInFlightScripts,
                $"{maxInFlightInsideExecutor} in flight while the executor was still inside a call");
            Assert.Equal(40, h.Surface.Backlog);             // reserved slot counts in the backlog

            // Completions delivered while the executor is inside a call (pumped by
            // BeforeReturn) must release exactly one slot each and keep order.
            for (var i = 0; i < 40; i++)
            {
                h.Complete(i);
                Assert.True(h.InFlight <= RookWebSurface.MaxInFlightScripts, $"in flight {h.InFlight} after completing {i}");
            }
            Assert.Equal(scripts, h.Started);
            Assert.Equal(0, h.InFlight);
            Assert.Equal(0, h.Surface.Backlog);
        }

        [Fact]
        public void Backlog_drained_fires_only_below_the_resume_threshold()
        {
            var h = new Harness();
            for (var i = 0; i < 20; i++) h.Post(0, "s" + i);
            h.Pump();
            Assert.Equal(0, h.DrainedEvents);
            var completed = 0;
            while (h.Surface.Backlog >= RookWebSurface.ScriptResumeThreshold)
            {
                h.Complete(completed++);
                if (h.Surface.Backlog >= RookWebSurface.ScriptResumeThreshold) Assert.Equal(0, h.DrainedEvents);
            }
            Assert.True(h.DrainedEvents >= 1);
        }

        [Fact]
        public void Stale_content_is_dropped_at_admission_and_at_start_but_control_survives()
        {
            var h = new Harness();
            for (var i = 0; i < RookWebSurface.MaxInFlightScripts; i++) h.Post(0, "fill" + i);
            h.Pump();                                        // all slots busy
            h.Post(0, "queued-stale");                       // queued behind the fill
            h.PostControl("queued-control");
            h.Post(0, "queued-stale-2");
            h.Pump();
            Assert.Equal(3, h.Queued);
            h.Surface.InvalidateDisplay();                   // Clear
            h.Post(0, "posted-after-clear-stale");           // dropped at admission
            h.Post(1, "posted-after-clear-fresh");
            h.Pump();
            Assert.Equal(4, h.Queued);                       // the stale post never entered the queue
            h.Complete(0);
            h.Complete(1);
            h.Complete(2);
            Assert.Equal(new[] { "queued-control", "posted-after-clear-fresh" },
                h.Started.Skip(RookWebSurface.MaxInFlightScripts).ToList());
        }

        [Fact]
        public void Not_ready_buffer_replays_control_and_current_generation_only_in_order()
        {
            var h = new Harness(ready: false);
            h.Post(0, "content-old");
            h.PostControl("control-a");
            h.Post(0, "content-old-2");
            h.Pump();
            Assert.Equal(3, h.Buffered);
            Assert.Empty(h.Started);
            h.Surface.InvalidateDisplay();                   // Clear while the document is loading
            h.Post(1, "content-new");
            h.PostControl("control-b");
            h.Pump();
            Assert.Equal(5, h.Buffered);
            h.DocumentLoaded();
            h.Pump();
            Assert.Equal(new[] { "control-a", "content-new", "control-b" }, h.Started);
            Assert.Equal(0, h.Buffered);
        }

        [Fact]
        public void Disposed_surface_ignores_posts_and_clears_its_queues()
        {
            var h = new Harness();
            for (var i = 0; i < 20; i++) h.Post(0, "s" + i);
            h.Pump();
            h.Surface.Dispose();
            Assert.Equal(0, h.Surface.Backlog);
            h.Post(0, "late");
            h.Pump();
            Assert.Equal(RookWebSurface.MaxInFlightScripts, h.Started.Count);
            h.Complete(0);                                    // completions after dispose are inert
            Assert.Equal(RookWebSurface.MaxInFlightScripts, h.Started.Count);
        }

        private static void Set(object target, Type type, string name, object value)
            => type.GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(target, value);

        private sealed class Executor : RealProxy
        {
            private readonly Harness _harness;
            public Executor(Harness harness) : base(typeof(WebView.IHandler)) => _harness = harness;
            public override IMessage Invoke(IMessage message)
            {
                var call = (IMethodCallMessage)message;
                if (call.MethodName == "ExecuteScriptAsync")
                    return new ReturnMessage(_harness.Execute((string)call.Args[0]), null, 0, call.LogicalCallContext, call);
                if (call.MethodName == "Dispose" || call.MethodName == "remove_DocumentLoaded" || call.MethodName.StartsWith("remove_"))
                    return new ReturnMessage(null, null, 0, call.LogicalCallContext, call);
                return new ReturnMessage(new InvalidOperationException("Unexpected WebView boundary: " + call.MethodName), call);
            }
        }
    }
}
