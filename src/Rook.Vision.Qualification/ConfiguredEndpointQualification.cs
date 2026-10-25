using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Handlers;
using Rook.Services.Vision;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video.Framing;

namespace Rook.Vision.Qualification
{
    /// <summary>Offline, data-only conformance runner. The only HTTP handler is a closed ordered fixture;
    /// no credentials, real upload, inference, or arbitrary executable from case data is possible.</summary>
    public static class ConfiguredEndpointQualification
    {
        public static async Task<int> VerifyAsync(string catalog, string casesPath, string reportPath)
        {
            var data = JsonNode.Parse(File.ReadAllText(casesPath))!.AsObject();
            if (data["schema_version"]?.GetValue<int>() != 1 || data["cases"] is not JsonArray cases || cases.Count == 0)
                throw new ArgumentException("A version-one nonempty case array is required.");
            var loaded = new FalCatalogCompiler().Compile(catalog, VisionProviderRegistrations.GetLegacyModelIds());
            var rows = new JsonArray();
            foreach (var item in cases)
            {
                var c = item!.AsObject();
                JsonObject row;
                try
                {
                    if (loaded.Catalog == null) throw new InvalidOperationException("catalog_invalid");
                    row = await RunCaseAsync(loaded.Catalog, c, FindRepo(casesPath));
                }
                catch (Exception ex) { row = new JsonObject { ["passed"] = false, ["failure"] = ex is QualificationMismatch ? ex.Message : ex.GetType().Name }; }
                row["id"] = c["id"]?.DeepClone(); row["covers"] = c["covers"]?.DeepClone(); rows.Add(row);
            }
            bool passed = rows.All(r => r!["passed"]!.GetValue<bool>());
            Write(reportPath, new JsonObject { ["schema_version"] = 1, ["offline"] = true, ["success"] = passed,
                ["cases_sha256"] = RuntimeFreezeManifest.HashFile(casesPath), ["cases"] = rows });
            return passed ? 0 : 1;
        }

        private static async Task<JsonObject> RunCaseAsync(FalCatalogSnapshot catalog, JsonObject c, string repo)
        {
            var expected = c["expected"]!.AsObject();
            if (expected["outcome"]?.GetValueKind() != JsonValueKind.String || expected["calls"]?.GetValueKind() != JsonValueKind.Number)
                throw new ArgumentException("Every case must assert its actual outcome and HTTP call count.");
            var request = c["request"]!.DeepClone().AsObject();
            var model = catalog.Definitions.Single(d => d.ModelId == request["model"]!.GetValue<string>());
            var binding = model.Operations.Single(o => request["operation"] == null || o.OperationId == request["operation"]!.GetValue<string>());
            string modality = binding.Result.MimeFamily;
            var descriptor = new FalDescriptorProjector().Describe(binding, null).ToJson();
            string surface = c["surface"]!.GetValue<string>();
            var row = new JsonObject { ["surface"] = surface, ["model_id"] = binding.ModelId, ["operation"] = binding.OperationId,
                ["endpoint"] = binding.EndpointId, ["definition_hash"] = binding.DefinitionHash, ["descriptor_sha256"] = FalCanonicalJson.Hash(descriptor) };
            using var transport = new FixtureTransport(c["protocol"]!.AsArray());
            using var http = new HttpClient(transport);
            var executor = new FalConfiguredExecutor(new FalApiClient(http), () => "offline-fixture-credential");
            var resources = new VideoPreparationResources();
            var temp = Path.Combine(Path.GetTempPath(), "rook-fal-qualification-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(temp);
            try
            {
                JsonObject? capture = null;
                if (surface == "panel")
                {
                    capture = await CapturePanel(repo, temp, descriptor, c, null);
                    if (capture["estimate"] == null)
                    {
                        row["outcome"] = "surface_rejected";
                        return Finish(row, expected, transport, resources);
                    }
                    request = capture["estimate"]!.DeepClone().AsObject();
                }
                else if (surface == "mcp") request = CaptureGateway(repo, temp, modality == "image" ? "rhino_image_estimate" : "rhino_video_estimate", request)["arguments"]!.DeepClone().AsObject();
                else if (surface != "managed") throw new ArgumentException("Unknown surface.");
                row["request_sha256"] = FalCanonicalJson.Hash(request);
                var parsed = FalConfiguredRequestParser.Parse(request, catalog, modality);
                if (!parsed.Success)
                {
                    row["outcome"] = "invalid_request"; row["field"] = parsed.Errors[0].Field;
                    return Finish(row, expected, transport, resources);
                }
                var normalized = parsed.Request!;
                var media = new Dictionary<MediaRef, ResolvedMedia>();
                foreach (var source in (c["media_bytes"] as JsonArray ?? new JsonArray()).OfType<JsonObject>())
                    media.Add(MediaRef.ForArtifact(Guid.Parse(source["artifact_id"]!.GetValue<string>()), source["artifact_role"]!.GetValue<string>()),
                        new ResolvedMedia(Convert.FromBase64String(source["base64"]!.GetValue<string>()), source["mime"]!.GetValue<string>()));
                using (var snapshot = FalMediaSnapshot.Capture(normalized, media, resources))
                {
                    var quotes = new FalQuoteService();
                    var quotedRequest = normalized;
                    if (c["quote_changes"] is JsonObject changes)
                    {
                        var quotedInput = request.DeepClone().AsObject();
                        foreach (var change in changes) quotedInput[change.Key] = change.Value?.DeepClone();
                        var quotedParse = FalConfiguredRequestParser.Parse(quotedInput, catalog, modality);
                        if (!quotedParse.Success) throw new QualificationMismatch("Quote fixture input is invalid.");
                        quotedRequest = quotedParse.Request!;
                    }
                    var estimated = quotes.Estimate(quotedRequest, snapshot);
                    if (!estimated.Success) { row["outcome"] = estimated.Error!.ProviderErrorCode ?? estimated.Error.Code.ToString(); return Finish(row, expected, transport, resources, true); }
                    var quote = estimated.Quote!;
                    row["quote_fingerprint"] = quote.Fingerprint; row["cap_usd"] = quote.MaximumEstimatedCostUsd;
                    if (surface == "panel")
                    {
                        capture = await CapturePanel(repo, temp, descriptor, c, quote.ToJson());
                        if (capture["submit"] == null) throw new QualificationMismatch("Panel did not submit after quote.");
                        request = capture["submit"]!.DeepClone().AsObject();
                    }
                    else
                    {
                        request["quote_fingerprint"] = quote.Fingerprint; request["max_estimated_cost_usd"] = quote.MaximumEstimatedCostUsd;
                        if (surface == "mcp") request = CaptureGateway(repo, temp, modality == "image" ? "rhino_generate_image" : "rhino_render_video", request)["arguments"]!.DeepClone().AsObject();
                    }
                    if (c["confirmation"] is JsonObject confirmation)
                        foreach (var p in confirmation) request[p.Key] = p.Value?.DeepClone();
                    var submitParsed = FalConfiguredRequestParser.Parse(request, catalog, modality);
                    if (!submitParsed.Success) throw new QualificationMismatch("Captured submission failed managed parsing.");
                    var invalid = FalSubmitConfirmation.TryParse(request, out var confirmed) ?? quotes.Validate(quote, submitParsed.Request!, snapshot, confirmed);
                    if (invalid != null) { row["outcome"] = invalid.ProviderErrorCode ?? invalid.Code.ToString(); snapshot.Dispose(); return Finish(row, expected, transport, resources); }
                    normalized = submitParsed.Request!;
                    row["effective_request"] = normalized.EffectiveRequestFields;
                    row["effective_options"] = normalized.EffectiveOptions;
                    row["normalized_sha256"] = FalCanonicalJson.Hash(new JsonObject { ["request"] = normalized.EffectiveRequestFields, ["options"] = normalized.EffectiveOptions, ["media"] = FalExecutionSnapshot.Create(normalized, snapshot).MediaProvenance });
                    row["media"] = FalExecutionSnapshot.Create(normalized, snapshot).MediaProvenance;
                    var observer = new FixtureObserver(c["observer"]?.GetValue<string>());
                    var outcome = await executor.SubmitAsync(normalized, snapshot, observer, CancellationToken.None);
                    var saved = FalExecutionSnapshot.Create(normalized, snapshot, quote.Pricing).WithOutcome(outcome);
                    snapshot.Dispose();
                    row["dispatch_events"] = new JsonArray(observer.Events.Select(v => (JsonNode?)JsonValue.Create(v)).ToArray());
                    row["outcome"] = outcome.GetType().Name;
                    if (outcome is FailedSubmitOutcome failed) row["disposition"] = failed.Disposition.ToString();
                    if (outcome is SyncSubmitOutcome sync) ObserveResult(row, sync.Result);
                    if (outcome is QueuedSubmitOutcome queued)
                    {
                        foreach (string action in (c["actions"] as JsonArray ?? new JsonArray()).Select(a => a!.GetValue<string>()))
                        {
                            if (action == "status") row["status_outcome"] = (await executor.GetStatusAsync(binding, queued.Handle, CancellationToken.None)).GetType().Name;
                            else if (action == "result") ObserveResult(row, await executor.FetchResultAsync(binding, queued.Handle, CancellationToken.None));
                            else if (action == "cancel") row["cancel_outcome"] = (await executor.CancelAsync(binding, queued.Handle, CancellationToken.None)).GetType().Name;
                            else if (action == "restore_cancel")
                            {
                                // Recovery deliberately has no catalog argument: cleanup uses the persisted authority.
                                var restored = FalExecutionSnapshotCodec.Deserialize(FalExecutionSnapshotCodec.Serialize(saved));
                                if (!restored.CleanupAvailable) throw new QualificationMismatch("Pinned cleanup unavailable.");
                                row["cancel_outcome"] = (await new FalExecutionRecovery(executor).CancelAsync(restored.Snapshot!, CancellationToken.None)).GetType().Name;
                            }
                            else if (action == "unsupported_snapshot")
                            {
                                var json = FalExecutionSnapshotCodec.Serialize(saved); json["version"] = 999;
                                row["cleanup_available"] = FalExecutionSnapshotCodec.Deserialize(json).CleanupAvailable;
                            }
                            else throw new ArgumentException("Unknown lifecycle action.");
                        }
                    }
                    row["provenance"] = Sanitize(FalExecutionSnapshotCodec.SerializePublic(saved));
                }
                return Finish(row, expected, transport, resources);
            }
            finally { Directory.Delete(temp, true); }
        }

        private static void ObserveResult(JsonObject row, ProviderResultOutcome result)
        {
            row["outcome"] = result.GetType().Name;
            if (result is SuccessResultOutcome ok)
            {
                row["result_count"] = ok.Envelope.Artifacts.Count;
                row["result_role"] = ok.Envelope.Artifacts.Single().Role;
                row["result_mime"] = ok.Envelope.Artifacts.Single().DeclaredMimeType;
            }
        }
        private static JsonObject Finish(JsonObject row, JsonObject expected, FixtureTransport transport, VideoPreparationResources resources, bool ownsSnapshot = false)
        {
            row["calls"] = transport.Calls; row["provider_payload"] = Sanitize(transport.Payload);
            if (transport.Payload != null) row["payload_sha256"] = FalCanonicalJson.Hash(transport.Payload);
            if (transport.Failure != null) throw new QualificationMismatch(transport.Failure);
            if (transport.Remaining != 0) throw new QualificationMismatch("Unconsumed protocol fixtures.");
            if (!ownsSnapshot && resources.ActiveBundles != 0) throw new QualificationMismatch("Media admission leaked.");
            foreach (var p in expected)
                if (!Equal(p.Value, row[p.Key])) throw new QualificationMismatch("Expected mismatch at " + p.Key);
            row["passed"] = true; return row;
        }
        public static bool Equal(JsonNode? a, JsonNode? b) => a == null || b == null ? a == b : FalCanonicalJson.Hash(a) == FalCanonicalJson.Hash(b);
        public static JsonNode? Sanitize(JsonNode? node)
        {
            if (node is JsonObject obj)
            {
                var output = new JsonObject();
                foreach (var p in obj)
                    if (p.Key.IndexOf("credential", StringComparison.OrdinalIgnoreCase) < 0 && p.Key.IndexOf("api_key", StringComparison.OrdinalIgnoreCase) < 0 && p.Key.IndexOf("authorization", StringComparison.OrdinalIgnoreCase) < 0 && p.Key != "base64") output[p.Key] = Sanitize(p.Value);
                return output;
            }
            if (node is JsonArray array) return new JsonArray(array.Select(Sanitize).ToArray());
            if (node?.GetValueKind() == JsonValueKind.String && (node.GetValue<string>().StartsWith("data:", StringComparison.OrdinalIgnoreCase) || Uri.TryCreate(node.GetValue<string>(), UriKind.Absolute, out var uri) && (uri.Scheme == "https" || uri.Scheme == "http")))
                return new JsonObject { ["redacted_sha256"] = FalCanonicalJson.Hash(node) };
            return node?.DeepClone();
        }
        internal static void Write(string path, JsonObject data) { Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!); File.WriteAllText(path, data.ToJsonString(new JsonSerializerOptions { WriteIndented = true })); }
        private static string FindRepo(string path)
        {
            var root = new DirectoryInfo(Path.GetDirectoryName(Path.GetFullPath(path))!);
            while (root != null && !File.Exists(Path.Combine(root.FullName, "src/Rook.Tests/UI/Vision/configured-models.test.cjs"))) root = root.Parent;
            // CLI case data can live outside the repository; host path retains its frozen checkout.
            if (root == null) { root = new DirectoryInfo(AppContext.BaseDirectory); while (root != null && !File.Exists(Path.Combine(root.FullName, "src/Rook.Tests/UI/Vision/configured-models.test.cjs"))) root = root.Parent; }
            return root?.FullName ?? throw new ArgumentException("Cannot locate frozen surface capture programs.");
        }
        private static async Task<JsonObject> CapturePanel(string repo, string temp, JsonObject descriptor, JsonObject c, JsonObject? quote)
        {
            var config = c["panel_config"]?.DeepClone().AsObject() ?? new JsonObject();
            if (quote != null) config["quote"] = quote.DeepClone();
            Write(Path.Combine(temp, "input.json"), new JsonObject { ["descriptor"] = descriptor.DeepClone(), ["values"] = c["panel_values"]?.DeepClone() ?? new JsonObject(), ["config"] = config });
            return await RunCapture(repo, temp, Environment.GetEnvironmentVariable("ROOK_TEST_NODE") ?? "node", "src/Rook.Tests/UI/Vision/configured-models.test.cjs", "--input", "--export");
        }
        private static JsonObject CaptureGateway(string repo, string temp, string tool, JsonObject request)
        {
            var args = request.DeepClone().AsObject(); args.Remove("op");
            Write(Path.Combine(temp, "input.json"), new JsonObject { ["name"] = tool, ["arguments"] = args });
            return RunCapture(repo, temp, Environment.GetEnvironmentVariable("ROOK_TEST_PYTHON") ?? "python", "mcp_server/tests/test_image_job_mcp_tools.py", "--capture-gateway", "").GetAwaiter().GetResult();
        }
        private static async Task<JsonObject> RunCapture(string repo, string temp, string executable, string script, string inputFlag, string outputFlag)
        {
            var output = Path.Combine(temp, "output.json"); if (File.Exists(output)) File.Delete(output);
            var start = new ProcessStartInfo(executable, $"\"{Path.Combine(repo, script)}\" {inputFlag} \"{Path.Combine(temp, "input.json")}\" {outputFlag} \"{output}\"")
            { WorkingDirectory = repo, UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
            start.EnvironmentVariables["PYTHONPATH"] = Path.Combine(repo, "mcp_server/src");
            using var process = Process.Start(start)!; var stdout = process.StandardOutput.ReadToEndAsync(); var stderr = process.StandardError.ReadToEndAsync();
            if (!process.WaitForExit(30000)) { process.Kill(); throw new QualificationMismatch("Surface capture timed out."); }
            await Task.WhenAll(stdout, stderr);
            if (process.ExitCode != 0 || !File.Exists(output)) throw new QualificationMismatch("Surface capture failed: " + script);
            return JsonNode.Parse(File.ReadAllText(output))!.AsObject();
        }
        private sealed class QualificationMismatch : Exception { internal QualificationMismatch(string message) : base(message) { } }
        private sealed class FixtureObserver : IFalExecutionObserver
        {
            private readonly string? _fault;
            internal List<string> Events { get; } = new();
            internal FixtureObserver(string? fault) { if (fault is not (null or "before_upload" or "before_dispatch" or "accepted_write")) throw new ArgumentException("Unknown observer fault."); _fault = fault; }
            public Task<GenerationError?> BeforeUploadAsync(CancellationToken ct) => Before("before_upload");
            public Task<GenerationError?> BeforeDispatchAsync(CancellationToken ct) => Before("before_dispatch");
            private Task<GenerationError?> Before(string phase) { Events.Add(phase); return Task.FromResult<GenerationError?>(_fault == phase ? new GenerationError(GenerationErrorCode.InvalidRequest, "fixture admission refusal", false) : null); }
            public Task AcceptedAsync(ProviderJobHandle handle, CancellationToken ct) { Events.Add("accepted"); if (_fault == "accepted_write") throw new IOException("fixture persistence refusal"); return Task.CompletedTask; }
        }
        private sealed class FixtureTransport : HttpMessageHandler
        {
            private readonly Queue<JsonObject> _fixtures;
            internal int Calls { get; private set; }
            internal int Remaining => _fixtures.Count;
            internal JsonObject? Payload { get; private set; }
            internal string? Failure { get; private set; }
            internal FixtureTransport(JsonArray fixtures) { _fixtures = new Queue<JsonObject>(fixtures.OfType<JsonObject>()); }
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
            {
                Calls++;
                if (_fixtures.Count == 0) { Failure = "Unexpected HTTP call."; throw new HttpRequestException(); }
                var f = _fixtures.Dequeue();
                if (request.Method.Method != f["method"]!.GetValue<string>() || request.RequestUri!.AbsoluteUri != f["url"]!.GetValue<string>())
                { Failure = "Protocol method or URL mismatch."; throw new HttpRequestException(); }
                if (request.Method == HttpMethod.Post && request.RequestUri.Host.EndsWith("fal.run", StringComparison.Ordinal)) Payload = JsonNode.Parse(await request.Content!.ReadAsStringAsync())!.AsObject();
                if (f["request_json"] != null && !Equal(JsonNode.Parse(await request.Content!.ReadAsStringAsync()), f["request_json"])) { Failure = "Protocol request body mismatch."; throw new HttpRequestException(); }
                if (f["request_bytes_sha256"] != null && RuntimeFreezeManifest.HashBytes(await request.Content!.ReadAsByteArrayAsync()) != f["request_bytes_sha256"]!.GetValue<string>()) { Failure = "Uploaded media digest mismatch."; throw new HttpRequestException(); }
                if (f["exception"]?.GetValue<string>() == "network") throw new HttpRequestException();
                if (f["exception"]?.GetValue<string>() == "timeout") throw new TaskCanceledException();
                return new HttpResponseMessage((HttpStatusCode)f["status"]!.GetValue<int>()) { Content = new StringContent(f["raw_body"]?.GetValue<string>() ?? f["body"]?.ToJsonString() ?? "") };
            }
        }
    }
}
