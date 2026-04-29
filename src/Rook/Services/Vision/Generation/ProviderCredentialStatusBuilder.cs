using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Generation
{
    public static class ProviderCredentialStatusBuilder
    {
        public static ProviderCredentialStatus Build(
            string providerName,
            IReadOnlyList<ProviderSecretRequirement> requirements,
            IGenerationSecretStore secretStore,
            IReadOnlyDictionary<string, ProviderSecretValidationState>? validationStates = null,
            IReadOnlyDictionary<string, string>? validationMessages = null)
        {
            if (string.IsNullOrWhiteSpace(providerName))
                throw new ArgumentException(
                    "Provider name must be non-empty.", nameof(providerName));
            if (requirements is null)
                throw new ArgumentNullException(nameof(requirements));
            if (secretStore is null)
                throw new ArgumentNullException(nameof(secretStore));

            var statuses = new List<ProviderSecretStatus>(requirements.Count);
            foreach (var requirement in requirements)
            {
                if (requirement is null)
                    throw new ArgumentException(
                        "Secret requirements cannot contain null entries.",
                        nameof(requirements));

                var presence = secretStore.HasSecret(requirement.Key)
                    ? ProviderSecretPresence.Present
                    : ProviderSecretPresence.Missing;

                var validation = ProviderSecretValidationState.NotAttempted;
                if (validationStates is not null
                    && validationStates.TryGetValue(requirement.Key, out var found))
                {
                    validation = found;
                }

                string? message = null;
                if (validationMessages is not null)
                    validationMessages.TryGetValue(requirement.Key, out message);

                statuses.Add(new ProviderSecretStatus(
                    requirement,
                    presence,
                    validation,
                    secretStore.GetPreview(requirement.Key),
                    message));
            }

            return new ProviderCredentialStatus(
                providerName,
                ComputeAvailability(statuses),
                statuses,
                BuildMessage(statuses));
        }

        private static ProviderCredentialAvailability ComputeAvailability(
            IReadOnlyList<ProviderSecretStatus> statuses)
        {
            foreach (var status in statuses)
            {
                if (status.Requirement.IsRequired
                    && status.Presence == ProviderSecretPresence.Missing)
                {
                    return ProviderCredentialAvailability.MissingRequiredSecret;
                }
            }

            foreach (var status in statuses)
            {
                if (status.Requirement.IsRequired
                    && status.ValidationState == ProviderSecretValidationState.Invalid)
                {
                    return ProviderCredentialAvailability.InvalidCredential;
                }
            }

            foreach (var status in statuses)
            {
                if (status.Requirement.IsRequired
                    && status.ValidationState == ProviderSecretValidationState.Inconclusive)
                {
                    return ProviderCredentialAvailability.AvailableWithInconclusiveValidation;
                }
            }

            var sawRequired = false;
            var allRequiredValid = true;
            foreach (var status in statuses)
            {
                if (!status.Requirement.IsRequired) continue;
                sawRequired = true;
                if (status.ValidationState != ProviderSecretValidationState.Valid)
                    allRequiredValid = false;
            }

            if (sawRequired && allRequiredValid)
                return ProviderCredentialAvailability.Available;

            return ProviderCredentialAvailability.AvailableButUnverified;
        }

        private static string? BuildMessage(IReadOnlyList<ProviderSecretStatus> statuses)
        {
            foreach (var status in statuses)
            {
                if (status.Requirement.IsRequired
                    && status.Presence == ProviderSecretPresence.Missing)
                {
                    return $"Missing required credential: {status.Requirement.DisplayName}.";
                }
            }

            foreach (var status in statuses)
            {
                if (status.Requirement.IsRequired
                    && status.ValidationState == ProviderSecretValidationState.Invalid)
                {
                    return status.Message
                        ?? $"Invalid credential: {status.Requirement.DisplayName}.";
                }
            }

            return null;
        }
    }
}
