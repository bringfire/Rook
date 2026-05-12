using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Video.Extraction;

namespace Rook.Services.Vision.Video
{
    internal enum VideoPosterSidecarResultCode
    {
        Published,
        SkippedAlreadyExists,
        SkippedFfmpegMissing,
        TimedOut,
        ExtractionFailed,
        InvalidOutput,
        PublishFailed,
        VideoBlobUnavailable,
        TempPathUnavailable,
        PosterReadFailed,
        FinalizerFailed,
        CancelledAfterArtifactCreated,
    }

    internal sealed record VideoPosterSidecarResult
    {
        private const int MaxDiagnosticLength = 2048;

        private VideoPosterSidecarResult(
            VideoPosterSidecarResultCode code,
            Guid artifactId,
            string? message,
            string? diagnostic)
        {
            Code = code;
            ArtifactId = artifactId;
            Message = message;
            Diagnostic = TruncateDiagnostic(diagnostic);
        }

        public VideoPosterSidecarResultCode Code { get; }
        public Guid ArtifactId { get; }
        public string? Message { get; }
        public string? Diagnostic { get; }

        public bool Success =>
            Code == VideoPosterSidecarResultCode.Published
            || Code == VideoPosterSidecarResultCode.SkippedAlreadyExists;

        public static VideoPosterSidecarResult From(
            VideoPosterSidecarResultCode code,
            Guid artifactId,
            string? message = null,
            string? diagnostic = null)
            => new VideoPosterSidecarResult(code, artifactId, message, diagnostic);

        private static string? TruncateDiagnostic(string? diagnostic)
        {
            if (diagnostic is null || diagnostic.Length <= MaxDiagnosticLength)
                return diagnostic;

            return diagnostic.Substring(0, MaxDiagnosticLength);
        }
    }

    internal interface IVideoPosterSidecarProducer
    {
        Task<VideoPosterSidecarResult> TryPublishPosterAsync(
            Guid artifactId,
            CancellationToken cancellationToken);
    }

    internal interface IVideoPosterFfmpegResolver
    {
        FfmpegBinaryResolution Resolve();
    }

    internal interface IVideoPosterExtractor
    {
        Task<FfmpegPosterExtractionResult> ExtractPosterAsync(
            string ffmpegPath,
            string inputPath,
            string outputPath,
            TimeSpan timeout,
            CancellationToken cancellationToken);
    }

    internal interface IVideoPosterTempFiles
    {
        string CreatePosterTempPath(Guid artifactId);
        void TryDelete(string path);
    }

    internal interface IVideoPosterByteReader
    {
        byte[] ReadAllBytes(string path);
    }

    internal interface IVideoPosterSidecarPublisher
    {
        VideoSidecarPublishResult Publish(
            Guid artifactId,
            string role,
            byte[] content,
            string fileExtension);
    }

    internal sealed class VideoPosterSidecarProducer : IVideoPosterSidecarProducer
    {
        private static readonly TimeSpan DefaultExtractionTimeout = TimeSpan.FromSeconds(30);
        private const int MaxDiagnosticLength = 2048;

        private readonly ArtifactStore _store;
        private readonly IVideoPosterSidecarPublisher _publisher;
        private readonly IVideoPosterFfmpegResolver _ffmpegResolver;
        private readonly IVideoPosterExtractor _extractor;
        private readonly IVideoPosterTempFiles _tempFiles;
        private readonly IVideoPosterByteReader _byteReader;

        public VideoPosterSidecarProducer(ArtifactStore store)
            : this(
                store,
                new DefaultVideoPosterFfmpegResolver(),
                new DefaultVideoPosterExtractor(),
                new DefaultVideoPosterTempFiles(),
                new DefaultVideoPosterByteReader())
        {
        }

        internal VideoPosterSidecarProducer(
            ArtifactStore store,
            IVideoPosterFfmpegResolver ffmpegResolver,
            IVideoPosterExtractor extractor,
            IVideoPosterTempFiles tempFiles,
            IVideoPosterByteReader byteReader,
            IVideoPosterSidecarPublisher? publisher = null)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
            _publisher = publisher ?? new DefaultVideoPosterSidecarPublisher(_store);
            _ffmpegResolver = ffmpegResolver ?? throw new ArgumentNullException(nameof(ffmpegResolver));
            _extractor = extractor ?? throw new ArgumentNullException(nameof(extractor));
            _tempFiles = tempFiles ?? throw new ArgumentNullException(nameof(tempFiles));
            _byteReader = byteReader ?? throw new ArgumentNullException(nameof(byteReader));
        }

        public async Task<VideoPosterSidecarResult> TryPublishPosterAsync(
            Guid artifactId,
            CancellationToken cancellationToken)
        {
            string videoPath;
            try
            {
                videoPath = _store.GetBlobAbsolutePath(artifactId, VideoMediaRoles.Video);
            }
            catch (Exception ex)
            {
                return VideoPosterSidecarResult.From(
                    VideoPosterSidecarResultCode.VideoBlobUnavailable,
                    artifactId,
                    ex.Message,
                    ex.ToString());
            }

            string? posterPath = null;
            try
            {
                var ffmpeg = _ffmpegResolver.Resolve();
                if (!ffmpeg.Success || string.IsNullOrWhiteSpace(ffmpeg.Path))
                {
                    return VideoPosterSidecarResult.From(
                        VideoPosterSidecarResultCode.SkippedFfmpegMissing,
                        artifactId,
                        ffmpeg.Message,
                        ffmpeg.ErrorCode?.ToString());
                }

                var ffmpegPath = ffmpeg.Path!;
                try
                {
                    posterPath = _tempFiles.CreatePosterTempPath(artifactId);
                }
                catch (Exception ex)
                {
                    return VideoPosterSidecarResult.From(
                        VideoPosterSidecarResultCode.TempPathUnavailable,
                        artifactId,
                        ex.Message,
                        ex.ToString());
                }

                cancellationToken.ThrowIfCancellationRequested();

                var extraction = await _extractor.ExtractPosterAsync(
                        ffmpegPath,
                        videoPath,
                        posterPath,
                        DefaultExtractionTimeout,
                        cancellationToken)
                    .ConfigureAwait(false);

                if (!extraction.Success)
                {
                    var code = MapExtractionFailure(extraction.ErrorCode);

                    return CleanupAndReturn(
                        posterPath,
                        VideoPosterSidecarResult.From(
                            code,
                            artifactId,
                            extraction.Message,
                            extraction.Stderr));
                }

                byte[] posterBytes;
                try
                {
                    posterBytes = _byteReader.ReadAllBytes(posterPath);
                }
                catch (Exception ex) when (!(ex is OperationCanceledException))
                {
                    return CleanupAndReturn(
                        posterPath,
                        VideoPosterSidecarResult.From(
                            VideoPosterSidecarResultCode.PosterReadFailed,
                            artifactId,
                            ex.Message,
                            ex.ToString()));
                }

                var publish = _publisher.Publish(
                    artifactId,
                    VideoMediaRoles.Poster,
                    posterBytes,
                    "jpg");

                var result = publish.Code switch
                {
                    VideoSidecarPublishResultCode.Succeeded =>
                        VideoPosterSidecarResult.From(
                            VideoPosterSidecarResultCode.Published,
                            artifactId,
                            publish.Message),

                    VideoSidecarPublishResultCode.SkippedAlreadyExists =>
                        VideoPosterSidecarResult.From(
                            VideoPosterSidecarResultCode.SkippedAlreadyExists,
                            artifactId,
                            publish.Message),

                    _ =>
                        VideoPosterSidecarResult.From(
                            VideoPosterSidecarResultCode.PublishFailed,
                            artifactId,
                            publish.Message,
                            publish.Code.ToString()),
                };

                return CleanupAndReturn(posterPath, result);
            }
            catch (OperationCanceledException ex)
            {
                return CleanupAndReturn(
                    posterPath,
                    VideoPosterSidecarResult.From(
                        VideoPosterSidecarResultCode.CancelledAfterArtifactCreated,
                        artifactId,
                        ex.Message,
                        ex.ToString()));
            }
            catch (Exception ex)
            {
                return CleanupAndReturn(
                    posterPath,
                    VideoPosterSidecarResult.From(
                        VideoPosterSidecarResultCode.FinalizerFailed,
                        artifactId,
                        ex.Message,
                        ex.ToString()));
            }
        }

        private VideoPosterSidecarResult CleanupAndReturn(
            string? tempPath,
            VideoPosterSidecarResult result)
        {
            if (tempPath is null || tempPath.Trim().Length == 0)
                return result;

            string path = tempPath;
            try
            {
                _tempFiles.TryDelete(path);
                return result;
            }
            catch (Exception ex)
            {
                return VideoPosterSidecarResult.From(
                    result.Code,
                    result.ArtifactId,
                    result.Message,
                    AppendDiagnostic(result.Diagnostic, $"Cleanup failed: {ex}"));
            }
        }

        private static VideoPosterSidecarResultCode MapExtractionFailure(
            FfmpegPosterExtractionError? error)
            => error switch
            {
                FfmpegPosterExtractionError.TimedOut => VideoPosterSidecarResultCode.TimedOut,
                FfmpegPosterExtractionError.InvalidOutputImage => VideoPosterSidecarResultCode.InvalidOutput,
                _ => VideoPosterSidecarResultCode.ExtractionFailed,
            };

        private static string AppendDiagnostic(string? diagnostic, string cleanupDiagnostic)
        {
            if (diagnostic is null || diagnostic.Trim().Length == 0)
                return Truncate(cleanupDiagnostic);

            string primaryDiagnostic = diagnostic;
            var separator = Environment.NewLine;
            var combined = primaryDiagnostic + separator + cleanupDiagnostic;
            if (combined.Length <= MaxDiagnosticLength)
                return combined;

            var cleanupSuffix = separator + cleanupDiagnostic;
            if (cleanupSuffix.Length >= MaxDiagnosticLength)
                return Truncate(cleanupSuffix);

            var primaryLength = MaxDiagnosticLength - cleanupSuffix.Length;
            return primaryDiagnostic.Substring(0, primaryLength) + cleanupSuffix;
        }

        private static string Truncate(string value)
            => value.Length <= MaxDiagnosticLength
                ? value
                : value.Substring(0, MaxDiagnosticLength);
    }

    internal sealed class DefaultVideoPosterFfmpegResolver : IVideoPosterFfmpegResolver
    {
        public FfmpegBinaryResolution Resolve()
            => FfmpegBinaryResolver.Resolve(
                bundledPath: FfmpegBundledBinaryLocator.GetInstalledFfmpegPath());
    }

    internal sealed class DefaultVideoPosterExtractor : IVideoPosterExtractor
    {
        private readonly FfmpegPosterFrameExtractor _extractor = new FfmpegPosterFrameExtractor();

        public Task<FfmpegPosterExtractionResult> ExtractPosterAsync(
            string ffmpegPath,
            string inputPath,
            string outputPath,
            TimeSpan timeout,
            CancellationToken cancellationToken)
            => _extractor.ExtractPosterAsync(
                ffmpegPath,
                inputPath,
                outputPath,
                timeout,
                cancellationToken);
    }

    internal sealed class DefaultVideoPosterTempFiles : IVideoPosterTempFiles
    {
        public string CreatePosterTempPath(Guid artifactId)
        {
            var directory = Path.Combine(Path.GetTempPath(), "rook-video-posters");
            Directory.CreateDirectory(directory);
            return Path.Combine(directory, $"{artifactId:N}-{Guid.NewGuid():N}.jpg");
        }

        public void TryDelete(string path)
        {
            if (!string.IsNullOrWhiteSpace(path) && File.Exists(path))
                File.Delete(path);
        }
    }

    internal sealed class DefaultVideoPosterByteReader : IVideoPosterByteReader
    {
        public byte[] ReadAllBytes(string path) => File.ReadAllBytes(path);
    }

    internal sealed class DefaultVideoPosterSidecarPublisher : IVideoPosterSidecarPublisher
    {
        private readonly VideoSidecarPublisher _publisher;

        public DefaultVideoPosterSidecarPublisher(ArtifactStore store)
        {
            _publisher = new VideoSidecarPublisher(store);
        }

        public VideoSidecarPublishResult Publish(
            Guid artifactId,
            string role,
            byte[] content,
            string fileExtension)
            => _publisher.Publish(artifactId, role, content, fileExtension);
    }
}
