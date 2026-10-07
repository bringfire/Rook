using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoStopSubmissionRaceTests
    {
        [Fact]
        public async Task StopReadingBeforeHandleCommit_PreservesLatestOperationAndBinding()
        {
            var root = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"));
            var ledger = new PausingLedger();
            var provider = new AcceptedProvider();
            try
            {
                var artifacts = new ArtifactStore(root);
                using var manager = new VideoJobManager(TestVideoFixtures.RegistryWithVeo(provider), new FakeVideoMediaResolver(), ledger, new VideoCostEstimator(), artifacts);
                var done = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                manager.AfterRunForTests = _ => done.TrySetResult(true);
                var submitted = await manager.SubmitAsync(TestVideoFixtures.DefaultT2vRequest(), CancellationToken.None);
                await Bounded(provider.Entered.Task);
                ledger.Arm();
                var stop = Task.Run(() => manager.CancelAsync(submitted.JobId!.Value, CancellationToken.None));
                Assert.True(await Task.Run(() => ledger.Captured.Wait(5000)));
                provider.Release.TrySetResult(true);
                Assert.True(await Task.Run(() => ledger.Accepted.Wait(5000)));
                ledger.Release.Set();
                await Bounded(stop);
                Assert.Equal(VideoJobState.Interrupted, (await stop).State);
                await Bounded(done.Task);
                var final = ledger.ReadAll().Records.Single();
                Assert.Equal(VideoJobState.Interrupted, final.State);
                Assert.NotNull(final.ProviderHandle);
                Assert.Equal("original-operation", final.ProviderHandle!.ProviderJobId);
                Assert.True(final.ProviderHandle.ProviderMetadata!.ContainsKey("vertex_binding"));
                Assert.Empty(artifacts.List());
            }
            finally
            {
                ledger.Release.Set(); provider.Release.TrySetResult(true);
                if (Directory.Exists(root)) Directory.Delete(root, true);
            }
        }

        private static async Task Bounded(Task task)
        {
            Assert.Same(task, await Task.WhenAny(task, Task.Delay(5000)));
            await task;
        }

        private sealed class PausingLedger : IVideoJobLedger
        {
            private readonly FakeVideoJobLedger _inner = new();
            private int _armed;
            public readonly ManualResetEventSlim Captured = new();
            public readonly ManualResetEventSlim Release = new();
            public readonly ManualResetEventSlim Accepted = new();
            public void Arm() => Interlocked.Exchange(ref _armed, 1);
            public void Append(VideoJobRecord record)
            {
                _inner.Append(record);
                if (record.ProviderHandle is not null) Accepted.Set();
            }
            public VideoJobLedgerReadResult ReadAll()
            {
                var captured = _inner.ReadAll();
                if (Interlocked.Exchange(ref _armed, 0) == 1)
                {
                    Captured.Set();
                    Assert.True(Release.Wait(5000));
                }
                return captured;
            }
        }

        private sealed class AcceptedProvider : IVideoProvider, ILocalMonitoringProvider
        {
            public string ProviderName => "guarded";
            public readonly TaskCompletionSource<bool> Entered = new(TaskCreationOptions.RunContinuationsAsynchronously);
            public readonly TaskCompletionSource<bool> Release = new(TaskCreationOptions.RunContinuationsAsynchronously);
            public async Task<ProviderSubmitOutcome> SubmitAsync(VideoGenerationRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> media, CancellationToken ct)
            {
                Entered.TrySetResult(true); await Release.Task;
                return new QueuedSubmitOutcome(new ProviderJobHandle("original-operation", providerMetadata: GuardedVideoProviderFixture.Metadata));
            }
            public async Task<ProviderStatusOutcome> GetStatusAsync(ProviderJobHandle handle, CancellationToken ct)
            {
                await Task.Delay(Timeout.Infinite, ct);
                throw new InvalidOperationException();
            }
            public Task<ProviderCancelOutcome> CancelAsync(ProviderJobHandle handle, CancellationToken ct) => throw new InvalidOperationException("Local stop must not cancel remotely.");
            public Task<ProviderResultOutcome> FetchResultAsync(ProviderJobHandle handle, CancellationToken ct) => throw new InvalidOperationException("Stopped work must not publish.");
        }
    }
}
