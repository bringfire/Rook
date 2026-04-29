namespace Rook.Services.Vision.Generation
{
    public enum ProviderCredentialAvailability
    {
        MissingRequiredSecret = 0,
        InvalidCredential = 1,
        Available = 2,
        AvailableButUnverified = 3,
        AvailableWithInconclusiveValidation = 4,
    }
}
