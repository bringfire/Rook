using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook;
using Rook.Handlers;
using Rook.InternalBridge;
using Rook.Services.Vision;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Image.Jobs;
using Rook.Tests.Services.Vision.Image;
using Rook.Tests.Services.Vision.Image.Jobs;
using Rook.UI.Vision;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class ImageFallbackHandlerTests
    {
        internal static VisionHandler Handler(ImageFallbackFixture f) =>
            new(f.Store, new FixtureSecrets(f), new PromptEnhancer(), new ViewportHandler(), f.Registry,
                new ImageArtifactMaterializer(f.DownloadHttp), imageSubmissionExecutor: f.Executor);
        internal static string Body(ImageFallbackFixture f, string model, string op = "generate", string aspect = "") =>
            new JsonObject
            {
                ["op"] = op, ["prompt"] = "private test prompt", ["model"] = model, ["resolution"] = "1K",
                ["aspect_ratio"] = aspect,
                ["input_image"] = new JsonObject { ["kind"] = "artifact_id",
                    ["artifact_id"] = f.ParentArtifactIds[0].ToString("D"), ["role"] = "image" },
                ["reference_images"] = new JsonArray(new JsonObject { ["kind"] = "artifact_id",
                    ["artifact_id"] = f.ParentArtifactIds[1].ToString("D"), ["role"] = "image" })
            }.ToJsonString();
        internal static JsonObject Json(ApiResponse response) => VisionWebSurface.ApiResponseToJsonNode(response).AsObject();

        [Theory]
        [InlineData("nano-banana-2", "fal-ai/nano-banana-2")]
        [InlineData("nano-banana-pro", "fal-ai/nano-banana-pro")]
        public async Task SynchronousFallbackUsesLocalRouteAndParents(string requested, string effective)
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            var result = await Handler(f).DispatchAsync(Body(f, requested));
            Assert.True(result.Success);
            var artifact = f.Store.List().Single(a => a.Kind == "generated_image");
            Assert.Equal("fal", artifact.Metadata["provider"]!.GetValue<string>());
            Assert.Equal(effective, artifact.Metadata["model"]!.GetValue<string>());
            Assert.Equal("gemini", artifact.Metadata["requested_provider"]!.GetValue<string>());
            Assert.Equal(f.ParentArtifactIds, artifact.ParentIds);
            Assert.Empty(f.GoogleHttp.Requests); Assert.Single(f.FalHttp.Requests);
        }

        [Theory]
        [InlineData(null, 200, "missing", 0)]
        [InlineData("key", 401, "rejected", 1)]
        [InlineData("key", 403, null, 1)]
        public async Task DirectFalProjectsIndependentCredentialEvidence(string? key, int status, string? kind, int sends)
        {
            using var f = new ImageFallbackFixture(falKey: key);
            f.FalHttp.OnSendAsync = (_, _) => Task.FromResult(ImageFallbackFixture.Json(status,
                "{\"detail\":\"fake-fal private test prompt\"}"));
            var response = await Handler(f).DispatchAsync(Body(f, "fal-ai/nano-banana-2"));
            Assert.False(response.Success);
            var data = Json(response)["data"]!;
            Assert.Equal("fal", data["provider"]!.GetValue<string>());
            Assert.Null(data["image_route"]);
            Assert.Equal(kind, data["credential_failure"]?["kind"]?.GetValue<string>());
            Assert.Equal(sends, f.FalHttp.Requests.Count); Assert.Empty(f.GoogleHttp.Requests);
            Assert.DoesNotContain("private test prompt", data.ToJsonString());
            Assert.DoesNotContain("fake-fal", data.ToJsonString());
        }

        [Theory]
        [InlineData(401, "rejected")]
        [InlineData(403, null)]
        [InlineData(500, null)]
        public async Task FalFailureRetainsFallbackRouteAndOnlyDefinitiveEvidence(int status, string? kind)
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            f.FalHttp.OnSendAsync = (_, _) => Task.FromResult(ImageFallbackFixture.Json(status, "{}"));
            var result = await Handler(f).DispatchAsync(Body(f, "nano-banana-2"));
            var data = Json(result)["data"]!;
            Assert.Equal("fal", data["image_route"]!["effective_provider"]!.GetValue<string>());
            Assert.Equal(kind, data["credential_failure"]?["kind"]?.GetValue<string>());
            Assert.Equal("attempted", data["fal_dispatch_state"]!.GetValue<string>());
        }

        [Fact]
        public void FalOnlyCatalogPreservesMissingGeminiAndSettingsRefresh()
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            var handler = Handler(f);
            JsonObject Gemini() => Json(handler.DispatchOffUi("{\"op\":\"list_image_models\"}"))["data"]!["models"]!.AsArray()
                .Select(n => n!.AsObject()).Single(n => n["model_id"]!.GetValue<string>() == GeminiImageCapabilities.NanoBanana2);
            var descriptor = Gemini();
            Assert.Equal("missing_required_secret", descriptor["credential_availability"]!.GetValue<string>());
            Assert.Equal("fal", descriptor["fallback_available"]!["provider_name"]!.GetValue<string>());
            Assert.Equal("available_but_unverified", descriptor["fallback_available"]!["credential_availability"]!.GetValue<string>());
            f.FalKey = null;
            Assert.Equal("missing_required_secret", Gemini()["fallback_available"]!["credential_availability"]!.GetValue<string>());
            f.GeminiKey = "replacement";
            Assert.Equal("available_but_unverified", Gemini()["credential_availability"]!.GetValue<string>());
            Assert.Empty(f.GoogleHttp.Requests); Assert.Empty(f.FalHttp.Requests);
        }

        [Theory]
        [InlineData(null, 200, "missing")]
        [InlineData("key", 401, "rejected")]
        [InlineData("key", 403, null)]
        public async Task JobStatusResultAndListKeepDirectFalEvidence(string? key, int status, string? kind)
        {
            using var f = new ImageFallbackFixture(falKey: key);
            f.FalHttp.OnSendAsync = (_, _) => Task.FromResult(ImageFallbackFixture.Json(status, "{}"));
            using var manager = new ImageJobManager(f.Registry, f.Store, null, null, null, 2,
                new ImageArtifactMaterializer(f.DownloadHttp), null,
                new JsonlImageJobLedger(System.IO.Path.Combine(f.Root, "ledger.jsonl")), f.Executor);
            var ops = new ImageJobOpHandler(manager, Handler(f));
            var start = Json(await ops.DispatchAsync(Body(f, "fal-ai/nano-banana-2", "image_generate_start")));
            var id = Guid.Parse(start["data"]!["job_id"]!.GetValue<string>());
            await ImageJobFallbackTests.Terminal(manager, id);
            await ImageJobFallbackTests.Settled(manager);
            foreach (var op in new[] { "image_job_status", "image_job_result", "image_jobs" })
            {
                var response = Json(ops.DispatchOffUi(new JsonObject { ["op"] = op, ["job_id"] = id.ToString("D") }.ToJsonString()));
                var data = op == "image_jobs" ? response["data"]!["jobs"]![0]! : response["data"]!;
                Assert.Equal("fal", data["provider"]!.GetValue<string>());
                Assert.Null(data["image_route"]);
                Assert.Equal(kind, data["credential_failure"]?["kind"]?.GetValue<string>());
            }
        }

        [Fact]
        public async Task NativeOuterTimeoutKeepsReceiptAndReturnsBeforeHeldTransport()
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            Task<ApiResponse>? handlerTask = null;
            var original = f.FalHttp.OnSendAsync!;
            f.FalHttp.OnSendAsync = async (r, ct) => { entered.TrySetResult(true); await release.Task; return await original(r, ct); };
            var handler = Handler(f); var context = new ImageExecutionContext();
            var outer = Task.Run(() => NativeGhBridgeRegistrar.RunVisionAsyncWithTimeout(Body(f, "nano-banana-2"),
                (body, ct) => handlerTask = handler.DispatchAsync(body, ct, context), TimeSpan.FromMilliseconds(500), context));
            Assert.Same(entered.Task, await Task.WhenAny(entered.Task, Task.Delay(5000)));
            var result = await outer;
            Assert.False(result.Success); Assert.False(release.Task.IsCompleted);
            var data = Json(result)["data"]!;
            Assert.Equal("interrupted", data["code"]!.GetValue<string>());
            Assert.True(data["image_route"]!["generation_dispatch_attempted"]!.GetValue<bool>());
            Assert.Null(data["credential_failure"]);
            release.TrySetResult(true);
            if (handlerTask != null) await handlerTask;
            Assert.DoesNotContain(f.Store.List(), a => a.Kind == "generated_image");
        }

        [Fact]
        public async Task PanelTimeoutClearsCredentialEvidenceAndPreservesDirectProvider()
        {
            using var f = new ImageFallbackFixture();
            f.Registry.TryResolve("fal-ai/nano-banana-2", out var fal);
            var context = new ImageExecutionContext(); context.Initialize(f.Request(fal.ModelId), fal);
            context.SetCredentialFailure(new("fal", ImageCredentialFailureKind.Rejected));
            var result = await VisionWebSurface.DispatchWithTimeoutAsync("generate", TimeSpan.FromMilliseconds(20),
                async ct => { await Task.Delay(Timeout.Infinite, ct); return new ApiResponse(); }, imageContext: context);
            var data = Json(result)["data"]!;
            Assert.Equal("fal", data["provider"]!.GetValue<string>());
            Assert.Null(data["image_route"]); Assert.Null(data["credential_failure"]);
            Assert.Equal("interrupted", data["code"]!.GetValue<string>());
        }

        [Theory]
        [InlineData("malformed")]
        [InlineData("download")]
        [InlineData("aspect")]
        public async Task LaterFailuresKeepFallbackWithoutCredentialWarnings(string failure)
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            if (failure == "malformed") f.FalHttp.OnSendAsync = (_, _) => Task.FromResult(ImageFallbackFixture.Json(200, "{}"));
            if (failure == "download") f.DownloadHttp.OnSendAsync = (_, _) => Task.FromResult(ImageFallbackFixture.Json(404, "{}"));
            var response = await Handler(f).DispatchAsync(Body(f, "nano-banana-pro", aspect: failure == "aspect" ? "8:1" : ""));
            var data = Json(response)["data"]!;
            Assert.False(response.Success); Assert.Null(data["credential_failure"]);
            Assert.Equal("fal", data["provider"]!.GetValue<string>());
            Assert.Equal("gemini", data["image_route"]!["requested_provider"]!.GetValue<string>());
            Assert.Equal(failure != "aspect", data["image_route"]!["generation_dispatch_attempted"]!.GetValue<bool>());
            Assert.DoesNotContain(f.Store.List(), a => a.Kind == "generated_image");
        }

        [Fact]
        public async Task RepeatedReferencesReuseResolvedBytesAfterPrimaryChangesPaths()
        {
            using var f = new ImageFallbackFixture();
            var source = System.IO.Path.Combine(f.Root, "source.png");
            var reference = System.IO.Path.Combine(f.Root, "reference.png");
            System.IO.File.WriteAllBytes(source, ImageFallbackFixture.Png);
            System.IO.File.WriteAllBytes(reference, ImageFallbackFixture.Png);
            f.GoogleHttp.OnSendAsync = (_, _) =>
            {
                System.IO.File.WriteAllBytes(source, new byte[] { 65 });
                System.IO.File.WriteAllBytes(reference, new byte[] { 66 });
                return Task.FromResult(ImageFallbackFixture.Json(401, "{\"error\":{\"status\":\"UNAUTHENTICATED\"}}"));
            };
            var body = JsonNode.Parse(Body(f, "nano-banana-2"))!.AsObject();
            body.Remove("input_image"); body.Remove("reference_images");
            body["input_image_path"] = source;
            body["reference_image_paths"] = new JsonArray(reference, reference);
            Assert.True((await Handler(f).DispatchAsync(body.ToJsonString())).Success);
            var urls = JsonNode.Parse(Assert.Single(f.FalHttp.Requests).Body!)!["image_urls"]!.AsArray();
            Assert.Equal(3, urls.Count);
            Assert.All(urls, n => Assert.Equal("data:image/png;base64," + Convert.ToBase64String(ImageFallbackFixture.Png), n!.GetValue<string>()));
        }

        [Fact]
        public async Task DirectFalValidationFailureIsStructuredBeforeHttp()
        {
            using var f = new ImageFallbackFixture();
            var body = JsonNode.Parse(Body(f, "fal-ai/nano-banana-2"))!.AsObject(); body["resolution"] = "512";
            var data = Json(await Handler(f).DispatchAsync(body.ToJsonString()))["data"]!;
            Assert.Equal("fal", data["provider"]!.GetValue<string>());
            Assert.Equal("resolution", data["field"]!.GetValue<string>());
            Assert.Null(data["image_route"]); Assert.Null(data["credential_failure"]);
            Assert.Empty(f.FalHttp.Requests); Assert.Empty(f.GoogleHttp.Requests);
        }

        [Fact]
        public void NativeUtf8CallbackPreservesIndependentCredentialProjection()
        {
            using var f = new ImageFallbackFixture();
            var response = new ApiResponse { Success = false, HttpStatus = 503,
                Data = ImageFailureProjection.Build(new(GenerationErrorCode.DependencyUnavailable, "生成失敗。", false),
                    "fal", "fal-ai/nano-banana-2", new(null, new("fal", ImageCredentialFailureKind.Missing)),
                    ImageFalDispatchState.NotStarted) };
            var callback = typeof(NativeGhBridgeRegistrar).GetMethod("ExecuteAsyncApiResponseCallback",
                System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!;
            var buffer = System.Runtime.InteropServices.Marshal.AllocHGlobal(65536);
            var length = System.Runtime.InteropServices.Marshal.AllocHGlobal(4);
            var status = System.Runtime.InteropServices.Marshal.AllocHGlobal(4);
            try
            {
                Func<string, CancellationToken, Task<ApiResponse>> operation = (_, _) => Task.FromResult(response);
                Assert.Equal(0, callback.Invoke(null, new object?[] { buffer, 65536, length, status, "{}", operation, 1, null }));
                var bytes = new byte[System.Runtime.InteropServices.Marshal.ReadInt32(length)];
                System.Runtime.InteropServices.Marshal.Copy(buffer, bytes, 0, bytes.Length);
                var data = JsonNode.Parse(System.Text.Encoding.UTF8.GetString(bytes))!["data"]!;
                Assert.Equal("生成失敗。", data["message"]!.GetValue<string>());
                Assert.Equal("missing", data["credential_failure"]!["kind"]!.GetValue<string>());
                Assert.Null(data["image_route"]); Assert.Equal(503, System.Runtime.InteropServices.Marshal.ReadInt32(status));
            }
            finally
            {
                System.Runtime.InteropServices.Marshal.FreeHGlobal(buffer);
                System.Runtime.InteropServices.Marshal.FreeHGlobal(length);
                System.Runtime.InteropServices.Marshal.FreeHGlobal(status);
            }
        }

        internal sealed class FixtureSecrets : IGenerationSecretStore
        {
            private readonly ImageFallbackFixture _f;
            public FixtureSecrets(ImageFallbackFixture f) => _f = f;
            public string? GetSecret(string key) => key == GenerationSecretKeys.GeminiApiKey ? _f.GeminiKey :
                key == GenerationSecretKeys.FalApiKey ? _f.FalKey : null;
            public void SetSecret(string key, string value)
            { if (key == GenerationSecretKeys.GeminiApiKey) _f.GeminiKey = value; if (key == GenerationSecretKeys.FalApiKey) _f.FalKey = value; }
            public void RemoveSecret(string key)
            { if (key == GenerationSecretKeys.GeminiApiKey) _f.GeminiKey = null; if (key == GenerationSecretKeys.FalApiKey) _f.FalKey = null; }
            public bool HasSecret(string key) => !string.IsNullOrWhiteSpace(GetSecret(key));
            public string? GetPreview(string key) => HasSecret(key) ? "***" : null;
        }

        [Fact]
        public async Task WriteFallbackBridgeFixtureIfRequested()
        {
            var fixtures = new JsonObject();
            using (var f = new ImageFallbackFixture(geminiKey: null))
            {
                var handler = Handler(f);
                fixtures["catalog_fal_only"] = Json(handler.DispatchOffUi("{\"op\":\"list_image_models\"}"));
                fixtures["fallback_success"] = Json(await handler.DispatchAsync(Body(f, "nano-banana-2")));
                f.FalKey = null;
                fixtures["catalog_neither"] = Json(handler.DispatchOffUi("{\"op\":\"list_image_models\"}"));
                fixtures["fallback_missing"] = Json(await handler.DispatchAsync(Body(f, "nano-banana-2")));
                f.GeminiKey = "fake-gemini"; f.FalKey = "fake-fal";
                fixtures["catalog_google"] = Json(handler.DispatchOffUi("{\"op\":\"list_image_models\"}"));
                fixtures["primary_success"] = Json(await handler.DispatchAsync(Body(f, "nano-banana-2")));
            }
            foreach (var direct in new[] { false, true })
            foreach (var status in new[] { 401, 403 })
            {
                using var f = new ImageFallbackFixture(geminiKey: direct ? "key" : null);
                f.FalHttp.OnSendAsync = (_, _) => Task.FromResult(ImageFallbackFixture.Json(status, "{}"));
                fixtures[(direct ? "direct_" : "fallback_") + status] =
                    Json(await Handler(f).DispatchAsync(Body(f, direct ? "fal-ai/nano-banana-2" : "nano-banana-2")));
            }
            using (var f = new ImageFallbackFixture(falKey: null))
                fixtures["direct_missing"] = Json(await Handler(f).DispatchAsync(Body(f, "fal-ai/nano-banana-2")));
            foreach (var status in new[] { 0, 401, 403 })
            {
                using var f = new ImageFallbackFixture(falKey: status == 0 ? null : "key");
                f.FalHttp.OnSendAsync = (_, _) => Task.FromResult(ImageFallbackFixture.Json(status == 0 ? 200 : status, "{}"));
                using var manager = new ImageJobManager(f.Registry, f.Store, null, null, null, 2,
                    new ImageArtifactMaterializer(f.DownloadHttp), null,
                    new JsonlImageJobLedger(System.IO.Path.Combine(f.Root, "ledger.jsonl")), f.Executor);
                var submit = await manager.SubmitAsync(f.Start("fal-ai/nano-banana-2"), CancellationToken.None);
                await ImageJobFallbackTests.Terminal(manager, submit.JobId!.Value);
                await ImageJobFallbackTests.Settled(manager);
                fixtures["direct_job_" + (status == 0 ? "missing" : status.ToString())] = Json(
                    new ImageJobOpHandler(manager, Handler(f)).DispatchOffUi(
                        "{\"op\":\"image_job_status\",\"job_id\":\"" + submit.JobId.Value.ToString("D") + "\"}"));
            }
            using (var f = new ImageFallbackFixture(geminiKey: null))
            {
                fixtures["incompatible"] = Json(await Handler(f).DispatchAsync(Body(f, "nano-banana-pro", aspect: "8:1")));
                f.DownloadHttp.OnSendAsync = (_, _) => Task.FromResult(ImageFallbackFixture.Json(404, "{}"));
                fixtures["materialization_failed"] = Json(await Handler(f).DispatchAsync(Body(f, "nano-banana-2")));
            }
            using (var f = new ImageFallbackFixture(geminiKey: null))
            {
                var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                var original = f.FalHttp.OnSendAsync!;
                f.FalHttp.OnSendAsync = async (r, ct) => { entered.TrySetResult(true); await release.Task; return await original(r, ct); };
                var ledger = new JsonlImageJobLedger(System.IO.Path.Combine(f.Root, "ledger.jsonl"));
                using var manager = new ImageJobManager(f.Registry, f.Store, null, null, null, 2,
                    new ImageArtifactMaterializer(f.DownloadHttp), null, ledger, f.Executor);
                var submit = await manager.SubmitAsync(f.Start(GeminiImageCapabilities.NanoBanana2), CancellationToken.None);
                Assert.Same(entered.Task, await Task.WhenAny(entered.Task, Task.Delay(5000)));
                var copy = System.IO.Path.Combine(f.Root, "snapshot.jsonl"); System.IO.File.Copy(ledger.FilePath, copy);
                using (var fresh = new ImageJobManager(f.Registry, f.Store, null, null, null, 2,
                    new ImageArtifactMaterializer(f.DownloadHttp), null, new JsonlImageJobLedger(copy), f.Executor))
                {
                    fresh.ReconcileInterruptedJobs();
                    var ops = new ImageJobOpHandler(fresh, Handler(f));
                    fixtures["restored_intent_status"] = Json(ops.DispatchOffUi(
                        "{\"op\":\"image_job_status\",\"job_id\":\"" + submit.JobId!.Value.ToString("D") + "\"}"));
                    fixtures["restored_intent_result"] = Json(ops.DispatchOffUi(
                        "{\"op\":\"image_job_result\",\"job_id\":\"" + submit.JobId.Value.ToString("D") + "\"}"));
                }
                release.TrySetResult(true);
                await ImageJobFallbackTests.Terminal(manager, submit.JobId!.Value);
                await ImageJobFallbackTests.Settled(manager);
                var completedOps = new ImageJobOpHandler(manager, Handler(f));
                fixtures["job_fallback_result"] = Json(completedOps.DispatchOffUi(
                    "{\"op\":\"image_job_result\",\"job_id\":\"" + submit.JobId.Value.ToString("D") + "\"}"));
            }
            NormalizeFixture(fixtures);
            var dir = new System.IO.DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null && !System.IO.File.Exists(System.IO.Path.Combine(dir.FullName, "src", "Rook", "Rook.csproj"))) dir = dir.Parent;
            Assert.NotNull(dir);
            var path = System.IO.Path.Combine(dir!.FullName, "src", "Rook.Tests", "UI", "Vision", "Fixtures", "image-fallback-bridge.json");
            if (Environment.GetEnvironmentVariable("ROOK_WRITE_IMAGE_FALLBACK_FIXTURE") == "1")
            {
                System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(path)!);
                System.IO.File.WriteAllText(path, fixtures.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + "\n");
            }
            Assert.True(System.IO.File.Exists(path), "Generate the opt-in managed bridge fixture first.");
            Assert.True(JsonNode.DeepEquals(fixtures, JsonNode.Parse(System.IO.File.ReadAllText(path))), "Managed bridge fixture differs from current projections.");
        }

        private static void NormalizeFixture(JsonNode node)
        {
            if (node is JsonObject obj)
            {
                foreach (var key in obj.Select(p => p.Key).ToArray())
                {
                    if (key is "created_at" or "updated_at" or "generated_at") { obj[key] = "<timestamp>"; continue; }
                    if (key is "file_path") { obj[key] = "<local-file>"; continue; }
                    var value = obj[key];
                    if (value is JsonValue v && v.TryGetValue<string>(out var s))
                        obj[key] = System.Text.RegularExpressions.Regex.Replace(s,
                            "[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}",
                            "11111111-1111-1111-1111-111111111111");
                    else if (value != null) NormalizeFixture(value);
                }
            }
            else if (node is JsonArray array)
                for (var i = 0; i < array.Count; i++)
                    if (array[i] is JsonValue v && v.TryGetValue<string>(out var s))
                        array[i] = System.Text.RegularExpressions.Regex.Replace(s,
                            "[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}",
                            "11111111-1111-1111-1111-111111111111");
                    else if (array[i] != null) NormalizeFixture(array[i]!);
        }
    }
}
