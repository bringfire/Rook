using System;
using System.IO;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Reconstruction.Fal;

public sealed record ReconstructionProviderSubmitRequest(
    string ModelId,
    Uri InputImageUrl,
    JsonObject Options);

public sealed record ReconstructionProviderSubmitResult(
    string ProviderJobId,
    JsonNode ProviderSubmitJson);

public enum ReconstructionProviderLifecycleState
{
    Queued,
    Polling,
    Materializing,
    Complete,
    Error,
    Cancelled,
    Unknown,
}

public sealed record ReconstructionProviderStatusResult(
    string ProviderJobId,
    ReconstructionProviderLifecycleState State,
    bool IsTerminal,
    bool IsSuccess,
    JsonNode ProviderStatusJson,
    ReconstructionFailure? Error);

public interface IReconstructionProvider
{
    Task<ReconstructionProviderSubmitResult> SubmitAsync(
        ReconstructionProviderSubmitRequest request,
        CancellationToken cancellationToken);

    Task<ReconstructionProviderStatusResult> GetStatusAsync(
        string modelId,
        string providerJobId,
        CancellationToken cancellationToken);

    Task<JsonNode> GetResultAsync(
        string modelId,
        string providerJobId,
        CancellationToken cancellationToken);

    Task<ProviderCancelOutcome> CancelAsync(
        string modelId,
        string providerJobId,
        CancellationToken cancellationToken);
}

public interface IFalReconstructionQueueClient
{
    Task<JsonNode> SubmitAsync(string modelId, JsonObject payload, CancellationToken ct);
    Task<JsonNode> GetStatusAsync(string modelId, string providerJobId, CancellationToken ct);
    Task<JsonNode> GetResultAsync(string modelId, string providerJobId, CancellationToken ct);
    Task<ProviderCancelOutcome> CancelAsync(string modelId, string providerJobId, CancellationToken ct);
}

public sealed class FalReconstructionSourceImagePublisher : IReconstructionSourceImagePublisher
{
    public const int SourceImageExpirationSeconds = 3600;

    private readonly FalApiClient _client;
    private readonly IGenerationSecretStore _secrets;

    public FalReconstructionSourceImagePublisher(
        FalApiClient client,
        IGenerationSecretStore secrets)
    {
        _client = client ?? throw new ArgumentNullException(nameof(client));
        _secrets = secrets ?? throw new ArgumentNullException(nameof(secrets));
    }

    public async Task<Uri> PublishAsync(
        Artifact artifact,
        string role,
        string absolutePath,
        CancellationToken ct)
    {
        if (artifact is null) throw new ArgumentNullException(nameof(artifact));
        if (string.IsNullOrWhiteSpace(absolutePath))
            throw new ArgumentException("Source image path is required.", nameof(absolutePath));

        var apiKey = _secrets.GetSecret(GenerationSecretKeys.FalApiKey);
        if (string.IsNullOrWhiteSpace(apiKey))
            throw new InvalidOperationException("fal API key is required for reconstruction.");

        var fileName = $"rook-reconstruction-{artifact.Id:D}-{role}{Path.GetExtension(absolutePath)}";
        var fileUrl = await _client.UploadFileToCdnAsync(
            apiKey!,
            fileName,
            File.ReadAllBytes(absolutePath),
            ContentTypeFor(absolutePath),
            FalUploadPlatformHeaders.ForSourceUpload(SourceImageExpirationSeconds),
            ct).ConfigureAwait(false);
        return new Uri(fileUrl, UriKind.Absolute);
    }

    private static string ContentTypeFor(string path)
    {
        return Path.GetExtension(path).ToLowerInvariant() switch
        {
            ".jpg" or ".jpeg" => "image/jpeg",
            ".webp" => "image/webp",
            _ => "image/png",
        };
    }
}

public sealed class FalReconstructionProvider : IReconstructionProvider
{
    private readonly IFalReconstructionQueueClient _client;

    public FalReconstructionProvider(IFalReconstructionQueueClient client)
    {
        _client = client ?? throw new ArgumentNullException(nameof(client));
    }

    public async Task<ReconstructionProviderSubmitResult> SubmitAsync(
        ReconstructionProviderSubmitRequest request,
        CancellationToken cancellationToken)
    {
        if (request is null) throw new ArgumentNullException(nameof(request));

        var payload = new JsonObject
        {
            ["input_image_url"] = request.InputImageUrl.ToString(),
        };
        foreach (var kvp in request.Options)
            payload[kvp.Key] = kvp.Value?.DeepClone();

        var submitJson = await _client.SubmitAsync(
            request.ModelId,
            payload,
            cancellationToken).ConfigureAwait(false);
        var requestId = ReadString(submitJson, "request_id")
            ?? ReadString(submitJson, "requestId")
            ?? ReadString(submitJson, "id");
        if (string.IsNullOrWhiteSpace(requestId))
            throw new InvalidOperationException("fal submit response did not include request_id.");

        return new ReconstructionProviderSubmitResult(requestId!, submitJson);
    }

    public async Task<ReconstructionProviderStatusResult> GetStatusAsync(
        string modelId,
        string providerJobId,
        CancellationToken cancellationToken)
    {
        var statusJson = await _client.GetStatusAsync(
            modelId,
            providerJobId,
            cancellationToken).ConfigureAwait(false);
        var state = MapStatus(ReadString(statusJson, "status"));
        var isSuccess = state == ReconstructionProviderLifecycleState.Complete;
        var isTerminal = isSuccess
            || state == ReconstructionProviderLifecycleState.Error
            || state == ReconstructionProviderLifecycleState.Cancelled;

        return new ReconstructionProviderStatusResult(
            ReadString(statusJson, "request_id") ?? providerJobId,
            state,
            isTerminal,
            isSuccess,
            statusJson,
            state == ReconstructionProviderLifecycleState.Error
                ? Failure("provider_error", "fal reconstruction job failed.", retryable: true)
                : null);
    }

    public Task<JsonNode> GetResultAsync(
        string modelId,
        string providerJobId,
        CancellationToken cancellationToken)
        => _client.GetResultAsync(modelId, providerJobId, cancellationToken);

    public Task<ProviderCancelOutcome> CancelAsync(
        string modelId,
        string providerJobId,
        CancellationToken cancellationToken)
        => _client.CancelAsync(modelId, providerJobId, cancellationToken);

    private static ReconstructionProviderLifecycleState MapStatus(string? status)
    {
        return (status ?? string.Empty).Trim().ToUpperInvariant() switch
        {
            "IN_QUEUE" or "QUEUED" => ReconstructionProviderLifecycleState.Queued,
            "IN_PROGRESS" or "RUNNING" or "PROCESSING" =>
                ReconstructionProviderLifecycleState.Polling,
            "COMPLETED" or "COMPLETE" or "SUCCEEDED" =>
                ReconstructionProviderLifecycleState.Complete,
            "FAILED" or "ERROR" => ReconstructionProviderLifecycleState.Error,
            "CANCELLED" or "CANCELED" => ReconstructionProviderLifecycleState.Cancelled,
            _ => ReconstructionProviderLifecycleState.Unknown,
        };
    }

    private static string? ReadString(JsonNode? node, string name)
        => node is JsonObject obj
            && obj.TryGetPropertyValue(name, out var value)
            && value is JsonValue jsonValue
            && jsonValue.TryGetValue<string>(out var text)
                ? text
                : null;

    private static ReconstructionFailure Failure(
        string code,
        string message,
        bool retryable)
        => new(code, message, retryable, null, new System.Collections.Generic.Dictionary<string, object?>());
}

public sealed class FalReconstructionQueueClient : IFalReconstructionQueueClient
{
    private readonly FalApiClient _client;
    private readonly Func<string?> _apiKeyProvider;

    public FalReconstructionQueueClient(FalApiClient client, string apiKey)
        : this(client, () => apiKey)
    {
    }

    public FalReconstructionQueueClient(FalApiClient client, Func<string?> apiKeyProvider)
    {
        _client = client ?? throw new ArgumentNullException(nameof(client));
        _apiKeyProvider = apiKeyProvider ?? throw new ArgumentNullException(nameof(apiKeyProvider));
    }

    public async Task<JsonNode> SubmitAsync(string modelId, JsonObject payload, CancellationToken ct)
    {
        var response = await _client.PostJsonAsync(
            ApiKey(),
            QueueUri(modelId),
            payload.ToJsonString(),
            ct).ConfigureAwait(false);
        return ParseSuccess(response, "fal reconstruction submit failed.");
    }

    public async Task<JsonNode> GetStatusAsync(string modelId, string providerJobId, CancellationToken ct)
    {
        var response = await _client.GetAsync(
            ApiKey(),
            QueueUri(modelId, providerJobId, "status"),
            ct).ConfigureAwait(false);
        return ParseSuccess(response, "fal reconstruction status failed.");
    }

    public async Task<JsonNode> GetResultAsync(string modelId, string providerJobId, CancellationToken ct)
    {
        var response = await _client.GetAsync(
            ApiKey(),
            QueueUri(modelId, providerJobId, null),
            ct).ConfigureAwait(false);
        return ParseSuccess(response, "fal reconstruction result failed.");
    }

    public async Task<ProviderCancelOutcome> CancelAsync(
        string modelId,
        string providerJobId,
        CancellationToken ct)
    {
        var response = await _client.SendAsync(
            ApiKey(),
            HttpMethod.Put,
            QueueUri(modelId, providerJobId, "cancel"),
            bodyJson: null,
            ct).ConfigureAwait(false);
        return response.IsSuccessStatusCode
            ? new CanceledOutcome()
            : new FailedCancelOutcome(new GenerationError(
                GenerationErrorCode.DependencyUnavailable,
                "fal reconstruction cancel failed.",
                Retryable: true));
    }

    private string ApiKey()
    {
        var apiKey = _apiKeyProvider();
        if (string.IsNullOrWhiteSpace(apiKey))
            throw new InvalidOperationException("fal API key is required for reconstruction.");
        return apiKey!;
    }

    private static Uri QueueUri(string modelId)
        => new($"https://queue.fal.run/{modelId}");

    private static Uri QueueUri(string modelId, string providerJobId, string? suffix)
    {
        var path = $"https://queue.fal.run/{modelId}/requests/{Uri.EscapeDataString(providerJobId)}";
        if (!string.IsNullOrWhiteSpace(suffix))
            path += "/" + suffix;
        return new Uri(path);
    }

    private static JsonNode ParseSuccess(FalHttpResponse response, string message)
    {
        if (!response.IsSuccessStatusCode)
            throw new InvalidOperationException($"{message} status={response.StatusCode}");
        return JsonNode.Parse(response.Body) ?? new JsonObject();
    }
}
