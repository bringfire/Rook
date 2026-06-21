using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image
{
    internal delegate ImageArtifactFetchRequest ImageArtifactRequestFactory(ResultArtifact artifact);

    internal sealed class ImageArtifactFetchRequest
    {
        private ImageArtifactFetchRequest(HttpRequestMessage? request, GenerationError? error)
        {
            Request = request;
            Error = error;
        }

        public HttpRequestMessage? Request { get; }
        public GenerationError? Error { get; }

        public static ImageArtifactFetchRequest Created(HttpRequestMessage request)
        {
            if (request is null) throw new ArgumentNullException(nameof(request));
            return new ImageArtifactFetchRequest(request, error: null);
        }

        public static ImageArtifactFetchRequest Failed(GenerationError error)
        {
            if (error is null) throw new ArgumentNullException(nameof(error));
            return new ImageArtifactFetchRequest(request: null, error);
        }
    }

    internal sealed class ImageArtifactMaterializer
    {
        internal const long MaxGeneratedImageBytes = 25L * 1024 * 1024;

        private readonly HttpClient _httpClient;

        public ImageArtifactMaterializer()
        {
            _httpClient = new HttpClient();
        }

        internal ImageArtifactMaterializer(HttpMessageHandler handler)
        {
            if (handler is null) throw new ArgumentNullException(nameof(handler));

            _httpClient = new HttpClient(handler);
        }

        public Task<ImageArtifactMaterializationResult> MaterializeAsync(
            ResultArtifact artifact,
            CancellationToken cancellationToken) =>
            MaterializeAsync(artifact, cancellationToken, requestFactory: null);

        public async Task<ImageArtifactMaterializationResult> MaterializeAsync(
            ResultArtifact artifact,
            CancellationToken cancellationToken,
            ImageArtifactRequestFactory? requestFactory)
        {
            if (artifact is null) throw new ArgumentNullException(nameof(artifact));

            if (artifact.Body is InlineArtifactBody inline)
            {
                if (inline.Bytes.LongLength > MaxGeneratedImageBytes)
                {
                    return ImageArtifactMaterializationResult.Fail(ExecutionFailed(
                        "Inline image artifact exceeded the maximum allowed size."));
                }

                return ImageArtifactMaterializationResult.Ok(
                    inline.Bytes,
                    artifact.DeclaredMimeType!);
            }

            if (artifact.Body is not RemoteArtifactBody remote)
                return ImageArtifactMaterializationResult.Fail(ExecutionFailed(
                    "Image artifact body type is unsupported."));

            try
            {
                var fetchRequest = CreateRequest(artifact, remote, requestFactory);
                if (fetchRequest.Error is not null)
                    return ImageArtifactMaterializationResult.Fail(fetchRequest.Error);

                if (fetchRequest.Request is null)
                    return ImageArtifactMaterializationResult.Fail(ExecutionFailed(
                        "Image artifact request factory did not return a request."));

                using var request = fetchRequest.Request;
                using var response = await _httpClient.SendAsync(
                        request,
                        HttpCompletionOption.ResponseHeadersRead,
                        cancellationToken)
                    .ConfigureAwait(false);

                if (!response.IsSuccessStatusCode)
                {
                    return ImageArtifactMaterializationResult.Fail(
                        new GenerationError(
                            GenerationErrorCode.DependencyUnavailable,
                            $"Remote image artifact fetch failed with HTTP {(int)response.StatusCode}.",
                            IsRetryableStatus(response.StatusCode)));
                }

                var contentLength = response.Content?.Headers.ContentLength;
                if (contentLength > MaxGeneratedImageBytes)
                {
                    return ImageArtifactMaterializationResult.Fail(ExecutionFailed(
                        "Remote image artifact exceeded the maximum allowed size."));
                }

                if (response.Content is null)
                    return ImageArtifactMaterializationResult.Fail(ExecutionFailed(
                        "Remote image artifact response was empty."));

                var mimeType = ResolveMimeType(
                    artifact.DeclaredMimeType,
                    response.Content.Headers.ContentType?.MediaType);

                using var stream = await response.Content.ReadAsStreamAsync()
                    .ConfigureAwait(false);

                var bytes = await CappedStreamReader.ReadCappedAsync(
                        stream, MaxGeneratedImageBytes, cancellationToken)
                    .ConfigureAwait(false);
                if (bytes is null)
                    return ImageArtifactMaterializationResult.Fail(ExecutionFailed(
                        "Remote image artifact exceeded the maximum allowed size."));

                if (bytes.Length == 0)
                    return ImageArtifactMaterializationResult.Fail(ExecutionFailed(
                        "Remote image artifact response was empty."));

                return ImageArtifactMaterializationResult.Ok(bytes, mimeType);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                return ImageArtifactMaterializationResult.Fail(
                    new GenerationError(
                        GenerationErrorCode.Interrupted,
                        "Remote image artifact fetch was cancelled.",
                        Retryable: false));
            }
            catch (TaskCanceledException)
            {
                return ImageArtifactMaterializationResult.Fail(
                    new GenerationError(
                        GenerationErrorCode.DependencyUnavailable,
                        "Remote image artifact fetch timed out.",
                        Retryable: true));
            }
            catch (HttpRequestException)
            {
                return ImageArtifactMaterializationResult.Fail(
                    new GenerationError(
                        GenerationErrorCode.DependencyUnavailable,
                        "Remote image artifact fetch failed due to a transport error.",
                        Retryable: true));
            }
            catch (IOException)
            {
                return ImageArtifactMaterializationResult.Fail(
                    new GenerationError(
                        GenerationErrorCode.DependencyUnavailable,
                        "Remote image artifact fetch failed while reading the response stream.",
                        Retryable: true));
            }
        }

        private static ImageArtifactFetchRequest CreateRequest(
            ResultArtifact artifact,
            RemoteArtifactBody remote,
            ImageArtifactRequestFactory? requestFactory)
        {
            if (requestFactory is null)
                return ImageArtifactFetchRequest.Created(
                    new HttpRequestMessage(HttpMethod.Get, remote.Url));

            return requestFactory(artifact)
                ?? ImageArtifactFetchRequest.Failed(ExecutionFailed(
                    "Image artifact request factory did not return a request."));
        }

        private static string ResolveMimeType(
            string? declaredMimeType,
            string? responseMimeType)
        {
            if (!string.IsNullOrWhiteSpace(declaredMimeType))
                return declaredMimeType!;

            if (!string.IsNullOrWhiteSpace(responseMimeType))
                return responseMimeType!;

            return "image/png";
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

    internal sealed class ImageArtifactMaterializationResult
    {
        private ImageArtifactMaterializationResult(
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

        public static ImageArtifactMaterializationResult Ok(
            byte[] bytes,
            string mimeType) =>
            new ImageArtifactMaterializationResult(
                success: true,
                bytes: bytes,
                mimeType: mimeType,
                error: null);

        public static ImageArtifactMaterializationResult Fail(
            GenerationError error) =>
            new ImageArtifactMaterializationResult(
                success: false,
                bytes: null,
                mimeType: null,
                error: error);
    }
}
