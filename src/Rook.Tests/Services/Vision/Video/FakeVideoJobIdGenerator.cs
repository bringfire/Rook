using System;
using System.Collections.Generic;
using Rook.Services.Vision.Video;

namespace Rook.Tests.Services.Vision.Video
{
    /// <summary>
    /// Deterministic id generator for job-id assertions in tests.
    /// Pre-load <see cref="Sequence"/> with the Guids the test wants;
    /// after the queue is drained, falls back to <see cref="Guid.NewGuid"/>.
    /// </summary>
    public sealed class FakeVideoJobIdGenerator : IVideoJobIdGenerator
    {
        public Queue<Guid> Sequence { get; } = new();

        public Guid NewJobId() =>
            Sequence.Count > 0 ? Sequence.Dequeue() : Guid.NewGuid();
    }
}
