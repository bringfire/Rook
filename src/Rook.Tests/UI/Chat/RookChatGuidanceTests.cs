using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Eto.Forms;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    [Xunit.Collection(Rook.Tests.UI.EtoUiCollection.Name)]
    public sealed class RookChatGuidanceTests : IClassFixture<AgentChatProgressTests.PanelThread>
    {
        private readonly AgentChatProgressTests.PanelThread _ui;
        public RookChatGuidanceTests(AgentChatProgressTests.PanelThread ui) => _ui = ui;
        private const BindingFlags Private = BindingFlags.Instance | BindingFlags.NonPublic;

        [Theory]
        [InlineData(false, "none", "oauth", "model", "New conversations: open Settings to connect a provider or configure a local model.")]
        [InlineData(true, "local_no_account", "none", "model", "")]
        [InlineData(false, "local_no_account", "none", "model", "")]
        [InlineData(true, "dedicated", "api_key", null, "No default model saved. You can choose one in Settings.")]
        [InlineData(true, "dedicated", "oauth", "model", "")]
        public async Task Guidance_uses_reported_configuration_not_catalog_or_credential_presence(
            bool configured, string route, string credential, string? model, string expected)
        {
            using var f = new GuidanceFixture(_ui);
            f.Handler.Reply = b => Task.FromResult(Reply(b, Snapshot(configured, route, credential, model)));
            await f.Pump(f.Start(() => f.Panel.RefreshSetupGuidanceAsync(f.Client)));
            f.Ui(() => { Assert.Equal(expected, f.Text); Assert.Equal(expected.Length > 0, f.Label.Visible); });
            Assert.Single(f.Handler.Operations);
            Assert.Equal("status", f.Handler.Operations.Single());
        }

        [Theory]
        [InlineData(false, true, "Setup status unavailable.")]
        [InlineData(true, false, "Settings unavailable for the selected runtime.")]
        public async Task Unavailable_status_does_not_start_a_configuration_child(bool runtime, bool configuration, string expected)
        {
            using var f = new GuidanceFixture(_ui);
            f.Health.RuntimeAvailable = runtime;
            f.Health.ConfigurationAvailable = configuration;
            await f.Pump(f.Start(() => f.Panel.RefreshSetupGuidanceAsync(f.Client)));
            f.Ui(() => Assert.Equal(expected, f.Text));
            Assert.Empty(f.Handler.Operations);
        }

        [Fact]
        public async Task Historical_conversation_is_not_diagnosed_from_selected_store()
        {
            using var f = new GuidanceFixture(_ui);
            f.Ui(() =>
            {
                f.AttachTab();
                typeof(AgentChatTab).GetField("_reopenAssociation", Private)!.SetValue(f.Tab, new ConversationSummary { ConversationId = "historical" });
            });
            await f.Pump(f.Start(() => f.Panel.RefreshSetupGuidanceAsync(f.Client)));
            f.Ui(() =>
            {
                Assert.Equal("Saved model defaults apply to new conversations. Account and connection changes may affect conversations using the same configuration.", f.Text);
                Assert.Equal("offline-fixture", f.Tab!.ConversationId);
                Assert.True(f.Settings.Enabled);
            });
        }

        [Theory]
        [InlineData("sending")]
        [InlineData("cancelled")]
        [InlineData("error")]
        [InlineData("settled")]
        [InlineData("unconfirmed")]
        public async Task Delayed_refresh_does_not_overwrite_turn_status_or_session_settings(string state)
        {
            using var f = new GuidanceFixture(_ui);
            var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            f.Handler.Reply = async b => { await release.Task; return Reply(b, Snapshot(true, "dedicated", "oauth", null)); };
            f.Ui(() =>
            {
                f.AttachTab();
                Invoke(f.Tab!, "ApplyReportedSettings", new ReportedEffectiveSettings("actual", "model", "high"));
            });
            var pending = f.Start(() => f.Panel.RefreshSetupGuidanceAsync(f.Client));
            try
            {
                await f.Until(() => f.Handler.Operations.Count == 1);
                string before = "";
                f.Ui(() =>
                {
                    if (state == "sending")
                    {
                        typeof(ChatTab).GetMethod("SetProcessing", Private)!.Invoke(f.Tab, new object[] { true });
                        typeof(ChatTab).GetMethod("SetStatus", Private)!.Invoke(f.Tab, new object[] { "Sending...", Eto.Drawing.Colors.Blue });
                    }
                    else if (state == "unconfirmed")
                    {
                        typeof(AgentChatTab).GetField("_promptOutcomeUnconfirmed", Private)!.SetValue(f.Tab, true);
                        Invoke(f.Tab!, "ApplyConversationStatus", new ConversationView
                        {
                            ConversationId = "offline-fixture", TargetAvailable = true,
                            EffectiveSettings = new ReportedEffectiveSettings("actual", "model", "high"),
                        });
                    }
                    else Invoke(f.Tab!, "HandleChatEvent", new ChatEvent { Type = "terminal", Outcome = state, PresentationOutcome = "delivered" });
                    before = Status(f.Tab!);
                });
                release.TrySetResult(true);
                await f.Pump(pending);
                f.Ui(() =>
                {
                    Assert.Equal(before, Status(f.Tab!));
                    Assert.Equal(state == "sending", typeof(ChatTab).GetProperty("IsProcessing", Private)!.GetValue(f.Tab));
                    Assert.Equal("", f.Text);
                    Assert.Equal("offline-fixture", f.Tab!.ConversationId);
                    if (state == "unconfirmed")
                    {
                        Assert.True((bool)typeof(AgentChatTab).GetField("_promptOutcomeUnconfirmed", Private)!.GetValue(f.Tab));
                        Assert.StartsWith("Request outcome is unconfirmed.", Status(f.Tab));
                    }
                    var effective = (Label)typeof(AgentChatTab).GetField("_effectiveSettingsLabel", Private)!.GetValue(f.Tab);
                    Assert.Contains("actual/model", effective.Text);
                    Assert.Contains("high", effective.Text);
                });
            }
            finally { release.TrySetResult(true); await f.Pump(pending); }
        }

        [Fact]
        public async Task Automatic_refresh_and_settings_cannot_overlap()
        {
            using var f = new GuidanceFixture(_ui);
            var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            f.Handler.Reply = async b => { await release.Task; return Reply(b, Snapshot()); };
            var pending = f.Start(() => f.Panel.RefreshSetupGuidanceAsync(f.Client));
            try
            {
                await f.Until(() => f.Handler.Operations.Count == 1);
                await f.Pump(f.Start(() => f.Panel.RefreshSetupGuidanceAsync(f.Client)));
                bool opened = false;
                await f.Pump(f.Start(() => f.Panel.ShowConfigurationAsync(f.Client, _ => { opened = true; return Task.CompletedTask; })));
                Assert.False(opened);
                Assert.Single(f.Handler.Operations);
                f.Ui(() => Assert.False(f.Settings.Enabled));
            }
            finally { release.TrySetResult(true); await f.Pump(pending); }
            f.Ui(() => Assert.True(f.Settings.Enabled));
        }

        [Theory]
        [InlineData("busy")]
        [InlineData("unavailable-response")]
        [InlineData("unavailable-before-dispatch")]
        public async Task Non_admission_allows_a_later_explicit_settings_attempt_without_automatic_retry(string refusal)
        {
            using var f = new GuidanceFixture(_ui);
            var refuse = true;
            f.Client.ConfigurationHealthQueryForTests = _ => Task.FromResult(new ChatServiceHealth
            {
                BaseUri = f.Health.BaseUri, ServiceAvailable = true, RuntimeAvailable = true,
                ConfigurationAvailable = !(refuse && refusal == "unavailable-before-dispatch"),
            });
            f.Handler.Reply = b => Task.FromResult(refuse ? Rejection(refusal == "busy" ? 409 : 503,
                refusal == "busy" ? "configuration_busy" : "configuration_unavailable") : Reply(b, Snapshot(true, "dedicated", "oauth", "model")));
            await f.Pump(f.Start(() => f.Panel.RefreshSetupGuidanceAsync(f.Client)));
            var expected = refusal == "unavailable-before-dispatch" ? 0 : 1;
            Assert.Equal(expected, f.Handler.Operations.Count);
            f.Ui(() => Assert.True(f.Settings.Enabled));
            refuse = false;
            bool opened = false;
            await f.Pump(f.Start(() => f.Panel.ShowConfigurationAsync(f.Client, async d =>
            {
                opened = true; f.UseDialogQueue(d); await d.InitializeAsync();
                Assert.True(d.LastSettlement!.Successful);
            })));
            Assert.True(opened);
            Assert.Equal(expected + 2, f.Handler.Operations.Count);
            f.Ui(() => Assert.Equal("", f.Text));
        }

        [Theory]
        [InlineData("busy")]
        [InlineData("unavailable-before-dispatch")]
        public async Task Dialog_non_admission_does_not_trigger_a_followup_or_prevent_a_user_retry(string refusal)
        {
            using var f = new GuidanceFixture(_ui);
            bool refuse = true;
            f.Client.ConfigurationHealthQueryForTests = _ => Task.FromResult(new ChatServiceHealth
            {
                BaseUri = f.Health.BaseUri, ServiceAvailable = true, RuntimeAvailable = true,
                ConfigurationAvailable = !(refuse && refusal == "unavailable-before-dispatch"),
            });
            f.Handler.Reply = b => Task.FromResult(refuse ? Rejection(409, "configuration_busy") : Reply(b, Snapshot()));
            await f.Pump(f.Start(() => f.Panel.ShowConfigurationAsync(f.Client, async d =>
            {
                f.UseDialogQueue(d); await d.InitializeAsync();
            })));
            var count = refusal == "busy" ? 1 : 0;
            Assert.Equal(count, f.Handler.Operations.Count);
            f.Ui(() => Assert.True(f.Settings.Enabled));
            refuse = false;
            await f.Pump(f.Start(() => f.Panel.ShowConfigurationAsync(f.Client, async d =>
            {
                f.UseDialogQueue(d); await d.InitializeAsync();
                Assert.True(d.LastSettlement!.Successful);
            })));
            Assert.Equal(count + 2, f.Handler.Operations.Count);
        }

        [Theory]
        [InlineData("connection")]
        [InlineData("bare-409")]
        [InlineData("wrong-code")]
        [InlineData("server-error")]
        [InlineData("malformed")]
        [InlineData("oversized")]
        public async Task Uncertain_dispatch_is_not_reclassified_as_non_admission(string fault)
        {
            using var f = new GuidanceFixture(_ui);
            f.Handler.Reply = _ => fault switch
            {
                "connection" => throw new HttpRequestException("synthetic"),
                "bare-409" => Task.FromResult(new HttpResponseMessage(HttpStatusCode.Conflict) { Content = new StringContent("") }),
                "wrong-code" => Task.FromResult(Rejection(409, "configuration_unavailable")),
                "server-error" => Task.FromResult(Rejection(500, "configuration_busy")),
                "oversized" => Task.FromResult(new HttpResponseMessage(HttpStatusCode.Conflict) { Content = new StringContent(
                    "{\"error\":{\"code\":\"configuration_busy\",\"message\":\"configuration_busy\"}}" + new string(' ', 1024)) }),
                _ => Task.FromResult(new HttpResponseMessage(HttpStatusCode.Conflict) { Content = new StringContent("{") }),
            };
            await f.Pump(f.Start(() => f.Panel.RefreshSetupGuidanceAsync(f.Client)));
            f.Ui(() => Assert.False(f.Settings.Enabled));
            bool opened = false;
            await f.Pump(f.Start(() => f.Panel.ShowConfigurationAsync(f.Client, _ => { opened = true; return Task.CompletedTask; })));
            Assert.False(opened); Assert.Single(f.Handler.Operations);
        }

        private static HttpResponseMessage Rejection(int status, string code)
            => new((HttpStatusCode)status) { Content = new StringContent(JsonSerializer.Serialize(new { error = new { code, message = code } }), Encoding.UTF8, "application/json") };

        [Theory]
        [InlineData("exited", 0, 2)]
        [InlineData("exited", 1, 2)]
        [InlineData("unconfirmed", null, 1)]
        public async Task Dialog_followup_requires_observed_settlement_not_success_or_task_completion(string cleanup, int? exit, int expected)
        {
            using var f = new GuidanceFixture(_ui);
            f.Handler.Reply = b => Task.FromResult(Reply(b, Snapshot(), cleanup, exit));
            await f.Pump(f.Start(() => f.Panel.ShowConfigurationAsync(f.Client, async d =>
            {
                f.UseDialogQueue(d);
                await d.InitializeAsync();
                var before = f.Handler.Operations.Count;
                await f.Panel.RefreshSetupGuidanceAsync(f.Client);
                Assert.Equal(before, f.Handler.Operations.Count);
            })));
            Assert.Equal(expected, f.Handler.Operations.Count);
            f.Ui(() => Assert.Equal(cleanup == "exited", f.Settings.Enabled));
        }

        [Fact]
        public async Task Saved_outcome_survives_uncertain_cleanup_and_blocks_followup()
        {
            using var f = new GuidanceFixture(_ui);
            f.Handler.Reply = b => Task.FromResult(Reply(b, Snapshot(true, "dedicated", "oauth", "model"),
                b.GetProperty("operation").GetString() == "apiKey.set" ? "unconfirmed" : "exited",
                b.GetProperty("operation").GetString() == "apiKey.set" ? null : 0));
            await f.Pump(f.Start(() => f.Panel.ShowConfigurationAsync(f.Client, async d =>
            {
                f.UseDialogQueue(d);
                await d.InitializeAsync();
                d.ApiKey.Text = "synthetic";
                await d.RunActionAsync("apiKey.set");
                Assert.Equal("saved", d.KnownResult!.Persistence);
            })));
            Assert.Equal(new[] { "status", "apiKey.set" }, f.Handler.Operations);
            f.Ui(() => { Assert.Equal("Configuration saved; configuration cleanup is not confirmed.", f.Text); Assert.False(f.Settings.Enabled); });
        }

        [Fact]
        public async Task Confirmed_save_refreshes_guidance_without_another_user_action()
        {
            using var f = new GuidanceFixture(_ui);
            bool configured = false;
            f.Handler.Reply = b =>
            {
                if (b.GetProperty("operation").GetString() == "apiKey.set") configured = true;
                return Task.FromResult(Reply(b, Snapshot(configured, configured ? "dedicated" : "none", configured ? "api_key" : "none", "model")));
            };
            await f.Pump(f.Start(() => f.Panel.RefreshSetupGuidanceAsync(f.Client)));
            f.Ui(() => Assert.Contains("open Settings", f.Text));
            await f.Pump(f.Start(() => f.Panel.ShowConfigurationAsync(f.Client, async d =>
            {
                f.UseDialogQueue(d);
                await d.InitializeAsync();
                d.ApiKey.Text = "synthetic";
                await d.RunActionAsync("apiKey.set");
                Assert.Equal("saved", d.KnownResult!.Persistence);
            })));
            Assert.Equal(new[] { "status", "status", "apiKey.set", "status" }, f.Handler.Operations);
            f.Ui(() => { Assert.Equal("", f.Text); Assert.True(f.Settings.Enabled); });
        }

        [Fact]
        public async Task Panel_disposal_cancels_owned_refresh_and_discards_its_late_result()
        {
            using var f = new GuidanceFixture(_ui);
            var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            f.Handler.Reply = async b => { await release.Task; return Reply(b, Snapshot()); };
            var pending = f.Start(() => f.Panel.RefreshSetupGuidanceAsync(f.Client));
            try
            {
                await f.Until(() => f.Handler.Operations.Count == 1);
                f.Ui(f.ClosePanel);
                release.TrySetResult(true);
                await f.Pump(pending);
                Assert.Equal(1, f.Handler.Cancellations);
                f.Ui(() => Assert.Null(typeof(RookChatPanel).GetField("_setupStatus", Private)!.GetValue(f.Panel)));
            }
            finally { release.TrySetResult(true); await f.Pump(pending); }
        }

        private static object Snapshot(bool configured = false, string route = "none", string credential = "none", string? model = null)
            => new { providers = new[] { new { id = "provider", name = "Provider", methods = ConfigurationJson.Operations,
                configured, route, credentialType = credential, headerNames = new string[0] } },
                defaults = new { provider = model == null ? null : "provider", model, reasoning = (string?)null }, apis = new[] { "openai-completions" } };

        private static HttpResponseMessage Reply(JsonElement begin, object data, string cleanup = "exited", int? exit = 0)
        {
            var op = begin.GetProperty("operation").GetString();
            var result = new Dictionary<string, object?> { ["v"] = 1, ["type"] = "result", ["operationId"] = begin.GetProperty("operationId").GetString(),
                ["outcome"] = "completed", ["code"] = "ok", ["persistence"] = op == "status" ? "not_applicable" : "saved" };
            if (op == "status") result["data"] = data;
            var body = JsonSerializer.Serialize(new { type = "configuration_settled", result, exit_code = exit, cleanup, failure_code = (string?)null }) + "\n";
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(body, Encoding.UTF8, "application/x-ndjson") };
        }

        private sealed class GuidanceHandler : HttpMessageHandler
        {
            internal Func<JsonElement, Task<HttpResponseMessage>> Reply = b => Task.FromResult(RookChatGuidanceTests.Reply(b, Snapshot()));
            internal readonly ConcurrentQueue<string> Operations = new();
            internal int Cancellations;
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
            {
                Assert.Equal("http://127.0.0.1:1", request.RequestUri!.GetLeftPart(UriPartial.Authority));
                Assert.Equal("synthetic", request.Headers.GetValues("X-Rook-Session").Single());
                if (request.RequestUri.AbsolutePath.EndsWith("/cancel", StringComparison.Ordinal))
                {
                    Assert.False(ct.IsCancellationRequested);
                    Interlocked.Increment(ref Cancellations);
                    return new HttpResponseMessage(HttpStatusCode.NoContent);
                }
                Assert.Equal("/agent/chat/configuration", request.RequestUri.AbsolutePath);
                using var json = JsonDocument.Parse(await request.Content!.ReadAsStringAsync());
                Operations.Enqueue(json.RootElement.GetProperty("operation").GetString()!);
                return await Reply(json.RootElement.Clone());
            }
        }

        private sealed class GuidanceFixture : IDisposable
        {
            private readonly AgentChatProgressTests.PanelThread _ui;
            private readonly ConcurrentQueue<Action> _queue = new();
            private readonly SynchronizationContext _context;
            private bool _closed;
            internal readonly GuidanceHandler Handler = new();
            internal readonly ChatServiceHealth Health = new() { ServiceAvailable = true, RuntimeAvailable = true, ConfigurationAvailable = true, BaseUri = new Uri("http://127.0.0.1:1") };
            internal readonly AgentChatClient Client;
            internal RookChatPanel Panel = null!;
            internal AgentChatTab? Tab;
            internal Label Label => (Label)typeof(RookChatPanel).GetField("_setupGuidance", Private)!.GetValue(Panel);
            internal string Text => Label.Text;
            internal Button Settings => (Button)typeof(RookChatPanel).GetField("_settingsButton", Private)!.GetValue(Panel);
            internal GuidanceFixture(AgentChatProgressTests.PanelThread ui)
            {
                _ui = ui; _context = new QueueContext(_queue);
                Client = AgentChatClient.ForTests(Handler, Health.BaseUri!, Health); Client.SetSessionNonce("synthetic");
                Ui(() => { Rook.Tests.UI.EtoTestPlatform.Ensure(); Panel = new RookChatPanel(1); });
            }
            internal void Ui(Action action) => _ui.Run(() => { SynchronizationContext.SetSynchronizationContext(_context); action(); });
            internal Task Start(Func<Task> action) { Task t = null!; Ui(() => t = action()); return t; }
            internal void UseDialogQueue(RookChatConfigurationDialog dialog)
                => typeof(RookChatConfigurationDialog).GetField("_post", Private)!.SetValue(dialog, (Action<Action>)_queue.Enqueue);
            internal void AttachTab()
            {
                Tab = CreateTab();
                SynchronizationContext.SetSynchronizationContext(_context);
                Tab.GuidanceContextChanged += () => Invoke(Panel, "RenderSetupGuidance");
                var tabs = new TabControl(); tabs.Pages.Add(new TabPage { Content = Tab }); tabs.SelectedIndex = 0;
                ((Panel)typeof(RookChatPanel).GetField("_tabHost", Private)!.GetValue(Panel)).Content = tabs;
            }
            internal async Task Until(Func<bool> ready)
            {
                var clock = Stopwatch.StartNew();
                while (!ready() && clock.ElapsedMilliseconds < 10000) { Drain(); await Task.Delay(1); }
                Assert.True(ready());
            }
            internal async Task Pump(Task task)
            {
                await Until(() => task.IsCompleted); Drain(); await task;
            }
            private void Drain() => Ui(() => { while (_queue.TryDequeue(out var action)) action(); });
            internal void ClosePanel() { if (!_closed) { _closed = true; Panel.Dispose(); } }
            public void Dispose() { Ui(() => { ClosePanel(); Tab?.Dispose(); }); Client.Dispose(); Handler.Dispose(); Drain(); }
            private sealed class QueueContext : SynchronizationContext
            {
                private readonly ConcurrentQueue<Action> _queue;
                internal QueueContext(ConcurrentQueue<Action> queue) => _queue = queue;
                public override void Post(SendOrPostCallback d, object? state) => _queue.Enqueue(() => d(state));
            }
        }

        [Theory]
        [InlineData(true, "Conversation connected")]
        [InlineData(false, "Conversation connected; Rhino document unavailable")]
        public void Connection_does_not_claim_model_readiness(bool target, string expected)
        {
            _ui.Run(() =>
            {
                using var tab = CreateTab();
                Invoke(tab, "ApplyConversationStatus", new ConversationView
                {
                    ConversationId = "offline-fixture", TargetAvailable = target,
                });
                Assert.Equal(expected, Status(tab));
            });
        }

        [Theory]
        [InlineData("failed", "delivered", "Request failed; the cause was not reported.")]
        [InlineData("cancelled", "delivered", "Cancelled")]
        [InlineData("refused", "delivered", "Prime refused the request")]
        [InlineData("incomplete", "delivered", "Prime turn incomplete")]
        [InlineData("error", "stream_failed", "Request failed; live presentation failed.")]
        public void Terminal_keeps_specific_explanations_and_uses_honest_fallback(string outcome, string presentation, string expected)
        {
            _ui.Run(() =>
            {
                using var tab = CreateTab();
                Invoke(tab, "ApplyTerminal", new ChatEvent { Type = "terminal", Outcome = outcome, PresentationOutcome = presentation });
                Assert.Equal(expected, Status(tab));
            });
        }

        [Theory]
        [InlineData("conversation_busy", "Another request is active. Wait for it to finish.")]
        [InlineData("conversation_not_open", "Conversation is not open. Open or reopen a conversation from the conversation list.")]
        [InlineData("target_unavailable", "Rhino document unavailable. Check the bound document.")]
        [InlineData("runtime_unavailable", "The conversation runtime is unavailable.")]
        [InlineData("synthetic-secret", "Request failed; the cause was not reported.")]
        public void Safe_reported_failure_is_not_replaced_with_unknown_cause(string code, string expected)
        {
            _ui.Run(() =>
            {
                using var tab = CreateTab();
                Invoke(tab, "ApplyTerminal", new ChatEvent { Outcome = "error", ErrorCode = code });
                Assert.Equal(expected, Status(tab));
            });
        }

        private static AgentChatTab CreateTab()
        {
            var tab = (AgentChatTab)typeof(AgentChatProgressTests).GetMethod("CreateTab", BindingFlags.Static | BindingFlags.NonPublic)!
                .Invoke(null, new object[] { AgentChatClient.ForTests(new GuidanceHandler(), new Uri("http://127.0.0.1:1"),
                    new ChatServiceHealth { ServiceAvailable = true, RuntimeAvailable = true, ConfigurationAvailable = true, BaseUri = new Uri("http://127.0.0.1:1") }), new List<string>() });
            typeof(ChatTab).GetField("_statusStack", Private)!.SetValue(tab, new StackLayout());
            return tab;
        }
        private static string Status(AgentChatTab tab)
            => ((Label)typeof(ChatTab).GetField("_statusLabel", Private)!.GetValue(tab)).Text;
        private static object Invoke(object target, string method, params object[] args)
            => target.GetType().GetMethod(method, Private)!.Invoke(target, args);
    }
}
