using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.MediaImport
{
    public sealed class MediaImportJobManager : IDisposable
    {
        private readonly object _gate = new();
        private readonly IMediaImportProcessor _processor;
        private readonly int _recentJobLimit;
        private readonly List<ImportJob> _jobs = new();
        private readonly List<Task> _workers = new();
        private readonly CancellationTokenSource _shutdown = new();
        private readonly SemaphoreSlim _processingGate = new(1, 1);
        private long _nextSequence;
        private bool _disposed;

        public MediaImportJobManager(
            IMediaImportProcessor processor,
            int recentJobLimit = MediaImportConstants.RecentJobLimit)
        {
            _processor = processor ?? throw new ArgumentNullException(nameof(processor));
            _recentJobLimit = Math.Max(0, recentJobLimit);
        }

        public Task<MediaImportStartResult> StartAsync(IEnumerable<string>? paths, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();

            var selectedPaths = paths?.ToArray() ?? Array.Empty<string>();
            if (selectedPaths.Length == 0)
            {
                return Task.FromResult(new MediaImportStartResult(
                    false,
                    null,
                    MediaImportStartFailureCode.EmptySelection,
                    "No media files were selected."));
            }

            if (selectedPaths.Length > MediaImportConstants.MaxBatchFiles)
            {
                return Task.FromResult(new MediaImportStartResult(
                    false,
                    null,
                    MediaImportStartFailureCode.TooManyFiles,
                    $"Select {MediaImportConstants.MaxBatchFiles} or fewer media files."));
            }

            var now = DateTimeOffset.UtcNow;
            var job = new ImportJob(
                Guid.NewGuid(),
                Interlocked.Increment(ref _nextSequence),
                MediaImportJobState.Queued,
                now,
                now,
                selectedPaths
                    .Select(path => new ImportItem(
                        Guid.NewGuid(),
                        path,
                        Path.GetFileName(path),
                        MediaImportItemState.Queued))
                    .ToList());

            MediaImportJobSnapshot snapshot;
            lock (_gate)
            {
                ThrowIfDisposedLocked();
                _jobs.Add(job);
                PruneTerminalJobsLocked();
                snapshot = CreateSnapshot(job);
                _workers.Add(Task.Run(() => ProcessJobAsync(job.JobId), CancellationToken.None));
            }

            return Task.FromResult(new MediaImportStartResult(true, snapshot, null, null));
        }

        public MediaImportJobSnapshot? GetJob(Guid jobId)
        {
            lock (_gate)
            {
                var job = _jobs.FirstOrDefault(candidate => candidate.JobId == jobId);
                return job is null ? null : CreateSnapshot(job);
            }
        }

        public void Dispose()
        {
            Task[] workers;
            lock (_gate)
            {
                if (_disposed)
                    return;

                _disposed = true;
                _shutdown.Cancel();
                workers = _workers.ToArray();
            }

            try
            {
                Task.WaitAll(workers);
            }
            catch (AggregateException)
            {
            }

            _processingGate.Dispose();
            _shutdown.Dispose();
        }

        public MediaImportJobListResult ListJobs()
        {
            lock (_gate)
            {
                PruneTerminalJobsLocked();
                return new MediaImportJobListResult(
                    _jobs
                        .OrderByDescending(job => job.Sequence)
                        .Select(CreateSnapshot)
                        .ToList());
            }
        }

        private async Task ProcessJobAsync(Guid jobId)
        {
            var acquired = false;
            try
            {
                await _processingGate.WaitAsync(_shutdown.Token).ConfigureAwait(false);
                acquired = true;
                MarkJobRunning(jobId);

                List<(Guid ItemId, string Path)> items;
                lock (_gate)
                {
                    var job = _jobs.FirstOrDefault(candidate => candidate.JobId == jobId);
                    if (job is null)
                        return;
                    items = job.Items
                        .Select(item => (item.ImportItemId, item.Path))
                        .ToList();
                }

                foreach (var item in items)
                {
                    UpdateItem(jobId, item.ItemId, current =>
                    {
                        current.State = MediaImportItemState.Copying;
                        current.Message = null;
                        current.FailureCode = null;
                        current.ArtifactId = null;
                        current.ArtifactKind = null;
                    });

                    MediaImportProcessResult result;
                    try
                    {
                        result = await _processor.ProcessAsync(item.Path, _shutdown.Token).ConfigureAwait(false);
                    }
                    catch (Exception ex)
                    {
                        result = MediaImportProcessResult.Failed(
                            MediaImportFailureCode.PublishFailed,
                            ex.Message);
                    }

                    UpdateItem(jobId, item.ItemId, current =>
                    {
                        if (result.IsSuccess)
                        {
                            current.State = MediaImportItemState.Imported;
                            current.ArtifactId = result.ArtifactId;
                            current.ArtifactKind = result.ArtifactKind;
                            current.FailureCode = null;
                            current.Message = result.Message;
                        }
                        else
                        {
                            current.State = MediaImportItemState.Failed;
                            current.ArtifactId = null;
                            current.ArtifactKind = null;
                            current.FailureCode = result.FailureCode ?? MediaImportFailureCode.PublishFailed;
                            current.Message = result.Message;
                        }
                    });
                }

                lock (_gate)
                {
                    var job = _jobs.FirstOrDefault(candidate => candidate.JobId == jobId);
                    if (job is null)
                        return;

                    job.State = MediaImportJobState.Complete;
                    job.UpdatedAt = DateTimeOffset.UtcNow;
                    PruneTerminalJobsLocked();
                }
            }
            catch (OperationCanceledException) when (_shutdown.IsCancellationRequested)
            {
            }
            finally
            {
                if (acquired)
                    _processingGate.Release();

                lock (_gate)
                {
                    _workers.RemoveAll(worker => worker.IsCompleted);
                }
            }
        }

        private void MarkJobRunning(Guid jobId)
        {
            lock (_gate)
            {
                var job = _jobs.FirstOrDefault(candidate => candidate.JobId == jobId);
                if (job is null)
                    return;

                job.State = MediaImportJobState.Running;
                job.UpdatedAt = DateTimeOffset.UtcNow;
            }
        }

        private void UpdateItem(Guid jobId, Guid itemId, Action<ImportItem> update)
        {
            lock (_gate)
            {
                var job = _jobs.FirstOrDefault(candidate => candidate.JobId == jobId);
                var item = job?.Items.FirstOrDefault(candidate => candidate.ImportItemId == itemId);
                if (job is null || item is null)
                    return;

                update(item);
                job.UpdatedAt = DateTimeOffset.UtcNow;
            }
        }

        private void ThrowIfDisposedLocked()
        {
            if (_disposed)
                throw new ObjectDisposedException(nameof(MediaImportJobManager));
        }

        private void PruneTerminalJobsLocked()
        {
            if (_recentJobLimit <= 0)
            {
                _jobs.RemoveAll(job => job.State == MediaImportJobState.Complete);
                return;
            }

            var terminalJobsToDrop = _jobs
                .Where(job => job.State == MediaImportJobState.Complete)
                .OrderByDescending(job => job.Sequence)
                .Skip(_recentJobLimit)
                .Select(job => job.JobId)
                .ToHashSet();

            if (terminalJobsToDrop.Count == 0)
                return;

            _jobs.RemoveAll(job => terminalJobsToDrop.Contains(job.JobId));
        }

        private static MediaImportJobSnapshot CreateSnapshot(ImportJob job) =>
            new(
                job.JobId,
                job.State,
                job.CreatedAt,
                job.UpdatedAt,
                job.Items.Select(CreateSnapshot).ToList());

        private static MediaImportItemSnapshot CreateSnapshot(ImportItem item) =>
            new(
                item.ImportItemId,
                item.Basename,
                item.State,
                item.ArtifactId,
                item.ArtifactKind,
                item.FailureCode,
                item.Message);

        private sealed class ImportJob
        {
            public ImportJob(
                Guid jobId,
                long sequence,
                MediaImportJobState state,
                DateTimeOffset createdAt,
                DateTimeOffset updatedAt,
                List<ImportItem> items)
            {
                JobId = jobId;
                Sequence = sequence;
                State = state;
                CreatedAt = createdAt;
                UpdatedAt = updatedAt;
                Items = items;
            }

            public Guid JobId { get; }
            public long Sequence { get; }
            public MediaImportJobState State { get; set; }
            public DateTimeOffset CreatedAt { get; }
            public DateTimeOffset UpdatedAt { get; set; }
            public List<ImportItem> Items { get; }
        }

        private sealed class ImportItem
        {
            public ImportItem(
                Guid importItemId,
                string path,
                string basename,
                MediaImportItemState state)
            {
                ImportItemId = importItemId;
                Path = path;
                Basename = basename;
                State = state;
            }

            public Guid ImportItemId { get; }
            public string Path { get; }
            public string Basename { get; }
            public MediaImportItemState State { get; set; }
            public Guid? ArtifactId { get; set; }
            public string? ArtifactKind { get; set; }
            public MediaImportFailureCode? FailureCode { get; set; }
            public string? Message { get; set; }
        }
    }
}
