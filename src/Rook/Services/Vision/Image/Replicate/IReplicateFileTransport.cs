using System;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Replicate
{
    internal interface IReplicateFileTransport
    {
        Task<ReplicateFileUploadResult> UploadAsync(
            string apiToken,
            string fileName,
            byte[] bytes,
            string mimeType,
            CancellationToken ct);
    }

    internal sealed class ReplicateFileUploadResult
    {
        private ReplicateFileUploadResult(
            Uri? url,
            GenerationError? error,
            bool success)
        {
            Url = url;
            Error = error;
            Success = success;
        }

        public Uri? Url { get; }
        public GenerationError? Error { get; }
        public bool Success { get; }

        public static ReplicateFileUploadResult Uploaded(Uri url)
        {
            if (url is null) throw new ArgumentNullException(nameof(url));
            return new ReplicateFileUploadResult(url, null, success: true);
        }

        public static ReplicateFileUploadResult Failed(GenerationError error)
        {
            if (error is null) throw new ArgumentNullException(nameof(error));
            return new ReplicateFileUploadResult(null, error, success: false);
        }
    }
}
