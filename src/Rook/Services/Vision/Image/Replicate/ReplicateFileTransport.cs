using System;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Replicate;

namespace Rook.Services.Vision.Image.Replicate
{
    internal sealed class ReplicateFileTransport : IReplicateFileTransport
    {
        private const string MetadataJson = "{\"rook_usage\":\"flux2_input\"}";

        private readonly ReplicateApiClient _client;

        public ReplicateFileTransport(ReplicateApiClient client)
        {
            _client = client ?? throw new ArgumentNullException(nameof(client));
        }

        public async Task<ReplicateFileUploadResult> UploadAsync(
            string apiToken,
            string fileName,
            byte[] bytes,
            string mimeType,
            CancellationToken ct)
        {
            try
            {
                var uploaded = await _client.UploadFileAsync(
                    apiToken,
                    fileName,
                    bytes,
                    mimeType,
                    MetadataJson,
                    ct).ConfigureAwait(false);

                return ReplicateFileUploadResult.Uploaded(uploaded.FileUrl);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception ex)
            {
                return ReplicateFileUploadResult.Failed(UploadUnavailable(ex));
            }
        }

        private static GenerationError UploadUnavailable(Exception ex) =>
            new(
                Code: GenerationErrorCode.DependencyUnavailable,
                Message: "Replicate file upload transport is unavailable, so local Flux 2 Pro source images cannot be submitted. "
                    + $"Upload failure detail: {ex.GetType().Name}: {ex.Message}",
                Retryable: true,
                Field: "input_image_path");
    }
}
