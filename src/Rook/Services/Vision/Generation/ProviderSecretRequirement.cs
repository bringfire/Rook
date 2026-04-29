using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Provider-declared credential slot. Phase 2 uses provider-level
    /// static requirements only; operation/model overlays are deferred
    /// to a later descriptor contract.
    /// </summary>
    public sealed class ProviderSecretRequirement
    {
        public ProviderSecretRequirement(
            string key,
            string displayName,
            bool isRequired,
            bool isSensitive = true)
        {
            if (string.IsNullOrWhiteSpace(key))
                throw new ArgumentException(
                    "Secret requirement key must be non-empty.", nameof(key));
            if (string.IsNullOrWhiteSpace(displayName))
                throw new ArgumentException(
                    "Secret requirement display name must be non-empty.",
                    nameof(displayName));

            Key = key;
            DisplayName = displayName;
            IsRequired = isRequired;
            IsSensitive = isSensitive;
        }

        public string Key { get; }
        public string DisplayName { get; }
        public bool IsRequired { get; }
        public bool IsSensitive { get; }
    }
}
