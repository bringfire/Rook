using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VeoDownloadSafetyTests
    {
        private const string Api = "https://generativelanguage.googleapis.com/v1beta/files/test:download?alt=media";
        private sealed class Http : HttpMessageHandler
        {
            internal Func<HttpRequestMessage, HttpResponseMessage> Send = _ => new(HttpStatusCode.OK);
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct) => Task.FromResult(Send(request));
        }
        private sealed class UnknownLengthStream : MemoryStream
        {
            internal UnknownLengthStream() : base(new byte[17]) { }
            public override bool CanSeek => false;
        }
        [Fact]
        public async Task DownloadEnforcesStreamingBoundWithoutContentLength()
        {
            var http = new Http { Send = _ => { var content = new StreamContent(new UnknownLengthStream()); Assert.Null(content.Headers.ContentLength); return new HttpResponseMessage(HttpStatusCode.OK) { Content = content }; } };
            await Assert.ThrowsAnyAsync<Exception>(() => new Rook.Services.Vision.Video.VeoClient(new HttpClient(http), 16).DownloadVideoAsync("test-only", Api, default));
        }
        [Fact]
        public async Task DeclaredOversizeIsRejectedWithoutReadingBody()
        {
            var content = new ByteArrayContent(new byte[] { 1 }); content.Headers.ContentLength = 17;
            var client = new Rook.Services.Vision.Video.VeoClient(new HttpClient(new Http { Send = _ => new HttpResponseMessage(HttpStatusCode.OK) { Content = content } }), 16);
            await Assert.ThrowsAsync<HttpRequestException>(() => client.DownloadVideoAsync("test-only", Api, default));
        }
        [Fact]
        public async Task DownloadFollowsBoundedTrustedRedirectWithoutForwardingApiKey()
        {
            int requests = 0;
            var http = new Http { Send = request => {
                requests++;
                if (requests == 1) { Assert.True(request.Headers.Contains("x-goog-api-key")); var redirect = new HttpResponseMessage(HttpStatusCode.Found); redirect.Headers.Location = new Uri("https://storage.googleapis.com/generated/test.mp4?signature=test"); return redirect; }
                Assert.False(request.Headers.Contains("x-goog-api-key")); return new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(new byte[] { 1, 2, 3 }) };
            } };
            var client = new Rook.Services.Vision.Video.VeoClient(new HttpClient(http));
            Assert.Equal(new byte[] { 1, 2, 3 }, await client.DownloadVideoAsync("test-only", Api, default)); Assert.Equal(2, requests);
        }
        [Theory]
        [InlineData("https://attacker.test/video")]
        [InlineData("http://generativelanguage.googleapis.com/video")]
        [InlineData("https://generativelanguage.googleapis.com:8443/video")]
        [InlineData("https://user@generativelanguage.googleapis.com/video")]
        public async Task UnsafeInitialUriIsRejectedBeforeCredentialsAreSent(string uri)
        {
            int sends = 0; var http = new Http { Send = _ => { sends++; return new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(new byte[] { 1 }) }; } };
            var client = new Rook.Services.Vision.Video.VeoClient(new HttpClient(http));
            await Assert.ThrowsAnyAsync<Exception>(() => client.DownloadVideoAsync("test-only", uri, default)); Assert.Equal(0, sends);
        }
        [Fact]
        public async Task UnsafeRedirectAndRedirectLoopAreBounded()
        {
            foreach (var location in new[] { "https://attacker.test/video", Api })
            {
                int sends = 0; var http = new Http { Send = _ => { sends++; var redirect = new HttpResponseMessage(HttpStatusCode.Found); redirect.Headers.Location = new Uri(location); return redirect; } };
                await Assert.ThrowsAnyAsync<Exception>(() => new Rook.Services.Vision.Video.VeoClient(new HttpClient(http)).DownloadVideoAsync("test-only", Api, default));
                Assert.InRange(sends, 1, 4);
            }
        }
    }
}
