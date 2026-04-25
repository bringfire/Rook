namespace Rook.Services.Vision.Video
{
    public enum VideoJobState
    {
        Queued = 0,
        Submitting = 1,
        Polling = 2,
        Downloading = 3,
        Saving = 4,
        Complete = 5,
        Error = 6,
        Cancelled = 7,
        Interrupted = 8,
    }
}
