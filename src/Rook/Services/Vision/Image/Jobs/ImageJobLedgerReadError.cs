namespace Rook.Services.Vision.Image.Jobs
{
    public sealed record ImageJobLedgerReadError(
        int LineNumber,
        ImageJobLedgerReadErrorReason Reason,
        string Message,
        string? FieldPath);
}
