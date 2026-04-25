using System;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Clock seam for <see cref="VideoJobManager"/>. Default impl uses
    /// <see cref="DateTimeOffset.UtcNow"/>; tests inject deterministic
    /// implementations so ledger snapshot timestamps are stable.
    /// </summary>
    public interface IVideoJobClock
    {
        DateTimeOffset UtcNow();
    }

    public sealed class SystemVideoJobClock : IVideoJobClock
    {
        public DateTimeOffset UtcNow() => DateTimeOffset.UtcNow;
    }
}
