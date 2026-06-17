using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public class AgentChatClientParseTests
    {
        [Fact]
        public void Success_from_2xx_without_success_field()
        {
            var body = "{\"conversation_id\":\"c1\",\"model\":\"m\",\"routing\":\"local\"}";
            var r = AgentChatClient.ParseSetModelResult(200, true, body);
            Assert.True(r.Success);
            Assert.Equal(200, r.StatusCode);
            Assert.Null(r.ErrorCode);
        }

        [Fact]
        public void Conversation_processing_409()
        {
            var body = "{\"code\":\"conversation_processing\",\"error\":\"busy\"}";
            var r = AgentChatClient.ParseSetModelResult(409, false, body);
            Assert.False(r.Success);
            Assert.Equal("conversation_processing", r.ErrorCode);
            Assert.Equal("busy", r.Message);
        }

        [Fact]
        public void Model_unavailable_400_with_allowed_list()
        {
            var body = "{\"code\":\"model_override_unavailable\",\"error\":\"nope\",\"allowed_model_overrides\":[\"a\",\"b\"]}";
            var r = AgentChatClient.ParseSetModelResult(400, false, body);
            Assert.False(r.Success);
            Assert.Equal("model_override_unavailable", r.ErrorCode);
            Assert.NotNull(r.AllowedModelOverrides);
            Assert.Equal(2, r.AllowedModelOverrides!.Count);
        }

        [Fact]
        public void Not_found_404()
        {
            var body = "{\"error\":\"Conversation not found\"}";
            var r = AgentChatClient.ParseSetModelResult(404, false, body);
            Assert.False(r.Success);
            Assert.Equal("Conversation not found", r.Message);
            Assert.Null(r.ErrorCode);
        }

        [Fact]
        public void Malformed_body_does_not_throw()
        {
            var r = AgentChatClient.ParseSetModelResult(200, true, "not json");
            Assert.True(r.Success);
            Assert.Null(r.ErrorCode);
        }

        [Fact]
        public void Empty_body_follows_http_status()
        {
            var r = AgentChatClient.ParseSetModelResult(500, false, "");
            Assert.False(r.Success);
        }
    }
}
