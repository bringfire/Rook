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
    }
}
