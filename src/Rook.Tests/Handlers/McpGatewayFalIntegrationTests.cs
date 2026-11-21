using System;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Rook.Handlers;
using Xunit;

namespace Rook.Tests.Handlers
{
    // Share the existing fake-fal handler fixture without changing its implementation.
    public partial class ConfiguredFalHandlerTests
    {
        [Theory]
        [InlineData(false, false)] [InlineData(false, true)]
        [InlineData(true, false)] [InlineData(true, true)]
        public async Task Mcp_gateway_capture_reaches_managed_defaults_and_fake_fal(bool video, bool modelOnly)
        {
            using var run = new HandlerRun(video, files =>
            {
                if (video)
                    files.Operation["fields"]!.AsArray().Add(JsonNode.Parse("""
                        {"key":"seed","scope":"request","type":"integer","min":-9007199254740991,"max":9007199254740991,"label":"Seed","payload":{"pointer":"/seed","conversion":"identity"}}
                        """));
                else
                    files.Operation["fields"]![0]!["default"] = "gateway default";
            });
            var caller = modelOnly ? new JsonObject { ["model"] = run.ModelId } : run.Request();
            if (video && !modelOnly) caller["seed"] = 9007199254740991L;
            var estimateTool = video ? "rhino_video_estimate" : "rhino_image_estimate";
            var submitTool = video ? "rhino_render_video" : "rhino_generate_image";
            var captured = CaptureMcpGateway(run.Files.Root, estimateTool, caller);
            Assert.Equal(caller.ToJsonString(), captured["arguments"]!.ToJsonString());
            Assert.Equal(new[] { "model" }, JsonSerializer.Deserialize<string[]>(captured["input_schema"]!["required"]!.ToJsonString()));
            var estimatedRequest = captured["arguments"]!.DeepClone().AsObject();
            estimatedRequest["op"] = video ? VideoOpHandler.OpEstimate : "image_estimate";
            var estimated = run.Read(estimatedRequest);
            Assert.True(estimated.Success, JsonSerializer.Serialize(estimated.Data));
            var quote = Wire(estimated);
            Assert.Equal(0, run.Transport.Posts);
            var confirmed = captured["arguments"]!.DeepClone().AsObject();
            confirmed["quote_fingerprint"] = quote["quote_fingerprint"]!.DeepClone();
            confirmed["max_estimated_cost_usd"] = quote["max_estimated_cost_usd"]!.DeepClone();
            var submittedCapture = CaptureMcpGateway(run.Files.Root, submitTool, confirmed);
            var capturedConfirmation = submittedCapture["arguments"]!.DeepClone().AsObject();
            Assert.Equal(.000001m, capturedConfirmation["max_estimated_cost_usd"]!.GetValue<decimal>());
            // Python may serialize 0.000001 as 1e-06; retain numeric value/type,
            // rather than requiring one JSON number spelling.
            capturedConfirmation.Remove("max_estimated_cost_usd");
            var expectedConfirmation = confirmed.DeepClone().AsObject();
            expectedConfirmation.Remove("max_estimated_cost_usd");
            Assert.Equal(expectedConfirmation.ToJsonString(), capturedConfirmation.ToJsonString());
            var submittedRequest = submittedCapture["arguments"]!.DeepClone().AsObject();
            submittedRequest["op"] = video ? VideoOpHandler.OpSubmit : "image_generate_start";
            var submitted = await run.Submit(submittedRequest);
            Assert.True(submitted.Success, JsonSerializer.Serialize(submitted.Data));
            await run.WaitComplete(Wire(submitted)["job_id"]!.GetValue<string>());
            Assert.Equal(1, run.Transport.Posts);
            if (video)
            {
                Assert.Equal(modelOnly ? 5m : 6.5m, run.Transport.Payload!["duration"]!.GetValue<decimal>());
                if (!modelOnly) Assert.Equal(9007199254740991L, run.Transport.Payload["seed"]!.GetValue<long>());
            }
            else if (modelOnly)
            {
                Assert.Equal("gateway default", run.Transport.Payload!["prompt"]!.GetValue<string>());
                Assert.Equal(0, run.Transport.Payload["seed"]!.GetValue<int>());
                Assert.Equal("S", run.Transport.Payload["size"]!.GetValue<string>());
            }
            else
            {
                Assert.Equal(9007199254740991L, run.Transport.Payload!["seed"]!.GetValue<long>());
                Assert.Equal(.7m, run.Transport.Payload["strength"]!.GetValue<decimal>());
                Assert.Equal(7.5m, run.Transport.Payload["guidance"]!.GetValue<decimal>());
                Assert.False(run.Transport.Payload["audio"]!.GetValue<bool>());
            }
            Assert.Equal(0, run.Resources.ActiveBundles);
            SaveMcpGatewayEvidence((video ? "video" : "image") + (modelOnly ? "-defaults" : "-controls"),
                new JsonObject {
                    ["discovery"] = Wire(run.Read(new JsonObject { ["op"] = video ? "list_video_models" : "list_image_models" })),
                    ["estimate_capture"] = captured,
                    ["submit_capture"] = submittedCapture,
                    ["provider_payload"] = run.Transport.Payload!.DeepClone(),
                });
        }

        [Fact]
        public void Mcp_gateway_legacy_omission_is_rejected_by_managed_validation()
        {
            using var run = new HandlerRun(true);
            var captured = CaptureMcpGateway(run.Files.Root, "rhino_video_estimate",
                new JsonObject { ["model"] = "veo-3.1-fast-generate-preview" });
            var request = captured["arguments"]!.DeepClone().AsObject();
            Assert.Single(request);
            request["op"] = VideoOpHandler.OpEstimate;
            var response = run.Read(request);
            Assert.False(response.Success);
            Assert.Equal("mode", Wire(response)["field"]!.GetValue<string>());
            Assert.Equal(0, run.Transport.Posts);
            SaveMcpGatewayEvidence("legacy-rejection", new JsonObject {
                ["estimate_capture"] = captured, ["managed_error"] = Wire(response),
            });
        }

        private static void SaveMcpGatewayEvidence(string name, JsonObject evidence)
        {
            var directory = Environment.GetEnvironmentVariable("ROOK_TEST_FAL_GATEWAY_CAPTURE_DIR");
            if (string.IsNullOrWhiteSpace(directory)) return;
            Directory.CreateDirectory(directory);
            File.WriteAllText(Path.Combine(directory, "gateway-" + name + ".json"), evidence.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
        }

        private static JsonObject CaptureMcpGateway(string temporaryRoot, string tool, JsonObject arguments)
        {
            var repository = new DirectoryInfo(AppContext.BaseDirectory);
            while (repository != null && !File.Exists(Path.Combine(repository.FullName, "mcp_server", "tests", "test_image_job_mcp_tools.py")))
                repository = repository.Parent;
            Assert.NotNull(repository);
            var python = Environment.GetEnvironmentVariable("ROOK_TEST_PYTHON");
            if (string.IsNullOrWhiteSpace(python))
            {
                var localPython = Path.Combine(repository!.FullName, "mcp_server", ".venv", "Scripts", "python.exe");
                python = File.Exists(localPython) ? localPython : "python";
            }
            var input = Path.Combine(temporaryRoot, "gateway-input.json");
            var output = Path.Combine(temporaryRoot, "gateway-output.json");
            if (File.Exists(output)) File.Delete(output);
            File.WriteAllText(input, new JsonObject { ["name"] = tool, ["arguments"] = arguments.DeepClone() }.ToJsonString());
            var script = Path.Combine(repository!.FullName, "mcp_server", "tests", "test_image_job_mcp_tools.py");
            var start = new ProcessStartInfo(python!, $"\"{script}\" --capture-gateway \"{input}\" \"{output}\"")
            {
                WorkingDirectory = repository.FullName,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            start.EnvironmentVariables["PYTHONPATH"] = Path.Combine(repository.FullName, "mcp_server", "src");
            using var process = Process.Start(start);
            Assert.NotNull(process);
            var stdout = process!.StandardOutput.ReadToEndAsync();
            var stderr = process.StandardError.ReadToEndAsync();
            if (!process.WaitForExit(30000)) { process.Kill(); Assert.Fail("MCP gateway capture exceeded 30 seconds."); }
            Assert.True(process.ExitCode == 0, "Gateway capture failed; set ROOK_TEST_PYTHON to the repository dependency environment. " + stdout.Result + stderr.Result);
            Assert.True(File.Exists(output), "Actual MCP gateway capture did not produce its forwarded JSON.");
            return JsonNode.Parse(File.ReadAllText(output))!.AsObject();
        }
    }
}
