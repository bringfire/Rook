using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Generation
{
    public sealed class ProviderCredentialMetadataCatalog
    {
        private readonly Dictionary<string, ProviderCredentialMetadata> _byProvider;
        private readonly IReadOnlyList<ProviderCredentialMetadata> _ordered;

        private ProviderCredentialMetadataCatalog(IReadOnlyList<ProviderCredentialMetadata> ordered)
        {
            _ordered = ordered;
            _byProvider = new Dictionary<string, ProviderCredentialMetadata>(StringComparer.Ordinal);
            foreach (var provider in ordered)
                _byProvider[provider.ProviderName] = provider;
        }

        public static ProviderCredentialMetadataCatalog FromProviders(
            IEnumerable<ProviderCredentialMetadata> providers)
        {
            if (providers is null) throw new ArgumentNullException(nameof(providers));

            var byProvider = new Dictionary<string, List<ProviderSecretRequirement>>(StringComparer.Ordinal);
            var order = new List<string>();

            foreach (var provider in providers)
            {
                if (provider is null)
                    throw new ArgumentException(
                        "Provider metadata cannot contain null entries.",
                        nameof(providers));

                if (!byProvider.TryGetValue(provider.ProviderName, out var requirements))
                {
                    requirements = new List<ProviderSecretRequirement>();
                    byProvider[provider.ProviderName] = requirements;
                    order.Add(provider.ProviderName);
                }

                foreach (var requirement in provider.SecretRequirements)
                    AddOrValidate(provider.ProviderName, requirements, requirement);
            }

            var ordered = new ProviderCredentialMetadata[order.Count];
            for (var i = 0; i < order.Count; i++)
            {
                var providerName = order[i];
                ordered[i] = new ProviderCredentialMetadata(providerName, byProvider[providerName]);
            }

            return new ProviderCredentialMetadataCatalog(Array.AsReadOnly(ordered));
        }

        public IReadOnlyList<ProviderCredentialMetadata> EnumerateProviders()
            => _ordered;

        public bool TryGetProvider(string providerName, out ProviderCredentialMetadata? metadata)
        {
            if (!string.IsNullOrWhiteSpace(providerName)
                && _byProvider.TryGetValue(providerName, out var found))
            {
                metadata = found;
                return true;
            }

            metadata = null;
            return false;
        }

        private static void AddOrValidate(
            string providerName,
            List<ProviderSecretRequirement> existing,
            ProviderSecretRequirement requirement)
        {
            foreach (var current in existing)
            {
                if (!string.Equals(current.Key, requirement.Key, StringComparison.Ordinal))
                    continue;

                if (!string.Equals(current.DisplayName, requirement.DisplayName, StringComparison.Ordinal)
                    || current.IsRequired != requirement.IsRequired
                    || current.IsSensitive != requirement.IsSensitive)
                {
                    throw new InvalidOperationException(
                        $"Conflicting secret requirement metadata for provider '{providerName}' key '{requirement.Key}'.");
                }

                return;
            }

            existing.Add(requirement);
        }
    }
}
