using System;
using System.Linq;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    public class ProviderCredentialMetadataCatalogTests
    {
        [Fact]
        public void FromProviders_merges_requirements_by_provider_name_and_secret_key()
        {
            var catalog = ProviderCredentialMetadataCatalog.FromProviders(new[]
            {
                Provider("gemini", Requirement(GenerationSecretKeys.GeminiApiKey, "Gemini API key")),
                Provider("gemini", Requirement(GenerationSecretKeys.GeminiApiKey, "Gemini API key")),
                Provider("fal", Requirement(GenerationSecretKeys.FalApiKey, "fal.ai API key")),
            });

            var providers = catalog.EnumerateProviders().ToArray();

            Assert.Equal(new[] { "gemini", "fal" }, providers.Select(p => p.ProviderName));
            Assert.Single(providers[0].SecretRequirements);
            Assert.Equal(GenerationSecretKeys.GeminiApiKey, providers[0].SecretRequirements[0].Key);
            Assert.Single(providers[1].SecretRequirements);
            Assert.Equal(GenerationSecretKeys.FalApiKey, providers[1].SecretRequirements[0].Key);
        }

        [Fact]
        public void FromProviders_rejects_conflicting_requirement_metadata_for_same_provider_key()
        {
            var ex = Assert.Throws<InvalidOperationException>(() =>
                ProviderCredentialMetadataCatalog.FromProviders(new[]
                {
                    Provider("fal", Requirement(GenerationSecretKeys.FalApiKey, "fal API key")),
                    Provider("fal", Requirement(GenerationSecretKeys.FalApiKey, "fal.ai API key")),
                }));

            Assert.Contains("Conflicting secret requirement metadata", ex.Message);
            Assert.Contains("fal", ex.Message);
            Assert.Contains(GenerationSecretKeys.FalApiKey, ex.Message);
        }

        [Fact]
        public void TryGetProvider_returns_false_for_unknown_provider()
        {
            var catalog = ProviderCredentialMetadataCatalog.FromProviders(new[]
            {
                Provider("gemini", Requirement(GenerationSecretKeys.GeminiApiKey, "Gemini API key")),
            });

            Assert.False(catalog.TryGetProvider("fal", out _));
        }

        private static ProviderCredentialMetadata Provider(
            string providerName,
            params ProviderSecretRequirement[] requirements)
            => new ProviderCredentialMetadata(providerName, requirements);

        private static ProviderSecretRequirement Requirement(string key, string displayName)
            => new ProviderSecretRequirement(key, displayName, isRequired: true);
    }
}
