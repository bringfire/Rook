using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Gemini;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public class GeminiImageProviderTests
    {
        [Fact]
        public async Task SubmitAsync_success_returns_sync_inline_artifact_and_metadata()
        {
            string? capturedBody = null;
            var (provider, _) = MakeProvider(req =>
            {
                capturedBody = req.Content?.ReadAsStringAsync().GetAwaiter().GetResult();
                return JsonResponse(HttpStatusCode.OK, """
                    {
                      "candidates": [
                        {
                          "finishReason": "STOP",
                          "content": {
                            "parts": [
                              {
                                "inlineData": {
                                  "mimeType": "image/png",
                                  "data": "AQIDBA=="
                                },
                                "thoughtSignature": "sig-123"
                              }
                            ]
                          }
                        }
                      ],
                      "modelVersion": "gemini-3.1-flash-image",
                      "responseId": "resp-123",
                      "usageMetadata": {
                        "promptTokenCount": 12,
                        "candidatesTokenCount": 1290
                      }
                    }
                    """);
            });

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedInputImage(),
                CancellationToken.None);

            var sync = Assert.IsType<SyncSubmitOutcome>(outcome);
            var success = Assert.IsType<SuccessResultOutcome>(sync.Result);
            var artifact = Assert.Single(success.Envelope.Artifacts);
            Assert.Equal(ImageMediaRoles.Image, artifact.Role);
            Assert.Equal("image/png", artifact.DeclaredMimeType);
            var body = Assert.IsType<InlineArtifactBody>(artifact.Body);
            Assert.Equal(new byte[] { 1, 2, 3, 4 }, body.Bytes);
            Assert.Equal("STOP", artifact.ProviderMetadata["finishReason"]!.GetValue<string>());
            Assert.Equal("sig-123", artifact.ProviderMetadata["thoughtSignature"]!.GetValue<string>());
            Assert.Equal("resp-123", success.Envelope.EnvelopeMetadata["responseId"]!.GetValue<string>());
            Assert.True(success.Envelope.EnvelopeMetadata.ContainsKey("usageMetadata"));
            Assert.NotNull(capturedBody);
            Assert.Contains("\"responseModalities\":[\"IMAGE\"]", capturedBody);
            Assert.Contains("\"imageSize\":\"1K\"", capturedBody);
            Assert.Contains("\"aspectRatio\":\"16:9\"", capturedBody);
        }

        [Fact]
        public async Task SubmitAsync_auto_aspect_omits_aspect_ratio_from_image_config()
        {
            string? capturedBody = null;
            var (provider, _) = MakeProvider(req =>
            {
                capturedBody = req.Content?.ReadAsStringAsync().GetAwaiter().GetResult();
                return JsonResponse(HttpStatusCode.OK, """
                    {
                      "candidates": [
                        {
                          "content": {
                            "parts": [
                              {
                                "inlineData": {
                                  "mimeType": "image/png",
                                  "data": "AQIDBA=="
                                }
                              }
                            ]
                          }
                        }
                      ]
                    }
                    """);
            });

            await provider.SubmitAsync(
                Request().With(aspectRatio: ""),
                ResolvedInputImage(),
                CancellationToken.None);

            Assert.NotNull(capturedBody);
            Assert.Contains("\"imageSize\":\"1K\"", capturedBody);
            Assert.DoesNotContain("aspectRatio", capturedBody);
        }

        [Fact]
        public async Task SubmitAsync_missing_api_key_returns_typed_dependency_error_without_network()
        {
            var (provider, handler) = MakeProvider(
                _ => JsonResponse(HttpStatusCode.OK, "{}"),
                apiKey: null);

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedInputImage(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.Contains("Gemini API key is not configured", failed.Error.Message);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_foreign_options_returns_typed_invalid_request()
        {
            var (provider, handler) = MakeProvider(
                _ => JsonResponse(HttpStatusCode.OK, "{}"));
            var request = Request().With(options: new ForeignImageOptions());

            var outcome = await provider.SubmitAsync(
                request,
                ResolvedInputImage(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("options", failed.Error.Field);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_provider_400_preserves_provider_error_detail()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.BadRequest, """
                    {
                      "error": {
                        "code": 400,
                        "status": "INVALID_ARGUMENT",
                        "message": "Bad image request"
                      }
                    }
                    """));

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedInputImage(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("INVALID_ARGUMENT", failed.Error.ProviderErrorCode);
            Assert.Contains("Bad image request", failed.Error.Message);
            Assert.NotNull(failed.Error.ProviderDetail);
            Assert.True(failed.Error.ProviderDetail!.ContainsKey("error"));
        }

        [Theory]
        [InlineData("[]")]
        [InlineData("\"bad\"")]
        public async Task SubmitAsync_provider_error_non_object_json_returns_typed_submit_failure(
            string responseJson)
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.BadRequest, responseJson));

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedInputImage(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Contains("API Error", failed.Error.Message);
            Assert.NotNull(failed.Error.ProviderDetail);
            Assert.True(failed.Error.ProviderDetail!.ContainsKey("error"));
        }

        [Fact]
        public async Task SubmitAsync_2xx_numeric_inline_data_returns_typed_result_failure()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, """
                    {
                      "candidates": [
                        {
                          "content": {
                            "parts": [
                              {
                                "inlineData": {
                                  "mimeType": "image/png",
                                  "data": 42
                                }
                              }
                            ]
                          }
                        }
                      ]
                    }
                    """));

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedInputImage(),
                CancellationToken.None);

            var sync = Assert.IsType<SyncSubmitOutcome>(outcome);
            var failed = Assert.IsType<FailedResultOutcome>(sync.Result);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.Contains("inlineData.data", failed.Error.Message);
        }

        [Fact]
        public async Task SubmitAsync_2xx_nested_malformed_json_returns_typed_result_failure()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, """
                    {
                      "candidates": [
                        {
                          "content": 42
                        }
                      ]
                    }
                    """));

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedInputImage(),
                CancellationToken.None);

            var sync = Assert.IsType<SyncSubmitOutcome>(outcome);
            var failed = Assert.IsType<FailedResultOutcome>(sync.Result);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.Contains("content", failed.Error.Message);
        }

        [Fact]
        public async Task SubmitAsync_2xx_invalid_base64_returns_sync_result_failure_not_submit_failure()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, """
                    {
                      "candidates": [
                        {
                          "content": {
                            "parts": [
                              {
                                "inlineData": {
                                  "mimeType": "image/png",
                                  "data": "not-base64"
                                }
                              }
                            ]
                          }
                        }
                      ]
                    }
                    """));

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedInputImage(),
                CancellationToken.None);

            var sync = Assert.IsType<SyncSubmitOutcome>(outcome);
            var failed = Assert.IsType<FailedResultOutcome>(sync.Result);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.Contains("base64", failed.Error.Message);
        }

        [Fact]
        public async Task SubmitAsync_2xx_without_image_returns_sync_result_failure_not_submit_failure()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, """
                    {
                      "candidates": [
                        {
                          "content": {
                            "parts": [
                              { "text": "no image" }
                            ]
                          }
                        }
                      ]
                    }
                    """));

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedInputImage(),
                CancellationToken.None);

            var sync = Assert.IsType<SyncSubmitOutcome>(outcome);
            var failed = Assert.IsType<FailedResultOutcome>(sync.Result);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.Contains("No image", failed.Error.Message);
        }

        [Theory]
        [InlineData("[]")]
        [InlineData("42")]
        [InlineData("\"ok\"")]
        public async Task SubmitAsync_2xx_non_object_json_returns_typed_result_failure(
            string responseJson)
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, responseJson));

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedInputImage(),
                CancellationToken.None);

            var sync = Assert.IsType<SyncSubmitOutcome>(outcome);
            var failed = Assert.IsType<FailedResultOutcome>(sync.Result);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.Contains("root", failed.Error.Message);
        }

        private static ImageGenerationRequest Request() =>
            new(
                Model: GeminiImageCapabilities.NanoBanana2,
                Prompt: "make this architectural rendering warmer",
                Resolution: "1K",
                AspectRatio: "16:9",
                NumberOfImages: 1,
                ReferenceImages: new[] { MediaRef.ForPath("C:/tmp/reference.png", ImageMediaRoles.ReferenceImage) },
                Options: new GeminiImageOptions());

        private static IReadOnlyDictionary<MediaRef, ResolvedMedia> ResolvedInputImage()
        {
            var input = MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage);
            var reference = MediaRef.ForPath("C:/tmp/reference.png", ImageMediaRoles.ReferenceImage);
            return new Dictionary<MediaRef, ResolvedMedia>
            {
                [input] = new ResolvedMedia(new byte[] { 9, 8, 7 }, "image/png"),
                [reference] = new ResolvedMedia(new byte[] { 6, 5, 4 }, "image/png"),
            };
        }

        private static (GeminiImageProvider provider, TestHttpMessageHandler handler) MakeProvider(
            System.Func<HttpRequestMessage, HttpResponseMessage> onSend,
            string? apiKey = "test-key")
        {
            var handler = new TestHttpMessageHandler { OnSend = onSend };
            var http = new HttpClient(handler);
            return (new GeminiImageProvider(() => apiKey, http), handler);
        }

        private static HttpResponseMessage JsonResponse(HttpStatusCode status, string json) =>
            new(status) { Content = new StringContent(json, Encoding.UTF8, "application/json") };

        private sealed class ForeignImageOptions : ProviderOptions
        {
        }
    }
}
