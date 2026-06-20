using System;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Reconstruction.Fal;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Reconstruction.Fal;

public sealed class FalReconstructionProviderTests
{
    [Fact]
    public async Task Submit_HunyuanRapid_UsesImageUrlAndBooleanOptions()
    {
        var client = new RecordingFalQueueClient();
        var provider = new FalReconstructionProvider(client);

        var result = await provider.SubmitAsync(new ReconstructionProviderSubmitRequest(
            ModelId: "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
            InputImageUrl: new Uri("https://rook.local/source.png"),
            Options: JsonNode.Parse(@"{""enable_pbr"":true,""enable_geometry"":false}")!.AsObject()),
            CancellationToken.None);

        Assert.Equal("fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d", client.LastModelId);
        Assert.Equal(
            "https://rook.local/source.png",
            client.LastPayload!["input_image_url"]!.GetValue<string>());
        Assert.True(client.LastPayload["enable_pbr"]!.GetValue<bool>());
        Assert.False(client.LastPayload["enable_geometry"]!.GetValue<bool>());
        Assert.Equal("https://queue.fal.run/status/req-123", result.ProviderStatusUrl!.ToString());
        Assert.Equal("https://queue.fal.run/response/req-123", result.ProviderResponseUrl!.ToString());
        Assert.Equal("https://queue.fal.run/cancel/req-123", result.ProviderCancelUrl!.ToString());
    }

    [Fact]
    public async Task GetStatus_UsesFalQueueStatusEndpointAndMapsPollingState()
    {
        var client = new RecordingFalQueueClient
        {
            StatusJson = JsonNode.Parse(@"{""status"":""IN_PROGRESS"",""request_id"":""req-123""}")!,
        };
        var provider = new FalReconstructionProvider(client);

        var status = await provider.GetStatusAsync(
            "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
            "req-123",
            new Uri("https://queue.fal.run/custom-status"),
            CancellationToken.None);

        Assert.Equal("https://queue.fal.run/custom-status", client.LastStatusUrl!.ToString());
        Assert.Equal("req-123", status.ProviderJobId);
        Assert.Equal(ReconstructionProviderLifecycleState.Polling, status.State);
        Assert.False(status.IsTerminal);
    }

    [Fact]
    public async Task GetStatus_MapsCompletedAsTerminalSuccess()
    {
        var client = new RecordingFalQueueClient
        {
            StatusJson = JsonNode.Parse(@"{""status"":""COMPLETED"",""request_id"":""req-123""}")!,
        };
        var provider = new FalReconstructionProvider(client);

        var status = await provider.GetStatusAsync(
            "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
            "req-123",
            new Uri("https://queue.fal.run/custom-status"),
            CancellationToken.None);

        Assert.True(status.IsTerminal);
        Assert.True(status.IsSuccess);
        Assert.Equal(ReconstructionProviderLifecycleState.Complete, status.State);
    }

    private sealed class RecordingFalQueueClient : IFalReconstructionQueueClient
    {
        public string? LastModelId { get; private set; }
        public JsonObject? LastPayload { get; private set; }
        public Uri? LastStatusUrl { get; private set; }
        public JsonNode StatusJson { get; set; } =
            JsonNode.Parse(@"{""status"":""IN_QUEUE"",""request_id"":""req-123""}")!;

        public Task<JsonNode> SubmitAsync(string modelId, JsonObject payload, CancellationToken ct)
        {
            LastModelId = modelId;
            LastPayload = payload;
            return Task.FromResult<JsonNode>(
                JsonNode.Parse(
                    @"{""request_id"":""req-123"",""status_url"":""https://queue.fal.run/status/req-123"",""response_url"":""https://queue.fal.run/response/req-123"",""cancel_url"":""https://queue.fal.run/cancel/req-123""}")!);
        }

        public Task<JsonNode> GetStatusAsync(
            Uri statusUrl,
            CancellationToken ct)
        {
            LastStatusUrl = statusUrl;
            return Task.FromResult(StatusJson);
        }

        public Task<JsonNode> GetResultAsync(
            Uri responseUrl,
            CancellationToken ct)
            => Task.FromResult<JsonNode>(JsonNode.Parse("{}")!);

        public Task<ProviderCancelOutcome> CancelAsync(
            Uri cancelUrl,
            string cancelHttpMethod,
            CancellationToken ct)
            => Task.FromResult<ProviderCancelOutcome>(new CanceledOutcome());
    }
}
