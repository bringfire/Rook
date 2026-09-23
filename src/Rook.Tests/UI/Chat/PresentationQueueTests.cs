using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using Rook.UI.Chat;
using Rook.UI.Web;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    /// <summary>
    /// Deterministic contract tests for the ordered presentation projection (plan §2):
    /// ordering, merging, bounded drains, backpressure pauses, and validity by display
    /// generation / active request. No Eto, no dispatcher: the scheduler is a list.
    /// </summary>
    public sealed class PresentationQueueTests
    {
        private sealed class Backpressure : IScriptBackpressure
        {
            public int Backlog { get; set; }
            public event Action? BacklogDrained;
            public void Drain() { Backlog = 0; BacklogDrained?.Invoke(); }
        }

        private sealed class Harness
        {
            public readonly List<Action> Scheduled = new();
            public readonly List<string> Applied = new();
            public readonly Backpressure Pressure = new();
            public int Generation;
            public int Request;
            public PresentationQueue Queue;

            public Harness(int maxItems = PresentationQueue.DefaultMaxItemsPerDrain, TimeSpan? budget = null, int pause = PresentationQueue.DefaultPauseThreshold)
            {
                Queue = new PresentationQueue(
                    schedule: Scheduled.Add,
                    currentDisplayGeneration: () => Generation,
                    activeRequestId: () => Request,
                    backpressure: Pressure,
                    applyText: text => Applied.Add("text:" + text),
                    applyThought: status => Applied.Add("thought:" + status),
                    maxItemsPerDrain: maxItems,
                    drainBudget: budget,
                    pauseThreshold: pause);
            }

            public void Text(string delta, int? gen = null) => Queue.Push(new PresentationItem.Text(gen ?? Generation, delta));
            public void Thought(string status, int? gen = null) => Queue.Push(new PresentationItem.Thought(gen ?? Generation, status));
            public void Content(string name, int? gen = null, bool emits = true)
                => Queue.Push(new PresentationItem.Content(gen ?? Generation, name, () => Applied.Add("content:" + name), emits));
            public void Control(string name, int? req = null, bool emits = true)
                => Queue.Push(new PresentationItem.Control(req ?? Request, name, () => Applied.Add("control:" + name), emits));

            /// <summary>Run scheduled drains until none remain (or a pause holds them).</summary>
            public int Pump()
            {
                var runs = 0;
                while (Scheduled.Count > 0)
                {
                    var action = Scheduled[0];
                    Scheduled.RemoveAt(0);
                    action();
                    runs++;
                    Assert.True(runs < 10_000, "runaway drain loop");
                }
                return runs;
            }
        }

        [Fact]
        public void Order_is_preserved_across_text_tool_text_and_terminal()
        {
            var h = new Harness();
            h.Text("alpha ");
            h.Text("repeat.");
            h.Content("card:t1");
            h.Text("beta ");
            h.Content("finalize:t1");
            h.Text("repeat.");
            h.Content("transcript-finalize");
            h.Control("settle");
            h.Pump();
            Assert.Equal(new[]
            {
                "text:alpha repeat.", "content:card:t1", "text:beta ", "content:finalize:t1",
                "text:repeat.", "content:transcript-finalize", "control:settle",
            }, h.Applied);
        }

        [Fact]
        public void Adjacent_deltas_merge_across_thoughts_but_never_across_a_card()
        {
            var h = new Harness();
            h.Text("a");
            h.Thought("reasoning");
            h.Text("b");
            h.Thought("reasoning again");
            h.Text("c");
            h.Content("card");
            h.Text("d");
            h.Pump();
            Assert.Equal(new[] { "text:abc", "thought:reasoning again", "content:card", "text:d" }, h.Applied);
        }

        [Fact]
        public void One_drain_is_scheduled_per_cycle_and_pushes_during_apply_reschedule_once()
        {
            var h = new Harness();
            h.Text("a");
            h.Text("b");
            Assert.Single(h.Scheduled);
            // Push during apply: the content applier pushes another item.
            h.Queue.Push(new PresentationItem.Content(h.Generation, "reentrant", () =>
            {
                h.Applied.Add("content:reentrant");
                h.Text("late");
            }));
            var drains = h.Pump();
            Assert.Equal(2, drains);
            Assert.Equal(new[] { "text:ab", "content:reentrant", "text:late" }, h.Applied);
            Assert.Equal(0, h.Queue.PendingCount);
        }

        [Fact]
        public void Generation_mismatch_drops_content_only_and_Discard_keeps_control_items()
        {
            var h = new Harness();
            h.Text("stale");
            h.Content("stale-card");
            h.Control("settle");
            h.Generation = 1;                 // Clear happened before the drain ran
            h.Queue.Discard();
            h.Content("fresh", gen: 1);
            h.Pump();
            Assert.Equal(new[] { "control:settle", "content:fresh" }, h.Applied);
        }

        [Fact]
        public void Stale_request_control_items_are_dropped_but_history_is_not()
        {
            var h = new Harness();
            h.Content("history-finalize");
            h.Control("old-request-controls", req: 0);
            h.Request = 1;
            h.Control("new-request-controls", req: 1);
            h.Pump();
            Assert.Equal(new[] { "content:history-finalize", "control:new-request-controls" }, h.Applied);
        }

        [Fact]
        public void Drains_are_bounded_by_item_count_and_rescheduled()
        {
            var h = new Harness(maxItems: 4);
            for (var i = 0; i < 10; i++) h.Content("c" + i);
            var drains = h.Pump();
            Assert.Equal(3, drains);
            Assert.Equal(10, h.Applied.Count);
            Assert.Equal(Enumerable.Range(0, 10).Select(i => "content:c" + i), h.Applied);
        }

        [Fact]
        public void Alternating_text_and_thought_yield_one_text_and_one_status_per_batch()
        {
            var h = new Harness(maxItems: 64);
            for (var i = 0; i < 10_000; i++)
            {
                h.Text("x");
                h.Thought("t" + i);
            }
            var drains = h.Pump();
            Assert.True(drains >= 10_000 * 2 / 64, "expected many bounded drains");
            var texts = h.Applied.Where(a => a.StartsWith("text:")).ToList();
            var thoughts = h.Applied.Where(a => a.StartsWith("thought:")).ToList();
            Assert.Equal(10_000, texts.Sum(t => t.Length - "text:".Length));
            Assert.Equal(texts.Count, thoughts.Count);          // one merged text + one status per batch
            Assert.True(texts.Count <= 10_000 * 2 / 64 + 1);
            Assert.Equal("thought:t9999", thoughts.Last());
        }

        [Fact]
        public void A_slow_apply_exhausts_the_time_budget_and_reschedules_the_remainder()
        {
            var h = new Harness(budget: TimeSpan.FromMilliseconds(1));
            h.Queue.Push(new PresentationItem.Content(h.Generation, "slow", () => { h.Applied.Add("content:slow"); Thread.Sleep(5); }));
            h.Content("after");
            var first = h.Scheduled[0];
            h.Scheduled.RemoveAt(0);
            first();
            Assert.Equal(new[] { "content:slow" }, h.Applied);
            Assert.Single(h.Scheduled);      // remainder rescheduled, not applied inline
            h.Pump();
            Assert.Equal(new[] { "content:slow", "content:after" }, h.Applied);
        }

        [Fact]
        public void Backlog_at_threshold_pauses_before_script_emitting_items_and_resumes_on_drain()
        {
            var h = new Harness(pause: 4);
            h.Content("first");
            h.Control("status-only", emits: false);
            h.Content("second");
            h.Pressure.Backlog = 4;
            h.Pump();
            // Paused before the first script-emitting item; nothing script-bound applied.
            Assert.Empty(h.Applied);
            Assert.True(h.Queue.IsPaused);
            Assert.Empty(h.Scheduled);
            h.Text("during-pause");         // pushes while paused must not schedule
            Assert.Empty(h.Scheduled);
            h.Pressure.Drain();             // BacklogDrained → resume
            Assert.Single(h.Scheduled);
            h.Pump();
            Assert.Equal(new[] { "content:first", "control:status-only", "content:second", "text:during-pause" }, h.Applied);
            Assert.False(h.Queue.IsPaused);
        }

        [Fact]
        public void Carried_items_keep_their_order_and_remerge_identically()
        {
            var h = new Harness(pause: 1);
            h.Text("a");
            h.Text("b");
            h.Content("card");
            h.Text("c");
            h.Pressure.Backlog = 1;
            h.Pump();                       // paused immediately
            Assert.Empty(h.Applied);
            h.Pressure.Drain();
            h.Pressure.Backlog = 0;
            h.Pump();
            Assert.Equal(new[] { "text:ab", "content:card", "text:c" }, h.Applied);
        }
    }
}
