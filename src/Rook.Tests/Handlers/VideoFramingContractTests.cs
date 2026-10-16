using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook.Handlers;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Framing;
using Rook.Tests.Services.Vision.Video;
using Xunit;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using System.IO;
using System.Linq;

namespace Rook.Tests.Handlers
{
    public sealed class VideoFramingContractTests
    {
        [Fact]
        public void Contract_FramingPersistsWhileLegacyJsonOmitsTheField()
        {
            using var rig = new VideoFalFallbackManagerTests.Rig();
            var request = VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(mode: VideoMode.I2V, startFrame: MediaRef.ForArtifact(Guid.NewGuid(), "image")), new JsonObject()).Request;
            Assert.True(rig.Coordinator.Registry.TryResolve(request.Model, out var model));
            string path = Path.Combine(rig.DirectoryPath, "framing-ledger.jsonl"); var ledger = new JsonlVideoJobLedger(path);
            var legacy = VideoJobRecordFactory.From(Guid.NewGuid(), request, model, new VideoCostEstimator().Estimate(model, request).Estimate!, VideoJobState.Queued, DateTimeOffset.UtcNow);
            ledger.Append(legacy); Assert.DoesNotContain("source_framing", File.ReadAllText(path));
            var framed = VideoJobRecordFactory.From(Guid.NewGuid(), request.With(sourceFraming: SourceFramingMode.Fill), model, new VideoCostEstimator().Estimate(model, request).Estimate!, VideoJobState.Queued, DateTimeOffset.UtcNow);
            ledger.Append(framed);
            Assert.Equal(SourceFramingMode.Fill, ledger.ReadAll().Records.Single(r => r.JobId == framed.JobId).NormalizedRequest.SourceFraming);
            File.AppendAllText(path, File.ReadLines(path).Last().Replace("\"source_framing\":\"fill\"", "\"source_framing\":null") + Environment.NewLine);
            Assert.NotEmpty(ledger.ReadAll().Errors);
        }
        [Fact]
        public async Task Contract_DirectManagerCannotBypassConfirmation()
        {
            using var rig = new VideoFalFallbackManagerTests.Rig();
            var request = TestVideoFixtures.DefaultT2vRequest(mode: VideoMode.I2V, startFrame: MediaRef.ForArtifact(Guid.NewGuid(), "image"))
                .With(sourceFraming: SourceFramingMode.Fit);
            var direct = await rig.Manager.SubmitAsync(request, default);
            Assert.Equal("estimate_fingerprint", direct.GenerationError!.Field);
            var confirmed = await ((IVideoConfirmedJobManager)rig.Manager).SubmitConfirmedAsync(VideoRequestIntent.Normalize(request, new JsonObject()), new(null, 10m), default);
            Assert.Equal("estimate_fingerprint", confirmed.GenerationError!.Field);
            Assert.Equal(0, rig.Google.Submits + rig.Fal.Submits);
        }
        internal static Dictionary<string, JsonElement> Args(JsonNode? mode)
        {
            var body = JsonNode.Parse("{\"model\":\"veo-3.1-generate-preview\",\"mode\":\"i2v\",\"duration_seconds\":8,\"resolution\":\"1080p\",\"aspect_ratio\":\"16:9\",\"options\":{},\"prompt\":\"clip\"}")!.AsObject();
            body["start_frame"] = new JsonObject { ["kind"] = "artifact_id", ["artifact_id"] = Guid.NewGuid().ToString("D"), ["role"] = "image" };
            body["source_framing"] = mode;
            return JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body.ToJsonString())!;
        }
        [Theory]
        [InlineData("fit", SourceFramingMode.Fit)]
        [InlineData("fill", SourceFramingMode.Fill)]
        public void Contract_FramingIsStrictTopLevelAndPreserved(string wire, SourceFramingMode mode)
        {
            using var rig = new VideoFalFallbackManagerTests.Rig();
            var handler = new VideoOpHandler(rig.Manager, rig.Coordinator.Registry, new VideoCostEstimator());
            var result = handler.ParseRequestIntent(Args(JsonValue.Create(wire)));
            Assert.Null(result.Error); Assert.Equal(mode, result.Intent!.Request.SourceFraming);
            Assert.Equal(mode, result.Intent.Request.WithPrompt("changed").With(resolution: "720p").SourceFraming);
            Assert.False(result.Intent.SuppliedOptions.ContainsKey("source_framing"));
        }
        [Theory]
        [InlineData("null")]
        [InlineData("123")]
        [InlineData("true")]
        [InlineData("\"crop\"")]
        [InlineData("{}")]
        public void Contract_NullNonstringAndUnknownRejected(string json)
        {
            using var rig = new VideoFalFallbackManagerTests.Rig();
            var handler = new VideoOpHandler(rig.Manager, rig.Coordinator.Registry, new VideoCostEstimator());
            var result = handler.ParseRequestIntent(Args(JsonNode.Parse(json)));
            Assert.Equal("source_framing", result.Error!.Field);
        }
        [Fact]
        public void Contract_OmittedStaysLegacy_AndUnsupportedUseIsRejected()
        {
            using var rig = new VideoFalFallbackManagerTests.Rig();
            var handler = new VideoOpHandler(rig.Manager, rig.Coordinator.Registry, new VideoCostEstimator());
            var args = Args(JsonValue.Create("fit")); args.Remove("source_framing");
            Assert.Null(handler.ParseRequestIntent(args).Intent!.Request.SourceFraming);
            args = Args(JsonValue.Create("fit")); args["mode"] = JsonSerializer.Deserialize<JsonElement>("\"t2v\"");
            Assert.Equal("source_framing", handler.ParseRequestIntent(args).Error!.Field);
        }
    }
}
