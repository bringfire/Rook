using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Vision;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    public class MissingKeyErrorParityTests : IDisposable
    {
        internal const string MissingGeminiGenerateKeyMessage =
            "Gemini API key is not configured. Set it via the Vision settings " +
            "before calling /vision/generate.";

        internal const string MissingGeminiEnhancePromptKeyMessage =
            "Configure a Gemini or fal.ai API key in Vision settings " +
            "before calling /vision/enhance-prompt.";

        private readonly string _tempDir;
        private readonly IGenerationSecretStore _secrets;

        public MissingKeyErrorParityTests()
        {
            _tempDir = Path.Combine(Path.GetTempPath(),
                "rook-missing-key-parity-" + Guid.NewGuid().ToString("N").Substring(0, 8));
            Directory.CreateDirectory(_tempDir);
            _secrets = new DpapiGenerationSecretStore(
                new RookSettingsStore(Path.Combine(_tempDir, "settings.json")));
        }

        public void Dispose()
        {
            try { Directory.Delete(_tempDir, recursive: true); } catch { }
        }

        [Fact]
        public async Task GenerateAsync_withoutEitherKey_projectsMissingFalWithGeminiFallbackReceipt()
        {
            var inputPath = Path.Combine(_tempDir, "input.png");
            File.WriteAllBytes(inputPath, new byte[] { 9, 8, 7 });

            var handler = NewHandler();
            var args = ParseArgs($$"""
                {
                  "prompt": "make this rendering warmer",
                  "input_image_path": "{{inputPath.Replace("\\", "\\\\")}}",
                  "model": "nano-banana-2",
                  "resolution": "1K",
                  "aspect_ratio": "16:9"
                }
                """);

            var response = await handler.GenerateAsync(args, CancellationToken.None);

            Assert.False(response.Success);
            var data = System.Text.Json.Nodes.JsonNode.Parse(JsonSerializer.Serialize(response.Data))!;
            Assert.Equal("fal", data["provider"]!.GetValue<string>());
            Assert.Equal("missing", data["credential_failure"]!["kind"]!.GetValue<string>());
            Assert.Equal("gemini_key_missing", data["image_route"]!["fallback_reason"]!.GetValue<string>());
            Assert.False(data["image_route"]!["generation_dispatch_attempted"]!.GetValue<bool>());
        }

        [Fact]
        public async Task EnhancePromptAsync_withoutEitherKey_explainsBothSupportedCredentials()
        {
            var handler = NewHandler();
            var args = ParseArgs("""
                {
                  "prompt": "make this prompt better"
                }
                """);

            var response = await handler.EnhancePromptAsync(args, CancellationToken.None);

            Assert.False(response.Success);
            Assert.Equal(MissingGeminiEnhancePromptKeyMessage, response.Data);
        }

        private VisionHandler NewHandler() =>
            new(
                new ArtifactStore(Path.Combine(_tempDir, "artifacts")),
                _secrets,
                new PromptEnhancer(),
                new ViewportHandler());

        private static Dictionary<string, JsonElement> ParseArgs(string json) =>
            JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(json)
            ?? new Dictionary<string, JsonElement>();
    }
}
