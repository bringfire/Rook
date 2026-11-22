using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Xunit;

namespace Rook.Tests.Handlers
{
    public partial class ConfiguredFalHandlerTests
    {
        [Theory]
        [InlineData("9007199254740991")]
        [InlineData("0")]
        [InlineData(null)]
        public async Task Compiled_descriptor_panel_capture_and_provider_payload_preserve_numeric_and_default_provenance(string? rawSeed)
        {
            using var run = new HandlerRun(false, files =>
            {
                files.Operation["fields"]![0]!["default"] = "default rook";
                files.Operation["fields"]![4]!["step"] = .000001m;
                files.Operation["fields"]![5]!["default"] = "large";
            });
            var discovery = Wire(run.Read(new JsonObject { ["op"] = "list_image_models" }));
            var descriptor = discovery["models"]!.AsArray()
                .Single(m => m!["model_id"]!.GetValue<string>() == run.ModelId)!["operations"]![0]!.AsObject();
            var values = new JsonObject
            {
                ["options.audio"] = "false",
                ["options.guidance"] = "0",
                ["options.strength"] = "0.1234560000"
            };
            if (rawSeed != null) values["request.seed"] = rawSeed;

            // The Node process renders this compiled descriptor, fires actual input
            // events, clicks Generate, and records the production bridge payloads.
            var initial = await CapturePanelAsync(run.Files.Root, descriptor, values);
            var estimate = initial["estimate"]!.AsObject();
            Assert.False(estimate.ContainsKey("prompt"));
            Assert.False(estimate.ContainsKey("resolution"));
            Assert.Equal(rawSeed != null, estimate.ContainsKey("seed"));
            Assert.Equal(.123456m, estimate["options"]!["strength"]!.GetValue<decimal>());
            var quoted = run.Read(estimate);
            Assert.True(quoted.Success, Wire(quoted).ToJsonString());
            Assert.Equal(0, run.Transport.Posts);

            // Re-render with the exact managed quote, so the UI's submitted JSON
            // (including fingerprint/cap) is consumed without reconstructing it.
            var captured = await CapturePanelAsync(run.Files.Root, descriptor, values, Wire(quoted));
            Assert.Equal(estimate.ToJsonString(), captured["estimate"]!.ToJsonString());
            var submitted = await run.Submit(captured["submit"]!.AsObject());
            Assert.True(submitted.Success, Wire(submitted).ToJsonString());
            await run.WaitComplete(Wire(submitted)["job_id"]!.GetValue<string>());
            Assert.Equal(1, run.Transport.Posts);
            var payload = run.Transport.Payload!;
            Assert.Equal(rawSeed == null ? 0 : decimal.Parse(rawSeed, System.Globalization.CultureInfo.InvariantCulture), payload["seed"]!.GetValue<decimal>());
            Assert.Equal(.123456m, payload["strength"]!.GetValue<decimal>());
            Assert.Equal(0m, payload["guidance"]!.GetValue<decimal>());
            Assert.False(payload["audio"]!.GetValue<bool>());
            Assert.Equal("default rook", payload["prompt"]!.GetValue<string>());
            Assert.Equal("L", payload["size"]!.GetValue<string>());
        }

        [Theory]
        [InlineData("request.seed", "9007199254740993")]
        [InlineData("options.strength", "0.1234567890123456789012345678")]
        public async Task Compiled_descriptor_panel_capture_rejects_lossy_raw_text_before_estimate(string field, string text)
        {
            using var run = new HandlerRun(false);
            var discovery = Wire(run.Read(new JsonObject { ["op"] = "list_image_models" }));
            var descriptor = discovery["models"]!.AsArray()
                .Single(m => m!["model_id"]!.GetValue<string>() == run.ModelId)!["operations"]![0]!.AsObject();
            var capture = await CapturePanelAsync(run.Files.Root, descriptor, new JsonObject { [field] = text });
            Assert.Null(capture["estimate"]);
            Assert.Null(capture["submit"]);
            Assert.Contains(field, capture["errors"]!.GetValue<string>());
            Assert.Equal(0, run.Transport.Posts);
        }

        private static async Task<JsonObject> CapturePanelAsync(string directory, JsonObject descriptor, JsonObject values, JsonObject? quote = null)
        {
            var root = new DirectoryInfo(AppContext.BaseDirectory);
            const string relativeScript = "src/Rook.Tests/UI/Vision/configured-models.test.cjs";
            while (root != null && !File.Exists(Path.Combine(root.FullName, relativeScript))) root = root.Parent;
            Assert.NotNull(root);
            var script = Path.Combine(root!.FullName, relativeScript);
            var input = Path.Combine(directory, "panel-input.json");
            var output = Path.Combine(directory, "panel-output.json");
            File.WriteAllText(input, new JsonObject
            {
                ["descriptor"] = descriptor.DeepClone(),
                ["values"] = values.DeepClone(),
                ["config"] = quote == null ? new JsonObject() : new JsonObject { ["quote"] = quote.DeepClone() }
            }.ToJsonString());
            using var process = Process.Start(new ProcessStartInfo
            {
                FileName = Environment.GetEnvironmentVariable("ROOK_TEST_NODE") ?? "node",
                Arguments = $"\"{script}\" --input \"{input}\" --export \"{output}\"",
                WorkingDirectory = root.FullName,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            });
            Assert.NotNull(process);
            var stdout = process!.StandardOutput.ReadToEndAsync();
            var stderr = process.StandardError.ReadToEndAsync();
            if (!process.WaitForExit(15000))
            {
                process.Kill();
                Assert.Fail("Panel capture Node process exceeded fifteen seconds.");
            }
            var standardOutput = await stdout;
            var standardError = await stderr;
            Assert.True(process.ExitCode == 0, $"Required Node panel capture failed ({process.ExitCode}): {standardOutput} {standardError}. Set ROOK_TEST_NODE or put node on PATH.");
            Assert.Equal("", standardOutput);
            Assert.Equal("", standardError);
            return JsonNode.Parse(File.ReadAllText(output))!.AsObject();
        }
    }
}
