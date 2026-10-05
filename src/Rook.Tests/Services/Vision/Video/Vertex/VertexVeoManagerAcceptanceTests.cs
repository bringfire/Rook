using System;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Vertex;
using Rook.Services.Vision.Image.Vertex;
using Rook.Tests.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Vertex
{
    public sealed class VertexVeoManagerAcceptanceTests
    {
        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task DisconnectDuringCompletion_CannotPublish(bool localStop)
        {
            var root = Path.Combine(Path.GetTempPath(), "rook-firm-race-" + Guid.NewGuid().ToString("N"));
            try {
                var store = new ArtifactStore(root); var ledger = new FakeVideoJobLedger();
                var tokens = new VertexTestTokenSource { Workforce = true };
                var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                var finished = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                tokens.OnValidate = async (binding, _) => {
                    if (tokens.ValidateCalls == 3) { entered.TrySetResult(true); await release.Task; }
                    return binding.AuthorizationGeneration == tokens.Generation ? null : new VertexAccessTokenFailure("vertex_authorization_changed", "Changed.", false);
                };
                var http = new VertexTestHandler((request, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(request.RequestUri!.AbsoluteUri.EndsWith(":predictLongRunning") ? "{\"name\":\"" + VertexVeoTests.Operation + "\"}" : "{\"done\":true,\"response\":{\"videos\":[{\"mimeType\":\"video/mp4\",\"bytesBase64Encoded\":\"AAAAGGZ0eXA=\"}]}}") }));
                var provider = new VertexVeoProvider(tokens, new VertexVeoClient(new HttpClient(http)));
                var registry = new DefaultVideoProviderRegistry(new[] { new VertexVeoProviderRegistration(provider) });
                using var manager = new VideoJobManager(registry, new FakeVideoMediaResolver(), ledger, new VideoCostEstimator(), store, null, null, TimeSpan.FromMilliseconds(1), 2, null, new FakePosterProducer(store), new FakeFrameProducer(store));
                manager.AfterRunForTests = _ => finished.TrySetResult(true);
                var job = await manager.SubmitAsync(VertexVeoTests.Request(), CancellationToken.None);
                Assert.Same(entered.Task, await Task.WhenAny(entered.Task, Task.Delay(5000)));
                if (localStop) Assert.Equal(VideoJobState.Interrupted, (await manager.CancelAsync(job.JobId!.Value, CancellationToken.None)).State);
                else tokens.Generation = new string('d', 32);
                release.TrySetResult(true);
                Assert.Same(finished.Task, await Task.WhenAny(finished.Task, Task.Delay(5000)));
                var latest = ledger.ReadAll().Records.Single();
                Assert.Equal(VideoJobState.Interrupted, latest.State); Assert.Empty(store.List()); Assert.Equal(3, http.Calls);
                var jsonl = new JsonlVideoJobLedger(Path.Combine(root, "jobs.jsonl"));
                jsonl.Append(latest with { State = VideoJobState.Polling });
                var persisted = jsonl.ReadAll().Records.Single();
                var binding = VertexAuthorizationBinding.FromMetadata(persisted.ProviderHandle!.ProviderMetadata!);
                Assert.Equal(2, binding!.BindingVersion); Assert.Equal(tokens.PrincipalId, binding.PrincipalId);
                using var restarted = new VideoJobManager(registry, new FakeVideoMediaResolver(), jsonl, new VideoCostEstimator(), store);
                restarted.ReconcileInterruptedJobs();
                Assert.Equal(VideoJobState.Interrupted, jsonl.ReadAll().Records.Single().State); Assert.Equal(3, http.Calls);
            }
            finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
        }

        [Fact]
        public async Task StopAfterUnknownSubmitReturnsRetainsClassification()
        {
            var root=Path.Combine(Path.GetTempPath(),"rook-vertex-return-stop-"+Guid.NewGuid().ToString("N"));
            try
            {
                var store=new ArtifactStore(root); var ledger=new FakeVideoJobLedger();
                var http=new VertexTestHandler((_,_)=>Task.FromResult(new HttpResponseMessage(HttpStatusCode.ServiceUnavailable) {Content=new StringContent("{}") }));
                var provider=new VertexVeoProvider(new VertexTestTokenSource(),new VertexVeoClient(new HttpClient(http)));
                var registry=new DefaultVideoProviderRegistry(new[]{new VertexVeoProviderRegistration(provider)});
                var entered=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                var release=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                var finished=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                using var manager=new VideoJobManager(registry,new FakeVideoMediaResolver(),ledger,new VideoCostEstimator(),store);
                manager.AfterSubmitForTests=async _=>{entered.TrySetResult(true);await release.Task;};
                manager.AfterRunForTests=_=>finished.TrySetResult(true);
                var job=await manager.SubmitAsync(VertexVeoTests.Request(),CancellationToken.None);
                Assert.Same(entered.Task,await Task.WhenAny(entered.Task,Task.Delay(5000)));
                Assert.Equal(VideoJobState.Interrupted,(await manager.CancelAsync(job.JobId!.Value,CancellationToken.None)).State);
                release.TrySetResult(true);
                Assert.Same(finished.Task,await Task.WhenAny(finished.Task,Task.Delay(5000)));
                var latest=ledger.ReadAll().Records.Single();
                Assert.Equal(VideoJobState.Interrupted,latest.State);
                Assert.Equal("vertex_submission_unknown",latest.Error!.ProviderErrorCode);
                Assert.True((await manager.GetStatusAsync(job.JobId!.Value,CancellationToken.None)).Error!.SubmissionOutcomeUnknown);
                Assert.Equal(1,http.Calls); Assert.Empty(store.List());
            }
            finally {if(Directory.Exists(root))Directory.Delete(root,true);}
        }
        private sealed class BlockingTokens : IVertexAccessTokenSource
        {
            internal readonly VertexTestTokenSource Source=new();
            internal Func<CancellationToken,Task>? BeforeAcquire;
            public async Task<VertexAccessTokenResult> AcquireAsync(string model,string location,VertexAuthorizationBinding? expected,CancellationToken ct)
            { if(BeforeAcquire is not null) await BeforeAcquire(ct); return await Source.AcquireAsync(model,location,expected,ct); }
            public Task<VertexAccessTokenFailure?> ValidateBindingAsync(VertexAuthorizationBinding binding,CancellationToken ct) => Source.ValidateBindingAsync(binding,ct);
        }
        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task StopClassifiesUnknownOnlyAfterSubmissionDispatch(bool dispatched)
        {
            var root=Path.Combine(Path.GetTempPath(),"rook-vertex-submit-stop-"+Guid.NewGuid().ToString("N"));
            try
            {
                var store=new ArtifactStore(root); var ledger=new FakeVideoJobLedger(); var tokens=new BlockingTokens();
                var entered=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                async Task Block(CancellationToken ct) {entered.TrySetResult(true); await Task.Delay(Timeout.Infinite,ct);}
                if(!dispatched) tokens.BeforeAcquire=Block;
                var http=new VertexTestHandler(async (_,ct)=>{await Block(ct); return new HttpResponseMessage(HttpStatusCode.OK);});
                var provider=new VertexVeoProvider(tokens,new VertexVeoClient(new HttpClient(http)));
                var registry=new DefaultVideoProviderRegistry(new[]{new VertexVeoProviderRegistration(provider)});
                var finished=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                using var manager=new VideoJobManager(registry,new FakeVideoMediaResolver(),ledger,new VideoCostEstimator(),store);
                manager.AfterRunForTests=_=>finished.TrySetResult(true);
                var submitted=await manager.SubmitAsync(VertexVeoTests.Request(),CancellationToken.None);
                Assert.Same(entered.Task,await Task.WhenAny(entered.Task,Task.Delay(5000)));
                Assert.Equal(VideoJobState.Interrupted,(await manager.CancelAsync(submitted.JobId!.Value,CancellationToken.None)).State);
                Assert.Same(finished.Task,await Task.WhenAny(finished.Task,Task.Delay(5000)));
                var latest=ledger.ReadAll().Records.Single();
                Assert.True(latest.State==VideoJobState.Interrupted,latest.Error?.Message);
                Assert.Equal(dispatched ? "vertex_submission_unknown" : null,latest.Error!.ProviderErrorCode);
                Assert.Equal(dispatched,(await manager.GetStatusAsync(submitted.JobId!.Value,CancellationToken.None)).Error!.SubmissionOutcomeUnknown);
                Assert.Equal(dispatched,(await manager.ListJobsAsync(10,CancellationToken.None)).Jobs.Single().Error!.SubmissionOutcomeUnknown);
                Assert.Equal(dispatched ? 1 : 0,http.Calls); Assert.Empty(store.List());
                manager.ReconcileInterruptedJobs(); Assert.Equal(dispatched ? 1 : 0,http.Calls);
            }
            finally {if(Directory.Exists(root))Directory.Delete(root,true);}
        }
        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task ReadDeadlineInterruptsOriginalOperationWithoutPublication(bool duringFetch)
        {
            var root=Path.Combine(Path.GetTempPath(),"rook-vertex-timeout-"+Guid.NewGuid().ToString("N"));
            try
            {
                var store=new ArtifactStore(root); var ledger=new FakeVideoJobLedger(); var reads=0;
                var http=new VertexTestHandler(async (request,ct) =>
                {
                    if(request.RequestUri!.AbsoluteUri.EndsWith(":predictLongRunning"))
                        return new HttpResponseMessage(HttpStatusCode.OK) {Content=new StringContent("{\"name\":\""+VertexVeoTests.Operation+"\"}")};
                    if(!duringFetch || ++reads==2) await Task.Delay(Timeout.Infinite,ct);
                    return new HttpResponseMessage(HttpStatusCode.OK) {Content=new StringContent("{\"done\":true,\"response\":{\"videos\":[{\"mimeType\":\"video/mp4\",\"bytesBase64Encoded\":\"AAAAGGZ0eXA=\"}]}}")};
                });
                var provider=new VertexVeoProvider(new VertexTestTokenSource(),new VertexVeoClient(new HttpClient(http)),operationTimeout:TimeSpan.FromMilliseconds(100));
                var registry=new DefaultVideoProviderRegistry(new[]{new VertexVeoProviderRegistration(provider)});
                var finished=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                using var manager=new VideoJobManager(registry,new FakeVideoMediaResolver(),ledger,new VideoCostEstimator(),store);
                manager.AfterRunForTests=_=>finished.TrySetResult(true);
                await manager.SubmitAsync(VertexVeoTests.Request(),CancellationToken.None);
                Assert.Same(finished.Task,await Task.WhenAny(finished.Task,Task.Delay(5000)));
                var latest=ledger.ReadAll().Records.Single();
                Assert.True(latest.State==VideoJobState.Interrupted,latest.Error?.Message);
                Assert.Equal(VertexVeoTests.Operation,latest.ProviderHandle!.ProviderJobId);
                Assert.Contains("vertex_binding",latest.ProviderHandle.ProviderMetadata!.Keys);
                Assert.False(latest.Error!.Retryable); Assert.Equal("vertex_monitoring_timeout",latest.Error.ProviderErrorCode);
                Assert.Contains("may continue and incur charges",latest.Error.Message);
                Assert.Empty(store.List()); Assert.Equal(duringFetch ? 3 : 2,http.Calls);
            }
            finally {if(Directory.Exists(root))Directory.Delete(root,true);}
        }
        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task ExplicitVertexProviderUsesExistingLedgerAndArtifacts(bool disconnect)
        {
            var root=Path.Combine(Path.GetTempPath(),"rook-vertex-acceptance-"+Guid.NewGuid().ToString("N"));
            try
            {
                var store=new ArtifactStore(root); var ledger=new FakeVideoJobLedger(); var tokens=new VertexTestTokenSource();
                var http=new VertexTestHandler((request,_) =>
                {
                    var submit=request.RequestUri!.AbsoluteUri.EndsWith(":predictLongRunning");
                    if(!submit && disconnect) tokens.Generation="fedcba9876543210fedcba9876543210";
                    return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) {Content=new StringContent(submit ?
                        "{\"name\":\""+VertexVeoTests.Operation+"\"}" : "{\"done\":true,\"response\":{\"videos\":[{\"mimeType\":\"video/mp4\",\"bytesBase64Encoded\":\"AAAAGGZ0eXA=\"}]}}")});
                });
                var provider=new VertexVeoProvider(tokens,new VertexVeoClient(new HttpClient(http)));
                var registry=new DefaultVideoProviderRegistry(new[]{new VertexVeoProviderRegistration(provider)});
                var finished=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                using var manager=new VideoJobManager(registry,new FakeVideoMediaResolver(),ledger,new VideoCostEstimator(),store,null,null,TimeSpan.FromMilliseconds(1),2,null,new FakePosterProducer(store),new FakeFrameProducer(store));
                manager.AfterRunForTests=_=>finished.TrySetResult(true);
                var submitted=await manager.SubmitAsync(VertexVeoTests.Request(),CancellationToken.None);
                Assert.Null(submitted.Error);
                Assert.Same(finished.Task,await Task.WhenAny(finished.Task,Task.Delay(5000)));
                await finished.Task;
                var latest=ledger.ReadAll().Records.Single();
                Assert.Equal(disconnect ? VideoJobState.Interrupted : VideoJobState.Complete,latest.State);
                Assert.Equal(VertexVeoTests.Operation,latest.ProviderHandle!.ProviderJobId);
                Assert.Equal(disconnect ? 0 : 1,store.List().Count);
                Assert.Equal(disconnect ? 2 : 3,http.Calls);
                var persisted=latest with {State=VideoJobState.Polling,ResultArtifactId=null,Error=null};
                var restartLedger=new FakeVideoJobLedger();restartLedger.Append(persisted);
                using var restarted=new VideoJobManager(registry,new FakeVideoMediaResolver(),restartLedger,new VideoCostEstimator(),store);
                restarted.ReconcileInterruptedJobs();
                Assert.Equal(VideoJobState.Interrupted,restartLedger.ReadAll().Records.Single().State);
                Assert.Equal(disconnect ? 2 : 3,http.Calls);
            }
            finally { if(Directory.Exists(root))Directory.Delete(root,true); }
        }
    }
}
