using System;
using Rook.Services.Vision.Image.Jobs;

namespace Rook.Tests.Services.Vision.Image.Jobs
{
    public sealed class FakeImageJobClock : IImageJobClock
    {
        private DateTimeOffset _now = new(2026, 4, 30, 0, 0, 0, TimeSpan.Zero);

        public DateTimeOffset UtcNow()
        {
            var value = _now;
            _now = _now.AddMilliseconds(1);
            return value;
        }
    }
}
