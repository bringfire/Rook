using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Framing;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoFramingPreparationTests
    {
        [Fact]
        public async Task Preview_BothVariantsInterpolationAndNoProviderAccess()
        {
            string root = Path.Combine(Path.GetTempPath(), "rook-preparation-test-" + Guid.NewGuid().ToString("N"));
            try
            {
                var store = new ArtifactStore(root);
                var artifact = store.Create("captured_viewport", new[] { new BlobInput("image", File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("rgb-1166x912.png")), "png") });
                var reference = MediaRef.ForArtifact(artifact.Id, "image");
                var resources = new VideoPreparationResources(); using var cache = new VideoFramingCache(); var renderer = new RecordingRenderer();
                var service = new VideoFramingPreparationService(new ArtifactOnlyVideoMediaResolver(store, resources), cache, renderer, resources);
                var request = new VideoFramingPreviewRequest("veo-3.1-generate-preview", VideoMode.Interp, new[] { new VideoFramingSourceSlot("start_frame", reference), new VideoFramingSourceSlot("end_frame", reference) }, "720p", "16:9");
                var result = await service.PreviewAsync(request, CancellationToken.None);
                Assert.Null(result.Error); Assert.True(result.Fit!.Success); Assert.True(result.Fill!.Success);
                Assert.Equal(new[] { "start_frame", "end_frame" }, System.Linq.Enumerable.Select(result.Fit.Slots, s => s.Role));
                Assert.Equal(2, renderer.Calls); // repeated ref shares storage/render while preserving positions
                Assert.Equal(result.Fit.Slots[0].PreviewId, result.Fit.Slots[1].PreviewId);
                var again = await service.PreviewAsync(request, CancellationToken.None); Assert.Equal(2, renderer.Calls);
                Assert.Equal(result.Fit.Slots[0].Sha256, again.Fit!.Slots[0].Sha256);
                Assert.Equal(0, resources.ActiveBundles);
            }
            finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
        }
        [Fact]
        public async Task Preview_ExtremeFillFailureKeepsFitUsable_AndInputUnchanged()
        {
            string root = Path.Combine(Path.GetTempPath(), "rook-preparation-test-" + Guid.NewGuid().ToString("N"));
            try
            {
                var store = new ArtifactStore(root); var bytes = File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("extreme-16384x720.png"));
                var artifact = store.Create("captured_viewport", new[] { new BlobInput("image", bytes, "png") });
                using var cache = new VideoFramingCache(); var renderer = new RecordingRenderer(); var resources = new VideoPreparationResources();
                var service = new VideoFramingPreparationService(new ArtifactOnlyVideoMediaResolver(store, resources), cache, renderer, resources);
                var result = await service.PreviewAsync(new("veo-3.1-generate-preview", VideoMode.I2V, new[] { new VideoFramingSourceSlot("start_frame", MediaRef.ForArtifact(artifact.Id, "image")) }, "4k", "9:16"), CancellationToken.None);
                Assert.True(result.Fit!.Success); Assert.False(result.Fill!.Success); Assert.Equal(1, renderer.Calls);
                Assert.Equal("render_limits_exceeded", result.Fill.Error!.ProviderDetail!["preparation_detail"]!.GetValue<string>());
                Assert.Equal(bytes, File.ReadAllBytes(store.GetBlobAbsolutePath(artifact.Id, "image")));
            }
            finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
        }
        private sealed class RecordingRenderer : IVideoSourceRenderer
        {
            public int Calls;
            public string? VerifyProfile() => null;
            public Task<VideoPreparedSourceResult> RenderAsync(VideoFrozenBuffer source, VideoStillImageInfo info, VideoFramingRecipe recipe, VideoPreparationLease lease, CancellationToken ct)
            {
                Calls++; return Task.FromResult(new VideoPreparedSourceResult(new VideoPreparedSource(VideoFrozenBuffer.CopyOf(new byte[] { (byte)recipe.Mode, 2, 3 }, lease.Buffers), recipe, 1), null));
            }
        }
        [Fact]
        public async Task Cache_ExpiredIdsRegenerateIdenticalContent_AndSourceReplacementIsRead()
        {
            string root = Path.Combine(Path.GetTempPath(), "rook-preparation-test-" + Guid.NewGuid().ToString("N"));
            try
            {
                var store = new ArtifactStore(root); var a = store.Create("captured_viewport", new[] { new BlobInput("image", File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("matching.png")), "png") });
                var now = DateTimeOffset.UtcNow; using var cache = new VideoFramingCache(() => now); var renderer = new RecordingRenderer();
                var service = new VideoFramingPreparationService(new ArtifactOnlyVideoMediaResolver(store), cache, renderer);
                var request = new VideoFramingPreviewRequest("veo-3.1-generate-preview", VideoMode.I2V, new[] { new VideoFramingSourceSlot("start_frame", MediaRef.ForArtifact(a.Id, "image")) }, "720p", "16:9");
                var first = await service.PreviewAsync(request, default); now += TimeSpan.FromMinutes(31); cache.Sweep();
                var second = await service.PreviewAsync(request, default);
                Assert.Equal(first.Fit!.Slots[0].Sha256, second.Fit!.Slots[0].Sha256);
                Assert.NotEqual(first.Fit.Slots[0].PreviewId, second.Fit.Slots[0].PreviewId); Assert.Equal(4, renderer.Calls);
                Assert.Null(cache.TryOpenPreview(first.Fit.Slots[0].PreviewId, "image"));
                File.WriteAllBytes(store.GetBlobAbsolutePath(a.Id, "image"), File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("square.png")));
                await service.PreviewAsync(request, default); Assert.Equal(6, renderer.Calls);
            }
            finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
        }
        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task Preview_AnimationAndOversizedOriginalNeverStartRenderer(bool oversized)
        {
            string root = Path.Combine(Path.GetTempPath(), "rook-preparation-test-" + Guid.NewGuid().ToString("N"));
            try
            {
                var store = new ArtifactStore(root); var artifact = store.Create("captured_viewport", new[] { new BlobInput("image", File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("animated.png")), "png") });
                if (oversized) { using var file = new FileStream(store.GetBlobAbsolutePath(artifact.Id, "image"), FileMode.Open, FileAccess.Write); file.SetLength(33_554_433); }
                using var cache = new VideoFramingCache(); var renderer = new RecordingRenderer(); var resources = new VideoPreparationResources();
                var service = new VideoFramingPreparationService(new ArtifactOnlyVideoMediaResolver(store, resources), cache, renderer, resources);
                var result = await service.PreviewAsync(new("veo-3.1-generate-preview", VideoMode.I2V, new[] { new VideoFramingSourceSlot("start_frame", MediaRef.ForArtifact(artifact.Id, "image")) }, "720p", "16:9"), default);
                Assert.Equal(oversized ? "source_input_too_large" : "source_animation_unsupported", (result.Error ?? result.Fit!.Error)!.ProviderErrorCode);
                Assert.Equal(0, renderer.Calls); Assert.Equal(0, resources.ActiveBundles); Assert.Equal(0, cache.RetainedBytes);
            }
            finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
        }
    }
}
