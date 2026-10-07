using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Image.Vertex;
using Rook.Services.Vision.Video.Vertex;
using Rook.Tests.Services.Vision.Video.Vertex;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    public sealed class VertexDispatchAuthorizationTests
    {
        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task StaleDeliveredImageLeaseNeverDispatches(bool workforce)
        {
            var tokens = new VertexTestTokenSource { Workforce = workforce, DisconnectAfterAcquire = true };
            var handler = new VertexTestHandler((_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{}") }));
            var result = await new VertexImageProvider(tokens, new HttpClient(handler)).SubmitAsync(
                new ImageGenerationRequest(VertexImageProvider.ModelKey, "building", "1K", "16:9", 1, null, new GeminiImageOptions()),
                new Dictionary<MediaRef, ResolvedMedia>(), CancellationToken.None);
            Assert.Equal(0, handler.Calls);
            Assert.Equal(GenerationErrorCode.Interrupted, Assert.IsType<FailedSubmitOutcome>(result).Error.Code);
        }

        [Theory]
        [InlineData("submit")]
        [InlineData("poll")]
        [InlineData("fetch")]
        public async Task StaleDeliveredVideoLeaseNeverDispatches(string operation)
        {
            var tokens = new VertexTestTokenSource { Workforce = true };
            var binding = (await tokens.AcquireAsync(VertexVeoTests.Model, "us-central1", null, CancellationToken.None)).Lease!.Binding;
            tokens.DisconnectAfterAcquire = true;
            var handler = new VertexTestHandler((_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{}") }));
            var provider = new VertexVeoProvider(tokens, new VertexVeoClient(new HttpClient(handler)));
            var handle = new ProviderJobHandle(VertexVeoTests.Operation, providerMetadata: binding.ToMetadata());
            var dispatches = 0;
            if (operation == "submit") Assert.IsType<FailedSubmitOutcome>(await provider.SubmitWithDispatchAsync(VertexVeoTests.Request(), new Dictionary<MediaRef, ResolvedMedia>(), () => dispatches++, CancellationToken.None));
            else if (operation == "poll") Assert.IsType<FailedStatusOutcome>(await provider.GetStatusAsync(handle, CancellationToken.None));
            else Assert.IsType<FailedResultOutcome>(await provider.FetchResultAsync(handle, CancellationToken.None));
            Assert.Equal(0, handler.Calls);
            Assert.Equal(0, dispatches);
        }
    }
}
