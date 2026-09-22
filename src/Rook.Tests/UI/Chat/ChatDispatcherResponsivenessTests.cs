using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Threading;
using Rook.UI.Chat;
using Rook.UI.Web;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    /// <summary>
    /// The responsiveness contract on a REAL WPF dispatcher (plan §7): the tab's UI
    /// scheduler is Dispatcher.BeginInvoke on this STA thread, the frame is pumped with
    /// Dispatcher.PushFrame, script execution completes asynchronously on the thread
    /// pool after a 5–20 ms delay (like WebView2), and a 10 ms DispatcherTimer heartbeat
    /// records the longest interval between ticks while 2,000 deltas and 5 tool cards
    /// stream through. The approved criterion is no UI stall over 250 ms.
    /// </summary>
    [Collection(EtoUiCollection.Name)]
    public sealed class ChatDispatcherResponsivenessTests : IClassFixture<AgentChatProgressTests.PanelThread>
    {
        private readonly AgentChatProgressTests.PanelThread _ui;
        public ChatDispatcherResponsivenessTests(AgentChatProgressTests.PanelThread ui) => _ui = ui;

        private const int Deltas = 2000;
        private const int Cards = 5;

        [Fact]
        public void Streaming_two_thousand_deltas_keeps_a_real_dispatcher_under_the_stall_budget()
        {
            _ui.Run(() =>
            {
                var body = new StringBuilder();
                var expectedText = new StringBuilder();
                for (var i = 0; i < Deltas; i++)
                {
                    if (i % (Deltas / Cards) == 0)
                        body.Append(Tool("t" + (i / (Deltas / Cards)), "in_progress"));
                    var delta = "w" + i + (i % 9 == 0 ? ". " : " ");
                    expectedText.Append(delta);
                    body.Append(Text(delta));
                }
                body.Append(Terminal());
                using var handler = new StreamHandler(body.ToString());
                using var client = AgentChatClient.ForTests(handler, new Uri("http://127.0.0.1:1"));
                var scripts = new List<string>();
                using var h = AgentChatProgressTests.Harness.Create(client, scripts);
                var dispatcher = Dispatcher.CurrentDispatcher;
                // Real marshaling: UI work is BeginInvoke'd, and awaits inside the tab
                // resume through a DispatcherSynchronizationContext, exactly as in Rhino.
                var previousContext = SynchronizationContext.Current;
                SynchronizationContext.SetSynchronizationContext(new DispatcherSynchronizationContext(dispatcher));
                try
                {
                h.Tab.UiScheduler = action => dispatcher.BeginInvoke(DispatcherPriority.Normal, action);
                var rng = new Random(42);
                h.Executor = script =>
                {
                    var delay = 5 + rng.Next(16);
                    return Task.Delay(delay).ContinueWith(_ => string.Empty, TaskScheduler.Default);
                };
                typeof(ChatTab).GetMethod("EnableWebComposer", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!.Invoke(h.Tab, null);

                var intervals = new List<double>();
                var last = DateTime.UtcNow;
                var heartbeat = new DispatcherTimer(DispatcherPriority.Normal, dispatcher) { Interval = TimeSpan.FromMilliseconds(10) };
                heartbeat.Tick += (_, __) =>
                {
                    var now = DateTime.UtcNow;
                    intervals.Add((now - last).TotalMilliseconds);
                    last = now;
                };

                var frame = new DispatcherFrame();
                var deadline = DateTime.UtcNow.AddSeconds(90);
                var surface = (RookWebSurface)h.Surface;
                Task<bool>? submission = null;
                var settle = new DispatcherTimer(DispatcherPriority.Background, dispatcher) { Interval = TimeSpan.FromMilliseconds(25) };
                settle.Tick += (_, __) =>
                {
                    if (DateTime.UtcNow > deadline) { frame.Continue = false; return; }
                    if (submission != null && submission.IsCompleted && !h.IsProcessing &&
                        h.Presentation.PendingCount == 0 && surface.Backlog == 0)
                        frame.Continue = false;
                };

                // Establish the heartbeat baseline BEFORE submitting, so the interval that
                // spans the submission itself is measured like every other one (review
                // finding: an initial UI stall must not escape detection).
                heartbeat.Start();
                var warmup = new DispatcherFrame();
                var warmupTimer = new DispatcherTimer(DispatcherPriority.Background, dispatcher) { Interval = TimeSpan.FromMilliseconds(10) };
                warmupTimer.Tick += (_, __) => { if (intervals.Count >= 5) warmup.Continue = false; };
                warmupTimer.Start();
                Dispatcher.PushFrame(warmup);
                warmupTimer.Stop();
                intervals.Clear();
                last = DateTime.UtcNow;

                settle.Start();
                submission = h.SubmitWithoutPumping();
                Dispatcher.PushFrame(frame);
                heartbeat.Stop();
                settle.Stop();

                Assert.True(DateTime.UtcNow <= deadline, "streaming did not settle within the deadline");
                Assert.True(submission!.Result);
                Assert.False(h.IsProcessing);
                Assert.Empty(h.SynchronousScripts);

                // Execution order == event order: the deltas reassemble exactly and the
                // cards appear in sequence, with the settle control script last.
                var snapshot = h.Scripts.ToList();
                Assert.Equal(expectedText.ToString(), string.Concat(AgentChatProgressTests.Segments(snapshot)));
                var cards = snapshot.Where(s => s.Contains("renderToolCard(")).Select(s => s.Substring(s.LastIndexOf('\'', s.Length - 3) + 1).TrimEnd(')', '\'')).ToList();
                Assert.Equal(Enumerable.Range(0, Cards).Select(i => "t" + i), cards);
                Assert.Equal("window.chatAPI.setComposerEnabled(true, true)", snapshot.Last(s => s.Contains("setComposerEnabled")));
                Assert.Equal("window.chatAPI.finalizeStreamingMessage()", snapshot.Last(s => s.Contains("finalizeStreaming")));

                // Responsiveness: the dispatcher kept ticking; no interval above the budget.
                Assert.True(intervals.Count > 5, $"heartbeat did not run (ticks={intervals.Count})");
                // Every interval counts, including the one covering the submission call.
                var worst = intervals.Max();
                Assert.True(worst < 250, $"worst heartbeat interval {worst:F0} ms (budget 250 ms); intervals={intervals.Count}, scripts={snapshot.Count}");
                Assert.True(surface.InFlightScripts <= RookWebSurface.MaxInFlightScripts);
                }
                finally { SynchronizationContext.SetSynchronizationContext(previousContext); }
            });
        }

        private static string Text(string text) => JsonSerializer.Serialize(new { type = "text_delta", text }) + "\n";
        private static string Tool(string id, string status)
            => JsonSerializer.Serialize(new { type = "tool_update", messageId = id, kind = "tool_call", payload = new { status, toolCallId = id } }) + "\n";
        private static string Terminal()
            => JsonSerializer.Serialize(new { type = "terminal", outcome = "settled", stopReason = "end_turn", presentationOutcome = "delivered", cachePublished = true }) + "\n";

        private sealed class StreamHandler : HttpMessageHandler
        {
            private readonly string _body;
            public StreamHandler(string body) => _body = body;
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
                => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(_body, Encoding.UTF8, "application/x-ndjson"),
                });
        }
    }
}
