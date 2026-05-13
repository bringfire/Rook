using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.MediaImport;
using Xunit;

namespace Rook.Tests.Services.Vision.MediaImport
{
    public class MediaImportJobManagerTests
    {
        [Fact]
        public async Task StartAsync_RejectsMoreThanTwentyFiles_AndCreatesNoJob()
        {
            var processor = new FakeProcessor();
            var manager = new MediaImportJobManager(processor);
            var paths = Enumerable.Range(0, 21)
                .Select(i => $@"C:\media\file-{i}.png")
                .ToArray();

            var result = await manager.StartAsync(paths, CancellationToken.None);

            Assert.False(result.Created);
            Assert.Equal(MediaImportStartFailureCode.TooManyFiles, result.FailureCode);
            Assert.Null(result.Job);
            Assert.Empty(manager.ListJobs().Jobs);
        }

        [Fact]
        public async Task StartAsync_EmptySelection_ReturnsNeutralNoJob()
        {
            var manager = new MediaImportJobManager(new FakeProcessor());

            var result = await manager.StartAsync(Array.Empty<string>(), CancellationToken.None);

            Assert.False(result.Created);
            Assert.Equal(MediaImportStartFailureCode.EmptySelection, result.FailureCode);
            Assert.Null(result.Job);
        }

        [Fact]
        public async Task StartAsync_ReturnsBasenames_NotFullPaths()
        {
            var processor = new FakeProcessor();
            var manager = new MediaImportJobManager(processor);

            var result = await manager.StartAsync(
                new[] { @"C:\secret\family\clip.mp4" },
                CancellationToken.None);

            Assert.True(result.Created);
            var item = Assert.Single(result.Job!.Items);
            Assert.Equal("clip.mp4", item.Basename);
            Assert.DoesNotContain("secret", item.Basename, StringComparison.OrdinalIgnoreCase);
            Assert.Null(item.ArtifactId);
        }

        [Fact]
        public async Task Processing_IsSequential_AndKeepsSuccessfulItemsWhenAnotherFails()
        {
            var processor = new FakeProcessor
            {
                Delay = TimeSpan.FromMilliseconds(20),
                Results =
                {
                    [@"C:\media\a.png"] = MediaImportProcessResult.Success(Guid.Parse("11111111-1111-1111-1111-111111111111"), "imported_image"),
                    [@"C:\media\b.mov"] = MediaImportProcessResult.Failed(MediaImportFailureCode.VideoProbeFailed, "Could not probe video."),
                },
            };
            var manager = new MediaImportJobManager(processor);

            var start = await manager.StartAsync(
                new[] { @"C:\media\a.png", @"C:\media\b.mov" },
                CancellationToken.None);

            await WaitForTerminal(manager, start.Job!.JobId);

            Assert.Equal(1, processor.MaxConcurrentObserved);
            var job = manager.GetJob(start.Job.JobId)!;
            Assert.Equal(MediaImportJobState.Complete, job.State);
            Assert.Contains(job.Items, i => i.State == MediaImportItemState.Imported && i.ArtifactId.HasValue);
            Assert.Contains(job.Items, i => i.State == MediaImportItemState.Failed && i.FailureCode == MediaImportFailureCode.VideoProbeFailed);
        }

        [Fact]
        public async Task ListJobs_DropsOldTerminalJobsBeyondRetentionLimit()
        {
            var manager = new MediaImportJobManager(new FakeProcessor(), recentJobLimit: 2);
            var a = await manager.StartAsync(new[] { @"C:\media\a.png" }, CancellationToken.None);
            var b = await manager.StartAsync(new[] { @"C:\media\b.png" }, CancellationToken.None);
            var c = await manager.StartAsync(new[] { @"C:\media\c.png" }, CancellationToken.None);

            await WaitForTerminal(manager, c.Job!.JobId);
            await Task.Delay(20);

            var jobs = manager.ListJobs().Jobs;
            Assert.Equal(2, jobs.Count);
            Assert.DoesNotContain(jobs, j => j.JobId == a.Job!.JobId);
            Assert.Contains(jobs, j => j.JobId == b.Job!.JobId);
            Assert.Contains(jobs, j => j.JobId == c.Job!.JobId);
        }

        private static async Task WaitForTerminal(MediaImportJobManager manager, Guid jobId)
        {
            for (var i = 0; i < 100; i++)
            {
                var job = manager.GetJob(jobId);
                if (job is not null && job.State == MediaImportJobState.Complete)
                    return;
                await Task.Delay(10);
            }
            throw new TimeoutException("Import job did not finish.");
        }

        private sealed class FakeProcessor : IMediaImportProcessor
        {
            private int _active;
            public int MaxConcurrentObserved { get; private set; }
            public TimeSpan Delay { get; set; }
            public Dictionary<string, MediaImportProcessResult> Results { get; } = new(StringComparer.OrdinalIgnoreCase);

            public async Task<MediaImportProcessResult> ProcessAsync(string path, CancellationToken ct)
            {
                var active = Interlocked.Increment(ref _active);
                MaxConcurrentObserved = Math.Max(MaxConcurrentObserved, active);
                try
                {
                    if (Delay > TimeSpan.Zero)
                        await Task.Delay(Delay, ct);
                    if (Results.TryGetValue(path, out var result))
                        return result;
                    return MediaImportProcessResult.Success(Guid.NewGuid(), "imported_image");
                }
                finally
                {
                    Interlocked.Decrement(ref _active);
                }
            }
        }
    }
}
