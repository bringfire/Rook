using System;
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
    public sealed class GuardedVideoJobManagerTests
    {
        private static async Task Bounded(Task task)
        { Assert.Same(task, await Task.WhenAny(task,Task.Delay(5000))); await task; }

        [Theory]
        [InlineData("fetch",true)]
        [InlineData("guard1",false)]
        [InlineData("guard1",true)]
        [InlineData("guard2",false)]
        [InlineData("guard2",true)]
        [InlineData("submit",true)]
        public async Task StopOrDisconnectWins_NeverPublishesOrOverwritesInterrupted(string blockAt,bool stop)
        {
            var root=Path.Combine(Path.GetTempPath(),Guid.NewGuid().ToString("N"));
            try
            {
                var store=new ArtifactStore(root); var ledger=new FakeVideoJobLedger();
                var provider=new GuardedVideoProviderFixture {BlockAt=blockAt};
                var finished=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                using var manager=new VideoJobManager(TestVideoFixtures.RegistryWithVeo(provider), new FakeVideoMediaResolver(),ledger,new VideoCostEstimator(),store,null,null,TimeSpan.FromMilliseconds(1),2,null,new FakePosterProducer(store),new FakeFrameProducer(store));
                manager.AfterRunForTests = _ => finished.TrySetResult(true);
                var job=await manager.SubmitAsync(TestVideoFixtures.DefaultT2vRequest(),CancellationToken.None);
                await Bounded(provider.Entered.Task);
                if (stop)
                {
                    var cancelled=await manager.CancelAsync(job.JobId!.Value,CancellationToken.None);
                    Assert.Null(cancelled.Error); Assert.Equal(VideoJobState.Interrupted,cancelled.State);
                }
                else provider.Authorized=false;
                provider.Release.TrySetResult(true);
                await Bounded(finished.Task);
                Assert.Equal(VideoJobState.Interrupted,ledger.ReadAll().Records.Single().State);
                Assert.DoesNotContain(ledger.AllRecords,r => r.State is VideoJobState.Complete or VideoJobState.Cancelled or VideoJobState.Error);
                Assert.Empty(store.List());
                Assert.Equal("original-operation",ledger.ReadAll().Records.Single().ProviderHandle!.ProviderJobId);
                if (stop) Assert.Equal(LocalStopOnlyOutcome.Message,ledger.ReadAll().Records.Single().Error!.Message);
            }
            finally { if(Directory.Exists(root)) Directory.Delete(root,true); }
        }

        [Fact]
        public async Task CompleteWinsBeforeStop_PreservesComplete()
        {
            var root=Path.Combine(Path.GetTempPath(),Guid.NewGuid().ToString("N"));
            try
            {
                var store=new ArtifactStore(root); var ledger=new FakeVideoJobLedger(); var provider=new GuardedVideoProviderFixture {BlockAt="none"};
                var finished=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                using var manager=new VideoJobManager(TestVideoFixtures.RegistryWithVeo(provider),new FakeVideoMediaResolver(),ledger,new VideoCostEstimator(),store,null,null,TimeSpan.FromMilliseconds(1),2,null,new FakePosterProducer(store),new FakeFrameProducer(store));
                manager.AfterRunForTests = _ => finished.TrySetResult(true);
                var job=await manager.SubmitAsync(TestVideoFixtures.DefaultT2vRequest(),CancellationToken.None);
                await Bounded(finished.Task);
                Assert.Equal(VideoJobState.Complete,(await manager.CancelAsync(job.JobId!.Value,CancellationToken.None)).State);
                Assert.Single(store.List());
                var calls=provider.Calls;
                manager.ReconcileInterruptedJobs();
                Assert.Equal(calls,provider.Calls);
                var persisted = ledger.ReadAll().Records.Single() with { State=VideoJobState.Polling,ResultArtifactId=null,Error=null };
                var restartLedger = new FakeVideoJobLedger(); restartLedger.Append(persisted);
                using var restarted = new VideoJobManager(TestVideoFixtures.RegistryWithVeo(provider),new FakeVideoMediaResolver(),restartLedger,new VideoCostEstimator(),store);
                restarted.ReconcileInterruptedJobs();
                Assert.Equal(VideoJobState.Interrupted,restartLedger.ReadAll().Records.Single().State);
                Assert.Equal("original-operation",restartLedger.ReadAll().Records.Single().ProviderHandle!.ProviderJobId);
                Assert.Equal(calls,provider.Calls);
            }
            finally { if(Directory.Exists(root)) Directory.Delete(root,true); }
        }

        [Theory]
        [InlineData(true,false)]
        [InlineData(false,true)]
        public async Task AuthChangedOrMissingBinding_UsesInterruptedNotError(bool failStatus, bool missingBinding)
        {
            var root=Path.Combine(Path.GetTempPath(),Guid.NewGuid().ToString("N"));
            try
            {
                var store=new ArtifactStore(root); var ledger=new FakeVideoJobLedger();
                var provider=new GuardedVideoProviderFixture {BlockAt="none", FailStatus=failStatus, MissingBinding=missingBinding};
                var finished=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                using var manager=new VideoJobManager(TestVideoFixtures.RegistryWithVeo(provider),new FakeVideoMediaResolver(),ledger,new VideoCostEstimator(),store,null,null,TimeSpan.FromMilliseconds(1),2,null,new FakePosterProducer(store),new FakeFrameProducer(store));
                manager.AfterRunForTests = _ => finished.TrySetResult(true);
                await manager.SubmitAsync(TestVideoFixtures.DefaultT2vRequest(),CancellationToken.None);
                await Bounded(finished.Task);
                Assert.Equal(VideoJobState.Interrupted,ledger.ReadAll().Records.Single().State);
                Assert.Empty(store.List());
                var calls=provider.Calls;
                manager.ReconcileInterruptedJobs();
                Assert.Equal(calls,provider.Calls);
                Assert.True(ledger.ReadAll().Records.Single().ProviderHandle!.ProviderMetadata!.ContainsKey("vertex_binding"));
            }
            finally { if(Directory.Exists(root)) Directory.Delete(root,true); }
        }
    }
}
