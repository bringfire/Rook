using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    internal sealed class VideoArtifactMaterializer
    {
        internal const long MaxGeneratedVideoBytes = 250L * 1024 * 1024;
        private const int MaxRemoteFetchAttempts = 3;

        private readonly HttpClient _httpClient;
        private readonly long _maxGeneratedVideoBytes;

        public VideoArtifactMaterializer()
            : this(MaxGeneratedVideoBytes)
        {
        }

        internal VideoArtifactMaterializer(long maxGeneratedVideoBytes)
        {
            if (maxGeneratedVideoBytes <= 0)
                throw new ArgumentOutOfRangeException(
                    nameof(maxGeneratedVideoBytes),
                    "Maximum generated video bytes must be positive.");

            _httpClient = new HttpClient();
            _maxGeneratedVideoBytes = maxGeneratedVideoBytes;
        }

        internal VideoArtifactMaterializer(
            HttpMessageHandler handler,
            long maxGeneratedVideoBytes = MaxGeneratedVideoBytes)
        {
            if (handler is null) throw new ArgumentNullException(nameof(handler));
            if (maxGeneratedVideoBytes <= 0)
                throw new ArgumentOutOfRangeException(
                    nameof(maxGeneratedVideoBytes),
                    "Maximum generated video bytes must be positive.");

            _httpClient = new HttpClient(handler);
            _maxGeneratedVideoBytes = maxGeneratedVideoBytes;
        }

        public async Task<VideoArtifactMaterializationResult> MaterializeAsync(
            ResultArtifact artifact,
            CancellationToken cancellationToken)
        {
            if (artifact is null) throw new ArgumentNullException(nameof(artifact));

            if (artifact.Body is InlineArtifactBody inline)
            {
                if (inline.Bytes.LongLength > _maxGeneratedVideoBytes)
                    return VideoArtifactMaterializationResult.Fail(ExecutionFailed(
                        "Inline video artifact exceeded the maximum allowed size."));

                return VideoArtifactMaterializationResult.Ok(
                    inline.Bytes,
                    artifact.DeclaredMimeType!);
            }

            if (artifact.Body is not RemoteArtifactBody remote)
                return VideoArtifactMaterializationResult.Fail(ExecutionFailed(
                    "Video artifact body type is unsupported."));

            for (var attempt = 1; attempt <= MaxRemoteFetchAttempts; attempt++)
            {
                try
                {
                    using var request = new HttpRequestMessage(HttpMethod.Get, remote.Url);
                    using var response = await _httpClient.SendAsync(
                            request,
                            HttpCompletionOption.ResponseHeadersRead,
                            cancellationToken)
                        .ConfigureAwait(false);

                    if (!response.IsSuccessStatusCode)
                    {
                        if (IsRetryableStatus(response.StatusCode)
                            && attempt < MaxRemoteFetchAttempts)
                        {
                            continue;
                        }

                        return VideoArtifactMaterializationResult.Fail(
                            new GenerationError(
                                GenerationErrorCode.DependencyUnavailable,
                                $"Remote video artifact fetch failed with HTTP {(int)response.StatusCode}.",
                                IsRetryableStatus(response.StatusCode)));
                    }

                    if (response.Content is null)
                        return VideoArtifactMaterializationResult.Fail(ExecutionFailed(
                            "Remote video artifact response was empty."));

                    var contentLength = response.Content.Headers.ContentLength;
                    if (contentLength > _maxGeneratedVideoBytes)
                        return VideoArtifactMaterializationResult.Fail(ExecutionFailed(
                            "Remote video artifact exceeded the maximum allowed size."));

                    var mimeType = ResolveMimeType(
                        artifact.DeclaredMimeType,
                        response.Content.Headers.ContentType?.MediaType);

                    using var stream = await response.Content.ReadAsStreamAsync()
                        .ConfigureAwait(false);

                    var bytes = await CappedStreamReader.ReadCappedAsync(
                            stream, _maxGeneratedVideoBytes, cancellationToken)
                        .ConfigureAwait(false);
                    if (bytes is null)
                        return VideoArtifactMaterializationResult.Fail(ExecutionFailed(
                            "Remote video artifact exceeded the maximum allowed size."));

                    if (bytes.Length == 0)
                        return VideoArtifactMaterializationResult.Fail(ExecutionFailed(
                            "Remote video artifact response was empty."));

                    return VideoArtifactMaterializationResult.Ok(bytes, mimeType);
                }
                catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
                {
                    return VideoArtifactMaterializationResult.Fail(
                        new GenerationError(
                            GenerationErrorCode.Interrupted,
                            "Remote video artifact fetch was cancelled.",
                            Retryable: false));
                }
                catch (TaskCanceledException)
                {
                    if (attempt < MaxRemoteFetchAttempts)
                        continue;

                    return VideoArtifactMaterializationResult.Fail(
                        new GenerationError(
                            GenerationErrorCode.DependencyUnavailable,
                            "Remote video artifact fetch timed out.",
                            Retryable: true));
                }
                catch (HttpRequestException)
                {
                    if (attempt < MaxRemoteFetchAttempts)
                        continue;

                    return VideoArtifactMaterializationResult.Fail(
                        new GenerationError(
                            GenerationErrorCode.DependencyUnavailable,
                            "Remote video artifact fetch failed due to a transport error.",
                            Retryable: true));
                }
                catch (IOException)
                {
                    if (attempt < MaxRemoteFetchAttempts)
                        continue;

                    return VideoArtifactMaterializationResult.Fail(
                        new GenerationError(
                            GenerationErrorCode.DependencyUnavailable,
                            "Remote video artifact fetch failed while reading the response stream.",
                            Retryable: true));
                }
            }

            return VideoArtifactMaterializationResult.Fail(ExecutionFailed(
                "Remote video artifact fetch failed."));
        }

        private static string ResolveMimeType(
            string? declaredMimeType,
            string? responseMimeType)
        {
            if (!string.IsNullOrWhiteSpace(declaredMimeType))
                return declaredMimeType!;

            if (!string.IsNullOrWhiteSpace(responseMimeType))
                return responseMimeType!;

            return "video/mp4";
        }

        private static bool IsRetryableStatus(HttpStatusCode statusCode)
        {
            var status = (int)statusCode;
            return status >= 500 && status <= 599;
        }

        private static GenerationError ExecutionFailed(string message) =>
            new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                message,
                Retryable: false);
    }

    internal sealed class VideoArtifactMaterializationResult
    {
        private VideoArtifactMaterializationResult(
            bool success,
            byte[]? bytes,
            string? mimeType,
            GenerationError? error)
        {
            Success = success;
            Bytes = bytes;
            MimeType = mimeType;
            Error = error;
        }

        public bool Success { get; }
        public byte[]? Bytes { get; }
        public string? MimeType { get; }
        public GenerationError? Error { get; }

        public static VideoArtifactMaterializationResult Ok(
            byte[] bytes,
            string mimeType) =>
            new VideoArtifactMaterializationResult(
                success: true,
                bytes: bytes,
                mimeType: mimeType,
                error: null);

        public static VideoArtifactMaterializationResult Fail(
            GenerationError error) =>
            new VideoArtifactMaterializationResult(
                success: false,
                bytes: null,
                mimeType: null,
                error: error);
    }
}
