using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Tests.Services.Vision.Video
{
    /// <summary>
    /// HttpMessageHandler test helper. Intercepts SendAsync and lets
    /// tests compose the response per request URL/method, while
    /// recording the requests for assertions.
    /// </summary>
    internal sealed class TestHttpMessageHandler : HttpMessageHandler
    {
        public Func<HttpRequestMessage, HttpResponseMessage>? OnSend { get; set; }

        public List<HttpRequestMessage> Requests { get; } = new();

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Requests.Add(request);

            if (cancellationToken.IsCancellationRequested)
                return Task.FromCanceled<HttpResponseMessage>(cancellationToken);

            var response = OnSend?.Invoke(request)
                ?? new HttpResponseMessage(System.Net.HttpStatusCode.OK);

            return Task.FromResult(response);
        }
    }
}
