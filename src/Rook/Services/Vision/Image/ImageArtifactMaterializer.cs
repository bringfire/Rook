using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image
{
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

        public async Task<ImageArtifactMaterializationResult> MaterializeAsync(
            ResultArtifact artifact,
            CancellationToken cancellationToken)
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
                using var request = new HttpRequestMessage(HttpMethod.Get, remote.Url);
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
                using var buffer = new MemoryStream();
                var readBuffer = new byte[81920];

                while (true)
                {
                    var read = await stream.ReadAsync(
                            readBuffer,
                            0,
                            readBuffer.Length,
                            cancellationToken)
                        .ConfigureAwait(false);
                    if (read == 0)
                        break;

                    if (buffer.Length + read > MaxGeneratedImageBytes)
                    {
                        return ImageArtifactMaterializationResult.Fail(ExecutionFailed(
                            "Remote image artifact exceeded the maximum allowed size."));
                    }

                    buffer.Write(readBuffer, 0, read);
                }

                if (buffer.Length == 0)
                    return ImageArtifactMaterializationResult.Fail(ExecutionFailed(
                        "Remote image artifact response was empty."));

                return ImageArtifactMaterializationResult.Ok(buffer.ToArray(), mimeType);
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
