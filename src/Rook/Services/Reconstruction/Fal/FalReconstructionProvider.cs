using System;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Reconstruction.Fal;

/// <summary>
/// Internal signal that the fal API key is not configured, raised at the reconstruction fal edge
/// (<see cref="FalApiTransport"/> / <see cref="FalReconstructionSourceImagePublisher"/>) and caught at
/// the <c>ReconstructionJobManager</c> boundary, which maps it to the public <c>missing_credential</c>
/// failure. NOT part of the public contract. Carries a short diagnostic only — the public remediation
/// text is owned by <c>ReconstructionErrorMapping.MissingCredentialFailure()</c>.
/// </summary>
internal sealed class ReconstructionCredentialMissingException : Exception
{
    public ReconstructionCredentialMissingException()
        : base("fal API key is not configured.")
    {
    }
}

public sealed record ReconstructionProviderSubmitRequest(
    string ModelId,
    Uri InputImageUrl,
    JsonObject Options);

/// <summary>
/// Narrow transport seam over <see cref="FalApiClient"/> that binds the fal API key at the edge so
/// the provider stays key-agnostic and trivially fakeable in tests. Mirrors the calls the
/// reconstruction queue lifecycle needs (submit POST, status/result GET, cancel SEND).
/// </summary>
public interface IFalTransport
{
    Task<FalHttpResponse> PostJsonAsync(Uri url, string bodyJson, CancellationToken ct);
    Task<FalHttpResponse> GetAsync(Uri url, CancellationToken ct);
    Task<FalHttpResponse> SendAsync(HttpMethod method, Uri url, string? bodyJson, CancellationToken ct);
}

/// <summary>Production adapter binding the fal API key to <see cref="FalApiClient"/>.</summary>
public sealed class FalApiTransport : IFalTransport
{
    private readonly FalApiClient _client;
    private readonly Func<string?> _apiKey;

    public FalApiTransport(FalApiClient client, Func<string?> apiKey)
    {
        _client = client ?? throw new ArgumentNullException(nameof(client));
        _apiKey = apiKey ?? throw new ArgumentNullException(nameof(apiKey));
    }

    private string Key()
    {
        var apiKey = _apiKey();
        if (string.IsNullOrWhiteSpace(apiKey))
            throw new ReconstructionCredentialMissingException();
        return apiKey!;
    }

    public Task<FalHttpResponse> PostJsonAsync(Uri url, string bodyJson, CancellationToken ct)
        => _client.PostJsonAsync(Key(), url, bodyJson, ct);

    public Task<FalHttpResponse> GetAsync(Uri url, CancellationToken ct)
        => _client.GetAsync(Key(), url, ct);

    public Task<FalHttpResponse> SendAsync(HttpMethod method, Uri url, string? bodyJson, CancellationToken ct)
        => _client.SendAsync(Key(), method, url, bodyJson, ct);
}

/// <summary>
/// Reconstruction-specific provider contract that returns the shared, modality-neutral generation
/// outcome union (rather than the generic <c>IGenerationProvider&lt;TRequest,TCapability&gt;</c>,
/// which over-fits a single-artifact model onto the multi-asset reconstruction package). Submit is
/// always async/queued for fal reconstruction.
/// </summary>
public interface IReconstructionProvider
{
    Task<ProviderSubmitOutcome> SubmitAsync(
        ReconstructionProviderSubmitRequest request,
        CancellationToken cancellationToken);

    Task<ProviderStatusOutcome> GetStatusAsync(
        ProviderJobHandle handle,
        CancellationToken cancellationToken);

    Task<ProviderResultOutcome> FetchResultAsync(
        ProviderJobHandle handle,
        CancellationToken cancellationToken);

    Task<ProviderCancelOutcome> CancelAsync(
        ProviderJobHandle handle,
        CancellationToken cancellationToken);
}

/// <summary>
/// Publishes a resolved source image to the fal CDN and returns its signed URL. Storage-agnostic:
/// the caller (manager) resolves bytes/mime/fileName from the artifact store and passes only those,
/// so this type never reads files or touches the artifact store.
/// </summary>
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
        byte[] bytes,
        string mimeType,
        string fileName,
        CancellationToken ct)
    {
        if (bytes is null || bytes.Length == 0)
            throw new ArgumentException("Source image bytes are required.", nameof(bytes));
        if (string.IsNullOrWhiteSpace(fileName))
            throw new ArgumentException("Source image file name is required.", nameof(fileName));

        var apiKey = _secrets.GetSecret(GenerationSecretKeys.FalApiKey);
        if (string.IsNullOrWhiteSpace(apiKey))
            throw new ReconstructionCredentialMissingException();

        var fileUrl = await _client.UploadFileToCdnAsync(
            apiKey!,
            fileName,
            bytes,
            mimeType,
            FalUploadPlatformHeaders.ForSourceUpload(SourceImageExpirationSeconds),
            ct).ConfigureAwait(false);
        return new Uri(fileUrl, UriKind.Absolute);
    }
}

/// <summary>
/// fal queue reconstruction provider built on the shared substrate:
/// <see cref="FalLifecycleMapper"/> (submit-handle + status), <see cref="FalErrorMapper"/>
/// (typed HTTP failures), and <see cref="FalReconstructionResultMapper"/> (result body → role'd
/// artifacts). Every non-2xx response and every parse failure becomes a typed
/// <see cref="GenerationError"/> on a Failed* outcome — there is no bare-throw path that the manager
/// would otherwise surface as an opaque <c>poll_failed</c>.
/// </summary>
public sealed class FalReconstructionProvider : IReconstructionProvider
{
    private const string CancelHttpMethod = "PUT";

    private readonly IFalTransport _transport;

    public FalReconstructionProvider(IFalTransport transport)
    {
        _transport = transport ?? throw new ArgumentNullException(nameof(transport));
    }

    public async Task<ProviderSubmitOutcome> SubmitAsync(
        ReconstructionProviderSubmitRequest request,
        CancellationToken cancellationToken)
    {
        if (request is null) throw new ArgumentNullException(nameof(request));

        var payload = BuildSubmitPayload(request);
        FalHttpResponse response;
        try
        {
            response = await _transport.PostJsonAsync(
                QueueSubmitUri(request.ModelId),
                payload.ToJsonString(),
                cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (TaskCanceledException)
        {
            return new FailedSubmitOutcome(TransportTimeout("submit"));
        }
        catch (HttpRequestException)
        {
            return new FailedSubmitOutcome(TransportError("submit"));
        }

        if (!response.IsSuccessStatusCode)
            return new FailedSubmitOutcome(FalErrorMapper.MapHttpFailure(response));

        if (!TryParse(response.Body, out var body))
            return new FailedSubmitOutcome(JsonError("fal submit body was not valid JSON."));

        try
        {
            return new QueuedSubmitOutcome(
                FalLifecycleMapper.ParseSubmitHandle(body, CancelHttpMethod));
        }
        catch (ArgumentException ex)
        {
            return new FailedSubmitOutcome(new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                ex.Message,
                Retryable: false));
        }
    }

    public async Task<ProviderStatusOutcome> GetStatusAsync(
        ProviderJobHandle handle,
        CancellationToken cancellationToken)
    {
        if (handle is null) throw new ArgumentNullException(nameof(handle));
        if (handle.StatusUrl is null)
            return new FailedStatusOutcome(new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                "Reconstruction job has no status URL.",
                Retryable: false));

        FalHttpResponse response;
        try
        {
            response = await _transport.GetAsync(handle.StatusUrl, cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (TaskCanceledException)
        {
            return new FailedStatusOutcome(TransportTimeout("status"));
        }
        catch (HttpRequestException)
        {
            return new FailedStatusOutcome(TransportError("status"));
        }

        if (!response.IsSuccessStatusCode)
            return new FailedStatusOutcome(FalErrorMapper.MapHttpFailure(response));

        if (!TryParse(response.Body, out var body))
            return new FailedStatusOutcome(JsonError("fal status body was not valid JSON."));

        return FalLifecycleMapper.MapStatus(handle, body);
    }

    public async Task<ProviderResultOutcome> FetchResultAsync(
        ProviderJobHandle handle,
        CancellationToken cancellationToken)
    {
        if (handle is null) throw new ArgumentNullException(nameof(handle));
        if (handle.ResponseUrl is null)
            return new FailedResultOutcome(new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                "Reconstruction job has no response URL.",
                Retryable: false));

        FalHttpResponse response;
        try
        {
            response = await _transport.GetAsync(handle.ResponseUrl, cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (TaskCanceledException)
        {
            return new FailedResultOutcome(TransportTimeout("result fetch"));
        }
        catch (HttpRequestException)
        {
            return new FailedResultOutcome(TransportError("result fetch"));
        }

        if (!response.IsSuccessStatusCode)
            return new FailedResultOutcome(FalErrorMapper.MapHttpFailure(response));

        if (!TryParse(response.Body, out var body))
            return new FailedResultOutcome(JsonError("fal result body was not valid JSON."));

        var artifacts = FalReconstructionResultMapper.MapArtifacts(body);
        if (artifacts.Count == 0)
            return new FailedResultOutcome(new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                "fal result contained no recognizable asset URLs.",
                Retryable: false));

        var metadata = new System.Collections.Generic.Dictionary<string, JsonNode>
        {
            ["provider_result_json"] = body.DeepClone(),
        };
        return new SuccessResultOutcome(new ProviderResultEnvelope(artifacts, metadata));
    }

    public async Task<ProviderCancelOutcome> CancelAsync(
        ProviderJobHandle handle,
        CancellationToken cancellationToken)
    {
        if (handle is null) throw new ArgumentNullException(nameof(handle));
        if (handle.CancelUrl is null)
            return new AlreadyTerminalOutcome(GenerationLifecycleState.Completed);

        var method = new HttpMethod(string.IsNullOrWhiteSpace(handle.CancelHttpMethod)
            ? CancelHttpMethod
            : handle.CancelHttpMethod!);
        FalHttpResponse response;
        try
        {
            response = await _transport.SendAsync(
                method,
                handle.CancelUrl,
                bodyJson: null,
                cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (TaskCanceledException)
        {
            return new FailedCancelOutcome(TransportTimeout("cancel"));
        }
        catch (HttpRequestException)
        {
            return new FailedCancelOutcome(TransportError("cancel"));
        }

        if (response.IsSuccessStatusCode)
            return new CanceledOutcome();
        if (response.StatusCode == 400)
            return new AlreadyTerminalOutcome(GenerationLifecycleState.Completed);
        return new FailedCancelOutcome(FalErrorMapper.MapHttpFailure(response));
    }

    private static JsonObject BuildSubmitPayload(ReconstructionProviderSubmitRequest request)
    {
        var payload = new JsonObject
        {
            ["input_image_url"] = request.InputImageUrl.ToString(),
        };
        foreach (var kvp in request.Options)
            payload[kvp.Key] = kvp.Value?.DeepClone();
        return payload;
    }

    private static bool TryParse(string body, out JsonNode node)
    {
        try
        {
            node = JsonNode.Parse(body) ?? new JsonObject();
            return true;
        }
        catch (JsonException)
        {
            node = new JsonObject();
            return false;
        }
    }

    private static GenerationError JsonError(string message)
        => new(GenerationErrorCode.ExecutionFailed, message, Retryable: false);

    // Raw transport faults from the HttpClient (FalApiClient does not wrap the JSON path) become typed,
    // retryable DependencyUnavailable failures here — parity with the RookVision fal providers — so they
    // never escape to the manager as an opaque submit_failed/poll_failed.
    private static GenerationError TransportTimeout(string phase)
        => new(
            GenerationErrorCode.DependencyUnavailable,
            $"fal reconstruction {phase} timed out.",
            Retryable: true);

    private static GenerationError TransportError(string phase)
        => new(
            GenerationErrorCode.DependencyUnavailable,
            $"fal reconstruction {phase} failed due to a transport error.",
            Retryable: true);

    private static Uri QueueSubmitUri(string modelId)
        => new($"https://queue.fal.run/{modelId}");
}
