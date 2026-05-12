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

            public FfmpegBinaryResolution Resolve()
            {
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

            public string CreateFrameTempPath(Guid artifactId, string role)
            {
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
