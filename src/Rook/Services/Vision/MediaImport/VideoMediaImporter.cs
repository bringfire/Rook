using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Extraction;

namespace Rook.Services.Vision.MediaImport
{
    internal interface IVideoImportSidecarExtractor
    {
        Task<VideoImportSidecarResult> ExtractAsync(
            string path,
            VideoImportProbeResult probe,
            CancellationToken ct);
    }

    internal sealed record VideoImportSidecarResult(
        bool IsSuccess,
        string? PosterPath,
        string? StartFramePath,
        string? EndFramePath,
        string? TempDirectory,
        string? Message)
    {
        public static VideoImportSidecarResult Success(
            string posterPath,
            string startFramePath,
            string endFramePath,
            string tempDirectory) =>
            new(true, posterPath, startFramePath, endFramePath, tempDirectory, null);

        public static VideoImportSidecarResult Failed(string message) =>
            new(false, null, null, null, null, message);
    }

    public sealed class VideoMediaImporter
    {
        private readonly ArtifactStore _store;
        private readonly IVideoImportProbe _probe;
        private readonly IVideoImportSidecarExtractor _sidecarExtractor;

        public VideoMediaImporter(ArtifactStore store)
            : this(store, new FfmpegVideoProbe(), new DefaultVideoImportSidecarExtractor())
        {
        }

        internal VideoMediaImporter(
            ArtifactStore store,
            IVideoImportProbe probe,
            IVideoImportSidecarExtractor sidecarExtractor)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
            _probe = probe ?? throw new ArgumentNullException(nameof(probe));
            _sidecarExtractor = sidecarExtractor ?? throw new ArgumentNullException(nameof(sidecarExtractor));
        }

        public async Task<MediaImportProcessResult> Import(string path, CancellationToken ct)
        {
            var validationFailure = ImageMediaImporter.ValidatePath(path, MediaImportConstants.MaxVideoBytes);
            if (validationFailure is not null)
                return validationFailure;

            var extension = Path.GetExtension(path).TrimStart('.').ToLowerInvariant();
            if (!IsSupportedExtension(extension))
            {
                return MediaImportProcessResult.Failed(
                    MediaImportFailureCode.UnsupportedMediaType,
                    $"Video extension '.{extension}' is not supported.");
            }

            VideoImportProbeResult probe;
            try
            {
                probe = await _probe.ProbeAsync(path, ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch
            {
                return MediaImportProcessResult.Failed(
                    MediaImportFailureCode.VideoProbeFailed,
                    "Could not probe video metadata.");
            }

            if (!probe.IsSuccess)
            {
                return MediaImportProcessResult.Failed(
                    MediaImportFailureCode.VideoProbeFailed,
                    "Could not probe video metadata.");
            }

            VideoImportSidecarResult sidecars;
            try
            {
                sidecars = await _sidecarExtractor.ExtractAsync(path, probe, ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch
            {
                return MediaImportProcessResult.Failed(
                    MediaImportFailureCode.SidecarExtractionFailed,
                    "Could not extract required video sidecars.");
            }

            try
            {
                if (!sidecars.IsSuccess ||
                    string.IsNullOrWhiteSpace(sidecars.PosterPath) ||
                    string.IsNullOrWhiteSpace(sidecars.StartFramePath) ||
                    string.IsNullOrWhiteSpace(sidecars.EndFramePath))
                {
                    return MediaImportProcessResult.Failed(
                        MediaImportFailureCode.SidecarExtractionFailed,
                        "Could not extract required video sidecars.");
                }

                var metadata = BuildMetadata(path, extension, probe);
                var artifact = _store.CreateFromFiles(
                    MediaImportConstants.ImportedVideoKind,
                    new[]
                    {
                        new BlobFileInput(VideoMediaRoles.Video, path, extension),
                        new BlobFileInput(VideoMediaRoles.Poster, sidecars.PosterPath, "jpg"),
                        new BlobFileInput(VideoMediaRoles.StartFrame, sidecars.StartFramePath, "jpg"),
                        new BlobFileInput(VideoMediaRoles.EndFrame, sidecars.EndFramePath, "jpg"),
                    },
                    metadata: metadata);

                return MediaImportProcessResult.Success(artifact.Id, artifact.Kind);
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                return ImageMediaImporter.MapPublishException(MediaImportConstants.ImportedVideoKind, ex);
            }
            finally
            {
                if (!string.IsNullOrWhiteSpace(sidecars.TempDirectory))
                    DefaultVideoImportSidecarExtractor.TryDeleteDirectory(sidecars.TempDirectory);
            }
        }

        private static bool IsSupportedExtension(string extension)
            => extension == "mp4" ||
               extension == "mov" ||
               extension == "webm";

        private static Dictionary<string, JsonNode?> BuildMetadata(
            string path,
            string extension,
            VideoImportProbeResult probe)
        {
            var metadata = new Dictionary<string, JsonNode?>
            {
                ["imported"] = true,
                ["import_source"] = "local_file",
                ["original_filename"] = Path.GetFileName(path),
                ["original_extension"] = extension,
                ["mime_type"] = MimeTypeForExtension(extension),
                ["byte_size"] = new FileInfo(path).Length,
                ["imported_at"] = DateTimeOffset.UtcNow.ToString("O", CultureInfo.InvariantCulture),
                ["duration_seconds"] = probe.DurationSeconds,
                ["width"] = probe.Width,
                ["height"] = probe.Height,
                ["poster_timestamp_seconds"] = 0.1,
                ["start_frame_timestamp_seconds"] = 0,
                ["end_frame_timestamp_seconds"] = probe.DurationSeconds,
                ["sidecars"] = new JsonObject
                {
                    ["poster"] = "ok",
                    ["start_frame"] = "ok",
                    ["end_frame"] = "ok",
                },
            };

            if (probe.FrameRate.HasValue)
                metadata["frame_rate"] = probe.FrameRate.Value;

            return metadata;
        }

        private static string MimeTypeForExtension(string extension)
        {
            switch (extension)
            {
                case "mp4":
                    return "video/mp4";
                case "mov":
                    return "video/quicktime";
                case "webm":
                    return "video/webm";
                default:
                    return "application/octet-stream";
            }
        }
    }

    internal sealed class DefaultVideoImportSidecarExtractor : IVideoImportSidecarExtractor
    {
        private static readonly TimeSpan ExtractionTimeout = TimeSpan.FromSeconds(60);

        public async Task<VideoImportSidecarResult> ExtractAsync(
            string path,
            VideoImportProbeResult probe,
            CancellationToken ct)
        {
            var resolution = FfmpegBinaryResolver.Resolve(FfmpegBundledBinaryLocator.GetInstalledFfmpegPath());
            if (!resolution.Success || string.IsNullOrWhiteSpace(resolution.Path))
                return VideoImportSidecarResult.Failed("ffmpeg.exe was not available for sidecar extraction.");

            var tempDir = Path.Combine(
                Path.GetTempPath(),
                "rook-media-import-sidecars",
                Guid.NewGuid().ToString("N"));
            var poster = Path.Combine(tempDir, "poster.jpg");
            var start = Path.Combine(tempDir, "start_frame.jpg");
            var end = Path.Combine(tempDir, "end_frame.jpg");

            try
            {
                Directory.CreateDirectory(tempDir);

                var posterResult = await new FfmpegPosterFrameExtractor()
                    .ExtractPosterAsync(resolution.Path, path, poster, ExtractionTimeout, ct)
                    .ConfigureAwait(false);
                if (!posterResult.Success)
                {
                    TryDeleteDirectory(tempDir);
                    return VideoImportSidecarResult.Failed(posterResult.Message);
                }

                var frameExtractor = new FfmpegVideoFrameExtractor();
                var startResult = await frameExtractor
                    .ExtractFrameAsync(resolution.Path, path, VideoFrameSelector.First, start, ExtractionTimeout, ct)
                    .ConfigureAwait(false);
                if (!startResult.Success)
                {
                    TryDeleteDirectory(tempDir);
                    return VideoImportSidecarResult.Failed(startResult.Message);
                }

                var endResult = await frameExtractor
                    .ExtractFrameAsync(resolution.Path, path, VideoFrameSelector.Last, end, ExtractionTimeout, ct)
                    .ConfigureAwait(false);
                if (!endResult.Success)
                {
                    TryDeleteDirectory(tempDir);
                    return VideoImportSidecarResult.Failed(endResult.Message);
                }

                return VideoImportSidecarResult.Success(poster, start, end, tempDir);
            }
            catch
            {
                TryDeleteDirectory(tempDir);
                throw;
            }
        }

        internal static void TryDeleteDirectory(string path)
        {
            try
            {
                if (Directory.Exists(path))
                    Directory.Delete(path, recursive: true);
            }
            catch
            {
            }
        }
    }
}
