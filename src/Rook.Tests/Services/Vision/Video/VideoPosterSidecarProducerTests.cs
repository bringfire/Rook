using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Extraction;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoPosterSidecarProducerTests : IDisposable
    {
        private readonly string _root;
        private readonly ArtifactStore _store;

        public VideoPosterSidecarProducerTests()
        {
            _root = Path.Combine(Path.GetTempPath(), $"rook-video-poster-producer-test-{Guid.NewGuid():N}");
            _store = new ArtifactStore(_root);
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        [Fact]
        public async Task TryPublishPosterAsync_ExtractsAndPublishesPoster()
        {
            var video = GeneratedVideo();
            var ffmpeg = Path.Combine(_root, "tools", "ffmpeg.exe");
            var posterTempPath = Path.Combine(_root, "tmp", "poster.jpg");
            var resolver = FakeVideoPosterFfmpegResolver.Found(ffmpeg);
            var extractor = new FakeVideoPosterExtractor(FfmpegPosterExtractionResult.Completed(
                "ffmpeg command",
                exitCode: 0,
                stderr: string.Empty,
                outputPath: posterTempPath,
                width: 80,
                height: 40,
                elapsed: TimeSpan.FromMilliseconds(25)));
            var tempFiles = new FakeVideoPosterTempFiles(posterTempPath);
            var posterBytes = Bytes("poster jpg bytes");
            var byteReader = new FakeVideoPosterByteReader(posterBytes);
            var producer = new VideoPosterSidecarProducer(
                _store,
                resolver,
                extractor,
                tempFiles,
                byteReader);

            var result = await producer.TryPublishPosterAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.Published, result.Code);
            Assert.True(result.Success);
            Assert.Equal(video.Id, result.ArtifactId);
            Assert.Equal(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.Video), extractor.InputPaths[0]);
            Assert.Equal(ffmpeg, extractor.FfmpegPaths[0]);
            Assert.Equal(posterTempPath, extractor.OutputPaths[0]);
            Assert.Equal(posterTempPath, byteReader.Paths[0]);
            Assert.Equal(new[] { posterTempPath }, tempFiles.DeletedPaths);
            Assert.Equal("poster jpg bytes", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.Poster)));
        }

        [Fact]
        public async Task TryPublishPosterAsync_MissingFfmpegReturnsTypedSkip()
        {
            var video = GeneratedVideo();
            var resolver = FakeVideoPosterFfmpegResolver.Missing("ffmpeg.exe was not found");
            var extractor = new FakeVideoPosterExtractor(FfmpegPosterExtractionResult.Completed(
                "should not run",
                exitCode: 0,
                stderr: string.Empty,
                outputPath: "unused.jpg",
                width: 1,
                height: 1,
                elapsed: TimeSpan.Zero));
            var tempFiles = new FakeVideoPosterTempFiles(Path.Combine(_root, "poster.jpg"));
            var byteReader = new FakeVideoPosterByteReader(Bytes("unused"));
            var producer = new VideoPosterSidecarProducer(
                _store,
                resolver,
                extractor,
                tempFiles,
                byteReader);

            var result = await producer.TryPublishPosterAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.SkippedFfmpegMissing, result.Code);
            Assert.False(result.Success);
            Assert.Equal(video.Id, result.ArtifactId);
            Assert.Contains("ffmpeg.exe was not found", result.Message);
            Assert.Empty(extractor.InputPaths);
            Assert.Empty(byteReader.Paths);
            Assert.Empty(tempFiles.DeletedPaths);
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.Poster);
        }

        private Artifact GeneratedVideo()
            => _store.Create(
                "generated_video",
                new[] { new BlobInput(VideoMediaRoles.Video, Bytes("mp4"), "mp4") });

        private static byte[] Bytes(string value) => Encoding.UTF8.GetBytes(value);

        private sealed class FakeVideoPosterFfmpegResolver : IVideoPosterFfmpegResolver
        {
            private readonly FfmpegBinaryResolution _resolution;

            private FakeVideoPosterFfmpegResolver(FfmpegBinaryResolution resolution)
            {
                _resolution = resolution;
            }

            public static FakeVideoPosterFfmpegResolver Found(string path)
                => new FakeVideoPosterFfmpegResolver(
                    FfmpegBinaryResolution.Found(path, FfmpegBinaryResolutionSource.ConfiguredPath));

            public static FakeVideoPosterFfmpegResolver Missing(string message)
                => new FakeVideoPosterFfmpegResolver(
                    FfmpegBinaryResolution.Failed(FfmpegBinaryResolutionError.NotFound, message));

            public FfmpegBinaryResolution Resolve() => _resolution;
        }

        private sealed class FakeVideoPosterExtractor : IVideoPosterExtractor
        {
            private readonly FfmpegPosterExtractionResult _result;

            public FakeVideoPosterExtractor(FfmpegPosterExtractionResult result)
            {
                _result = result;
            }

            public List<string> FfmpegPaths { get; } = new List<string>();
            public List<string> InputPaths { get; } = new List<string>();
            public List<string> OutputPaths { get; } = new List<string>();

            public Task<FfmpegPosterExtractionResult> ExtractPosterAsync(
                string ffmpegPath,
                string inputPath,
                string outputPath,
                TimeSpan timeout,
                CancellationToken cancellationToken)
            {
                FfmpegPaths.Add(ffmpegPath);
                InputPaths.Add(inputPath);
                OutputPaths.Add(outputPath);
                return Task.FromResult(_result);
            }
        }

        private sealed class FakeVideoPosterTempFiles : IVideoPosterTempFiles
        {
            private readonly string _path;

            public FakeVideoPosterTempFiles(string path)
            {
                _path = path;
            }

            public List<string> DeletedPaths { get; } = new List<string>();

            public string CreatePosterTempPath(Guid artifactId) => _path;

            public void TryDelete(string path) => DeletedPaths.Add(path);
        }

        private sealed class FakeVideoPosterByteReader : IVideoPosterByteReader
        {
            private readonly byte[] _bytes;

            public FakeVideoPosterByteReader(byte[] bytes)
            {
                _bytes = bytes;
            }

            public List<string> Paths { get; } = new List<string>();

            public byte[] ReadAllBytes(string path)
            {
                Paths.Add(path);
                return _bytes;
            }
        }
    }
}
