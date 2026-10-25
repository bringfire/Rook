using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalMediaPreparationTests
    {
        internal static readonly byte[] Png = { 137, 80, 78, 71, 13, 10, 26, 10, 1 };
        [Fact]
        public async Task Snapshots_own_bytes_and_preserve_order()
        {
            using var files = MediaFiles("data_uri");
            var first = MediaRef.ForArtifact(Guid.NewGuid(), "thumbnail"); var second = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = Request(files, new[] { new FalMediaInput("reference_image", 1, second), new FalMediaInput("reference_image", 0, first) });
            var bytes = (byte[])Png.Clone();
            using var snapshot = FalMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [first] = new(bytes, "image/png"), [second] = new(Png, "image/png") });
            var firstSlot = Assert.Single(snapshot.Slots, s => s.Role == "reference_image" && s.Ordinal == 0);
            var digest = firstSlot.Sha256; bytes[0] = 0; firstSlot.CopyBytes()[0] = 0;
            Assert.Equal(digest, firstSlot.Sha256); Assert.Equal(Png, firstSlot.CopyBytes());
            Assert.Equal(first, firstSlot.Source); Assert.Equal(0, firstSlot.Ordinal);
            var prepared = await new FalMediaPreparation(new FalApiClient(), () => "key").PrepareAsync(request, snapshot, CancellationToken.None);
            Assert.Equal("data:image/png;base64,iVBORw0KGgoB", prepared[0].TransportValue);
            Assert.Equal(new[] { 0, 1 }, prepared.Where(p => p.Role == "reference_image").Select(p => p.Ordinal));
        }
        [Theory]
        [InlineData("missing")]
        [InlineData("mime")]
        [InlineData("bytes")]
        [InlineData("limit")]
        [InlineData("extra")]
        public async Task Invalid_media_never_uploads(string invalid)
        {
            using var files = MediaFiles("fal_upload");
            if (invalid == "limit") { files.Operation["media"]![0]!["max_bytes"] = 8; files.Save(); }
            var source = MediaRef.ForArtifact(Guid.NewGuid(), "image"); var request = Request(files, new[] { new FalMediaInput("reference_image", 0, source) });
            var media = new Dictionary<MediaRef, ResolvedMedia>();
            if (invalid != "missing") media[source] = new ResolvedMedia(invalid == "bytes" ? new byte[] { 1 } : Png, invalid == "mime" ? "image/jpeg" : "image/png");
            if (invalid == "extra") media[MediaRef.ForArtifact(Guid.NewGuid(), "image")] = new ResolvedMedia(Png, "image/png");
            using var snapshot = FalMediaSnapshot.Capture(request, media);
            var handler = new UploadHandler(); using var http = new HttpClient(handler);
            var executor = new FalConfiguredExecutor(new FalApiClient(http), () => "key");
            Assert.IsType<FailedSubmitOutcome>(await executor.SubmitAsync(request, snapshot, new RecordingObserver(new List<string>(), () => null), CancellationToken.None));
            Assert.Equal(0, handler.Calls);
        }
        [Fact]
        public async Task Unconfirmed_sources_never_upload()
        {
            using var files = MediaFiles("fal_upload"); var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = Request(files, new[] { new FalMediaInput("reference_image", 0, source) });
            using var snapshot = FalMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [source] = new(Png, "image/png") });
            var handler = new UploadHandler(); using var http = new HttpClient(handler);
            var observer = new RecordingObserver(new List<string>(), () => null) { DeniedPhase = "beforeUpload" };
            Assert.Equal(SubmissionDisposition.NotAccepted, Assert.IsType<FailedSubmitOutcome>(await new FalConfiguredExecutor(new FalApiClient(http), () => "key").SubmitAsync(request, snapshot, observer, CancellationToken.None)).Disposition);
            Assert.Equal(0, handler.Calls);
        }
        [Fact]
        public async Task A_late_invalid_reference_prevents_uploading_earlier_valid_sources()
        {
            using var files = MediaFiles("fal_upload"); var first = MediaRef.ForArtifact(Guid.NewGuid(), "image"); var bad = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = Request(files, new[] { new FalMediaInput("reference_image", 0, first), new FalMediaInput("reference_image", 1, bad) });
            using var snapshot = FalMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [first] = new(Png, "image/png"), [bad] = new(new byte[] { 0 }, "image/png") });
            var handler = new UploadHandler(); using var http = new HttpClient(handler);
            Assert.IsType<FailedSubmitOutcome>(await new FalConfiguredExecutor(new FalApiClient(http), () => "key").SubmitAsync(request, snapshot, new RecordingObserver(new List<string>(), () => null), CancellationToken.None));
            Assert.Equal(0, handler.Calls); Assert.Empty(snapshot.Slots);
        }
        [Fact]
        public async Task Disposed_or_different_operation_snapshots_are_rejected()
        {
            using var files = MediaFiles("data_uri"); var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = Request(files, new[] { new FalMediaInput("reference_image", 0, source) });
            using var snapshot = FalMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [source] = new(Png, "image/png") });
            using var other = new ConfiguredRun();
            Assert.IsType<FailedSubmitOutcome>(await other.Executor.SubmitAsync(other.Request, snapshot, other.Observer, CancellationToken.None));
            snapshot.Dispose();
            Assert.Throws<ObjectDisposedException>(() => snapshot.Slots[0].CopyBytes());
            Assert.IsType<FailedSubmitOutcome>(await other.Executor.SubmitAsync(request, snapshot, other.Observer, CancellationToken.None));
            Assert.Empty(other.Events);
        }
        [Fact]
        public async Task Upload_timeout_is_known_not_dispatched()
        {
            using var files = MediaFiles("fal_upload"); var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = Request(files, new[] { new FalMediaInput("reference_image", 0, source) });
            using var snapshot = FalMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [source] = new(Png, "image/png") });
            var handler = new UploadHandler { Timeout = true }; using var http = new HttpClient(handler);
            var events = new List<string>();
            var failed = Assert.IsType<FailedSubmitOutcome>(await new FalConfiguredExecutor(new FalApiClient(http), () => "key").SubmitAsync(request, snapshot, new RecordingObserver(events, () => null), CancellationToken.None));
            Assert.Equal(SubmissionDisposition.NotAccepted, failed.Disposition); Assert.Equal(new[] { "beforeUpload" }, events); Assert.Equal(1, handler.Calls);
        }
        [Fact]
        public async Task Fal_CDN_profile_uploads_copied_original_bytes()
        {
            using var files = MediaFiles("fal_upload"); var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = Request(files, new[] { new FalMediaInput("reference_image", 0, source) });
            using var snapshot = FalMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [source] = new(Png, "image/png") });
            var handler = new UploadHandler(); using var http = new HttpClient(handler);
            var prepared = await new FalMediaPreparation(new FalApiClient(http), () => "key").PrepareAsync(request, snapshot, CancellationToken.None);
            Assert.All(prepared, p => Assert.Equal("https://v3.fal.media/files/source.png", p.TransportValue)); Assert.Equal(Png, handler.Bytes); Assert.Equal(2, handler.Calls);
        }
        internal static CatalogFiles MediaFiles(string transport)
        {
            var files = new CatalogFiles(); files.Operation["operation_id"] = "image_to_image";
            files.Operation["media"] = JsonNode.Parse("[{\"role\":\"primary_image\",\"min_count\":1,\"max_count\":1,\"ordered\":false,\"preparation\":\"validated_original\",\"transport\":\"" + transport + "\",\"payload\":{\"pointer\":\"/image\",\"conversion\":\"identity\"}},{\"role\":\"reference_image\",\"min_count\":0,\"max_count\":4,\"ordered\":true,\"preparation\":\"validated_original\",\"transport\":\"" + transport + "\",\"payload\":{\"pointer\":\"/images\",\"conversion\":\"ordered_array\"}}]"); files.Save(); return files;
        }
        internal static FalNormalizedRequest Request(CatalogFiles files, FalMediaInput[] media)
        { var result = new FalModelNormalizer().Normalize(FalModelNormalizerTests.Binding(files), new FalModelInput(new JsonObject { ["prompt"] = "draw" }, media: new[] { new FalMediaInput("primary_image", 0, media[0].Source) }.Concat(media).ToArray())); Assert.True(result.Success); return result.Request!; }
        private sealed class UploadHandler : HttpMessageHandler
        {
            internal int Calls; internal byte[]? Bytes;
            internal bool Timeout;
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
            {
                Calls++;
                if (Timeout) throw new TaskCanceledException();
                if (request.Method == HttpMethod.Put) Bytes = await request.Content!.ReadAsByteArrayAsync();
                return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{\"upload_url\":\"https://upload.example/signed\",\"file_url\":\"https://v3.fal.media/files/source.png\"}") };
            }
        }
    }
}
