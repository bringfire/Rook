using System;
using Rook.Services.Vision.Image.Jobs;

namespace Rook.Tests.Services.Vision.Image.Jobs
{
    public sealed class FakeImageJobIdGenerator : IImageJobIdGenerator
    {
        public Guid JobId { get; set; }
            = Guid.Parse("11111111-2222-3333-4444-555555555555");

        public Guid NewJobId() => JobId;
    }
}
