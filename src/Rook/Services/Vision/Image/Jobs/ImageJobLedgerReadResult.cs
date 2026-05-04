using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed class ImageJobLedgerReadResult
    {
        public ImageJobLedgerReadResult(
            IReadOnlyList<ImageJobLedgerRecord> records,
            IReadOnlyList<ImageJobLedgerReadError> errors)
        {
            Records = records ?? throw new ArgumentNullException(nameof(records));
            Errors = errors ?? throw new ArgumentNullException(nameof(errors));
        }

        public IReadOnlyList<ImageJobLedgerRecord> Records { get; }

        public IReadOnlyList<ImageJobLedgerReadError> Errors { get; }
    }
}
