namespace Rook.Services.Vision.Video
{
    public enum LedgerReadErrorReason
    {
        MalformedJson = 0,
        UnsupportedSchemaVersion = 1,
        UnknownPricingKind = 2,
        MissingRequiredField = 3,
    }
}
