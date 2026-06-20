using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Reconstruction;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionRemoteAssetDownloaderTests
{
    private sealed class StubHandler : HttpMessageHandler
    {
        public Queue<Func<HttpResponseMessage>> Responses = new();
        public int Calls;

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage r, CancellationToken ct)
        {
            Calls++;
            ct.ThrowIfCancellationRequested();
            return Task.FromResult(Responses.Dequeue()());
        }
    }

    private static HttpResponseMessage Ok(byte[] body, string mime = "model/gltf-binary", long? len = null)
    {
        var m = new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(body) };
        m.Content.Headers.ContentType = new MediaTypeHeaderValue(mime);
        if (len is { } l) m.Content.Headers.ContentLength = l;
        return m;
    }

    private static IReconstructionRemoteAssetDownloader Make(StubHandler h) =>
        new ReconstructionRemoteAssetDownloader(new HttpClient(h), maxBytesByRole: r => r.StartsWith("model_") ? 100_000_000 : 25_000_000);

    [Fact]
    public async Task Download_Success_ReturnsBytesAndMime()
    {
        var h = new StubHandler();
        h.Responses.Enqueue(() => Ok(new byte[] { 1, 2, 3 }));
        var r = await Make(h).DownloadAsync(new Uri("https://cdn.fal.run/a.glb"), "model_glb", CancellationToken.None);
        Assert.True(r.Success);
        Assert.Equal(3, r.Bytes!.Length);
    }

    [Fact]
    public async Task Download_HeaderCapExceeded_FailsWithoutStreaming()
    {
        var h = new StubHandler();
        h.Responses.Enqueue(() => Ok(new byte[] { 1 }, len: 999_999_999_999));
        var r = await Make(h).DownloadAsync(new Uri("https://cdn.fal.run/a.glb"), "model_glb", CancellationToken.None);
        Assert.False(r.Success);
        Assert.Equal(GenerationErrorCode.UnsupportedMedia, r.Error!.Code);
    }

    [Fact]
    public async Task Download_StreamCapExceeded_Fails()
    {
        var big = new byte[26_000_000];
        var h = new StubHandler();
        h.Responses.Enqueue(() => Ok(big)); // texture role → 25MB cap
        var r = await Make(h).DownloadAsync(new Uri("https://cdn.fal.run/t.png"), "texture", CancellationToken.None);
        Assert.False(r.Success);
    }

    [Fact]
    public async Task Download_EmptyBody_Fails()
    {
        var h = new StubHandler();
        h.Responses.Enqueue(() => Ok(Array.Empty<byte>()));
        var r = await Make(h).DownloadAsync(new Uri("https://cdn.fal.run/a.glb"), "model_glb", CancellationToken.None);
        Assert.False(r.Success);
    }

    [Fact]
    public async Task Download_404_NoRetry()
    {
        var h = new StubHandler();
        h.Responses.Enqueue(() => new HttpResponseMessage(HttpStatusCode.NotFound));
        var r = await Make(h).DownloadAsync(new Uri("https://cdn.fal.run/a.glb"), "model_glb", CancellationToken.None);
        Assert.False(r.Success);
        Assert.Equal(1, h.Calls);
    }

    [Fact]
    public async Task Download_500_RetriesThenFails()
    {
        var h = new StubHandler();
        for (int i = 0; i < 3; i++) h.Responses.Enqueue(() => new HttpResponseMessage(HttpStatusCode.InternalServerError));
        var r = await Make(h).DownloadAsync(new Uri("https://cdn.fal.run/a.glb"), "model_glb", CancellationToken.None);
        Assert.False(r.Success);
        Assert.Equal(3, h.Calls);
    }

    [Fact]
    public async Task Download_Cancellation_NoRetry()
    {
        var h = new StubHandler();
        using var cts = new CancellationTokenSource();
        cts.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Make(h).DownloadAsync(new Uri("https://cdn.fal.run/a.glb"), "model_glb", cts.Token));
        Assert.Equal(0, h.Calls);
    }
}
