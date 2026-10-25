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
using Rook.Services.Vision.Video.Framing;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalMediaPreparationTests
    {
        private readonly VideoPreparationResources _resources = new();
        private FalMediaSnapshot Capture(FalNormalizedRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> media) => FalMediaSnapshot.Capture(request, media, _resources);
        internal static readonly byte[] Png = { 137, 80, 78, 71, 13, 10, 26, 10, 1 };
        [Fact]
        public async Task Encoded_bundle_is_rejected_before_any_CDN_upload()
        {
            using var files = MediaFiles("data_uri");
            files.Operation["media"]![0]!["transport"] = "fal_upload"; files.Save();
            var sources = Enumerable.Range(0, 3).Select(_ => MediaRef.ForArtifact(Guid.NewGuid(), "image")).ToArray();
            var request = Request(files, sources.Select((s, i) => new FalMediaInput("reference_image", i, s)).ToArray());
            var bytes = new byte[4 * 1024 * 1024]; Png.CopyTo(bytes, 0);
            using var snapshot = Capture(request, sources.ToDictionary(s => s, _ => new ResolvedMedia(bytes, "image/png")));
            var handler = new UploadHandler(); using var http = new HttpClient(handler);
            var error = await Assert.ThrowsAsync<FalMediaPreparationException>(() => new FalMediaPreparation(new FalApiClient(http), () => "key").PrepareAsync(request, snapshot, CancellationToken.None));
            Assert.Equal("media_payload_limit", error.Error.ProviderErrorCode); Assert.Equal(0, handler.Calls);
        }
        [Fact]
        public void Retained_snapshots_hold_admitted_capacity_until_disposed()
        {
            using var run = new ConfiguredRun();
            var media = new Dictionary<MediaRef, ResolvedMedia>();
            using var first = Capture(run.Request, media);
            using var second = Capture(run.Request, media);
            Assert.Equal(2, _resources.ActiveBundles);
            using var denied = Capture(run.Request, media);
            Assert.Equal("media_preparation_busy", denied.ValidationError!.ProviderErrorCode);
            first.Dispose();
            using var replacement = Capture(run.Request, media);
            Assert.Null(replacement.ValidationError);
        }
        [Fact]
        public async Task Concurrent_capture_admits_only_the_bounded_number_of_retained_snapshots()
        {
            using var files = MediaFiles("data_uri"); var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = Request(files, new[] { new FalMediaInput("reference_image", 0, source) });
            var media = new Dictionary<MediaRef, ResolvedMedia> { [source] = new(Png, "image/png") };
            var snapshots = await Task.WhenAll(Enumerable.Range(0, 12).Select(_ => Task.Run(() => Capture(request, media))));
            try
            {
                Assert.Equal(2, snapshots.Count(s => s.ValidationError == null));
                Assert.Equal(2, _resources.ActiveBundles);
                Assert.All(snapshots.Where(s => s.ValidationError != null), s => { Assert.True(s.ValidationError!.Retryable); Assert.Equal("media_preparation_busy", s.ValidationError.ProviderErrorCode); Assert.Empty(s.Slots); });
                Assert.All(snapshots.Where(s => s.ValidationError == null), s => Assert.True(s.Phase.Buffers.ReservedBytes > 0));
            }
            finally { foreach (var snapshot in snapshots) snapshot.Dispose(); }
            Assert.Equal(0, _resources.ActiveBundles);
            using var replacement = Capture(request, media); Assert.Null(replacement.ValidationError);
        }
        [Fact]
        public void Failed_capture_releases_its_nonblocking_admission_and_partial_buffers()
        {
            using var files = MediaFiles("data_uri"); var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = Request(files, new[] { new FalMediaInput("reference_image", 0, source) });
            var media = new Dictionary<MediaRef, ResolvedMedia> { [source] = new(Png, "image/png") };
            var tiny = new VideoPreparationResources(maxBundles: 1, transientLimit: 65540);
            using var denied = FalMediaSnapshot.Capture(request, media, tiny);
            Assert.Equal("media_preparation_busy", denied.ValidationError!.ProviderErrorCode); Assert.True(denied.ValidationError.Retryable);
            Assert.Equal(0, tiny.ActiveBundles); Assert.Empty(denied.Slots);
            Assert.True(tiny.TryAcquire(out var replacement)); replacement!.Dispose(); Assert.Equal(0, tiny.ActiveBundles);
        }
        [Theory]
        [InlineData(0, false)]
        [InlineData(251, true)]
        public async Task Data_URI_budget_accounts_for_JSON_escaped_base64(int fill, bool denied)
        {
            using var files = MediaFiles("data_uri"); var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = Request(files, new[] { new FalMediaInput("reference_image", 0, source) });
            var bytes = Enumerable.Repeat((byte)fill, 3 * 1024 * 1024).ToArray(); Png.CopyTo(bytes, 0);
            using var snapshot = Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [source] = new(bytes, "image/png") });
            var original = snapshot.Phase.Buffers.ReservedBytes;
            var preparation = new FalMediaPreparation(new FalApiClient(), () => "key");
            if (denied)
            {
                var failure = await Assert.ThrowsAsync<FalMediaPreparationException>(() => preparation.PrepareAsync(request, snapshot, CancellationToken.None));
                Assert.Equal("media_payload_limit", failure.Error.ProviderErrorCode); Assert.Equal(original, snapshot.Phase.Buffers.ReservedBytes);
            }
            else
            {
                var prepared = await preparation.PrepareAsync(request, snapshot, CancellationToken.None);
                Assert.Equal(2, prepared.Count); Assert.True(snapshot.Phase.Buffers.ReservedBytes > original);
                Assert.True(snapshot.Phase.Buffers.PeakReservedBytes <= 134_217_728);
            }
            snapshot.Dispose(); Assert.Equal(0, _resources.ActiveBundles);
        }
        [Theory]
        [InlineData("request")]
        [InlineData("options")]
        public async Task Oversized_common_or_option_controls_fail_preflight_before_upload(string scope)
        {
            using var files = MediaFiles("fal_upload");
            files.Operation["fields"]![0]!["max_length"] = 1048576;
            files.Operation["fields"]!.AsArray().Add(JsonNode.Parse("{\"key\":\"note\",\"scope\":\"options\",\"type\":\"string\",\"max_length\":1048576,\"label\":\"Note\",\"payload\":{\"pointer\":\"/note\",\"conversion\":\"identity\"}}")); files.Save();
            var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var controls = new JsonObject { ["prompt"] = scope == "request" ? new string('a', 1048576) : "draw" };
            var options = scope == "options" ? new JsonObject { ["note"] = new string('+', 1048576) } : new JsonObject();
            var normalized = new FalModelNormalizer().Normalize(FalModelNormalizerTests.Binding(files), new FalModelInput(controls, options, media: new[] { new FalMediaInput("primary_image", 0, source) }));
            Assert.True(normalized.Success); var request = normalized.Request!;
            using var snapshot = Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [source] = new(Png, "image/png") });
            var handler = new UploadHandler(); using var http = new HttpClient(handler);
            var failure = await Assert.ThrowsAsync<FalMediaPreparationException>(() => new FalMediaPreparation(new FalApiClient(http), () => "key").PrepareAsync(request, snapshot, CancellationToken.None));
            Assert.Equal("media_payload_limit", failure.Error.ProviderErrorCode); Assert.Equal(0, handler.Calls);
            Assert.Equal(9, snapshot.Phase.Buffers.ReservedBytes);
        }
        [Fact]
        public async Task CDN_URLs_must_fit_the_reserved_length_allowance()
        {
            using var files = MediaFiles("fal_upload"); var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = Request(files, new[] { new FalMediaInput("reference_image", 0, source) });
            using var snapshot = Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [source] = new(Png, "image/png") });
            var original = snapshot.Phase.Buffers.ReservedBytes;
            var handler = new UploadHandler { FileUrl = "https://v3.fal.media/files/" + new string('a', 4096) }; using var http = new HttpClient(handler);
            var failure = await Assert.ThrowsAsync<FalMediaPreparationException>(() => new FalMediaPreparation(new FalApiClient(http), () => "key").PrepareAsync(request, snapshot, CancellationToken.None));
            Assert.Equal("media_payload_limit", failure.Error.ProviderErrorCode); Assert.Equal(original, snapshot.Phase.Buffers.ReservedBytes);
            snapshot.Dispose(); Assert.Equal(0, _resources.ActiveBundles);
        }
        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task Preparation_failure_or_cancellation_releases_encoding_but_retains_caller_snapshot(bool cancel)
        {
            using var files = MediaFiles("fal_upload"); var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = Request(files, new[] { new FalMediaInput("reference_image", 0, source) });
            using var snapshot = Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [source] = new(Png, "image/png") });
            var original = snapshot.Phase.Buffers.ReservedBytes;
            using var stop = new CancellationTokenSource();
            var handler = new UploadHandler { Timeout = !cancel, Cancel = cancel ? stop : null }; using var http = new HttpClient(handler);
            var preparation = new FalMediaPreparation(new FalApiClient(http), () => "key");
            if (cancel) await Assert.ThrowsAnyAsync<OperationCanceledException>(() => preparation.PrepareAsync(request, snapshot, stop.Token));
            else await Assert.ThrowsAsync<FalApiException>(() => preparation.PrepareAsync(request, snapshot, stop.Token));
            Assert.Equal(original, snapshot.Phase.Buffers.ReservedBytes); Assert.Equal(1, _resources.ActiveBundles);
            snapshot.Dispose(); Assert.Equal(0, _resources.ActiveBundles);
        }
        [Fact]
        public async Task Snapshots_own_bytes_and_preserve_order()
        {
            using var files = MediaFiles("data_uri");
            var first = MediaRef.ForArtifact(Guid.NewGuid(), "thumbnail"); var second = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = Request(files, new[] { new FalMediaInput("reference_image", 1, second), new FalMediaInput("reference_image", 0, first) });
            var bytes = (byte[])Png.Clone();
            using var snapshot = Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [first] = new(bytes, "image/png"), [second] = new(Png, "image/png") });
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
            using var snapshot = Capture(request, media);
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
            using var snapshot = Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [source] = new(Png, "image/png") });
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
            using var snapshot = Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [first] = new(Png, "image/png"), [bad] = new(new byte[] { 0 }, "image/png") });
            var handler = new UploadHandler(); using var http = new HttpClient(handler);
            Assert.IsType<FailedSubmitOutcome>(await new FalConfiguredExecutor(new FalApiClient(http), () => "key").SubmitAsync(request, snapshot, new RecordingObserver(new List<string>(), () => null), CancellationToken.None));
            Assert.Equal(0, handler.Calls); Assert.Empty(snapshot.Slots);
        }
        [Fact]
        public async Task Disposed_or_different_operation_snapshots_are_rejected()
        {
            using var files = MediaFiles("data_uri"); var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = Request(files, new[] { new FalMediaInput("reference_image", 0, source) });
            using var snapshot = Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [source] = new(Png, "image/png") });
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
            using var snapshot = Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [source] = new(Png, "image/png") });
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
            using var snapshot = Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [source] = new(Png, "image/png") });
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
            internal CancellationTokenSource? Cancel;
            internal string FileUrl = "https://v3.fal.media/files/source.png";
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
            {
                Calls++;
                if (Cancel != null) { Cancel.Cancel(); throw new OperationCanceledException(Cancel.Token); }
                if (Timeout) throw new TaskCanceledException();
                if (request.Method == HttpMethod.Put) Bytes = await request.Content!.ReadAsByteArrayAsync();
                return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(new JsonObject { ["upload_url"] = "https://upload.example/signed", ["file_url"] = FileUrl }.ToJsonString()) };
            }
        }
    }
}
