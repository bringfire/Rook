using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;

namespace Rook.Services.Vision.MediaImport
{
    public sealed class MediaImportProcessor : IMediaImportProcessor
    {
        private readonly ImageMediaImporter _imageImporter;
        private readonly VideoMediaImporter _videoImporter;

        public MediaImportProcessor(ArtifactStore store)
        {
            store = store ?? throw new ArgumentNullException(nameof(store));
            _imageImporter = new ImageMediaImporter(store);
            _videoImporter = new VideoMediaImporter(store);
        }

        public Task<MediaImportProcessResult> ProcessAsync(
            string path,
            CancellationToken ct,
            Action<MediaImportItemState>? reportState = null)
        {
            ct.ThrowIfCancellationRequested();

            if (string.IsNullOrWhiteSpace(path))
            {
                return Task.FromResult(MediaImportProcessResult.Failed(
                    MediaImportFailureCode.FileNotFound,
                    "Source file was not found."));
            }

            var extension = Path.GetExtension(path).TrimStart('.').ToLowerInvariant();
            if (IsImageExtension(extension))
                return Task.FromResult(_imageImporter.Import(path, reportState));

            if (IsVideoExtension(extension))
                return _videoImporter.Import(path, ct, reportState);

            return Task.FromResult(MediaImportProcessResult.Failed(
                MediaImportFailureCode.UnsupportedMediaType,
                $"Media extension '.{extension}' is not supported."));
        }

        private static bool IsImageExtension(string extension)
            => extension == "png" ||
               extension == "jpg" ||
               extension == "jpeg" ||
               extension == "webp" ||
               extension == "gif" ||
               extension == "tiff" ||
               extension == "heic" ||
               extension == "heif" ||
               extension == "svg";

        private static bool IsVideoExtension(string extension)
            => extension == "mp4" ||
               extension == "mov" ||
               extension == "webm";
    }
}
