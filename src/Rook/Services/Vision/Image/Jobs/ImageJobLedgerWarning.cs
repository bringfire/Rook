namespace Rook.Services.Vision.Image.Jobs
{
    public sealed record ImageJobLedgerWarning(
        int LineNumber,
        ImageJobLedgerReadErrorReason Reason,
        string Message,
        string? FieldPath);
}
