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

        [Fact]
        public async Task TryPublishPosterAsync_DuplicatePosterIsIdempotentSkip()
        {
            var video = GeneratedVideo();
            var publisher = new VideoSidecarPublisher(_store);
            var prepublish = publisher.Publish(video.Id, VideoMediaRoles.Poster, Bytes("existing poster"), "jpg");
            var posterTempPath = Path.Combine(_root, "tmp", "poster.jpg");
            var producer = CreateProducer(ConfigureSuccessfulExtraction(posterTempPath));

            var result = await producer.TryPublishPosterAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.SkippedAlreadyExists, result.Code);
            Assert.True(result.Success);
            Assert.Equal(VideoSidecarPublishResultCode.Succeeded, prepublish.Code);
            Assert.Single(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.Poster);
        }

        public static IEnumerable<object[]> ExtractionFailures()
        {
            yield return new object[]
            {
                FfmpegPosterExtractionError.TimedOut,
                VideoPosterSidecarResultCode.TimedOut
            };
            yield return new object[]
            {
                FfmpegPosterExtractionError.InvalidOutputImage,
                VideoPosterSidecarResultCode.InvalidOutput
            };
            yield return new object[]
            {
                FfmpegPosterExtractionError.ProcessFailed,
                VideoPosterSidecarResultCode.ExtractionFailed
            };
            yield return new object[]
            {
                FfmpegPosterExtractionError.OutputMissing,
                VideoPosterSidecarResultCode.ExtractionFailed
            };
        }

        [Theory]
        [MemberData(nameof(ExtractionFailures))]
        public async Task TryPublishPosterAsync_ExtractionFailureMapsToTypedResult(
            object extractionErrorValue,
            object expectedCodeValue)
        {
            var extractionError = (FfmpegPosterExtractionError)extractionErrorValue;
            var expectedCode = (VideoPosterSidecarResultCode)expectedCodeValue;
            var video = GeneratedVideo();
            var posterTempPath = Path.Combine(_root, "tmp", "poster.jpg");
            var stderr = new string('x', 2050);
            var extractor = new FakeVideoPosterExtractor(FfmpegPosterExtractionResult.Failed(
                "ffmpeg command",
                exitCode: 1,
                stderr: stderr,
                outputPath: posterTempPath,
                elapsed: TimeSpan.FromMilliseconds(10),
                errorCode: extractionError,
                message: "extraction failed"));
            var producer = CreateProducer(extractor, posterTempPath: posterTempPath);

            var result = await producer.TryPublishPosterAsync(video.Id, CancellationToken.None);

            Assert.Equal(expectedCode, result.Code);
            Assert.False(result.Success);
            Assert.NotNull(result.Diagnostic);
            Assert.True(result.Diagnostic!.Length <= 2048);
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.Poster);
        }

        [Fact]
        public async Task TryPublishPosterAsync_VideoBlobResolutionFailureReturnsTypedResult()
        {
            var artifact = _store.Create(
                "generated_video",
                new[] { new BlobInput("metadata", Bytes("not video"), "txt") });
            var producer = CreateProducer(ConfigureSuccessfulExtraction(Path.Combine(_root, "tmp", "poster.jpg")));

            var result = await producer.TryPublishPosterAsync(artifact.Id, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.VideoBlobUnavailable, result.Code);
            Assert.False(result.Success);
            Assert.DoesNotContain(_store.Get(artifact.Id)!.Files, f => f.Role == VideoMediaRoles.Poster);
        }

        [Fact]
        public async Task TryPublishPosterAsync_TempPathFailureReturnsTypedResult()
        {
            var video = GeneratedVideo();
            var tempFiles = new FakeVideoPosterTempFiles(Path.Combine(_root, "tmp", "poster.jpg"))
            {
                ThrowOnCreate = new IOException("temp path unavailable")
            };
            var producer = CreateProducer(
                ConfigureSuccessfulExtraction(Path.Combine(_root, "tmp", "poster.jpg")),
                tempFiles: tempFiles);

            var result = await producer.TryPublishPosterAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.TempPathUnavailable, result.Code);
            Assert.False(result.Success);
            Assert.Contains("temp path unavailable", result.Message);
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.Poster);
        }

        [Fact]
        public async Task TryPublishPosterAsync_PosterReadFailureReturnsTypedResult()
        {
            var video = GeneratedVideo();
            var posterTempPath = Path.Combine(_root, "tmp", "poster.jpg");
            var byteReader = new FakeVideoPosterByteReader(Bytes("unused"))
            {
                ThrowOnRead = new IOException("poster read failed")
            };
            var producer = CreateProducer(
                ConfigureSuccessfulExtraction(posterTempPath),
                posterTempPath: posterTempPath,
                byteReader: byteReader);

            var result = await producer.TryPublishPosterAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.PosterReadFailed, result.Code);
            Assert.False(result.Success);
            Assert.Contains("poster read failed", result.Message);
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.Poster);
        }

        [Fact]
        public async Task TryPublishPosterAsync_CancellationAfterArtifactCreatedReturnsTypedResult()
        {
            var video = GeneratedVideo();
            var extractor = ConfigureSuccessfulExtraction(Path.Combine(_root, "tmp", "poster.jpg"));
            extractor.ThrowOnExtract = new OperationCanceledException("cancel after artifact");
            var producer = CreateProducer(extractor);

            var result = await producer.TryPublishPosterAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.CancelledAfterArtifactCreated, result.Code);
            Assert.False(result.Success);
            Assert.Contains("cancel after artifact", result.Message);
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.Poster);
        }

        [Fact]
        public async Task TryPublishPosterAsync_PreCancelledTokenReturnsTypedResult()
        {
            var video = GeneratedVideo();
            using var cts = new CancellationTokenSource();
            cts.Cancel();
            var producer = CreateProducer(ConfigureSuccessfulExtraction(Path.Combine(_root, "tmp", "poster.jpg")));

            var result = await producer.TryPublishPosterAsync(video.Id, cts.Token);

            Assert.Equal(VideoPosterSidecarResultCode.CancelledAfterArtifactCreated, result.Code);
            Assert.False(result.Success);
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.Poster);
        }

        [Fact]
        public async Task TryPublishPosterAsync_PublishFailureReturnsTypedResult()
        {
            var video = GeneratedVideo();
            var publisher = new FakeVideoPosterSidecarPublisher(new VideoSidecarPublishResult(
                VideoSidecarPublishResultCode.StorageFailed,
                video.Id,
                VideoMediaRoles.Poster,
                Message: "publish failed"));
            var producer = CreateProducer(
                ConfigureSuccessfulExtraction(Path.Combine(_root, "tmp", "poster.jpg")),
                publisher: publisher);

            var result = await producer.TryPublishPosterAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.PublishFailed, result.Code);
            Assert.False(result.Success);
            Assert.Contains("publish failed", result.Message);
            Assert.Equal(VideoMediaRoles.Poster, publisher.Roles[0]);
            Assert.Equal("jpg", publisher.FileExtensions[0]);
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.Poster);
        }

        [Fact]
        public async Task TryPublishPosterAsync_PublisherExceptionReturnsFinalizerFailed()
        {
            var video = GeneratedVideo();
            var publisher = new FakeVideoPosterSidecarPublisher(new VideoSidecarPublishResult(
                VideoSidecarPublishResultCode.Succeeded,
                video.Id,
                VideoMediaRoles.Poster))
            {
                ThrowOnPublish = new InvalidOperationException("publisher broke")
            };
            var producer = CreateProducer(
                ConfigureSuccessfulExtraction(Path.Combine(_root, "tmp", "poster.jpg")),
                publisher: publisher);

            var result = await producer.TryPublishPosterAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.FinalizerFailed, result.Code);
            Assert.False(result.Success);
            Assert.Contains("publisher broke", result.Message);
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.Poster);
        }

        [Fact]
        public async Task TryPublishPosterAsync_UnexpectedProducerExceptionReturnsFinalizerFailed()
        {
            var video = GeneratedVideo();
            var resolver = FakeVideoPosterFfmpegResolver.Found(Path.Combine(_root, "tools", "ffmpeg.exe"));
            resolver.ThrowOnResolve = new InvalidOperationException("resolver broke");
            var producer = CreateProducer(
                ConfigureSuccessfulExtraction(Path.Combine(_root, "tmp", "poster.jpg")),
                resolver: resolver);

            var result = await producer.TryPublishPosterAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.FinalizerFailed, result.Code);
            Assert.False(result.Success);
            Assert.Contains("resolver broke", result.Message);
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.Poster);
        }

        [Fact]
        public async Task TryPublishPosterAsync_CleanupFailureDoesNotOverridePublishedResult()
        {
            var video = GeneratedVideo();
            var posterTempPath = Path.Combine(_root, "tmp", "poster.jpg");
            var tempFiles = new FakeVideoPosterTempFiles(posterTempPath)
            {
                ThrowOnDelete = new IOException("cleanup failed")
            };
            var producer = CreateProducer(
                ConfigureSuccessfulExtraction(posterTempPath),
                posterTempPath: posterTempPath,
                tempFiles: tempFiles);

            var result = await producer.TryPublishPosterAsync(video.Id, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.Published, result.Code);
            Assert.True(result.Success);
            Assert.Contains("cleanup failed", result.Diagnostic);
            Assert.Single(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.Poster);
        }

        [Fact]
        public void DefaultTempFiles_TryDeletePropagatesDeleteFailure()
        {
            var tempFiles = new DefaultVideoPosterTempFiles();
            var path = tempFiles.CreatePosterTempPath(Guid.NewGuid());
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, "locked poster");
            File.SetAttributes(path, FileAttributes.ReadOnly);

            try
            {
                Assert.ThrowsAny<Exception>(() => tempFiles.TryDelete(path));
            }
            finally
            {
                if (File.Exists(path))
                {
                    File.SetAttributes(path, FileAttributes.Normal);
                    File.Delete(path);
                }
            }
        }

        private VideoPosterSidecarProducer CreateProducer(
            FakeVideoPosterExtractor extractor,
            string? posterTempPath = null,
            FakeVideoPosterFfmpegResolver? resolver = null,
            FakeVideoPosterTempFiles? tempFiles = null,
            FakeVideoPosterByteReader? byteReader = null,
            IVideoPosterSidecarPublisher? publisher = null)
        {
            var ffmpeg = Path.Combine(_root, "tools", "ffmpeg.exe");
            posterTempPath ??= Path.Combine(_root, "tmp", "poster.jpg");
            return new VideoPosterSidecarProducer(
                _store,
                resolver ?? FakeVideoPosterFfmpegResolver.Found(ffmpeg),
                extractor,
                tempFiles ?? new FakeVideoPosterTempFiles(posterTempPath),
                byteReader ?? new FakeVideoPosterByteReader(Bytes("poster jpg bytes")),
                publisher);
        }

        private FakeVideoPosterExtractor ConfigureSuccessfulExtraction(string outputPath)
            => new FakeVideoPosterExtractor(FfmpegPosterExtractionResult.Completed(
                "ffmpeg command",
                exitCode: 0,
                stderr: string.Empty,
                outputPath: outputPath,
                width: 80,
                height: 40,
                elapsed: TimeSpan.FromMilliseconds(25)));

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

            public Exception? ThrowOnResolve { get; set; }

            public FfmpegBinaryResolution Resolve()
            {
                if (ThrowOnResolve is not null)
                    throw ThrowOnResolve;

                return _resolution;
            }
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

            public Exception? ThrowOnExtract { get; set; }

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
                if (ThrowOnExtract is not null)
                    throw ThrowOnExtract;

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

            public Exception? ThrowOnCreate { get; set; }
            public Exception? ThrowOnDelete { get; set; }

            public string CreatePosterTempPath(Guid artifactId)
            {
                if (ThrowOnCreate is not null)
                    throw ThrowOnCreate;

                return _path;
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

        private sealed class FakeVideoPosterByteReader : IVideoPosterByteReader
        {
            private readonly byte[] _bytes;

            public FakeVideoPosterByteReader(byte[] bytes)
            {
                _bytes = bytes;
            }

            public List<string> Paths { get; } = new List<string>();

            public Exception? ThrowOnRead { get; set; }

            public byte[] ReadAllBytes(string path)
            {
                Paths.Add(path);
                if (ThrowOnRead is not null)
                    throw ThrowOnRead;

                return _bytes;
            }
        }

        private sealed class FakeVideoPosterSidecarPublisher : IVideoPosterSidecarPublisher
        {
            private readonly VideoSidecarPublishResult _result;

            public FakeVideoPosterSidecarPublisher(VideoSidecarPublishResult result)
            {
                _result = result;
            }

            public List<string> Roles { get; } = new List<string>();
            public List<string> FileExtensions { get; } = new List<string>();

            public Exception? ThrowOnPublish { get; set; }

            public VideoSidecarPublishResult Publish(
                Guid artifactId,
                string role,
                byte[] content,
                string fileExtension)
            {
                Roles.Add(role);
                FileExtensions.Add(fileExtension);
                if (ThrowOnPublish is not null)
                    throw ThrowOnPublish;

                return _result;
            }
        }
    }
}
