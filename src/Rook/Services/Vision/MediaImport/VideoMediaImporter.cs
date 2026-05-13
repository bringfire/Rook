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

        public async Task<MediaImportProcessResult> Import(
            string path,
            CancellationToken ct,
            Action<MediaImportItemState>? reportState = null)
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
                reportState?.Invoke(MediaImportItemState.Probing);
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

            long byteSize;
            try
            {
                byteSize = new FileInfo(path).Length;
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

            VideoImportSidecarResult sidecars;
            try
            {
                reportState?.Invoke(MediaImportItemState.ExtractingSidecars);
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
                var posterPath = sidecars.PosterPath;
                var startFramePath = sidecars.StartFramePath;
                var endFramePath = sidecars.EndFramePath;
                if (!sidecars.IsSuccess ||
                    string.IsNullOrWhiteSpace(posterPath) ||
                    string.IsNullOrWhiteSpace(startFramePath) ||
                    string.IsNullOrWhiteSpace(endFramePath))
                {
                    return MediaImportProcessResult.Failed(
                        MediaImportFailureCode.SidecarExtractionFailed,
                        "Could not extract required video sidecars.");
                }
                var posterSourcePath = posterPath!;
                var startFrameSourcePath = startFramePath!;
                var endFrameSourcePath = endFramePath!;

                var metadata = BuildMetadata(path, extension, probe, byteSize);
                reportState?.Invoke(MediaImportItemState.Publishing);
                var artifact = _store.CreateFromFiles(
                    MediaImportConstants.ImportedVideoKind,
                    new[]
                    {
                        new BlobFileInput(
                            VideoMediaRoles.Video,
                            path,
                            extension,
                            MaxBytes: MediaImportConstants.MaxVideoBytes,
                            ExpectedBytes: byteSize),
                        new BlobFileInput(VideoMediaRoles.Poster, posterSourcePath, "jpg"),
                        new BlobFileInput(VideoMediaRoles.StartFrame, startFrameSourcePath, "jpg"),
                        new BlobFileInput(VideoMediaRoles.EndFrame, endFrameSourcePath, "jpg"),
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
                var tempDirectory = sidecars.TempDirectory;
                if (!string.IsNullOrWhiteSpace(tempDirectory))
                    DefaultVideoImportSidecarExtractor.TryDeleteDirectory(tempDirectory!);
            }
        }

        private static bool IsSupportedExtension(string extension)
            => extension == "mp4" ||
               extension == "mov" ||
               extension == "webm";

        private static Dictionary<string, JsonNode?> BuildMetadata(
            string path,
            string extension,
            VideoImportProbeResult probe,
            long byteSize)
        {
            var metadata = new Dictionary<string, JsonNode?>
            {
                ["imported"] = true,
                ["import_source"] = "local_file",
                ["original_filename"] = Path.GetFileName(path),
                ["original_extension"] = extension,
                ["mime_type"] = MimeTypeForExtension(extension),
                ["byte_size"] = byteSize,
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
        private readonly Func<string?> _ffmpegPathProvider;
        private readonly Func<string, string, string, TimeSpan, CancellationToken, Task<FfmpegPosterExtractionResult>> _extractPosterAsync;
        private readonly Func<string, string, VideoFrameSelector, string, TimeSpan, CancellationToken, Task<FfmpegVideoFrameExtractionResult>> _extractFrameAsync;
        private readonly Func<IProcessRunner> _processRunnerFactory;
        private readonly string _tempRoot;

        public DefaultVideoImportSidecarExtractor()
            : this(
                FfmpegBundledBinaryLocator.GetInstalledFfmpegPath,
                () => new KillOnCancelProcessRunner(),
                Path.Combine(Path.GetTempPath(), "rook-media-import-sidecars"))
        {
        }

        internal DefaultVideoImportSidecarExtractor(
            Func<string?> ffmpegPathProvider,
            Func<IProcessRunner> processRunnerFactory,
            string tempRoot)
            : this(
                ffmpegPathProvider,
                (ffmpegPath, inputPath, outputPath, timeout, ct) => new FfmpegPosterFrameExtractor(processRunnerFactory())
                    .ExtractPosterAsync(ffmpegPath, inputPath, outputPath, timeout, ct),
                (ffmpegPath, inputPath, selector, outputPath, timeout, ct) => new FfmpegVideoFrameExtractor(processRunnerFactory())
                    .ExtractFrameAsync(ffmpegPath, inputPath, selector, outputPath, timeout, ct),
                tempRoot,
                processRunnerFactory)
        {
        }

        internal DefaultVideoImportSidecarExtractor(
            Func<string?> ffmpegPathProvider,
            Func<string, string, string, TimeSpan, CancellationToken, Task<FfmpegPosterExtractionResult>> extractPosterAsync,
            Func<string, string, VideoFrameSelector, string, TimeSpan, CancellationToken, Task<FfmpegVideoFrameExtractionResult>> extractFrameAsync,
            string tempRoot,
            Func<IProcessRunner>? processRunnerFactory = null)
        {
            _ffmpegPathProvider = ffmpegPathProvider ?? throw new ArgumentNullException(nameof(ffmpegPathProvider));
            _extractPosterAsync = extractPosterAsync ?? throw new ArgumentNullException(nameof(extractPosterAsync));
            _extractFrameAsync = extractFrameAsync ?? throw new ArgumentNullException(nameof(extractFrameAsync));
            _processRunnerFactory = processRunnerFactory ?? (() => new KillOnCancelProcessRunner());
            _tempRoot = string.IsNullOrWhiteSpace(tempRoot)
                ? throw new ArgumentException("Temp root must be non-empty.", nameof(tempRoot))
                : tempRoot;
        }

        internal IProcessRunner CreateProcessRunnerForTests()
            => _processRunnerFactory();

        public async Task<VideoImportSidecarResult> ExtractAsync(
            string path,
            VideoImportProbeResult probe,
            CancellationToken ct)
        {
            var resolution = FfmpegBinaryResolver.Resolve(bundledPath: _ffmpegPathProvider());
            var ffmpegPath = resolution.Path;
            if (!resolution.Success || string.IsNullOrWhiteSpace(ffmpegPath))
                return VideoImportSidecarResult.Failed("ffmpeg.exe was not available for sidecar extraction.");
            var resolvedFfmpegPath = ffmpegPath!;

            var tempDir = Path.Combine(
                _tempRoot,
                Guid.NewGuid().ToString("N"));
            var poster = Path.Combine(tempDir, "poster.jpg");
            var start = Path.Combine(tempDir, "start_frame.jpg");
            var end = Path.Combine(tempDir, "end_frame.jpg");

            try
            {
                Directory.CreateDirectory(tempDir);

                var posterResult = await _extractPosterAsync(resolvedFfmpegPath, path, poster, ExtractionTimeout, ct)
                    .ConfigureAwait(false);
                if (!posterResult.Success)
                {
                    TryDeleteDirectory(tempDir);
                    return VideoImportSidecarResult.Failed(posterResult.Message);
                }

                var startResult = await _extractFrameAsync(resolvedFfmpegPath, path, VideoFrameSelector.First, start, ExtractionTimeout, ct)
                    .ConfigureAwait(false);
                if (!startResult.Success)
                {
                    if (startResult.ErrorCode == FfmpegVideoFrameExtractionError.Cancelled)
                        throw new OperationCanceledException(startResult.Message);
                    TryDeleteDirectory(tempDir);
                    return VideoImportSidecarResult.Failed(startResult.Message);
                }

                var endResult = await _extractFrameAsync(resolvedFfmpegPath, path, VideoFrameSelector.Last, end, ExtractionTimeout, ct)
                    .ConfigureAwait(false);
                if (!endResult.Success)
                {
                    if (endResult.ErrorCode == FfmpegVideoFrameExtractionError.Cancelled)
                        throw new OperationCanceledException(endResult.Message);
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
