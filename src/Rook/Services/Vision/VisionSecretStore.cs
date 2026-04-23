using System;
using System.Security.Cryptography;
using System.Text;

namespace Rook.Services.Vision
{
    /// <summary>
    /// Settings record for the Vision section in RookSettingsStore.
    /// Only holds the DPAPI-encrypted API key (base64 of the ciphertext).
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
    /// Why entropy: scopes the ciphertext to this specific purpose.
    /// Without entropy, any DPAPI blob for the user would be interchangeable,
    /// letting another app decrypt this blob if it ran as the same user.
    /// The fixed entropy string ties the blob to Rook Vision specifically.
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

        public VisionSecretStore() : this(new RookSettingsStore()) { }

        public VisionSecretStore(RookSettingsStore settings)
        {
            _settings = settings ?? throw new ArgumentNullException(nameof(settings));
        }

        /// <summary>
        /// Returns the plaintext Gemini API key, or null if none is stored.
        /// Throws <see cref="InvalidOperationException"/> if a ciphertext
        /// is present but fails to decrypt (generic message only).
        /// </summary>
        public string? GetGeminiApiKey()
        {
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
        /// Encrypts and persists the Gemini API key. Rejects null/empty.
        /// </summary>
        public void SetGeminiApiKey(string apiKey)
        {
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
            _settings.SaveSection(SectionName, existing);
        }

        /// <summary>
        /// True if a ciphertext is present in the settings file. Does NOT
        /// attempt to decrypt — cheap check for config-existence UI paths.
        /// </summary>
        public bool HasGeminiApiKey()
        {
            var section = _settings.LoadSection<VisionSettings>(SectionName);
            return !string.IsNullOrEmpty(section?.GeminiApiKeyEncrypted);
        }

        /// <summary>
        /// Clears the stored Gemini API key. Leaves other vision settings
        /// fields (if any) untouched.
        /// </summary>
        public void ClearGeminiApiKey()
        {
            var section = _settings.LoadSection<VisionSettings>(SectionName);
            if (section is null) return;
            if (string.IsNullOrEmpty(section.GeminiApiKeyEncrypted)) return;
            section.GeminiApiKeyEncrypted = null;
            _settings.SaveSection(SectionName, section);
        }
    }
}
