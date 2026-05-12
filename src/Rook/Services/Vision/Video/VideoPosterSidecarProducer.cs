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

    internal sealed class VideoPosterSidecarProducer : IVideoPosterSidecarProducer
    {
        private static readonly TimeSpan DefaultExtractionTimeout = TimeSpan.FromSeconds(30);

        private readonly ArtifactStore _store;
        private readonly VideoSidecarPublisher _publisher;
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
            IVideoPosterByteReader byteReader)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
            _publisher = new VideoSidecarPublisher(_store);
            _ffmpegResolver = ffmpegResolver ?? throw new ArgumentNullException(nameof(ffmpegResolver));
            _extractor = extractor ?? throw new ArgumentNullException(nameof(extractor));
            _tempFiles = tempFiles ?? throw new ArgumentNullException(nameof(tempFiles));
            _byteReader = byteReader ?? throw new ArgumentNullException(nameof(byteReader));
        }

        public async Task<VideoPosterSidecarResult> TryPublishPosterAsync(
            Guid artifactId,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();

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
            string posterPath;
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

            try
            {
                var extraction = await _extractor.ExtractPosterAsync(
                        ffmpegPath,
                        videoPath,
                        posterPath,
                        DefaultExtractionTimeout,
                        cancellationToken)
                    .ConfigureAwait(false);

                if (!extraction.Success)
                {
                    var code = extraction.ErrorCode == FfmpegPosterExtractionError.TimedOut
                        ? VideoPosterSidecarResultCode.TimedOut
                        : VideoPosterSidecarResultCode.ExtractionFailed;

                    return VideoPosterSidecarResult.From(
                        code,
                        artifactId,
                        extraction.Message,
                        extraction.Stderr);
                }

                byte[] posterBytes;
                try
                {
                    posterBytes = _byteReader.ReadAllBytes(posterPath);
                }
                catch (Exception ex)
                {
                    return VideoPosterSidecarResult.From(
                        VideoPosterSidecarResultCode.PosterReadFailed,
                        artifactId,
                        ex.Message,
                        ex.ToString());
                }

                var publish = _publisher.Publish(
                    artifactId,
                    VideoMediaRoles.Poster,
                    posterBytes,
                    "jpg");

                return publish.Code switch
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
            }
            finally
            {
                _tempFiles.TryDelete(posterPath);
            }
        }
    }

    internal sealed class DefaultVideoPosterFfmpegResolver : IVideoPosterFfmpegResolver
    {
        public FfmpegBinaryResolution Resolve() => FfmpegBinaryResolver.Resolve();
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
            try
            {
                if (!string.IsNullOrWhiteSpace(path) && File.Exists(path))
                    File.Delete(path);
            }
            catch
            {
                // Best-effort cleanup; Task 2 will harden finalizer failure mapping.
            }
        }
    }

    internal sealed class DefaultVideoPosterByteReader : IVideoPosterByteReader
    {
        public byte[] ReadAllBytes(string path) => File.ReadAllBytes(path);
    }
}
