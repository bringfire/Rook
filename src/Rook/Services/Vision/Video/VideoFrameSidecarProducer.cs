using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Video.Extraction;

namespace Rook.Services.Vision.Video
{
    internal enum VideoFrameSidecarRoleResultCode
    {
        Published,
        SkippedAlreadyExists,
        FfmpegMissing,
        ExtractionTimedOut,
        ExtractionFailed,
        InvalidOutput,
        VideoBlobUnavailable,
        TempPathUnavailable,
        FrameReadFailed,
        PublishFailed,
        CancelledAfterArtifactCreated,
        FinalizerFailed,
    }

    internal sealed record VideoFrameSidecarRoleResult
    {
        private const int MaxDiagnosticLength = 2048;

        private VideoFrameSidecarRoleResult(
            string role,
            VideoFrameSelector selector,
            VideoFrameSidecarRoleResultCode code,
            string? message,
            string? diagnostic)
        {
            Role = role ?? throw new ArgumentNullException(nameof(role));
            Selector = selector;
            Code = code;
            Message = message;
            Diagnostic = TruncateDiagnostic(diagnostic);
        }

        public string Role { get; }
        public VideoFrameSelector Selector { get; }
        public VideoFrameSidecarRoleResultCode Code { get; }
        public string? Message { get; }
        public string? Diagnostic { get; }

        public bool Success =>
            Code == VideoFrameSidecarRoleResultCode.Published
            || Code == VideoFrameSidecarRoleResultCode.SkippedAlreadyExists;

        public static VideoFrameSidecarRoleResult From(
            string role,
            VideoFrameSelector selector,
            VideoFrameSidecarRoleResultCode code,
            string? message = null,
            string? diagnostic = null)
            => new VideoFrameSidecarRoleResult(role, selector, code, message, diagnostic);

        private static string? TruncateDiagnostic(string? diagnostic)
        {
            if (diagnostic is null || diagnostic.Length <= MaxDiagnosticLength)
                return diagnostic;

            return diagnostic.Substring(0, MaxDiagnosticLength);
        }
    }

    internal sealed record VideoFrameSidecarResult(
        Guid ArtifactId,
        IReadOnlyList<VideoFrameSidecarRoleResult> RoleResults);

    internal interface IVideoFrameSidecarProducer
    {
        Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
            Guid artifactId,
            CancellationToken cancellationToken);
    }

    internal interface IVideoFrameFfmpegResolver
    {
        FfmpegBinaryResolution Resolve();
    }

    internal interface IVideoFrameExtractor
    {
        Task<FfmpegVideoFrameExtractionResult> ExtractFrameAsync(
            string ffmpegPath,
            string inputPath,
            VideoFrameSelector selector,
            string outputPath,
            TimeSpan timeout,
            CancellationToken cancellationToken);
    }

    internal interface IVideoFrameTempFiles
    {
        string CreateFrameTempPath(Guid artifactId, string role);
        void TryDelete(string path);
    }

    internal interface IVideoFrameByteReader
    {
        byte[] ReadAllBytes(string path);
    }

    internal interface IVideoFrameSidecarPublisher
    {
        VideoSidecarPublishResult Publish(
            Guid artifactId,
            string role,
            byte[] content,
            string fileExtension);
    }

    internal sealed class VideoFrameSidecarProducer : IVideoFrameSidecarProducer
    {
        private static readonly TimeSpan DefaultExtractionTimeout = TimeSpan.FromSeconds(30);
        private const int MaxDiagnosticLength = 2048;

        private readonly ArtifactStore _store;
        private readonly IVideoFrameFfmpegResolver _ffmpegResolver;
        private readonly IVideoFrameExtractor _extractor;
        private readonly IVideoFrameTempFiles _tempFiles;
        private readonly IVideoFrameByteReader _byteReader;
        private readonly IVideoFrameSidecarPublisher _publisher;

        public VideoFrameSidecarProducer(ArtifactStore store)
            : this(
                store,
                new DefaultVideoFrameFfmpegResolver(),
                new DefaultVideoFrameExtractor(),
                new DefaultVideoFrameTempFiles(),
                new DefaultVideoFrameByteReader())
        {
        }

        internal VideoFrameSidecarProducer(
            ArtifactStore store,
            IVideoFrameFfmpegResolver ffmpegResolver,
            IVideoFrameExtractor extractor,
            IVideoFrameTempFiles tempFiles,
            IVideoFrameByteReader byteReader,
            IVideoFrameSidecarPublisher? publisher = null)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
            _ffmpegResolver = ffmpegResolver ?? throw new ArgumentNullException(nameof(ffmpegResolver));
            _extractor = extractor ?? throw new ArgumentNullException(nameof(extractor));
            _tempFiles = tempFiles ?? throw new ArgumentNullException(nameof(tempFiles));
            _byteReader = byteReader ?? throw new ArgumentNullException(nameof(byteReader));
            _publisher = publisher ?? new DefaultVideoFrameSidecarPublisher(_store);
        }

        public async Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
            Guid artifactId,
            CancellationToken cancellationToken)
        {
            var rolePlans = CreateRolePlans();

            string videoPath;
            try
            {
                videoPath = _store.GetBlobAbsolutePath(artifactId, VideoMediaRoles.Video);
            }
            catch (Exception ex)
            {
                return new VideoFrameSidecarResult(
                    artifactId,
                    ResultsForAll(
                        rolePlans,
                        VideoFrameSidecarRoleResultCode.VideoBlobUnavailable,
                        ex.Message,
                        ex.ToString()));
            }

            FfmpegBinaryResolution ffmpeg;
            try
            {
                ffmpeg = _ffmpegResolver.Resolve();
            }
            catch (Exception ex)
            {
                return new VideoFrameSidecarResult(
                    artifactId,
                    ResultsForAll(
                        rolePlans,
                        VideoFrameSidecarRoleResultCode.FinalizerFailed,
                        ex.Message,
                        ex.ToString()));
            }

            if (!ffmpeg.Success || string.IsNullOrWhiteSpace(ffmpeg.Path))
            {
                return new VideoFrameSidecarResult(
                    artifactId,
                    ResultsForAll(
                        rolePlans,
                        VideoFrameSidecarRoleResultCode.FfmpegMissing,
                        ffmpeg.Message,
                        ffmpeg.ErrorCode?.ToString()));
            }

            var results = new List<VideoFrameSidecarRoleResult>(rolePlans.Count);
            foreach (var plan in rolePlans)
            {
                var result = await TryPublishRoleAsync(
                        artifactId,
                        videoPath,
                        ffmpeg.Path!,
                        plan,
                        cancellationToken)
                    .ConfigureAwait(false);
                results.Add(result);
            }

            return new VideoFrameSidecarResult(artifactId, results);
        }

        private async Task<VideoFrameSidecarRoleResult> TryPublishRoleAsync(
            Guid artifactId,
            string videoPath,
            string ffmpegPath,
            VideoFrameSidecarRolePlan plan,
            CancellationToken cancellationToken)
        {
            string? framePath = null;
            try
            {
                try
                {
                    framePath = _tempFiles.CreateFrameTempPath(artifactId, plan.Role);
                }
                catch (OperationCanceledException ex)
                {
                    return VideoFrameSidecarRoleResult.From(
                        plan.Role,
                        plan.Selector,
                        VideoFrameSidecarRoleResultCode.CancelledAfterArtifactCreated,
                        ex.Message,
                        ex.ToString());
                }
                catch (Exception ex)
                {
                    return VideoFrameSidecarRoleResult.From(
                        plan.Role,
                        plan.Selector,
                        VideoFrameSidecarRoleResultCode.TempPathUnavailable,
                        ex.Message,
                        ex.ToString());
                }

                var extraction = await _extractor.ExtractFrameAsync(
                        ffmpegPath,
                        videoPath,
                        plan.Selector,
                        framePath,
                        DefaultExtractionTimeout,
                        cancellationToken)
                    .ConfigureAwait(false);

                if (!extraction.Success)
                {
                    return CleanupAndReturn(
                        framePath,
                        VideoFrameSidecarRoleResult.From(
                            plan.Role,
                            plan.Selector,
                            MapExtractionFailure(extraction.ErrorCode),
                            extraction.Message,
                            extraction.Stderr));
                }

                byte[] frameBytes;
                try
                {
                    frameBytes = _byteReader.ReadAllBytes(framePath);
                }
                catch (OperationCanceledException ex)
                {
                    return CleanupAndReturn(
                        framePath,
                        VideoFrameSidecarRoleResult.From(
                            plan.Role,
                            plan.Selector,
                            VideoFrameSidecarRoleResultCode.CancelledAfterArtifactCreated,
                            ex.Message,
                            ex.ToString()));
                }
                catch (Exception ex)
                {
                    return CleanupAndReturn(
                        framePath,
                        VideoFrameSidecarRoleResult.From(
                            plan.Role,
                            plan.Selector,
                            VideoFrameSidecarRoleResultCode.FrameReadFailed,
                            ex.Message,
                            ex.ToString()));
                }

                var publish = _publisher.Publish(
                    artifactId,
                    plan.Role,
                    frameBytes,
                    "jpg");

                var result = publish.Code switch
                {
                    VideoSidecarPublishResultCode.Succeeded =>
                        VideoFrameSidecarRoleResult.From(
                            plan.Role,
                            plan.Selector,
                            VideoFrameSidecarRoleResultCode.Published,
                            publish.Message),

                    VideoSidecarPublishResultCode.SkippedAlreadyExists =>
                        VideoFrameSidecarRoleResult.From(
                            plan.Role,
                            plan.Selector,
                            VideoFrameSidecarRoleResultCode.SkippedAlreadyExists,
                            publish.Message),

                    _ =>
                        VideoFrameSidecarRoleResult.From(
                            plan.Role,
                            plan.Selector,
                            VideoFrameSidecarRoleResultCode.PublishFailed,
                            publish.Message,
                            publish.Code.ToString()),
                };

                return CleanupAndReturn(framePath, result);
            }
            catch (OperationCanceledException ex)
            {
                return CleanupAndReturn(
                    framePath,
                    VideoFrameSidecarRoleResult.From(
                        plan.Role,
                        plan.Selector,
                        VideoFrameSidecarRoleResultCode.CancelledAfterArtifactCreated,
                        ex.Message,
                        ex.ToString()));
            }
            catch (Exception ex)
            {
                return CleanupAndReturn(
                    framePath,
                    VideoFrameSidecarRoleResult.From(
                        plan.Role,
                        plan.Selector,
                        VideoFrameSidecarRoleResultCode.FinalizerFailed,
                        ex.Message,
                        ex.ToString()));
            }
        }

        private VideoFrameSidecarRoleResult CleanupAndReturn(
            string? tempPath,
            VideoFrameSidecarRoleResult result)
        {
            if (tempPath is null || tempPath.Trim().Length == 0)
                return result;

            try
            {
                _tempFiles.TryDelete(tempPath);
                return result;
            }
            catch (Exception ex)
            {
                return VideoFrameSidecarRoleResult.From(
                    result.Role,
                    result.Selector,
                    result.Code,
                    result.Message,
                    AppendDiagnostic(result.Diagnostic, $"Cleanup failed: {ex}"));
            }
        }

        private static List<VideoFrameSidecarRolePlan> CreateRolePlans()
            => new List<VideoFrameSidecarRolePlan>
            {
                new VideoFrameSidecarRolePlan(VideoMediaRoles.StartFrame, VideoFrameSelector.First),
                new VideoFrameSidecarRolePlan(VideoMediaRoles.EndFrame, VideoFrameSelector.Last),
            };

        private static IReadOnlyList<VideoFrameSidecarRoleResult> ResultsForAll(
            IReadOnlyList<VideoFrameSidecarRolePlan> plans,
            VideoFrameSidecarRoleResultCode code,
            string? message,
            string? diagnostic)
        {
            var results = new List<VideoFrameSidecarRoleResult>(plans.Count);
            foreach (var plan in plans)
            {
                results.Add(VideoFrameSidecarRoleResult.From(
                    plan.Role,
                    plan.Selector,
                    code,
                    message,
                    diagnostic));
            }

            return results;
        }

        private static VideoFrameSidecarRoleResultCode MapExtractionFailure(
            FfmpegVideoFrameExtractionError? error)
            => error switch
            {
                FfmpegVideoFrameExtractionError.FfmpegMissing =>
                    VideoFrameSidecarRoleResultCode.FfmpegMissing,
                FfmpegVideoFrameExtractionError.TimedOut =>
                    VideoFrameSidecarRoleResultCode.ExtractionTimedOut,
                FfmpegVideoFrameExtractionError.InvalidOutputImage =>
                    VideoFrameSidecarRoleResultCode.InvalidOutput,
                FfmpegVideoFrameExtractionError.Cancelled =>
                    VideoFrameSidecarRoleResultCode.CancelledAfterArtifactCreated,
                FfmpegVideoFrameExtractionError.InputMissing =>
                    VideoFrameSidecarRoleResultCode.VideoBlobUnavailable,
                _ => VideoFrameSidecarRoleResultCode.ExtractionFailed,
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

        private sealed record VideoFrameSidecarRolePlan(string Role, VideoFrameSelector Selector);
    }

    internal sealed class DefaultVideoFrameFfmpegResolver : IVideoFrameFfmpegResolver
    {
        public FfmpegBinaryResolution Resolve() => FfmpegBinaryResolver.Resolve();
    }

    internal sealed class DefaultVideoFrameExtractor : IVideoFrameExtractor
    {
        private readonly FfmpegVideoFrameExtractor _extractor = new FfmpegVideoFrameExtractor();

        public Task<FfmpegVideoFrameExtractionResult> ExtractFrameAsync(
            string ffmpegPath,
            string inputPath,
            VideoFrameSelector selector,
            string outputPath,
            TimeSpan timeout,
            CancellationToken cancellationToken)
            => _extractor.ExtractFrameAsync(
                ffmpegPath,
                inputPath,
                selector,
                outputPath,
                timeout,
                cancellationToken);
    }

    internal sealed class DefaultVideoFrameTempFiles : IVideoFrameTempFiles
    {
        public string CreateFrameTempPath(Guid artifactId, string role)
        {
            var directory = Path.Combine(Path.GetTempPath(), "rook-video-frames");
            Directory.CreateDirectory(directory);
            return Path.Combine(directory, $"{artifactId:N}-{role}-{Guid.NewGuid():N}.jpg");
        }

        public void TryDelete(string path)
        {
            if (!string.IsNullOrWhiteSpace(path) && File.Exists(path))
                File.Delete(path);
        }
    }

    internal sealed class DefaultVideoFrameByteReader : IVideoFrameByteReader
    {
        public byte[] ReadAllBytes(string path) => File.ReadAllBytes(path);
    }

    internal sealed class DefaultVideoFrameSidecarPublisher : IVideoFrameSidecarPublisher
    {
        private readonly VideoSidecarPublisher _publisher;

        public DefaultVideoFrameSidecarPublisher(ArtifactStore store)
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
