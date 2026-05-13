using System;
using System.IO;
using System.Text.Json.Nodes;
using Rook.Artifacts;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.MediaImport;
using Xunit;

namespace Rook.Tests.Services.Vision.MediaImport
{
    public sealed class ImageMediaImporterTests : IDisposable
    {
        private readonly string _root;
        private readonly string _artifactRoot;
        private readonly ArtifactStore _store;

        public ImageMediaImporterTests()
        {
            _root = Path.Combine(Path.GetTempPath(), "rook-image-import-tests", Guid.NewGuid().ToString("N"));
            _artifactRoot = Path.Combine(_root, "artifacts");
            Directory.CreateDirectory(_root);
            _store = new ArtifactStore(_artifactRoot);
        }

        [Fact]
        public void ImportPng_PublishesImportedImage_WithTechnicalMetadata()
        {
            var source = Path.Combine(_root, "source.png");
            File.WriteAllBytes(source, OneByOnePngBytes());
            var importer = new ImageMediaImporter(_store);

            var result = importer.Import(source);

            Assert.True(result.IsSuccess, result.Message);
            var artifact = _store.Get(result.ArtifactId!.Value)!;
            Assert.Equal(MediaImportConstants.ImportedImageKind, artifact.Kind);
            var file = Assert.Single(artifact.Files);
            Assert.Equal(ImageMediaRoles.Image, file.Role);
            Assert.Equal("image.png", file.Path);
            Assert.Equal("source.png", ReadString(artifact.Metadata, "original_filename"));
            Assert.Equal("png", ReadString(artifact.Metadata, "original_extension"));
            Assert.Equal("image/png", ReadString(artifact.Metadata, "mime_type"));
            Assert.Equal(1, ReadInt(artifact.Metadata, "width"));
            Assert.Equal(1, ReadInt(artifact.Metadata, "height"));
            Assert.True(ReadBool(artifact.Metadata, "imported"));
            Assert.DoesNotContain(
                artifact.Metadata.Keys,
                key => key.IndexOf("path", StringComparison.OrdinalIgnoreCase) >= 0);
        }

        [Fact]
        public void ImportWebp_ReadsDimensionsFromHeader_AndPublishesImportedImage()
        {
            var source = Path.Combine(_root, "source.webp");
            File.WriteAllBytes(source, OneByOneWebpVp8xBytes());
            var importer = new ImageMediaImporter(_store);

            var result = importer.Import(source);

            Assert.True(result.IsSuccess, result.Message);
            var artifact = _store.Get(result.ArtifactId!.Value)!;
            Assert.Equal(MediaImportConstants.ImportedImageKind, artifact.Kind);
            var file = Assert.Single(artifact.Files);
            Assert.Equal(ImageMediaRoles.Image, file.Role);
            Assert.Equal("image.webp", file.Path);
            Assert.Equal("image/webp", ReadString(artifact.Metadata, "mime_type"));
            Assert.Equal(1, ReadInt(artifact.Metadata, "width"));
            Assert.Equal(1, ReadInt(artifact.Metadata, "height"));
        }

        [Fact]
        public void MapPublishException_CopyException_ReturnsCopyFailed()
        {
            var exception = new ArtifactBlobCopyException(
                "image",
                @"C:\source.png",
                @"C:\artifact\image.png",
                new IOException("copy failed"));

            var result = ImageMediaImporter.MapPublishException(
                MediaImportConstants.ImportedImageKind,
                exception);

            Assert.False(result.IsSuccess);
            Assert.Equal(MediaImportFailureCode.CopyFailed, result.FailureCode);
            Assert.Equal(MediaImportConstants.ImportedImageKind, result.ArtifactKind);
        }

        [Fact]
        public void ImportGif_ReturnsUnsupportedMediaType_AndPublishesNothing()
        {
            var source = Path.Combine(_root, "source.gif");
            File.WriteAllBytes(source, new byte[] { 0x47, 0x49, 0x46, 0x38 });
            var importer = new ImageMediaImporter(_store);

            var result = importer.Import(source);

            Assert.False(result.IsSuccess);
            Assert.Equal(MediaImportFailureCode.UnsupportedMediaType, result.FailureCode);
            Assert.Empty(_store.List());
        }

        [Fact]
        public void ImportMalformedWebp_ReturnsDecodeFailed_AndPublishesNothing()
        {
            var source = Path.Combine(_root, "broken.webp");
            File.WriteAllBytes(source, new byte[] { 0x52, 0x49, 0x46, 0x46, 0x00, 0x00 });
            var importer = new ImageMediaImporter(_store);

            var result = importer.Import(source);

            Assert.False(result.IsSuccess);
            Assert.Equal(MediaImportFailureCode.DecodeFailed, result.FailureCode);
            Assert.Empty(_store.List());
        }

        [Fact]
        public void ImportDirectory_ReturnsNotRegularFile()
        {
            var source = Path.Combine(_root, "folder.png");
            Directory.CreateDirectory(source);
            var importer = new ImageMediaImporter(_store);

            var result = importer.Import(source);

            Assert.False(result.IsSuccess);
            Assert.Equal(MediaImportFailureCode.NotRegularFile, result.FailureCode);
        }

        [Fact]
        public void MapPublishException_SanitizesFullSourcePathFromMessage()
        {
            var sourceDirectory = Path.Combine(_root, "private");
            var sourcePath = Path.Combine(sourceDirectory, "source.png");
            var exception = new InvalidOperationException($"Failed while copying {sourcePath}.");

            var result = ImageMediaImporter.MapPublishException(
                MediaImportConstants.ImportedImageKind,
                exception);

            Assert.False(result.IsSuccess);
            Assert.Equal(MediaImportFailureCode.PublishFailed, result.FailureCode);
            Assert.DoesNotContain(sourceDirectory, result.Message, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain(sourcePath, result.Message, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public async System.Threading.Tasks.Task ProcessAsync_BlankPath_ReturnsFileNotFound()
        {
            var processor = new MediaImportProcessor(_store);

            var result = await processor.ProcessAsync("   ", System.Threading.CancellationToken.None);

            Assert.False(result.IsSuccess);
            Assert.Equal(MediaImportFailureCode.FileNotFound, result.FailureCode);
        }

        public void Dispose()
        {
            try
            {
                if (Directory.Exists(_root))
                    Directory.Delete(_root, recursive: true);
            }
            catch
            {
            }
        }

        private static string ReadString(
            System.Collections.Generic.IReadOnlyDictionary<string, JsonNode?> metadata,
            string key) => metadata[key]!.GetValue<string>();

        private static int ReadInt(
            System.Collections.Generic.IReadOnlyDictionary<string, JsonNode?> metadata,
            string key) => metadata[key]!.GetValue<int>();

        private static bool ReadBool(
            System.Collections.Generic.IReadOnlyDictionary<string, JsonNode?> metadata,
            string key) => metadata[key]!.GetValue<bool>();

        private static byte[] OneByOnePngBytes() => Convert.FromBase64String(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=");

        private static byte[] OneByOneWebpVp8xBytes() => new byte[]
        {
            0x52, 0x49, 0x46, 0x46,
            0x1E, 0x00, 0x00, 0x00,
            0x57, 0x45, 0x42, 0x50,
            0x56, 0x50, 0x38, 0x58,
            0x0A, 0x00, 0x00, 0x00,
            0x00,
            0x00, 0x00, 0x00,
            0x00, 0x00, 0x00,
            0x00, 0x00, 0x00,
        };
    }
}
