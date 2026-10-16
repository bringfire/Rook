using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Rook.Services.Vision.Video.Framing;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public sealed class LegacyFalSourceValidationTests
    {
        [Theory]
        [InlineData("empty-idat.png", "i2v")]
        [InlineData("empty-scan.jpg", "i2v")]
        [InlineData("empty-vp8l.webp", "i2v")]
        [InlineData("short-rows-360.png", "i2v")]
        [InlineData("short-rows-719.png", "i2v")]
        [InlineData("empty-idat.png", "interp")]
        [InlineData("empty-scan.jpg", "interp")]
        [InlineData("empty-vp8l.webp", "interp")]
        [InlineData("short-rows-360.png", "interp")]
        [InlineData("short-rows-719.png", "interp")]
        [InlineData("empty-idat.png", "reference")]
        [InlineData("empty-scan.jpg", "reference")]
        [InlineData("empty-vp8l.webp", "reference")]
        [InlineData("short-rows-360.png", "reference")]
        [InlineData("short-rows-719.png", "reference")]
        public async Task InvalidCompressedPixelsNeverReachUploadOrGeneration(string file, string mode)
        {
            var first = MediaRef.ForArtifact(Guid.NewGuid(), "image"); var bad = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = TestVideoFixtures.DefaultT2vRequest(model: "fal-ai/veo3.1", mode: mode == "reference" ? VideoMode.T2V : mode == "interp" ? VideoMode.Interp : VideoMode.I2V,
                startFrame: mode == "reference" ? null : mode == "interp" ? first : bad, endFrame: mode == "interp" ? bad : null,
                referenceFrames: mode == "reference" ? new[] { first, bad } : null).With(options: new FalVeoOptions());
            string mime = file.EndsWith("png") ? "image/png" : file.EndsWith("jpg") ? "image/jpeg" : "image/webp";
            var bytes = File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("legacy-validation/" + file));
            using var snapshot = VideoPreparedMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia> {
                [first] = new(File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("matching.png")), "image/png"), [bad] = new(bytes, mime) });
            var binding = FalVeoCompatibilityTests.ActiveCatalog().Resolve(request, DateTimeOffset.UtcNow).Binding!;
            Assert.Null(FalVeoCompatibility.ValidateMetadata(VideoRequestIntent.Normalize(request, new()), binding, snapshot)); // Headers alone are deliberately insufficient.
            int uploads = 0, generations = 0, intent = 0;
            var http = new FalVeoQueueAdapterTests.Http { Send = message => {
                if (message.RequestUri!.Host == "rest.fal.ai") { uploads++; return Task.FromResult(FalVeoQueueAdapterTests.Http.Json(200, "{\"upload_url\":\"https://v3.fal.media/upload/source\",\"file_url\":\"https://v3.fal.media/files/source.png\"}")); }
                if (message.RequestUri.Host == "queue.fal.run") generations++;
                return Task.FromResult(FalVeoQueueAdapterTests.Http.Json(200, FalVeoQueueAdapterTests.Accepted));
            } };
            var client = new FalApiClient(new HttpClient(http));
            var adapter = new FalVeoQueueAdapter(() => "synthetic", client, FalVeoCompatibilityTests.ActiveCatalog(), new FalSourceFrameTransport(client));
            var resources = new VideoPreparationResources();
            using (var phase = await resources.AcquireAsync(default))
            {
                var result = await adapter.SubmitPreparedAsync(request, snapshot, () => intent++, default, phase);
                Assert.Equal(0, uploads); Assert.Equal(0, generations); Assert.Equal(0, intent);
                var failure = Assert.IsType<FailedSubmitOutcome>(result);
                Assert.Equal(mode == "interp" ? "end_frame" : mode == "reference" ? "reference_frames[1]" : "start_frame", failure.Error.Field);
                Assert.Equal("source_preparation_failed", failure.Error.ProviderErrorCode);
                Assert.Equal(0, phase.Buffers.ReservedBytes);
            }
            Assert.Equal(0, resources.ActiveBundles);
        }

        [Fact]
        public async Task LegacyApngUploadsOriginalBytesAndPreservesRepeatedRoles()
        {
            var bundled = Rook.Services.Vision.Video.Extraction.FfmpegBundledBinaryLocator.GetInstalledFfmpegPath();
            Assert.True(File.Exists(bundled), bundled);
            var reference = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var bytes = File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("legacy-validation/legacy-single.apng.png"));
            var request = TestVideoFixtures.DefaultT2vRequest(model: "fal-ai/veo3.1", mode: VideoMode.Interp, startFrame: reference, endFrame: reference).With(options: new FalVeoOptions());
            using var snapshot = VideoPreparedMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [reference] = new(bytes, "image/png") });
            int uploads = 0, generations = 0;
            var http = new FalVeoQueueAdapterTests.Http { Send = async message => {
                if (message.RequestUri!.Host == "rest.fal.ai") return FalVeoQueueAdapterTests.Http.Json(200, "{\"upload_url\":\"https://v3.fal.media/upload/source\",\"file_url\":\"https://v3.fal.media/files/source.png\"}");
                if (message.Method == HttpMethod.Put) { uploads++; Assert.Equal(bytes, await message.Content!.ReadAsByteArrayAsync()); return FalVeoQueueAdapterTests.Http.Json(200, "{}"); }
                generations++; return FalVeoQueueAdapterTests.Http.Json(200, FalVeoQueueAdapterTests.Accepted);
            } };
            var client = new FalApiClient(new HttpClient(http));
            var adapter = new FalVeoQueueAdapter(() => "synthetic", client, FalVeoCompatibilityTests.ActiveCatalog(), new FalSourceFrameTransport(client));
            using var phase = await new VideoPreparationResources().AcquireAsync(default);
            var outcome = await adapter.SubmitPreparedAsync(request, snapshot, () => { }, default, phase);
            Assert.True(outcome is QueuedSubmitOutcome, System.Text.Json.JsonSerializer.Serialize((outcome as FailedSubmitOutcome)?.Error));
            Assert.Equal(1, uploads); Assert.Equal(1, generations);
            Assert.Equal(bytes, snapshot.Slots[0].CopyBytes()); Assert.Equal(bytes, snapshot.Slots[1].CopyBytes());
        }
    }
}
