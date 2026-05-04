namespace Rook.Services.Vision.Image.Jobs
{
    public enum ImageJobLedgerReadErrorReason
    {
        MalformedJson = 0,
        UnsupportedSchemaVersion = 1,
        MissingRequiredField = 2,
    }
}
