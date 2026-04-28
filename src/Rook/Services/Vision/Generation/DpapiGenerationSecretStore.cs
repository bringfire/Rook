using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Keyed DPAPI-backed secret store for generation providers.
    /// Ciphertexts are purpose-bound by both the store version and the
    /// individual secret key, so blobs cannot be swapped across slots.
    /// </summary>
    public sealed class DpapiGenerationSecretStore : IGenerationSecretStore
    {
        private const string SectionName = "generation_secrets";
        private const string LegacyVisionSectionName = "vision";

        private static readonly byte[] LegacyGeminiEntropy =
            Encoding.UTF8.GetBytes("rook-vision-gemini-v1");

        private readonly RookSettingsStore _settings;

        public DpapiGenerationSecretStore() : this(new RookSettingsStore()) { }

        public DpapiGenerationSecretStore(RookSettingsStore settings)
        {
            _settings = settings ?? throw new ArgumentNullException(nameof(settings));
        }

        public string? GetSecret(string secretKey)
        {
            ValidateSecretKey(secretKey);
            MigrateLegacyGeminiIfNeeded(secretKey);

            var encrypted = TryGetEntry(secretKey)?.EncryptedValue;
            if (encrypted is null || encrypted.Length == 0)
            {
                return null;
            }

            return Decrypt(encrypted!, BuildEntropy(secretKey));
        }

        public void SetSecret(string secretKey, string value)
        {
            ValidateSecretKey(secretKey);
            if (string.IsNullOrEmpty(value))
            {
                throw new ArgumentException(
                    "Secret value must be non-null and non-empty.", nameof(value));
            }

            var section = LoadOrCreateSection();
            section.Secrets[secretKey] = new GenerationSecretEntry
            {
                EncryptedValue = Encrypt(value, BuildEntropy(secretKey)),
                Preview = Rook.Services.Vision.VisionSecretStore.BuildPreview(value),
            };
            _settings.SaveSection(SectionName, section);
        }

        public void RemoveSecret(string secretKey)
        {
            ValidateSecretKey(secretKey);

            var section = _settings.LoadSection<GenerationSecretsSettings>(SectionName);
            var changed = section?.Secrets is not null && section.Secrets.Remove(secretKey);

            if (string.Equals(secretKey, GenerationSecretKeys.GeminiApiKey, StringComparison.Ordinal))
            {
                changed = ClearLegacyGeminiSlot() || changed;
            }

            if (changed && section is not null)
            {
                _settings.SaveSection(SectionName, section);
            }
        }

        public bool HasSecret(string secretKey)
        {
            ValidateSecretKey(secretKey);

            var entry = TryGetEntry(secretKey);
            if (!string.IsNullOrEmpty(entry?.EncryptedValue))
            {
                return true;
            }

            if (!string.Equals(
                    secretKey,
                    GenerationSecretKeys.GeminiApiKey,
                    StringComparison.Ordinal))
            {
                return false;
            }

            var legacy = _settings.LoadSection<Rook.Services.Vision.VisionSettings>(
                LegacyVisionSectionName);
            return !string.IsNullOrEmpty(legacy?.GeminiApiKeyEncrypted);
        }

        public string? GetPreview(string secretKey)
        {
            ValidateSecretKey(secretKey);

            var entry = TryGetEntry(secretKey);
            if (entry is not null && !string.IsNullOrEmpty(entry.EncryptedValue))
            {
                var preview = entry.Preview;
                return string.IsNullOrEmpty(preview) ? null : preview;
            }

            if (!string.Equals(
                    secretKey,
                    GenerationSecretKeys.GeminiApiKey,
                    StringComparison.Ordinal))
            {
                return null;
            }

            var legacy = _settings.LoadSection<Rook.Services.Vision.VisionSettings>(
                LegacyVisionSectionName);
            if (legacy is null || string.IsNullOrEmpty(legacy.GeminiApiKeyEncrypted))
                return null;
            return string.IsNullOrEmpty(legacy.ApiKeyPreview)
                ? null
                : legacy.ApiKeyPreview;
        }

        private void MigrateLegacyGeminiIfNeeded(string secretKey)
        {
            if (!string.Equals(secretKey, GenerationSecretKeys.GeminiApiKey, StringComparison.Ordinal))
            {
                return;
            }

            var current = _settings.LoadSection<GenerationSecretsSettings>(SectionName);
            if (current?.Secrets is not null
                && current.Secrets.TryGetValue(GenerationSecretKeys.GeminiApiKey, out var gemini)
                && !string.IsNullOrEmpty(gemini.EncryptedValue))
            {
                return;
            }

            var legacy = _settings.LoadSection<Rook.Services.Vision.VisionSettings>(
                LegacyVisionSectionName);
            var legacyEncrypted = legacy?.GeminiApiKeyEncrypted;
            if (legacyEncrypted is null || legacyEncrypted.Length == 0)
            {
                return;
            }

            var plaintext = Decrypt(legacyEncrypted!, LegacyGeminiEntropy);
            SetSecret(GenerationSecretKeys.GeminiApiKey, plaintext);
        }

        private bool ClearLegacyGeminiSlot()
        {
            var legacy = _settings.LoadSection<Rook.Services.Vision.VisionSettings>(
                LegacyVisionSectionName);
            if (legacy is null || string.IsNullOrEmpty(legacy.GeminiApiKeyEncrypted))
            {
                return false;
            }

            legacy.GeminiApiKeyEncrypted = null;
            legacy.ApiKeyPreview = null;
            _settings.SaveSection(LegacyVisionSectionName, legacy);
            return true;
        }

        private GenerationSecretEntry? TryGetEntry(string secretKey)
        {
            var section = _settings.LoadSection<GenerationSecretsSettings>(SectionName);
            if (section?.Secrets is null) return null;

            return section.Secrets.TryGetValue(secretKey, out var entry)
                ? entry
                : null;
        }

        private GenerationSecretsSettings LoadOrCreateSection()
        {
            var section = _settings.LoadSection<GenerationSecretsSettings>(SectionName)
                ?? new GenerationSecretsSettings();
            if (section.Secrets is null)
            {
                section.Secrets = new Dictionary<string, GenerationSecretEntry>();
            }
            return section;
        }

        private static string Encrypt(string plaintext, byte[] entropy)
        {
            var plaintextBytes = Encoding.UTF8.GetBytes(plaintext);
            var cipher = ProtectedData.Protect(
                plaintextBytes, entropy, DataProtectionScope.CurrentUser);
            return Convert.ToBase64String(cipher);
        }

        private static string Decrypt(string encrypted, byte[] entropy)
        {
            byte[] cipher;
            try
            {
                cipher = Convert.FromBase64String(encrypted);
            }
            catch (FormatException)
            {
                throw new InvalidOperationException(
                    "Stored generation secret is not valid base64. Re-enter the credential.");
            }

            try
            {
                var plaintextBytes = ProtectedData.Unprotect(
                    cipher, entropy, DataProtectionScope.CurrentUser);
                return Encoding.UTF8.GetString(plaintextBytes);
            }
            catch (CryptographicException)
            {
                throw new InvalidOperationException(
                    "Unable to decrypt the stored generation secret. " +
                    "This usually means it was encrypted under a different " +
                    "Windows user profile or on a different machine. " +
                    "Re-enter the credential on this machine.");
            }
        }

        private static byte[] BuildEntropy(string secretKey)
        {
            return Encoding.UTF8.GetBytes("rook-generation-secret-v1::" + secretKey);
        }

        private static void ValidateSecretKey(string secretKey)
        {
            if (string.IsNullOrWhiteSpace(secretKey))
            {
                throw new ArgumentException(
                    "Secret key must be non-null and non-whitespace.", nameof(secretKey));
            }
        }
    }
}
