using System;

namespace Rook.Services.Vision.Image.Jobs
{
    public interface IImageJobClock
    {
        DateTimeOffset UtcNow();
    }

    public sealed class SystemImageJobClock : IImageJobClock
    {
        public DateTimeOffset UtcNow() => DateTimeOffset.UtcNow;
    }
}
