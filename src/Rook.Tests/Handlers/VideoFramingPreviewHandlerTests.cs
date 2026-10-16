using System;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook;
using Rook.Handlers;
using Rook.Services.Vision.Video;
using Rook.Tests.Services.Vision.Video;
using Rook.UI.Vision;
using Rook.Services.Vision.Video.Framing;
using Rook.Artifacts;
using System.Collections.Generic;
using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public sealed class VideoFramingPreviewHandlerTests
    {
        [Fact]
        public async Task Blob_PrivatePreviewDoesNotLoosenVideoFence_AndExpiredIdsReturn404()
        {
            using var rig = new VideoFramingQuoteTests.Rig();
            using var manager = new VideoJobManager(rig.Coordinator.Registry, new ArtifactOnlyVideoMediaResolver(rig.Store), new FakeVideoJobLedger(), new VideoCostEstimator(), rig.Store);
            var handler = new VideoOpHandler(manager, rig.Coordinator.Registry, new VideoCostEstimator(), rig.Preparation);
            var preview = await rig.Preparation.PreviewAsync(new(rig.Intent.Request.Model, VideoMode.I2V,
                new[] { new VideoFramingSourceSlot("start_frame", rig.Source) }, "1080p", "16:9"), default);
            var slot = preview.Fit!.Slots[0];
            using var surface = new VisionWebSurface(new VisionHandler(), handler, null, null, rig.Store, _ => false);
            var uri = new Uri($"https://app.rook.invalid/blob/{slot.PreviewId:D}/image");
            var resource = surface.ResolveVirtualResourceForTest(uri)!;
            Assert.Equal(200, resource.StatusCode); Assert.Equal("image/png", resource.ContentType); Assert.False(resource.Content.CanWrite);
            Assert.Contains("Cache-Control: no-store", resource.ExtraHeaders);
            using var body = new MemoryStream(); resource.Content.CopyTo(body);
            using var bytes = VideoFrozenBuffer.CopyOf(body.ToArray(), new VideoBufferBudget()); Assert.Equal(slot.Sha256, bytes.Sha256);
            Assert.Single(rig.Store.List());
            var video = rig.Store.Create("generated_video", new[] { new BlobInput("video", new byte[] { 1 }, "mp4"), new BlobInput("start_frame", new byte[] { 2 }, "png") },
                metadata: new Dictionary<string, JsonNode?> { ["video_job_id"] = JsonValue.Create(Guid.NewGuid().ToString("D")) },
                flags: new Dictionary<string, JsonNode?> { ["video_publication"] = JsonValue.Create("provisional") });
            foreach (string role in new[] { "video", "start_frame" })
            { var rejected = surface.ResolveVirtualResourceForTest(new Uri($"https://app.rook.invalid/blob/{video.Id:D}/{role}"))!; Assert.Equal(404, rejected.StatusCode); rejected.Content.Dispose(); }
            rig.Now += TimeSpan.FromMinutes(31); rig.Cache.Sweep(); Assert.True(rig.Cache.RetainedBytes > 0);
            resource.Content.Dispose(); rig.Now += TimeSpan.FromMinutes(31); rig.Cache.Sweep();
            var expired = surface.ResolveVirtualResourceForTest(uri)!; Assert.Equal(404, expired.StatusCode); expired.Content.Dispose();
            Assert.Equal(2, rig.Store.List().Count);
        }
        [Fact]
        public async Task PreviewHandler_NoCredentialsAndNoGenerationSideEffects()
        {
            using var rig = new VideoFramingQuoteTests.Rig(secrets: new VideoRouteQuoteTests.Secrets { Google = null, Fal = null });
            using var manager = new VideoJobManager(rig.Coordinator.Registry, new ArtifactOnlyVideoMediaResolver(rig.Store), new FakeVideoJobLedger(), new VideoCostEstimator(), rig.Store);
            var handler = new VideoOpHandler(manager, rig.Coordinator.Registry, new VideoCostEstimator(), rig.Preparation);
            var response = await handler.DispatchAsync(new JsonObject { ["op"] = VideoOpHandler.OpPreviewFraming, ["model"] = rig.Intent.Request.Model, ["mode"] = "interp", ["resolution"] = "1080p", ["aspect_ratio"] = "16:9",
                ["start_frame"] = new JsonObject { ["kind"] = "artifact_id", ["artifact_id"] = rig.Source.ArtifactId!.Value.ToString("D"), ["role"] = "image" },
                ["end_frame"] = new JsonObject { ["kind"] = "artifact_id", ["artifact_id"] = rig.Source.ArtifactId!.Value.ToString("D"), ["role"] = "image" } }.ToJsonString());
            Assert.True(response.Success);
            var data = JsonNode.Parse(JsonSerializer.Serialize(response.Data))!;
            Assert.True(data["fit"]!["success"]!.GetValue<bool>()); Assert.Equal(2, data["fit"]!["slots"]!.AsArray().Count);
            Assert.Equal("start_frame", data["fit"]!["slots"]![0]!["role"]!.GetValue<string>());
            Assert.Equal("end_frame", data["fit"]!["slots"]![1]!["role"]!.GetValue<string>());
            Assert.Single(rig.Store.List()); Assert.Equal(0, rig.Resources.ActiveBundles);
        }
        [Fact]
        public async Task PreviewSession_SupersededAndCancelledRevisionsNeverRestartWork()
        {
            using var session = new VideoFramingPreviewSession(); var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var first = session.RunAsync(1, async ct => { entered.SetResult(true); await Task.Delay(Timeout.Infinite, ct); return new ApiResponse { Success = true }; }, default);
            await entered.Task;
            var current = await session.RunAsync(2, _ => Task.FromResult(new ApiResponse { Success = true }), default);
            Assert.True(current.Success); Assert.Equal(409, (await first).HttpStatus);
            int starts = 0; session.Cancel(3);
            var late = await session.RunAsync(2, _ => { starts++; return Task.FromResult(new ApiResponse { Success = true }); }, default);
            Assert.Equal(409, late.HttpStatus); Assert.Equal(0, starts);
        }
    }
}
