using System;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Jobs;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Jobs
{
    public class ImageJobResultTypesTests
    {
        [Fact]
        public void SubmitOk_requires_non_empty_job_id()
        {
            Assert.Throws<ArgumentException>(() =>
                ImageJobSubmitResult.Ok(Guid.Empty, ImageJobState.Queued));
        }

        [Fact]
        public void StatusComplete_requires_artifact_id()
        {
            Assert.Throws<ArgumentException>(() =>
                ImageJobStatusResult.Complete(Guid.Empty));
        }

        [Fact]
        public void StatusInFlight_rejects_undefined_state()
        {
            Assert.Throws<ArgumentException>(() =>
                ImageJobStatusResult.InFlight((ImageJobState)999, null));
        }

        [Fact]
        public void StatusFailed_requires_terminal_failure_state()
        {
            var error = new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                "failed",
                Retryable: true);

            Assert.Throws<ArgumentException>(() =>
                ImageJobStatusResult.Failed(ImageJobState.Polling, error));
        }

        [Fact]
        public void FetchComplete_requires_files()
        {
            Assert.Throws<ArgumentException>(() =>
                ImageJobFetchResult.Complete(
                    Guid.NewGuid(),
                    Array.Empty<ImageJobResultFile>()));
        }

        [Fact]
        public void Record_constructor_allows_optional_job_details()
        {
            var jobId = Guid.NewGuid();
            var updatedAt = DateTimeOffset.UtcNow;

            var record = new ImageJobRecord(
                jobId,
                ImageJobState.Queued,
                "model",
                "provider",
                updatedAt);

            Assert.Equal(jobId, record.JobId);
            Assert.Equal(ImageJobState.Queued, record.State);
            Assert.Equal("model", record.Model);
            Assert.Equal("provider", record.Provider);
            Assert.Equal(updatedAt, record.UpdatedAt);
            Assert.Null(record.ProviderHandle);
            Assert.Null(record.ResultArtifactId);
            Assert.Null(record.Error);
        }
    }
}
