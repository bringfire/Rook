using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Vision;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision
{
    public sealed class PromptEnhancementFallbackTests
    {
        private const string Prompt = "A timber pavilion with amber light";
        private const string Output = "{\"subject\":\"A timber pavilion with amber light\",\"camera_constraint\":\"Change the viewpoint\",\"style\":{\"primary\":\"photorealistic\"}}";
        private static string GoogleOutput => JsonSerializer.Serialize(new
        {
            candidates = new[] { new { content = new { parts = new[] { new { text = Output } } }, finishReason = "STOP" } }
        });
        private static string FalOutput => JsonSerializer.Serialize(new { output = Output, partial = false });
        private static string Rejection = "{\"error\":{\"status\":\"UNAUTHENTICATED\"}}";
        private static string InvalidKey = "{\"error\":{\"details\":[{\"@type\":\"type.googleapis.com/google.rpc.ErrorInfo\",\"domain\":\"googleapis.com\",\"reason\":\"API_KEY_INVALID\"}]}}";

        [Theory]
        [InlineData(null)]
        [InlineData(" ")]
        public async Task MissingGoogleKey_usesConfiguredFalAndPublishesActualAttribution(string? googleKey)
        {
            using var f = new Fixture(googleKey);
            var response = await f.Run();
            Assert.True(response.Success, response.Data?.ToString());
            var artifact = JsonNode.Parse(JsonSerializer.Serialize(response.Data))!;
            var meta = artifact["metadata"]!;
            Assert.Equal("fal", meta["provider"]!.GetValue<string>());
            Assert.Equal("google/gemini-2.5-flash", meta["model"]!.GetValue<string>());
            Assert.True(meta["fallback_used"]!.GetValue<bool>());
            Assert.Equal("gemini_key_missing", meta["fallback_reason"]!.GetValue<string>());
            Assert.Equal(Prompt, meta["original_prompt"]!.GetValue<string>());
            Assert.Single(f.Http.Requests);
            var sent = f.Http.Requests[0];
            Assert.Equal("https://fal.run/openrouter/router", sent.Url);
            Assert.Equal("Key fake-fal", sent.Authorization);
            Assert.Null(sent.GoogleHeader);
            Assert.DoesNotContain("fake-fal", sent.Body);
            var payload = JsonNode.Parse(sent.Body)!;
            Assert.Equal("google/gemini-2.5-flash", payload["model"]!.GetValue<string>());
            Assert.Contains("Context: architecture", payload["prompt"]!.GetValue<string>());
            Assert.Contains(Prompt, payload["prompt"]!.GetValue<string>());
            Assert.Contains("PRESERVE everything", payload["system_prompt"]!.GetValue<string>());
            Assert.False(payload["enable_web_search"]!.GetValue<bool>());
            AssertCamera(meta["enhanced_prompt"]!.GetValue<string>());
            Assert.Single(Directory.GetFiles(f.Root, "manifest.json", SearchOption.AllDirectories));
        }

        [Fact]
        public async Task ConfiguredGoogle_successKeepsPrimaryAndSharesPromptInstructionsWithFal()
        {
            using var primary = new Fixture("fake-google");
            var response = await primary.Run();
            Assert.True(response.Success, response.Data?.ToString());
            var meta = JsonNode.Parse(JsonSerializer.Serialize(response.Data))!["metadata"]!;
            Assert.Equal("gemini", meta["provider"]!.GetValue<string>());
            Assert.Equal("gemini-2.5-flash", meta["model"]!.GetValue<string>());
            Assert.False(meta["fallback_used"]!.GetValue<bool>());
            AssertCamera(meta["enhanced_prompt"]!.GetValue<string>());
            var sent = Assert.Single(primary.Http.Requests);
            Assert.Equal("fake-google", sent.GoogleHeader);
            Assert.Null(sent.Authorization);
            Assert.DoesNotContain("fake-google", sent.Url + sent.Body);
            using var fallback = new Fixture(null);
            Assert.True((await fallback.Run()).Success);
            var g = JsonNode.Parse(sent.Body)!;
            var fal = JsonNode.Parse(fallback.Http.Requests[0].Body)!;
            Assert.Equal(g["systemInstruction"]!["parts"]![0]!["text"]!.GetValue<string>(), fal["system_prompt"]!.GetValue<string>());
            Assert.Equal(g["contents"]![0]!["parts"]![0]!["text"]!.GetValue<string>(), fal["prompt"]!.GetValue<string>());
        }

        [Theory]
        [InlineData(401, true)]
        [InlineData(400, true)]
        [InlineData(403, true)]
        [InlineData(429, false)]
        [InlineData(500, false)]
        public async Task ClosedCredentialEvidence_onlyFallsBackOnDefinitiveRejection(int status, bool expectedFallback)
        {
            using var f = new Fixture("fake-google");
            f.Http.Google = (status, status == 401 ? Rejection : InvalidKey);
            var response = await f.Run();
            Assert.Equal(expectedFallback, response.Success);
            Assert.Equal(expectedFallback ? 2 : 1, f.Http.Requests.Count);
            if (expectedFallback)
                Assert.Equal("gemini_key_rejected", JsonNode.Parse(JsonSerializer.Serialize(response.Data))!["metadata"]!["fallback_reason"]!.GetValue<string>());
        }

        [Theory]
        [InlineData(401, "{\"error\":{\"message\":\"Invalid key fake-google\"}}")]
        [InlineData(403, "{\"error\":{\"status\":\"PERMISSION_DENIED\",\"message\":\"fake-google\"}}")]
        [InlineData(400, "{\"error\":{\"details\":[{\"reason\":\"API_KEY_INVALID\"}]}}")]
        [InlineData(403, "{\"error\":{\"details\":[{\"@type\":\"type.googleapis.com/google.rpc.ErrorInfo\",\"domain\":\"other\",\"reason\":\"API_KEY_INVALID\"}]}}")]
        [InlineData(403, "{\"error\":{\"details\":[{\"@type\":\"type.googleapis.com/google.rpc.ErrorInfo\",\"domain\":\"googleapis.com\",\"reason\":\"API_KEY_INVALID\",\"metadata\":{\"service\":\"other\"}}]}}")]
        [InlineData(401, "not JSON fake-google")]
        public async Task AmbiguousGoogleFailure_neverSendsToFalOrLeaksBody(int status, string body)
        {
            using var f = new Fixture("fake-google");
            f.Http.Google = (status, body);
            var response = await f.Run();
            Assert.False(response.Success);
            Assert.Single(f.Http.Requests);
            Assert.DoesNotContain("fake-google", JsonSerializer.Serialize(response));
            Assert.Empty(Directory.GetFiles(f.Root, "*.json", SearchOption.AllDirectories));
        }

        [Theory]
        [InlineData(401, "fake-fal")]
        [InlineData(403, "fake-fal")]
        [InlineData(500, "fake-fal")]
        [InlineData(200, "{\"output\":\"{\\\"subject\\\":\\\"test\\\"}\",\"partial\":true}")]
        [InlineData(200, "{\"output\":\"{\\\"subject\\\":\\\"test\\\"}\",\"error\":\"fake-fal\"}")]
        [InlineData(200, "{\"output\":\"\"}")]
        [InlineData(200, "{\"output\":\"not JSON\"}")]
        [InlineData(200, "{\"output\":\"[]\"}")]
        [InlineData(200, "{\"output\":\"{}\"}")]
        [InlineData(200, "{\"output\":\"null\"}")]
        [InlineData(200, "{\"output\":\"[{\\\"subject\\\":\\\"test\\\"}\"}")]
        [InlineData(200, "{\"output\":\"[{\\\"subject\\\":\\\"test\\\"}]\"}")]
        [InlineData(200, "{\"output\":\"Extra explanation {\\\"subject\\\":\\\"test\\\"}\"}")]
        [InlineData(200, "{\"output\":\"```json\\n{\\\"subject\\\":\\\"test\\\"}\"}")]
        public async Task FalFailure_isSafeAndPublishesNothing(int status, string body)
        {
            using var f = new Fixture(null);
            f.Http.Fal = (status, body);
            var response = await f.Run();
            Assert.False(response.Success);
            Assert.Single(f.Http.Requests);
            Assert.DoesNotContain("fake-fal", JsonSerializer.Serialize(response));
            Assert.Empty(Directory.GetFiles(f.Root, "*.json", SearchOption.AllDirectories));
        }

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task OneDeadlineBoundsBothAttempts_evenWhenTransportIgnoresCancellation(bool callerCancellation)
        {
            using var deadline = new CancellationTokenSource();
            using var caller = new CancellationTokenSource();
            using var f = new Fixture("fake-google", deadline);
            f.Http.Google = (401, Rejection);
            var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            f.Http.HoldFal = async () => { entered.TrySetResult(true); await release.Task; };
            var work = f.Run(caller.Token);
            try
            {
                Assert.Same(entered.Task, await Task.WhenAny(entered.Task, Task.Delay(5000)));
                Assert.Equal(1, f.DeadlineCreations);
                (callerCancellation ? caller : deadline).Cancel();
                Assert.Same(work, await Task.WhenAny(work, Task.Delay(5000)));
                var response = await work;
                Assert.False(response.Success);
                Assert.Contains(callerCancellation ? "cancelled" : "timed out", response.Data!.ToString());
                Assert.Equal(2, f.Http.Requests.Count);
                Assert.Empty(Directory.GetFiles(f.Root, "*.json", SearchOption.AllDirectories));
            }
            finally { release.TrySetResult(true); }
        }

        [Fact]
        public async Task CancellationBeforeDispatch_sendsNothing()
        {
            using var f = new Fixture(null);
            using var caller = new CancellationTokenSource(); caller.Cancel();
            var response = await f.Run(caller.Token);
            Assert.False(response.Success);
            Assert.Empty(f.Http.Requests);
        }

        [Fact]
        public async Task CredentialProbe_neverFallsBackToFal()
        {
            using var f = new Fixture("fake-google");
            f.Http.Google = (401, Rejection);
            var response = await f.Enhancer.EnhancePromptAsync("fake-google", "ping");
            Assert.False(response.Success);
            Assert.Equal("gemini", response.Provider);
            Assert.False(response.FallbackUsed);
            Assert.Single(f.Http.Requests);
        }

        [Fact]
        public async Task UnreadableUnusedFalCredential_doesNotBlockConfiguredGoogle()
        {
            using var f = new Fixture("fake-google", throwFalRead: true);
            var response = await f.Run();
            Assert.True(response.Success, response.Data?.ToString());
            Assert.Single(f.Http.Requests);
        }

        [Fact]
        public async Task RejectedGoogle_withoutFalKey_explainsFallbackConfiguration()
        {
            using var f = new Fixture("fake-google", falKey: null);
            f.Http.Google = (401, Rejection);
            var response = await f.Run();
            Assert.False(response.Success);
            Assert.Contains("Configure a fal.ai API key", response.Data!.ToString());
            Assert.Single(f.Http.Requests);
        }

        [Theory]
        [InlineData("MAX_TOKENS")]
        [InlineData("SAFETY")]
        public async Task IncompleteGoogleResponse_preservesOriginalWithoutTryingFal(string finishReason)
        {
            using var f = new Fixture("fake-google");
            f.Http.Google = (200, GoogleOutput.Replace("STOP", finishReason));
            var response = await f.Enhancer.EnhanceWithFallbackAsync("fake-google", "fake-fal", Prompt);
            Assert.False(response.Success);
            Assert.Equal(Prompt, response.OriginalPrompt);
            Assert.Null(response.EnhancedPrompt);
            Assert.Single(f.Http.Requests);
        }

        [Theory]
        [InlineData(null)]
        [InlineData("null")]
        [InlineData("123")]
        [InlineData("{}")]
        [InlineData("\"\"")]
        public async Task GoogleWithoutCompletionEvidence_isNotPublishedOrRerouted(string? finishReasonJson)
        {
            using var f = new Fixture("fake-google");
            var body = JsonNode.Parse(GoogleOutput)!;
            var candidate = (JsonObject)body["candidates"]![0]!;
            candidate.Remove("finishReason");
            if (finishReasonJson != null) candidate["finishReason"] = JsonNode.Parse(finishReasonJson);
            f.Http.Google = (200, body.ToJsonString());
            var response = await f.Run();
            Assert.False(response.Success);
            Assert.Single(f.Http.Requests);
            Assert.Empty(Directory.GetFiles(f.Root, "*.json", SearchOption.AllDirectories));
        }

        [Theory]
        [InlineData("```json\n", "\n```")]
        [InlineData("```\n", "\n```")]
        [InlineData("", "")]
        public async Task CompleteJsonOutput_acceptsWhitespaceAndCompleteEnclosingFences(string prefix, string suffix)
        {
            using var f = new Fixture(null);
            f.Http.Fal = (200, JsonSerializer.Serialize(new { output = "  " + prefix + Output + suffix + "  " }));
            var response = await f.Run();
            Assert.True(response.Success, response.Data?.ToString());
        }

        [Fact]
        public async Task DeadlineWhileGoogleIsPending_blocksFallbackAndKeepsFirstStopReason()
        {
            using var deadline = new CancellationTokenSource();
            using var caller = new CancellationTokenSource();
            using var f = new Fixture("fake-google", deadline);
            f.Http.Google = (401, Rejection);
            var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            f.Http.HoldGoogle = async () => { entered.TrySetResult(true); await release.Task; };
            var work = f.Run(caller.Token);
            try
            {
                Assert.Same(entered.Task, await Task.WhenAny(entered.Task, Task.Delay(5000)));
                deadline.Cancel(); caller.Cancel();
                Assert.Same(work, await Task.WhenAny(work, Task.Delay(5000)));
                var response = await work;
                Assert.False(response.Success);
                Assert.Contains("timed out", response.Data!.ToString());
                Assert.Single(f.Http.Requests);
                Assert.Equal(1, f.DeadlineCreations);
                Assert.Empty(Directory.GetFiles(f.Root, "*.json", SearchOption.AllDirectories));
            }
            finally { release.TrySetResult(true); }
        }

        private static void AssertCamera(string output)
        {
            var camera = JsonNode.Parse(output)!["camera_constraint"]!.GetValue<string>();
            Assert.Contains("EXACT camera angle", camera);
            Assert.Contains("Do NOT change the viewpoint", camera);
        }

        private sealed record Request(string Url, string Body, string? Authorization, string? GoogleHeader);
        private sealed class Transport : HttpMessageHandler
        {
            public readonly List<Request> Requests = new();
            public (int, string) Google = (200, GoogleOutput), Fal = (200, FalOutput);
            public Func<Task>? HoldFal, HoldGoogle;
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
            {
                Requests.Add(new(request.RequestUri!.AbsoluteUri, await request.Content!.ReadAsStringAsync(),
                    request.Headers.Authorization?.ToString(), request.Headers.TryGetValues("x-goog-api-key", out var values) ? values.Single() : null));
                var fal = request.RequestUri.Host == "fal.run";
                if (fal && HoldFal != null) await HoldFal();
                if (!fal && HoldGoogle != null) await HoldGoogle();
                var response = fal ? Fal : Google;
                return new HttpResponseMessage((HttpStatusCode)response.Item1) { Content = new StringContent(response.Item2, Encoding.UTF8, "application/json") };
            }
        }
        private sealed class Fixture : IDisposable
        {
            public readonly string Root = Path.Combine(Path.GetTempPath(), "rook-prompt-" + Guid.NewGuid().ToString("N"));
            public readonly Transport Http = new();
            public int DeadlineCreations;
            public readonly PromptEnhancer Enhancer;
            private readonly HttpClient _client;
            private readonly VisionHandler _handler;
            public Fixture(string? google, CancellationTokenSource? deadline = null, string? falKey = "fake-fal", bool throwFalRead = false)
            {
                Directory.CreateDirectory(Root);
                _client = new HttpClient(Http) { Timeout = Timeout.InfiniteTimeSpan };
                Enhancer = new PromptEnhancer(_client, timeout =>
                {
                    Assert.Equal(TimeSpan.FromSeconds(30), timeout);
                    DeadlineCreations++;
                    return deadline ?? new CancellationTokenSource(timeout);
                });
                _handler = new VisionHandler(new ArtifactStore(Root), new Secrets(google, falKey, throwFalRead), Enhancer, new ViewportHandler());
            }
            public Task<Rook.ApiResponse> Run(CancellationToken ct = default) => _handler.EnhancePromptAsync(
                JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(JsonSerializer.Serialize(new { prompt = Prompt, context = "architecture" }))!, ct);
            public void Dispose() { _client.Dispose(); if (Directory.Exists(Root)) Directory.Delete(Root, true); }
        }
        private sealed class Secrets : IGenerationSecretStore
        {
            private readonly string? _google;
            private readonly string? _fal;
            private readonly bool _throwFalRead;
            public Secrets(string? google, string? fal, bool throwFalRead) { _google = google; _fal = fal; _throwFalRead = throwFalRead; }
            public string? GetSecret(string key)
            {
                if (key == GenerationSecretKeys.FalApiKey && _throwFalRead) throw new InvalidOperationException("Unreadable fake-fal");
                return key == GenerationSecretKeys.GeminiApiKey ? _google : key == GenerationSecretKeys.FalApiKey ? _fal : null;
            }
            public bool HasSecret(string key) => !string.IsNullOrWhiteSpace(GetSecret(key));
            public string? GetPreview(string key) => null;
            public void SetSecret(string key, string value) => throw new NotSupportedException();
            public void RemoveSecret(string key) => throw new NotSupportedException();
        }
    }
}
