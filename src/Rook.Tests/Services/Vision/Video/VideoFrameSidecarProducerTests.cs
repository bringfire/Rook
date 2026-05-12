using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Extraction;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoFrameSidecarProducerTests : IDisposable
    {
        private readonly string _root;
        private readonly ArtifactStore _store;

        public VideoFrameSidecarProducerTests()
        {
            _root = Path.Combine(Path.GetTempPath(), $"rook-video-frame-sidecar-test-{Guid.NewGuid():N}");
            _store = new ArtifactStore(_root);
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_PublishesStartThenEnd()
        {
            var video = GeneratedVideo();
            var ffmpeg = Path.Combine(_root, "tools", "ffmpeg.exe");
            var tempFiles = new FakeFrameTempFiles(
                Path.Combine(_root, "tmp", "start.jpg"),
                Path.Combine(_root, "tmp", "end.jpg"));
            var extractor = new FakeFrameExtractor();
            var byteReader = new FakeFrameByteReader(new Dictionary<string, byte[]>
            {
                [tempFiles.StartPath] = Bytes("start jpg"),
                [tempFiles.EndPath] = Bytes("end jpg"),
            });
            var producer = CreateProducer(
                resolver: FakeFrameFfmpegResolver.Found(ffmpeg),
                extractor: extractor,
                tempFiles: tempFiles,
                byteReader: byteReader);

            var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

            Assert.Equal(video.Id, result.ArtifactId);
            Assert.Equal(
                new[] { VideoMediaRoles.StartFrame, VideoMediaRoles.EndFrame },
                result.RoleResults.Select(r => r.Role).ToArray());
            Assert.All(result.RoleResults, r => Assert.Equal(VideoFrameSidecarRoleResultCode.Published, r.Code));
            Assert.Equal(
                new[] { VideoFrameSelectorKind.First, VideoFrameSelectorKind.Last },
                extractor.Selectors.Select(s => s.Kind).ToArray());
            Assert.Equal(new[] { ffmpeg, ffmpeg }, extractor.FfmpegPaths);
            Assert.Equal(new[] { tempFiles.StartPath, tempFiles.EndPath }, extractor.OutputPaths);
            Assert.Equal(new[] { tempFiles.StartPath, tempFiles.EndPath }, tempFiles.DeletedPaths);
            Assert.Equal("start jpg", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.StartFrame)));
            Assert.Equal("end jpg", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.EndFrame)));
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_MissingFfmpegReportsBothRolesWithoutExtraction()
        {
            var video = GeneratedVideo();
            var extractor = new FakeFrameExtractor();
            var producer = CreateProducer(
                resolver: FakeFrameFfmpegResolver.Missing("ffmpeg.exe was not found"),
                extractor: extractor);

            var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

            Assert.Equal(
                new[] { VideoMediaRoles.StartFrame, VideoMediaRoles.EndFrame },
                result.RoleResults.Select(r => r.Role).ToArray());
            Assert.All(result.RoleResults, r => Assert.Equal(VideoFrameSidecarRoleResultCode.FfmpegMissing, r.Code));
            Assert.Empty(extractor.Selectors);
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.StartFrame);
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.EndFrame);
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_StartSuccessEndExtractionFailurePublishesOnlyStart()
        {
            var video = GeneratedVideo();
            var extractor = new FakeFrameExtractor();
            extractor.ResultsByKind[VideoFrameSelectorKind.Last] = Failed(
                VideoFrameSelector.Last,
                FfmpegVideoFrameExtractionError.ProcessFailed,
                "end frame failed");
            var producer = CreateProducer(extractor: extractor);

            var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[0].Code);
            Assert.Equal(VideoFrameSidecarRoleResultCode.ExtractionFailed, result.RoleResults[1].Code);
            Assert.Equal(new[] { VideoFrameSelectorKind.First, VideoFrameSelectorKind.Last }, extractor.Selectors.Select(s => s.Kind));
            Assert.Equal("start jpg", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.StartFrame)));
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.EndFrame);
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_StartFailureEndSuccessPublishesOnlyEnd()
        {
            var video = GeneratedVideo();
            var extractor = new FakeFrameExtractor();
            extractor.ResultsByKind[VideoFrameSelectorKind.First] = Failed(
                VideoFrameSelector.First,
                FfmpegVideoFrameExtractionError.ProcessFailed,
                "start frame failed");
            var producer = CreateProducer(extractor: extractor);

            var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoFrameSidecarRoleResultCode.ExtractionFailed, result.RoleResults[0].Code);
            Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[1].Code);
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.StartFrame);
            Assert.Equal("end jpg", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.EndFrame)));
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_DuplicateStartDoesNotPreventEnd()
        {
            var video = GeneratedVideo();
            var publisher = new FakeFrameSidecarPublisher();
            publisher.ResultsByRole[VideoMediaRoles.StartFrame] = new VideoSidecarPublishResult(
                VideoSidecarPublishResultCode.SkippedAlreadyExists,
                video.Id,
                VideoMediaRoles.StartFrame,
                Message: "duplicate");
            var producer = CreateProducer(publisher: publisher);

            var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoFrameSidecarRoleResultCode.SkippedAlreadyExists, result.RoleResults[0].Code);
            Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[1].Code);
            Assert.Equal(new[] { VideoMediaRoles.StartFrame, VideoMediaRoles.EndFrame }, publisher.Roles);
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_TempPathFailureForStartDoesNotPreventEnd()
        {
            var video = GeneratedVideo();
            var tempFiles = new FakeFrameTempFiles(
                Path.Combine(_root, "tmp", "start.jpg"),
                Path.Combine(_root, "tmp", "end.jpg"))
            {
                ThrowOnCreateStart = new IOException("no start temp"),
            };
            var extractor = new FakeFrameExtractor();
            var producer = CreateProducer(tempFiles: tempFiles, extractor: extractor);

            var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoFrameSidecarRoleResultCode.TempPathUnavailable, result.RoleResults[0].Code);
            Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[1].Code);
            Assert.Equal(new[] { VideoFrameSelectorKind.Last }, extractor.Selectors.Select(s => s.Kind));
            Assert.Equal(new[] { tempFiles.EndPath }, tempFiles.DeletedPaths);
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.StartFrame);
            Assert.Equal("end jpg", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.EndFrame)));
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_ReadFailureForEndDoesNotChangeStart()
        {
            var video = GeneratedVideo();
            var byteReader = new FakeFrameByteReader(new Dictionary<string, byte[]>
            {
                [Path.Combine(_root, "tmp", "start.jpg")] = Bytes("start jpg"),
                [Path.Combine(_root, "tmp", "end.jpg")] = Bytes("end jpg"),
            })
            {
                ThrowOnEndRead = new IOException("end read failed"),
            };
            var producer = CreateProducer(byteReader: byteReader);

            var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[0].Code);
            Assert.Equal(VideoFrameSidecarRoleResultCode.FrameReadFailed, result.RoleResults[1].Code);
            Assert.Equal("start jpg", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.StartFrame)));
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.EndFrame);
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_StartPublishFailureDoesNotPreventEnd()
        {
            var video = GeneratedVideo();
            var publisher = new FakeFrameSidecarPublisher();
            publisher.ResultsByRole[VideoMediaRoles.StartFrame] = new VideoSidecarPublishResult(
                VideoSidecarPublishResultCode.StorageFailed,
                video.Id,
                VideoMediaRoles.StartFrame,
                Message: "start publish failed");
            var producer = CreateProducer(publisher: publisher);

            var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoFrameSidecarRoleResultCode.PublishFailed, result.RoleResults[0].Code);
            Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[1].Code);
            Assert.Equal(new[] { VideoMediaRoles.StartFrame, VideoMediaRoles.EndFrame }, publisher.Roles);
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_GenericExceptionDuringOneRoleBecomesFinalizerFailedAndOtherRoleIsAttempted()
        {
            var video = GeneratedVideo();
            var extractor = new FakeFrameExtractor();
            extractor.ExceptionsByKind[VideoFrameSelectorKind.First] = new InvalidOperationException("start blew up");
            var publisher = new FakeFrameSidecarPublisher();
            var producer = CreateProducer(extractor: extractor, publisher: publisher);

            var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoFrameSidecarRoleResultCode.FinalizerFailed, result.RoleResults[0].Code);
            Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[1].Code);
            Assert.Equal(new[] { VideoFrameSelectorKind.First, VideoFrameSelectorKind.Last }, extractor.Selectors.Select(s => s.Kind));
            Assert.Equal(new[] { VideoMediaRoles.EndFrame }, publisher.Roles);
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_CancellationDuringOneRoleIsPerRoleFailure()
        {
            var video = GeneratedVideo();
            var extractor = new FakeFrameExtractor();
            extractor.ExceptionsByKind[VideoFrameSelectorKind.First] = new OperationCanceledException("start cancelled");
            var producer = CreateProducer(extractor: extractor);

            var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoFrameSidecarRoleResultCode.CancelledAfterArtifactCreated, result.RoleResults[0].Code);
            Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[1].Code);
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.StartFrame);
            Assert.Equal("end jpg", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.EndFrame)));
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_CleanupFailureIsDiagnosticOnly()
        {
            var video = GeneratedVideo();
            var tempFiles = new FakeFrameTempFiles(
                Path.Combine(_root, "tmp", "start.jpg"),
                Path.Combine(_root, "tmp", "end.jpg"))
            {
                ThrowOnDelete = new IOException("delete failed"),
            };
            var producer = CreateProducer(tempFiles: tempFiles);

            var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

            Assert.All(result.RoleResults, r => Assert.Equal(VideoFrameSidecarRoleResultCode.Published, r.Code));
            Assert.All(result.RoleResults, r => Assert.Contains("Cleanup failed", r.Diagnostic));
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_OneFrameVideoStillPublishesDistinctRolesWhenBothExtractionsSucceed()
        {
            var video = GeneratedVideo();
            var tempFiles = new FakeFrameTempFiles(
                Path.Combine(_root, "tmp", "start.jpg"),
                Path.Combine(_root, "tmp", "end.jpg"));
            var byteReader = new FakeFrameByteReader(new Dictionary<string, byte[]>
            {
                [tempFiles.StartPath] = Bytes("same visual frame"),
                [tempFiles.EndPath] = Bytes("same visual frame"),
            });
            var producer = CreateProducer(tempFiles: tempFiles, byteReader: byteReader);

            var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

            Assert.All(result.RoleResults, r => Assert.Equal(VideoFrameSidecarRoleResultCode.Published, r.Code));
            Assert.Equal("same visual frame", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.StartFrame)));
            Assert.Equal("same visual frame", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.EndFrame)));
            Assert.NotEqual(
                _store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.StartFrame),
                _store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.EndFrame));
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_TargetedEndOnlyPublishesOnlyEnd()
        {
            var video = GeneratedVideo();
            var extractor = new FakeFrameExtractor();
            var producer = CreateProducer(extractor: extractor);

            var result = await producer.TryPublishFrameSidecarsAsync(
                video.Id,
                new[] { VideoMediaRoles.EndFrame },
                CancellationToken.None);

            var roleResult = Assert.Single(result.RoleResults);
            Assert.Equal(VideoMediaRoles.EndFrame, roleResult.Role);
            Assert.Equal(VideoFrameSelectorKind.Last, roleResult.Selector.Kind);
            Assert.Equal(VideoFrameSidecarRoleResultCode.Published, roleResult.Code);
            Assert.Equal(new[] { VideoFrameSelectorKind.Last }, extractor.Selectors.Select(s => s.Kind));
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.StartFrame);
            Assert.Equal("end jpg", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.EndFrame)));
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_TargetedStartOnlyPublishesOnlyStart()
        {
            var video = GeneratedVideo();
            var extractor = new FakeFrameExtractor();
            var producer = CreateProducer(extractor: extractor);

            var result = await producer.TryPublishFrameSidecarsAsync(
                video.Id,
                new[] { VideoMediaRoles.StartFrame },
                CancellationToken.None);

            var roleResult = Assert.Single(result.RoleResults);
            Assert.Equal(VideoMediaRoles.StartFrame, roleResult.Role);
            Assert.Equal(VideoFrameSelectorKind.First, roleResult.Selector.Kind);
            Assert.Equal(VideoFrameSidecarRoleResultCode.Published, roleResult.Code);
            Assert.Equal(new[] { VideoFrameSelectorKind.First }, extractor.Selectors.Select(s => s.Kind));
            Assert.Equal("start jpg", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.StartFrame)));
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.EndFrame);
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_AllUnknownRolesDoesNotResolveVideoOrFfmpeg()
        {
            var video = GeneratedVideo();
            var resolver = FakeFrameFfmpegResolver.Found(Path.Combine(_root, "tools", "ffmpeg.exe"));
            var extractor = new FakeFrameExtractor();
            var tempFiles = new FakeFrameTempFiles(
                Path.Combine(_root, "tmp", "start.jpg"),
                Path.Combine(_root, "tmp", "end.jpg"));
            var producer = CreateProducer(
                resolver: resolver,
                extractor: extractor,
                tempFiles: tempFiles);

            var result = await producer.TryPublishFrameSidecarsAsync(
                video.Id,
                new[] { "bogus_role" },
                CancellationToken.None);

            var roleResult = Assert.Single(result.RoleResults);
            Assert.Equal("bogus_role", roleResult.Role);
            Assert.Equal(VideoFrameSidecarRoleResultCode.UnsupportedRole, roleResult.Code);
            Assert.Equal(0, resolver.ResolveCount);
            Assert.Equal(0, tempFiles.CreateCallCount);
            Assert.Empty(extractor.Selectors);
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == "bogus_role");
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_MixedUnknownAndKnownReportsUnknownAndAttemptsKnown()
        {
            var video = GeneratedVideo();
            var resolver = FakeFrameFfmpegResolver.Found(Path.Combine(_root, "tools", "ffmpeg.exe"));
            var extractor = new FakeFrameExtractor();
            var producer = CreateProducer(resolver: resolver, extractor: extractor);

            var result = await producer.TryPublishFrameSidecarsAsync(
                video.Id,
                new[] { "bogus_role", VideoMediaRoles.EndFrame },
                CancellationToken.None);

            Assert.Equal(new[] { "bogus_role", VideoMediaRoles.EndFrame }, result.RoleResults.Select(r => r.Role));
            Assert.Equal(VideoFrameSidecarRoleResultCode.UnsupportedRole, result.RoleResults[0].Code);
            Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[1].Code);
            Assert.Equal(1, resolver.ResolveCount);
            Assert.Equal(new[] { VideoFrameSelectorKind.Last }, extractor.Selectors.Select(s => s.Kind));
        }

        private VideoFrameSidecarProducer CreateProducer(
            FakeFrameFfmpegResolver? resolver = null,
            FakeFrameExtractor? extractor = null,
            FakeFrameTempFiles? tempFiles = null,
            FakeFrameByteReader? byteReader = null,
            IVideoFrameSidecarPublisher? publisher = null)
        {
            tempFiles ??= new FakeFrameTempFiles(
                Path.Combine(_root, "tmp", "start.jpg"),
                Path.Combine(_root, "tmp", "end.jpg"));
            return new VideoFrameSidecarProducer(
                _store,
                resolver ?? FakeFrameFfmpegResolver.Found(Path.Combine(_root, "tools", "ffmpeg.exe")),
                extractor ?? new FakeFrameExtractor(),
                tempFiles,
                byteReader ?? new FakeFrameByteReader(new Dictionary<string, byte[]>
                {
                    [tempFiles.StartPath] = Bytes("start jpg"),
                    [tempFiles.EndPath] = Bytes("end jpg"),
                }),
                publisher);
        }

        private Artifact GeneratedVideo()
            => _store.Create(
                "generated_video",
                new[] { new BlobInput(VideoMediaRoles.Video, Bytes("mp4"), "mp4") });

        private static byte[] Bytes(string value) => Encoding.UTF8.GetBytes(value);

        private static FfmpegVideoFrameExtractionResult Failed(
            VideoFrameSelector selector,
            FfmpegVideoFrameExtractionError error,
            string message)
            => FfmpegVideoFrameExtractionResult.Failed(
                selector,
                "ffmpeg command",
                exitCode: 1,
                stderr: message,
                outputPath: "frame.jpg",
                elapsed: TimeSpan.FromMilliseconds(1),
                error,
                message);

        private sealed class FakeFrameFfmpegResolver : IVideoFrameFfmpegResolver
        {
            private readonly FfmpegBinaryResolution _resolution;

            private FakeFrameFfmpegResolver(FfmpegBinaryResolution resolution)
            {
                _resolution = resolution;
            }

            public static FakeFrameFfmpegResolver Found(string path)
                => new FakeFrameFfmpegResolver(
                    FfmpegBinaryResolution.Found(path, FfmpegBinaryResolutionSource.ConfiguredPath));

            public static FakeFrameFfmpegResolver Missing(string message)
                => new FakeFrameFfmpegResolver(
                    FfmpegBinaryResolution.Failed(FfmpegBinaryResolutionError.NotFound, message));

            public Exception? ThrowOnResolve { get; set; }
            public int ResolveCount { get; private set; }

            public FfmpegBinaryResolution Resolve()
            {
                ResolveCount++;
                if (ThrowOnResolve is not null)
                    throw ThrowOnResolve;
                return _resolution;
            }
        }

        private sealed class FakeFrameExtractor : IVideoFrameExtractor
        {
            public List<string> FfmpegPaths { get; } = new List<string>();
            public List<string> InputPaths { get; } = new List<string>();
            public List<VideoFrameSelector> Selectors { get; } = new List<VideoFrameSelector>();
            public List<string> OutputPaths { get; } = new List<string>();
            public Dictionary<VideoFrameSelectorKind, FfmpegVideoFrameExtractionResult> ResultsByKind { get; } =
                new Dictionary<VideoFrameSelectorKind, FfmpegVideoFrameExtractionResult>();
            public Dictionary<VideoFrameSelectorKind, Exception> ExceptionsByKind { get; } =
                new Dictionary<VideoFrameSelectorKind, Exception>();
            public Exception? ThrowOnExtract { get; set; }

            public Task<FfmpegVideoFrameExtractionResult> ExtractFrameAsync(
                string ffmpegPath,
                string inputPath,
                VideoFrameSelector selector,
                string outputPath,
                TimeSpan timeout,
                CancellationToken cancellationToken)
            {
                FfmpegPaths.Add(ffmpegPath);
                InputPaths.Add(inputPath);
                Selectors.Add(selector);
                OutputPaths.Add(outputPath);
                if (ThrowOnExtract is not null)
                    throw ThrowOnExtract;
                if (ExceptionsByKind.TryGetValue(selector.Kind, out var exception))
                    throw exception;

                if (ResultsByKind.TryGetValue(selector.Kind, out var result))
                    return Task.FromResult(result);

                return Task.FromResult(FfmpegVideoFrameExtractionResult.Completed(
                    selector,
                    "ffmpeg command",
                    0,
                    string.Empty,
                    outputPath,
                    80,
                    40,
                    TimeSpan.FromMilliseconds(1)));
            }
        }

        private sealed class FakeFrameTempFiles : IVideoFrameTempFiles
        {
            public FakeFrameTempFiles(string startPath, string endPath)
            {
                StartPath = startPath;
                EndPath = endPath;
            }

            public string StartPath { get; }
            public string EndPath { get; }
            public List<string> DeletedPaths { get; } = new List<string>();
            public Exception? ThrowOnCreateStart { get; set; }
            public Exception? ThrowOnCreateEnd { get; set; }
            public Exception? ThrowOnDelete { get; set; }
            public int CreateCallCount { get; private set; }

            public string CreateFrameTempPath(Guid artifactId, string role)
            {
                CreateCallCount++;
                if (role == VideoMediaRoles.StartFrame && ThrowOnCreateStart is not null)
                    throw ThrowOnCreateStart;
                if (role == VideoMediaRoles.EndFrame && ThrowOnCreateEnd is not null)
                    throw ThrowOnCreateEnd;
                return role == VideoMediaRoles.StartFrame ? StartPath : EndPath;
            }

            public void TryDelete(string path)
            {
                DeletedPaths.Add(path);
                if (ThrowOnDelete is not null)
                    throw ThrowOnDelete;
                if (File.Exists(path))
                    File.Delete(path);
            }
        }

        private sealed class FakeFrameByteReader : IVideoFrameByteReader
        {
            private readonly Dictionary<string, byte[]> _bytesByPath;

            public FakeFrameByteReader(Dictionary<string, byte[]> bytesByPath)
            {
                _bytesByPath = bytesByPath;
            }

            public Exception? ThrowOnStartRead { get; set; }
            public Exception? ThrowOnEndRead { get; set; }

            public byte[] ReadAllBytes(string path)
            {
                if (path.Contains("start") && ThrowOnStartRead is not null)
                    throw ThrowOnStartRead;
                if (path.Contains("end") && ThrowOnEndRead is not null)
                    throw ThrowOnEndRead;
                return _bytesByPath[path];
            }
        }

        private sealed class FakeFrameSidecarPublisher : IVideoFrameSidecarPublisher
        {
            public Dictionary<string, VideoSidecarPublishResult> ResultsByRole { get; } =
                new Dictionary<string, VideoSidecarPublishResult>();
            public List<string> Roles { get; } = new List<string>();
            public Exception? ThrowOnStartPublish { get; set; }
            public Exception? ThrowOnEndPublish { get; set; }

            public VideoSidecarPublishResult Publish(
                Guid artifactId,
                string role,
                byte[] content,
                string fileExtension)
            {
                Roles.Add(role);
                if (role == VideoMediaRoles.StartFrame && ThrowOnStartPublish is not null)
                    throw ThrowOnStartPublish;
                if (role == VideoMediaRoles.EndFrame && ThrowOnEndPublish is not null)
                    throw ThrowOnEndPublish;
                if (ResultsByRole.TryGetValue(role, out var result))
                    return result;
                return new VideoSidecarPublishResult(
                    VideoSidecarPublishResultCode.Succeeded,
                    artifactId,
                    role);
            }
        }
    }
}
