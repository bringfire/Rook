using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    public class ProviderCredentialStatusBuilderTests
    {
        [Theory]
        [InlineData("")]
        [InlineData("   ")]
        public void Empty_or_whitespace_provider_name_throws_argument_exception(
            string providerName)
        {
            var ex = Assert.Throws<ArgumentException>(() =>
                ProviderCredentialStatusBuilder.Build(
                    providerName,
                    new[] { new ProviderSecretRequirement("provider.api_key", "API key", true) },
                    new FakeSecretStore()));

            Assert.Equal("providerName", ex.ParamName);
        }

        [Fact]
        public void Null_requirements_throws_argument_null_exception()
        {
            var ex = Assert.Throws<ArgumentNullException>(() =>
                ProviderCredentialStatusBuilder.Build(
                    "provider",
                    null!,
                    new FakeSecretStore()));

            Assert.Equal("requirements", ex.ParamName);
        }

        [Fact]
        public void Null_secret_store_throws_argument_null_exception()
        {
            var ex = Assert.Throws<ArgumentNullException>(() =>
                ProviderCredentialStatusBuilder.Build(
                    "provider",
                    new[] { new ProviderSecretRequirement("provider.api_key", "API key", true) },
                    null!));

            Assert.Equal("secretStore", ex.ParamName);
        }

        [Fact]
        public void Null_requirement_entry_throws_argument_exception()
        {
            var ex = Assert.Throws<ArgumentException>(() =>
                ProviderCredentialStatusBuilder.Build(
                    "provider",
                    new ProviderSecretRequirement[] { null! },
                    new FakeSecretStore()));

            Assert.Equal("requirements", ex.ParamName);
        }

        [Fact]
        public void Missing_required_secret_blocks_provider()
        {
            var store = new FakeSecretStore();
            store.SetSecret("optional.token", "optional-value");
            var requirements = new[]
            {
                new ProviderSecretRequirement("provider.api_key", "API key", isRequired: true),
                new ProviderSecretRequirement("optional.token", "Optional token", isRequired: false),
            };

            var status = ProviderCredentialStatusBuilder.Build(
                "provider",
                requirements,
                store);

            Assert.Equal(
                ProviderCredentialAvailability.MissingRequiredSecret,
                status.Availability);
            Assert.Equal(ProviderSecretPresence.Missing, status.Secrets[0].Presence);
            Assert.Equal(ProviderSecretPresence.Present, status.Secrets[1].Presence);
        }

        [Fact]
        public void Missing_required_secret_sets_provider_message()
        {
            var status = ProviderCredentialStatusBuilder.Build(
                "provider",
                new[] { new ProviderSecretRequirement("provider.api_key", "API key", true) },
                new FakeSecretStore());

            Assert.Equal(
                "Missing required credential: API key.",
                status.Message);
        }

        [Fact]
        public void Optional_missing_secret_does_not_block_provider()
        {
            var store = new FakeSecretStore();
            store.SetSecret("provider.api_key", "value");
            var requirements = new[]
            {
                new ProviderSecretRequirement("provider.api_key", "API key", isRequired: true),
                new ProviderSecretRequirement("provider.sts_token", "STS token", isRequired: false),
            };

            var status = ProviderCredentialStatusBuilder.Build(
                "provider",
                requirements,
                store);

            Assert.Equal(
                ProviderCredentialAvailability.AvailableButUnverified,
                status.Availability);
            Assert.Equal(ProviderSecretPresence.Missing, status.Secrets[1].Presence);
        }

        [Fact]
        public void Required_invalid_validation_blocks_provider()
        {
            var store = new FakeSecretStore();
            store.SetSecret("provider.api_key", "value");
            var validations = new Dictionary<string, ProviderSecretValidationState>
            {
                ["provider.api_key"] = ProviderSecretValidationState.Invalid,
            };

            var status = ProviderCredentialStatusBuilder.Build(
                "provider",
                new[] { new ProviderSecretRequirement("provider.api_key", "API key", true) },
                store,
                validations);

            Assert.Equal(
                ProviderCredentialAvailability.InvalidCredential,
                status.Availability);
        }

        [Fact]
        public void Required_invalid_validation_uses_validation_message_as_provider_message()
        {
            var store = new FakeSecretStore();
            store.SetSecret("provider.api_key", "value");
            var validations = new Dictionary<string, ProviderSecretValidationState>
            {
                ["provider.api_key"] = ProviderSecretValidationState.Invalid,
            };
            var validationMessages = new Dictionary<string, string>
            {
                ["provider.api_key"] = "Provider rejected the API key.",
            };

            var status = ProviderCredentialStatusBuilder.Build(
                "provider",
                new[] { new ProviderSecretRequirement("provider.api_key", "API key", true) },
                store,
                validations,
                validationMessages);

            Assert.Equal("Provider rejected the API key.", status.Message);
        }

        [Fact]
        public void Required_invalid_validation_without_message_sets_fallback_provider_message()
        {
            var store = new FakeSecretStore();
            store.SetSecret("provider.api_key", "value");
            var validations = new Dictionary<string, ProviderSecretValidationState>
            {
                ["provider.api_key"] = ProviderSecretValidationState.Invalid,
            };

            var status = ProviderCredentialStatusBuilder.Build(
                "provider",
                new[] { new ProviderSecretRequirement("provider.api_key", "API key", true) },
                store,
                validations);

            Assert.Equal("Invalid credential: API key.", status.Message);
        }

        [Fact]
        public void Optional_invalid_validation_is_per_key_only()
        {
            var store = new FakeSecretStore();
            store.SetSecret("provider.api_key", "value");
            store.SetSecret("provider.sts_token", "bad");
            var validations = new Dictionary<string, ProviderSecretValidationState>
            {
                ["provider.sts_token"] = ProviderSecretValidationState.Invalid,
            };

            var status = ProviderCredentialStatusBuilder.Build(
                "provider",
                new[]
                {
                    new ProviderSecretRequirement("provider.api_key", "API key", true),
                    new ProviderSecretRequirement("provider.sts_token", "STS token", false),
                },
                store,
                validations);

            Assert.Equal(
                ProviderCredentialAvailability.AvailableButUnverified,
                status.Availability);
            Assert.Equal(
                ProviderSecretValidationState.Invalid,
                status.Secrets[1].ValidationState);
        }

        [Fact]
        public void Required_inconclusive_validation_sets_provider_inconclusive()
        {
            var store = new FakeSecretStore();
            store.SetSecret("provider.api_key", "value");
            var validations = new Dictionary<string, ProviderSecretValidationState>
            {
                ["provider.api_key"] = ProviderSecretValidationState.Inconclusive,
            };

            var status = ProviderCredentialStatusBuilder.Build(
                "provider",
                new[] { new ProviderSecretRequirement("provider.api_key", "API key", true) },
                store,
                validations);

            Assert.Equal(
                ProviderCredentialAvailability.AvailableWithInconclusiveValidation,
                status.Availability);
        }

        [Fact]
        public void Required_valid_validation_sets_provider_available()
        {
            var store = new FakeSecretStore();
            store.SetSecret("provider.api_key", "value");
            var validations = new Dictionary<string, ProviderSecretValidationState>
            {
                ["provider.api_key"] = ProviderSecretValidationState.Valid,
            };

            var status = ProviderCredentialStatusBuilder.Build(
                "provider",
                new[] { new ProviderSecretRequirement("provider.api_key", "API key", true) },
                store,
                validations);

            Assert.Equal(ProviderCredentialAvailability.Available, status.Availability);
        }

        private sealed class FakeSecretStore : IGenerationSecretStore
        {
            private readonly Dictionary<string, string> _values =
                new Dictionary<string, string>(StringComparer.Ordinal);

            public string? GetSecret(string secretKey) =>
                _values.TryGetValue(secretKey, out var value) ? value : null;

            public void SetSecret(string secretKey, string value)
            {
                _values[secretKey] = value;
            }

            public void RemoveSecret(string secretKey)
            {
                _values.Remove(secretKey);
            }

            public bool HasSecret(string secretKey) => _values.ContainsKey(secretKey);

            public string? GetPreview(string secretKey) =>
                _values.ContainsKey(secretKey) ? "prev…1234" : null;
        }
    }
}
