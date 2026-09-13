using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Reflection;
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
    public sealed class RookChatConfigurationTests : IClassFixture<AgentChatProgressTests.PanelThread>
    {
        private readonly AgentChatProgressTests.PanelThread _ui;
        public RookChatConfigurationTests(AgentChatProgressTests.PanelThread ui) => _ui = ui;
        private const string Id = "0123456789abcdef0123456789abcdef";
        private static readonly Uri BaseUri = new("http://127.0.0.1:1");

        [Fact]
        public void Task7_actual_stream_updates_label_without_resetting_text()
        {
            _ui.Run(() =>
            {
                var scripts = new List<string>();
                var helper = typeof(AgentChatProgressTests);
                var flags = BindingFlags.Static | BindingFlags.NonPublic;
                using var handler = new SettingsHandler(
                    "{\"type\":\"text_delta\",\"text\":\"before\"}\n" +
                    "{\"type\":\"session_status\",\"effectiveSettings\":{\"provider\":\"actual\",\"model\":\"c\",\"reasoning\":\"off\"}}\n" +
                    "{\"type\":\"text_delta\",\"text\":\"after\"}\n" +
                    "{\"type\":\"terminal\",\"outcome\":\"settled\",\"stopReason\":\"end_turn\",\"presentationOutcome\":\"delivered\",\"cachePublished\":true}\n");
                using var client = AgentChatClient.ForTests(handler, BaseUri);
                using var tab = (AgentChatTab)helper.GetMethod("CreateTab", flags)!.Invoke(null, new object[] { client, scripts });
                typeof(ChatTab).GetField("_statusStack", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(tab, new StackLayout());
                typeof(AgentChatTab).GetMethod("ShowRequestedSettings", BindingFlags.Instance | BindingFlags.NonPublic)!
                    .Invoke(tab, new object[] { "requested/b", "high" });
                helper.GetMethod("Prompt", flags)!.Invoke(null, new object[] { tab });
                Assert.Equal(1, handler.Count);
                Assert.Contains("window.chatAPI.updateStreamingMessage('beforeafter')", scripts);
                var label = typeof(AgentChatTab).GetField("_effectiveSettingsLabel", BindingFlags.Instance | BindingFlags.NonPublic)?.GetValue(tab) as Label;
                Assert.NotNull(label);
                Assert.Contains("Requested model: requested/b", label!.Text);
                Assert.Contains("Last reported effective settings: actual/c", label.Text);
                Assert.Contains("reasoning: off", label.Text);
                typeof(AgentChatTab).GetField("_uiAttached", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(tab, false);
                using var doc = JsonDocument.Parse("{\"type\":\"session_status\",\"effectiveSettings\":{\"provider\":\"stale\",\"model\":\"x\",\"reasoning\":null}}");
                var evt = doc.RootElement.Deserialize<ChatEvent>();
                typeof(AgentChatTab).GetMethod("HandleChatEvent", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(tab, new object[] { evt! });
                Assert.DoesNotContain("stale", label.Text);
            });
        }

        private sealed class SettingsHandler : HttpMessageHandler
        {
            private readonly string _body;
            internal int Count;
            internal SettingsHandler(string body) => _body = body;
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
            {
                Count++;
                return Task.FromResult(Response(_body));
            }
        }

        [Theory]
        [InlineData("null")]
        [InlineData("{}")]
        [InlineData("{\"provider\":5}")]
        [InlineData("{\"model\":\"\\ud800\"}")]
        [InlineData("{\"\\ud800\":\"synthetic\"}")]
        [InlineData("{\"model\":\"a\",\"model\":\"b\"}")]
        [InlineData("{\"secret\":\"synthetic-secret\"}")]
        public async Task Task7_malformed_optional_settings_remain_unknown(string value)
        {
            using var handler = new SettingsHandler("{\"conversationId\":\"c\",\"effectiveSettings\":" + value + "}");
            using var client = AgentChatClient.ForTests(handler, BaseUri);
            var view = await client.CreateAsync(new CreateConversationRequest());
            Assert.Null(view.EffectiveSettings?.Provider);
            Assert.Null(view.EffectiveSettings?.Model);
            Assert.Null(view.EffectiveSettings?.Reasoning);
            Assert.Equal(1, handler.Count);
        }

        [Fact]
        public async Task Task7_original_producer_values_survive_managed_http_parser()
        {
            var path = Environment.GetEnvironmentVariable("ROOK_TASK7_HTTP_FIXTURE");
            Assert.False(string.IsNullOrEmpty(path), "Stage B requires the real producer fixture from its Python gate.");
            Assert.InRange(new FileInfo(path!).Length, 1, 16 * 1024);
            using var doc = JsonDocument.Parse(File.ReadAllBytes(path!));
            var root = doc.RootElement;
            using var handler = new SettingsHandler(root.GetProperty("view").GetRawText());
            using var client = AgentChatClient.ForTests(handler, BaseUri);
            var view = await client.CreateAsync(new CreateConversationRequest { Model = "requested/b", Reasoning = "high" });
            Assert.Equal("actual-c", view.EffectiveSettings?.Model);
            Assert.Equal("off", view.EffectiveSettings?.Reasoning);
            Assert.NotEqual(root.GetProperty("producer").GetProperty("defaults")[0].GetProperty("model").GetString(), view.EffectiveSettings?.Model);
            var terminal = "{\"type\":\"terminal\",\"outcome\":\"settled\",\"stopReason\":\"end_turn\",\"presentationOutcome\":\"delivered\",\"cachePublished\":true}\n";
            using var streamHandler = new SettingsHandler(root.GetProperty("status").GetRawText() + "\n" + terminal);
            using var streamClient = AgentChatClient.ForTests(streamHandler, BaseUri);
            var events = new List<ChatEvent>();
            await streamClient.PromptAsync(BaseUri, "c", "fixture", Array.Empty<ChatImageInput>(), events.Add, CancellationToken.None);
            Assert.Equal("actual-d", events[0].EffectiveSettings?.Model);
            Assert.Equal("high", events[0].EffectiveSettings?.Reasoning);
            _ui.Run(() =>
            {
                var flags = BindingFlags.NonPublic | BindingFlags.Instance;
                using var tab = new AgentChatTab(new CreateConversationRequest(), client, null, initializePresentation:false);
                typeof(ChatTab).GetField("_statusStack", flags)!.SetValue(tab, new StackLayout());
                typeof(AgentChatTab).GetMethod("ShowRequestedSettings", flags)!.Invoke(tab, new object[] { "requested/b", "high" });
                typeof(AgentChatTab).GetMethod("HandleChatEvent", flags)!.Invoke(tab, new object[] { events[0] });
                var label = (Label)typeof(AgentChatTab).GetField("_effectiveSettingsLabel", flags)!.GetValue(tab);
                Assert.Contains("Last reported effective settings: task7-synthetic/actual-d", label.Text);
                Assert.Contains("Requested model: requested/b", label.Text);
            });
        }
        [Fact]
        public void Configuration_client_exposes_finite_operation_entrypoint()
            => Assert.NotNull(typeof(AgentChatClient).GetMethod("RunConfigurationAsync"));

        [Fact]
        public void Health_exposes_configuration_availability_separately()
            => Assert.NotNull(typeof(ChatServiceHealth).GetProperty("ConfigurationAvailable"));

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task Wrapper_first_result_and_identical_duplicate_both_retain_saved(bool eventFirst)
        {
            using var handler = new Handler(b => Response((eventFirst ? Line(Result(b)) : "") + Line(Settled(Result(b)))));
            using var client = Client(handler);
            var observed = new List<ConfigurationEvent>();
            var result = await client.RunConfigurationAsync(Begin(), e => { observed.Add(e); return Task.CompletedTask; }, CancellationToken.None);
            Assert.True(result.Successful);
            Assert.Equal("saved", result.Result!.Persistence);
            Assert.Equal(eventFirst ? 1 : 0, observed.Count);
            Assert.Equal("exited", result.Cleanup);
            Assert.Single(handler.Requests);
        }

        [Theory]
        [InlineData("contradiction")]
        [InlineData("missing-wrapper")]
        [InlineData("null-wrapper-result")]
        [InlineData("extra-wrapper-field")]
        [InlineData("late-event")]
        [InlineData("truncated")]
        public async Task Saved_result_survives_invalid_or_missing_settlement(string fault)
        {
            using var handler = new Handler(b =>
            {
                var first = Line(Result(b));
                var tail = fault switch
                {
                    "contradiction" => Line(Settled(Result(b, "unchanged"))),
                    "null-wrapper-result" => Line(Settled(null)),
                    "extra-wrapper-field" => Line(Settled(Result(b))).TrimEnd().TrimEnd('}') + ",\"secret\":\"synthetic-secret\"}\n",
                    "late-event" => Line(Settled(Result(b))) + Line(Progress(b)),
                    "truncated" => "{\"type\":",
                    _ => "",
                };
                return Response(first + tail);
            });
            using var client = Client(handler);
            var result = await client.RunConfigurationAsync(Begin(), _ => Task.CompletedTask, CancellationToken.None);
            Assert.False(result.Successful);
            Assert.Equal("saved", result.Result!.Persistence);
            Assert.Equal("configuration_stream_failed", result.DeliveryFailure);
            Assert.Single(handler.Requests); // No cancellation after authentic terminal result.
        }

        [Theory]
        [InlineData("output_failed", "exited", 0)]
        [InlineData("cleanup_unconfirmed", "unconfirmed", null)]
        [InlineData("process_failed", "exited", 1)]
        public async Task Saved_is_not_overall_success_when_delivery_or_cleanup_failed(string failure, string cleanup, int? exit)
        {
            using var handler = new Handler(b => Response(Line(Settled(Result(b), failure, cleanup, exit))));
            using var client = Client(handler);
            var result = await client.RunConfigurationAsync(Begin(), _ => Task.CompletedTask, CancellationToken.None);
            Assert.Equal("saved", result.Result!.Persistence);
            Assert.Equal(failure, result.FailureCode);
            Assert.Equal(cleanup, result.Cleanup);
            Assert.False(result.Successful);
        }

        [Theory]
        [InlineData("wrong-id")]
        [InlineData("version")]
        [InlineData("duplicate-key")]
        [InlineData("surrogate")]
        [InlineData("nul")]
        [InlineData("invalid-utf8")]
        [InlineData("unknown-event")]
        [InlineData("oversized-record")]
        [InlineData("too-many-events")]
        [InlineData("total-bytes")]
        public async Task Malformed_stream_refuses_safely_before_any_result(string fault)
        {
            using var handler = new Handler(b =>
            {
                string raw = fault switch
                {
                    "wrong-id" => Line(Progress(b)).Replace(Id, new string('a', 32)),
                    "version" => Line(Progress(b)).Replace("\"v\":1", "\"v\":2"),
                    "duplicate-key" => Line(Progress(b)).Replace("\"v\":1", "\"v\":1,\"v\":1"),
                    "surrogate" => "{\"v\":1,\"type\":\"authorize\",\"operationId\":\"" + Id + "\",\"url\":\"https://example.invalid/\",\"instructionCode\":\"open_browser\",\"instructions\":\"\\ud800\"}\n",
                    "nul" => Line(Progress(b)).Replace("loading", "load\\u0000ing"),
                    "unknown-event" => Line(Progress(b)).Replace("progress", "synthetic-secret"),
                    "oversized-record" => new string('x', ConfigurationJson.EventLimit + 1024),
                    "too-many-events" => string.Concat(Enumerable.Repeat(Line(Progress(b)), 257)),
                    "total-bytes" => string.Concat(Enumerable.Repeat("{\"v\":1,\"type\":\"authorize\",\"operationId\":\"" + Id + "\",\"url\":\"https://example.invalid/\",\"instructionCode\":\"open_browser\",\"instructions\":\"" + string.Concat(Enumerable.Repeat("\\u0061", 8000)) + "\"}\n", 100)),
                    _ => "",
                };
                return fault == "invalid-utf8" ? new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(new byte[] { 255, 10 }) } : Response(raw);
            });
            using var client = Client(handler);
            var result = await client.RunConfigurationAsync(new ConfigurationBegin("oauth.connect", new { provider = "provider" }, Id), _ => Task.CompletedTask, CancellationToken.None);
            Assert.False(result.Successful);
            Assert.Null(result.Result);
            Assert.Equal("configuration_stream_failed", result.DeliveryFailure);
            Assert.Single(handler.Requests.Where(r => r.GetProperty("type").GetString() == "cancel"));
        }

        [Fact]
        public async Task Presentation_failure_cancels_but_drains_valid_saved_result()
        {
            using var handler = new Handler(b => Response(Line(Progress(b)) + Line(Result(b)) + Line(Settled(Result(b)))));
            using var client = Client(handler);
            int calls = 0;
            var result = await client.RunConfigurationAsync(Begin(), _ => { calls++; throw new Exception("synthetic-secret"); }, CancellationToken.None);
            Assert.Equal(1, calls);
            Assert.Equal("saved", result.Result!.Persistence);
            Assert.Equal("exited", result.Cleanup);
            Assert.Equal("configuration_delivery_failed", result.DeliveryFailure);
            Assert.False(result.Successful);
            Assert.Single(handler.Requests.Where(r => r.GetProperty("type").GetString() == "cancel"));
        }

        [Fact]
        public async Task Correlated_reply_rejects_wrong_duplicate_and_late_inputs()
        {
            using var stream = new ControlledStream();
            JsonElement begin = default;
            using var handler = new Handler(b => { begin = b; stream.Push(Line(Input(b, 7))); return StreamResponse(stream); });
            using var client = Client(handler);
            var seen = new TaskCompletionSource<bool>();
            var operation = client.RunConfigurationAsync(new ConfigurationBegin("oauth.connect", new { provider = "provider" }, Id), _ => { seen.TrySetResult(true); return Task.CompletedTask; }, CancellationToken.None);
            try
            {
                await Bounded(seen.Task);
                await Assert.ThrowsAsync<InvalidOperationException>(() => client.ReplyConfigurationAsync(new string('a', 32), 7, "synthetic-secret"));
                await Assert.ThrowsAsync<InvalidOperationException>(() => client.ReplyConfigurationAsync(Id, 8, "synthetic-secret"));
                await client.ReplyConfigurationAsync(Id, 7, "synthetic-secret");
                await Assert.ThrowsAsync<InvalidOperationException>(() => client.ReplyConfigurationAsync(Id, 7, "synthetic-secret"));
                stream.Push(Line(Result(begin)) + Line(Settled(Result(begin)))); stream.Finish();
                await Bounded(operation);
                await Assert.ThrowsAsync<InvalidOperationException>(() => client.ReplyConfigurationAsync(Id, 7, "synthetic-secret"));
                Assert.Single(handler.Requests.Where(r => r.GetProperty("type").GetString() == "reply"));
            }
            finally { stream.Finish(); await Bounded(operation); }
        }

        [Fact]
        public async Task Cancelled_UI_token_uses_fresh_control_and_retains_a_saved_result()
        {
            using var stream = new ControlledStream();
            using var cancellation = new CancellationTokenSource();
            JsonElement begin = default;
            using var handler = new Handler(b => { begin = b; stream.Push(Line(Progress(b))); return StreamResponse(stream); });
            handler.Control = c => { Assert.False(handler.LastControlTokenCancelled); stream.Push(Line(Result(begin)) + Line(Settled(Result(begin)))); stream.Finish(); };
            using var client = Client(handler);
            var seen = new TaskCompletionSource<bool>();
            var operation = client.RunConfigurationAsync(Begin(), _ => { seen.TrySetResult(true); return Task.CompletedTask; }, cancellation.Token);
            try
            {
                await Bounded(seen.Task);
                var overlap = await client.RunConfigurationAsync(Begin(), _ => Task.CompletedTask, CancellationToken.None);
                Assert.False(overlap.Successful);
                cancellation.Cancel();
                await Bounded(operation);
                Assert.Equal("saved", operation.Result.Result!.Persistence);
                Assert.Equal("exited", operation.Result.Cleanup);
                Assert.Single(handler.Requests.Where(r => r.GetProperty("type").GetString() == "begin"));
                Assert.Single(handler.Requests.Where(r => r.GetProperty("type").GetString() == "cancel"));
            }
            finally { stream.Finish(); await Bounded(operation); }
        }

        [Theory]
        [InlineData(401)]
        [InlineData(409)]
        [InlineData(503)]
        public async Task HTTP_failures_do_not_publish_response_bodies(int status)
        {
            using var handler = new Handler(_ => new HttpResponseMessage((HttpStatusCode)status) { Content = new StringContent("synthetic-secret") });
            using var client = Client(handler);
            var result = await client.RunConfigurationAsync(Begin(), _ => Task.CompletedTask, CancellationToken.None);
            Assert.False(result.Successful); Assert.Null(result.Result);
            Assert.DoesNotContain("synthetic", result.FailureCode!);
        }

        [Theory]
        [InlineData("oversized-key")]
        [InlineData("nul-key")]
        [InlineData("unknown-operation")]
        [InlineData("extra-input")]
        [InlineData("wrong-operation-id")]
        public async Task Invalid_private_inputs_refuse_before_HTTP(string fault)
        {
            using var handler = new Handler(); using var client = Client(handler);
            var begin = fault switch
            {
                "oversized-key" => new ConfigurationBegin("apiKey.set", new { provider = "provider", key = new string('x', 16385) }),
                "nul-key" => new ConfigurationBegin("apiKey.set", new { provider = "provider", key = "synthetic\0secret" }),
                "unknown-operation" => new ConfigurationBegin("execute", new { command = "forbidden" }),
                "extra-input" => new ConfigurationBegin("status", new { key = "synthetic-secret" }),
                _ => new ConfigurationBegin("status", new { }, "wrong"),
            };
            var result = await client.RunConfigurationAsync(begin, _ => Task.CompletedTask, CancellationToken.None);
            Assert.False(result.Successful); Assert.Empty(handler.Requests);
            Assert.Equal(JsonValueKind.Undefined, begin.Input.ValueKind);
        }

        [Fact]
        public async Task Precancelled_UI_admission_does_not_send_begin_or_cancel()
        {
            using var handler = new Handler(); using var client = Client(handler); using var ct = new CancellationTokenSource();
            ct.Cancel();
            var result = await client.RunConfigurationAsync(Begin(), _ => Task.CompletedTask, ct.Token);
            Assert.False(result.Successful); Assert.Empty(handler.Requests);
        }

        [Theory]
        [InlineData(true, true)]
        [InlineData(true, false)]
        [InlineData(false, true)]
        [InlineData(false, false)]
        public async Task Preparation_cancellation_prevents_dispatch(bool cancel, bool healthContainsUri)
        {
            using var handler = new Handler(); using var client = Client(handler); using var ct = new CancellationTokenSource();
            var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var release = new TaskCompletionSource<ChatServiceHealth>(TaskCreationOptions.RunContinuationsAsynchronously);
            var health = new ChatServiceHealth { ConfigurationAvailable = true, ServiceAvailable = true, BaseUri = healthContainsUri ? BaseUri : null };
            // Replace only the health query; the real command awaits it and resolves/dispatches normally.
            client.ConfigurationHealthQueryForTests = _ => { entered.TrySetResult(true); return release.Task; };
            var operation = client.RunConfigurationAsync(Begin(), _ => Task.CompletedTask, ct.Token);
            try
            {
                await Bounded(entered.Task);
                Assert.Empty(handler.Requests);
                if (cancel) ct.Cancel();
                release.SetResult(health);
                await Bounded(operation);
                var result = await operation;
                if (cancel)
                {
                    Assert.Empty(handler.Requests); // Neither a begin write nor a cancellation for an unstarted operation.
                    Assert.False(result.Successful); Assert.Null(result.Result); Assert.Equal("cancelled", result.DeliveryFailure);
                }
                else { Assert.Single(handler.Requests); Assert.True(result.Successful); }
            }
            finally { release.TrySetResult(health); await Bounded(operation); }
        }

        public static IEnumerable<object[]> OutboundUnicodeCases()
        {
            foreach (var field in new[] { "apiKey", "provider", "headerName", "headerValue", "endpointUrl", "api", "modelId", "modelName", "defaultModel", "defaultReasoning" })
                foreach (var form in new[] { "high", "low", "valid", "replacement" })
                    foreach (var boundary in new[] { "begin", "encode" }) yield return new object[] { field, form, boundary };
        }

        [Theory]
        [MemberData(nameof(OutboundUnicodeCases))]
        public async Task Original_outbound_Unicode_is_rejected_or_preserved_before_serialization(string field, string form, string boundary)
        {
            var text = form == "high" ? "synthetic-\ud800-end" : form == "low" ? "synthetic-\udc00-end" :
                form == "valid" ? "synthetic-e\u0301-\u00e9-\U0001f511" : "synthetic-\ufffd-end";
            var invalid = form == "high" || form == "low";
            var input = new Dictionary<string, object?> { ["provider"] = "provider" };
            var operationName = "endpoint.save";
            if (field == "apiKey") { operationName = "apiKey.set"; input["key"] = text; }
            else if (field == "defaultModel" || field == "defaultReasoning")
            {
                operationName = "defaults.save"; input["model"] = field == "defaultModel" ? text : "model"; input["reasoning"] = field == "defaultReasoning" ? text : "low";
            }
            else
            {
                if (field == "provider") input["provider"] = text;
                input["baseUrl"] = field == "endpointUrl" ? text : "http://localhost:11434/v1";
                input["api"] = field == "api" ? text : "openai-completions";
                input["authHeader"] = true;
                input["headers"] = new { action = "replace", values = new Dictionary<string, string> { [field == "headerName" ? text : "X-Local"] = field == "headerValue" ? text : "literal" } };
                input["models"] = new[] { new { id = field == "modelId" ? text : "model", name = field == "modelName" ? text : "Model", reasoning = true, input = new[] { "text" }, contextWindow = 1000, maxTokens = 100 } };
            }
            using var handler = new Handler(); using var client = Client(handler);
            InvalidDataException? refusal = null;
            ConfigurationSettlement? result = null;
            try
            {
                // Endpoint editing also uses Encode before constructing a begin record.
                object original = boundary == "encode" ? ConfigurationJson.Parse(ConfigurationJson.Encode(input, ConfigurationJson.InputLimit), ConfigurationJson.InputLimit) : (object)input;
                var begin = new ConfigurationBegin(operationName, original);
                result = await client.RunConfigurationAsync(begin, _ => Task.CompletedTask, CancellationToken.None);
            }
            catch (InvalidDataException ex) { refusal = ex; }
            if (invalid)
            {
                Assert.Empty(handler.Requests);
                Assert.NotNull(refusal);
                Assert.DoesNotContain("synthetic", refusal!.Message);
                Assert.Null(refusal.InnerException);
            }
            else
            {
                Assert.Null(refusal); Assert.True(result!.Successful);
                var sent = Assert.Single(handler.Requests).GetProperty("input");
                var observed = field switch
                {
                    "apiKey" => sent.GetProperty("key").GetString(),
                    "provider" => sent.GetProperty("provider").GetString(),
                    "defaultModel" => sent.GetProperty("model").GetString(),
                    "defaultReasoning" => sent.GetProperty("reasoning").GetString(),
                    "endpointUrl" => sent.GetProperty("baseUrl").GetString(),
                    "api" => sent.GetProperty("api").GetString(),
                    "headerName" => sent.GetProperty("headers").GetProperty("values").EnumerateObject().Single().Name,
                    "headerValue" => sent.GetProperty("headers").GetProperty("values").GetProperty("X-Local").GetString(),
                    "modelId" => sent.GetProperty("models")[0].GetProperty("id").GetString(),
                    _ => sent.GetProperty("models")[0].GetProperty("name").GetString(),
                };
                Assert.Equal(text, observed); // Includes decomposed text and a legitimate U+FFFD; no normalization.
            }
        }

        [Fact]
        public async Task Cancellation_after_dispatch_waits_for_admission_and_uses_fresh_control()
        {
            using var stream = new ControlledStream(); using var ct = new CancellationTokenSource();
            var sent = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var headers = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            JsonElement begin = default;
            using var handler = new Handler(b => { begin = b; sent.TrySetResult(true); return StreamResponse(stream); }) { BeforeBeginResponse = headers.Task };
            handler.Control = c =>
            {
                Assert.Equal("cancel", c.GetProperty("type").GetString());
                Assert.False(handler.LastControlTokenCancelled);
                stream.Push(Line(Result(begin)) + Line(Settled(Result(begin)))); stream.Finish();
            };
            using var client = Client(handler);
            var operation = client.RunConfigurationAsync(Begin(), _ => Task.CompletedTask, ct.Token);
            try
            {
                await Bounded(sent.Task); ct.Cancel();
                Assert.Single(handler.Requests); // The service has not confirmed admission yet.
                headers.SetResult(true);
                await Bounded(operation);
                var result = await operation;
                Assert.Equal("saved", result.Result!.Persistence); Assert.Equal("exited", result.Cleanup);
                Assert.Single(handler.Requests, r => r.GetProperty("type").GetString() == "begin");
                Assert.Single(handler.Requests, r => r.GetProperty("type").GetString() == "cancel");
            }
            finally { headers.TrySetResult(true); stream.Finish(); await Bounded(operation); }
        }

        [Theory]
        [InlineData("unknown", "failed", "storage_failed")]
        [InlineData("unchanged", "cancelled", "cancelled")]
        public async Task Dialog_keeps_unknown_and_cancelled_outcomes_distinct(string persistence, string outcome, string code)
        {
            using var fixture = new DialogFixture(this);
            await fixture.Run(d => d.InitializeAsync());
            fixture.Handler.Begin = b => Response(Line(Settled(new { v = 1, type = "result", operationId = b.GetProperty("operationId").GetString(), outcome, persistence, code })));
            fixture.Ui(d => d.ApiKey.Text = "synthetic-secret");
            await fixture.Run(d => d.RunActionAsync("apiKey.set"));
            fixture.Ui(d => { Assert.Equal(persistence, d.KnownResult!.Persistence); Assert.False(d.LastSettlement!.Successful); Assert.Contains(persistence == "unknown" ? "Persistence unknown" : "unchanged", d.Persistence.Text); Assert.Equal("", d.ApiKey.Text); });
        }

        [Fact]
        public async Task Model_catalog_and_reasoning_are_not_an_account_access_claim()
        {
            using var fixture = new DialogFixture(this);
            await fixture.Run(d => d.InitializeAsync());
            await fixture.Run(d => d.RunActionAsync("models"));
            fixture.Ui(d => { Assert.Equal(new[] { "model" }, d.Model.Items.Select(x => x.Key)); Assert.Equal(new[] { "low", "high" }, d.Reasoning.Items.Select(x => x.Key)); Assert.Contains("access unverified", d.AccountRoute.Text); Assert.Contains("Saved defaults", d.SavedDefaults.Text); });
            Assert.All(fixture.Handler.Requests, r => Assert.Contains(r.GetProperty("operation").GetString(), new[] { "status", "models" }));
        }

        [Fact]
        public async Task Unknown_provider_is_not_presented_as_supporting_OAuth()
        {
            using var fixture = new DialogFixture(this);
            await fixture.Run(d => d.InitializeAsync());
            fixture.Ui(d => d.ProviderId.Text = "new-local-provider");
            await fixture.Run(d => d.RunActionAsync("oauth.connect"));
            Assert.Single(fixture.Handler.Requests);
            fixture.Ui(d => Assert.Contains("unavailable", d.Status.Text));
            await fixture.Run(d => d.RunActionAsync("endpoint.read"));
            Assert.Equal("endpoint.read", fixture.Handler.Requests.Last().GetProperty("operation").GetString());
        }

        [Fact]
        public async Task Saved_result_is_visible_before_cleanup_and_late_cancel_sends_no_control()
        {
            using var stream = new ControlledStream(); JsonElement begin = default;
            using var fixture = new DialogFixture(this);
            await fixture.Run(d => d.InitializeAsync());
            fixture.Handler.Begin = b => { begin = b; stream.Push(Line(Result(b))); return StreamResponse(stream); };
            fixture.Ui(d => d.ApiKey.Text = "synthetic-secret");
            var task = fixture.Start(d => d.RunActionAsync("apiKey.set"));
            try
            {
                await fixture.Until(d => d.Persistence.Text == "Configuration saved.");
                fixture.Ui(d => { Assert.True(d.Busy); Assert.Contains("Awaiting", d.Cleanup.Text); d.CancelCurrent(); Assert.Equal("saved", d.KnownResult!.Persistence); });
                Assert.DoesNotContain(fixture.Handler.Requests, r => r.GetProperty("type").GetString() == "cancel");
                stream.Push(Line(Settled(Result(begin)))); stream.Finish();
                await fixture.Pump(task);
                fixture.Ui(d => { Assert.Equal("Configuration saved.", d.Persistence.Text); Assert.Equal("exited", d.LastSettlement!.Cleanup); });
            }
            finally { stream.Finish(); await fixture.Pump(task); }
        }

        [Fact]
        public async Task Dialog_does_not_replace_known_saved_with_contradictory_wrapper()
        {
            using var fixture = new DialogFixture(this);
            await fixture.Run(d => d.InitializeAsync());
            fixture.Handler.Begin = b => Response(Line(Result(b)) + Line(Settled(Result(b, "unchanged"))));
            fixture.Ui(d => d.ApiKey.Text = "synthetic-secret");
            await fixture.Run(d => d.RunActionAsync("apiKey.set"));
            fixture.Ui(d => { Assert.Equal("saved", d.KnownResult!.Persistence); Assert.Equal("Configuration saved.", d.Persistence.Text); Assert.False(d.LastSettlement!.Successful); Assert.Equal("configuration_stream_failed", d.LastSettlement.DeliveryFailure); });
        }

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task Dialog_first_and_returning_open_read_status_only(bool returning)
        {
            using var fixture = new DialogFixture(this);
            await fixture.Run(d => d.InitializeAsync());
            if (returning) await fixture.Run(d => d.InitializeAsync());
            Assert.Equal(returning ? 2 : 1, fixture.Handler.Requests.Count);
            Assert.All(fixture.Handler.Requests, r => Assert.Equal("status", r.GetProperty("operation").GetString()));
            fixture.Ui(d => { Assert.Contains("provider/model", d.SavedDefaults.Text); Assert.Contains("dedicated", d.AccountRoute.Text); Assert.Equal("", d.ApiKey.Text); });
        }

        [Fact]
        public async Task Unsupported_runtime_does_not_post_configuration_or_disable_conversation_client()
        {
            using var fixture = new DialogFixture(this, available: false);
            await fixture.Run(d => d.InitializeAsync());
            Assert.Empty(fixture.Handler.Requests);
            fixture.Ui(d => Assert.Contains("Existing conversations remain available", d.Status.Text));
        }

        [Theory]
        [InlineData("models")]
        [InlineData("oauth.connect")]
        [InlineData("oauth.disconnect")]
        [InlineData("apiKey.set")]
        [InlineData("apiKey.remove")]
        [InlineData("endpoint.read")]
        [InlineData("endpoint.save")]
        [InlineData("defaults.save")]
        public async Task Actual_dialog_actions_use_exact_finite_HTTP_inputs(string operation)
        {
            using var fixture = new DialogFixture(this);
            await fixture.Run(d => d.InitializeAsync());
            if (operation == "defaults.save") await fixture.Run(d => d.RunActionAsync("models"));
            fixture.Ui(d =>
            {
                d.ApiKey.Text = "literal-synthetic-key";
                if (operation == "endpoint.save")
                {
                    d.EndpointUrl.Text = "http://localhost:11434/v1";
                    d.EndpointModelId.Text = "local-model"; d.EndpointModelName.Text = "Local model"; d.AddEndpointModel();
                    d.DeveloperRole.Checked = false; d.ReasoningEffort.Checked = false;
                }
            });
            await fixture.Run(d => d.RunActionAsync(operation));
            var sent = fixture.Handler.Requests.Last();
            Assert.Equal(operation, sent.GetProperty("operation").GetString());
            var input = sent.GetProperty("input");
            Assert.Equal("provider", input.GetProperty("provider").GetString());
            if (operation == "apiKey.set") Assert.Equal("literal-synthetic-key", input.GetProperty("key").GetString());
            if (operation == "defaults.save") { Assert.Equal("model", input.GetProperty("model").GetString()); Assert.Equal("low", input.GetProperty("reasoning").GetString()); }
            if (operation == "endpoint.save") { Assert.Equal("keep", input.GetProperty("headers").GetProperty("action").GetString()); Assert.False(input.GetProperty("compat").GetProperty("supportsDeveloperRole").GetBoolean()); Assert.Single(input.GetProperty("models").EnumerateArray()); }
            fixture.Ui(d => { Assert.Equal("", d.ApiKey.Text); Assert.NotNull(d.LastSettlement); Assert.True(d.LastSettlement!.Successful); });
        }

        [Fact]
        public async Task Endpoint_read_has_names_only_and_header_replacement_is_explicit()
        {
            using var fixture = new DialogFixture(this);
            await fixture.Run(d => d.InitializeAsync());
            await fixture.Run(d => d.RunActionAsync("endpoint.read"));
            fixture.Ui(d =>
            {
                Assert.False(d.ReplaceHeaders.Checked); Assert.Equal("", d.HeaderValue.Text); Assert.Equal("", d.ApiKey.Text);
                using var keep = JsonDocument.Parse(Encoding.UTF8.GetString(ConfigurationJson.Begin(d.BuildOperation("endpoint.save"))));
                Assert.Equal("keep", keep.RootElement.GetProperty("input").GetProperty("headers").GetProperty("action").GetString());
                d.ReplaceHeaders.Checked = true; d.HeaderName.Text = "X-Local"; d.HeaderValue.Text = "synthetic-header"; d.AddHeader();
                Assert.Equal("", d.HeaderValue.Text);
            });
            await fixture.Run(d => d.RunActionAsync("endpoint.save"));
            var h = fixture.Handler.Requests.Last().GetProperty("input").GetProperty("headers");
            Assert.Equal("replace", h.GetProperty("action").GetString()); Assert.Equal("synthetic-header", h.GetProperty("values").GetProperty("X-Local").GetString());
            fixture.Ui(d => Assert.False(d.ReplaceHeaders.Checked));
        }

        [Fact]
        public async Task Dialog_authorization_is_plain_correlated_and_cleared_after_reply()
        {
            using var stream = new ControlledStream(); JsonElement begin = default;
            using var fixture = new DialogFixture(this);
            await fixture.Run(d => d.InitializeAsync());
            fixture.Handler.Begin = b => { begin = b; stream.Push(Line(new { v = 1, type = "authorize", operationId = b.GetProperty("operationId").GetString(), url = "https://example.invalid/authorize", instructionCode = "open_browser", instructions = "<b>device code</b> \U0001F511" }) + Line(Input(b, 3))); return StreamResponse(stream); };
            fixture.Handler.Control = c => { if (c.GetProperty("type").GetString() == "reply") { stream.Push(Line(Result(begin)) + Line(Settled(Result(begin)))); stream.Finish(); } };
            var task = fixture.Start(d => d.RunActionAsync("oauth.connect"));
            try
            {
                await fixture.Until(d => d.SecretReply.Visible);
                Assert.Empty(fixture.BrowserUrls);
                fixture.Ui(d => { Assert.Equal("<b>device code</b> \U0001F511", d.Instructions.Text); d.OpenAuthorization(); d.SecretReply.Text = "synthetic-reply"; });
                await fixture.Run(d => d.SubmitReplyAsync()); await fixture.Pump(task);
                Assert.Single(fixture.BrowserUrls);
                Assert.Equal(3, fixture.Handler.Requests.Last(r => r.GetProperty("type").GetString() == "reply").GetProperty("requestId").GetInt32());
                fixture.Ui(d => { Assert.Equal("", d.SecretReply.Text); Assert.Equal("", d.Instructions.Text); Assert.Equal("saved", d.KnownResult!.Persistence); });
                await fixture.Run(d => d.SubmitReplyAsync());
                Assert.Single(fixture.Handler.Requests.Where(r => r.GetProperty("type").GetString() == "reply"));
            }
            finally { stream.Finish(); await fixture.Pump(task); }
        }

        [Fact]
        public async Task Dialog_close_before_queued_dispatch_does_not_open_browser_or_lose_result()
        {
            using var fixture = new DialogFixture(this);
            // Begin reaches HTTP and queues the real result callback; dispose before dispatch.
            var operation = fixture.Start(d => d.InitializeAsync());
            fixture.Ui(d => d.Dispose());
            await fixture.Pump(operation);
            Assert.Empty(fixture.BrowserUrls);
            Assert.Equal("not_applicable", fixture.Dialog.KnownResult!.Persistence);
            Assert.False(fixture.Dialog.Busy);
        }

        [Fact]
        public async Task Dialog_cancel_during_save_preserves_saved_plus_cleanup_failure()
        {
            using var stream = new ControlledStream(); JsonElement begin = default;
            using var fixture = new DialogFixture(this);
            await fixture.Run(d => d.InitializeAsync());
            fixture.Handler.Begin = b => { begin = b; stream.Push(Line(Progress(b))); return StreamResponse(stream); };
            fixture.Handler.Control = _ => { Assert.False(fixture.Handler.LastControlTokenCancelled); stream.Push(Line(Settled(Result(begin), "cleanup_unconfirmed", "unconfirmed", null))); stream.Finish(); };
            fixture.Ui(d => d.ApiKey.Text = "synthetic-secret");
            var task = fixture.Start(d => d.RunActionAsync("apiKey.set"));
            try
            {
                await fixture.Until(d => d.Status.Text == "Configuration: loading");
                fixture.Ui(d => { d.CancelCurrent(); Assert.Equal("", d.ApiKey.Text); });
                await fixture.Pump(task);
                fixture.Ui(d => { Assert.Equal("Configuration saved.", d.Persistence.Text); Assert.Contains("unconfirmed", d.Cleanup.Text); Assert.False(d.LastSettlement!.Successful); Assert.Equal("saved", d.KnownResult!.Persistence); });
            }
            finally { stream.Finish(); await fixture.Pump(task); }
        }

        [Fact]
        public void Health_envelope_maps_configuration_availability_without_runtime_assumptions()
        {
            var health = JsonSerializer.Deserialize<ChatServiceHealthEnvelope>("{\"configurationAvailable\":true,\"runtime\":{\"available\":false}}");
            Assert.True(health!.ConfigurationAvailable); Assert.False(health.Runtime!.Available);
            var root = FindRoot();
            Assert.Contains("ConfigurationAvailable = payload.ConfigurationAvailable", File.ReadAllText(Path.Combine(root, "src/Rook/UI/Chat/ChatServiceManager.cs")));
            Assert.Contains("OnConfigurationClicked", File.ReadAllText(Path.Combine(root, "src/Rook/UI/Chat/RookChatPanel.cs")));
            Assert.Contains("Last reported effective settings: ", File.ReadAllText(Path.Combine(root, "src/Rook/UI/Chat/AgentChatTab.cs")));
        }

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task Real_health_query_carries_configuration_availability(bool available)
        {
            using var handler = new HealthHandler(available);
            using var http = new HttpClient(handler);
            // Exercise the production health consumer without constructing/starting a service owner.
            var manager = (ChatServiceManager)FormatterServices.GetUninitializedObject(typeof(ChatServiceManager));
            typeof(ChatServiceManager).GetField("_httpClient", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(manager, http);
            var task = (Task<ChatServiceHealth?>)typeof(ChatServiceManager).GetMethod("QueryHealthAsync", BindingFlags.Instance | BindingFlags.NonPublic)!
                .Invoke(manager, new object[] { BaseUri, CancellationToken.None });
            var health = await task;
            Assert.NotNull(health); Assert.True(health!.ServiceAvailable); Assert.True(health.RuntimeAvailable);
            Assert.Equal(available, health.ConfigurationAvailable); Assert.Equal(1, handler.Count);
        }

        private static string FindRoot()
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory != null && !File.Exists(Path.Combine(directory.FullName, "Rook.sln"))) directory = directory.Parent;
            return directory?.FullName ?? throw new InvalidOperationException("Test checkout not found.");
        }
        private static ConfigurationBegin Begin() => new("apiKey.set", new { provider = "provider", key = "synthetic-secret" }, Id);
        private static AgentChatClient Client(Handler handler, bool available = true)
        {
            var client = AgentChatClient.ForTests(handler, BaseUri, new ChatServiceHealth { BaseUri = BaseUri, ServiceAvailable = true, ConfigurationAvailable = available });
            client.SetSessionNonce("synthetic-nonce"); return client;
        }
        private static string Line(object value) => JsonSerializer.Serialize(value) + "\n";
        private static HttpResponseMessage Response(string value) => new(HttpStatusCode.OK) { Content = new StringContent(value, Encoding.UTF8, "application/x-ndjson") };
        private static HttpResponseMessage StreamResponse(Stream stream) => new(HttpStatusCode.OK) { Content = new StreamContent(stream) };
        private static object Progress(JsonElement b) => new { v = 1, type = "progress", operationId = b.GetProperty("operationId").GetString(), stage = "loading" };
        private static object Input(JsonElement b, int requestId) => new { v = 1, type = "input", operationId = b.GetProperty("operationId").GetString(), requestId, kind = "code", label = "Enter callback", secret = true };
        private static object Settled(object? result, string? failure = null, string cleanup = "exited", int? exit = 0) => new { type = "configuration_settled", result, exit_code = exit, cleanup, failure_code = failure };
        private static readonly object EndpointModel = new { id = "local-model", name = "Local model", reasoning = true, input = new[] { "text", "image" }, contextWindow = 32768, maxTokens = 4096 };
        private static object Result(JsonElement b, string? persistence = null)
        {
            var op = b.GetProperty("operation").GetString();
            var result = new Dictionary<string, object?> { ["v"] = 1, ["type"] = "result", ["operationId"] = b.GetProperty("operationId").GetString(), ["outcome"] = "completed", ["persistence"] = persistence ?? (op == "status" || op == "models" || op == "endpoint.read" ? "not_applicable" : "saved"), ["code"] = "ok" };
            if (op == "status") result["data"] = new { providers = new[] { new { id = "provider", name = "Provider", methods = ConfigurationJson.Operations, credentialType = "oauth", configured = true, route = "dedicated", headerNames = new string[0] } }, defaults = new { provider = "provider", model = "model", reasoning = "low" }, apis = new[] { "openai-completions" } };
            if (op == "models") result["data"] = new { provider = b.GetProperty("input").GetProperty("provider").GetString(), access = "unverified", models = new[] { new { id = "model", name = "Model", input = new[] { "text", "image" }, reasoningLevels = new[] { "low", "high" } } } };
            if (op == "endpoint.read") result["data"] = new { provider = b.GetProperty("input").GetProperty("provider").GetString(), entry = new { baseUrl = "http://localhost:11434/v1", api = "openai-completions", authHeader = true, models = new[] { EndpointModel }, headerNames = new[] { "X-Local" }, compat = new { supportsDeveloperRole = false, supportsReasoningEffort = false } } };
            return result;
        }
        private static async Task Bounded(Task task)
        {
            Assert.Same(task, await Task.WhenAny(task, Task.Delay(10000)));
            await task;
        }
        private sealed class Handler : HttpMessageHandler
        {
            internal Func<JsonElement, HttpResponseMessage> Begin;
            internal Action<JsonElement>? Control;
            internal Task BeforeBeginResponse = Task.CompletedTask;
            internal bool LastControlTokenCancelled;
            private readonly ConcurrentQueue<JsonElement> _requests = new();
            internal List<JsonElement> Requests => _requests.ToList();
            internal Handler(Func<JsonElement, HttpResponseMessage>? begin = null) => Begin = begin ?? (b => Response(Line(Result(b)) + Line(Settled(Result(b)))));
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            {
                Assert.Equal(BaseUri.Host, request.RequestUri!.Host); Assert.Equal(BaseUri.Port, request.RequestUri.Port);
                Assert.Equal(HttpMethod.Post, request.Method);
                Assert.Equal("synthetic-nonce", request.Headers.GetValues("X-Rook-Session").Single());
                using var document = JsonDocument.Parse(await request.Content!.ReadAsStringAsync());
                var body = document.RootElement.Clone(); _requests.Enqueue(body);
                if (request.RequestUri.AbsolutePath == "/agent/chat/configuration")
                {
                    var response = Begin(body);
                    await BeforeBeginResponse;
                    return response;
                }
                Assert.Contains(request.RequestUri.AbsolutePath, new[] { "/agent/chat/configuration/reply", "/agent/chat/configuration/cancel" });
                LastControlTokenCancelled = cancellationToken.IsCancellationRequested;
                Control?.Invoke(body); return new HttpResponseMessage(HttpStatusCode.NoContent);
            }
        }
        private sealed class HealthHandler : HttpMessageHandler
        {
            private readonly bool _available;
            internal int Count;
            internal HealthHandler(bool available) => _available = available;
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            {
                Assert.Equal(new Uri(BaseUri, "/agent/chat/health"), request.RequestUri); Assert.Equal(HttpMethod.Get, request.Method); Count++;
                return Task.FromResult(Response(JsonSerializer.Serialize(new { configurationAvailable = _available,
                    service = new { owner = "rhino-panel", rhinoProcessId = Process.GetCurrentProcess().Id, status = "ok" }, runtime = new { available = true } })));
            }
        }
        private sealed class ControlledStream : Stream
        {
            private readonly ConcurrentQueue<byte[]> _chunks = new();
            private readonly SemaphoreSlim _ready = new(0);
            private byte[]? _current; private int _offset; private bool _finished;
            internal void Push(string text) { _chunks.Enqueue(Encoding.UTF8.GetBytes(text)); _ready.Release(); }
            internal void Finish() { _finished = true; _ready.Release(); }
            public override async Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken cancellationToken)
            {
                while (_current == null)
                {
                    if (_chunks.TryDequeue(out _current)) { _offset = 0; break; }
                    if (_finished) return 0;
                    await _ready.WaitAsync(cancellationToken);
                }
                int size = Math.Min(count, _current!.Length - _offset);
                System.Array.Copy(_current, _offset, buffer, offset, size); _offset += size;
                if (_offset == _current.Length) _current = null;
                return size;
            }
            protected override void Dispose(bool disposing) { Finish(); base.Dispose(disposing); }
            public override bool CanRead => true; public override bool CanSeek => false; public override bool CanWrite => false;
            public override long Length => throw new NotSupportedException(); public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
            public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException(); public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
            public override void SetLength(long value) => throw new NotSupportedException(); public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException(); public override void Flush() { }
        }
        private sealed class DialogFixture : IDisposable
        {
            private readonly RookChatConfigurationTests _owner;
            private readonly ConcurrentQueue<Action> _queue = new();
            internal readonly Handler Handler = new();
            internal readonly AgentChatClient Client;
            internal RookChatConfigurationDialog Dialog = null!;
            internal readonly List<string> BrowserUrls = new();
            internal DialogFixture(RookChatConfigurationTests owner, bool available = true)
            {
                _owner = owner; Client = RookChatConfigurationTests.Client(Handler, available);
                _owner._ui.Run(() => { if (Application.Instance == null) _ = new Application(Eto.Platforms.Wpf); SynchronizationContext.SetSynchronizationContext(null); Dialog = new RookChatConfigurationDialog(Client, _queue.Enqueue, BrowserUrls.Add); });
            }
            internal void Ui(Action<RookChatConfigurationDialog> action) => _owner._ui.Run(() => action(Dialog));
            internal Task Start(Func<RookChatConfigurationDialog, Task> run) { Task task = null!; Ui(d => task = run(d)); return task; }
            internal async Task Run(Func<RookChatConfigurationDialog, Task> run) => await Pump(Start(run));
            internal async Task Pump(Task task)
            {
                var clock = Stopwatch.StartNew();
                while (!task.IsCompleted && clock.ElapsedMilliseconds < 10000) { Drain(); await Task.Delay(1); }
                Drain(); await Bounded(task);
            }
            internal async Task Until(Func<RookChatConfigurationDialog, bool> predicate)
            {
                var clock = Stopwatch.StartNew(); bool ready = false;
                while (!ready && clock.ElapsedMilliseconds < 10000) { Drain(); Ui(d => ready = predicate(d)); await Task.Delay(1); }
                Assert.True(ready);
            }
            private void Drain() => _owner._ui.Run(() => { while (_queue.TryDequeue(out var action)) action(); });
            public void Dispose() { Ui(d => d.Dispose()); Client.Dispose(); Drain(); Handler.Dispose(); }
        }
    }
}
