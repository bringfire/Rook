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

        await provider.SubmitAsync(new ReconstructionProviderSubmitRequest(
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
            CancellationToken.None);

        Assert.Equal("fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d", client.LastStatusModelId);
        Assert.Equal("req-123", client.LastStatusProviderJobId);
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
            CancellationToken.None);

        Assert.True(status.IsTerminal);
        Assert.True(status.IsSuccess);
        Assert.Equal(ReconstructionProviderLifecycleState.Complete, status.State);
    }

    private sealed class RecordingFalQueueClient : IFalReconstructionQueueClient
    {
        public string? LastModelId { get; private set; }
        public JsonObject? LastPayload { get; private set; }
        public string? LastStatusModelId { get; private set; }
        public string? LastStatusProviderJobId { get; private set; }
        public JsonNode StatusJson { get; set; } =
            JsonNode.Parse(@"{""status"":""IN_QUEUE"",""request_id"":""req-123""}")!;

        public Task<JsonNode> SubmitAsync(string modelId, JsonObject payload, CancellationToken ct)
        {
            LastModelId = modelId;
            LastPayload = payload;
            return Task.FromResult<JsonNode>(
                JsonNode.Parse(@"{""request_id"":""req-123""}")!);
        }

        public Task<JsonNode> GetStatusAsync(
            string modelId,
            string providerJobId,
            CancellationToken ct)
        {
            LastStatusModelId = modelId;
            LastStatusProviderJobId = providerJobId;
            return Task.FromResult(StatusJson);
        }

        public Task<JsonNode> GetResultAsync(
            string modelId,
            string providerJobId,
            CancellationToken ct)
            => Task.FromResult<JsonNode>(JsonNode.Parse("{}")!);

        public Task<ProviderCancelOutcome> CancelAsync(
            string modelId,
            string providerJobId,
            CancellationToken ct)
            => Task.FromResult<ProviderCancelOutcome>(new CanceledOutcome());
    }
}
