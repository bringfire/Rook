using System;
using System.IO;
using Rook.Services.Vision;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    public class GenerationSecretStoreTests : IDisposable
    {
        private const string GeminiKey = "gemini.api_key";
        private const string PairedSecretId = "provider.secret_id";
        private const string PairedSecretKey = "provider.secret_key";

        private readonly string _tempDir;
        private readonly string _settingsPath;
        private readonly RookSettingsStore _settings;
        private readonly DpapiGenerationSecretStore _store;

        public GenerationSecretStoreTests()
        {
            _tempDir = Path.Combine(Path.GetTempPath(),
                "rook-generation-secrets-" + Guid.NewGuid().ToString("N").Substring(0, 8));
            Directory.CreateDirectory(_tempDir);
            _settingsPath = Path.Combine(_tempDir, "settings.json");
            _settings = new RookSettingsStore(_settingsPath);
            _store = new DpapiGenerationSecretStore(_settings);
        }

        public void Dispose()
        {
            try { Directory.Delete(_tempDir, recursive: true); } catch { }
        }

        [Fact]
        public void NoSecret_GetHasAndPreviewReturnEmpty()
        {
            Assert.Null(_store.GetSecret(GeminiKey));
            Assert.False(_store.HasSecret(GeminiKey));
            Assert.Null(_store.GetPreview(GeminiKey));
        }

        [Fact]
        public void SetThenGet_RoundtripsPlaintextByKey()
        {
            const string plaintext = "AIzaSyExample_KeyForTestsOnly_12345";

            _store.SetSecret(GeminiKey, plaintext);

            Assert.True(_store.HasSecret(GeminiKey));
            Assert.Equal(plaintext, _store.GetSecret(GeminiKey));
        }

        [Fact]
        public void SetSecret_PersistsCiphertextAndPreviewWithoutPlaintext()
        {
            const string plaintext = "AIzaSyExampleKeyForTesting-abcd1234";

            _store.SetSecret(GeminiKey, plaintext);

            var section = _settings.LoadSection<GenerationSecretsSettings>("generation_secrets");
            Assert.NotNull(section);
            Assert.True(section!.Secrets.ContainsKey(GeminiKey));
            Assert.StartsWith("AIza", _store.GetPreview(GeminiKey));
            Assert.EndsWith("1234", _store.GetPreview(GeminiKey));
            Assert.Contains("…", _store.GetPreview(GeminiKey));
            Assert.DoesNotContain(plaintext, File.ReadAllText(_settingsPath));
        }

        [Fact]
        public void PairedCredentials_RoundtripInIndependentSlots()
        {
            _store.SetSecret(PairedSecretId, "AKID-test");
            _store.SetSecret(PairedSecretKey, "secret-test");

            Assert.Equal("AKID-test", _store.GetSecret(PairedSecretId));
            Assert.Equal("secret-test", _store.GetSecret(PairedSecretKey));
            Assert.True(_store.HasSecret(PairedSecretId));
            Assert.True(_store.HasSecret(PairedSecretKey));

            _store.RemoveSecret(PairedSecretKey);

            Assert.True(_store.HasSecret(PairedSecretId));
            Assert.False(_store.HasSecret(PairedSecretKey));
            Assert.Equal("AKID-test", _store.GetSecret(PairedSecretId));
            Assert.Null(_store.GetSecret(PairedSecretKey));
        }

        [Fact]
        public void SetWithInvalidInputs_Throws()
        {
            Assert.Throws<ArgumentException>(() => _store.SetSecret("", "value"));
            Assert.Throws<ArgumentException>(() => _store.SetSecret("   ", "value"));
            Assert.Throws<ArgumentException>(() => _store.SetSecret(GeminiKey, ""));
            Assert.Throws<ArgumentException>(() => _store.SetSecret(GeminiKey, null!));
        }

        [Fact]
        public void LegacyGeminiSlot_MigratesOnFirstRead()
        {
            const string plaintext = "AIzaSyLegacyKeyForMigration-1234";
            var legacy = new VisionSecretStore(_settings);
            legacy.SetGeminiApiKey(plaintext);

            var migrated = _store.GetSecret(GeminiKey);

            Assert.Equal(plaintext, migrated);
            Assert.Equal(plaintext, _store.GetSecret(GeminiKey));
            Assert.True(_store.HasSecret(GeminiKey));
            Assert.Equal(legacy.GetApiKeyPreview(), _store.GetPreview(GeminiKey));

            var generation = _settings.LoadSection<GenerationSecretsSettings>("generation_secrets");
            var vision = _settings.LoadSection<VisionSettings>("vision");
            Assert.NotNull(generation);
            Assert.True(generation!.Secrets.ContainsKey(GeminiKey));
            Assert.NotNull(vision);
            Assert.False(string.IsNullOrEmpty(vision!.GeminiApiKeyEncrypted));
        }

        [Fact]
        public void LegacyGeminiSlot_MigrationIsIdempotent()
        {
            const string plaintext = "AIzaSyLegacyKeyForMigration-5678";
            new VisionSecretStore(_settings).SetGeminiApiKey(plaintext);

            Assert.Equal(plaintext, _store.GetSecret(GeminiKey));
            var first = _settings.LoadSection<GenerationSecretsSettings>("generation_secrets")!
                .Secrets[GeminiKey].EncryptedValue;

            Assert.Equal(plaintext, _store.GetSecret(GeminiKey));
            var second = _settings.LoadSection<GenerationSecretsSettings>("generation_secrets")!
                .Secrets[GeminiKey].EncryptedValue;

            Assert.Equal(first, second);
        }

        [Fact]
        public void LegacyGeminiSlot_MigratesEvenWhenOtherSecretExists()
        {
            const string plaintext = "AIzaSyLegacyKeyForMigration-2222";
            _store.SetSecret("other.api_key", "other-provider-key");
            new VisionSecretStore(_settings).SetGeminiApiKey(plaintext);

            Assert.Equal(plaintext, _store.GetSecret(GeminiKey));
            Assert.Equal("other-provider-key", _store.GetSecret("other.api_key"));
            Assert.True(_store.HasSecret(GeminiKey));
        }

        [Fact]
        public void MigratedGeminiSlot_ClearDoesNotResurrectFromLegacySlot()
        {
            const string plaintext = "AIzaSyLegacyKeyForMigration-3333";
            var legacy = new VisionSecretStore(_settings);
            legacy.SetGeminiApiKey(plaintext);
            Assert.Equal(plaintext, _store.GetSecret(GeminiKey));

            var shim = new VisionSecretStore(_store);
            shim.ClearGeminiApiKey();

            Assert.False(_store.HasSecret(GeminiKey));
            Assert.Null(_store.GetSecret(GeminiKey));
            Assert.Null(_store.GetPreview(GeminiKey));
            Assert.False(legacy.HasGeminiApiKey());
        }

        [Fact]
        public void LegacyGeminiSlot_HasAndPreviewDoNotDecryptMalformedLegacyCiphertext()
        {
            const string preview = "AIza…1234";
            _settings.SaveSection("vision", new VisionSettings
            {
                GeminiApiKeyEncrypted = "not!valid@base64===",
                ApiKeyPreview = preview,
            });
            var shim = new VisionSecretStore(_store);

            Assert.True(_store.HasSecret(GeminiKey));
            Assert.Equal(preview, _store.GetPreview(GeminiKey));
            Assert.True(shim.HasGeminiApiKey());
            Assert.Equal(preview, shim.GetApiKeyPreview());

            var ex = Assert.Throws<InvalidOperationException>(
                () => _store.GetSecret(GeminiKey));
            Assert.Contains("base64", ex.Message, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void VisionSecretStore_DelegatesToGenerationSecretStore()
        {
            var generationStore = new DpapiGenerationSecretStore(_settings);
            var visionStore = new VisionSecretStore(generationStore);

            visionStore.SetGeminiApiKey("AIzaSyShimKeyForTesting-9999");

            Assert.True(generationStore.HasSecret(GeminiKey));
            Assert.Equal("AIzaSyShimKeyForTesting-9999", generationStore.GetSecret(GeminiKey));
            Assert.Equal(generationStore.GetPreview(GeminiKey), visionStore.GetApiKeyPreview());

            visionStore.ClearGeminiApiKey();
            Assert.False(generationStore.HasSecret(GeminiKey));
            Assert.Null(visionStore.GetGeminiApiKey());
        }
    }
}
