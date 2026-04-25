using System;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Job id generator seam for <see cref="VideoJobManager"/>. Default
    /// impl uses <see cref="Guid.NewGuid"/>; tests inject deterministic
    /// implementations so job-id assertions are stable.
    /// </summary>
    public interface IVideoJobIdGenerator
    {
        Guid NewJobId();
    }

    public sealed class GuidVideoJobIdGenerator : IVideoJobIdGenerator
    {
        public Guid NewJobId() => Guid.NewGuid();
    }
}
