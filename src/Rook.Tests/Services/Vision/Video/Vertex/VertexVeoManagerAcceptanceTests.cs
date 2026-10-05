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
using Rook.Tests.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Vertex
{
    public sealed class VertexVeoManagerAcceptanceTests
    {
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
