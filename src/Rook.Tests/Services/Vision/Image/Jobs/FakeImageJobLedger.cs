using System;
using System.Collections.Generic;
using System.Linq;
using Rook.Services.Vision.Image.Jobs;

namespace Rook.Tests.Services.Vision.Image.Jobs
{
    public sealed class FakeImageJobLedger : IImageJobLedger
    {
        private readonly List<ImageJobLedgerRecord> _records = new();
        private readonly object _lock = new();

        public Action<ImageJobLedgerRecord>? BeforeAppend { get; set; }

        public IReadOnlyList<ImageJobLedgerRecord> AllRecords
        {
            get { lock (_lock) return _records.ToArray(); }
        }

        public void Append(ImageJobLedgerRecord record)
        {
            BeforeAppend?.Invoke(record);
            lock (_lock) _records.Add(record);
        }

        public ImageJobLedgerReadResult ReadAll()
        {
            lock (_lock)
            {
                var byId = new Dictionary<Guid, ImageJobLedgerRecord>();
                foreach (var record in _records)
                    byId[record.JobId] = record;
                return new ImageJobLedgerReadResult(
                    byId.Values.ToArray(),
                    Array.Empty<ImageJobLedgerReadError>());
            }
        }
    }
}
