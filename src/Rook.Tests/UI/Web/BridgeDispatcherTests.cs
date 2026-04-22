using System;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Rook.UI.Web;
using Xunit;

namespace Rook.Tests.UI.Web
{
    public class BridgeDispatcherTests
    {
        private static Func<JsonNode?, Task<JsonNode?>> NoopHandler =>
            args => Task.FromResult<JsonNode?>(null);

        // ─── Register ────────────────────────────────────────────────

        [Fact]
        public void Register_Single_Stored()
        {
            var d = new BridgeDispatcher();
            d.Register("vision.generate", NoopHandler);

            Assert.Equal(1, d.HandlerCount);
            Assert.True(d.HasHandler("vision.generate"));
            Assert.False(d.HasHandler("other"));
        }

        [Fact]
        public void Register_Duplicate_Throws()
        {
            var d = new BridgeDispatcher();
            d.Register("m", NoopHandler);

            Assert.Throws<ArgumentException>(() => d.Register("m", NoopHandler));
        }

        [Theory]
        [InlineData("")]
        [InlineData(" ")]
        public void Register_BlankMethodName_Throws(string method)
        {
            var d = new BridgeDispatcher();
            Assert.Throws<ArgumentException>(() => d.Register(method, NoopHandler));
        }

        [Fact]
        public void Register_NullMethod_Throws()
        {
            var d = new BridgeDispatcher();
            Assert.Throws<ArgumentNullException>(() => d.Register(null!, NoopHandler));
        }

        [Fact]
        public void Register_NullHandler_Throws()
        {
            var d = new BridgeDispatcher();
            Assert.Throws<ArgumentNullException>(() => d.Register("m", null!));
        }

        // ─── DispatchAsync — silent-ignore cases ─────────────────────

        [Theory]
        [InlineData(null)]
        [InlineData("")]
        [InlineData("not json")]
        [InlineData("[1,2,3]")]                                 // root not an object
        [InlineData("{\"type\":\"event\"}")]                     // type != invoke
        [InlineData("{\"type\":42}")]                            // type wrong shape
        [InlineData("{\"type\":\"invoke\"}")]                    // missing requestId
        [InlineData("{\"type\":\"invoke\",\"requestId\":\"\"}")] // empty requestId
        [InlineData("{\"type\":\"invoke\",\"requestId\":42}")]   // non-string requestId
        public async Task DispatchAsync_SilentIgnoreCases_ReturnNull(string? incoming)
        {
            var d = new BridgeDispatcher();
            d.Register("any", NoopHandler);

            var result = await d.DispatchAsync(incoming);
            Assert.Null(result);
        }

        // ─── DispatchAsync — error responses ─────────────────────────

        [Fact]
        public async Task DispatchAsync_MethodMissing_RespondsInvalidRequest()
        {
            var d = new BridgeDispatcher();

            var resp = await d.DispatchAsync(
                "{\"type\":\"invoke\",\"requestId\":\"r1\"}");

            var node = JsonNode.Parse(resp!) as JsonObject;
            Assert.NotNull(node);
            Assert.Equal("response", node!["type"]!.GetValue<string>());
            Assert.Equal("r1", node["requestId"]!.GetValue<string>());
            Assert.False(node["ok"]!.GetValue<bool>());
            Assert.Equal("invalid request", node["error"]!.GetValue<string>());
        }

        [Fact]
        public async Task DispatchAsync_MethodBlank_RespondsInvalidRequest()
        {
            var d = new BridgeDispatcher();

            var resp = await d.DispatchAsync(
                "{\"type\":\"invoke\",\"requestId\":\"r1\",\"method\":\"  \"}");

            var node = JsonNode.Parse(resp!) as JsonObject;
            Assert.False(node!["ok"]!.GetValue<bool>());
            Assert.Equal("invalid request", node["error"]!.GetValue<string>());
        }

        [Fact]
        public async Task DispatchAsync_UnknownMethod_RespondsUnknownMethod()
        {
            var d = new BridgeDispatcher();
            d.Register("known", NoopHandler);

            var resp = await d.DispatchAsync(
                "{\"type\":\"invoke\",\"requestId\":\"r1\",\"method\":\"unknown\"}");

            var node = JsonNode.Parse(resp!) as JsonObject;
            Assert.False(node!["ok"]!.GetValue<bool>());
            Assert.Equal("unknown method", node["error"]!.GetValue<string>());
        }

        // ─── DispatchAsync — success ─────────────────────────────────

        [Fact]
        public async Task DispatchAsync_SyncHandler_ReturnsResult()
        {
            var d = new BridgeDispatcher();
            d.Register("echo", args => Task.FromResult<JsonNode?>(args?.DeepClone()));

            var resp = await d.DispatchAsync(
                "{\"type\":\"invoke\",\"requestId\":\"r1\",\"method\":\"echo\",\"args\":{\"x\":42}}");

            var node = JsonNode.Parse(resp!) as JsonObject;
            Assert.True(node!["ok"]!.GetValue<bool>());
            Assert.Equal("r1", node["requestId"]!.GetValue<string>());
            Assert.Equal(42, ((JsonObject)node["result"]!)["x"]!.GetValue<int>());
        }

        [Fact]
        public async Task DispatchAsync_AsyncHandler_ReturnsResult()
        {
            var d = new BridgeDispatcher();
            d.Register("delayed", async args =>
            {
                await Task.Yield();
                return JsonValue.Create("done");
            });

            var resp = await d.DispatchAsync(
                "{\"type\":\"invoke\",\"requestId\":\"r1\",\"method\":\"delayed\"}");

            var node = JsonNode.Parse(resp!) as JsonObject;
            Assert.True(node!["ok"]!.GetValue<bool>());
            Assert.Equal("done", node["result"]!.GetValue<string>());
        }

        [Fact]
        public async Task DispatchAsync_HandlerReturnsNull_ResultIsJsonNull()
        {
            var d = new BridgeDispatcher();
            d.Register("nothing", args => Task.FromResult<JsonNode?>(null));

            var resp = await d.DispatchAsync(
                "{\"type\":\"invoke\",\"requestId\":\"r1\",\"method\":\"nothing\"}");

            var node = JsonNode.Parse(resp!) as JsonObject;
            Assert.True(node!["ok"]!.GetValue<bool>());
            // JSON null = absent property; verify "result" key is present-but-null
            Assert.True(node.ContainsKey("result"));
            Assert.Null(node["result"]);
        }

        [Fact]
        public async Task DispatchAsync_NullArgs_HandlerReceivesNull()
        {
            JsonNode? capturedArgs = new JsonObject();  // sentinel
            var d = new BridgeDispatcher();
            d.Register("capture", args => { capturedArgs = args; return Task.FromResult<JsonNode?>(null); });

            await d.DispatchAsync(
                "{\"type\":\"invoke\",\"requestId\":\"r1\",\"method\":\"capture\"}");

            Assert.Null(capturedArgs);
        }

        // ─── DispatchAsync — handler exception ───────────────────────

        [Fact]
        public async Task DispatchAsync_HandlerThrows_RespondsGenericError()
        {
            var d = new BridgeDispatcher();
            d.Register("boom", args =>
                throw new InvalidOperationException("internal-secret-detail"));

            var resp = await d.DispatchAsync(
                "{\"type\":\"invoke\",\"requestId\":\"r1\",\"method\":\"boom\"}");

            var node = JsonNode.Parse(resp!) as JsonObject;
            Assert.False(node!["ok"]!.GetValue<bool>());
            var err = node["error"]!.GetValue<string>();
            Assert.Equal("handler failed", err);
            // Substrate must NEVER leak handler internals to JS:
            Assert.DoesNotContain("internal-secret-detail", err);
            Assert.DoesNotContain("InvalidOperationException", err);
        }

        [Fact]
        public async Task DispatchAsync_HandlerThrows_LogReceivesFullDetail()
        {
            string? logged = null;
            var d = new BridgeDispatcher(msg => logged = msg);
            d.Register("boom", args =>
                throw new InvalidOperationException("internal-secret-detail"));

            await d.DispatchAsync(
                "{\"type\":\"invoke\",\"requestId\":\"r1\",\"method\":\"boom\"}");

            Assert.NotNull(logged);
            Assert.Contains("boom", logged);
            Assert.Contains("internal-secret-detail", logged!);
            Assert.Contains("InvalidOperationException", logged);
        }

        // ─── Wire format pinning ─────────────────────────────────────

        [Fact]
        public async Task Response_HasExactFieldNamesAndTypes()
        {
            var d = new BridgeDispatcher();
            d.Register("ok", args => Task.FromResult<JsonNode?>(JsonValue.Create("hi")));

            var resp = await d.DispatchAsync(
                "{\"type\":\"invoke\",\"requestId\":\"abc\",\"method\":\"ok\"}");

            // Pin exact field names by checking the raw JSON string.
            Assert.Contains("\"type\":\"response\"", resp);
            Assert.Contains("\"requestId\":\"abc\"", resp);
            Assert.Contains("\"ok\":true", resp);
            Assert.Contains("\"result\":\"hi\"", resp);
        }
    }
}
