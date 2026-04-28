using System;
using System.Security.Cryptography;
using System.Text;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision
{
    /// <summary>
    /// Settings record for the Vision section in RookSettingsStore.
    /// Holds the DPAPI-encrypted API key plus a short non-secret preview
    /// ("AIza…xyz1") so the Settings UI can show "API key configured"
    /// across sessions without decrypting the ciphertext on every read.
    /// Plaintext never appears in the JSON file.
    /// </summary>
    public sealed class VisionSettings
    {
        /// <summary>
        /// Base64-encoded DPAPI ciphertext of the Gemini API key, or null
        /// if the key has not been configured. Scope: CurrentUser, with a
        /// purpose-specific entropy so this ciphertext cannot be used as a
        /// general DPAPI oracle for the same user.
        /// </summary>
        public string? GeminiApiKeyEncrypted { get; set; }

        /// <summary>
        /// Display-only obscured form of the key — <c>first 4 characters</c>
        /// + "…" + <c>last 4 characters</c>. Written alongside the
        /// ciphertext by <see cref="VisionSecretStore.SetGeminiApiKey"/>
        /// so the Settings UI can display a placeholder that proves the
        /// key is stored without costing a DPAPI decrypt on every read.
        ///
        /// Why plaintext: the first 4 chars of a Gemini key are the
        /// publicly-known "AIza" prefix, and 4 trailing chars leak
        /// effectively 4 key characters of entropy — acceptable for
        /// single-user local UI display. The DPAPI envelope still
        /// protects the 20+ middle characters.
        /// </summary>
        public string? ApiKeyPreview { get; set; }
    }

    /// <summary>
    /// DPAPI-wrapped secret store for Vision credentials. Reads/writes
    /// against <see cref="RookSettingsStore"/> under section "vision".
    ///
    /// Why DPAPI: the Windows Data Protection API encrypts blobs with a
    /// key derived from the current user's profile. The ciphertext can
    /// only be decrypted by the same user on the same machine. No key
    /// material is stored in the plaintext JSON file.
    ///
    /// Why entropy: purpose-binds the ciphertext. The entropy string is
    /// NOT a secret — it lives in source and any same-user process with
    /// that value can still call <c>ProtectedData.Unprotect</c> to
    /// decrypt. What entropy does buy: it prevents the blob from being
    /// interchangeable with other DPAPI ciphertexts produced by this
    /// user under different purposes (e.g. a user-level password manager
    /// cannot unwrap this blob even though both share the CurrentUser
    /// scope). It also catches accidental cross-purpose misuse inside
    /// Rook (if a different Rook subsystem uses different entropy, their
    /// blobs can't collide). It is NOT an authentication boundary
    /// against same-user malware.
    ///
    /// Error discipline: decryption failures surface as
    /// <see cref="InvalidOperationException"/> with a generic message. The
    /// ciphertext, the DPAPI error detail, and the plaintext value never
    /// appear in exception messages or log output.
    /// </summary>
    public sealed class VisionSecretStore
    {
        private const string SectionName = "vision";
        /// <summary>
        /// Purpose-binding entropy. Changing this string would invalidate
        /// existing stored keys — callers would need to re-enter their
        /// API key.
        /// </summary>
        private static readonly byte[] Entropy =
            Encoding.UTF8.GetBytes("rook-vision-gemini-v1");

        private readonly RookSettingsStore _settings;
        private readonly IGenerationSecretStore? _generationSecrets;

        public VisionSecretStore() : this(new RookSettingsStore()) { }

        public VisionSecretStore(RookSettingsStore settings)
        {
            _settings = settings ?? throw new ArgumentNullException(nameof(settings));
        }

        public VisionSecretStore(IGenerationSecretStore generationSecrets)
        {
            _generationSecrets = generationSecrets
                ?? throw new ArgumentNullException(nameof(generationSecrets));
            _settings = new RookSettingsStore();
        }

        /// <summary>
        /// Returns the plaintext Gemini API key, or null if none is stored.
        /// Throws <see cref="InvalidOperationException"/> if a ciphertext
        /// is present but fails to decrypt (generic message only).
        /// </summary>
        public string? GetGeminiApiKey()
        {
            if (_generationSecrets is not null)
            {
                return _generationSecrets.GetSecret(GenerationSecretKeys.GeminiApiKey);
            }

            var section = _settings.LoadSection<VisionSettings>(SectionName);
            var encrypted = section?.GeminiApiKeyEncrypted;
            if (string.IsNullOrEmpty(encrypted))
            {
                return null;
            }

            byte[] cipher;
            try
            {
                cipher = Convert.FromBase64String(encrypted);
            }
            catch (FormatException)
            {
                // Do not include the stored value in the error — it could
                // be a mangled ciphertext that still leaks bytes via the
                // partial base64.
                throw new InvalidOperationException(
                    "Stored Gemini API key is not valid base64. Re-enter the key.");
            }

            try
            {
                var plaintextBytes = ProtectedData.Unprotect(
                    cipher, Entropy, DataProtectionScope.CurrentUser);
                return Encoding.UTF8.GetString(plaintextBytes);
            }
            catch (CryptographicException)
            {
                // Could be: wrong user profile, corrupted ciphertext, or
                // entropy mismatch after a purpose change. All surface
                // with the same generic message — never include the raw
                // exception.
                throw new InvalidOperationException(
                    "Unable to decrypt the stored Gemini API key. " +
                    "This usually means it was encrypted under a different " +
                    "Windows user profile or on a different machine. " +
                    "Re-enter the key on this machine.");
            }
        }

        /// <summary>
        /// Encrypts and persists the Gemini API key, alongside a short
        /// obscured preview for UI display. Rejects null/empty.
        /// </summary>
        public void SetGeminiApiKey(string apiKey)
        {
            if (_generationSecrets is not null)
            {
                _generationSecrets.SetSecret(GenerationSecretKeys.GeminiApiKey, apiKey);
                return;
            }

            if (string.IsNullOrEmpty(apiKey))
            {
                throw new ArgumentException(
                    "API key must be non-null and non-empty.", nameof(apiKey));
            }

            var plaintextBytes = Encoding.UTF8.GetBytes(apiKey);
            var cipher = ProtectedData.Protect(
                plaintextBytes, Entropy, DataProtectionScope.CurrentUser);
            var encoded = Convert.ToBase64String(cipher);

            // Preserve any other fields we add to VisionSettings later.
            var existing = _settings.LoadSection<VisionSettings>(SectionName)
                ?? new VisionSettings();
            existing.GeminiApiKeyEncrypted = encoded;
            existing.ApiKeyPreview = BuildPreview(apiKey);
            _settings.SaveSection(SectionName, existing);
        }

        /// <summary>
        /// True if a ciphertext is present in the settings file. Does NOT
        /// attempt to decrypt — cheap check for config-existence UI paths.
        /// </summary>
        public bool HasGeminiApiKey()
        {
            if (_generationSecrets is not null)
            {
                return _generationSecrets.HasSecret(GenerationSecretKeys.GeminiApiKey);
            }

            var section = _settings.LoadSection<VisionSettings>(SectionName);
            return !string.IsNullOrEmpty(section?.GeminiApiKeyEncrypted);
        }

        /// <summary>
        /// Return the stored obscured preview of the API key, or null if
        /// no key is stored or the preview was never recorded (settings
        /// file predates the preview field). Never decrypts.
        /// </summary>
        public string? GetApiKeyPreview()
        {
            if (_generationSecrets is not null)
            {
                return _generationSecrets.GetPreview(GenerationSecretKeys.GeminiApiKey);
            }

            var section = _settings.LoadSection<VisionSettings>(SectionName);
            if (section is null) return null;
            if (string.IsNullOrEmpty(section.GeminiApiKeyEncrypted)) return null;
            return string.IsNullOrEmpty(section.ApiKeyPreview) ? null : section.ApiKeyPreview;
        }

        /// <summary>
        /// Clears the stored Gemini API key and its preview. Leaves
        /// other vision settings fields (if any) untouched.
        /// </summary>
        public void ClearGeminiApiKey()
        {
            if (_generationSecrets is not null)
            {
                _generationSecrets.RemoveSecret(GenerationSecretKeys.GeminiApiKey);
                return;
            }

            var section = _settings.LoadSection<VisionSettings>(SectionName);
            if (section is null) return;
            if (string.IsNullOrEmpty(section.GeminiApiKeyEncrypted)) return;
            section.GeminiApiKeyEncrypted = null;
            section.ApiKeyPreview = null;
            _settings.SaveSection(SectionName, section);
        }

        /// <summary>
        /// Build the first4…last4 preview for UI display. Returned value
        /// is SAFE to persist in the plaintext settings file — the
        /// prefix is publicly-known for Gemini keys ("AIza…") and 4
        /// trailing chars reveal minimal entropy. For keys shorter than
        /// 8 chars, return all asterisks so we don't accidentally echo
        /// an entire short credential. Exposed internally for
        /// <see cref="VisionHandler.SetApiKey"/> to share the same
        /// computation when returning the preview in the response
        /// envelope (same value is later persisted on read-back).
        /// </summary>
        internal static string BuildPreview(string apiKey)
        {
            if (string.IsNullOrEmpty(apiKey)) return "";
            if (apiKey.Length <= 8) return new string('*', apiKey.Length);
            return apiKey.Substring(0, 4) + "…" + apiKey.Substring(apiKey.Length - 4);
        }
    }
}
