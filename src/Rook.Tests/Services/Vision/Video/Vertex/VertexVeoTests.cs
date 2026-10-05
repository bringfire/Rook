using System;
using System.Collections.Generic;
using System.Net;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Vertex;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Vertex;
using Rook.Tests.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Vertex
{
    public sealed class VertexVeoTests
    {
        internal const string Model = "vertex_ai/veo-3.1-fast-generate-001";
        internal const string Operation = "projects/company-project/locations/us-central1/publishers/google/models/veo-3.1-fast-generate-001/operations/accepted_job";
        internal static VideoGenerationRequest Request() => new(Model,VideoMode.T2V,4,"720p","16:9","a building",null,null,null,null,new VertexVeoOptions(PersonGenerationPolicy.AllowAdult),1);
        private static HttpResponseMessage Response(int status,string body) => new((HttpStatusCode)status) {Content=new StringContent(body,Encoding.UTF8,"application/json")};
        [Fact]
        public async Task SubmitPollAndFetchUseOriginalOperationAndInlineBytes()
        {
            var tokens = new VertexTestTokenSource();
            var handler = new VertexTestHandler(async (request,_) =>
            {
                Assert.Equal("Bearer",request.Headers.Authorization!.Scheme);
                Assert.False(request.Headers.Contains("x-goog-api-key"));
                Assert.False(request.Headers.Contains("x-goog-user-project"));
                var json = await request.Content!.ReadAsStringAsync();
                if(request.RequestUri!.AbsoluteUri.EndsWith(":predictLongRunning"))
                {
                    using var doc=JsonDocument.Parse(json);
                    Assert.Equal(1,doc.RootElement.GetProperty("parameters").GetProperty("sampleCount").GetInt32());
                    Assert.Equal("allow_adult",doc.RootElement.GetProperty("parameters").GetProperty("personGeneration").GetString());
                    Assert.DoesNotContain("storageUri",json);
                    return Response(200,"{\"name\":\""+Operation+"\"}");
                }
                Assert.EndsWith(":fetchPredictOperation",request.RequestUri.AbsoluteUri);
                Assert.Equal(Operation,JsonDocument.Parse(json).RootElement.GetProperty("operationName").GetString());
                return Response(200,"{\"done\":true,\"response\":{\"videos\":[{\"bytesBase64Encoded\":\"AQIDBA==\",\"mimeType\":\"video/mp4\"}]}}");
            });
            var provider=new VertexVeoProvider(tokens,new VertexVeoClient(new HttpClient(handler)));
            var handle=Assert.IsType<QueuedSubmitOutcome>(await provider.SubmitAsync(Request(),new Dictionary<MediaRef,ResolvedMedia>(),CancellationToken.None)).Handle;
            Assert.Null(handle.ProviderResultToken);
            var complete=Assert.IsType<ProviderCompleteStatusOutcome>(await provider.GetStatusAsync(Model,handle,CancellationToken.None));
            Assert.Null(complete.UpdatedHandle.ProviderResultToken);
            Assert.DoesNotContain("AQIDBA",complete.UpdatedHandle.ProviderMetadata!["vertex_binding"].ToJsonString());
            var success=Assert.IsType<SuccessResultOutcome>(await provider.FetchResultAsync(Model,handle,CancellationToken.None));
            Assert.Equal(new byte[]{1,2,3,4},Assert.IsType<InlineArtifactBody>(Assert.Single(success.Envelope.Artifacts).Body).Bytes);
            Assert.IsType<LocalStopOnlyOutcome>(await provider.CancelAsync(handle,CancellationToken.None));
            Assert.Equal(3,handler.Calls);
        }
        [Fact]
        public async Task FirmQuotaHeader_IsBoundOnSubmitAndEveryPoll()
        {
            var tokens = new VertexTestTokenSource { Workforce = true };
            var handler = new VertexTestHandler((request, _) => {
                Assert.Equal("synthetic-firm-project", request.Headers.GetValues("x-goog-user-project").Single());
                Assert.Contains("projects/company-project/locations/us-central1/", request.RequestUri!.AbsoluteUri);
                Assert.False(request.Headers.Contains("x-goog-api-key"));
                return Task.FromResult(Response(200, request.RequestUri.AbsoluteUri.EndsWith(":predictLongRunning") ? "{\"name\":\"" + Operation + "\"}" : "{\"done\":true,\"response\":{\"videos\":[{\"bytesBase64Encoded\":\"AQIDBA==\",\"mimeType\":\"video/mp4\"}]}}"));
            });
            var provider = new VertexVeoProvider(tokens, new VertexVeoClient(new HttpClient(handler)));
            var handle = Assert.IsType<QueuedSubmitOutcome>(await provider.SubmitAsync(Request(), new Dictionary<MediaRef, ResolvedMedia>(), CancellationToken.None)).Handle;
            Assert.IsType<ProviderCompleteStatusOutcome>(await provider.GetStatusAsync(handle, CancellationToken.None));
            Assert.IsType<SuccessResultOutcome>(await provider.FetchResultAsync(handle, CancellationToken.None));
            Assert.Equal(3, handler.Calls);
            tokens.Generation = new string('d', 32); // Same employee reconnects deliberately.
            Assert.IsType<FailedStatusOutcome>(await provider.GetStatusAsync(handle, CancellationToken.None));
            Assert.Equal(3, handler.Calls);
        }
        [Theory]
        [InlineData(401)] [InlineData(429)] [InlineData(500)] [InlineData(302)] [InlineData(200)]
        public async Task LostOrRefusedSubmissionSendsExactlyOnce(int status)
        {
            var handler=new VertexTestHandler((_,_)=>Task.FromResult(Response(status,"{\"error\":\"secret-bearer-sentinel\"}")));
            var provider=new VertexVeoProvider(new VertexTestTokenSource(),new VertexVeoClient(new HttpClient(handler)));
            var failed=Assert.IsType<FailedSubmitOutcome>(await provider.SubmitAsync(Request(),new Dictionary<MediaRef,ResolvedMedia>(),CancellationToken.None));
            Assert.False(failed.Error.Retryable); Assert.Null(failed.Error.ProviderDetail);
            Assert.DoesNotContain("secret-bearer-sentinel",failed.Error.Message);
            Assert.Equal(1,handler.Calls);
        }
        [Theory]
        [InlineData("https://evil.example/job")] [InlineData("projects/other-project/locations/us-central1/publishers/google/models/veo-3.1-fast-generate-001/operations/job")]
        [InlineData(Operation+"/../job")]
        public async Task OperationMismatchAndUnboundHandleMakeZeroCalls(string operation)
        {
            var tokens=new VertexTestTokenSource();
            var handler=new VertexTestHandler((_,_)=>throw new Exception("No Google call"));
            var provider=new VertexVeoProvider(tokens,new VertexVeoClient(new HttpClient(handler)));
            var lease=(await tokens.AcquireAsync(Model,"us-central1",null,CancellationToken.None)).Lease!;
            var handle=new ProviderJobHandle(operation,providerMetadata:lease.Binding.ToMetadata());
            Assert.IsType<FailedStatusOutcome>(await provider.GetStatusAsync(Model,handle,CancellationToken.None));
            Assert.IsType<FailedResultOutcome>(await provider.FetchResultAsync(new ProviderJobHandle(Operation),CancellationToken.None));
            Assert.Equal(0,handler.Calls);
        }
        [Theory]
        [InlineData("{\"done\":true,\"response\":{\"videos\":[{\"gcsUri\":\"gs://bucket/file\",\"mimeType\":\"video/mp4\"}]}}")]
        [InlineData("{\"done\":true,\"response\":{\"videos\":[{\"bytesBase64Encoded\":\"bad!\",\"mimeType\":\"video/mp4\"}]}}")]
        [InlineData("{\"done\":true,\"response\":{\"videos\":[]}}")]
        [InlineData("{\"done\":true,\"error\":{\"message\":\"secret-bearer-sentinel\"}}")]
        public async Task InvalidTerminalOutputIsFixedFailure(string body)
        {
            var tokens=new VertexTestTokenSource();
            var binding=(await tokens.AcquireAsync(Model,"us-central1",null,CancellationToken.None)).Lease!.Binding;
            var provider=new VertexVeoProvider(tokens,new VertexVeoClient(new HttpClient(new VertexTestHandler((_,_)=>Task.FromResult(Response(200,body))))));
            var error=Assert.IsType<FailedResultOutcome>(await provider.FetchResultAsync(new ProviderJobHandle(Operation,providerMetadata:binding.ToMetadata()),CancellationToken.None)).Error;
            Assert.Null(error.ProviderDetail); Assert.DoesNotContain("secret-bearer-sentinel",error.Message);
        }
        [Fact]
        public async Task ReadsRetryAtMostThreeTimesAndBindEveryLease()
        {
            var tokens=new VertexTestTokenSource();
            var binding=(await tokens.AcquireAsync(Model,"us-central1",null,CancellationToken.None)).Lease!.Binding;
            var handler=new VertexTestHandler((_,_)=>Task.FromResult(Response(503,"{}")));
            var delays=new List<TimeSpan>();
            var provider=new VertexVeoProvider(tokens,new VertexVeoClient(new HttpClient(handler)),(delay,_)=>{delays.Add(delay);return Task.CompletedTask;});
            Assert.IsType<FailedStatusOutcome>(await provider.GetStatusAsync(new ProviderJobHandle(Operation,providerMetadata:binding.ToMetadata()),CancellationToken.None));
            Assert.Equal(3,handler.Calls); Assert.Equal(4,tokens.AcquireCalls);
            Assert.Equal(new[]{TimeSpan.FromSeconds(1),TimeSpan.FromSeconds(2)},delays);
        }
        [Fact]
        public async Task DisconnectAfterPollAndChangeBeforeRetryInterrupts()
        {
            var tokens=new VertexTestTokenSource();
            var binding=(await tokens.AcquireAsync(Model,"us-central1",null,CancellationToken.None)).Lease!.Binding;
            var handler=new VertexTestHandler((_,_)=>{tokens.Generation="fedcba9876543210fedcba9876543210";return Task.FromResult(Response(503,"{}"));});
            var provider=new VertexVeoProvider(tokens,new VertexVeoClient(new HttpClient(handler)),(_,_)=>Task.CompletedTask);
            var error=Assert.IsType<FailedStatusOutcome>(await provider.GetStatusAsync(new ProviderJobHandle(Operation,providerMetadata:binding.ToMetadata()),CancellationToken.None)).Error;
            Assert.Equal(GenerationErrorCode.Interrupted,error.Code); Assert.Equal(1,handler.Calls);
        }
        [Theory]
        [InlineData("{\"done\":true,\"response\":{\"videos\":[{\"bytesBase64Encoded\":\"\",\"mimeType\":\"video/mp4\"}]}}")]
        [InlineData("{\"done\":true,\"response\":{\"videos\":[{\"bytesBase64Encoded\":\"AQIDBA==\",\"mimeType\":\"video/mp4\",\"uri\":\"https://evil.example\"}]}}")]
        [InlineData("{\"done\":true,\"response\":{\"videos\":[{},{}]}}")]
        public void ConflictingOrEmptyInlineOutputIsRejected(string body)
            => Assert.NotNull(VertexVeoClient.ParseOperation(Encoding.UTF8.GetBytes(body),Operation,true).Error);
        [Fact]
        public async Task OversizedHeadersAreRejectedWithoutDecodeOrRetry()
        {
            var tokens=new VertexTestTokenSource();
            var binding=(await tokens.AcquireAsync(Model,"us-central1",null,CancellationToken.None)).Lease!.Binding;
            var handler=new VertexTestHandler((_,_)=>{var response=Response(200,"{}");response.Content.Headers.ContentLength=VertexVeoClient.WireLimit+1;return Task.FromResult(response);});
            var provider=new VertexVeoProvider(tokens,new VertexVeoClient(new HttpClient(handler)));
            Assert.IsType<FailedResultOutcome>(await provider.FetchResultAsync(new ProviderJobHandle(Operation,providerMetadata:binding.ToMetadata()),CancellationToken.None));
            Assert.Equal(1,handler.Calls);
        }
        [Fact]
        public void VertexOptionsAndCatalogStaySeparateFromDeveloperApi()
        {
            var codec=new VertexVeoOptionsCodec();
            Assert.True(codec.Deserialize(new System.Text.Json.Nodes.JsonObject { ["person_generation"]="disallow" }).Success);
            Assert.False(codec.Deserialize(new System.Text.Json.Nodes.JsonObject { ["person_generation"]="dont_allow" }).Success);
            Assert.False(codec.Validate(Request(),new VertexVeoOptions(PersonGenerationPolicy.AllowAll),VertexVeoProviderRegistration.Capability).Success);
            var registration=new VertexVeoProviderRegistration(new VertexVeoProvider(UnavailableVertexAccessTokenSource.Instance));
            Assert.Equal(Model,Assert.Single(registration.Models).Key); Assert.Empty(registration.SecretRequirements);
            Assert.DoesNotContain("4k",VertexVeoProviderRegistration.Capability.Resolutions);
        }
    }
}
