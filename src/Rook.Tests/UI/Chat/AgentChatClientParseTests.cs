using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public sealed class AgentChatClientParseTests
    {
        private static readonly Uri BaseUri = new("http://127.0.0.1:8765");

        [Fact]
        public async Task Reopen_does_not_send_model_or_reasoning_overrides()
        {
            var handler = RecordingHandler.Json("{\"conversationId\":\"c1\",\"durable\":true,\"targetAvailable\":true}");
            using var client = AgentChatClient.ForTests(handler, BaseUri);

            await client.ReopenAsync("c1", CancellationToken.None);

            Assert.Equal(HttpMethod.Post, handler.LastMethod);
            Assert.Equal("/agent/chat/conversations/c1/reopen", handler.LastPath);
            Assert.Equal("{}", handler.LastBody);
            Assert.DoesNotContain("model", handler.LastBody!, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("reasoning", handler.LastBody!, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public async Task Create_sends_only_the_approved_creation_contract()
        {
            var handler = RecordingHandler.Json("{\"conversationId\":\"c1\",\"durable\":false,\"targetAvailable\":true}", HttpStatusCode.Created);
            using var client = AgentChatClient.ForTests(handler, BaseUri);
            var request = new CreateConversationRequest
            {
                HostGenerationId = "11111111-1111-1111-1111-111111111111",
                DocumentSerialNumber = 41,
                RouteProcessId = 123,
                SavedDocumentDirectory = "C:\\work",
                Model = "anthropic/claude-sonnet-4-6",
                Reasoning = "high",
            };

            var view = await client.CreateAsync(request, CancellationToken.None);

            Assert.Equal("c1", view.ConversationId);
            Assert.False(view.Durable);
            Assert.Equal("/agent/chat/conversations", handler.LastPath);
            using var payload = JsonDocument.Parse(handler.LastBody!);
            var root = payload.RootElement;
            Assert.Equal(7, CountProperties(root));
            Assert.Equal("full", root.GetProperty("profile").GetString());
            Assert.Equal(request.HostGenerationId, root.GetProperty("hostGenerationId").GetString());
            Assert.Equal(41u, root.GetProperty("documentSerialNumber").GetUInt32());
            Assert.Equal(123, root.GetProperty("routeProcessId").GetInt32());
            Assert.Equal("C:\\work", root.GetProperty("savedDocumentDirectory").GetString());
            Assert.Equal(request.Model, root.GetProperty("model").GetString());
            Assert.Equal("high", root.GetProperty("reasoning").GetString());
        }

        [Fact]
        public async Task Reopen_history_is_presentation_only_and_keeps_image_metadata()
        {
            var json = "{\"available\":true,\"earlierHistoryOmitted\":true," +
                       "\"message\":\"Earlier presentation history was omitted. Prime retains the authoritative conversation state.\"," +
                       "\"turns\":[{\"sequence\":2,\"userText\":\"look\",\"assistantText\":\"seen\"," +
                       "\"stopReason\":\"end_turn\",\"images\":[{\"fileName\":\"paste.png\",\"mimeType\":\"image/png\"," +
                       "\"width\":1,\"height\":1,\"binaryByteCount\":68,\"sha256\":\"abc\"}]}]}";
            var handler = RecordingHandler.Json(json);
            using var client = AgentChatClient.ForTests(handler, BaseUri);

            var history = await client.GetHistoryAsync("c1", CancellationToken.None);

            Assert.True(history.Available);
            Assert.True(history.EarlierHistoryOmitted);
            Assert.Single(history.Turns);
            Assert.Equal("look", history.Turns[0].UserText);
            Assert.Single(history.Turns[0].Images);
            Assert.Equal("paste.png", history.Turns[0].Images[0].FileName);
            Assert.Null(history.Turns[0].Images[0].Base64Data);
        }

        [Theory]
        [InlineData("settled")]
        [InlineData("cancelled")]
        [InlineData("incomplete")]
        [InlineData("refused")]
        [InlineData("error")]
        public async Task Prompt_parser_preserves_every_closed_terminal_outcome(string outcome)
        {
            var rows = "{\"type\":\"text_delta\",\"sourceOrdinal\":1,\"messageId\":\"m1\",\"text\":\"hi\"}\n" +
                       "{\"type\":\"terminal\",\"outcome\":\"" + outcome +
                       "\",\"stopReason\":\"end_turn\",\"presentationOutcome\":\"stream_failed\",\"cachePublished\":true}\n";
            var handler = RecordingHandler.Ndjson(rows);
            using var client = AgentChatClient.ForTests(handler, BaseUri);
            var events = new List<ChatEvent>();

            await client.PromptAsync("c1", "hello", Array.Empty<ChatImageInput>(), events.Add, CancellationToken.None);

            Assert.Equal(2, events.Count);
            Assert.Equal("hi", events[0].Text);
            Assert.Equal(outcome, events[1].Outcome);
            Assert.Equal("stream_failed", events[1].PresentationOutcome);
            Assert.True(events[1].CachePublished);
        }

        [Fact]
        public async Task Prompt_parser_keeps_tool_cards_as_presentation_only()
        {
            var rows = "{\"type\":\"tool_update\",\"sourceOrdinal\":7,\"kind\":\"tool_call_update\"," +
                       "\"messageId\":\"t1\",\"text\":\"Inspect\",\"payload\":{\"status\":\"completed\"}}\n" +
                       "{\"type\":\"terminal\",\"outcome\":\"settled\",\"presentationOutcome\":\"delivered\"}\n";
            var handler = RecordingHandler.Ndjson(rows);
            using var client = AgentChatClient.ForTests(handler, BaseUri);
            var events = new List<ChatEvent>();

            await client.PromptAsync("c1", "hello", Array.Empty<ChatImageInput>(), events.Add, CancellationToken.None);

            Assert.Equal("tool_update", events[0].Type);
            Assert.Equal("tool_call_update", events[0].Kind);
            Assert.Equal("completed", events[0].Payload!.Value.GetProperty("status").GetString());
            Assert.False(events[0].CertifiesMutation);
        }

        [Fact]
        public async Task Error_body_is_bounded_and_classified()
        {
            var body = "{\"code\":\"target_unavailable\",\"error\":\"" + new string('x', 40_000) + "\"}";
            var handler = RecordingHandler.Json(body, HttpStatusCode.Conflict);
            using var client = AgentChatClient.ForTests(handler, BaseUri);

            var error = await Assert.ThrowsAsync<AgentChatHttpException>(
                () => client.ReopenAsync("c1", CancellationToken.None));

            Assert.Equal("target_unavailable", error.Code);
            Assert.True(Encoding.UTF8.GetByteCount(error.Message) <= AgentChatClient.MaxErrorMessageUtf8Bytes);
        }

        [Fact]
        public async Task Cancel_close_and_delete_use_closed_routes_and_empty_bodies()
        {
            var handler = RecordingHandler.Sequence(
                RecordingHandler.Response("{\"accepted\":true}"),
                RecordingHandler.Response("{\"outcome\":\"clean\",\"childExitObserved\":true}"),
                RecordingHandler.Response("{\"associationRemoved\":true,\"artifactsRemoved\":false}"));
            using var client = AgentChatClient.ForTests(handler, BaseUri);

            Assert.True((await client.CancelAsync("c1", CancellationToken.None)).Accepted);
            Assert.Equal("clean", (await client.CloseAsync("c1", CancellationToken.None)).Outcome);
            Assert.True((await client.DeleteAsync("c1", CancellationToken.None)).AssociationRemoved);

            Assert.Equal(new[]
            {
                "POST /agent/chat/conversations/c1/cancel {}",
                "POST /agent/chat/conversations/c1/close {}",
                "DELETE /agent/chat/conversations/c1 "
            }, handler.Requests);
        }

        private static int CountProperties(JsonElement element)
        {
            var count = 0;
            foreach (var _ in element.EnumerateObject()) count++;
            return count;
        }

        private sealed class RecordingHandler : HttpMessageHandler
        {
            private readonly Queue<HttpResponseMessage> _responses;

            private RecordingHandler(IEnumerable<HttpResponseMessage> responses)
            {
                _responses = new Queue<HttpResponseMessage>(responses);
            }

            public HttpMethod? LastMethod { get; private set; }
            public string? LastPath { get; private set; }
            public string? LastBody { get; private set; }
            public List<string> Requests { get; } = new();

            public static RecordingHandler Json(string body, HttpStatusCode status = HttpStatusCode.OK)
                => Sequence(Response(body, status));

            public static RecordingHandler Ndjson(string body)
                => Sequence(new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(body, Encoding.UTF8, "application/x-ndjson"),
                });

            public static RecordingHandler Sequence(params HttpResponseMessage[] responses)
                => new(responses);

            public static HttpResponseMessage Response(string body, HttpStatusCode status = HttpStatusCode.OK)
                => new(status) { Content = new StringContent(body, Encoding.UTF8, "application/json") };

            protected override async Task<HttpResponseMessage> SendAsync(
                HttpRequestMessage request,
                CancellationToken cancellationToken)
            {
                LastMethod = request.Method;
                LastPath = request.RequestUri!.AbsolutePath;
                LastBody = request.Content == null ? null : await request.Content.ReadAsStringAsync();
                Requests.Add($"{request.Method.Method} {LastPath} {LastBody}");
                return _responses.Dequeue();
            }
        }
    }
}
