using System;
using System.Collections.Generic;
using System.Diagnostics;
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
    [Xunit.Collection(Rook.Tests.UI.EtoUiCollection.Name)]
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
                       "\"width\":1,\"height\":1,\"binaryBytes\":68," +
                       "\"sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"," +
                       "\"previewAvailable\":false}]}]}";
            var handler = RecordingHandler.Json(json);
            using var client = AgentChatClient.ForTests(handler, BaseUri);

            var history = await client.GetHistoryAsync("c1", CancellationToken.None);

            Assert.True(history.Available);
            Assert.True(history.EarlierHistoryOmitted);
            Assert.Single(history.Turns);
            Assert.Equal("look", history.Turns[0].UserText);
            Assert.Single(history.Turns[0].Images);
            var image = history.Turns[0].Images[0];
            Assert.Equal("paste.png", image.FileName);
            Assert.Equal("image/png", image.MimeType);
            Assert.Equal(1, image.Width);
            Assert.Equal(1, image.Height);
            Assert.Equal(68, image.BinaryByteCount);
            Assert.Equal(new string('a', 64), image.Sha256);
            Assert.Null(image.Base64Data);
        }

        [Theory]
        [InlineData("settled", "end_turn")]
        [InlineData("cancelled", "cancelled")]
        [InlineData("incomplete", "max_tokens")]
        [InlineData("incomplete", "max_turn_requests")]
        [InlineData("refused", "refusal")]
        public async Task Prompt_parser_preserves_every_closed_terminal_outcome(string outcome, string stopReason)
        {
            var rows = "{\"type\":\"text_delta\",\"sourceOrdinal\":1,\"messageId\":\"m1\",\"text\":\"hi\"}\n" +
                       "{\"type\":\"terminal\",\"outcome\":\"" + outcome +
                       "\",\"stopReason\":\"" + stopReason +
                       "\",\"presentationOutcome\":\"stream_failed\",\"cachePublished\":true}\n";
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
        public async Task Prompt_parser_accepts_the_closed_transport_error_terminal()
        {
            var handler = RecordingHandler.Ndjson(
                "{\"type\":\"terminal\",\"outcome\":\"error\",\"errorCode\":\"protocol_failed\"}\n");
            using var client = AgentChatClient.ForTests(handler, BaseUri);
            var events = new List<ChatEvent>();

            await client.PromptAsync("c1", "hello", Array.Empty<ChatImageInput>(), events.Add, CancellationToken.None);

            var terminal = Assert.Single(events);
            Assert.Equal("error", terminal.Outcome);
            Assert.Equal("protocol_failed", terminal.ErrorCode);
        }

        [Theory]
        [InlineData(null)]
        [InlineData("end_turn")]
        public async Task Prompt_parser_accepts_the_closed_product_error_terminal(string? stopReason)
        {
            var encodedStopReason = stopReason == null ? "null" : "\"" + stopReason + "\"";
            var handler = RecordingHandler.Ndjson(
                "{\"type\":\"terminal\",\"outcome\":\"error\",\"stopReason\":" + encodedStopReason +
                ",\"presentationOutcome\":\"delivered\",\"cachePublished\":false}\n");
            using var client = AgentChatClient.ForTests(handler, BaseUri);
            var events = new List<ChatEvent>();

            await client.PromptAsync("c1", "hello", Array.Empty<ChatImageInput>(), events.Add, CancellationToken.None);

            var terminal = Assert.Single(events);
            Assert.Equal("error", terminal.Outcome);
            Assert.Equal(stopReason, terminal.StopReason);
        }

        [Theory]
        [InlineData("{\"type\":\"terminal\",\"outcome\":\"mystery\",\"stopReason\":\"end_turn\",\"presentationOutcome\":\"delivered\",\"cachePublished\":true}")]
        [InlineData("{\"type\":\"terminal\",\"outcome\":\"settled\",\"stopReason\":\"end_turn\",\"presentationOutcome\":\"mystery\",\"cachePublished\":true}")]
        [InlineData("{\"type\":\"terminal\",\"outcome\":\"settled\",\"stopReason\":\"cancelled\",\"presentationOutcome\":\"delivered\",\"cachePublished\":true}")]
        [InlineData("{\"type\":\"terminal\",\"outcome\":null,\"stopReason\":null,\"presentationOutcome\":\"delivered\",\"cachePublished\":true}")]
        [InlineData("{\"type\":\"terminal\",\"outcome\":\"error\",\"stopReason\":\"provider_error\",\"presentationOutcome\":\"delivered\",\"cachePublished\":true}")]
        [InlineData("{\"type\":\"terminal\",\"outcome\":\"settled\",\"stopReason\":\"end_turn\",\"presentationOutcome\":\"delivered\"}")]
        [InlineData("{\"type\":\"terminal\",\"outcome\":\"error\",\"errorCode\":\"protocol_failed\",\"cachePublished\":false}")]
        [InlineData("{\"type\":\"terminal\",\"outcome\":\"error\",\"errorCode\":\"\"}")]
        [InlineData("{\"type\":\"terminal\",\"outcome\":\"settled\",\"stopReason\":\"end_turn\",\"presentationOutcome\":\"delivered\",\"cachePublished\":true,\"extra\":1}")]
        public async Task Prompt_parser_rejects_terminal_rows_outside_the_closed_schema(string terminalRow)
        {
            var handler = RecordingHandler.Ndjson(terminalRow + "\n");
            using var client = AgentChatClient.ForTests(handler, BaseUri);

            var error = await Assert.ThrowsAsync<AgentChatHttpException>(
                () => client.PromptAsync("c1", "hello", Array.Empty<ChatImageInput>(), _ => { }, CancellationToken.None));

            Assert.Equal("invalid_stream", error.Code);
        }

        [Fact]
        public async Task Prompt_parser_keeps_tool_cards_as_presentation_only()
        {
            var rows = "{\"type\":\"tool_update\",\"sourceOrdinal\":7,\"kind\":\"tool_call_update\"," +
                       "\"messageId\":\"t1\",\"text\":\"Inspect\",\"payload\":{\"status\":\"completed\"}}\n" +
                       "{\"type\":\"terminal\",\"outcome\":\"settled\",\"stopReason\":\"end_turn\",\"presentationOutcome\":\"delivered\",\"cachePublished\":true}\n";
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
        public async Task Prompt_sends_the_closed_text_and_image_wire_shape()
        {
            var handler = RecordingHandler.Ndjson(
                "{\"type\":\"terminal\",\"outcome\":\"settled\",\"stopReason\":\"end_turn\",\"presentationOutcome\":\"delivered\",\"cachePublished\":true}\n");
            using var client = AgentChatClient.ForTests(handler, BaseUri);

            await client.PromptAsync(
                "c1",
                "inspect",
                new[] { new ChatImageInput("paste.png", "image/png", "AQID") },
                _ => { },
                CancellationToken.None);

            using var body = JsonDocument.Parse(handler.LastBody!);
            Assert.Equal(2, CountProperties(body.RootElement));
            Assert.Equal("inspect", body.RootElement.GetProperty("text").GetString());
            var image = body.RootElement.GetProperty("images")[0];
            Assert.Equal(3, CountProperties(image));
            Assert.Equal("paste.png", image.GetProperty("fileName").GetString());
            Assert.Equal("image/png", image.GetProperty("mimeType").GetString());
            Assert.Equal("AQID", image.GetProperty("base64Data").GetString());
        }

        [Fact]
        public async Task Slice_C_panel_prompt_owner_preserves_frozen_authenticated_image_wire()
        {
            var root = new System.IO.DirectoryInfo(AppContext.BaseDirectory);
            while (root != null && !System.IO.File.Exists(System.IO.Path.Combine(root.FullName,
                "scripts", "qualification", "fixtures", "slice-c-http-request.json"))) root = root.Parent;
            Assert.NotNull(root);
            using var fixture = JsonDocument.Parse(System.IO.File.ReadAllBytes(System.IO.Path.Combine(root!.FullName,
                "scripts", "qualification", "fixtures", "slice-c-http-request.json")));
            var input = fixture.RootElement;
            var image = input.GetProperty("images")[0];
            var handler = RecordingHandler.Ndjson(
                "{\"type\":\"terminal\",\"outcome\":\"settled\",\"stopReason\":\"end_turn\",\"presentationOutcome\":\"delivered\",\"cachePublished\":true}\n");
            using var client = AgentChatClient.ForTests(handler, BaseUri);
            client.SetSessionNonce("slice-c-fixture-nonce");
            await AgentChatTab.RunOwnedPromptAsync(client, BaseUri, "cccccccccccc4ccc8ccccccccccccccc",
                input.GetProperty("text").GetString()!,
                new[] { new ChatImageInput(image.GetProperty("fileName").GetString()!,
                    image.GetProperty("mimeType").GetString()!, image.GetProperty("base64Data").GetString()!) },
                _ => { }, CancellationToken.None);
            Assert.Equal("slice-c-fixture-nonce", handler.LastNonce);
            Assert.Equal("/agent/chat/conversations/cccccccccccc4ccc8ccccccccccccccc/prompt", handler.LastPath);
            Assert.Single(handler.Requests);
            using var actual = JsonDocument.Parse(handler.LastBody!);
            Assert.Equal(2, CountProperties(actual.RootElement));
            Assert.Equal(input.GetProperty("text").GetString(), actual.RootElement.GetProperty("text").GetString());
            Assert.Equal(1, actual.RootElement.GetProperty("images").GetArrayLength());
            var sent = actual.RootElement.GetProperty("images")[0];
            Assert.Equal(3, CountProperties(sent));
            foreach (var key in new[] { "fileName", "mimeType", "base64Data" })
                Assert.Equal(image.GetProperty(key).GetString(), sent.GetProperty(key).GetString());
        }

        [Fact]
        public async Task Error_body_is_bounded_and_classified()
        {
            var body = "{\"error\":{\"code\":\"target_unavailable\",\"message\":\"" +
                       new string('x', 40_000) + "\"}}";
            var handler = RecordingHandler.Json(body, HttpStatusCode.Conflict);
            using var client = AgentChatClient.ForTests(handler, BaseUri);

            var error = await Assert.ThrowsAsync<AgentChatHttpException>(
                () => client.ReopenAsync("c1", CancellationToken.None));

            Assert.Equal("target_unavailable", error.Code);
            Assert.True(Encoding.UTF8.GetByteCount(error.Message) <= AgentChatClient.MaxErrorMessageUtf8Bytes);
        }

        [Fact]
        public async Task Prompt_parser_rejects_a_malformed_intermediate_row()
        {
            var rows = "{\"type\":\"text_delta\",\"sourceOrdinal\":1,\"text\":\"kept\"}\n" +
                       "{not-json}\n" +
                       "{\"type\":\"terminal\",\"outcome\":\"settled\",\"stopReason\":\"end_turn\",\"presentationOutcome\":\"delivered\",\"cachePublished\":true}\n";
            var handler = RecordingHandler.Ndjson(rows);
            using var client = AgentChatClient.ForTests(handler, BaseUri);
            var events = new List<ChatEvent>();

            var error = await Assert.ThrowsAsync<AgentChatHttpException>(
                () => client.PromptAsync("c1", "hello", Array.Empty<ChatImageInput>(), events.Add, CancellationToken.None));

            Assert.Equal("invalid_stream", error.Code);
            Assert.Single(events);
            Assert.Equal("kept", events[0].Text);
        }

        [Fact]
        public async Task Agent_tab_prompt_owner_requests_cancel_once_when_stream_is_invalid()
        {
            var handler = RecordingHandler.Sequence(
                RecordingHandler.NdjsonResponse("{not-json}\n"),
                RecordingHandler.Response("{\"accepted\":true}"));
            using var client = AgentChatClient.ForTests(handler, BaseUri);

            var error = await Assert.ThrowsAsync<AgentChatHttpException>(
                () => AgentChatTab.RunOwnedPromptAsync(
                    client,
                    BaseUri,
                    "c1",
                    "hello",
                    Array.Empty<ChatImageInput>(),
                    _ => { },
                    CancellationToken.None));

            Assert.Equal("invalid_stream", error.Code);
            Assert.Equal(2, handler.Requests.Count);
            Assert.StartsWith("POST /agent/chat/conversations/c1/prompt ", handler.Requests[0]);
            Assert.Equal("POST /agent/chat/conversations/c1/cancel {}", handler.Requests[1]);
        }

        [Fact]
        public async Task Agent_tab_prompt_owner_cancels_after_malformed_utf8_stream_bytes()
        {
            var handler = RecordingHandler.Sequence(
                RecordingHandler.NdjsonBytesResponse(0xc3, 0x28, 0x0a),
                RecordingHandler.Response("{\"accepted\":true}"));
            using var client = AgentChatClient.ForTests(handler, BaseUri);

            var error = await Assert.ThrowsAsync<AgentChatHttpException>(
                () => AgentChatTab.RunOwnedPromptAsync(
                    client,
                    BaseUri,
                    "c1",
                    "hello",
                    Array.Empty<ChatImageInput>(),
                    _ => { },
                    CancellationToken.None));

            Assert.Equal("invalid_stream", error.Code);
            Assert.Equal(2, handler.Requests.Count);
            Assert.Equal("POST /agent/chat/conversations/c1/cancel {}", handler.Requests[1]);
        }

        [Fact]
        public async Task Invalid_stream_cancel_deadline_preserves_the_original_stream_error()
        {
            var handler = new SlowCancelHandler();
            using var client = AgentChatClient.ForTests(handler, BaseUri);
            var elapsed = Stopwatch.StartNew();

            var error = await Assert.ThrowsAsync<AgentChatHttpException>(
                () => AgentChatTab.RunOwnedPromptAsync(
                    client,
                    BaseUri,
                    "c1",
                    "hello",
                    Array.Empty<ChatImageInput>(),
                    _ => { },
                    CancellationToken.None));

            elapsed.Stop();
            Assert.Equal("invalid_stream", error.Code);
            Assert.Equal(2, handler.RequestCount);
            Assert.True(handler.CancelRequestWasCancelled);
            Assert.True(elapsed.Elapsed < TimeSpan.FromSeconds(2.5), $"Cancellation took {elapsed.Elapsed}.");
        }

        [Fact]
        public async Task Reopen_rejects_a_different_returned_conversation_identity()
        {
            var handler = RecordingHandler.Json(
                "{\"conversationId\":\"different\",\"durable\":true,\"targetAvailable\":true}");
            using var client = AgentChatClient.ForTests(handler, BaseUri);

            var error = await Assert.ThrowsAsync<ReopenIdentityMismatchException>(
                () => client.ReopenAsync("authoritative", CancellationToken.None));

            Assert.Equal("invalid_response", error.Code);
        }

        [Fact]
        public async Task Prompt_parser_requires_exactly_one_terminal_row()
        {
            var handler = RecordingHandler.Ndjson(
                "{\"type\":\"text_delta\",\"sourceOrdinal\":1,\"text\":\"partial\"}\n");
            using var client = AgentChatClient.ForTests(handler, BaseUri);

            var error = await Assert.ThrowsAsync<AgentChatHttpException>(
                () => client.PromptAsync("c1", "hello", Array.Empty<ChatImageInput>(), _ => { }, CancellationToken.None));

            Assert.Equal("invalid_stream", error.Code);
        }

        [Fact]
        public async Task Prompt_parser_rejects_rows_after_terminal_settlement()
        {
            var rows = "{\"type\":\"terminal\",\"outcome\":\"settled\",\"stopReason\":\"end_turn\",\"presentationOutcome\":\"delivered\",\"cachePublished\":true}\n" +
                       "{\"type\":\"text_delta\",\"sourceOrdinal\":2,\"text\":\"late\"}\n";
            var handler = RecordingHandler.Ndjson(rows);
            using var client = AgentChatClient.ForTests(handler, BaseUri);
            var events = new List<ChatEvent>();

            var error = await Assert.ThrowsAsync<AgentChatHttpException>(
                () => client.PromptAsync("c1", "hello", Array.Empty<ChatImageInput>(), events.Add, CancellationToken.None));

            Assert.Equal("invalid_stream", error.Code);
            Assert.Empty(events);
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

        [Fact]
        public async Task Closing_during_create_defers_client_disposal_until_identity_can_be_handed_off()
        {
            var handler = new DelayedResponseHandler(
                "{\"conversationId\":\"created-after-close\",\"durable\":false,\"targetAvailable\":true}");
            using var client = AgentChatClient.ForTests(handler, BaseUri);
            var custody = new InitializationRequestCustody();
            Assert.True(custody.TryBegin());
            var create = client.CreateAsync(new CreateConversationRequest
            {
                HostGenerationId = "11111111-1111-1111-1111-111111111111",
                DocumentSerialNumber = 41,
                RouteProcessId = 123,
            });

            await handler.RequestStarted.Task;
            Assert.False(custody.Detach());
            handler.ReleaseResponse.SetResult(true);
            var view = await create;
            var handoff = custody.CompleteWithIdentity();

            Assert.False(custody.IsAttached);
            Assert.Equal("created-after-close", view.ConversationId);
            Assert.False(handoff.PublishToTab);
            Assert.True(handoff.QueueClose);
            Assert.True(handoff.DisposeClient);
            Assert.False(handler.RequestWasCancelled);
        }

        [Fact]
        public void Agent_tab_close_during_create_hands_the_returned_identity_to_close_delivery()
        {
            RunOnSta(() =>
            {
                EnsureEtoApplication();
                var handler = new DelayedResponseHandler(
                    "{\"conversationId\":\"created-after-close\",\"durable\":false,\"targetAvailable\":true}");
                using var client = AgentChatClient.ForTests(handler, BaseUri, HealthyService());
                var closed = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
                using var coordinator = ConversationCloseCoordinator.ForTests((_, conversationId, _, _) =>
                {
                    closed.TrySetResult(conversationId);
                    return Task.CompletedTask;
                });
                using var tab = new AgentChatTab(new CreateConversationRequest
                {
                    HostGenerationId = "11111111-1111-1111-1111-111111111111",
                    DocumentSerialNumber = 41,
                    RouteProcessId = 123,
                }, client, coordinator, initializePresentation: false);

                var initialize = tab.InitializeAsync();
                handler.RequestStarted.Task.GetAwaiter().GetResult();
                tab.OnTabClosed();
                handler.ReleaseResponse.TrySetResult(true);

                initialize.GetAwaiter().GetResult();
                Assert.Equal("created-after-close", closed.Task.GetAwaiter().GetResult());
                Assert.False(handler.RequestWasCancelled);
            });
        }

        [Fact]
        public void Agent_tab_close_during_reopen_hands_the_returned_identity_to_close_delivery()
        {
            RunOnSta(() =>
            {
                EnsureEtoApplication();
                var handler = new DelayedResponseHandler(
                    "{\"conversationId\":\"existing-conversation\",\"durable\":true,\"targetAvailable\":true}");
                using var client = AgentChatClient.ForTests(handler, BaseUri, HealthyService());
                var closed = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
                using var coordinator = ConversationCloseCoordinator.ForTests((_, conversationId, _, _) =>
                {
                    closed.TrySetResult(conversationId);
                    return Task.CompletedTask;
                });
                using var tab = new AgentChatTab(new ConversationSummary
                {
                    ConversationId = "existing-conversation",
                }, client, coordinator, initializePresentation: false);

                var initialize = tab.InitializeAsync();
                handler.RequestStarted.Task.GetAwaiter().GetResult();
                tab.OnTabClosed();
                handler.ReleaseResponse.TrySetResult(true);

                initialize.GetAwaiter().GetResult();
                Assert.Equal("existing-conversation", closed.Task.GetAwaiter().GetResult());
                Assert.False(handler.RequestWasCancelled);
            });
        }

        [Fact]
        public void Agent_tab_mismatched_reopen_queues_only_the_authoritative_identity()
        {
            RunOnSta(() =>
            {
                EnsureEtoApplication();
                var handler = new DelayedResponseHandler(
                    "{\"conversationId\":\"different-conversation\",\"durable\":true,\"targetAvailable\":true}");
                using var client = AgentChatClient.ForTests(handler, BaseUri, HealthyService());
                var closed = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
                using var coordinator = ConversationCloseCoordinator.ForTests((_, conversationId, _, _) =>
                {
                    closed.TrySetResult(conversationId);
                    return Task.CompletedTask;
                });
                using var tab = new AgentChatTab(new ConversationSummary
                {
                    ConversationId = "authoritative-conversation",
                }, client, coordinator, initializePresentation: false);

                var initialize = tab.InitializeAsync();
                handler.RequestStarted.Task.GetAwaiter().GetResult();
                tab.OnTabClosed();
                handler.ReleaseResponse.TrySetResult(true);

                initialize.GetAwaiter().GetResult();
                Assert.Equal("authoritative-conversation", closed.Task.GetAwaiter().GetResult());
                Assert.False(handler.RequestWasCancelled);
            });
        }

        [Fact]
        public async Task Provisional_delete_is_a_successful_delete_without_a_durable_record()
        {
            var handler = RecordingHandler.Json(
                "{\"associationRemoved\":false,\"artifactsRemoved\":true}");
            using var client = AgentChatClient.ForTests(handler, BaseUri);

            var result = await client.DeleteAsync("provisional", CancellationToken.None);

            Assert.False(result.AssociationRemoved);
            Assert.True(result.ArtifactsRemoved);
        }

        private static int CountProperties(JsonElement element)
        {
            var count = 0;
            foreach (var _ in element.EnumerateObject()) count++;
            return count;
        }

        private static ChatServiceHealth HealthyService()
            => new()
            {
                ServiceAvailable = true,
                RuntimeAvailable = true,
                BaseUri = BaseUri,
            };

        private static void EnsureEtoApplication()
        {
            Rook.Tests.UI.EtoTestPlatform.Ensure();
            SynchronizationContext.SetSynchronizationContext(null);
        }

        private static void RunOnSta(Action action)
        {
            Exception? failure = null;
            using var finished = new ManualResetEventSlim();
            var thread = new Thread(() =>
            {
                try
                {
                    action();
                }
                catch (Exception ex)
                {
                    failure = ex;
                }
                finally
                {
                    finished.Set();
                }
            })
            {
                IsBackground = true,
            };
            thread.SetApartmentState(ApartmentState.STA);
            thread.Start();
            Assert.True(finished.Wait(TimeSpan.FromSeconds(10)), "STA integration test timed out.");
            if (failure != null) throw new AggregateException(failure);
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
            public string? LastNonce { get; private set; }
            public List<string> Requests { get; } = new();

            public static RecordingHandler Json(string body, HttpStatusCode status = HttpStatusCode.OK)
                => Sequence(Response(body, status));

            public static RecordingHandler Ndjson(string body)
                => Sequence(NdjsonResponse(body));

            public static HttpResponseMessage NdjsonResponse(string body)
                => new(HttpStatusCode.OK)
                {
                    Content = new StringContent(body, Encoding.UTF8, "application/x-ndjson"),
                };

            public static HttpResponseMessage NdjsonBytesResponse(params byte[] body)
            {
                var content = new ByteArrayContent(body);
                content.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue(
                    "application/x-ndjson");
                return new HttpResponseMessage(HttpStatusCode.OK) { Content = content };
            }

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
                LastNonce = request.Headers.TryGetValues("X-Rook-Session", out var nonces)
                    ? string.Join("", nonces) : null;
                Requests.Add($"{request.Method.Method} {LastPath} {LastBody}");
                return _responses.Dequeue();
            }
        }

        private sealed class DelayedResponseHandler : HttpMessageHandler
        {
            private readonly string _body;

            public DelayedResponseHandler(string body)
            {
                _body = body;
            }

            public TaskCompletionSource<bool> RequestStarted { get; } =
                new(TaskCreationOptions.RunContinuationsAsynchronously);
            public TaskCompletionSource<bool> ReleaseResponse { get; } =
                new(TaskCreationOptions.RunContinuationsAsynchronously);
            public bool RequestWasCancelled { get; private set; }

            protected override async Task<HttpResponseMessage> SendAsync(
                HttpRequestMessage request,
                CancellationToken cancellationToken)
            {
                using var cancellation = cancellationToken.Register(() => RequestWasCancelled = true);
                RequestStarted.TrySetResult(true);
                await ReleaseResponse.Task;
                cancellationToken.ThrowIfCancellationRequested();
                return RecordingHandler.Response(_body, HttpStatusCode.Created);
            }
        }

        private sealed class SlowCancelHandler : HttpMessageHandler
        {
            public int RequestCount { get; private set; }
            public bool CancelRequestWasCancelled { get; private set; }

            protected override async Task<HttpResponseMessage> SendAsync(
                HttpRequestMessage request,
                CancellationToken cancellationToken)
            {
                RequestCount++;
                if (RequestCount == 1)
                    return RecordingHandler.NdjsonResponse("{not-json}\n");
                using var registration = cancellationToken.Register(() => CancelRequestWasCancelled = true);
                await Task.Delay(TimeSpan.FromSeconds(3), cancellationToken);
                return RecordingHandler.Response("{\"accepted\":true}");
            }
        }
    }
}
