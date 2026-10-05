using System;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.UI.Chat;
using Rook.Tests.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public sealed class VertexConfigurationClientTests
    {
        [Fact]
        public async Task LocalStatusUsesOwnedVertexRouteAndPreservesUnsupportedRegion()
        {
            var handler=new VertexTestHandler((request,_)=>
            {
                Assert.Equal("/internal/providers/vertex/configuration",request.RequestUri!.AbsolutePath);
                Assert.Equal(HttpMethod.Post,request.Method);
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) {Content=new StringContent(
                    "{\"success\":true,\"data\":{\"configured\":true,\"mode\":\"adc\",\"project_id\":\"company-project\",\"video_location\":\"europe-west4\",\"image_location\":\"global\",\"video_available\":false}}",Encoding.UTF8,"application/json")});
            });
            var client=AgentChatClient.ForTests(handler,new Uri("http://127.0.0.1:1"));
            client.SetSessionNonce("owned-nonce");
            var result=await client.ReadVertexConfigurationAsync(CancellationToken.None);
            Assert.True(result.Success); Assert.Equal("europe-west4",result.Status!.VideoLocation); Assert.False(result.Status.VideoAvailable);
            Assert.Equal(1,handler.Calls);
        }
        [Theory]
        [InlineData(302)] [InlineData(500)] [InlineData(200)]
        public async Task UnexpectedResponseNeverLeaksUpstreamText(int status)
        {
            var handler=new VertexTestHandler((_,_)=>Task.FromResult(new HttpResponseMessage((HttpStatusCode)status)
                {Content=new StringContent("{\"secret\":\"secret-sentinel\"}")}));
            var result=await AgentChatClient.ForTests(handler,new Uri("http://127.0.0.1:1")).ReadVertexConfigurationAsync(CancellationToken.None);
            Assert.False(result.Success); Assert.DoesNotContain("secret-sentinel",result.Message);
        }
    }
}
