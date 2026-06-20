using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Reconstruction;
using Rook.Services.Reconstruction.Fal;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Reconstruction.Fal;

public sealed class FalReconstructionProviderTests
{
    private const string HunyuanModelId = "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d";

    [Fact]
    public async Task Submit_Queued_ReturnsHandleWithRequestIdAndUrls()
    {
        var transport = new FakeTransport();
        transport.Posts.Enqueue(Resp(200, @"{
            ""request_id"":""req-123"",
            ""status_url"":""https://queue.fal.run/status/req-123"",
            ""response_url"":""https://queue.fal.run/response/req-123"",
            ""cancel_url"":""https://queue.fal.run/cancel/req-123""}"));

        var outcome = await new FalReconstructionProvider(transport).SubmitAsync(
            new ReconstructionProviderSubmitRequest(
                HunyuanModelId,
                new Uri("https://rook.local/source.png"),
                JsonNode.Parse(@"{""enable_pbr"":true,""enable_geometry"":false}")!.AsObject()),
            CancellationToken.None);

        var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
        Assert.Equal("req-123", queued.Handle.ProviderJobId);
        Assert.Equal("https://queue.fal.run/status/req-123", queued.Handle.StatusUrl!.ToString());
        Assert.Equal("https://queue.fal.run/response/req-123", queued.Handle.ResponseUrl!.ToString());
        Assert.Equal("https://queue.fal.run/cancel/req-123", queued.Handle.CancelUrl!.ToString());
        Assert.Equal("PUT", queued.Handle.CancelHttpMethod);

        // input image url + boolean options forwarded verbatim in the submit payload
        Assert.Contains(@"""input_image_url"":""https://rook.local/source.png""", transport.LastPostBody);
        Assert.Contains(@"""enable_pbr"":true", transport.LastPostBody);
        Assert.Contains(@"""enable_geometry"":false", transport.LastPostBody);
    }

    [Fact]
    public async Task Submit_401_ReturnsFailedSubmitTyped()
    {
        var transport = new FakeTransport();
        transport.Posts.Enqueue(Resp(401, @"{""detail"":""bad key""}"));

        var outcome = await new FalReconstructionProvider(transport).SubmitAsync(
            new ReconstructionProviderSubmitRequest(HunyuanModelId, new Uri("https://rook.local/s.png"), new JsonObject()),
            CancellationToken.None);

        var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
        Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
    }

    [Fact]
    public async Task Submit_MissingRequestId_ReturnsFailedSubmit_NotThrow()
    {
        var transport = new FakeTransport();
        transport.Posts.Enqueue(Resp(200, @"{""status_url"":""https://queue.fal.run/s""}"));

        var outcome = await new FalReconstructionProvider(transport).SubmitAsync(
            new ReconstructionProviderSubmitRequest(HunyuanModelId, new Uri("https://rook.local/s.png"), new JsonObject()),
            CancellationToken.None);

        Assert.IsType<FailedSubmitOutcome>(outcome);
    }

    [Fact]
    public async Task Status_InProgress_MapsToInFlight()
    {
        var transport = new FakeTransport();
        transport.Gets.Enqueue(Resp(200, @"{""status"":""IN_PROGRESS"",""request_id"":""req-123""}"));

        var outcome = await new FalReconstructionProvider(transport).GetStatusAsync(
            new ProviderJobHandle("req-123", statusUrl: new Uri("https://queue.fal.run/status/req-123")),
            CancellationToken.None);

        Assert.IsType<InFlightStatusOutcome>(outcome);
        Assert.Equal("https://queue.fal.run/status/req-123", transport.LastGetUrl!.ToString());
    }

    [Fact]
    public async Task Status_Completed_MapsToProviderComplete()
    {
        var transport = new FakeTransport();
        transport.Gets.Enqueue(Resp(200, @"{""status"":""COMPLETED"",""request_id"":""req-123""}"));

        var outcome = await new FalReconstructionProvider(transport).GetStatusAsync(
            new ProviderJobHandle("req-123", statusUrl: new Uri("https://queue.fal.run/status/req-123")),
            CancellationToken.None);

        Assert.IsType<ProviderCompleteStatusOutcome>(outcome);
    }

    [Fact]
    public async Task Status_429NeedsRetry_ReturnsFailedRetryableQuota()
    {
        var transport = new FakeTransport();
        transport.Gets.Enqueue(new FalHttpResponse(
            429,
            "{}",
            new Dictionary<string, IReadOnlyList<string>> { ["x-fal-needs-retry"] = new[] { "true" } }));

        var outcome = await new FalReconstructionProvider(transport).GetStatusAsync(
            new ProviderJobHandle("req-123", statusUrl: new Uri("https://queue.fal.run/status/req-123")),
            CancellationToken.None);

        var failed = Assert.IsType<FailedStatusOutcome>(outcome);
        Assert.Equal(GenerationErrorCode.QuotaExceeded, failed.Error.Code);
        Assert.True(failed.Error.Retryable);
    }

    [Fact]
    public async Task Status_NoStatusUrl_ReturnsFailed()
    {
        var outcome = await new FalReconstructionProvider(new FakeTransport()).GetStatusAsync(
            new ProviderJobHandle("req-123"),
            CancellationToken.None);

        Assert.IsType<FailedStatusOutcome>(outcome);
    }

    [Fact]
    public async Task Fetch_HunyuanModelUrlsBucket_MapsRolesAndExtensions()
    {
        var artifacts = await FetchArtifacts(@"{
            ""model_urls"":{
                ""glb"":{""url"":""https://example.test/model.glb""},
                ""obj"":{""url"":""https://example.test/model.obj""},
                ""mtl"":{""url"":""https://example.test/material.mtl""}
            },
            ""texture"":{""url"":""https://example.test/texture.png""},
            ""thumbnail"":{""url"":""https://example.test/thumb.png""}}");

        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.ModelGlb);
        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.ModelObj);
        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.MaterialMtl);
        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.Texture);
        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.Thumbnail);
        Assert.Equal("glb", Extension(artifacts, ReconstructionFileRoles.ModelGlb));
    }

    [Fact]
    public async Task Fetch_RootModelGlbPointingToObj_NormalizesToObjRole()
    {
        var artifacts = await FetchArtifacts(@"{
            ""model_glb"":{""url"":""https://example.test/hunyuan.obj""},
            ""model_urls"":{""mtl"":{""url"":""https://example.test/hunyuan.mtl""}},
            ""texture"":{""url"":""https://example.test/texture.png""}}");

        Assert.DoesNotContain(artifacts, a => a.Role == ReconstructionFileRoles.ModelGlb);
        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.ModelObj);
        Assert.Equal("obj", Extension(artifacts, ReconstructionFileRoles.ModelObj));
        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.MaterialMtl);
    }

    [Fact]
    public async Task Fetch_ProviderFileNameAndContentType_NormalizesRoleAndExtension()
    {
        var artifacts = await FetchArtifacts(@"{
            ""model_glb"":{
                ""url"":""https://cdn.example.test/download?id=asset"",
                ""file_name"":""hunyuan-output.obj"",
                ""content_type"":""model/obj""}}");

        Assert.DoesNotContain(artifacts, a => a.Role == ReconstructionFileRoles.ModelGlb);
        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.ModelObj);
        Assert.Equal("obj", Extension(artifacts, ReconstructionFileRoles.ModelObj));
    }

    [Fact]
    public async Task Fetch_MeshyTextureMaps_PreserveSubroles()
    {
        var artifacts = await FetchArtifacts(@"{
            ""model_glb"":{""url"":""https://example.test/meshy.glb""},
            ""texture_urls"":{
                ""base_color"":{""url"":""https://example.test/base_color.png""},
                ""normal"":{""url"":""https://example.test/normal.png""},
                ""roughness"":{""url"":""https://example.test/roughness.png""}}}");

        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.ModelGlb);
        Assert.Contains(artifacts, a => a.Role == "texture_base_color");
        Assert.Contains(artifacts, a => a.Role == "texture_normal");
        Assert.Contains(artifacts, a => a.Role == "texture_roughness");
    }

    [Fact]
    public async Task Fetch_422_ReturnsFailedResult()
    {
        var transport = new FakeTransport();
        transport.Gets.Enqueue(Resp(422, @"{""detail"":""bad""}"));

        var outcome = await new FalReconstructionProvider(transport).FetchResultAsync(
            new ProviderJobHandle("req-123", responseUrl: new Uri("https://queue.fal.run/response/req-123")),
            CancellationToken.None);

        Assert.IsType<FailedResultOutcome>(outcome);
    }

    [Fact]
    public async Task Fetch_NoRecognizableAssets_ReturnsFailedResult()
    {
        var transport = new FakeTransport();
        transport.Gets.Enqueue(Resp(200, @"{""unrelated"":true}"));

        var outcome = await new FalReconstructionProvider(transport).FetchResultAsync(
            new ProviderJobHandle("req-123", responseUrl: new Uri("https://queue.fal.run/response/req-123")),
            CancellationToken.None);

        Assert.IsType<FailedResultOutcome>(outcome);
    }

    [Fact]
    public async Task Cancel_Success_ReturnsCanceled()
    {
        var transport = new FakeTransport();
        transport.Sends.Enqueue(Resp(200, "{}"));

        var outcome = await new FalReconstructionProvider(transport).CancelAsync(
            new ProviderJobHandle("req-123", cancelUrl: new Uri("https://queue.fal.run/cancel/req-123"), cancelHttpMethod: "PUT"),
            CancellationToken.None);

        Assert.IsType<CanceledOutcome>(outcome);
    }

    [Fact]
    public async Task Cancel_NoCancelUrl_ReturnsAlreadyTerminal()
    {
        var outcome = await new FalReconstructionProvider(new FakeTransport()).CancelAsync(
            new ProviderJobHandle("req-123"),
            CancellationToken.None);

        Assert.IsType<AlreadyTerminalOutcome>(outcome);
    }

    private static async Task<IReadOnlyList<ResultArtifact>> FetchArtifacts(string resultJson)
    {
        var transport = new FakeTransport();
        transport.Gets.Enqueue(Resp(200, resultJson));
        var outcome = await new FalReconstructionProvider(transport).FetchResultAsync(
            new ProviderJobHandle("req-123", responseUrl: new Uri("https://queue.fal.run/response/req-123")),
            CancellationToken.None);
        return Assert.IsType<SuccessResultOutcome>(outcome).Envelope.Artifacts;
    }

    private static string? Extension(IReadOnlyList<ResultArtifact> artifacts, string role)
    {
        var artifact = artifacts.Single(a => a.Role == role);
        return artifact.ProviderMetadata.TryGetValue("file_extension", out var ext)
            && ext is JsonValue value
            && value.TryGetValue<string>(out var text)
                ? text
                : null;
    }

    private static FalHttpResponse Resp(int statusCode, string body)
        => new(statusCode, body, new Dictionary<string, IReadOnlyList<string>>());

    private sealed class FakeTransport : IFalTransport
    {
        public Queue<FalHttpResponse> Posts { get; } = new();
        public Queue<FalHttpResponse> Gets { get; } = new();
        public Queue<FalHttpResponse> Sends { get; } = new();
        public string? LastPostBody { get; private set; }
        public Uri? LastGetUrl { get; private set; }

        public Task<FalHttpResponse> PostJsonAsync(Uri url, string bodyJson, CancellationToken ct)
        {
            LastPostBody = bodyJson;
            return Task.FromResult(Posts.Dequeue());
        }

        public Task<FalHttpResponse> GetAsync(Uri url, CancellationToken ct)
        {
            LastGetUrl = url;
            return Task.FromResult(Gets.Dequeue());
        }

        public Task<FalHttpResponse> SendAsync(HttpMethod method, Uri url, string? bodyJson, CancellationToken ct)
            => Task.FromResult(Sends.Dequeue());
    }
}
