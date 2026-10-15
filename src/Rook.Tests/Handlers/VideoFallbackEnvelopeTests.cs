using System;
using System.Linq;
using System.IO;
using System.Threading;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Rook.Handlers;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;
using static Rook.Tests.Services.Vision.Video.VideoFalFallbackManagerTests;

namespace Rook.Tests.Handlers
{
    public class VideoFallbackEnvelopeTests
    {
        [Fact]
        public async Task BridgeFixtureMatchesActualHandlers()
        {
            var fixtures = new JsonObject();
            using (var rig = new Rig()) fixtures["estimate"] = JsonSerializer.SerializeToNode(Handler(rig).DispatchOffUi(Request().ToJsonString()));
            foreach (var scenario in new[] { "missing", "rejected", "403" })
            {
                using var rig = new Rig(); var marker = scenario == "403" ? null : "rook.fal.key_" + scenario;
                rig.Fal.Submit = (r, ct) => Task.FromResult<ProviderSubmitOutcome>(new FailedSubmitOutcome(new GenerationError(GenerationErrorCode.DependencyUnavailable, "Safe provider failure.", false, null, marker)));
                var handler = Handler(rig); var submit = await handler.DispatchAsync(Request(VideoOpHandler.OpSubmit, "fal-ai/veo3.1").ToJsonString()); await Limit(rig.Done.Task);
                var status = Data(handler.DispatchOffUi(new JsonObject { ["op"] = VideoOpHandler.OpStatus, ["job_id"] = Data(submit)["job_id"]!.DeepClone() }.ToJsonString()));
                var projection = new JsonObject();
                foreach (var field in new[] { "state", "error", "requested_provider", "requested_model", "effective_provider", "effective_model", "credential_failure", "video_route", "submission_outcome_unknown", "execution_stopped", "stop_persistence" }) projection[field] = status[field]?.DeepClone();
                fixtures["direct_" + scenario] = new JsonObject { ["success"] = true, ["data"] = projection };
            }
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory != null && !File.Exists(Path.Combine(directory.FullName, "Rook.sln"))) directory = directory.Parent;
            var path = Path.Combine(directory!.FullName, "src/Rook.Tests/UI/Vision/Fixtures/video-fallback-bridge.json");
            if (Environment.GetEnvironmentVariable("ROOK_UPDATE_VIDEO_BRIDGE_FIXTURE") == "1") File.WriteAllText(path, fixtures.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
            Assert.True(File.Exists(path), "Explicit fixture regeneration required.");
            Assert.True(JsonNode.DeepEquals(JsonNode.Parse(File.ReadAllText(path)), fixtures));
        }
        [Fact]
        public async Task PendingPersistenceIsNotCancelledSuccess()
        {
            using var rig = new Rig(); var entered = Signal<bool>(); var release = Signal<bool>();
            rig.Google.Poll = (h, ct) => Signal<ProviderStatusOutcome>().Task;
            var handler = Handler(rig); var submit = await handler.DispatchAsync(Request(VideoOpHandler.OpSubmit).ToJsonString()); var id = Data(submit)["job_id"]!.GetValue<string>();
            rig.Ledger.BeforeAppend = r => { if (r.State == VideoJobState.Interrupted || r.State == VideoJobState.Cancelled) { entered.TrySetResult(true); release.Task.GetAwaiter().GetResult(); } };
            rig.Timer.Fire(); await Limit(entered.Task);
            try { var status = Data(handler.DispatchOffUi(new JsonObject { ["op"] = VideoOpHandler.OpStatus, ["job_id"] = id }.ToJsonString())); Assert.Equal("pending", status["stop_persistence"]!.GetValue<string>()); Assert.True(status["execution_stopped"]!.GetValue<bool>()); Assert.NotEqual("cancelled", status["state"]!.GetValue<string>()); }
            finally { release.TrySetResult(true); }
            await Limit(rig.Done.Task);
        }
        internal static JsonObject Request(string op = VideoOpHandler.OpEstimate, string model = "veo-3.1-generate-preview") => new() { ["op"] = op, ["model"] = model, ["mode"] = "t2v", ["prompt"] = "A moving garden", ["duration_seconds"] = 4, ["resolution"] = "720p", ["aspect_ratio"] = "16:9", ["options"] = new JsonObject() };
        internal static VideoOpHandler Handler(Rig rig) => new(rig.Manager, rig.Coordinator.Registry, new VideoCostEstimator());
        internal static JsonObject Data(Rook.ApiResponse response) => JsonSerializer.SerializeToNode(response.Data)!.AsObject();
        [Fact]
        public async Task ActualHandlersRetainEvidenceAcrossAllOperations()
        {
            using var rig = new Rig(); var handler = Handler(rig); var request = Request();
            var estimate = handler.DispatchOffUi(request.ToJsonString()); Assert.True(estimate.Success);
            var quoted = Data(estimate); Assert.NotNull(quoted["estimate_fingerprint"]); Assert.NotNull(quoted["maximum_estimated_cost_usd"]);
            request["op"] = VideoOpHandler.OpSubmit; request["estimate_fingerprint"] = quoted["estimate_fingerprint"]!.DeepClone(); request["max_estimated_cost_usd"] = quoted["maximum_estimated_cost_usd"]!.DeepClone();
            var submitted = await handler.DispatchAsync(request.ToJsonString()); Assert.True(submitted.Success);
            var id = Data(submitted)["job_id"]!.GetValue<string>(); await Limit(rig.Done.Task);
            foreach (var op in new[] { VideoOpHandler.OpStatus, VideoOpHandler.OpResult })
            { var response = handler.DispatchOffUi(new JsonObject { ["op"] = op, ["job_id"] = id }.ToJsonString()); Assert.True(response.Success); Assert.Equal("veo", Data(response)["effective_provider"]!.GetValue<string>()); }
            var listed = Data(handler.DispatchOffUi("{\"op\":\"list_video_jobs\"}")); Assert.NotNull(listed["jobs"]![0]!["accepted_quote"]);
            Assert.NotNull(Data(await handler.DispatchAsync(new JsonObject { ["op"] = VideoOpHandler.OpCancel, ["job_id"] = id }.ToJsonString()))["effective_provider"]);
        }
        [Theory]
        [InlineData("rook.fal.key_missing", "missing")]
        [InlineData("rook.fal.key_rejected", "rejected")]
        [InlineData(null, null)]
        public async Task DirectFalCredentialFailuresNeedNoReceipt(string? marker, string? kind)
        {
            using var rig = new Rig(); rig.Fal.Submit = (r, ct) => Task.FromResult<ProviderSubmitOutcome>(new FailedSubmitOutcome(new GenerationError(GenerationErrorCode.DependencyUnavailable, "Safe provider failure.", false, null, marker)));
            var handler = Handler(rig); var submit = await handler.DispatchAsync(Request(VideoOpHandler.OpSubmit, "fal-ai/veo3.1").ToJsonString()); Assert.True(submit.Success); await Limit(rig.Done.Task);
            var status = Data(handler.DispatchOffUi(new JsonObject { ["op"] = VideoOpHandler.OpStatus, ["job_id"] = Data(submit)["job_id"]!.DeepClone() }.ToJsonString()));
            Assert.Null(status["video_route"]); Assert.Equal(kind, status["credential_failure"]?["kind"]?.GetValue<string>());
            if (kind != null) Assert.Equal("fal", status["credential_failure"]!["provider"]!.GetValue<string>());
        }
        [Fact]
        public void UntouchedOptionsAndExplicitLegacyRequestsDiffer()
        {
            using var rig = new Rig(); rig.Secrets.Google = null; var handler = Handler(rig); var request = Request();
            Assert.True(handler.DispatchOffUi(request.ToJsonString()).Success);
            request["options"] = new JsonObject { ["person_generation"] = "allow_all" };
            var rejected = handler.DispatchOffUi(request.ToJsonString()); Assert.False(rejected.Success); Assert.Contains("person_generation", Data(rejected)["field"]!.GetValue<string>());
        }
        [Theory]
        [InlineData("{\"estimate_fingerprint\":\"bad\"}", "estimate_fingerprint")]
        [InlineData("{\"max_estimated_cost_usd\":-1}", "max_estimated_cost_usd")]
        [InlineData("{\"max_estimated_cost_usd\":\"1\"}", "max_estimated_cost_usd")]
        [InlineData("{\"max_estimated_cost_usd\":null}", "max_estimated_cost_usd")]
        public async Task FingerprintAndCapParsingIsStrict(string extra, string field)
        {
            using var rig = new Rig(); var request = Request(VideoOpHandler.OpSubmit);
            foreach (var kv in JsonNode.Parse(extra)!.AsObject()) request[kv.Key] = kv.Value?.DeepClone();
            var result = await Handler(rig).DispatchAsync(request.ToJsonString()); Assert.False(result.Success); Assert.Equal(field, Data(result)["field"]!.GetValue<string>()); Assert.Equal(0, rig.Google.Submits);
        }
    }
}
