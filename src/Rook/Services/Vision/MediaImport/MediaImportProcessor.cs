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

        public MediaImportProcessor(ArtifactStore store)
        {
            _imageImporter = new ImageMediaImporter(store ?? throw new ArgumentNullException(nameof(store)));
        }

        public Task<MediaImportProcessResult> ProcessAsync(string path, CancellationToken ct)
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
                return Task.FromResult(_imageImporter.Import(path));

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
    }
}
