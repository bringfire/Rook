using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Rook.UI.Web;
using Xunit;

namespace Rook.Tests.UI.Web
{
    public class RookWebSurfaceBridgeQueueTests
    {
        private sealed class Surface : RookWebSurface
        {
            protected override string ResourceRoot => "Rook.Tests.Surfaces";
            protected override string EntryPage => "test.html";
            protected override string MinimalFallbackHtml => "<html></html>";
            public readonly List<string> Logs = new();
            protected override void Log(string message) => Logs.Add(message);
            public void Register(string name, Func<JsonNode?, Task<JsonNode?>> handler)
                => RegisterBridgeHandler(name, handler);
        }

        private static string Request(string method, string id = "r7")
            => new JsonObject { ["type"] = "invoke", ["method"] = method,
                ["requestId"] = id, ["args"] = new JsonObject { ["marker"] = "fixture" } }.ToJsonString();

        [Theory]
        [InlineData("submit")]
        [InlineData("vision")]
        [InlineData("reconstruction")]
        public void Handler_runs_only_after_callback_returns_and_preserves_correlation(string method)
        {
            using var surface = new Surface();
            var queue = new Queue<Action>();
            var responses = new List<string>();
            bool returned = false;
            int calls = 0;
            surface.Register(method, args =>
            {
                Assert.True(returned, "handler ran inside the WebView callback");
                calls++;
                return Task.FromResult(args);
            });
            surface.QueueBridgeMessage(Request(method), queue.Enqueue, () => true, responses.Add);
            Assert.Equal(0, calls);
            Assert.Empty(surface.Logs);
            Assert.Single(queue);
            returned = true;
            queue.Dequeue()();
            Assert.Equal(1, calls);
            Assert.Empty(responses);
            Assert.Single(queue);
            queue.Dequeue()();
            var response = JsonNode.Parse(Assert.Single(responses))!;
            Assert.Equal("r7", response["requestId"]!.GetValue<string>());
            Assert.True(response["ok"]!.GetValue<bool>());
            Assert.Equal("fixture", response["result"]!["marker"]!.GetValue<string>());
            Assert.Empty(surface.Logs);
        }

        [Theory]
        [InlineData(true, false)]
        [InlineData(false, false)]
        [InlineData(true, true)]
        [InlineData(false, true)]
        public void Disposal_or_replacement_blocks_dispatch_or_delivery(bool dispose, bool afterDispatch)
        {
            using var surface = new Surface();
            var queue = new Queue<Action>();
            var responses = new List<string>();
            int calls = 0;
            bool current = true;
            surface.Register("submit", _ => { calls++; return Task.FromResult<JsonNode?>(null); });
            surface.QueueBridgeMessage(Request("submit"), queue.Enqueue, () => current, responses.Add);
            if (afterDispatch) queue.Dequeue()();
            if (dispose) surface.Dispose(); else current = false;
            while (queue.Count > 0) queue.Dequeue()();
            Assert.Equal(afterDispatch ? 1 : 0, calls);
            Assert.Empty(responses);
            Assert.Empty(surface.Logs);
        }

        [Fact]
        public async Task Handler_failure_after_await_is_observed_and_returns_correlated_error()
        {
            using var surface = new Surface();
            var queue = new Queue<Action>();
            var responses = new List<string>();
            var release = new TaskCompletionSource<JsonNode?>();
            var responseQueued = new TaskCompletionSource<bool>();
            int posts = 0;
            surface.Register("submit", _ => release.Task);
            surface.QueueBridgeMessage(Request("submit"), action =>
            {
                queue.Enqueue(action);
                if (++posts == 2) responseQueued.SetResult(true);
            }, () => true, responses.Add);
            queue.Dequeue()();
            release.SetException(new InvalidOperationException("local handler failure"));
            Assert.Same(responseQueued.Task, await Task.WhenAny(responseQueued.Task, Task.Delay(3000)));
            queue.Dequeue()();
            var response = JsonNode.Parse(Assert.Single(responses))!;
            Assert.Equal("r7", response["requestId"]!.GetValue<string>());
            Assert.False(response["ok"]!.GetValue<bool>());
            Assert.Equal("handler failed", response["error"]!.GetValue<string>());
            Assert.Contains(surface.Logs, line => line.Contains("local handler failure"));
        }

        [Theory]
        [InlineData("dispatch-post")]
        [InlineData("response-post")]
        [InlineData("response-send")]
        public void Deferred_infrastructure_exceptions_are_observed(string failure)
        {
            using var surface = new Surface();
            var queue = new Queue<Action>();
            int posts = 0;
            surface.Register("submit", _ => Task.FromResult<JsonNode?>(null));
            surface.QueueBridgeMessage(Request("submit"), action =>
            {
                posts++;
                if ((failure == "dispatch-post" && posts == 1) ||
                    (failure == "response-post" && posts == 2)) throw new InvalidOperationException(failure);
                queue.Enqueue(action);
            }, () => true, _ => throw new InvalidOperationException("response-send"));
            while (queue.Count > 0) queue.Dequeue()();
            Assert.Contains(surface.Logs, line => line.Contains(failure));
        }
    }
}
