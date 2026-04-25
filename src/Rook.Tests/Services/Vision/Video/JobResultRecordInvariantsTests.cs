using System;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    /// <summary>
    /// Pins the type-level invariants on the four <c>Job*Result</c>
    /// envelopes: private constructors + factory-only construction
    /// prevent invalid states from existing at all. Codex round 3
    /// finding: documented invariants on positional records were not
    /// compiler-enforced; V1b will consume these envelopes directly,
    /// so the type system must do the work.
    /// </summary>
    public class JobResultRecordInvariantsTests
    {
        // ─── JobSubmitResult (manager output, Rook-side JobId) ────────

        [Fact]
        public void Submit_Ok_constructs_with_job_id_and_no_error()
        {
            var jobId = Guid.NewGuid();

            var r = JobSubmitResult.Ok(jobId, VideoJobState.Queued);

            Assert.Equal(jobId, r.JobId);
            Assert.Equal(VideoJobState.Queued, r.State);
            Assert.Null(r.Error);
        }

        [Fact]
        public void Submit_Ok_rejects_empty_guid()
        {
            Assert.Throws<ArgumentException>(() =>
                JobSubmitResult.Ok(Guid.Empty, VideoJobState.Queued));
        }

        [Fact]
        public void Submit_Fail_carries_error_and_no_job_id()
        {
            var err = new VideoJobError(
                VideoErrorCode.DependencyUnavailable, "auth", Retryable: true);

            var r = JobSubmitResult.Fail(err);

            Assert.Null(r.JobId);
            Assert.Same(err, r.Error);
            Assert.Equal(VideoJobState.Error, r.State);
        }

        [Fact]
        public void Submit_Fail_rejects_null_error()
        {
            Assert.Throws<ArgumentNullException>(() =>
                JobSubmitResult.Fail(null!));
        }

        // ─── JobStatusResult ──────────────────────────────────────────

        [Fact]
        public void Status_InFlight_accepts_inflight_state()
        {
            var r = JobStatusResult.InFlight(
                VideoJobState.Polling,
                new VideoJobProgress(50, "polling", null));

            Assert.Equal(VideoJobState.Polling, r.State);
            Assert.NotNull(r.Progress);
            Assert.Null(r.ResultArtifactId);
            Assert.Null(r.Error);
        }

        [Theory]
        [InlineData(VideoJobState.Complete)]
        [InlineData(VideoJobState.Error)]
        [InlineData(VideoJobState.Cancelled)]
        [InlineData(VideoJobState.Interrupted)]
        public void Status_InFlight_rejects_terminal_states(VideoJobState terminal)
        {
            Assert.Throws<ArgumentException>(() =>
                JobStatusResult.InFlight(terminal, progress: null));
        }

        [Fact]
        public void Status_Complete_carries_artifact_id_and_no_error()
        {
            var id = Guid.NewGuid();

            var r = JobStatusResult.Complete(id);

            Assert.Equal(VideoJobState.Complete, r.State);
            Assert.Equal(id, r.ResultArtifactId);
            Assert.Null(r.Error);
        }

        [Fact]
        public void Status_Complete_rejects_empty_artifact_id()
        {
            Assert.Throws<ArgumentException>(() =>
                JobStatusResult.Complete(Guid.Empty));
        }

        [Theory]
        [InlineData(VideoJobState.Error)]
        [InlineData(VideoJobState.Cancelled)]
        [InlineData(VideoJobState.Interrupted)]
        public void Status_Failed_accepts_terminal_failure_states(
            VideoJobState terminal)
        {
            var err = new VideoJobError(
                VideoErrorCode.ExecutionFailed, "boom", Retryable: true);

            var r = JobStatusResult.Failed(terminal, err);

            Assert.Equal(terminal, r.State);
            Assert.Same(err, r.Error);
            Assert.Null(r.ResultArtifactId);
        }

        [Theory]
        [InlineData(VideoJobState.Queued)]
        [InlineData(VideoJobState.Polling)]
        [InlineData(VideoJobState.Complete)]
        public void Status_Failed_rejects_non_terminal_failure_states(
            VideoJobState wrong)
        {
            var err = new VideoJobError(
                VideoErrorCode.ExecutionFailed, "boom", Retryable: true);

            Assert.Throws<ArgumentException>(() =>
                JobStatusResult.Failed(wrong, err));
        }

        // ─── JobCancelResult ──────────────────────────────────────────

        [Fact]
        public void Cancel_Ok_carries_state_and_no_error()
        {
            var r = JobCancelResult.Ok(VideoJobState.Cancelled);

            Assert.Equal(VideoJobState.Cancelled, r.State);
            Assert.Null(r.Error);
        }

        [Fact]
        public void Cancel_Fail_carries_error()
        {
            var err = new VideoJobError(
                VideoErrorCode.DependencyUnavailable, "net down", Retryable: true);

            var r = JobCancelResult.Fail(err);

            Assert.Same(err, r.Error);
        }

        [Fact]
        public void Cancel_Fail_rejects_null_error()
        {
            Assert.Throws<ArgumentNullException>(() =>
                JobCancelResult.Fail(null!));
        }

        // ─── JobFetchResult ───────────────────────────────────────────

        [Fact]
        public void Fetch_Complete_carries_artifact_id_and_files_and_no_error()
        {
            var id = Guid.NewGuid();
            var files = new[]
            {
                new JobResultFile(VideoMediaRoles.Video, "primary.mp4"),
            };

            var r = JobFetchResult.Complete(id, files);

            Assert.Equal(VideoJobState.Complete, r.State);
            Assert.Equal(id, r.ResultArtifactId);
            Assert.NotNull(r.Files);
            Assert.Single(r.Files!);
            Assert.Null(r.Error);
        }

        [Fact]
        public void Fetch_Complete_rejects_empty_artifact_id()
        {
            var files = new[]
            {
                new JobResultFile(VideoMediaRoles.Video, "primary.mp4"),
            };

            Assert.Throws<ArgumentException>(() =>
                JobFetchResult.Complete(Guid.Empty, files));
        }

        [Fact]
        public void Fetch_Complete_rejects_empty_files()
        {
            Assert.Throws<ArgumentException>(() =>
                JobFetchResult.Complete(Guid.NewGuid(), Array.Empty<JobResultFile>()));
        }

        [Fact]
        public void Fetch_Failed_carries_error_and_no_artifact_id()
        {
            var err = new VideoJobError(
                VideoErrorCode.ExecutionFailed, "fetched too early", Retryable: true);

            var r = JobFetchResult.Failed(VideoJobState.Polling, err);

            Assert.Equal(VideoJobState.Polling, r.State);
            Assert.Null(r.ResultArtifactId);
            Assert.Null(r.Files);
            Assert.Same(err, r.Error);
        }

        [Fact]
        public void Fetch_Failed_rejects_Complete_state()
        {
            var err = new VideoJobError(
                VideoErrorCode.ExecutionFailed, "bad", Retryable: true);

            Assert.Throws<ArgumentException>(() =>
                JobFetchResult.Failed(VideoJobState.Complete, err));
        }
    }
}
