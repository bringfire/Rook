using System;
using Rook.Services.Vision.Video;

namespace Rook.Tests.Services.Vision.Video
{
    /// <summary>
    /// Deterministic clock for ledger-snapshot stability in tests.
    /// </summary>
    public sealed class FakeVideoJobClock : IVideoJobClock
    {
        public DateTimeOffset Now { get; set; }
            = new(2026, 4, 25, 0, 0, 0, TimeSpan.Zero);

        public DateTimeOffset UtcNow() => Now;

        public void Advance(TimeSpan delta) => Now = Now + delta;
    }
}
