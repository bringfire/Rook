namespace Rook.Services.Vision.Image.Jobs
{
    public enum ImageJobState
    {
        Queued = 0,
        Submitting = 1,
        Polling = 2,
        Materializing = 3,
        Complete = 4,
        Error = 5,
        Cancelled = 6,
        Interrupted = 7,
    }
}
