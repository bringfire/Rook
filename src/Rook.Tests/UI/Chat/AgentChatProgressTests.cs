using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Runtime.Remoting.Messaging;
using System.Runtime.Remoting.Proxies;
using System.Runtime.Serialization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Eto.Forms;
using Rook.UI.Chat;
using Rook.UI.Web;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    /// <summary>
    /// Real AgentChatTab / ChatTab / RookWebSurface with only Eto's native script
    /// executor replaced. UI marshaling is a recording scheduler pumped by the test,
    /// so every assertion is about what the presentation stream actually posted and
    /// executed, in order, without a dispatcher (plan §7 deterministic tests).
    /// </summary>
    [Collection(Rook.Tests.UI.EtoUiCollection.Name)]
    public sealed class AgentChatProgressTests : IClassFixture<AgentChatProgressTests.PanelThread>
    {
        private readonly PanelThread _ui;
        public AgentChatProgressTests(PanelThread ui) => _ui = ui;

        [Theory]
        [InlineData("settled", "end_turn")]
        [InlineData("cancelled", "cancelled")]
        [InlineData("incomplete", "max_tokens")]
        public void Real_panel_segments_text_at_rendered_tools_and_starts_next_prompt_cleanly(
            string outcome, string stopReason)
        {
            RunOnSta(() =>
            {
                using var handler = new PromptHandler(
                    Text("alpha ") + Text("repeat.") + Tool("t1", "in_progress") +
                    Tool("t2", "in_progress") + Tool("t1", "completed") + Text("beta ") +
                    Tool("t2", "failed") + Text("repeat.") + Tool("t3", "in_progress") +
                    Text("repeat.") + Terminal(outcome, stopReason),
                    Text("next") + Terminal("settled", "end_turn"));
                using var h = Harness.Create(handler);

                h.Prompt();
                h.Prompt();
                Assert.Equal(2, handler.RequestCount);
                // Retain real emitted commands even on RED; the HTML test consumes these,
                // never a second implementation of the managed accumulation logic.
                var directory = Environment.GetEnvironmentVariable("ROOK_PROGRESS_TEST_OUTPUT");
                if (!string.IsNullOrEmpty(directory))
                {
                    Directory.CreateDirectory(directory);
                    File.WriteAllText(Path.Combine(directory, outcome + ".json"),
                        JsonSerializer.Serialize(h.Scripts), new UTF8Encoding(false));
                }
                // Tool finalization (completed/failed) preserves the active bubble:
                // "beta " + failed t2 + "repeat." is one segment. Cards start new ones.
                Assert.Equal(new[] { "alpha repeat.", "beta repeat.", "repeat.", "next" }, Segments(h.Scripts));
                Assert.Equal(2, h.Scripts.Count(s => s == "window.chatAPI.finalizeStreamingMessage()"));
                Assert.Empty(h.SynchronousScripts);
                // Cards and finalizations execute in event order relative to text.
                var cards = h.Scripts.Where(s => s.Contains("renderToolCard(") || s.Contains("finalizeToolCard(")).ToList();
                Assert.Equal(new[] { "t1", "t2", "t1", "t2", "t3" },
                    cards.Select(s => s.Contains("renderToolCard(") ? s.Substring(s.LastIndexOf('\'', s.Length - 3) + 1).TrimEnd(')', '\'') : s.Split('\'')[1]));
            });
        }

        [Fact]
        public void Detached_panel_does_not_render_or_reset_its_buffer()
        {
            RunOnSta(() =>
            {
                using var handler = new PromptHandler();
                using var h = Harness.Create(handler);
                Set(h.Tab, typeof(AgentChatTab), "_assistantBuffer", new StringBuilder("retained"));
                Set(h.Tab, typeof(AgentChatTab), "_uiAttached", false);
                using var payload = JsonDocument.Parse("{\"status\":\"in_progress\"}");
                Invoke(h.Tab, typeof(AgentChatTab), "HandleChatEvent", new ChatEvent
                {
                    Type = "tool_update", Payload = payload.RootElement.Clone(),
                });
                h.Pump();
                Assert.Empty(h.Scripts);
                Assert.Equal("retained", Get(h.Tab, typeof(AgentChatTab), "_assistantBuffer").ToString());
                Assert.Equal(0, handler.RequestCount);
            });
        }

        [Theory]
        [InlineData("refused", "refusal", "Prime refused the request")]
        [InlineData("settled", "end_turn", "Ready")]
        [InlineData("cancelled", "cancelled", "Cancelled")]
        [InlineData("incomplete", "max_tokens", "Prime turn incomplete")]
        public void Confirmed_settlement_allows_only_explicit_same_conversation_submission(string outcome, string stopReason, string status)
        {
            RunOnSta(() =>
            {
                using var handler = new PromptHandler(Terminal(outcome, stopReason),
                    Text("next") + Terminal("settled", "end_turn"));
                using var h = Harness.Create(handler);
                h.Submit();
                Assert.Equal(1, handler.RequestCount);
                Assert.False(h.IsProcessing);
                Assert.Equal(status, h.StatusText);
                h.Submit();
                Assert.Equal(2, handler.RequestCount);
                Assert.Equal("offline-fixture", h.Tab.ConversationId);
            });
        }

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public void Unconfirmed_submission_blocks_both_handlers_without_erasing_input_or_adding_bubbles(bool nativeFirst)
        {
            RunOnSta(() =>
            {
                using var handler = new UnsettledPromptHandler();
                using var h = Harness.Create(handler);
                Invoke(h.Tab, typeof(ChatTab), "EnableWebComposer");
                h.Submit(nativeFirst);
                Assert.Equal(1, handler.Prompts);
                Assert.Equal(1, handler.Cancels);
                Assert.False(h.IsProcessing);
                Assert.False(((Button)Get(h.Tab, typeof(ChatTab), "_sendButton")).Enabled);
                Assert.Equal("Request outcome is unconfirmed. Another request is blocked because the previous one may still be running.",
                    h.StatusText);
                Assert.Contains("window.chatAPI.showTypingIndicator(false)", h.Scripts);
                Assert.Equal("window.chatAPI.setComposerEnabled(true, false)", h.Scripts.Last(s => s.Contains("setComposerEnabled")));
                // Neither a normal processing reset nor an updated view may erase uncertainty.
                Invoke(h.Tab, typeof(ChatTab), "SetProcessing", false);
                Invoke(h.Tab, typeof(AgentChatTab), "ApplyConversationStatus", new ConversationView
                { ConversationId = "offline-fixture", TargetAvailable = true });
                h.Pump();
                var before = h.Scripts.Count;
                h.Submit();
                h.Submit(native: true);
                h.Submit();
                Assert.Equal("local fixture", ((TextArea)Get(h.Tab, typeof(ChatTab), "_inputArea")).Text);
                Assert.Equal(before, h.Scripts.Count);
                Assert.Equal(1, handler.Prompts);
                Assert.Equal(1, handler.Cancels);
                Assert.Equal("offline-fixture", h.Tab.ConversationId);
                Invoke(h.Tab, typeof(ChatTab), "OnClearClicked", new object(), EventArgs.Empty);
                h.Pump();
                Assert.False(((Button)Get(h.Tab, typeof(ChatTab), "_sendButton")).Enabled);
                Assert.StartsWith("Request outcome is unconfirmed.", h.StatusText);
            });
        }

        [Theory]
        [InlineData(409, "{\"error\":{\"code\":\"image_unsupported\",\"message\":\"image_unsupported\"}}", true)]
        [InlineData(400, "{\"error\":{\"code\":\"invalid_prompt\",\"message\":\"invalid prompt\"}}", true)]
        [InlineData(409, "{}", false)]
        [InlineData(500, "{\"error\":{\"code\":\"internal_error\",\"message\":\"internal_error\"}}", false)]
        [InlineData(500, "{\"error\":{\"code\":\"image_unsupported\",\"message\":\"image_unsupported\"}}", false)]
        [InlineData(409, "{\"error\":{\"code\":\"image_unsupported\",\"message\":\"image_unsupported\"},\"extra\":true}", false)]
        [InlineData(0, "", false)]
        public void Retry_requires_proven_pre_admission_refusal_not_an_arbitrary_http_or_connection_failure(int status, string body, bool canRetry)
        {
            RunOnSta(() =>
            {
                using var handler = new RefusalHandler(status, body);
                using var h = Harness.Create(handler);
                h.Submit();
                Assert.False(h.IsProcessing);
                Assert.Equal(canRetry, ((Button)Get(h.Tab, typeof(ChatTab), "_sendButton")).Enabled);
                h.Submit();
                Assert.Equal(canRetry ? 2 : 1, handler.Prompts);
                Assert.Equal("offline-fixture", h.Tab.ConversationId);
            });
        }

        [Fact]
        public void Local_image_refusal_does_not_block_a_later_valid_submission()
        {
            RunOnSta(() =>
            {
                using var handler = new PromptHandler(Terminal("settled", "end_turn"));
                using var h = Harness.Create(handler);
                h.Submit(images: new[] { new ChatImageInput("fixture", "unsupported", "") });
                Assert.Equal(0, handler.RequestCount);
                Assert.True(((Button)Get(h.Tab, typeof(ChatTab), "_sendButton")).Enabled);
                h.Submit();
                Assert.Equal(1, handler.RequestCount);
            });
        }

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public void Bridge_acceptance_means_handled_not_successful_and_blocked_submissions_are_refused(bool uncertain)
        {
            RunOnSta(() =>
            {
                using HttpMessageHandler handler = uncertain ? new UnsettledPromptHandler() : new PromptHandler(Terminal("refused", "refusal"));
                using var h = Harness.Create(handler);
                var reply = h.Submit(bridge: true);
                Assert.NotNull(reply);
                Assert.True(reply!["accepted"]!.GetValue<bool>());
                if (uncertain)
                {
                    var before = h.Scripts.Count;
                    Assert.False(h.Submit(bridge: true)!["accepted"]!.GetValue<bool>());
                    Assert.False(h.Submit(bridge: true)!["accepted"]!.GetValue<bool>());
                    Assert.Equal(before, h.Scripts.Count);
                    Assert.Equal(1, ((UnsettledPromptHandler)handler).Prompts);
                }
            });
        }

        // ─── Lifecycle contract (plan §A) ─────────────────────────────

        [Fact]
        public void Completion_barrier_preserves_pending_presentation_and_gates_the_next_prompt()
        {
            RunOnSta(() =>
            {
                using var handler = new PromptHandler(
                    Text("alpha ") + Tool("t1", "in_progress") + Text("beta") + Tool("t1", "completed") + Terminal("settled", "end_turn"),
                    Text("next") + Terminal("settled", "end_turn"));
                using var h = Harness.Create(handler);
                Invoke(h.Tab, typeof(ChatTab), "EnableWebComposer");
                h.Pump();
                h.HoldScripts = true;

                // Turn N through the real web-composer handler, with all presentation withheld.
                var first = h.SubmitWithoutPumping();
                h.WaitForCompletion(first);
                Assert.True(h.IsProcessing);                       // ControlSettle not applied yet
                var rejected = h.SubmitWithoutPumping();
                h.WaitForCompletion(rejected);
                Assert.False(rejected.Result);                     // gate holds until settle applies
                Assert.Equal(1, handler.RequestCount);

                h.Pump();                                          // S3 drains; S4 tasks still held
                Assert.False(h.IsProcessing);
                var startedBeforeNext = h.Scripts.Count;
                Assert.Contains("window.chatAPI.finalizeStreamingMessage()", h.Scripts);
                Assert.Contains("window.chatAPI.setComposerEnabled(true, true)", h.Scripts);

                // Turn N+1 admitted; its user bubble queues behind every pending N script.
                var second = h.SubmitWithoutPumping();
                h.WaitForCompletion(second);
                Assert.True(second.Result);
                h.Pump();
                Assert.Equal(2, handler.RequestCount);
                h.ReleaseAll();

                var userBubble = h.Scripts.FindLastIndex(s => s.StartsWith("window.chatAPI.addMessage('user'"));
                Assert.True(userBubble >= startedBeforeNext, "N+1 user bubble executed before N's presentation finished");
                Assert.Equal(new[] { "alpha ", "beta", "next" }, Segments(h.Scripts));
                Assert.Equal(2, h.Scripts.Count(s => s == "window.chatAPI.finalizeStreamingMessage()"));
                Assert.Equal("window.chatAPI.setComposerEnabled(true, true)", h.Scripts.Last(s => s.Contains("setComposerEnabled")));
                Assert.Empty(h.SynchronousScripts);
            });
        }

        [Fact]
        public void Failure_after_partial_output_finalizes_then_errors_then_settles()
        {
            RunOnSta(() =>
            {
                using var handler = new UnsettledPromptHandler();
                using var h = Harness.Create(handler);
                Invoke(h.Tab, typeof(ChatTab), "EnableWebComposer");
                h.Pump();
                h.Submit();
                var order = h.Scripts.Select(s => s.Split('(')[0]).ToList();
                var partial = h.Scripts.FindIndex(s => s == "window.chatAPI.appendStreaming('partial')");
                var finalize = h.Scripts.FindIndex(s => s == "window.chatAPI.finalizeStreamingMessage()");
                var error = h.Scripts.FindIndex(s => s.StartsWith("window.chatAPI.addMessage('error'"));
                var settle = h.Scripts.FindLastIndex(s => s == "window.chatAPI.setComposerEnabled(true, false)");
                Assert.True(partial >= 0 && finalize > partial && error > finalize && settle > error,
                    "expected partial → finalize → error → settle, got: " + string.Join(" | ", order));
                Assert.False(h.IsProcessing);
                Assert.StartsWith("Request outcome is unconfirmed.", h.StatusText);
            });
        }

        [Fact]
        public void Clear_after_settlement_keeps_the_composer_control_script_through_a_not_ready_replay()
        {
            RunOnSta(() =>
            {
                using var handler = new PromptHandler(Text("hello") + Terminal("settled", "end_turn"));
                using var h = Harness.Create(handler);
                Invoke(h.Tab, typeof(ChatTab), "EnableWebComposer");
                h.Pump();
                h.Scripts.Clear();                                 // drop the composer script from enabling
                // Document not ready: everything buffers at the surface.
                Set(h.Surface, h.Surface.GetType().BaseType!, "_webViewReady", false);
                h.Submit();
                Assert.False(h.IsProcessing);
                Assert.Empty(h.Scripts);
                Assert.True(h.BufferedScripts > 0);

                Invoke(h.Tab, typeof(ChatTab), "OnClearClicked", new object(), EventArgs.Empty);
                h.Pump();
                // Replay after Clear: control scripts survive, stale content is dropped.
                // (The layout is not built in this offline fixture, so keep the
                // web-composer ready hook from touching layout controls.)
                Set(h.Tab, typeof(ChatTab), "_useWebComposer", false);
                Invoke(h.Surface, h.Surface.GetType().BaseType!, "OnDocumentLoaded",
                    (object?)null, new WebViewLoadedEventArgs(new Uri("https://app.rook.invalid/chat.html")));
                h.Pump();
                Assert.Contains("window.chatAPI.setComposerEnabled(true, true)", h.Scripts);
                Assert.DoesNotContain(h.Scripts, s => s.StartsWith("window.chatAPI.appendStreaming("));
                Assert.DoesNotContain(h.Scripts, s => s.StartsWith("window.chatAPI.addMessage('user'"));
                Assert.Contains("window.chatAPI.clearMessages()", h.Scripts);
                Assert.True(h.Scripts.IndexOf("window.chatAPI.clearMessages()") < h.Scripts.LastIndexOf("window.chatAPI.setComposerEnabled(true, true)"));
                Assert.False(h.IsProcessing);
            });
        }

        [Fact]
        public void Clear_during_streaming_discards_content_but_the_terminal_still_settles_controls()
        {
            RunOnSta(() =>
            {
                using var handler = new PromptHandler(Text("hello ") + Text("world") + Terminal("settled", "end_turn"),
                    Text("next") + Terminal("settled", "end_turn"));
                using var h = Harness.Create(handler);
                Invoke(h.Tab, typeof(ChatTab), "EnableWebComposer");
                h.Pump();
                var first = h.SubmitWithoutPumping();
                h.WaitForCompletion(first);                        // all items queued, nothing drained
                Invoke(h.Tab, typeof(ChatTab), "OnClearClicked", new object(), EventArgs.Empty);
                h.Pump();
                Assert.False(h.IsProcessing);                      // ControlSettle applied despite Clear
                Assert.DoesNotContain(h.Scripts, s => s.StartsWith("window.chatAPI.appendStreaming("));
                Assert.Contains("window.chatAPI.clearMessages()", h.Scripts);
                Assert.Equal("window.chatAPI.setComposerEnabled(true, true)", h.Scripts.Last(s => s.Contains("setComposerEnabled")));
                h.Submit();                                        // next submission works
                Assert.Equal(2, handler.RequestCount);
                Assert.Equal(new[] { "next" }, Segments(h.Scripts));
            });
        }

        [Fact]
        public void Oversized_tool_payloads_are_summarized_before_becoming_a_script()
        {
            var big = "{\"status\":\"in_progress\",\"catalog\":\"" + new string('x', AgentChatTab.MaxToolCardPayloadBytes) + "\",\"z\":1}";
            using var payload = JsonDocument.Parse(big);
            var bounded = AgentChatTab.BoundToolCardPayload(payload.RootElement.Clone());
            using var parsed = JsonDocument.Parse(bounded);
            Assert.True(parsed.RootElement.GetProperty("truncated").GetBoolean());
            Assert.Equal(big.Length, parsed.RootElement.GetProperty("bytes").GetInt32());
            Assert.Equal(new[] { "status", "catalog", "z" }, parsed.RootElement.GetProperty("keys").EnumerateArray().Select(k => k.GetString()));
            Assert.Equal("{\"a\":1}", AgentChatTab.BoundToolCardPayload(JsonDocument.Parse("{\"a\":1}").RootElement.Clone()));
        }

        [Fact]
        public void No_synchronous_ui_or_script_calls_remain_on_the_chat_stream_path()
        {
            var root = FindRepoRoot();
            foreach (var relative in new[] { "src/Rook/UI/Chat/ChatTab.cs", "src/Rook/UI/Chat/AgentChatTab.cs" })
            {
                var source = File.ReadAllText(Path.Combine(root, relative));
                Assert.DoesNotContain("Application.Instance.Invoke(", source);
                Assert.DoesNotContain(".ExecuteScript(", source);
            }
            var surface = File.ReadAllText(Path.Combine(root, "src/Rook/UI/Web/RookWebSurface.cs"));
            var post = ExtractMethod(surface, "public void PostScript(ScriptRequest request)");
            Assert.Contains("_uiScheduler(", post);
            Assert.DoesNotContain("Application.Instance.Invoke", post);
            var start = ExtractMethod(surface, "private void TryStartScripts()");
            Assert.Contains("ExecuteScriptAsyncCore", start);
            Assert.DoesNotContain(".ExecuteScript(", start);
        }

        // ─── Helpers ──────────────────────────────────────────────────

        // Legacy seams used by RookChatGuidanceTests / RookChatConfigurationTests via
        // reflection: a tab whose UI scheduler runs inline on the owning STA thread
        // (so direct handler calls keep their synchronous semantics) and queues work
        // arriving from the background reader, which Prompt(tab) pumps.
        private static readonly System.Runtime.CompilerServices.ConditionalWeakTable<AgentChatTab, Harness> s_legacy = new();

        internal static AgentChatTab CreateTab(AgentChatClient client, List<string> scripts)
        {
            var h = Harness.Create(client, scripts);
            var owner = Thread.CurrentThread;
            h.Tab.UiScheduler = action =>
            {
                if (Thread.CurrentThread == owner) action();
                else h.Scheduler.Enqueue(action);
            };
            s_legacy.Add(h.Tab, h);
            return h.Tab;
        }

        internal static void Prompt(AgentChatTab tab)
        {
            if (s_legacy.TryGetValue(tab, out var h)) { h.Prompt(); return; }
            ((Task)Invoke(tab, typeof(AgentChatTab), "RunPromptAsync", "local fixture", Array.Empty<ChatImageInput>())).GetAwaiter().GetResult();
        }

        internal static List<string> Segments(IReadOnlyList<string> scripts)
        {
            var segments = new List<string>();
            var current = new StringBuilder();
            var open = false;
            const string append = "window.chatAPI.appendStreaming('";
            foreach (var s in scripts)
            {
                if (s.StartsWith(append, StringComparison.Ordinal))
                {
                    current.Append(s.Substring(append.Length, s.Length - append.Length - 2).Replace("\\'", "'"));
                    open = true;
                }
                else if (s == "window.chatAPI.finalizeStreamingMessage()" ||
                         s.StartsWith("window.chatAPI.renderToolCard(", StringComparison.Ordinal) ||
                         s == "window.chatAPI.clearMessages()")
                {
                    if (open) { segments.Add(current.ToString()); current.Clear(); open = false; }
                }
            }
            if (open) segments.Add(current.ToString());
            return segments;
        }

        private static string FindRepoRoot()
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory != null && !File.Exists(Path.Combine(directory.FullName, "src", "Rook", "Rook.csproj")))
                directory = directory.Parent;
            return directory?.FullName ?? throw new InvalidOperationException("repo root not found");
        }

        private static string ExtractMethod(string source, string signature)
        {
            var start = source.IndexOf(signature, StringComparison.Ordinal);
            Assert.True(start >= 0, "signature not found: " + signature);
            var brace = source.IndexOf('{', start);
            var depth = 0;
            for (var i = brace; i < source.Length; i++)
            {
                if (source[i] == '{') depth++;
                else if (source[i] == '}' && --depth == 0) return source.Substring(start, i - start + 1);
            }
            throw new InvalidOperationException("unbalanced method body");
        }

        private sealed class RefusalHandler : HttpMessageHandler
        {
            private readonly int _status;
            private readonly string _body;
            public int Prompts { get; private set; }
            public RefusalHandler(int status, string body) { _status = status; _body = body; }
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
            {
                Assert.Equal("/agent/chat/conversations/offline-fixture/prompt", request.RequestUri!.AbsolutePath);
                Prompts++;
                if (_status == 0) throw new HttpRequestException("synthetic lost connection");
                return Task.FromResult(new HttpResponseMessage(Prompts == 1 ? (HttpStatusCode)_status : HttpStatusCode.OK)
                { Content = new StringContent(Prompts == 1 ? _body : Terminal("settled", "end_turn"), Encoding.UTF8) });
            }
        }

        private sealed class SubmitContext : SynchronizationContext
        {
            internal readonly ConcurrentQueue<Action> Actions = new();
            public override void Post(SendOrPostCallback d, object? state) => Actions.Enqueue(() => d(state));
        }

        private sealed class UnsettledPromptHandler : HttpMessageHandler
        {
            public int Prompts { get; private set; }
            public int Cancels { get; private set; }
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
            {
                Assert.Equal(HttpMethod.Post, request.Method);
                var path = request.RequestUri!.AbsolutePath;
                if (path == "/agent/chat/conversations/offline-fixture/cancel")
                {
                    Cancels++;
                    return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
                    { Content = new StringContent("{\"accepted\":true}", Encoding.UTF8, "application/json") });
                }
                Assert.Equal("/agent/chat/conversations/offline-fixture/prompt", path);
                Prompts++;
                return Task.FromResult(Prompts == 1
                    ? new HttpResponseMessage(HttpStatusCode.OK)
                    { Content = new StringContent(Text("partial"), Encoding.UTF8, "application/x-ndjson") }
                    : new HttpResponseMessage(HttpStatusCode.Conflict)
                    { Content = new StringContent("{\"error\":{\"code\":\"conversation_busy\",\"message\":\"conversation_busy\"}}", Encoding.UTF8, "application/json") });
            }
        }

        /// <summary>
        /// Real tab + surface with a recording UI scheduler and a controllable script
        /// executor. Pump() runs marshaled work; HoldScripts keeps S4 tasks incomplete
        /// until ReleaseAll().
        /// </summary>
        internal sealed class Harness : IDisposable
        {
            public List<string> Scripts = new();                     // started, in admission order
            public readonly List<string> SynchronousScripts = new(); // must stay empty
            public readonly ConcurrentQueue<Action> Scheduler = new();
            private readonly List<TaskCompletionSource<string>> _held = new();
            public bool HoldScripts;
            public AgentChatTab Tab = null!;
            public object Surface = null!;
            public AgentChatClient Client = null!;

            public static Harness Create(HttpMessageHandler handler)
                => Create(AgentChatClient.ForTests(handler, new Uri("http://127.0.0.1:1")), new List<string>());

            public static Harness Create(AgentChatClient client, List<string> scripts)
            {
                Rook.Tests.UI.EtoTestPlatform.Ensure();
                SynchronizationContext.SetSynchronizationContext(null);
                var h = new Harness { Client = client, Scripts = scripts };
                var tab = new AgentChatTab(new CreateConversationRequest(), h.Client, null, initializePresentation: false);
                Invoke(tab, typeof(ChatTab), "InitializeComponents");
                Set(tab, typeof(ChatTab), "_statusStack", new StackLayout());
                Set(tab, typeof(AgentChatTab), "_conversationBaseUri", new Uri("http://127.0.0.1:1"));
                Set(tab, typeof(AgentChatTab), "_conversationId", "offline-fixture");
                var surface = Get(tab, typeof(ChatTab), "_webSurface");
                // Replace only Eto's native script executor. The actual tab, HTTP parser,
                // ChatTab and RookWebSurface execute unchanged; no browser/service is started.
                var view = (WebView)FormatterServices.GetUninitializedObject(typeof(WebView));
                Set(view, typeof(Eto.Widget), "_handler", new ScriptHandler(h).GetTransparentProxy());
                Set(surface, surface.GetType().BaseType!, "_webView", view);
                Set(surface, surface.GetType().BaseType!, "_webViewReady", true);
                tab.UiScheduler = action => h.Scheduler.Enqueue(action);
                h.Tab = tab;
                h.Surface = surface;
                return h;
            }

            public bool IsProcessing => (bool)Get(Tab, typeof(ChatTab), "_isProcessing");
            public string StatusText => ((Label)Get(Tab, typeof(ChatTab), "_statusLabel")).Text;
            public int BufferedScripts => (int)Surface.GetType().BaseType!
                .GetProperty("BufferedScripts", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(Surface);

            public Task<string> Execute(string script)
            {
                Scripts.Add(script);
                if (!HoldScripts) return Task.FromResult(string.Empty);
                var tcs = new TaskCompletionSource<string>();
                _held.Add(tcs);
                return tcs.Task;
            }

            /// <summary>Run every marshaled callback until the scheduler is empty.</summary>
            public void Pump()
            {
                var guard = 0;
                while (Scheduler.TryDequeue(out var action))
                {
                    action();
                    Assert.True(++guard < 100_000, "runaway scheduler loop");
                }
            }

            /// <summary>Complete held scripts in admission order, pumping the continuations.</summary>
            public void ReleaseAll()
            {
                HoldScripts = false;
                while (_held.Count > 0)
                {
                    var tcs = _held[0];
                    _held.RemoveAt(0);
                    tcs.TrySetResult(string.Empty);
                    Pump();
                }
                Pump();
            }

            public void Prompt()
            {
                var task = (Task)Invoke(Tab, typeof(AgentChatTab), "RunPromptAsync", "local fixture", Array.Empty<ChatImageInput>());
                WaitForCompletion(task);
                task.GetAwaiter().GetResult();
                Pump();
            }

            public Task<bool> SubmitWithoutPumping()
                => (Task<bool>)Invoke(Tab, typeof(ChatTab), "SubmitWebInputAsync", "local fixture", Array.Empty<ChatImageInput>());

            public void WaitForCompletion(Task task)
            {
                var deadline = System.Diagnostics.Stopwatch.StartNew();
                while (!task.IsCompleted && deadline.Elapsed < TimeSpan.FromSeconds(10)) Thread.Sleep(1);
                Assert.True(task.IsCompleted, "Synthetic request did not settle.");
            }

            public JsonNode? Submit(bool native = false, IReadOnlyList<ChatImageInput>? images = null, bool bridge = false)
            {
                var previous = SynchronizationContext.Current;
                var context = new SubmitContext();
                SynchronizationContext.SetSynchronizationContext(context);
                try
                {
                    Task task;
                    if (bridge)
                    {
                        var payload = JsonNode.Parse("{\"type\":\"submit\",\"text\":\"local fixture\",\"images\":[]}");
                        task = (Task)Invoke(Surface, Surface.GetType(), "HandleSubmit", payload!);
                    }
                    else if (native)
                    {
                        ((TextArea)Get(Tab, typeof(ChatTab), "_inputArea")).Text = "local fixture";
                        Func<string, Task> action = text => (Task)Invoke(Tab, typeof(AgentChatTab), "OnSendMessage", text);
                        task = (Task)Invoke(Tab, typeof(ChatTab), "SubmitInputAsync", action);
                    }
                    else task = (Task)Invoke(Tab, typeof(ChatTab), "SubmitWebInputAsync", "local fixture", images ?? Array.Empty<ChatImageInput>());
                    var deadline = System.Diagnostics.Stopwatch.StartNew();
                    while (!task.IsCompleted && deadline.Elapsed < TimeSpan.FromSeconds(10))
                    {
                        if (context.Actions.TryDequeue(out var action)) action();
                        else if (Scheduler.TryDequeue(out var scheduled)) scheduled();
                        else Thread.Sleep(1);
                    }
                    Assert.True(task.IsCompleted, "Synthetic submission did not settle.");
                    task.GetAwaiter().GetResult();
                    while (context.Actions.TryDequeue(out var late)) late();
                    Pump();
                    return task is Task<JsonNode?> acknowledgement ? acknowledgement.GetAwaiter().GetResult() : null;
                }
                finally { SynchronizationContext.SetSynchronizationContext(previous); }
            }

            public void Dispose()
            {
                Tab.Dispose();
                Client.Dispose();
            }
        }

        private static string Text(string text)
            => JsonSerializer.Serialize(new { type = "text_delta", text }) + "\n";

        private static string Tool(string id, string status)
            => JsonSerializer.Serialize(new
            {
                type = "tool_update", messageId = id, kind = "tool_call",
                payload = new { status, toolCallId = id },
            }) + "\n";

        private static string Terminal(string outcome, string stopReason)
            => JsonSerializer.Serialize(new
            {
                type = "terminal", outcome, stopReason, presentationOutcome = "delivered", cachePublished = true,
            }) + "\n";

        private static object Get(object target, Type type, string name)
            => type.GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(target);
        private static void Set(object target, Type type, string name, object value)
            => type.GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(target, value);
        private static object Invoke(object target, Type type, string name, params object?[] args)
            => type.GetMethod(name, BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(target, args);

        private void RunOnSta(Action action) => _ui.Run(action);

        public sealed class PanelThread : IDisposable
        {
            private readonly BlockingCollection<Action> _actions = new();
            private readonly Thread _thread;
            public PanelThread()
            {
                // Eto's application belongs to one STA for the whole collection.
                _thread = new Thread(() => { foreach (var action in _actions.GetConsumingEnumerable()) action(); })
                    { IsBackground = true };
                _thread.SetApartmentState(ApartmentState.STA);
                _thread.Start();
            }
            public void Run(Action action)
            {
                Exception? failure = null;
                using var done = new ManualResetEventSlim();
                _actions.Add(() => { try { action(); } catch (Exception ex) { failure = ex; } finally { done.Set(); } });
                Assert.True(done.Wait(TimeSpan.FromSeconds(30)), "Offline panel test did not settle.");
                if (failure != null) throw new AggregateException(failure);
            }
            public void Dispose()
            {
                _actions.CompleteAdding();
                Assert.True(_thread.Join(TimeSpan.FromSeconds(5)), "Offline UI thread did not exit.");
                _actions.Dispose();
            }
        }

        private sealed class PromptHandler : HttpMessageHandler
        {
            private readonly Queue<string> _responses;
            public int RequestCount { get; private set; }
            public PromptHandler(params string[] responses) => _responses = new Queue<string>(responses);
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
            {
                Assert.Equal(HttpMethod.Post, request.Method);
                Assert.Equal("/agent/chat/conversations/offline-fixture/prompt", request.RequestUri!.AbsolutePath);
                RequestCount++;
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(_responses.Dequeue(), Encoding.UTF8, "application/x-ndjson"),
                });
            }
        }

        private sealed class ScriptHandler : RealProxy
        {
            private readonly Harness _harness;
            public ScriptHandler(Harness harness) : base(typeof(WebView.IHandler)) => _harness = harness;
            public override IMessage Invoke(IMessage message)
            {
                var call = (IMethodCallMessage)message;
                if (call.MethodName == "ExecuteScriptAsync")
                    return new ReturnMessage(_harness.Execute((string)call.Args[0]), null, 0, call.LogicalCallContext, call);
                if (call.MethodName == "ExecuteScript")
                {
                    _harness.SynchronousScripts.Add((string)call.Args[0]);
                    return new ReturnMessage("", null, 0, call.LogicalCallContext, call);
                }
                if (call.MethodName == "Dispose") return new ReturnMessage(null, null, 0, call.LogicalCallContext, call);
                return new ReturnMessage(new InvalidOperationException("Unexpected WebView boundary: " + call.MethodName), call);
            }
        }
    }
}
