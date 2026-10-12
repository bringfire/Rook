using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Fal;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Image.Jobs;

namespace Rook.Tests.Services.Vision.Image
{
    internal sealed record RecordedHttpRequest(Uri Uri, string Method, string? Body);
    internal sealed class HeldImageFallbackResponse : IDisposable
    {
        private readonly TaskCompletionSource<bool> _entered = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource<bool> _release = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private int _requests;
        public HeldImageFallbackResponse(ImageFallbackHttpHandler handler)
        {
            var original = handler.OnSendAsync ?? throw new InvalidOperationException("Configure the transport before holding it.");
            handler.OnSendAsync = async (request, ct) =>
            {
                if (Interlocked.Increment(ref _requests) == 1)
                {
                    _entered.TrySetResult(true);
                    await _release.Task.ConfigureAwait(false);
                }
                return await original(request, ct).ConfigureAwait(false);
            };
        }
        public Task Entered => _entered.Task;
        public void Release() => _release.TrySetResult(true);
        public void Dispose() => Release();
    }
    internal sealed class ImageFallbackHttpHandler : HttpMessageHandler
    {
        private readonly ConcurrentQueue<RecordedHttpRequest> _requests = new();
        public IReadOnlyList<RecordedHttpRequest> Requests => _requests.ToArray();
        public Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>>? OnSendAsync { get; set; }
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            var body = request.Content == null ? null : await request.Content.ReadAsStringAsync();
            _requests.Enqueue(new(request.RequestUri!, request.Method.Method, body));
            if (OnSendAsync == null) throw new InvalidOperationException("Unexpected HTTP request: " + request.RequestUri);
            return await OnSendAsync(request, ct);
        }
    }
    internal sealed class ImageFallbackFixture : IDisposable
    {
        public static readonly byte[] Png = Convert.FromBase64String(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2ioAAAAASUVORK5CYII=");
        public readonly string Root = Path.Combine(Path.GetTempPath(), "rook-fallback-" + Guid.NewGuid().ToString("N"));
        public string? GeminiKey { get; set; }
        public string? FalKey { get; set; }
        public ArtifactStore Store { get; }
        public DefaultImageProviderRegistry Registry { get; }
        public ImageSubmissionExecutor Executor { get; }
        public IReadOnlyDictionary<MediaRef, ResolvedMedia> Media { get; }
        public IReadOnlyList<Guid> ParentArtifactIds { get; }
        public ImageFallbackHttpHandler GoogleHttp { get; } = new();
        public ImageFallbackHttpHandler FalHttp { get; } = new();
        public ImageFallbackHttpHandler DownloadHttp { get; } = new();
        public ImageFallbackFixture(string? geminiKey = "fake-gemini", string? falKey = "fake-fal")
        {
            GeminiKey = geminiKey; FalKey = falKey;
            Store = new ArtifactStore(Path.Combine(Root, "artifacts"));
            var source = Store.Create("captured_viewport", new[] { new BlobInput("image", Png, "png") });
            var reference = Store.Create("captured_viewport", new[] { new BlobInput("image", Png, "png") });
            var s = MediaRef.ForArtifact(source.Id, ImageMediaRoles.InputImage);
            var r = MediaRef.ForArtifact(reference.Id, ImageMediaRoles.ReferenceImage);
            Media = new Dictionary<MediaRef, ResolvedMedia> { [s] = new(Png, "image/png"), [r] = new(Png, "image/png") };
            ParentArtifactIds = new[] { source.Id, reference.Id };
            Registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
            {
                new GeminiImageProviderRegistration(new GeminiImageProvider(() => GeminiKey, new HttpClient(GoogleHttp))),
                new FalImageProviderRegistration(new FalImageProvider(() => FalKey, new FalApiClient(new HttpClient(FalHttp))))
            });
            Executor = new ImageSubmissionExecutor(Registry);
            GoogleHttp.OnSendAsync = (_, _) => Task.FromResult(Json(200,
                "{\"candidates\":[{\"content\":{\"parts\":[{\"inlineData\":{\"mimeType\":\"image/png\",\"data\":\"" +
                Convert.ToBase64String(Png) + "\"}}]}}]}"));
            FalHttp.OnSendAsync = (_, _) => Task.FromResult(Json(200,
                "{\"images\":[{\"url\":\"https://fal.media/result.png\",\"content_type\":\"image/png\"}]}"));
            DownloadHttp.OnSendAsync = (_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
                { Content = new ByteArrayContent(Png) });
        }
        public static HttpResponseMessage Json(int status, string body) =>
            new((HttpStatusCode)status) { Content = new StringContent(body, Encoding.UTF8, "application/json") };
        public ImageGenerationRequest Request(string model, string resolution = "1K", string aspectRatio = "") =>
            new(model, "private test prompt", resolution, aspectRatio, 1,
                new[] { MediaRef.ForArtifact(ParentArtifactIds[1], ImageMediaRoles.ReferenceImage) },
                model.StartsWith("fal-", StringComparison.Ordinal) ? new FalImageOptions() : new GeminiImageOptions());
        public ImageJobStartRequest Start(string model) => new(Request(model), Media, ParentArtifactIds);
        public HeldImageFallbackResponse HoldNextResponse(ImageFallbackHttpHandler handler) => new(handler);
        public void Dispose()
        {
            GoogleHttp.Dispose(); FalHttp.Dispose(); DownloadHttp.Dispose();
            if (Directory.Exists(Root)) Directory.Delete(Root, true);
        }
    }
}
