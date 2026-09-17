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
using Xunit;

namespace Rook.Tests.UI.Chat
{
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
                var scripts = new List<string>();
                using var handler = new PromptHandler(
                    Text("alpha ") + Text("repeat.") + Tool("t1", "in_progress") +
                    Tool("t2", "in_progress") + Tool("t1", "completed") + Text("beta ") +
                    Tool("t2", "failed") + Text("repeat.") + Tool("t3", "in_progress") +
                    Text("repeat.") + Terminal(outcome, stopReason),
                    Text("next") + Terminal("settled", "end_turn"));
                using var client = AgentChatClient.ForTests(handler, new Uri("http://127.0.0.1:1"));
                using var tab = CreateTab(client, scripts);

                Prompt(tab);
                Prompt(tab);
                Assert.Equal(2, handler.RequestCount);
                // Retain real emitted commands even on RED; the HTML test consumes these,
                // never a second implementation of the managed accumulation logic.
                var directory = Environment.GetEnvironmentVariable("ROOK_PROGRESS_TEST_OUTPUT");
                if (!string.IsNullOrEmpty(directory))
                {
                    Directory.CreateDirectory(directory);
                    File.WriteAllText(Path.Combine(directory, outcome + ".json"),
                        JsonSerializer.Serialize(scripts), new UTF8Encoding(false));
                }
                Assert.Equal(new[] { "alpha ", "alpha repeat.", "beta ", "beta repeat.", "repeat.", "next" },
                    scripts.Where(s => s.StartsWith("window.chatAPI.updateStreamingMessage('", StringComparison.Ordinal))
                        .Select(s => s.Substring("window.chatAPI.updateStreamingMessage('".Length).Replace("')", "")));
                Assert.Equal(2, scripts.Count(s => s == "window.chatAPI.finalizeStreamingMessage()"));
            });
        }

        [Fact]
        public void Detached_panel_does_not_render_or_reset_its_buffer()
        {
            RunOnSta(() =>
            {
                var scripts = new List<string>();
                using var handler = new PromptHandler();
                using var client = AgentChatClient.ForTests(handler, new Uri("http://127.0.0.1:1"));
                using var tab = CreateTab(client, scripts);
                Set(tab, typeof(AgentChatTab), "_assistantBuffer", new StringBuilder("retained"));
                Set(tab, typeof(AgentChatTab), "_uiAttached", false);
                using var payload = JsonDocument.Parse("{\"status\":\"in_progress\"}");
                Invoke(tab, typeof(AgentChatTab), "HandleChatEvent", new ChatEvent
                {
                    Type = "tool_update", Payload = payload.RootElement.Clone(),
                });
                Assert.Empty(scripts);
                Assert.Equal("retained", Get(tab, typeof(AgentChatTab), "_assistantBuffer").ToString());
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
                using var client = AgentChatClient.ForTests(handler, new Uri("http://127.0.0.1:1"));
                using var tab = CreateTab(client, new List<string>());
                Submit(tab);
                Assert.Equal(1, handler.RequestCount);
                Assert.False((bool)Get(tab, typeof(ChatTab), "_isProcessing"));
                Assert.Equal(status, ((Label)Get(tab, typeof(ChatTab), "_statusLabel")).Text);
                Submit(tab);
                Assert.Equal(2, handler.RequestCount);
                Assert.Equal("offline-fixture", tab.ConversationId);
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
                using var client = AgentChatClient.ForTests(handler, new Uri("http://127.0.0.1:1"));
                var scripts = new List<string>();
                using var tab = CreateTab(client, scripts);
                Invoke(tab, typeof(ChatTab), "EnableWebComposer");
                Submit(tab, nativeFirst);
                Assert.Equal(1, handler.Prompts);
                Assert.Equal(1, handler.Cancels);
                Assert.False((bool)Get(tab, typeof(ChatTab), "_isProcessing"));
                Assert.False(((Button)Get(tab, typeof(ChatTab), "_sendButton")).Enabled);
                Assert.Equal("Request outcome is unconfirmed. Another request is blocked because the previous one may still be running.",
                    ((Label)Get(tab, typeof(ChatTab), "_statusLabel")).Text);
                Assert.Contains("window.chatAPI.showTypingIndicator(false)", scripts);
                Assert.Equal("window.chatAPI.setComposerEnabled(true, false)", scripts.Last(s => s.Contains("setComposerEnabled")));
                // Neither a normal processing reset nor an updated view may erase uncertainty.
                Invoke(tab, typeof(ChatTab), "SetProcessing", false);
                Invoke(tab, typeof(AgentChatTab), "ApplyConversationStatus", new ConversationView
                { ConversationId = "offline-fixture", TargetAvailable = true });
                var before = scripts.Count;
                Submit(tab);
                Submit(tab, native: true);
                Submit(tab);
                Assert.Equal("local fixture", ((TextArea)Get(tab, typeof(ChatTab), "_inputArea")).Text);
                Assert.Equal(before, scripts.Count);
                Assert.Equal(1, handler.Prompts);
                Assert.Equal(1, handler.Cancels);
                Assert.Equal("offline-fixture", tab.ConversationId);
                Invoke(tab, typeof(ChatTab), "OnClearClicked", new object(), EventArgs.Empty);
                Assert.False(((Button)Get(tab, typeof(ChatTab), "_sendButton")).Enabled);
                Assert.StartsWith("Request outcome is unconfirmed.", ((Label)Get(tab, typeof(ChatTab), "_statusLabel")).Text);
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
                using var client = AgentChatClient.ForTests(handler, new Uri("http://127.0.0.1:1"));
                using var tab = CreateTab(client, new List<string>());
                Submit(tab);
                Assert.False((bool)Get(tab, typeof(ChatTab), "_isProcessing"));
                Assert.Equal(canRetry, ((Button)Get(tab, typeof(ChatTab), "_sendButton")).Enabled);
                Submit(tab);
                Assert.Equal(canRetry ? 2 : 1, handler.Prompts);
                Assert.Equal("offline-fixture", tab.ConversationId);
            });
        }

        [Fact]
        public void Local_image_refusal_does_not_block_a_later_valid_submission()
        {
            RunOnSta(() =>
            {
                using var handler = new PromptHandler(Terminal("settled", "end_turn"));
                using var client = AgentChatClient.ForTests(handler, new Uri("http://127.0.0.1:1"));
                using var tab = CreateTab(client, new List<string>());
                Submit(tab, images: new[] { new ChatImageInput("fixture", "unsupported", "") });
                Assert.Equal(0, handler.RequestCount);
                Assert.True(((Button)Get(tab, typeof(ChatTab), "_sendButton")).Enabled);
                Submit(tab);
                Assert.Equal(1, handler.RequestCount);
            });
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

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public void Bridge_acceptance_means_handled_not_successful_and_blocked_submissions_are_refused(bool uncertain)
        {
            RunOnSta(() =>
            {
                using HttpMessageHandler handler = uncertain ? new UnsettledPromptHandler() : new PromptHandler(Terminal("refused", "refusal"));
                using var client = AgentChatClient.ForTests(handler, new Uri("http://127.0.0.1:1"));
                var scripts = new List<string>();
                using var tab = CreateTab(client, scripts);
                var reply = Submit(tab, bridge: true);
                Assert.NotNull(reply);
                Assert.True(reply!["accepted"]!.GetValue<bool>());
                if (uncertain)
                {
                    var before = scripts.Count;
                    Assert.False(Submit(tab, bridge: true)!["accepted"]!.GetValue<bool>());
                    Assert.False(Submit(tab, bridge: true)!["accepted"]!.GetValue<bool>());
                    Assert.Equal(before, scripts.Count);
                    Assert.Equal(1, ((UnsettledPromptHandler)handler).Prompts);
                }
            });
        }

        private static JsonNode? Submit(AgentChatTab tab, bool native = false, IReadOnlyList<ChatImageInput>? images = null, bool bridge = false)
        {
            var previous = SynchronizationContext.Current;
            var context = new SubmitContext();
            SynchronizationContext.SetSynchronizationContext(context);
            try
            {
                Task task;
                if (bridge)
                {
                    var surface = Get(tab, typeof(ChatTab), "_webSurface");
                    var payload = JsonNode.Parse("{\"type\":\"submit\",\"text\":\"local fixture\",\"images\":[]}");
                    task = (Task)Invoke(surface, surface.GetType(), "HandleSubmit", payload!);
                }
                else if (native)
                {
                    ((TextArea)Get(tab, typeof(ChatTab), "_inputArea")).Text = "local fixture";
                    Func<string, Task> action = text => (Task)Invoke(tab, typeof(AgentChatTab), "OnSendMessage", text);
                    task = (Task)Invoke(tab, typeof(ChatTab), "SubmitInputAsync", action);
                }
                else task = (Task)Invoke(tab, typeof(ChatTab), "SubmitWebInputAsync", "local fixture", images ?? Array.Empty<ChatImageInput>());
                var deadline = System.Diagnostics.Stopwatch.StartNew();
                while (!task.IsCompleted && deadline.Elapsed < TimeSpan.FromSeconds(10))
                {
                    if (context.Actions.TryDequeue(out var action)) action();
                    else Thread.Sleep(1);
                }
                Assert.True(task.IsCompleted, "Synthetic submission did not settle.");
                task.GetAwaiter().GetResult();
                return task is Task<JsonNode?> acknowledgement ? acknowledgement.GetAwaiter().GetResult() : null;
            }
            finally { SynchronizationContext.SetSynchronizationContext(previous); }
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

        private static AgentChatTab CreateTab(AgentChatClient client, List<string> scripts)
        {
            if (Application.Instance == null) _ = new Application(Eto.Platforms.Wpf);
            SynchronizationContext.SetSynchronizationContext(null);
            var tab = new AgentChatTab(new CreateConversationRequest(), client, null, initializePresentation: false);
            Invoke(tab, typeof(ChatTab), "InitializeComponents");
            Set(tab, typeof(ChatTab), "_statusStack", new StackLayout());
            Set(tab, typeof(AgentChatTab), "_conversationBaseUri", new Uri("http://127.0.0.1:1"));
            Set(tab, typeof(AgentChatTab), "_conversationId", "offline-fixture");
            var surface = Get(tab, typeof(ChatTab), "_webSurface");
            // Replace only Eto's native script executor. The actual tab, HTTP parser,
            // ChatTab and RookWebSurface execute unchanged; no browser/service is started.
            var view = (WebView)FormatterServices.GetUninitializedObject(typeof(WebView));
            Set(view, typeof(Eto.Widget), "_handler", new ScriptHandler(scripts).GetTransparentProxy());
            Set(surface, surface.GetType().BaseType!, "_webView", view);
            Set(surface, surface.GetType().BaseType!, "_webViewReady", true);
            return tab;
        }

        private static void Prompt(AgentChatTab tab)
            => ((Task)Invoke(tab, typeof(AgentChatTab), "RunPromptAsync", "local fixture", Array.Empty<ChatImageInput>()))
                .GetAwaiter().GetResult();

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
        private static object Invoke(object target, Type type, string name, params object[] args)
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
                Assert.True(done.Wait(TimeSpan.FromSeconds(20)), "Offline panel test did not settle.");
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
            private readonly List<string> _scripts;
            public ScriptHandler(List<string> scripts) : base(typeof(WebView.IHandler)) => _scripts = scripts;
            public override IMessage Invoke(IMessage message)
            {
                var call = (IMethodCallMessage)message;
                if (call.MethodName == "ExecuteScript")
                {
                    _scripts.Add((string)call.Args[0]);
                    return new ReturnMessage("", null, 0, call.LogicalCallContext, call);
                }
                if (call.MethodName == "Dispose") return new ReturnMessage(null, null, 0, call.LogicalCallContext, call);
                return new ReturnMessage(new InvalidOperationException("Unexpected WebView boundary: " + call.MethodName), call);
            }
        }
    }
}
