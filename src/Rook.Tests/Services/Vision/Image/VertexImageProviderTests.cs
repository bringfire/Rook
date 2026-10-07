using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Image.Vertex;
using Rook.Tests.Services.Vision.Generation;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Vision;
using System.Text.Json;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public sealed class VertexImageProviderTests
    {
        private const string Success = "{\"candidates\":[{\"content\":{\"parts\":[{\"inlineData\":{\"mimeType\":\"image/png\",\"data\":\"AQIDBA==\"}}]}}]}";
        private static ImageGenerationRequest Request(string model="vertex_ai/gemini-3.1-flash-image") => new(model,"a building","1K","16:9",1,null,new GeminiImageOptions());
        private static HttpResponseMessage Response(HttpStatusCode status,string json) => new(status) {Content=new StringContent(json,Encoding.UTF8,"application/json")};
        [Fact]
        public async Task GlobalEndpointUsesBearerAndExistingInlineEnvelope()
        {
            var tokens=new VertexTestTokenSource();
            var handler=new VertexTestHandler(async (request,_) =>
            {
                Assert.Equal("https://aiplatform.googleapis.com/v1/projects/company-project/locations/global/publishers/google/models/gemini-3.1-flash-image:generateContent",request.RequestUri!.AbsoluteUri);
                Assert.Equal("Bearer",request.Headers.Authorization!.Scheme);
                Assert.False(request.Headers.Contains("x-goog-api-key"));
                Assert.False(request.Headers.Contains("x-goog-user-project"));
                var json=await request.Content!.ReadAsStringAsync();
                Assert.Contains("\"responseModalities\":[\"IMAGE\"]",json);
                Assert.Contains("\"imageSize\":\"1K\"",json);
                return Response(HttpStatusCode.OK,Success);
            });
            var provider=new VertexImageProvider(tokens,new HttpClient(handler));
            var sync=Assert.IsType<SyncSubmitOutcome>(await provider.SubmitAsync(Request(),new Dictionary<MediaRef,ResolvedMedia>(),CancellationToken.None));
            var envelope=Assert.IsType<SuccessResultOutcome>(sync.Result).Envelope;
            Assert.Equal(new byte[]{1,2,3,4},Assert.IsType<InlineArtifactBody>(Assert.Single(envelope.Artifacts).Body).Bytes);
            Assert.Equal(tokens.Generation,VertexAuthorizationBinding.FromMetadata(envelope.EnvelopeMetadata)!.AuthorizationGeneration);
            Assert.DoesNotContain("secret-bearer-sentinel",envelope.EnvelopeMetadata["vertex_binding"].ToJsonString());
            Assert.Equal(1,handler.Calls);
        }
        [Theory]
        [InlineData(null)]
        [InlineData("synthetic-firm-project")]
        public async Task FirmImageQuotaIsOptionalAndBound(string? quota)
        {
            var tokens = new VertexTestTokenSource { Workforce = true, QuotaProject = quota };
            var handler = new VertexTestHandler((request, _) => {
                Assert.Equal(quota is not null, request.Headers.Contains("x-goog-user-project"));
                if (quota is not null) Assert.Equal(quota, Assert.Single(request.Headers.GetValues("x-goog-user-project")));
                return Task.FromResult(Response(HttpStatusCode.OK, Success));
            });
            var result = Assert.IsType<SyncSubmitOutcome>(await new VertexImageProvider(tokens, new HttpClient(handler)).SubmitAsync(Request(), new Dictionary<MediaRef, ResolvedMedia>(), CancellationToken.None));
            var metadata = Assert.IsType<SuccessResultOutcome>(result.Result).Envelope.EnvelopeMetadata;
            Assert.Equal(2, VertexAuthorizationBinding.FromMetadata(metadata)!.BindingVersion);
            Assert.Equal(1, handler.Calls);
        }
        [Theory]
        [InlineData(401)] [InlineData(429)] [InlineData(500)] [InlineData(302)]
        public async Task SubmissionFailureNeverRetriesOrLeaksProviderText(int status)
        {
            var handler=new VertexTestHandler((_,_) => Task.FromResult(Response((HttpStatusCode)status,"{\"error\":{\"message\":\"secret-bearer-sentinel\"}}")));
            var result=Assert.IsType<FailedSubmitOutcome>(await new VertexImageProvider(new VertexTestTokenSource(),new HttpClient(handler)).SubmitAsync(Request(),new Dictionary<MediaRef,ResolvedMedia>(),CancellationToken.None));
            Assert.False(result.Error.Retryable); Assert.Null(result.Error.ProviderDetail);
            Assert.DoesNotContain("secret-bearer-sentinel",result.Error.Message); Assert.Equal(1,handler.Calls);
        }
        [Theory]
        [InlineData("{}")]
        [InlineData("{\"candidates\":[{\"content\":{\"parts\":[{\"inlineData\":{\"mimeType\":\"image/png\",\"data\":\"bad!\"}}]}}]}")]
        [InlineData("{\"candidates\":[{\"content\":{\"parts\":[{\"inlineData\":{\"mimeType\":\"text/html\",\"data\":\"AQIDBA==\"}}]}}]}")]
        public async Task MalformedImageDataIsTypedAndBounded(string json)
        {
            var handler=new VertexTestHandler((_,_) => Task.FromResult(Response(HttpStatusCode.OK,json)));
            Assert.IsType<FailedSubmitOutcome>(await new VertexImageProvider(new VertexTestTokenSource(),new HttpClient(handler)).SubmitAsync(Request(),new Dictionary<MediaRef,ResolvedMedia>(),CancellationToken.None));
        }
        [Fact]
        public async Task AuthorizationChangeAfterResponseCannotPublish()
        {
            var tokens=new VertexTestTokenSource();
            var handler=new VertexTestHandler((_,_) => {tokens.Generation="fedcba9876543210fedcba9876543210"; return Task.FromResult(Response(HttpStatusCode.OK,Success));});
            var result=Assert.IsType<FailedSubmitOutcome>(await new VertexImageProvider(tokens,new HttpClient(handler)).SubmitAsync(Request(),new Dictionary<MediaRef,ResolvedMedia>(),CancellationToken.None));
            Assert.Equal(GenerationErrorCode.Interrupted,result.Error.Code);
        }
        [Fact]
        public async Task UnsupportedModelOrMissingAuthorizationMakesZeroGoogleCalls()
        {
            var tokens=new VertexTestTokenSource {Failure=new("vertex_signed_out","Signed out.",false)};
            var handler=new VertexTestHandler((_,_)=>throw new Exception("Google must not be called"));
            var provider=new VertexImageProvider(tokens,new HttpClient(handler));
            Assert.IsType<FailedSubmitOutcome>(await provider.SubmitAsync(Request("gemini-3.1-flash-image-preview"),new Dictionary<MediaRef,ResolvedMedia>(),CancellationToken.None));
            Assert.Equal(0,tokens.AcquireCalls);
            Assert.IsType<FailedSubmitOutcome>(await provider.SubmitAsync(Request(),new Dictionary<MediaRef,ResolvedMedia>(),CancellationToken.None));
            Assert.Equal(0,handler.Calls);
        }
        [Fact]
        public void CatalogHasOneExplicitQualifiedEntryAndNoApiKey()
        {
            var reg=new VertexImageProviderRegistration(new VertexImageProvider(UnavailableVertexAccessTokenSource.Instance));
            Assert.Equal("vertex_ai/gemini-3.1-flash-image",Assert.Single(reg.Models).Key);
            Assert.Empty(reg.SecretRequirements);
            Assert.Equal("gemini-3.1-flash-image-preview",GeminiImageCapabilities.DefaultModel);
        }
        [Fact]
        public async Task OversizedHeadersAndCallerCancellationCannotSubmitAgain()
        {
            var handler=new VertexTestHandler((_,_) =>
            {
                var response=Response(HttpStatusCode.OK,Success);
                response.Content.Headers.ContentLength=40L*1024*1024;
                return Task.FromResult(response);
            });
            var provider=new VertexImageProvider(new VertexTestTokenSource(),new HttpClient(handler));
            Assert.IsType<FailedSubmitOutcome>(await provider.SubmitAsync(Request(),new Dictionary<MediaRef,ResolvedMedia>(),CancellationToken.None));
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => provider.SubmitAsync(Request(),new Dictionary<MediaRef,ResolvedMedia>(),new CancellationToken(true)));
            Assert.Equal(1,handler.Calls);
        }
        [Theory]
        [InlineData(3)] [InlineData(4)]
        public async Task SynchronousHandlerGuardsBeforeCreateAndCommit(int failAt)
        {
            var root=Path.Combine(Path.GetTempPath(),Guid.NewGuid().ToString("N"));
            try
            {
                var store=new ArtifactStore(root);
                var input=store.Create("captured_viewport",new[]{new BlobInput("image",new byte[]{137,80,78,71,13,10,26,10,0},"png")});
                var tokens=new VertexTestTokenSource();
                tokens.OnValidate=(_,_) => Task.FromResult<VertexAccessTokenFailure?>(tokens.ValidateCalls >= failAt ? new("vertex_authorization_changed","Changed.",false) : null);
                var provider=new VertexImageProvider(tokens,new HttpClient(new VertexTestHandler((_,_) => Task.FromResult(Response(HttpStatusCode.OK,Success)))));
                var handler=new VisionHandler(store,new VisionSecretStore(),new PromptEnhancer(),new ViewportHandler(),new DefaultImageProviderRegistry(new[]{new VertexImageProviderRegistration(provider)}));
                var args=JsonSerializer.Deserialize<Dictionary<string,JsonElement>>("{\"model\":\"vertex_ai/gemini-3.1-flash-image\",\"prompt\":\"a building\",\"input_image\":{\"kind\":\"artifact_id\",\"artifact_id\":\""+input.Id+"\",\"role\":\"image\"},\"resolution\":\"1K\",\"aspect_ratio\":\"16:9\"}")!;
                Assert.False((await handler.GenerateAsync(args,CancellationToken.None)).Success);
                Assert.Single(store.List());
                Assert.Equal(input.Id,store.List()[0].Id);
            }
            finally { if(Directory.Exists(root)) Directory.Delete(root,true); }
        }
        [Fact]
        public void UnknownVertexModelNeverFallsBackToAiStudio()
        {
            var handler = new VisionHandler(new ArtifactStore(Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"))),
                new VisionSecretStore(), new PromptEnhancer(), new ViewportHandler());
            var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(
                "{\"model\":\"vertex_ai/unknown-model\",\"prompt\":\"a building\"}")!;
            Assert.False(handler.BuildImageGenerationWorkItem(args).Success);
        }
    }
}
