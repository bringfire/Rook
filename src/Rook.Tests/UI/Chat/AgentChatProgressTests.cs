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

        private static AgentChatTab CreateTab(AgentChatClient client, List<string> scripts)
        {
            if (Application.Instance == null) _ = new Application(Eto.Platforms.Wpf);
            SynchronizationContext.SetSynchronizationContext(null);
            var tab = new AgentChatTab(new CreateConversationRequest(), client, null, initializePresentation: false);
            Invoke(tab, typeof(ChatTab), "InitializeComponents");
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
