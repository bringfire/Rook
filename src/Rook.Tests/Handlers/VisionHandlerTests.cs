using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Vision;
using Xunit;

namespace Rook.Tests.Handlers
{
    /// <summary>
    /// Pure-helper tests for <see cref="VisionHandler"/>.
    ///
    /// Dispatch-level tests are NOT here — instantiating VisionHandler and
    /// calling Dispatch triggers RhinoCommon assembly resolution (via
    /// DocumentContext and RhinoApp), which fails in the xUnit test host
    /// where RhinoCommon is not on the probe path. Dispatch-level
    /// validation is covered by the live Python tests at
    /// <c>mcp_server/tests/test_vision_routes_live.py</c>, which run
    /// against a real Rhino instance.
    ///
    /// Covered here:
    /// - Artifact kind constants (pinned strings; changing them
    ///   invalidates previously stored artifacts)
    /// - Validation helpers: ValidateResolution, ParseObjectBody,
    ///   RequireString
    /// - No-secret-leakage: GenericizeProviderError sanitizes API-key
    ///   query parameters from echoed URLs in provider error text
    /// - DPAPI roundtrip: <see cref="VisionSecretStoreTests"/>
    /// </summary>
    public class VisionHandlerTests
    {
        // ─── Artifact kind constants ────────────────────────────────────

        [Fact]
        public void ArtifactKinds_ArePinned()
        {
            Assert.Equal("generated_image", VisionHandler.ArtifactKindGeneratedImage);
            Assert.Equal("enhanced_prompt", VisionHandler.ArtifactKindEnhancedPrompt);
            Assert.Equal("depth_map", VisionHandler.ArtifactKindDepthMap);
        }

        // ─── Input bound constants ──────────────────────────────────────

        [Fact]
        public void InputBounds_ArePinned()
        {
            Assert.Equal(16_000, VisionHandler.MaxPromptLength);
            Assert.Equal(4_000, VisionHandler.MaxContextLength);
            Assert.Equal(10L * 1024 * 1024, VisionHandler.MaxInputImageBytes);
            Assert.Equal(8, VisionHandler.MaxReferenceImages);
            Assert.Equal(15L * 1024 * 1024, VisionHandler.MaxAggregateImageBytes);
            Assert.Equal(4096, VisionHandler.MaxDepthMaxEdge);
            Assert.Equal(1024, VisionHandler.DefaultDepthMaxEdge);
        }

        [Fact]
        public void AggregateCap_IsBelowGeminiInlinePayloadLimit()
        {
            // Gemini's inline-payload guidance is ~20 MB per request;
            // after base64 expansion (~1.33x) and JSON envelope overhead,
            // the raw aggregate must stay under 20 MB. 15 MB raw = ~20 MB
            // base64 leaves safety margin.
            const long GeminiInlineLimit = 20L * 1024 * 1024;
            Assert.True(
                VisionHandler.MaxAggregateImageBytes < GeminiInlineLimit,
                "Aggregate cap must leave headroom under Gemini's inline limit.");
        }

        [Fact]
        public void AggregateCap_IsGreaterThanPerFileCap()
        {
            // Nonsense otherwise — aggregate must accommodate at least
            // one max-sized primary image.
            Assert.True(
                VisionHandler.MaxAggregateImageBytes >= VisionHandler.MaxInputImageBytes,
                "Aggregate cap must accommodate at least one max-sized image.");
        }

        // ─── Resolution validation ──────────────────────────────────────

        [Theory]
        [InlineData("1K")]
        [InlineData("2K")]
        [InlineData("4K")]
        [InlineData("1k")]   // case-insensitive
        [InlineData("2k")]
        [InlineData("")]     // empty is "caller didn't specify"; allowed
        public void ValidateResolution_AllowedValues_NoThrow(string resolution)
        {
            VisionHandler.ValidateResolution(resolution);
        }

        [Theory]
        [InlineData("8K")]
        [InlineData("HD")]
        [InlineData("1080p")]
        [InlineData("bogus")]
        public void ValidateResolution_RejectedValues_Throw(string resolution)
        {
            var ex = Assert.Throws<ArgumentException>(
                () => VisionHandler.ValidateResolution(resolution));
            Assert.Contains("resolution", ex.Message, StringComparison.OrdinalIgnoreCase);
        }

        // ─── GenericizeProviderError: no secret leakage ─────────────────
        // Gemini URLs embed the API key as ?key=... — if an error response
        // echoes the URL, the key could leak into our envelope. These
        // tests pin the sanitizer so regressions are caught.

        [Fact]
        public void GenericizeProviderError_RedactsKeyInUrl()
        {
            var raw = "Error calling https://generativelanguage.googleapis.com/" +
                      "v1beta/models/gemini-3.1-flash-image-preview:generateContent" +
                      "?key=AIzaSyExample_SecretKey12345";
            var sanitized = VisionHandler.GenericizeProviderError(raw);
            Assert.DoesNotContain("AIzaSyExample_SecretKey12345", sanitized);
            Assert.Contains("REDACTED", sanitized);
        }

        [Fact]
        public void GenericizeProviderError_RedactsKeyInAmpersandUrl()
        {
            var raw = "URL: https://example.com/api?foo=bar&key=SECRET_12345&baz=qux";
            var sanitized = VisionHandler.GenericizeProviderError(raw);
            Assert.DoesNotContain("SECRET_12345", sanitized);
            Assert.Contains("REDACTED", sanitized);
        }

        [Fact]
        public void GenericizeProviderError_CaseInsensitiveKeyParam()
        {
            var raw = "Error: ?Key=SHOULD_ALSO_REDACT";
            var sanitized = VisionHandler.GenericizeProviderError(raw);
            Assert.DoesNotContain("SHOULD_ALSO_REDACT", sanitized);
        }

        [Fact]
        public void GenericizeProviderError_NullOrEmpty_ReturnsPlaceholder()
        {
            Assert.Equal("(no detail)", VisionHandler.GenericizeProviderError(null));
            Assert.Equal("(no detail)", VisionHandler.GenericizeProviderError(""));
        }

        [Fact]
        public void GenericizeProviderError_TruncatesLongMessages()
        {
            var raw = new string('x', 1000);
            var sanitized = VisionHandler.GenericizeProviderError(raw);
            Assert.True(sanitized.Length <= 520,
                $"Sanitized length {sanitized.Length} exceeded cap.");
            Assert.Contains("truncated", sanitized);
        }

        [Fact]
        public void GenericizeProviderError_NoKey_LeavesMessageAlone()
        {
            var raw = "plain error with no key parameter at all";
            var sanitized = VisionHandler.GenericizeProviderError(raw);
            Assert.Equal(raw, sanitized);
        }

        // ─── ParseObjectBody ────────────────────────────────────────────

        [Fact]
        public void ParseObjectBody_NullEmpty_ReturnsEmpty()
        {
            Assert.Empty(VisionHandler.ParseObjectBody(null));
            Assert.Empty(VisionHandler.ParseObjectBody(""));
        }

        [Fact]
        public void ParseObjectBody_MalformedJson_ThrowsArgumentException()
        {
            var ex = Assert.Throws<ArgumentException>(
                () => VisionHandler.ParseObjectBody("{not-json"));
            Assert.Contains("Invalid JSON", ex.Message);
        }

        [Fact]
        public void ParseObjectBody_ValidObject_ReturnsFields()
        {
            var body = JsonSerializer.Serialize(new { op = "generate", prompt = "x" });
            var args = VisionHandler.ParseObjectBody(body);
            Assert.Equal(2, args.Count);
            Assert.True(args.ContainsKey("op"));
            Assert.True(args.ContainsKey("prompt"));
        }

        // ─── RequireString ──────────────────────────────────────────────

        [Fact]
        public void RequireString_Present_ReturnsValue()
        {
            var args = VisionHandler.ParseObjectBody("{\"x\":\"hello\"}");
            Assert.Equal("hello", VisionHandler.RequireString(args, "x", 100));
        }

        [Fact]
        public void RequireString_Missing_Throws()
        {
            var args = VisionHandler.ParseObjectBody("{}");
            var ex = Assert.Throws<ArgumentException>(
                () => VisionHandler.RequireString(args, "x", 100));
            Assert.Contains("x", ex.Message);
        }

        [Fact]
        public void RequireString_WrongType_Throws()
        {
            var args = VisionHandler.ParseObjectBody("{\"x\":42}");
            Assert.Throws<ArgumentException>(
                () => VisionHandler.RequireString(args, "x", 100));
        }

        [Fact]
        public void RequireString_Empty_Throws()
        {
            var args = VisionHandler.ParseObjectBody("{\"x\":\"\"}");
            Assert.Throws<ArgumentException>(
                () => VisionHandler.RequireString(args, "x", 100));
        }

        [Fact]
        public void RequireString_OverLength_Throws()
        {
            var big = "\"" + new string('a', 101) + "\"";
            var args = VisionHandler.ParseObjectBody("{\"x\":" + big + "}");
            var ex = Assert.Throws<ArgumentException>(
                () => VisionHandler.RequireString(args, "x", 100));
            Assert.Contains("length", ex.Message, StringComparison.OrdinalIgnoreCase);
        }

        // ─── RequireArtifactId (PR-5b) ──────────────────────────────────

        [Fact]
        public void RequireArtifactId_Present_ReturnsGuid()
        {
            var id = Guid.NewGuid();
            var args = VisionHandler.ParseObjectBody(
                "{\"artifact_id\":\"" + id.ToString("D") + "\"}");
            Assert.Equal(id, VisionHandler.RequireArtifactId(args));
        }

        [Fact]
        public void RequireArtifactId_Missing_Throws()
        {
            var args = VisionHandler.ParseObjectBody("{}");
            var ex = Assert.Throws<ArgumentException>(
                () => VisionHandler.RequireArtifactId(args));
            Assert.Contains("artifact_id", ex.Message);
        }

        [Fact]
        public void RequireArtifactId_WrongType_Throws()
        {
            var args = VisionHandler.ParseObjectBody("{\"artifact_id\":42}");
            Assert.Throws<ArgumentException>(
                () => VisionHandler.RequireArtifactId(args));
        }

        [Fact]
        public void RequireArtifactId_Empty_Throws()
        {
            var args = VisionHandler.ParseObjectBody("{\"artifact_id\":\"\"}");
            Assert.Throws<ArgumentException>(
                () => VisionHandler.RequireArtifactId(args));
        }

        [Theory]
        [InlineData("not-a-guid")]
        [InlineData("12345")]
        [InlineData("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")]
        public void RequireArtifactId_Malformed_Throws(string bad)
        {
            var args = VisionHandler.ParseObjectBody(
                "{\"artifact_id\":\"" + bad + "\"}");
            var ex = Assert.Throws<ArgumentException>(
                () => VisionHandler.RequireArtifactId(args));
            Assert.Contains("GUID", ex.Message);
        }

        // ─── GetBoolArg (PR-5b) ─────────────────────────────────────────

        [Theory]
        [InlineData("{\"approved\":true}", true)]
        [InlineData("{\"approved\":false}", false)]
        public void GetBoolArg_BooleanValue_Returned(string json, bool expected)
        {
            var args = VisionHandler.ParseObjectBody(json);
            Assert.Equal(expected, VisionHandler.GetBoolArg(args, "approved"));
        }

        [Theory]
        [InlineData("{}")]
        [InlineData("{\"approved\":\"true\"}")]       // string "true" is NOT bool
        [InlineData("{\"approved\":1}")]              // number 1 is NOT bool
        [InlineData("{\"approved\":null}")]
        public void GetBoolArg_NonBoolean_ReturnsNull(string json)
        {
            var args = VisionHandler.ParseObjectBody(json);
            Assert.Null(VisionHandler.GetBoolArg(args, "approved"));
        }

        // ─── IsApproved (PR-5b) ─────────────────────────────────────────

        [Fact]
        public void IsApproved_FlagTrue_ReturnsTrue()
        {
            var artifact = MakeArtifactWithFlags(
                new Dictionary<string, JsonNode?> { ["approved"] = JsonValue.Create(true) });
            Assert.True(VisionHandler.IsApproved(artifact));
        }

        [Fact]
        public void IsApproved_FlagFalse_ReturnsFalse()
        {
            var artifact = MakeArtifactWithFlags(
                new Dictionary<string, JsonNode?> { ["approved"] = JsonValue.Create(false) });
            Assert.False(VisionHandler.IsApproved(artifact));
        }

        [Fact]
        public void IsApproved_FlagMissing_ReturnsFalse()
        {
            var artifact = MakeArtifactWithFlags(new Dictionary<string, JsonNode?>());
            Assert.False(VisionHandler.IsApproved(artifact));
        }

        [Fact]
        public void IsApproved_FlagNotBool_ReturnsFalse()
        {
            // Defensive: a flag value of a non-bool type (e.g. string)
            // should not throw — a best-effort "false" is correct.
            var artifact = MakeArtifactWithFlags(
                new Dictionary<string, JsonNode?> { ["approved"] = JsonValue.Create("yes") });
            Assert.False(VisionHandler.IsApproved(artifact));
        }

        [Fact]
        public void IsApproved_FlagNull_ReturnsFalse()
        {
            var artifact = MakeArtifactWithFlags(
                new Dictionary<string, JsonNode?> { ["approved"] = null });
            Assert.False(VisionHandler.IsApproved(artifact));
        }

        private static Artifact MakeArtifactWithFlags(
            IReadOnlyDictionary<string, JsonNode?> flags)
        {
            return new Artifact(
                Id: Guid.NewGuid(),
                Kind: "generated_image",
                CreatedAt: DateTimeOffset.UtcNow,
                Files: new[] { new ArtifactFile("image", "image.png") },
                ParentIds: Array.Empty<Guid>(),
                Metadata: new Dictionary<string, JsonNode?>(),
                Flags: flags);
        }
    }

    /// <summary>
    /// DPAPI roundtrip tests for <see cref="VisionSecretStore"/>. DPAPI is
    /// CurrentUser-scoped; these tests assume the test runner is the same
    /// user profile that would read the key in production (trivially true
    /// for a local test run).
    ///
    /// No RhinoCommon references — this class stays loadable in the bare
    /// xUnit host.
    /// </summary>
    public class VisionSecretStoreTests : IDisposable
    {
        private readonly string _tempDir;
        private readonly string _settingsPath;
        private readonly RookSettingsStore _settings;
        private readonly VisionSecretStore _store;

        public VisionSecretStoreTests()
        {
            _tempDir = Path.Combine(Path.GetTempPath(),
                "rook-vision-secrets-" + Guid.NewGuid().ToString("N").Substring(0, 8));
            Directory.CreateDirectory(_tempDir);
            _settingsPath = Path.Combine(_tempDir, "settings.json");
            _settings = new RookSettingsStore(_settingsPath);
            _store = new VisionSecretStore(_settings);
        }

        public void Dispose()
        {
            try { Directory.Delete(_tempDir, recursive: true); } catch { }
        }

        [Fact]
        public void NoKey_GetReturnsNull()
        {
            Assert.Null(_store.GetGeminiApiKey());
            Assert.False(_store.HasGeminiApiKey());
        }

        [Fact]
        public void SetThenGet_RoundtripsPlaintext()
        {
            const string plaintext = "AIzaSyExample_KeyForTestsOnly_12345";
            _store.SetGeminiApiKey(plaintext);
            Assert.True(_store.HasGeminiApiKey());
            Assert.Equal(plaintext, _store.GetGeminiApiKey());
        }

        [Fact]
        public void SetWithEmpty_Throws()
        {
            Assert.Throws<ArgumentException>(() => _store.SetGeminiApiKey(""));
            Assert.Throws<ArgumentException>(() => _store.SetGeminiApiKey(null!));
        }

        [Fact]
        public void PersistedCiphertext_IsNotPlaintext()
        {
            const string plaintext = "verysecretkey-should-not-appear-in-file";
            _store.SetGeminiApiKey(plaintext);

            var fileContent = File.ReadAllText(_settingsPath);
            Assert.DoesNotContain(plaintext, fileContent);
        }

        [Fact]
        public void Clear_RemovesKey()
        {
            _store.SetGeminiApiKey("whatever");
            Assert.True(_store.HasGeminiApiKey());
            _store.ClearGeminiApiKey();
            Assert.False(_store.HasGeminiApiKey());
            Assert.Null(_store.GetGeminiApiKey());
        }

        [Fact]
        public void Clear_WhenEmpty_NoThrow()
        {
            _store.ClearGeminiApiKey();
            Assert.False(_store.HasGeminiApiKey());
        }

        [Fact]
        public void MalformedBase64_GetThrowsGenericMessage()
        {
            var section = new VisionSettings { GeminiApiKeyEncrypted = "not!valid@base64===" };
            _settings.SaveSection("vision", section);

            var ex = Assert.Throws<InvalidOperationException>(
                () => _store.GetGeminiApiKey());
            Assert.Contains("base64", ex.Message, StringComparison.OrdinalIgnoreCase);
            // The stored (malformed) value must not appear in the error.
            Assert.DoesNotContain("not!valid@base64", ex.Message);
        }

        [Fact]
        public void ValidBase64ButWrongCiphertext_GetThrowsGenericMessage()
        {
            // Valid base64 but not DPAPI-produced ciphertext — exercises
            // the CryptographicException catch.
            var bogus = Convert.ToBase64String(new byte[] { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 });
            var section = new VisionSettings { GeminiApiKeyEncrypted = bogus };
            _settings.SaveSection("vision", section);

            var ex = Assert.Throws<InvalidOperationException>(
                () => _store.GetGeminiApiKey());
            Assert.Contains("Unable to decrypt", ex.Message);
            // No raw exception detail must leak.
            Assert.DoesNotContain("CryptographicException", ex.Message);
        }

        [Fact]
        public void SetTwice_OverwritesExisting()
        {
            _store.SetGeminiApiKey("first");
            _store.SetGeminiApiKey("second");
            Assert.Equal("second", _store.GetGeminiApiKey());
        }
    }
}
