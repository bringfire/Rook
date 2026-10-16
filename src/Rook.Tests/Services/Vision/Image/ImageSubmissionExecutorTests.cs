using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Gemini;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public class ImageSubmissionExecutorTests
    {
        private static async Task<ImageSubmissionResult> Submit(ImageFallbackFixture f, string model,
            string resolution = "1K", string aspect = "")
        {
            Assert.True(f.Registry.TryResolve(model, out var resolved));
            return await f.Executor.SubmitAsync(f.Request(model, resolution, aspect), resolved, f.Media,
                new ImageExecutionContext(), CancellationToken.None);
        }
        [Theory]
        [InlineData(GeminiImageCapabilities.NanoBanana2, "fal-ai/nano-banana-2")]
        [InlineData(GeminiImageCapabilities.NanoBananaPro, "fal-ai/nano-banana-pro")]
        public async Task MissingGeminiFallsBackExactlyOnce(string model, string target)
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            var result = await Submit(f, model);
            Assert.Empty(f.GoogleHttp.Requests); Assert.Single(f.FalHttp.Requests);
            Assert.Equal("fal", result.Execution.EffectiveModel!.ProviderName);
            Assert.Equal(target, result.Execution.EffectiveRequest!.Model);
            Assert.Equal(ImageFallbackReason.GeminiKeyMissing, result.Execution.Routing!.Route!.FallbackReason);
            Assert.True(result.Execution.Routing.Route.GenerationDispatchAttempted);
            Assert.Equal(ImageFalDispatchState.Attempted, result.Execution.FalDispatchState);
        }
        [Fact]
        public async Task FallbackTranslates512OnlyInExecutor()
        {
            using var f = new ImageFallbackFixture(geminiKey: " ");
            var requested = f.Request(GeminiImageCapabilities.NanoBanana2, "512");
            var result = await Submit(f, requested.Model, requested.Resolution);
            Assert.Equal("512", requested.Resolution);
            Assert.Equal("0.5K", result.Execution.EffectiveRequest!.Resolution);
            Assert.Equal("0.5K", JsonNode.Parse(Assert.Single(f.FalHttp.Requests).Body!)!["resolution"]!.GetValue<string>());
        }
        [Theory]
        [InlineData(401, "{\"error\":{\"status\":\"UNAUTHENTICATED\"}}", true)]
        [InlineData(403, "{\"error\":{\"status\":\"PERMISSION_DENIED\"}}", false)]
        [InlineData(429, "{}", false)]
        [InlineData(500, "{\"error\":{\"status\":\"UNAUTHENTICATED\"}}", false)]
        public async Task OnlyDefinitiveCredentialFailureAdmitsFallback(int status, string body, bool fallback)
        {
            using var f = new ImageFallbackFixture();
            f.GoogleHttp.OnSendAsync = (_, _) => Task.FromResult(ImageFallbackFixture.Json(status, body));
            var result = await Submit(f, GeminiImageCapabilities.NanoBanana2);
            Assert.Single(f.GoogleHttp.Requests);
            Assert.Equal(fallback ? 1 : 0, f.FalHttp.Requests.Count);
            Assert.Equal(fallback, result.Execution.Routing?.Route != null);
        }
        [Theory]
        [InlineData(null, 200, ImageCredentialFailureKind.Missing)]
        [InlineData("key", 401, ImageCredentialFailureKind.Rejected)]
        [InlineData("key", 403, null)]
        public async Task DirectFalHasIndependentCredentialEvidence(string? key, int status, ImageCredentialFailureKind? kind)
        {
            using var f = new ImageFallbackFixture(falKey: key);
            f.FalHttp.OnSendAsync = (_, _) => Task.FromResult(ImageFallbackFixture.Json(status, "{}"));
            var result = await Submit(f, "fal-ai/nano-banana-2");
            Assert.Empty(f.GoogleHttp.Requests);
            Assert.NotNull(result.Execution.Routing);
            Assert.Null(result.Execution.Routing!.Route);
            Assert.Equal(kind, result.Execution.Routing.CredentialFailure?.Kind);
        }
        [Fact]
        public async Task RouteAndDispatchPreparationCanDenyAllFalHttp()
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            f.Registry.TryResolve(GeminiImageCapabilities.NanoBanana2, out var model);
            foreach (var routeDenied in new[] { true, false })
            {
                var context = new ImageExecutionContext();
                var error = new GenerationError(GenerationErrorCode.ExecutionFailed, "Persistence failed.", false);
                var result = await f.Executor.SubmitAsync(f.Request(model.ModelId), model, f.Media, context, CancellationToken.None,
                    (_, _) => Task.FromResult<GenerationError?>(routeDenied ? error : null),
                    (_, _) => Task.FromResult<GenerationError?>(error));
                Assert.IsType<FailedSubmitOutcome>(result.Outcome);
                Assert.False(context.Snapshot().Routing!.Route!.GenerationDispatchAttempted);
            }
            Assert.Empty(f.FalHttp.Requests);
        }
        [Fact]
        public async Task ReplacementGoogleKeyIsUsedOnNextRequest()
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            await Submit(f, GeminiImageCapabilities.NanoBanana2);
            f.GeminiKey = "replacement";
            var second = await Submit(f, GeminiImageCapabilities.NanoBanana2);
            Assert.Null(second.Execution.Routing);
            Assert.Equal("gemini", second.Execution.EffectiveModel!.ProviderName);
            Assert.Single(f.FalHttp.Requests);
        }
        [Fact]
        public async Task FalCompatibilityAndMissingKeyRetainSelectedTargetWithoutDispatch()
        {
            using var f = new ImageFallbackFixture(geminiKey: null, falKey: null);
            var missing = await Submit(f, GeminiImageCapabilities.NanoBanana2);
            Assert.Equal("fal", missing.Execution.EffectiveModel!.ProviderName);
            Assert.Equal(ImageCredentialFailureKind.Missing, missing.Execution.Routing!.CredentialFailure!.Kind);
            f.FalKey = "key";
            var incompatible = await Submit(f, GeminiImageCapabilities.NanoBananaPro, aspect: "8:1");
            Assert.Equal("aspect_ratio", Assert.IsType<FailedSubmitOutcome>(incompatible.Outcome).Error.Field);
            Assert.Null(incompatible.Execution.Routing!.CredentialFailure);
            Assert.Empty(f.FalHttp.Requests);
        }

        [Fact]
        public async Task MissingFalRegistrationRetainsClosedTargetReceipt()
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
            {
                new Rook.Services.Vision.Image.Gemini.GeminiImageProviderRegistration(
                    new Rook.Services.Vision.Image.Gemini.GeminiImageProvider(() => null))
            });
            registry.TryResolve(GeminiImageCapabilities.NanoBanana2, out var model);
            var result = await new ImageSubmissionExecutor(registry).SubmitAsync(f.Request(model.ModelId), model,
                f.Media, new ImageExecutionContext(), CancellationToken.None);
            Assert.Null(result.Execution.EffectiveModel);
            Assert.Equal("fal", result.Execution.Routing!.Route!.EffectiveProvider);
            Assert.False(result.Execution.Routing.Route.GenerationDispatchAttempted);
            Assert.Empty(f.FalHttp.Requests);
        }

        [Fact]
        public async Task SecretReadExceptionIsNeverMissingEvidence()
        {
            using var f = new ImageFallbackFixture();
            var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
            {
                new GeminiImageProviderRegistration(new GeminiImageProvider(() => throw new InvalidOperationException("private"))),
                new Rook.Services.Vision.Image.Fal.FalImageProviderRegistration(
                    new Rook.Services.Vision.Image.Fal.FalImageProvider(() => throw new InvalidOperationException("private")))
            });
            foreach (var id in new[] { GeminiImageCapabilities.NanoBanana2, "fal-ai/nano-banana-2" })
            {
                registry.TryResolve(id, out var model);
                var result = await new ImageSubmissionExecutor(registry).SubmitAsync(f.Request(id), model, f.Media,
                    new ImageExecutionContext(), CancellationToken.None);
                Assert.Null(result.Execution.Routing?.CredentialFailure);
                Assert.Null(result.Execution.Routing?.Route);
                Assert.DoesNotContain("private", Assert.IsType<FailedSubmitOutcome>(result.Outcome).Error.Message);
            }
        }

        [Fact]
        public async Task CancellationAfterRoutePreparationDoesNotSend()
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            using var cts = new CancellationTokenSource();
            f.Registry.TryResolve(GeminiImageCapabilities.NanoBanana2, out var model);
            var result = await f.Executor.SubmitAsync(f.Request(model.ModelId), model, f.Media,
                new ImageExecutionContext(), cts.Token, (_, _) =>
                { cts.Cancel(); return Task.FromResult<GenerationError?>(null); });
            Assert.Equal(GenerationErrorCode.Interrupted, Assert.IsType<FailedSubmitOutcome>(result.Outcome).Error.Code);
            Assert.False(result.Execution.Routing!.Route!.GenerationDispatchAttempted);
            Assert.Empty(f.FalHttp.Requests);
        }

        [Fact]
        public async Task FailureInsideSyncOutcomeCannotAdmitFallback()
        {
            using var f = new ImageFallbackFixture();
            f.GoogleHttp.OnSendAsync = (_, _) => Task.FromResult(ImageFallbackFixture.Json(200, "{}"));
            var result = await Submit(f, GeminiImageCapabilities.NanoBanana2);
            Assert.IsType<FailedResultOutcome>(Assert.IsType<SyncSubmitOutcome>(result.Outcome).Result);
            Assert.Empty(f.FalHttp.Requests);
        }
    }
}
