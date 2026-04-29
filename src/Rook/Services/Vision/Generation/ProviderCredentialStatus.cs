using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Generation
{
    public sealed class ProviderCredentialStatus
    {
        public ProviderCredentialStatus(
            string providerName,
            ProviderCredentialAvailability availability,
            IReadOnlyList<ProviderSecretStatus> secrets,
            string? message)
        {
            if (string.IsNullOrWhiteSpace(providerName))
                throw new ArgumentException(
                    "Provider name must be non-empty.", nameof(providerName));
            if (secrets is null)
                throw new ArgumentNullException(nameof(secrets));

            var copy = new ProviderSecretStatus[secrets.Count];
            for (var i = 0; i < secrets.Count; i++)
            {
                copy[i] = secrets[i]
                    ?? throw new ArgumentException(
                        $"Secrets[{i}] is null.", nameof(secrets));
            }

            ProviderName = providerName;
            Availability = availability;
            Secrets = copy;
            Message = string.IsNullOrEmpty(message) ? null : message;
        }

        public string ProviderName { get; }
        public ProviderCredentialAvailability Availability { get; }
        public IReadOnlyList<ProviderSecretStatus> Secrets { get; }
        public string? Message { get; }
    }
}
