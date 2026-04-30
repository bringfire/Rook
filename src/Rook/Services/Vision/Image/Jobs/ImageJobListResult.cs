using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed class ImageJobListResult
    {
        public ImageJobListResult(
            IReadOnlyList<ImageJobRecord> jobs, int appliedLimit)
        {
            Jobs = jobs ?? throw new ArgumentNullException(nameof(jobs));
            AppliedLimit = appliedLimit;
        }

        public IReadOnlyList<ImageJobRecord> Jobs { get; }
        public int AppliedLimit { get; }
    }
}
