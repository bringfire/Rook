using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Generation
{
    public sealed class ProviderCredentialMetadata
    {
        public ProviderCredentialMetadata(
            string providerName,
            IReadOnlyList<ProviderSecretRequirement> secretRequirements)
        {
            if (string.IsNullOrWhiteSpace(providerName))
                throw new ArgumentException("Provider name must be non-empty.", nameof(providerName));
            if (secretRequirements is null)
                throw new ArgumentNullException(nameof(secretRequirements));

            var copy = new ProviderSecretRequirement[secretRequirements.Count];
            for (var i = 0; i < secretRequirements.Count; i++)
            {
                copy[i] = secretRequirements[i]
                    ?? throw new ArgumentException(
                        "Secret requirements cannot contain null entries.",
                        nameof(secretRequirements));
            }

            ProviderName = providerName;
            SecretRequirements = Array.AsReadOnly(copy);
        }

        public string ProviderName { get; }
        public IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; }
    }
}
