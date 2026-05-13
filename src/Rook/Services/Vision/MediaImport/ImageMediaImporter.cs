using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.Json.Nodes;
using Rook.Artifacts;
using Rook.Services.Vision.Image;

namespace Rook.Services.Vision.MediaImport
{
    public sealed class ImageMediaImporter
    {
        private readonly ArtifactStore _store;

        public ImageMediaImporter(ArtifactStore store)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
        }

        public MediaImportProcessResult Import(string path)
        {
            var validationFailure = ValidatePath(path, MediaImportConstants.MaxImageBytes);
            if (validationFailure is not null)
                return validationFailure;

            var extension = Path.GetExtension(path).TrimStart('.').ToLowerInvariant();
            if (!IsSupportedExtension(extension))
            {
                return MediaImportProcessResult.Failed(
                    MediaImportFailureCode.UnsupportedMediaType,
                    $"Image extension '.{extension}' is not supported.");
            }

            ImageDimensions dimensions;
            try
            {
                dimensions = ProbeDimensions(path, extension);
            }
            catch (Exception ex) when (
                ex is ArgumentException ||
                ex is InvalidDataException ||
                ex is IOException ||
                ex is OutOfMemoryException)
            {
                return MediaImportProcessResult.Failed(
                    MediaImportFailureCode.DecodeFailed,
                    "Could not decode image dimensions.");
            }

            Dictionary<string, JsonNode?> metadata;
            try
            {
                metadata = BuildMetadata(path, extension, dimensions);
            }
            catch (Exception ex) when (
                ex is FileNotFoundException ||
                ex is DirectoryNotFoundException)
            {
                return MediaImportProcessResult.Failed(
                    MediaImportFailureCode.FileNotFound,
                    "Source file was not found during import.");
            }
            catch (Exception ex) when (
                ex is UnauthorizedAccessException ||
                ex is IOException)
            {
                return MediaImportProcessResult.Failed(
                    MediaImportFailureCode.FileInaccessible,
                    "Source file became inaccessible during import.");
            }

            try
            {
                var artifact = _store.CreateFromFiles(
                    MediaImportConstants.ImportedImageKind,
                    new[] { new BlobFileInput(ImageMediaRoles.Image, path, extension) },
                    metadata: metadata);

                return MediaImportProcessResult.Success(artifact.Id, artifact.Kind);
            }
            catch (Exception ex)
            {
                return MapPublishException(MediaImportConstants.ImportedImageKind, ex);
            }
        }

        internal static MediaImportProcessResult MapPublishException(string mediaKind, Exception ex)
        {
            var code = ex is ArtifactBlobCopyException
                ? MediaImportFailureCode.CopyFailed
                : MediaImportFailureCode.PublishFailed;

            return new MediaImportProcessResult(
                IsSuccess: false,
                ArtifactId: null,
                ArtifactKind: mediaKind,
                FailureCode: code,
                Message: PublishFailureMessage(code));
        }

        internal static MediaImportProcessResult? ValidatePath(string path, long maxBytes)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                return MediaImportProcessResult.Failed(
                    MediaImportFailureCode.FileNotFound,
                    "Source file was not found.");
            }

            FileAttributes attributes;
            try
            {
                attributes = File.GetAttributes(path);
            }
            catch (Exception ex) when (
                ex is FileNotFoundException ||
                ex is DirectoryNotFoundException)
            {
                return MediaImportProcessResult.Failed(
                    MediaImportFailureCode.FileNotFound,
                    $"Source file '{Path.GetFileName(path)}' was not found.");
            }
            catch (Exception ex) when (
                ex is UnauthorizedAccessException ||
                ex is IOException)
            {
                return MediaImportProcessResult.Failed(
                    MediaImportFailureCode.FileInaccessible,
                    "Source file could not be accessed.");
            }

            if ((attributes & FileAttributes.Directory) == FileAttributes.Directory)
            {
                return MediaImportProcessResult.Failed(
                    MediaImportFailureCode.NotRegularFile,
                    "Source path must be a regular file.");
            }

            try
            {
                var length = new FileInfo(path).Length;
                if (length > maxBytes)
                {
                    return MediaImportProcessResult.Failed(
                        MediaImportFailureCode.FileTooLarge,
                        $"Source file exceeds the {maxBytes.ToString(CultureInfo.InvariantCulture)} byte limit.");
                }
            }
            catch (Exception ex) when (
                ex is UnauthorizedAccessException ||
                ex is IOException)
            {
                return MediaImportProcessResult.Failed(
                    MediaImportFailureCode.FileInaccessible,
                    "Source file could not be accessed.");
            }

            return null;
        }

        private static bool IsSupportedExtension(string extension)
            => extension == "png" ||
               extension == "jpg" ||
               extension == "jpeg" ||
               extension == "webp";

        private static ImageDimensions ProbeDimensions(string path, string extension)
        {
            if (extension == "webp")
                return ProbeWebpDimensions(path);

            using var image = System.Drawing.Image.FromFile(path);
            return new ImageDimensions(image.Width, image.Height);
        }

        private static Dictionary<string, JsonNode?> BuildMetadata(
            string path,
            string extension,
            ImageDimensions dimensions)
        {
            return new Dictionary<string, JsonNode?>
            {
                ["imported"] = true,
                ["import_source"] = "local_file",
                ["original_filename"] = Path.GetFileName(path),
                ["original_extension"] = extension,
                ["mime_type"] = MimeTypeForExtension(extension),
                ["byte_size"] = GetFileLength(path),
                ["imported_at"] = DateTimeOffset.UtcNow.ToString("O", CultureInfo.InvariantCulture),
                ["width"] = dimensions.Width,
                ["height"] = dimensions.Height,
                ["normalized"] = false,
            };
        }

        private static string MimeTypeForExtension(string extension)
        {
            switch (extension)
            {
                case "png":
                    return "image/png";
                case "jpg":
                case "jpeg":
                    return "image/jpeg";
                case "webp":
                    return "image/webp";
                default:
                    return "application/octet-stream";
            }
        }

        private static long GetFileLength(string path)
        {
            try
            {
                return new FileInfo(path).Length;
            }
            catch (Exception ex) when (
                ex is FileNotFoundException ||
                ex is DirectoryNotFoundException)
            {
                throw new FileNotFoundException("Source file was not found during import.", Path.GetFileName(path), ex);
            }
            catch (Exception ex) when (
                ex is UnauthorizedAccessException ||
                ex is IOException)
            {
                throw new IOException("Source file became inaccessible during import.", ex);
            }
        }

        private static string PublishFailureMessage(MediaImportFailureCode code)
        {
            switch (code)
            {
                case MediaImportFailureCode.CopyFailed:
                    return "Artifact blob copy failed.";
                default:
                    return "Artifact publish failed.";
            }
        }

        private static ImageDimensions ProbeWebpDimensions(string path)
        {
            using var stream = File.OpenRead(path);
            using var reader = new BinaryReader(stream);

            if (stream.Length < 20 ||
                ReadAscii(reader, 4) != "RIFF")
            {
                throw new InvalidDataException("WebP file is missing RIFF header.");
            }

            _ = reader.ReadUInt32();
            if (ReadAscii(reader, 4) != "WEBP")
                throw new InvalidDataException("WebP file is missing WEBP signature.");

            while (stream.Position + 8 <= stream.Length)
            {
                var chunkType = ReadAscii(reader, 4);
                var chunkSize = reader.ReadUInt32();
                var chunkStart = stream.Position;
                if (chunkStart + chunkSize > stream.Length)
                    throw new InvalidDataException("WebP chunk extends past end of file.");

                switch (chunkType)
                {
                    case "VP8X":
                        if (chunkSize < 10)
                            throw new InvalidDataException("WebP VP8X chunk is too small.");
                        _ = reader.ReadByte();
                        _ = reader.ReadBytes(3);
                        var vp8xWidth = 1 + ReadUInt24(reader);
                        var vp8xHeight = 1 + ReadUInt24(reader);
                        return new ImageDimensions(vp8xWidth, vp8xHeight);

                    case "VP8L":
                        if (chunkSize < 5)
                            throw new InvalidDataException("WebP VP8L chunk is too small.");
                        if (reader.ReadByte() != 0x2F)
                            throw new InvalidDataException("WebP VP8L signature is invalid.");
                        var bits = reader.ReadUInt32();
                        var vp8lWidth = (int)(bits & 0x3FFF) + 1;
                        var vp8lHeight = (int)((bits >> 14) & 0x3FFF) + 1;
                        return new ImageDimensions(vp8lWidth, vp8lHeight);

                    case "VP8 ":
                        if (chunkSize < 10)
                            throw new InvalidDataException("WebP VP8 chunk is too small.");
                        _ = reader.ReadBytes(3);
                        if (reader.ReadByte() != 0x9D ||
                            reader.ReadByte() != 0x01 ||
                            reader.ReadByte() != 0x2A)
                        {
                            throw new InvalidDataException("WebP VP8 start code is invalid.");
                        }
                        var vp8Width = reader.ReadUInt16() & 0x3FFF;
                        var vp8Height = reader.ReadUInt16() & 0x3FFF;
                        return new ImageDimensions(vp8Width, vp8Height);
                }

                stream.Position = chunkStart + chunkSize + (chunkSize % 2);
            }

            throw new InvalidDataException("WebP file has no supported image chunk.");
        }

        private static int ReadUInt24(BinaryReader reader)
        {
            var b0 = reader.ReadByte();
            var b1 = reader.ReadByte();
            var b2 = reader.ReadByte();
            return b0 | (b1 << 8) | (b2 << 16);
        }

        private static string ReadAscii(BinaryReader reader, int length)
            => System.Text.Encoding.ASCII.GetString(reader.ReadBytes(length));

        private readonly struct ImageDimensions
        {
            public ImageDimensions(int width, int height)
            {
                Width = width;
                Height = height;
            }

            public int Width { get; }
            public int Height { get; }
        }
    }
}
