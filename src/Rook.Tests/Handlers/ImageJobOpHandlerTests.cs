using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook;
using Rook.Handlers;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Image.Jobs;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class ImageJobOpHandlerTests
    {
        private static readonly Guid SampleJobId =
            Guid.Parse("11111111-1111-1111-1111-111111111111");
        private static readonly Guid SampleResultArtifactId =
            Guid.Parse("22222222-2222-2222-2222-222222222222");

        [Fact]
        public async Task DispatchAsync_Start_ReturnsJobIdAndQueuedState()
        {
            using var temp = TempDir.Create();
            var inputPath = Path.Combine(temp.Path, "input.png");
            File.WriteAllBytes(inputPath, new byte[] { 0x89, 0x50, 0x4E, 0x47 });

            ImageJobStartRequest? captured = null;
            var manager = new StubImageJobManager
            {
                SubmitImpl = (request, _) =>
                {
                    captured = request;
                    return ImageJobSubmitResult.Ok(
                        SampleJobId,
                        ImageJobState.Queued);
                },
            };
            var handler = new ImageJobOpHandler(manager, NewVisionHandler());

            var body = $$"""
                {
                  "op": "image_generate_start",
                  "prompt": "a brass rook",
                  "input_image_path": "{{Escape(inputPath)}}",
                  "model": "nano-banana-2",
                  "resolution": "1K",
                  "aspect_ratio": "1:1"
                }
                """;

            var response = await handler.DispatchAsync(body);

            AssertOk(response);
            var data = AssertDataDict(response);
            Assert.Equal(SampleJobId.ToString("D"), data["job_id"]);
            Assert.Equal("queued", data["state"]);
            Assert.NotNull(captured);
            Assert.Equal(GeminiImageCapabilities.NanoBanana2, captured!.Request.Model);
            Assert.NotNull(captured.ResolvedModel);
            Assert.NotEmpty(captured.ResolvedMedia);
        }

        [Fact]
        public void DispatchOffUi_Status_ReturnsSnakeCaseState()
        {
            var manager = new StubImageJobManager
            {
                StatusImpl = _ => ImageJobStatusResult.InFlight(
                    ImageJobState.Materializing,
                    new GenerationProgress(PercentComplete: 75, Message: "saving")),
            };
            var handler = new ImageJobOpHandler(manager, NewVisionHandler());

            var response = handler.DispatchOffUi(StatusBody());

            AssertOk(response);
            var data = AssertDataDict(response);
            Assert.Equal(SampleJobId.ToString("D"), data["job_id"]);
            Assert.Equal("materializing", data["state"]);
            Assert.Null(data["result_artifact_id"]);
            Assert.Null(data["error"]);
        }

        [Fact]
        public void DispatchOffUi_Result_ReturnsBlobFilePath()
        {
            var filePath = @"C:\tmp\rook-image-output.png";
            var manager = new StubImageJobManager
            {
                FetchImpl = _ => ImageJobFetchResult.Complete(
                    SampleResultArtifactId,
                    new[] { new ImageJobResultFile("image", filePath) }),
            };
            var handler = new ImageJobOpHandler(manager, NewVisionHandler());

            var response = handler.DispatchOffUi(ResultBody());

            AssertOk(response);
            var data = AssertDataDict(response);
            Assert.Equal(SampleJobId.ToString("D"), data["job_id"]);
            Assert.Equal("complete", data["state"]);
            Assert.Equal(SampleResultArtifactId.ToString("D"), data["result_artifact_id"]);
            var files = Assert.IsType<List<Dictionary<string, object?>>>(data["files"]);
            var file = Assert.Single(files);
            Assert.Equal("image", file["role"]);
            Assert.Equal(filePath, file["path"]);
        }

        [Fact]
        public async Task DispatchAsync_StatusOpRejectedOnAsyncDispatcher()
        {
            var handler = new ImageJobOpHandler(
                new StubImageJobManager(),
                NewVisionHandler());

            var response = await handler.DispatchAsync(StatusBody());

            AssertFail(
                response,
                GenerationErrorCode.InvalidRequest,
                expectedHttp: 400);
        }

        [Fact]
        public async Task DispatchAsync_Cancel_ReturnsCancelledState()
        {
            var manager = new StubImageJobManager
            {
                CancelImpl = (_, _) => ImageJobCancelResult.Ok(ImageJobState.Cancelled),
            };
            var handler = new ImageJobOpHandler(manager, NewVisionHandler());

            var response = await handler.DispatchAsync(CancelBody());

            AssertOk(response);
            var data = AssertDataDict(response);
            Assert.Equal(SampleJobId.ToString("D"), data["job_id"]);
            Assert.Equal("cancelled", data["state"]);
        }

        [Fact]
        public void DispatchOffUi_List_ReturnsJobsAndAppliedLimit()
        {
            var updatedAt = new DateTimeOffset(
                2026, 4, 30, 12, 0, 0, TimeSpan.Zero);
            var manager = new StubImageJobManager
            {
                ListImpl = limit => new ImageJobListResult(
                    new[]
                    {
                        new ImageJobRecord(
                            SampleJobId,
                            ImageJobState.Polling,
                            "nano-banana-2",
                            "gemini",
                            updatedAt,
                            resultArtifactId: null),
                    },
                    appliedLimit: limit),
            };
            var handler = new ImageJobOpHandler(manager, NewVisionHandler());

            var response = handler.DispatchOffUi("""{"op":"image_jobs","limit":5}""");

            AssertOk(response);
            var data = AssertDataDict(response);
            Assert.Equal(5, data["applied_limit"]);
            var jobs = Assert.IsType<List<Dictionary<string, object?>>>(data["jobs"]);
            var job = Assert.Single(jobs);
            Assert.Equal(SampleJobId.ToString("D"), job["job_id"]);
            Assert.Equal("polling", job["state"]);
            Assert.Equal("nano-banana-2", job["model"]);
            Assert.Equal("gemini", job["provider"]);
            Assert.Null(job["result_artifact_id"]);
        }

        [Fact]
        public void DispatchOffUi_StatusInvalidRequest_ReturnsFailure()
        {
            var manager = new StubImageJobManager
            {
                StatusImpl = _ => ImageJobStatusResult.Failed(
                    ImageJobState.Error,
                    new GenerationError(
                        GenerationErrorCode.InvalidRequest,
                        "unknown job",
                        Retryable: false,
                        Field: "job_id")),
            };
            var handler = new ImageJobOpHandler(manager, NewVisionHandler());

            var response = handler.DispatchOffUi(StatusBody());

            AssertFail(
                response,
                GenerationErrorCode.InvalidRequest,
                expectedHttp: 400);
        }

        private static VisionHandler NewVisionHandler() => new();

        private static string StatusBody() =>
            $$"""{"op":"image_job_status","job_id":"{{SampleJobId:D}}"}""";

        private static string ResultBody() =>
            $$"""{"op":"image_job_result","job_id":"{{SampleJobId:D}}"}""";

        private static string CancelBody() =>
            $$"""{"op":"image_job_cancel","job_id":"{{SampleJobId:D}}"}""";

        private static string Escape(string value) =>
            value.Replace("\\", "\\\\");

        private static void AssertOk(ApiResponse response)
        {
            Assert.True(
                response.Success,
                "expected success=true; data: " +
                JsonSerializer.Serialize(response.Data));
            Assert.Equal(200, response.HttpStatus);
        }

        private static void AssertFail(
            ApiResponse response,
            GenerationErrorCode expectedCode,
            int expectedHttp)
        {
            Assert.False(
                response.Success,
                "expected success=false; data: " +
                JsonSerializer.Serialize(response.Data));
            Assert.Equal(expectedHttp, response.HttpStatus);
            var data = AssertDataDict(response);
            Assert.Equal(CodeString(expectedCode), data["code"]);
        }

        private static Dictionary<string, object?> AssertDataDict(ApiResponse response)
        {
            Assert.NotNull(response.Data);
            var dict = response.Data as Dictionary<string, object?>;
            Assert.NotNull(dict);
            return dict!;
        }

        private static string CodeString(GenerationErrorCode code) => code switch
        {
            GenerationErrorCode.InvalidRequest => "invalid_request",
            GenerationErrorCode.UnsupportedMedia => "unsupported_media",
            GenerationErrorCode.DependencyUnavailable => "dependency_unavailable",
            GenerationErrorCode.ExecutionFailed => "execution_failed",
            GenerationErrorCode.Cancelled => "cancelled",
            GenerationErrorCode.Interrupted => "interrupted",
            GenerationErrorCode.QuotaExceeded => "quota_exceeded",
            GenerationErrorCode.ContentPolicy => "content_policy",
            _ => code.ToString().ToLowerInvariant(),
        };

        private sealed class StubImageJobManager : IImageJobManager
        {
            public Func<ImageJobStartRequest, CancellationToken, ImageJobSubmitResult>?
                SubmitImpl { get; set; }
            public Func<Guid, ImageJobStatusResult>? StatusImpl { get; set; }
            public Func<Guid, CancellationToken, ImageJobCancelResult>? CancelImpl { get; set; }
            public Func<Guid, ImageJobFetchResult>? FetchImpl { get; set; }
            public Func<int, ImageJobListResult>? ListImpl { get; set; }

            public Task<ImageJobSubmitResult> SubmitAsync(
                ImageJobStartRequest request,
                CancellationToken ct)
            {
                return Task.FromResult(SubmitImpl?.Invoke(request, ct)
                    ?? ImageJobSubmitResult.Fail(new GenerationError(
                        GenerationErrorCode.ExecutionFailed,
                        "Stub: SubmitImpl not configured.",
                        Retryable: false)));
            }

            public Task<ImageJobStatusResult> GetStatusAsync(
                Guid jobId,
                CancellationToken ct)
            {
                return Task.FromResult(StatusImpl?.Invoke(jobId)
                    ?? ImageJobStatusResult.Failed(
                        ImageJobState.Error,
                        new GenerationError(
                            GenerationErrorCode.ExecutionFailed,
                            "Stub: StatusImpl not configured.",
                            Retryable: false)));
            }

            public Task<ImageJobCancelResult> CancelAsync(
                Guid jobId,
                CancellationToken ct)
            {
                return Task.FromResult(CancelImpl?.Invoke(jobId, ct)
                    ?? ImageJobCancelResult.Fail(new GenerationError(
                        GenerationErrorCode.ExecutionFailed,
                        "Stub: CancelImpl not configured.",
                        Retryable: false)));
            }

            public Task<ImageJobFetchResult> FetchResultAsync(
                Guid jobId,
                CancellationToken ct)
            {
                return Task.FromResult(FetchImpl?.Invoke(jobId)
                    ?? ImageJobFetchResult.Failed(
                        ImageJobState.Error,
                        new GenerationError(
                            GenerationErrorCode.ExecutionFailed,
                            "Stub: FetchImpl not configured.",
                            Retryable: false)));
            }

            public Task<ImageJobListResult> ListJobsAsync(
                int limit,
                CancellationToken ct)
            {
                return Task.FromResult(ListImpl?.Invoke(limit)
                    ?? new ImageJobListResult(
                        Array.Empty<ImageJobRecord>(),
                        appliedLimit: limit));
            }
        }

        private sealed class TempDir : IDisposable
        {
            private TempDir(string path)
            {
                Path = path;
            }

            public string Path { get; }

            public static TempDir Create()
            {
                var path = System.IO.Path.Combine(
                    System.IO.Path.GetTempPath(),
                    "rook-image-job-op-" + Guid.NewGuid().ToString("N"));
                Directory.CreateDirectory(path);
                return new TempDir(path);
            }

            public void Dispose()
            {
                try
                {
                    if (Directory.Exists(Path))
                        Directory.Delete(Path, recursive: true);
                }
                catch (IOException) { }
                catch (UnauthorizedAccessException) { }
            }
        }
    }
}
