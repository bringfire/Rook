using System;

namespace Rook.Services.Vision.Image.Jobs
{
    public interface IImageJobIdGenerator
    {
        Guid NewJobId();
    }

    public sealed class GuidImageJobIdGenerator : IImageJobIdGenerator
    {
        public Guid NewJobId() => Guid.NewGuid();
    }
}
