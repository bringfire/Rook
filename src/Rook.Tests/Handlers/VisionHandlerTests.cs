using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
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
            Assert.Equal("captured_viewport", VisionHandler.ArtifactKindCapturedViewport);
        }

        [Fact]
        public void BuildArtifactCountsByKind_IncludesAllVisionKinds()
        {
            var tempDir = Path.Combine(Path.GetTempPath(),
                "rook-vision-artifact-counts-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(tempDir);
            try
            {
                var artifactStore = new ArtifactStore(tempDir);
                artifactStore.Create(
                    VisionHandler.ArtifactKindGeneratedImage,
                    new[] { new BlobInput("image", new byte[] { 1 }, "png") });
                artifactStore.Create(
                    VisionHandler.ArtifactKindGeneratedImage,
                    new[] { new BlobInput("image", new byte[] { 2 }, "png") });
                artifactStore.Create(
                    VisionHandler.ArtifactKindCapturedViewport,
                    new[] { new BlobInput("image", new byte[] { 3 }, "png") });
                artifactStore.Create(
                    VisionHandler.ArtifactKindEnhancedPrompt,
                    new[] { new BlobInput("prompt", new byte[] { 4 }, "json") });

                var counts = VisionHandler.BuildArtifactCountsByKind(artifactStore.List());

                Assert.Equal(2, counts[VisionHandler.ArtifactKindGeneratedImage]);
                Assert.Equal(1, counts[VisionHandler.ArtifactKindCapturedViewport]);
                Assert.Equal(1, counts[VisionHandler.ArtifactKindEnhancedPrompt]);
                Assert.Equal(0, counts[VisionHandler.ArtifactKindDepthMap]);
            }
            finally
            {
                try { Directory.Delete(tempDir, recursive: true); } catch { }
            }
        }

        [Fact]
        public void BuildOpenFolderStartInfo_UsesShellExecuteForCanonicalFolderPath()
        {
            var path = Path.Combine(Path.GetTempPath(), "rook-vision-artifacts-test");

            var psi = VisionHandler.BuildOpenFolderStartInfo(path);

            Assert.Equal(Path.GetFullPath(path), psi.FileName);
            Assert.True(psi.UseShellExecute);
        }

        // ─── Model catalog + short-name resolution ──────────────────────

        [Fact]
        public void Models_AvailableCatalog_OffersTwoPaidOnlyEntries()
        {
            // The UI dropdown is populated from AvailableModels. Changing
            // the count or the short-name set is a user-visible change —
            // surface it as a test diff, not a silent drop.
            var shortNames = GeminiClient.Models.AvailableModels
                .Select(m => (string?)m["short_name"])
                .ToList();
            Assert.Equal(2, shortNames.Count);
            Assert.Contains("nano-banana-2", shortNames);
            Assert.Contains("nano-banana-pro", shortNames);
        }

        [Fact]
        public void Models_AvailableCatalog_AdvertisesModelSpecificResolutions()
        {
            var byShortName = GeminiClient.Models.AvailableModels
                .ToDictionary(m => (string)m["short_name"]!);

            var flashResolutions = Assert.IsAssignableFrom<IEnumerable<string>>(
                byShortName["nano-banana-2"]["supported_resolutions"]);
            Assert.Contains("512", flashResolutions);
            Assert.Contains("1K", flashResolutions);
            Assert.Contains("2K", flashResolutions);
            Assert.Contains("4K", flashResolutions);

            var proResolutions = Assert.IsAssignableFrom<IEnumerable<string>>(
                byShortName["nano-banana-pro"]["supported_resolutions"]);
            Assert.DoesNotContain("512", proResolutions);
            Assert.Contains("1K", proResolutions);
            Assert.Contains("2K", proResolutions);
            Assert.Contains("4K", proResolutions);
        }

        [Fact]
        public void Models_ResolutionMetadata_SeparatesCommonFromModelSpecificValues()
        {
            Assert.Equal(new[] { "1K", "2K", "4K" }, VisionHandler.CommonResolutions);

            var byModel = VisionHandler.SupportedResolutionsByModelShortName();
            Assert.Equal(
                new[] { "512", "1K", "2K", "4K" },
                byModel["nano-banana-2"]);
            Assert.Equal(
                new[] { "1K", "2K", "4K" },
                byModel["nano-banana-pro"]);
        }

        [Fact]
        public void Models_AvailableCatalog_DoesNotExposeFreeTier()
        {
            // Regression: free-tier models are deliberately NOT exposed
            // because API keys can't invoke free-tier endpoints —
            // including them would only generate 429s. A future addition
            // must be an explicit decision documented on the catalog.
            var shortNames = GeminiClient.Models.AvailableModels
                .Select(m => (string?)m["short_name"] ?? "")
                .ToList();
            Assert.DoesNotContain(shortNames, n => n.Contains("2.5-flash"));
            Assert.DoesNotContain(shortNames, n => n.Contains("free"));
        }

        [Fact]
        public void Models_DefaultShortName_MatchesShortNameToIdEntry()
        {
            // The UI selects the "default" option by matching the
            // overview's default_model string against each option's
            // value. If DefaultShortName isn't in ShortNameToId the UI
            // never marks any option selected.
            Assert.Contains(GeminiClient.Models.DefaultShortName,
                GeminiClient.Models.ShortNameToId.Keys);
        }

        [Fact]
        public void Models_DefaultShortName_ResolvesToDefaultFullId()
        {
            Assert.Equal(
                GeminiClient.Models.Default,
                GeminiClient.Models.ResolveShortName(GeminiClient.Models.DefaultShortName));
        }

        [Theory]
        [InlineData("nano-banana-2", "gemini-3.1-flash-image-preview")]
        [InlineData("nano-banana-pro", "gemini-3-pro-image-preview")]
        public void Models_ResolveShortName_MapsKnownShortNames(string shortName, string expectedFullId)
        {
            Assert.Equal(expectedFullId, GeminiClient.Models.ResolveShortName(shortName));
        }

        [Fact]
        public void Models_ResolveShortName_NullOrEmpty_ReturnsDefault()
        {
            Assert.Equal(GeminiClient.Models.Default, GeminiClient.Models.ResolveShortName(null));
            Assert.Equal(GeminiClient.Models.Default, GeminiClient.Models.ResolveShortName(""));
        }

        [Fact]
        public void Models_ResolveShortName_UnknownValue_PassesThrough()
        {
            // Power users (and agents targeting a new Google release
            // before Rook catches up) need to be able to request a model
            // by full Gemini ID. The resolver must not clobber anything
            // that isn't a short-name entry.
            const string custom = "gemini-4-hypothetical-image-preview";
            Assert.Equal(custom, GeminiClient.Models.ResolveShortName(custom));
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
        [InlineData("512")]
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

        [Fact]
        public void ValidateResolution_512RejectedForNanoBananaPro()
        {
            var ex = Assert.Throws<ArgumentException>(
                () => VisionHandler.ValidateResolution(
                    "512", GeminiClient.Models.NanoBananaPro));
            Assert.Contains("resolution", ex.Message, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("nano-banana-pro", ex.Message);
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

        // ─── Aspect-ratio validation / normalization ───────────────────

        [Fact]
        public void AllowedAspectRatios_MatchesGeminiApiList()
        {
            Assert.Equal(
                new[]
                {
                    "1:1", "1:4", "4:1", "1:8", "8:1",
                    "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
                    "9:16", "16:9", "21:9",
                },
                VisionHandler.AllowedAspectRatios);
        }

        [Theory]
        [InlineData(null)]
        [InlineData("")]
        [InlineData("auto")]
        [InlineData("AUTO")]
        [InlineData("current")]
        public void NormalizeAspectRatio_AutoValues_ReturnNull(string? raw)
        {
            Assert.Null(VisionHandler.NormalizeAspectRatio(raw));
        }

        [Theory]
        [InlineData("1:1")]
        [InlineData("1:4")]
        [InlineData("4:1")]
        [InlineData("1:8")]
        [InlineData("8:1")]
        [InlineData("2:3")]
        [InlineData("3:2")]
        [InlineData("3:4")]
        [InlineData("4:3")]
        [InlineData("4:5")]
        [InlineData("5:4")]
        [InlineData("9:16")]
        [InlineData("16:9")]
        [InlineData("21:9")]
        public void NormalizeAspectRatio_SupportedValues_ReturnRaw(string ratio)
        {
            Assert.Equal(ratio, VisionHandler.NormalizeAspectRatio(ratio));
        }

        [Theory]
        [InlineData("5:7")]
        [InlineData("square")]
        [InlineData("16/9")]
        public void NormalizeAspectRatio_UnsupportedValues_Throw(string ratio)
        {
            var ex = Assert.Throws<ArgumentException>(
                () => VisionHandler.NormalizeAspectRatio(ratio));
            Assert.Contains("aspect_ratio", ex.Message);
        }

        [Fact]
        public void GeminiBuildImageConfig_AutoAspect_OmitsAspectRatio()
        {
            var config = GeminiClient.BuildImageConfig("1K", null);
            Assert.Equal("1K", config["imageSize"]);
            Assert.False(config.ContainsKey("aspectRatio"));
        }

        [Fact]
        public void GeminiBuildImageConfig_ExplicitAspect_IncludesAspectRatio()
        {
            var config = GeminiClient.BuildImageConfig("512", "16:9");
            Assert.Equal("512", config["imageSize"]);
            Assert.Equal("16:9", config["aspectRatio"]);
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

        // ─── API key preview (UI affordance) ────────────────────────────

        [Fact]
        public void Preview_NoKey_ReturnsNull()
        {
            Assert.Null(_store.GetApiKeyPreview());
        }

        [Fact]
        public void Preview_StoredOnSet_ReturnsTruncated()
        {
            // Arrange/Act
            _store.SetGeminiApiKey("AIzaSyExampleKeyForTesting-abcd1234");

            // Assert — first4…last4 shape
            var preview = _store.GetApiKeyPreview();
            Assert.NotNull(preview);
            Assert.StartsWith("AIza", preview);
            Assert.EndsWith("1234", preview);
            Assert.Contains("…", preview);
        }

        [Fact]
        public void Preview_IsPersistedInSettingsFile()
        {
            _store.SetGeminiApiKey("AIzaSyExampleKeyForTesting-abcd1234");

            var section = _settings.LoadSection<VisionSettings>("vision");
            Assert.NotNull(section);
            Assert.NotNull(section!.ApiKeyPreview);
            Assert.StartsWith("AIza", section.ApiKeyPreview);
            // The MIDDLE of the key must still not appear in the file.
            var fileContent = File.ReadAllText(_settingsPath);
            Assert.DoesNotContain("ExampleKey", fileContent);
        }

        [Fact]
        public void Preview_ShortKey_AllAsterisks()
        {
            // Keys <=8 chars get fully asterisked so we never echo the
            // bulk of a short credential. Defensive — real Gemini keys
            // are much longer; this guards against misuse.
            _store.SetGeminiApiKey("short");
            Assert.Equal("*****", _store.GetApiKeyPreview());
        }

        [Fact]
        public void Preview_ClearedOnClear()
        {
            _store.SetGeminiApiKey("AIzaSyExampleKeyForTesting-abcd1234");
            Assert.NotNull(_store.GetApiKeyPreview());

            _store.ClearGeminiApiKey();
            Assert.Null(_store.GetApiKeyPreview());
        }

        [Fact]
        public void Preview_RebuildOnReSave()
        {
            // User rotates the key — preview must reflect the new value,
            // not the first one that was saved.
            _store.SetGeminiApiKey("AIzaSyFirst--key---EndsHere1111");
            var first = _store.GetApiKeyPreview();
            _store.SetGeminiApiKey("AIzaSySecond-key---EndsHere2222");
            var second = _store.GetApiKeyPreview();

            Assert.NotEqual(first, second);
            Assert.EndsWith("1111", first);
            Assert.EndsWith("2222", second);
        }

        [Fact]
        public void Preview_LegacySettingsFile_ReturnsNull()
        {
            // A settings.json written by a previous companion build has
            // GeminiApiKeyEncrypted but no ApiKeyPreview. Reading must
            // return null (not throw); the UI falls back to the generic
            // "API key configured" placeholder, and the next save
            // rebuilds the preview field.
            var legacy = new VisionSettings
            {
                GeminiApiKeyEncrypted = "anything-looks-encrypted",
                ApiKeyPreview = null,
            };
            _settings.SaveSection("vision", legacy);

            Assert.Null(_store.GetApiKeyPreview());
            Assert.True(_store.HasGeminiApiKey());
        }
    }
}
