using System;

namespace Rook.Services.Vision.Generation
{
    public sealed class ProviderSecretStatus
    {
        public ProviderSecretStatus(
            ProviderSecretRequirement requirement,
            ProviderSecretPresence presence,
            ProviderSecretValidationState validationState,
            string? preview,
            string? message)
        {
            Requirement = requirement
                ?? throw new ArgumentNullException(nameof(requirement));
            Presence = presence;
            ValidationState = validationState;
            Preview = string.IsNullOrEmpty(preview) ? null : preview;
            Message = string.IsNullOrEmpty(message) ? null : message;
        }

        public ProviderSecretRequirement Requirement { get; }
        public ProviderSecretPresence Presence { get; }
        public ProviderSecretValidationState ValidationState { get; }
        public string? Preview { get; }
        public string? Message { get; }
    }
}
