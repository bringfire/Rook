using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Fal;
using Rook.Services.Vision.Fal;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Fal
{
    public class FalNanoBananaPricingModelTests
    {
        private static ImageGenerationRequest Request(string model = "fal-ai/nano-banana-2",
            string resolution = "1K", string aspect = "") =>
            new(model, "unchanged prompt", resolution, aspect, 1, null, new FalImageOptions());
        private static Dictionary<MediaRef, ResolvedMedia> Empty() => new();
        private static FalImageProvider Provider(TestHttpMessageHandler http, string? key = "key") =>
            new(() => key, new FalApiClient(new HttpClient(http)));
        private static HttpResponseMessage Response(int status, string body) =>
            new((HttpStatusCode)status) { Content = new StringContent(body, Encoding.UTF8, "application/json") };
        private const string Success = "{\"images\":[{\"url\":\"https://fal.media/result.png\",\"content_type\":\"image/png\"}]}";

        [Theory]
        [InlineData("fal-ai/nano-banana-2", "0.5K", "", true)]
        [InlineData("fal-ai/nano-banana-2", "512", "", false)]
        [InlineData("fal-ai/nano-banana-2", "4K", "8:1", true)]
        [InlineData("fal-ai/nano-banana-pro", "1K", "", true)]
        [InlineData("fal-ai/nano-banana-pro", "2K", "16:9", true)]
        [InlineData("fal-ai/nano-banana-pro", "4K", "1:1", true)]
        [InlineData("fal-ai/nano-banana-pro", "0.5K", "", false)]
        [InlineData("fal-ai/nano-banana-pro", "1K", "8:1", false)]
        public async Task NativeResolutionAndAspectAreValidatedBeforeDispatch(string model, string resolution, string aspect, bool valid)
        {
            var http = new TestHttpMessageHandler { OnSend = _ => Response(200, Success) };
            var prepare = 0; var send = 0;
            var outcome = await Provider(http).SubmitAsync(Request(model, resolution, aspect), Empty(),
                _ => { prepare++; return Task.FromResult<GenerationError?>(null); }, () => send++, CancellationToken.None);
            Assert.Equal(valid ? 1 : 0, prepare); Assert.Equal(prepare, send);
            Assert.Equal(prepare, http.Requests.Count);
            if (!valid) Assert.IsType<FailedSubmitOutcome>(outcome);
        }

        [Fact]
        public void PayloadPreservesSourceOrderAndRepeatedReferences()
        {
            var source = MediaRef.ForPath("source", ImageMediaRoles.InputImage);
            var a = MediaRef.ForPath("a", ImageMediaRoles.ReferenceImage);
            var b = MediaRef.ForPath("b", ImageMediaRoles.ReferenceImage);
            var media = new Dictionary<MediaRef, ResolvedMedia>
            {
                [b] = new(new byte[] { 67 }, "image/webp"),
                [a] = new(new byte[] { 66 }, "image/jpeg"),
                [source] = new(new byte[] { 65 }, "image/png")
            };
            var body = JsonNode.Parse(FalNanoBananaPayload.Encode(Request(resolution: "0.5K")
                .With(referenceImages: new[] { a, a, b }), media))!;
            Assert.Equal(new[] { "data:image/png;base64,QQ==", "data:image/jpeg;base64,Qg==",
                "data:image/jpeg;base64,Qg==", "data:image/webp;base64,Qw==" },
                body["image_urls"]!.AsArray().Select(n => n!.GetValue<string>()));
            Assert.Equal("0.5K", body["resolution"]!.GetValue<string>());
            Assert.Equal("unchanged prompt", body["prompt"]!.GetValue<string>());
            Assert.Equal(1, body["num_images"]!.GetValue<int>());
            Assert.True(body["limit_generations"]!.GetValue<bool>());
            Assert.False(body["sync_mode"]!.GetValue<bool>());
            Assert.Equal("png", body["output_format"]!.GetValue<string>());
            Assert.Null(body["safety_tolerance"]);
        }

        [Theory]
        [InlineData("fal-ai/nano-banana-2", false, "fal-ai/nano-banana-2")]
        [InlineData("fal-ai/nano-banana-2", true, "fal-ai/nano-banana-2/edit")]
        [InlineData("fal-ai/nano-banana-pro", false, "fal-ai/nano-banana-pro")]
        [InlineData("fal-ai/nano-banana-pro", true, "fal-ai/nano-banana-pro/edit")]
        public void LocallySelectedEndpoint(string model, bool media, string endpoint) =>
            Assert.Equal(endpoint, FalNanoBananaPayload.EndpointId(model, media));

        [Theory]
        [InlineData(401, true)]
        [InlineData(403, false)]
        [InlineData(402, false)]
        [InlineData(422, false)]
        [InlineData(429, false)]
        [InlineData(500, false)]
        public async Task FalCredentialPolicyRequires401(int status, bool rejected)
        {
            var http = new TestHttpMessageHandler { OnSend = _ => Response(status, "{\"detail\":\"Invalid key\"}") };
            var failure = Assert.IsType<FailedSubmitOutcome>(await Provider(http).SubmitAsync(Request(), Empty(), CancellationToken.None));
            Assert.Equal(rejected, ImageCredentialErrors.FromError("fal", failure.Error) != null);
        }

        [Fact]
        public async Task LocalCredentialAndDurablePreparationFailuresNeverSend()
        {
            var http = new TestHttpMessageHandler { OnSend = _ => Response(200, Success) };
            var prepare = 0; var send = 0;
            var result = await Provider(http, " ").SubmitAsync(Request(), Empty(),
                _ => { prepare++; return Task.FromResult<GenerationError?>(null); }, () => send++, CancellationToken.None);
            Assert.Equal(ImageCredentialErrors.FalMissing, Assert.IsType<FailedSubmitOutcome>(result).Error.ProviderErrorCode);
            Assert.Equal(0, prepare);
            result = await Provider(http).SubmitAsync(Request(), Empty(),
                _ => { prepare++; return Task.FromResult<GenerationError?>(new(GenerationErrorCode.ExecutionFailed, "Ledger failed.", false)); },
                () => send++, CancellationToken.None);
            Assert.IsType<FailedSubmitOutcome>(result);
            Assert.Equal(1, prepare); Assert.Equal(0, send); Assert.Empty(http.Requests);
        }

        [Theory]
        [InlineData("{}")]
        [InlineData("{\"images\":[]}")]
        [InlineData("{\"images\":[{},{}]}")]
        [InlineData("{\"images\":[{\"url\":\"http://fal.media/output.png\"}]}")]
        [InlineData("{\"images\":[{\"url\":\"data:image/png;base64,QQ==\"}]}")]
        [InlineData("{\"images\":[{\"url\":42}]}")]
        [InlineData("[]")]
        public async Task InvalidRemoteResultFails(string body)
        {
            var http = new TestHttpMessageHandler { OnSend = _ => Response(200, body) };
            var result = Assert.IsType<SyncSubmitOutcome>(await Provider(http).SubmitAsync(Request(), Empty(), CancellationToken.None));
            Assert.IsType<FailedResultOutcome>(result.Result);
        }

        [Fact]
        public void InvalidMediaIsRejectedInsteadOfDropped()
        {
            var source = MediaRef.ForPath("a", ImageMediaRoles.InputImage);
            var extra = MediaRef.ForPath("b", ImageMediaRoles.InputImage);
            var bytes = new ResolvedMedia(new byte[] { 65 }, "image/png");
            Assert.Throws<ArgumentException>(() => FalNanoBananaPayload.Encode(Request(),
                new Dictionary<MediaRef, ResolvedMedia> { [source] = bytes, [extra] = bytes }));
            Assert.Throws<ArgumentException>(() => FalNanoBananaPayload.Encode(Request().With(referenceImages:
                new[] { MediaRef.ForPath("absent", ImageMediaRoles.ReferenceImage) }), Empty()));
            Assert.Throws<ArgumentException>(() => FalNanoBananaPayload.Encode(Request(),
                new Dictionary<MediaRef, ResolvedMedia> { [MediaRef.ForPath("extra", "unaccounted")] = bytes }));
        }

        [Theory]
        [InlineData("fal-ai/nano-banana-2")]
        [InlineData("fal-ai/nano-banana-pro")]
        public void RegisteredSynchronousModelHasUnavailablePricing(string model)
        {
            var registration = new FalImageProviderRegistration(Provider(new TestHttpMessageHandler { OnSend = _ => Response(200, Success) }));
            Assert.Equal(ImageSubmissionMode.Sync, registration.GetSubmissionMode(model));
            var entry = registration.Models[model];
            var pricing = entry.PricingModel.Estimate(Request(model), entry.Capability);
            Assert.Null(pricing.Pricing!.UnitPrice);
            Assert.Null(pricing.Pricing.TotalUsd);
            Assert.False(pricing.Estimate!.IsExact);
            Assert.Equal("fal-nano-banana-unavailable-2026-10-12", entry.PricingModel.PricingSource);
            Assert.Null(entry.PricingModel.ExtractActualSpend(new Dictionary<string, IReadOnlyList<string>>(), null));
        }
    }
}
