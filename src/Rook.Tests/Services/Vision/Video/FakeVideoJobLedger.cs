using System;
using System.Collections.Generic;
using System.Linq;
using Rook.Services.Vision.Video;

namespace Rook.Tests.Services.Vision.Video
{
    /// <summary>
    /// In-memory test substrate for <see cref="IVideoJobLedger"/>.
    /// Exposes <see cref="AllRecords"/> for tests to inspect every append
    /// (not just the compacted view from <see cref="ReadAll"/>).
    /// </summary>
    public sealed class FakeVideoJobLedger : IVideoJobLedger
    {
        private readonly List<VideoJobRecord> _records = new();
        private readonly object _lock = new();

        public IReadOnlyList<VideoJobRecord> AllRecords
        {
            get { lock (_lock) return _records.ToArray(); }
        }

        public void Append(VideoJobRecord record)
        {
            lock (_lock) _records.Add(record);
        }

        public VideoJobLedgerReadResult ReadAll()
        {
            lock (_lock)
            {
                // Compact by job_id, file order: later entries win.
                var byId = new Dictionary<Guid, VideoJobRecord>();
                foreach (var r in _records)
                    byId[r.JobId] = r;
                return new VideoJobLedgerReadResult(
                    byId.Values.ToArray(),
                    Array.Empty<LedgerReadError>());
            }
        }
    }
}
