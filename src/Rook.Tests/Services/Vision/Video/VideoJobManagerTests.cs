using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using GenErrorCode = Rook.Services.Vision.Generation.GenerationErrorCode;
using GenInlineArtifactBody = Rook.Services.Vision.Generation.InlineArtifactBody;
using GenProviderResultEnvelope = Rook.Services.Vision.Generation.ProviderResultEnvelope;
using GenResultArtifact = Rook.Services.Vision.Generation.ResultArtifact;
using GenSuccessResultOutcome = Rook.Services.Vision.Generation.SuccessResultOutcome;
using GenSyncSubmitOutcome = Rook.Services.Vision.Generation.SyncSubmitOutcome;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoJobManagerTests : IDisposable
    {
        private readonly string _artifactRoot;
        private readonly ArtifactStore _artifactStore;
        private readonly FakeVideoJobLedger _ledger = new();
        private readonly FakeVideoJobClock _clock = new();
        private readonly FakeVideoJobIdGenerator _idGen = new();
        private readonly FakeVideoProvider _provider = new();
        private readonly FakeVideoMediaResolver _resolver = new();
        private readonly IVideoProviderRegistry _registry;
        private readonly VideoCostEstimator _estimator = new();
        private readonly ResolvedVideoModel _resolvedModel;

        public VideoJobManagerTests()
        {
            _artifactRoot = Path.Combine(
                Path.GetTempPath(),
                $"rook-mgr-test-{Guid.NewGuid():N}");
            _artifactStore = new ArtifactStore(_artifactRoot);
            _registry = TestVideoFixtures.RegistryWithVeo(_provider);
            _resolvedModel = TestVideoFixtures.VeoLiteResolved(_provider);
        }

        public void Dispose()
        {
            if (Directory.Exists(_artifactRoot))
                Directory.Delete(_artifactRoot, recursive: true);
        }

        private VideoJobManager Manager(
            TimeSpan? pollInterval = null,
            IVideoCostEstimator? estimator = null,
            VideoArtifactMaterializer? materializer = null,
            IVideoPosterSidecarProducer? posterProducer = null,
            IVideoFrameSidecarProducer? frameProducer = null,
            IVideoProviderRegistry? registry = null,
            IVideoJobLedger? ledger = null) =>
            new(
                registry: registry ?? _registry,
                mediaResolver: _resolver,
                ledger: ledger ?? _ledger,
                estimator: estimator ?? _estimator,
                artifactStore: _artifactStore,
                clock: _clock,
                idGenerator: _idGen,
                pollInterval: pollInterval ?? TimeSpan.FromMilliseconds(5),
                maxConcurrentJobs: VideoJobManager.DefaultMaxConcurrentJobs,
                materializer: materializer,
                posterProducer: posterProducer ?? new FakePosterProducer(_artifactStore),
                frameProducer: frameProducer ?? new FakeFrameProducer(_artifactStore));

        private VideoGenerationRequest T2vRequest() =>
            TestVideoFixtures.DefaultT2vRequest();

        private VideoCostEstimate EstimateFor(VideoGenerationRequest req) =>
            _estimator.Estimate(_resolvedModel, req).Estimate!;

        private static byte[] FakeMp4 => new byte[] { 0x00, 0x00, 0x00, 0x18, 0x66, 0x74, 0x79, 0x70 };

        // Helper: poll the manager until the job reaches a terminal state
        // or the deadline passes. Returns the final status.
        private async Task<JobStatusResult> WaitForTerminalAsync(
            VideoJobManager mgr, Guid jobId,
            TimeSpan? deadline = null)
        {
            var stop = DateTime.UtcNow + (deadline ?? TimeSpan.FromSeconds(5));
            JobStatusResult? last = null;
            while (DateTime.UtcNow < stop)
            {
                last = await mgr.GetStatusAsync(jobId, CancellationToken.None);
                if (IsTerminal(last.State)) return last;
                await Task.Delay(10);
            }
            return last ?? throw new TimeoutException("Never observed any status.");
        }

        private static bool IsTerminal(VideoJobState s) =>
            s is VideoJobState.Complete
              or VideoJobState.Error
              or VideoJobState.Cancelled
              or VideoJobState.Interrupted;

        private static async Task WaitForSignalAsync(Task signal, string timeoutMessage)
        {
            var timeout = Task.Delay(TimeSpan.FromSeconds(2));
            if (await Task.WhenAny(signal, timeout) != signal)
                throw new TimeoutException(timeoutMessage);

            await signal.ConfigureAwait(false);
        }

        private async Task WaitUntilProviderJobIdAsync(Guid jobId)
        {
            var deadline = DateTime.UtcNow + TimeSpan.FromSeconds(2);
            while (DateTime.UtcNow < deadline)
            {
                if (_ledger.AllRecords.Any(r => r.JobId == jobId && r.ProviderJobId is not null))
                    return;
                await Task.Delay(10);
            }

            throw new TimeoutException("Provider job id was not persisted.");
        }

        // ─── Submit happy path ────────────────────────────────────────

        [Fact]
        public async Task Submit_returns_jobId_immediately_with_Queued_state()
        {
            var preMintedJobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(preMintedJobId);
            ConfigureProviderHappyPath();

            var mgr = Manager();
            var submit = await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);

            Assert.Equal(preMintedJobId, submit.JobId);
            Assert.Equal(VideoJobState.Queued, submit.State);
            Assert.Null(submit.Error);
        }

        [Fact]
        public async Task Initial_ledger_record_has_null_provider_job_id()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);

            // Block provider.SubmitAsync so we can observe initial state
            // before the background task transitions it.
            var gate = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            _provider.OnSubmit = (_, _) =>
            {
                gate.Task.GetAwaiter().GetResult();
                return FakeVideoProvider.SubmitQueued("op-123");
            };
            _provider.OnGetStatus = handle =>
                FakeVideoProvider.StatusComplete(handle, "https://veo/result/x");
            _provider.OnFetchResult = _ =>
                FakeVideoProvider.ResultOk(FakeMp4, "video/mp4");

            var mgr = Manager();
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);

            // The first record (Queued) is appended synchronously
            // during SubmitAsync and is observable before we release
            // the gate.
            var initial = _ledger.AllRecords.First(r => r.JobId == jobId);
            Assert.Equal(VideoJobState.Queued, initial.State);
            Assert.Null(initial.ProviderJobId);
            Assert.Null(initial.ProviderResultToken);
            Assert.Null(initial.ResultArtifactId);

            gate.SetResult(true);
            await WaitForTerminalAsync(mgr, jobId);
        }

        [Fact]
        public async Task ProviderJobId_appears_after_provider_submit_returns()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();

            var mgr = Manager();
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            await WaitForTerminalAsync(mgr, jobId);

            // At least one record after the initial Queued must have
            // ProviderJobId set — that's the post-submit transition.
            var withProvId = _ledger.AllRecords
                .Where(r => r.JobId == jobId && r.ProviderJobId is not null)
                .ToList();

            Assert.NotEmpty(withProvId);
            Assert.All(withProvId, r => Assert.Equal("op-123", r.ProviderJobId));
        }

        [Fact]
        public async Task ProviderResultToken_appears_after_provider_complete()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();

            var mgr = Manager();
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            await WaitForTerminalAsync(mgr, jobId);

            var withToken = _ledger.AllRecords
                .Where(r => r.JobId == jobId && r.ProviderResultToken is not null)
                .ToList();

            Assert.NotEmpty(withToken);
            Assert.All(withToken, r => Assert.Equal("https://veo/result/x", r.ProviderResultToken));
        }

        [Fact]
        public async Task Happy_path_reaches_Complete_with_artifact_id()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();

            var mgr = Manager();
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            Assert.NotNull(final.ResultArtifactId);

            var artifact = _artifactStore.Get(final.ResultArtifactId!.Value);
            Assert.NotNull(artifact);
            Assert.Equal("generated_video", artifact!.Kind);
            Assert.Single(artifact.Files);
            Assert.Equal("video", artifact.Files[0].Role);
        }

        [Fact]
        public async Task Complete_video_publishes_poster_before_Complete_when_poster_succeeds()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();
            var posterStarted = new TaskCompletionSource<Guid>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            var releasePoster = new TaskCompletionSource<bool>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            var posterProducer = new FakePosterProducer(_artifactStore)
            {
                OnPublishAsync = async (artifact, _) =>
                {
                    posterStarted.TrySetResult(artifact.Id);
                    await releasePoster.Task.ConfigureAwait(false);
                    new VideoSidecarPublisher(_artifactStore).Publish(
                        artifact.Id,
                        VideoMediaRoles.Poster,
                        new byte[] { 8, 8, 8 },
                        "jpg");
                    return VideoPosterSidecarResult.From(
                        VideoPosterSidecarResultCode.Published,
                        artifact.Id);
                },
            };

            var mgr = Manager(posterProducer: posterProducer);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);

            await WaitForSignalAsync(
                posterStarted.Task,
                "Poster publisher did not start before job completion.");
            var status = await mgr.GetStatusAsync(jobId, CancellationToken.None);
            Assert.NotEqual(VideoJobState.Complete, status.State);
            Assert.DoesNotContain(
                _ledger.AllRecords.Where(r => r.JobId == jobId),
                r => r.State == VideoJobState.Complete);
            Assert.Equal(
                VideoJobState.Saving,
                _ledger.AllRecords.Last(r => r.JobId == jobId).State);

            releasePoster.SetResult(true);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            var posterArtifactId = await posterStarted.Task;
            Assert.Equal(posterArtifactId, final.ResultArtifactId);
            var artifact = _artifactStore.Get(final.ResultArtifactId!.Value);
            Assert.NotNull(artifact);
            Assert.Contains(artifact!.Files, f => f.Role == VideoMediaRoles.Video);
            Assert.Contains(artifact.Files, f => f.Role == VideoMediaRoles.Poster);
        }

        [Fact]
        public async Task Complete_video_still_completes_when_poster_fails()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();
            var posterProducer = new FakePosterProducer(_artifactStore)
            {
                OnPublishAsync = (artifact, _) => Task.FromResult(
                    VideoPosterSidecarResult.From(
                        VideoPosterSidecarResultCode.PublishFailed,
                        artifact.Id)),
            };

            var mgr = Manager(posterProducer: posterProducer);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            Assert.NotNull(final.ResultArtifactId);
            var artifact = _artifactStore.Get(final.ResultArtifactId!.Value);
            Assert.NotNull(artifact);
            Assert.Contains(artifact!.Files, f => f.Role == VideoMediaRoles.Video);
            Assert.DoesNotContain(artifact.Files, f => f.Role == VideoMediaRoles.Poster);
            Assert.DoesNotContain(
                _ledger.AllRecords.Where(r => r.JobId == jobId),
                r => r.State == VideoJobState.Error);
        }

        [Fact]
        public async Task Complete_video_still_completes_when_poster_duplicate_is_skipped()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();
            var posterProducer = new FakePosterProducer(_artifactStore)
            {
                OnPublishAsync = (artifact, _) => Task.FromResult(
                    VideoPosterSidecarResult.From(
                        VideoPosterSidecarResultCode.SkippedAlreadyExists,
                        artifact.Id)),
            };

            var mgr = Manager(posterProducer: posterProducer);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            Assert.Single(posterProducer.ArtifactIds);
            Assert.DoesNotContain(
                _ledger.AllRecords.Where(r => r.JobId == jobId),
                r => r.State == VideoJobState.Error || r.State == VideoJobState.Cancelled);
        }

        [Fact]
        public async Task Complete_video_still_completes_when_poster_stage_observes_cancellation()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();
            var posterProducer = new FakePosterProducer(_artifactStore)
            {
                OnPublishAsync = (_, _) => throw new OperationCanceledException(),
            };

            var mgr = Manager(posterProducer: posterProducer);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            Assert.NotNull(final.ResultArtifactId);
            Assert.DoesNotContain(
                _ledger.AllRecords.Where(r => r.JobId == jobId),
                r => r.State == VideoJobState.Cancelled);
        }

        [Fact]
        public async Task Sync_submit_completion_uses_same_poster_finalization()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            _provider.OnSubmit = (_, _) =>
                new GenSyncSubmitOutcome(
                    new GenSuccessResultOutcome(VideoSuccessEnvelope(FakeMp4, "video/mp4")));
            var posterProducer = new FakePosterProducer(_artifactStore);

            var mgr = Manager(posterProducer: posterProducer);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            Assert.NotNull(final.ResultArtifactId);
            Assert.Single(posterProducer.ArtifactIds);
            Assert.Equal(final.ResultArtifactId.Value, posterProducer.ArtifactIds[0]);
        }

        [Fact]
        public async Task Complete_video_publishes_frame_sidecars_before_Complete()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();
            var frameStarted = new TaskCompletionSource<Guid>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            var releaseFrameSidecars = new TaskCompletionSource<bool>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            var frameProducer = new FakeFrameProducer(_artifactStore)
            {
                OnPublishAsync = async (artifact, _) =>
                {
                    frameStarted.TrySetResult(artifact.Id);
                    await releaseFrameSidecars.Task.ConfigureAwait(false);
                    return FakeFrameProducer.Result(
                        artifact.Id,
                        VideoFrameSidecarRoleResultCode.Published,
                        VideoFrameSidecarRoleResultCode.Published);
                },
            };

            var mgr = Manager(frameProducer: frameProducer);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);

            await WaitForSignalAsync(
                frameStarted.Task,
                "Frame sidecar producer did not start before job completion.");
            var status = await mgr.GetStatusAsync(jobId, CancellationToken.None);
            Assert.NotEqual(VideoJobState.Complete, status.State);
            Assert.DoesNotContain(
                _ledger.AllRecords.Where(r => r.JobId == jobId),
                r => r.State == VideoJobState.Complete);
            Assert.Equal(
                VideoJobState.Saving,
                _ledger.AllRecords.Last(r => r.JobId == jobId).State);

            releaseFrameSidecars.SetResult(true);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            var frameArtifactId = await frameStarted.Task;
            Assert.Equal(frameArtifactId, final.ResultArtifactId);
            Assert.Single(frameProducer.ArtifactIds);
            Assert.Equal(final.ResultArtifactId.Value, frameProducer.ArtifactIds[0]);
        }

        [Fact]
        public async Task Complete_video_still_completes_when_frame_sidecars_partially_fail()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();
            var frameProducer = new FakeFrameProducer(_artifactStore)
            {
                OnPublishAsync = (artifact, _) => Task.FromResult(
                    FakeFrameProducer.Result(
                        artifact.Id,
                        VideoFrameSidecarRoleResultCode.Published,
                        VideoFrameSidecarRoleResultCode.ExtractionFailed)),
            };

            var mgr = Manager(frameProducer: frameProducer);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            Assert.NotNull(final.ResultArtifactId);
            Assert.Single(frameProducer.ArtifactIds);
            Assert.DoesNotContain(
                _ledger.AllRecords.Where(r => r.JobId == jobId),
                r => r.State == VideoJobState.Error || r.State == VideoJobState.Cancelled);
        }

        [Fact]
        public async Task Complete_video_still_completes_when_frame_stage_observes_cancellation()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();
            var frameProducer = new FakeFrameProducer(_artifactStore)
            {
                OnPublishAsync = (_, _) => throw new OperationCanceledException(),
            };

            var mgr = Manager(frameProducer: frameProducer);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            Assert.NotNull(final.ResultArtifactId);
            Assert.DoesNotContain(
                _ledger.AllRecords.Where(r => r.JobId == jobId),
                r => r.State == VideoJobState.Cancelled);
        }

        [Fact]
        public async Task Sync_submit_completion_uses_same_frame_sidecar_finalization()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            _provider.OnSubmit = (_, _) =>
                new GenSyncSubmitOutcome(
                    new GenSuccessResultOutcome(VideoSuccessEnvelope(FakeMp4, "video/mp4")));
            var frameProducer = new FakeFrameProducer(_artifactStore);

            var mgr = Manager(frameProducer: frameProducer);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            Assert.NotNull(final.ResultArtifactId);
            Assert.Single(frameProducer.ArtifactIds);
            Assert.Equal(final.ResultArtifactId.Value, frameProducer.ArtifactIds[0]);
        }

        [Fact]
        public async Task Remote_mp4_result_materializes_to_generated_video_artifact()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            _provider.OnSubmit = (_, _) => FakeVideoProvider.SubmitQueued("op-remote");
            _provider.OnGetStatus = handle =>
                FakeVideoProvider.StatusComplete(handle, "https://veo/result/remote");
            _provider.OnFetchResult = _ =>
                FakeVideoProvider.ResultRemote("https://cdn.example.test/out.mp4", "video/mp4");
            var materializer = new VideoArtifactMaterializer(
                new StaticVideoResponseHandler(
                    HttpStatusCode.OK,
                    new byte[] { 9, 8, 7, 6 },
                    "video/mp4"),
                maxGeneratedVideoBytes: 1024);

            var mgr = Manager(materializer: materializer);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            Assert.NotNull(final.ResultArtifactId);
            var artifact = _artifactStore.Get(final.ResultArtifactId!.Value);
            Assert.NotNull(artifact);
            Assert.Equal("generated_video", artifact!.Kind);
            Assert.Single(artifact.Files);
            Assert.Equal("video", artifact.Files[0].Role);
            Assert.Equal("video.mp4", artifact.Files[0].Path);
            var blobPath = _artifactStore.GetBlobAbsolutePath(artifact.Id, "video");
            Assert.Equal(new byte[] { 9, 8, 7, 6 }, File.ReadAllBytes(blobPath));
        }

        [Fact]
        public async Task Remote_materialization_failure_writes_durable_Error_not_Complete()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            _provider.OnSubmit = (_, _) => FakeVideoProvider.SubmitQueued("op-remote-fail");
            _provider.OnGetStatus = handle =>
                FakeVideoProvider.StatusComplete(handle, "https://veo/result/remote");
            _provider.OnFetchResult = _ =>
                FakeVideoProvider.ResultRemote("https://cdn.example.test/out.mp4", "video/mp4");
            var materializer = new VideoArtifactMaterializer(
                new StaticVideoResponseHandler(HttpStatusCode.ServiceUnavailable),
                maxGeneratedVideoBytes: 1024);

            var mgr = Manager(materializer: materializer);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Error, final.State);
            Assert.NotNull(final.Error);
            Assert.Equal(VideoErrorCode.DependencyUnavailable, final.Error!.Code);
            var latest = _ledger.AllRecords.Last(r => r.JobId == jobId);
            Assert.Equal(VideoJobState.Error, latest.State);
            Assert.Null(latest.ResultArtifactId);
            Assert.DoesNotContain(
                _ledger.AllRecords,
                r => r.JobId == jobId && r.State == VideoJobState.Complete);
        }

        [Fact]
        public async Task Materialization_failure_preserves_provider_handle_metadata()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            var queuedHandle = new ProviderJobHandle(
                providerJobId: "queue/123",
                statusUrl: new Uri("https://queue.example.test/status/123"),
                responseUrl: new Uri("https://queue.example.test/response/123"),
                cancelUrl: new Uri("https://queue.example.test/cancel/123"),
                cancelHttpMethod: "PUT",
                providerMetadata: new Dictionary<string, JsonNode>
                {
                    ["queue_position"] = JsonValue.Create(2)!,
                });
            var completeHandle = queuedHandle.WithResultToken("https://queue.example.test/result/123");
            _provider.OnSubmit = (_, _) => new QueuedSubmitOutcome(queuedHandle);
            _provider.OnGetStatus = _ => new ProviderCompleteStatusOutcome(completeHandle);
            _provider.OnFetchResult = _ =>
                FakeVideoProvider.ResultRemote("https://cdn.example.test/out.mp4", "video/mp4");
            var materializer = new VideoArtifactMaterializer(
                new StaticVideoResponseHandler(HttpStatusCode.ServiceUnavailable),
                maxGeneratedVideoBytes: 1024);

            var mgr = Manager(materializer: materializer);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            await WaitForTerminalAsync(mgr, jobId);

            var latest = _ledger.AllRecords.Last(r => r.JobId == jobId);
            Assert.Equal(VideoJobState.Error, latest.State);
            Assert.Equal("queue/123", latest.ProviderJobId);
            Assert.Equal("https://queue.example.test/result/123", latest.ProviderResultToken);
            Assert.NotNull(latest.Extensions);
            var handle = latest.ProviderHandle;
            Assert.NotNull(handle);
            Assert.Equal(new Uri("https://queue.example.test/status/123"), handle!.StatusUrl);
            Assert.Equal(new Uri("https://queue.example.test/response/123"), handle.ResponseUrl);
            Assert.Equal(new Uri("https://queue.example.test/cancel/123"), handle.CancelUrl);
            Assert.Equal("PUT", handle.CancelHttpMethod);
            Assert.NotNull(handle.ProviderMetadata);
            Assert.Equal(2, handle.ProviderMetadata!["queue_position"].GetValue<int>());
        }

        [Fact]
        public async Task Inline_video_over_materializer_cap_transitions_to_Error()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            _provider.OnSubmit = (_, _) => FakeVideoProvider.SubmitQueued("op-inline-cap");
            _provider.OnGetStatus = handle =>
                FakeVideoProvider.StatusComplete(handle, "https://veo/result/inline");
            _provider.OnFetchResult = _ =>
                FakeVideoProvider.ResultOk(new byte[] { 1, 2, 3, 4 }, "video/mp4");
            var materializer = new VideoArtifactMaterializer(maxGeneratedVideoBytes: 3);

            var mgr = Manager(materializer: materializer);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Error, final.State);
            Assert.NotNull(final.Error);
            Assert.Equal(VideoErrorCode.ExecutionFailed, final.Error!.Code);
            Assert.Contains("exceeded the maximum allowed size", final.Error.Message);
            Assert.DoesNotContain(
                _ledger.AllRecords,
                r => r.JobId == jobId && r.State == VideoJobState.Complete);
        }

        // ─── Validation / estimator / resolver failures ──────────────

        [Fact]
        public async Task Submit_with_invalid_model_returns_Fail_no_ledger_write()
        {
            var mgr = Manager();
            var bad = T2vRequest().With(model: "veo-9000");

            var result = await mgr.SubmitAsync(bad, CancellationToken.None);

            Assert.NotNull(result.Error);
            Assert.Null(result.JobId);
            Assert.Empty(_ledger.AllRecords);
        }

        [Fact]
        public async Task Submit_with_path_media_ref_returns_InvalidRequest()
        {
            // Resolver throws NotSupportedException for Path-kind refs;
            // manager translates to InvalidRequest before any ledger write.
            _resolver.OnResolve = mediaRef =>
                mediaRef.Kind == MediaRefKind.Path
                    ? throw new NotSupportedException("Path unsupported in V1b")
                    : new ResolvedMedia(new byte[] { 1 }, "image/png");

            var mgr = Manager();
            var req = T2vRequest()
                .With(
                    mode: VideoMode.I2V,
                    startFrame: MediaRef.ForPath(@"C:\nope.png", VideoMediaRoles.Image),
                    options: new VeoOptions(PersonGenerationPolicy.AllowAdult),
                    model: "veo-3.1-generate-preview")
                .WithPrompt(null);

            var result = await mgr.SubmitAsync(req, CancellationToken.None);

            Assert.NotNull(result.Error);
            Assert.Equal(VideoErrorCode.InvalidRequest, result.Error!.Code);
            Assert.Empty(_ledger.AllRecords);
        }

        [Fact]
        public async Task Submit_preserves_generic_estimator_error_for_http_projection()
        {
            var genericError = new Rook.Services.Vision.Generation.GenerationError(
                GenErrorCode.QuotaExceeded,
                "Pricing quota exhausted.",
                Retryable: true,
                Field: "quota",
                ProviderErrorCode: "rate_limit_exceeded",
                ProviderDetail: new Dictionary<string, JsonNode>
                {
                    ["detail"] = JsonValue.Create("pricing detail")!,
                });
            var mgr = Manager(estimator: new FailingEstimator(genericError));

            var result = await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);

            Assert.Null(result.JobId);
            Assert.Same(genericError, result.GenerationError);
            Assert.NotNull(result.Error);
            Assert.Equal(VideoErrorCode.DependencyUnavailable, result.Error!.Code);
            Assert.Empty(_ledger.AllRecords);
        }

        // ─── Provider-side errors ────────────────────────────────────

        [Fact]
        public async Task Provider_submit_failure_transitions_to_Error()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            _provider.OnSubmit = (_, _) => FakeVideoProvider.SubmitFailed(new VideoJobError(
                Code: VideoErrorCode.DependencyUnavailable,
                Message: "auth bad",
                Retryable: false));

            var mgr = Manager();
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Error, final.State);
            Assert.NotNull(final.Error);
            Assert.Equal(VideoErrorCode.DependencyUnavailable, final.Error!.Code);
        }

        [Fact]
        public async Task Provider_fetch_success_without_video_artifact_transitions_to_typed_Error()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            _provider.OnSubmit = (_, _) => FakeVideoProvider.SubmitQueued("op-123");
            _provider.OnGetStatus = handle =>
                FakeVideoProvider.StatusComplete(handle, "https://veo/result/x");
            _provider.OnFetchResult = _ =>
                new GenSuccessResultOutcome(NonVideoSuccessEnvelope());

            var mgr = Manager();
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Error, final.State);
            Assert.NotNull(final.Error);
            Assert.Equal(VideoErrorCode.ExecutionFailed, final.Error!.Code);
            Assert.Equal(
                "Provider result envelope did not contain an inline video artifact.",
                final.Error.Message);
            Assert.DoesNotContain("Unexpected error during job", final.Error.Message);
        }

        [Fact]
        public async Task Sync_submit_success_without_video_artifact_transitions_to_typed_Error()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            _provider.OnSubmit = (_, _) =>
                new GenSyncSubmitOutcome(
                    new GenSuccessResultOutcome(NonVideoSuccessEnvelope()));

            var mgr = Manager();
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Error, final.State);
            Assert.NotNull(final.Error);
            Assert.Equal(VideoErrorCode.ExecutionFailed, final.Error!.Code);
            Assert.Equal(
                "Provider result envelope did not contain an inline video artifact.",
                final.Error.Message);
            Assert.DoesNotContain("Unexpected error during job", final.Error.Message);
        }

        // ─── Cancel ──────────────────────────────────────────────────

        [Fact]
        public async Task Cancel_unknown_jobId_returns_Fail()
        {
            var mgr = Manager();

            var result = await mgr.CancelAsync(Guid.NewGuid(), CancellationToken.None);

            Assert.NotNull(result.Error);
            Assert.Equal(VideoErrorCode.InvalidRequest, result.Error!.Code);
        }

        [Fact]
        public async Task Cancel_in_flight_calls_provider_cancel_with_persisted_provider_job_id()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);

            // Provider submits ok, polls forever (so we can cancel)
            _provider.OnSubmit = (_, _) =>
                FakeVideoProvider.SubmitQueued("op-cancel-test");
            _provider.OnGetStatus = _ => FakeVideoProvider.StatusInFlight(10);

            string? cancelCalledWith = null;
            _provider.OnCancel = handle =>
            {
                cancelCalledWith = handle.ProviderJobId;
                return FakeVideoProvider.CancelOk();
            };

            var mgr = Manager(pollInterval: TimeSpan.FromMilliseconds(20));
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);

            // Wait until provider_job_id is persisted (post-submit).
            var deadline = DateTime.UtcNow + TimeSpan.FromSeconds(2);
            while (DateTime.UtcNow < deadline)
            {
                if (_ledger.AllRecords.Any(r => r.JobId == jobId && r.ProviderJobId is not null))
                    break;
                await Task.Delay(10);
            }

            var cancel = await mgr.CancelAsync(jobId, CancellationToken.None);

            Assert.Equal(VideoJobState.Cancelled, cancel.State);
            Assert.Equal("op-cancel-test", cancelCalledWith);
        }

        [Fact]
        public async Task Active_polling_passes_resolved_model_id_to_model_aware_provider()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);

            var statusCalled = new TaskCompletionSource<bool>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            var fetchCalled = new TaskCompletionSource<bool>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            _provider.OnSubmit = (_, _) =>
                FakeVideoProvider.SubmitQueued("op-model-status");
            _provider.OnGetStatus = _ =>
                throw new InvalidOperationException("Legacy status should not be called.");
            _provider.OnGetStatusForModel = (modelId, handle) =>
            {
                Assert.Equal(TestVideoFixtures.DefaultModelId, modelId);
                Assert.Equal("op-model-status", handle.ProviderJobId);
                statusCalled.TrySetResult(true);
                return FakeVideoProvider.StatusComplete(handle, "model-aware-result-token");
            };
            _provider.OnFetchResult = _ =>
                throw new InvalidOperationException("Legacy fetch should not be called.");
            _provider.OnFetchResultForModel = (modelId, handle) =>
            {
                Assert.Equal(TestVideoFixtures.DefaultModelId, modelId);
                Assert.Equal("op-model-status", handle.ProviderJobId);
                Assert.Equal("model-aware-result-token", handle.ProviderResultToken);
                fetchCalled.TrySetResult(true);
                return FakeVideoProvider.ResultOk(FakeMp4, "video/mp4");
            };

            using var mgr = Manager(pollInterval: TimeSpan.FromMilliseconds(20));
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            await WaitForSignalAsync(
                statusCalled.Task,
                "Background job did not poll through the model-aware provider.");
            await WaitForSignalAsync(
                fetchCalled.Task,
                "Background job did not fetch through the model-aware provider.");

            Assert.Equal(VideoJobState.Complete, final.State);
            var call = _provider.RecordedCalls.First(
                c => c.Method == "GetStatusForModel");
            var payload = Assert.IsType<FakeVideoProvider.ModelAwareCall>(call.Payload);
            Assert.Equal(TestVideoFixtures.DefaultModelId, payload.ModelId);
            Assert.Equal("op-model-status", payload.ProviderJobId);
            var fetchCall = Assert.Single(_provider.RecordedCalls,
                c => c.Method == "FetchResultForModel");
            var fetchPayload = Assert.IsType<FakeVideoProvider.ModelAwareCall>(fetchCall.Payload);
            Assert.Equal(TestVideoFixtures.DefaultModelId, fetchPayload.ModelId);
            Assert.Equal("op-model-status", fetchPayload.ProviderJobId);
            Assert.Equal("model-aware-result-token", fetchPayload.ProviderResultToken);
            Assert.DoesNotContain(_provider.RecordedCalls,
                c => c.Method == "FetchResult");
        }

        [Fact]
        public async Task Active_cancel_passes_resolved_model_id_to_model_aware_provider()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);

            var cancelCalled = new TaskCompletionSource<bool>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            _provider.OnSubmit = (_, _) =>
                FakeVideoProvider.SubmitQueued("op-model-cancel");
            _provider.OnGetStatus = _ => FakeVideoProvider.StatusInFlight(10);
            _provider.OnCancel = _ =>
                throw new InvalidOperationException("Legacy cancel should not be called.");
            _provider.OnCancelForModel = (modelId, handle) =>
            {
                Assert.Equal(TestVideoFixtures.DefaultModelId, modelId);
                Assert.Equal("op-model-cancel", handle.ProviderJobId);
                cancelCalled.TrySetResult(true);
                return FakeVideoProvider.CancelOk();
            };

            using var mgr = Manager(pollInterval: TimeSpan.FromMilliseconds(20));
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            await WaitUntilProviderJobIdAsync(jobId);

            var result = await mgr.CancelAsync(jobId, CancellationToken.None);

            Assert.Equal(VideoJobState.Cancelled, result.State);
            Assert.Null(result.Error);
            await WaitForSignalAsync(
                cancelCalled.Task,
                "Cancel did not use the model-aware provider.");
            var call = Assert.Single(_provider.RecordedCalls,
                c => c.Method == "CancelForModel");
            var payload = Assert.IsType<FakeVideoProvider.ModelAwareCall>(call.Payload);
            Assert.Equal(TestVideoFixtures.DefaultModelId, payload.ModelId);
            Assert.Equal("op-model-cancel", payload.ProviderJobId);
        }

        // ─── Codex round 6: cancel correctness invariants ────────────
        //
        // These pin the cost-leak prevention contract that v3.1 D4 +
        // V1b's `provider_job_id` persistence were designed to enforce:
        // Interrupted jobs must remain remote-cancellable, and the
        // manager must not claim cancellation when the provider rejects
        // the cancel.

        [Fact]
        public async Task Cancel_interrupted_job_calls_provider_cancel_with_persisted_id()
        {
            var jobId = Guid.NewGuid();
            // Pre-populate ledger with an Interrupted record carrying
            // provider_job_id (the post-Reconcile state).
            var prior = VideoJobRecordFactory.From(
                jobId, T2vRequest(), _resolvedModel,
                EstimateFor(T2vRequest()),
                VideoJobState.Polling, _clock.UtcNow());
            prior = VideoJobRecordFactory.WithState(
                prior, VideoJobState.Polling, _clock.UtcNow(),
                providerJobId: "op-stale-456");
            prior = VideoJobRecordFactory.WithState(
                prior, VideoJobState.Interrupted, _clock.UtcNow(),
                error: new VideoJobError(VideoErrorCode.Interrupted, "x", Retryable: true));
            _ledger.Append(prior);

            string? cancelCalledWith = null;
            _provider.OnCancel = handle =>
            {
                cancelCalledWith = handle.ProviderJobId;
                return FakeVideoProvider.CancelOk();
            };

            var mgr = Manager();
            var result = await mgr.CancelAsync(jobId, CancellationToken.None);

            Assert.Equal("op-stale-456", cancelCalledWith);
            Assert.Equal(VideoJobState.Cancelled, result.State);
            Assert.Null(result.Error);

            // Final ledger record is Cancelled with Cancelled error attached.
            var latest = _ledger.AllRecords.Last(r => r.JobId == jobId);
            Assert.Equal(VideoJobState.Cancelled, latest.State);
            Assert.NotNull(latest.Error);
            Assert.Equal(GenErrorCode.Cancelled, latest.Error!.Code);
            Assert.False(latest.Error.Retryable);
        }

        [Fact]
        public async Task Cancel_interrupted_job_when_provider_fails_returns_Fail_no_state_change()
        {
            var jobId = Guid.NewGuid();
            var prior = VideoJobRecordFactory.From(
                jobId, T2vRequest(), _resolvedModel,
                EstimateFor(T2vRequest()),
                VideoJobState.Interrupted, _clock.UtcNow());
            prior = VideoJobRecordFactory.WithState(
                prior, VideoJobState.Interrupted, _clock.UtcNow(),
                providerJobId: "op-stale-789",
                error: new VideoJobError(VideoErrorCode.Interrupted, "x", Retryable: true));
            _ledger.Append(prior);

            _provider.OnCancel = _ => FakeVideoProvider.CancelFailed(new VideoJobError(
                Code: VideoErrorCode.DependencyUnavailable,
                Message: "Veo cancel rate-limited",
                Retryable: true));

            var beforeCount = _ledger.AllRecords.Count;
            var mgr = Manager();
            var result = await mgr.CancelAsync(jobId, CancellationToken.None);

            // CancelAsync surfaces the provider's failure to the caller.
            Assert.NotNull(result.Error);
            Assert.Equal(VideoErrorCode.DependencyUnavailable, result.Error!.Code);
            // No new record appended — durable state stays Interrupted,
            // provider_job_id intact for the next retry.
            Assert.Equal(beforeCount, _ledger.AllRecords.Count);
            var latest = _ledger.AllRecords.Last(r => r.JobId == jobId);
            Assert.Equal(VideoJobState.Interrupted, latest.State);
            Assert.Equal("op-stale-789", latest.ProviderJobId);
        }

        [Fact]
        public async Task Cancel_in_flight_when_provider_fails_returns_Fail_local_task_kept_running()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);

            // Provider submits ok, polls forever (so the local task
            // remains in-flight throughout the cancel attempt).
            _provider.OnSubmit = (_, _) =>
                FakeVideoProvider.SubmitQueued("op-keepalive");
            _provider.OnGetStatus = _ => FakeVideoProvider.StatusInFlight(10);

            // Provider rejects cancel.
            _provider.OnCancel = _ => FakeVideoProvider.CancelFailed(new VideoJobError(
                Code: VideoErrorCode.InvalidRequest,
                Message: "Veo refused cancel",
                Retryable: false));

            var mgr = Manager(pollInterval: TimeSpan.FromMilliseconds(20));
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);

            // Wait until provider_job_id is persisted (post-submit).
            var deadline = DateTime.UtcNow + TimeSpan.FromSeconds(2);
            while (DateTime.UtcNow < deadline)
            {
                if (_ledger.AllRecords.Any(r => r.JobId == jobId && r.ProviderJobId is not null))
                    break;
                await Task.Delay(10);
            }

            var cancel = await mgr.CancelAsync(jobId, CancellationToken.None);

            // Cancel surfaces Fail — not Ok(Cancelled) — because the
            // remote may still be running and billing.
            Assert.NotNull(cancel.Error);
            Assert.Equal(VideoErrorCode.InvalidRequest, cancel.Error!.Code);

            // Latest ledger record should NOT be Cancelled — the local
            // task is still running.
            var latest = _ledger.AllRecords.Last(r => r.JobId == jobId);
            Assert.NotEqual(VideoJobState.Cancelled, latest.State);
        }

        [Fact]
        public async Task Cancel_in_flight_when_provider_succeeds_persists_Cancelled_with_error()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            _provider.OnSubmit = (_, _) => FakeVideoProvider.SubmitQueued("op-ok");
            _provider.OnGetStatus = _ => FakeVideoProvider.StatusInFlight(10);
            _provider.OnCancel = _ => FakeVideoProvider.CancelOk();

            var mgr = Manager(pollInterval: TimeSpan.FromMilliseconds(20));
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);

            var deadline = DateTime.UtcNow + TimeSpan.FromSeconds(2);
            while (DateTime.UtcNow < deadline)
            {
                if (_ledger.AllRecords.Any(r => r.JobId == jobId && r.ProviderJobId is not null))
                    break;
                await Task.Delay(10);
            }

            await mgr.CancelAsync(jobId, CancellationToken.None);

            // Wait for the background task to finalize its Cancelled write
            // after the local CTS fires.
            deadline = DateTime.UtcNow + TimeSpan.FromSeconds(2);
            while (DateTime.UtcNow < deadline)
            {
                var latest = _ledger.AllRecords.LastOrDefault(r => r.JobId == jobId);
                if (latest is not null && latest.State == VideoJobState.Cancelled) break;
                await Task.Delay(10);
            }

            var final = _ledger.AllRecords.Last(r => r.JobId == jobId);
            Assert.Equal(VideoJobState.Cancelled, final.State);
            // Background task's catch path persists the Cancelled error.
            Assert.NotNull(final.Error);
            Assert.Equal(GenErrorCode.Cancelled, final.Error!.Code);
        }

        [Fact]
        public async Task Cancel_during_remote_materialization_persists_Cancelled_not_Error()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            _provider.OnSubmit = (_, _) => FakeVideoProvider.SubmitQueued("op-remote-cancel");
            _provider.OnGetStatus = handle =>
                FakeVideoProvider.StatusComplete(handle, "https://veo/result/x");
            _provider.OnFetchResult = _ =>
                FakeVideoProvider.ResultRemote("https://cdn.example.test/out.mp4", "video/mp4");
            _provider.OnCancel = _ => FakeVideoProvider.CancelOk();

            var blockingHandler = new BlockingVideoResponseHandler();
            var mgr = Manager(
                materializer: new VideoArtifactMaterializer(
                    blockingHandler,
                    maxGeneratedVideoBytes: 1024));

            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            await blockingHandler.WaitForRequestAsync();

            await mgr.CancelAsync(jobId, CancellationToken.None);
            await WaitForTerminalAsync(mgr, jobId);

            var final = _ledger.AllRecords.Last(r => r.JobId == jobId);
            Assert.Equal(VideoJobState.Cancelled, final.State);
            Assert.NotNull(final.Error);
            Assert.Equal(GenErrorCode.Cancelled, final.Error!.Code);
        }

        // ─── Reconcile (no auto-resume) ──────────────────────────────

        [Fact]
        public void Reconcile_marks_non_terminal_jobs_as_Interrupted()
        {
            // Pre-populate the ledger as if a prior session left a
            // job mid-flight. ReconcileInterruptedJobs should append
            // an Interrupted record without touching the provider.
            var jobId = Guid.NewGuid();
            var staleRecord = VideoJobRecordFactory.From(
                jobId, T2vRequest(), _resolvedModel,
                EstimateFor(T2vRequest()),
                VideoJobState.Polling, _clock.UtcNow());
            staleRecord = VideoJobRecordFactory.WithState(
                staleRecord, VideoJobState.Polling, _clock.UtcNow(),
                providerJobId: "op-stale-123");
            _ledger.Append(staleRecord);

            // Track provider calls — should be NONE during reconcile.
            var providerCalls = 0;
            _provider.OnSubmit = (_, _) => { providerCalls++; return FakeVideoProvider.SubmitQueued("x"); };
            _provider.OnGetStatus = _ => { providerCalls++; return FakeVideoProvider.StatusInFlight(); };
            _provider.OnCancel = _ => { providerCalls++; return FakeVideoProvider.CancelOk(); };
            _provider.OnFetchResult = _ =>
            {
                providerCalls++;
                return FakeVideoProvider.ResultFailed(new VideoJobError(
                    VideoErrorCode.ExecutionFailed, "x", Retryable: false));
            };

            var mgr = Manager();
            mgr.ReconcileInterruptedJobs();

            Assert.Equal(0, providerCalls);  // no auto-resume per v3.1 D4

            var latest = _ledger.AllRecords.Last(r => r.JobId == jobId);
            Assert.Equal(VideoJobState.Interrupted, latest.State);
            Assert.Equal("op-stale-123", latest.ProviderJobId);  // persisted for explicit cancel
            Assert.NotNull(latest.Error);
            Assert.Equal(GenErrorCode.Interrupted, latest.Error!.Code);
        }

        [Fact]
        public void Reconcile_does_not_touch_terminal_jobs()
        {
            var jobId = Guid.NewGuid();
            var staleRecord = VideoJobRecordFactory.From(
                jobId, T2vRequest(), _resolvedModel,
                EstimateFor(T2vRequest()),
                VideoJobState.Complete, _clock.UtcNow());
            _ledger.Append(staleRecord);

            var beforeCount = _ledger.AllRecords.Count;

            var mgr = Manager();
            mgr.ReconcileInterruptedJobs();

            // No new record appended — terminal state stays terminal.
            Assert.Equal(beforeCount, _ledger.AllRecords.Count);
        }

        // ─── Pricing single-pass invariant (M3) ───────────────────────

        [Fact]
        public async Task Pricing_model_Estimate_is_called_exactly_once_across_submit_to_complete()
        {
            // M3: the audit-snapshot invariant says pricing is computed
            // once at estimate time and copied verbatim downstream. A
            // counting pricing model proves it end-to-end — no recompute
            // anywhere between submit and the persisted Complete record.
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();

            var counter = new CountingPricingModel(
                inner: VeoCapabilities.Models["veo-3.1-lite-generate-preview"].PricingModel);
            var resolvedWithCounter = _resolvedModel with { PricingModel = counter };
            var registryWithCounter = new SingleModelRegistry(resolvedWithCounter);
            var mgr = Manager(registry: registryWithCounter);

            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(1, counter.CallCount);
        }

        // Test pricing model that delegates to a real one but counts calls.
        private sealed class CountingPricingModel
            : Rook.Services.Vision.Generation.IPricingModel<VideoGenerationRequest, VideoCapability>
        {
            private readonly Rook.Services.Vision.Generation.IPricingModel<VideoGenerationRequest, VideoCapability> _inner;
            public int CallCount { get; private set; }

            public CountingPricingModel(
                Rook.Services.Vision.Generation.IPricingModel<VideoGenerationRequest, VideoCapability> inner)
            {
                _inner = inner;
            }

            public string PricingSource => _inner.PricingSource;
            public Rook.Services.Vision.Generation.PricingMetadataLocation MetadataLocation =>
                _inner.MetadataLocation;

            public Rook.Services.Vision.Generation.PricingResult Estimate(
                VideoGenerationRequest request,
                VideoCapability cap)
            {
                CallCount++;
                return _inner.Estimate(request, cap);
            }

            public Rook.Services.Vision.Generation.JobPricing? ExtractActualSpend(
                IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
                JsonNode? responseBody) =>
                _inner.ExtractActualSpend(responseHeaders, responseBody);
        }

        // Trivial registry holding one resolved model. Avoids the
        // VeoProviderRegistration path so the swapped PricingModel sticks.
        private sealed class SingleModelRegistry : IVideoProviderRegistry
        {
            private readonly ResolvedVideoModel _model;

            public SingleModelRegistry(ResolvedVideoModel model) { _model = model; }

            public bool TryResolve(string modelId, out ResolvedVideoModel model)
            {
                if (modelId == _model.ModelId)
                {
                    model = _model;
                    return true;
                }
                model = null!;
                return false;
            }

            public bool TryResolveProviderByName(string providerName, out IVideoProvider provider)
            {
                if (providerName == _model.ProviderName)
                {
                    provider = _model.Provider;
                    return true;
                }
                provider = null!;
                return false;
            }

            public IReadOnlyList<VideoModelDescriptor> EnumerateAllModels() =>
                new[]
                {
                    new VideoModelDescriptor(
                        _model.ModelId, _model.ProviderName, _model.Capability,
                        VideoJobPricingTranslator.PricingKindFor(_model.PricingModel),
                        _model.PricingModel.PricingSource),
                };
        }

        // ─── Submit short-circuits before media resolver on validation failure (M5) ──

        [Fact]
        public async Task Submit_with_invalid_request_does_not_invoke_media_resolver()
        {
            // M5: media resolution is non-trivial work (artifact lookup,
            // disk IO). Submit must reject validation failures BEFORE
            // touching the resolver, otherwise a bad request burns IO on
            // every retry.
            var resolverCalls = 0;
            _resolver.OnResolve = _ =>
            {
                resolverCalls++;
                return new ResolvedMedia(new byte[] { 1 }, "image/png");
            };

            var mgr = Manager();
            // Invalid: resolution doesn't match cap.
            var bad = T2vRequest().With(resolution: "8k");

            var result = await mgr.SubmitAsync(bad, CancellationToken.None);

            Assert.NotNull(result.Error);
            Assert.Equal(0, resolverCalls);
            Assert.Empty(_ledger.AllRecords);
        }

        // ─── H1 regression: cancel succeeds when model deprecated but provider still registered ──

        [Fact]
        public async Task Cancel_after_model_deprecation_resolves_provider_by_name_and_succeeds()
        {
            // H1: persisted record's model id may no longer be in the
            // registry (Google sunsets a Veo model overnight while a job
            // is mid-flight from yesterday). The cancel path must NOT
            // refuse on model-id miss — it should resolve by provider
            // name (which is still registered) and call CancelAsync.
            var jobId = Guid.NewGuid();

            // Pre-populate ledger with an Interrupted record using a
            // DEPRECATED model id that's not in our registry.
            // Construct via the production VeoProviderRegistration first
            // to get a valid pricing snapshot, then force the model on
            // the record.
            var realModel = TestVideoFixtures.VeoLiteResolved(_provider);
            var validReq = TestVideoFixtures.DefaultT2vRequest();
            var prior = VideoJobRecordFactory.From(
                jobId, validReq, realModel, EstimateFor(validReq),
                VideoJobState.Polling, _clock.UtcNow())
                with { Model = "veo-deprecated-yesterday" };  // forced
            prior = VideoJobRecordFactory.WithState(
                prior, VideoJobState.Interrupted, _clock.UtcNow(),
                providerJobId: "operations/stranded-by-deprecation",
                error: new VideoJobError(
                    VideoErrorCode.Interrupted, "x", Retryable: true));
            _ledger.Append(prior);

            // Provider is still registered under the real Veo registration.
            string? cancelCalledWith = null;
            _provider.OnCancel = handle =>
            {
                cancelCalledWith = handle.ProviderJobId;
                return FakeVideoProvider.CancelOk();
            };
            _provider.OnCancelForModel = (_, _) =>
                throw new InvalidOperationException(
                    "Deprecated model cancel should use the legacy provider-name path.");

            var mgr = Manager();
            var result = await mgr.CancelAsync(jobId, CancellationToken.None);

            Assert.Equal("operations/stranded-by-deprecation", cancelCalledWith);
            Assert.DoesNotContain(_provider.RecordedCalls,
                c => c.Method == "CancelForModel");
            Assert.Equal(VideoJobState.Cancelled, result.State);
            Assert.Null(result.Error);

            // Final record is Cancelled with the Cancelled error attached.
            var latest = _ledger.AllRecords.Last(r => r.JobId == jobId);
            Assert.Equal(VideoJobState.Cancelled, latest.State);
            Assert.NotNull(latest.Error);
            Assert.Equal(GenErrorCode.Cancelled, latest.Error!.Code);
        }

        [Fact]
        public async Task Cancel_interrupted_model_aware_provider_validates_persisted_provider_and_model()
        {
            var providerMismatchJobId = Guid.NewGuid();
            var falModelId = "fal-ai/seedance/v1/pro/text-to-video";
            var request = T2vRequest().With(model: falModelId);
            var falModel = _resolvedModel with
            {
                ModelId = falModelId,
                ProviderName = "fal",
                Provider = _provider,
            };
            var mismatchedModel = falModel with { ProviderName = "veo" };
            var mismatchRegistry = new SingleModelRegistry(mismatchedModel);

            var mismatchPrior = VideoJobRecordFactory.From(
                providerMismatchJobId, request, falModel,
                _estimator.Estimate(falModel, request).Estimate!,
                VideoJobState.Polling, _clock.UtcNow());
            mismatchPrior = VideoJobRecordFactory.WithState(
                mismatchPrior, VideoJobState.Interrupted, _clock.UtcNow(),
                providerJobId: "fal-request-provider-mismatch",
                error: new VideoJobError(
                    VideoErrorCode.Interrupted, "x", Retryable: true));
            _ledger.Append(mismatchPrior);

            _provider.OnCancel = _ =>
                throw new InvalidOperationException("Legacy cancel should not be called.");
            _provider.OnCancelForModel = (_, _) =>
                throw new InvalidOperationException(
                    "Model-aware cancel should not be called for provider mismatch.");

            var mismatchMgr = Manager(registry: mismatchRegistry);
            var mismatchResult = await mismatchMgr.CancelAsync(
                providerMismatchJobId,
                CancellationToken.None);

            Assert.NotNull(mismatchResult.Error);
            Assert.Equal(VideoErrorCode.InvalidRequest, mismatchResult.Error!.Code);
            Assert.DoesNotContain(_provider.RecordedCalls,
                c => c.Method == "CancelForModel" || c.Method == "Cancel");

            var successJobId = Guid.NewGuid();
            var matchingPrior = VideoJobRecordFactory.From(
                successJobId, request, falModel,
                _estimator.Estimate(falModel, request).Estimate!,
                VideoJobState.Polling, _clock.UtcNow());
            matchingPrior = VideoJobRecordFactory.WithState(
                matchingPrior, VideoJobState.Interrupted, _clock.UtcNow(),
                providerJobId: "fal-request-model-aware",
                error: new VideoJobError(
                    VideoErrorCode.Interrupted, "x", Retryable: true));
            _ledger.Append(matchingPrior);

            _provider.RecordedCalls.Clear();
            _provider.OnCancelForModel = (modelId, handle) =>
            {
                Assert.Equal(falModelId, modelId);
                Assert.Equal("fal-request-model-aware", handle.ProviderJobId);
                return FakeVideoProvider.CancelOk();
            };

            var successMgr = Manager(registry: new SingleModelRegistry(falModel));
            var successResult = await successMgr.CancelAsync(
                successJobId,
                CancellationToken.None);

            Assert.Equal(VideoJobState.Cancelled, successResult.State);
            Assert.Null(successResult.Error);
            var call = Assert.Single(_provider.RecordedCalls,
                c => c.Method == "CancelForModel");
            var payload = Assert.IsType<FakeVideoProvider.ModelAwareCall>(call.Payload);
            Assert.Equal(falModelId, payload.ModelId);
            Assert.Equal("fal-request-model-aware", payload.ProviderJobId);
            Assert.DoesNotContain(_provider.RecordedCalls,
                c => c.Method == "Cancel");
        }

        [Fact]
        public async Task Cancel_deprecated_fal_url_handle_bypasses_model_aware_provider()
        {
            var jobId = Guid.NewGuid();
            var activeFalModel = _resolvedModel with
            {
                ModelId = "fal-ai/seedance/v1/pro/text-to-video",
                ProviderName = "fal",
                Provider = _provider,
            };
            var deprecatedRequest = T2vRequest()
                .With(model: "fal-ai/seedance/deprecated/url-handle");
            var handle = new ProviderJobHandle(
                providerJobId: "fal-url-queue-id",
                statusUrl: new Uri("https://queue.fal.ai/status/fal-url-queue-id"),
                responseUrl: new Uri("https://queue.fal.ai/response/fal-url-queue-id"),
                cancelUrl: new Uri("https://queue.fal.ai/cancel/fal-url-queue-id"),
                cancelHttpMethod: "PUT");
            var prior = VideoJobRecordFactory.From(
                jobId, deprecatedRequest, activeFalModel,
                _estimator.Estimate(activeFalModel, T2vRequest()
                    .With(model: activeFalModel.ModelId)).Estimate!,
                VideoJobState.Polling, _clock.UtcNow());
            prior = VideoJobRecordFactory.WithState(
                prior, VideoJobState.Interrupted, _clock.UtcNow(),
                providerHandle: handle,
                error: new VideoJobError(
                    VideoErrorCode.Interrupted, "x", Retryable: true));
            _ledger.Append(prior);

            string? cancelCalledWith = null;
            _provider.OnCancel = h =>
            {
                cancelCalledWith = h.ProviderJobId;
                return FakeVideoProvider.CancelOk();
            };
            _provider.OnCancelForModel = (_, _) =>
                throw new InvalidOperationException(
                    "URL-bearing fal handles must bypass model-aware cancel.");

            var mgr = Manager(registry: new SingleModelRegistry(activeFalModel));
            var result = await mgr.CancelAsync(jobId, CancellationToken.None);

            Assert.Equal(VideoJobState.Cancelled, result.State);
            Assert.Null(result.Error);
            Assert.Equal("fal-url-queue-id", cancelCalledWith);
            Assert.Contains(_provider.RecordedCalls,
                c => c.Method == "Cancel");
            Assert.DoesNotContain(_provider.RecordedCalls,
                c => c.Method == "CancelForModel");
        }

        [Fact]
        public async Task Submit_seedance_blank_prompt_fails_before_media_resolution_or_provider_submit()
        {
            var startFrame = MediaRef.ForArtifact(
                Guid.NewGuid(),
                VideoMediaRoles.StartFrame);
            var request = SeedanceI2vRequest(startFrame).WithPrompt("   ");
            _resolver.OnResolve = _ =>
                throw new InvalidOperationException(
                    "Invalid Seedance prompt should fail before media resolution.");
            _provider.OnSubmit = (_, _) =>
                throw new InvalidOperationException(
                    "Invalid Seedance prompt should fail before provider submit.");

            var mgr = Manager(registry: RegistryWithSeedance(_provider));

            var result = await mgr.SubmitAsync(request, CancellationToken.None);

            Assert.Null(result.JobId);
            Assert.Equal(VideoErrorCode.InvalidRequest, result.Error!.Code);
            Assert.Equal(nameof(VideoGenerationRequest.Prompt), result.Error.Field);
            Assert.Empty(_provider.RecordedCalls);
            Assert.Empty(_ledger.AllRecords);
        }

        [Fact]
        public async Task Seedance_job_materializes_without_fal_transport_in_ledger_or_artifact_metadata()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            var startFrame = MediaRef.ForArtifact(
                Guid.NewGuid(),
                VideoMediaRoles.StartFrame);
            _resolver.OnResolve = mediaRef =>
            {
                Assert.Equal(startFrame, mediaRef);
                return new ResolvedMedia(PngBytes(), "image/png");
            };
            _provider.OnSubmit = (request, resolvedMedia) =>
            {
                Assert.Equal(FalVideoCapabilities.SeedanceI2v, request.Model);
                Assert.Single(resolvedMedia);
                return new QueuedSubmitOutcome(
                    new ProviderJobHandle("seedance-request-1"));
            };
            _provider.OnGetStatusForModel = (modelId, handle) =>
            {
                Assert.Equal(FalVideoCapabilities.SeedanceI2v, modelId);
                Assert.Equal("seedance-request-1", handle.ProviderJobId);
                Assert.Null(handle.StatusUrl);
                Assert.Null(handle.ResponseUrl);
                Assert.Null(handle.CancelUrl);
                return FakeVideoProvider.StatusComplete(
                    handle,
                    "seedance-request-1");
            };
            _provider.OnFetchResultForModel = (modelId, handle) =>
            {
                Assert.Equal(FalVideoCapabilities.SeedanceI2v, modelId);
                Assert.Equal("seedance-request-1", handle.ProviderJobId);
                return FakeVideoProvider.ResultRemote(
                    "https://v3.fal.media/files/seedance.mp4",
                    "video/mp4");
            };
            _provider.OnGetStatus = _ =>
                throw new InvalidOperationException("Legacy status should not be called.");
            _provider.OnFetchResult = _ =>
                throw new InvalidOperationException("Legacy fetch should not be called.");

            var ledgerPath = Path.Combine(_artifactRoot, "seedance-ledger.jsonl");
            var ledger = new JsonlVideoJobLedger(ledgerPath);
            var downloadHandler = new TestHttpMessageHandler
            {
                OnSend = request =>
                {
                    Assert.Equal(
                        "https://v3.fal.media/files/seedance.mp4",
                        request.RequestUri!.ToString());
                    return new HttpResponseMessage(HttpStatusCode.OK)
                    {
                        Content = new ByteArrayContent(FakeMp4)
                        {
                            Headers =
                            {
                                ContentType =
                                    new System.Net.Http.Headers.MediaTypeHeaderValue(
                                        "video/mp4"),
                            },
                        },
                    };
                },
            };
            var materializer = new VideoArtifactMaterializer(
                downloadHandler,
                maxGeneratedVideoBytes: 1024);

            var mgr = Manager(
                registry: RegistryWithSeedance(_provider),
                ledger: ledger,
                materializer: materializer);

            await mgr.SubmitAsync(
                SeedanceI2vRequest(startFrame),
                CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            Assert.NotNull(final.ResultArtifactId);
            Assert.Single(downloadHandler.Requests);

            var ledgerJson = File.ReadAllText(ledgerPath);
            Assert.Contains("seedance-request-1", ledgerJson);
            Assert.DoesNotContain("queue.fal.run", ledgerJson);
            Assert.DoesNotContain("status_url", ledgerJson);
            Assert.DoesNotContain("response_url", ledgerJson);
            Assert.DoesNotContain("cancel_url", ledgerJson);
            AssertNoFalSourceTransportMarkers(ledgerJson);

            var artifact = _artifactStore.Get(final.ResultArtifactId!.Value);
            Assert.NotNull(artifact);
            var artifactMetadataJson = JsonSerializer.Serialize(artifact!.Metadata);
            Assert.DoesNotContain("fal.media", artifactMetadataJson);
            Assert.DoesNotContain("queue.fal.run", artifactMetadataJson);
            AssertNoFalSourceTransportMarkers(artifactMetadataJson);
            Assert.DoesNotContain("seedance-request-1", artifactMetadataJson);
        }

        [Fact]
        public async Task Seedance_submit_failure_does_not_persist_echoed_source_transport()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            var startFrame = MediaRef.ForArtifact(
                Guid.NewGuid(),
                VideoMediaRoles.StartFrame);
            var startBytes = PngBytes();
            _resolver.OnResolve = mediaRef =>
            {
                Assert.Equal(startFrame, mediaRef);
                return new ResolvedMedia(startBytes, "image/png");
            };
            var echoedDataUri =
                "data:image/png;base64," + Convert.ToBase64String(startBytes);
            const string echoedStartUrl =
                "https://v3.fal.media/files/rook/seedance-sources/start.png";
            const string echoedEndUrl =
                "https://v3.fal.media/files/rook/seedance-sources/end.png";
            var submitHandler = new TestHttpMessageHandler
            {
                OnSend = request =>
                {
                    if (request.RequestUri!.Host == "rest.fal.ai")
                    {
                        return new HttpResponseMessage(HttpStatusCode.OK)
                        {
                            Content = new StringContent(
                                """
                                {
                                  "upload_url": "https://uploads.example.test/source-token",
                                  "file_url": "https://v3b.fal.media/files/source-private.png"
                                }
                                """,
                                System.Text.Encoding.UTF8,
                                "application/json"),
                        };
                    }

                    if (request.RequestUri.Host == "uploads.example.test")
                        return new HttpResponseMessage(HttpStatusCode.NoContent);

                    return new HttpResponseMessage((HttpStatusCode)422)
                    {
                        Content = new StringContent(
                            $$"""
                            {
                              "detail": [{
                                "loc": ["body", "image_url"],
                                "msg": "invalid image",
                                "input": "{{echoedDataUri}}"
                              }],
                              "image_url": "{{echoedStartUrl}}",
                              "end_image_url": "{{echoedEndUrl}}",
                              "upload_url": "https://v3b.fal.media/upload/presigned-token",
                              "initiate_url": "https://rest.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3",
                              "body": "{{echoedDataUri}}"
                            }
                            """,
                            System.Text.Encoding.UTF8,
                            "application/json"),
                    };
                },
            };
            var falProvider = new FalVideoProvider(
                () => "test-fal-key",
                new Rook.Services.Vision.Fal.FalApiClient(
                    new HttpClient(submitHandler)));
            var ledgerPath = Path.Combine(_artifactRoot, "seedance-failure-ledger.jsonl");
            var ledger = new JsonlVideoJobLedger(ledgerPath);
            var mgr = Manager(
                registry: RegistryWithSeedance(falProvider),
                ledger: ledger);

            var submit = await mgr.SubmitAsync(
                SeedanceI2vRequest(startFrame),
                CancellationToken.None);

            Assert.Equal(jobId, submit.JobId);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Error, final.State);
            Assert.NotNull(final.Error);
            Assert.Collection(
                submitHandler.Requests,
                request =>
                {
                    Assert.Equal(HttpMethod.Post, request.Method);
                    Assert.Equal(
                        "https://rest.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3",
                        request.RequestUri!.ToString());
                },
                request =>
                {
                    Assert.Equal(HttpMethod.Put, request.Method);
                    Assert.Equal(
                        "https://uploads.example.test/source-token",
                        request.RequestUri!.ToString());
                },
                request =>
                {
                    Assert.Equal(HttpMethod.Post, request.Method);
                    Assert.Equal(
                        "https://queue.fal.run/bytedance/seedance-2.0/image-to-video",
                        request.RequestUri!.ToString());
                });

            var ledgerJson = File.ReadAllText(ledgerPath);
            Assert.Contains("fal request failed with HTTP 422", ledgerJson);
            AssertNoFalSourceTransportMarkers(ledgerJson);
            Assert.DoesNotContain("fal.media", ledgerJson);
            Assert.DoesNotContain("upload_url", ledgerJson);
            Assert.DoesNotContain("initiate_url", ledgerJson);
            Assert.DoesNotContain("v3b.fal.media/upload/presigned-token", ledgerJson);
            Assert.DoesNotContain("https://v3b.fal.media/files/source-private.png", ledgerJson);
            Assert.DoesNotContain(Convert.ToBase64String(startBytes), ledgerJson);

            var finalJson = JsonSerializer.Serialize(final);
            AssertNoFalSourceTransportMarkers(finalJson);
            Assert.DoesNotContain("fal.media", finalJson);
            Assert.DoesNotContain("upload_url", finalJson);
            Assert.DoesNotContain("initiate_url", finalJson);
            Assert.DoesNotContain("v3b.fal.media/upload/presigned-token", finalJson);
            Assert.DoesNotContain("https://v3b.fal.media/files/source-private.png", finalJson);
            Assert.DoesNotContain(Convert.ToBase64String(startBytes), finalJson);
        }

        [Fact]
        public async Task Seedance_cancel_after_restart_uses_request_id_only_with_model_identity()
        {
            var jobId = Guid.NewGuid();
            var startFrame = MediaRef.ForArtifact(
                Guid.NewGuid(),
                VideoMediaRoles.StartFrame);
            var request = SeedanceI2vRequest(startFrame);
            var registry = RegistryWithSeedance(_provider);
            Assert.True(registry.TryResolve(
                FalVideoCapabilities.SeedanceI2v,
                out var seedanceModel));
            var estimate = _estimator.Estimate(seedanceModel, request).Estimate!;
            var prior = VideoJobRecordFactory.From(
                jobId,
                request,
                seedanceModel,
                estimate,
                VideoJobState.Polling,
                _clock.UtcNow());
            prior = VideoJobRecordFactory.WithState(
                prior,
                VideoJobState.Interrupted,
                _clock.UtcNow(),
                providerJobId: "seedance-request-2",
                error: new VideoJobError(
                    VideoErrorCode.Interrupted,
                    "x",
                    Retryable: true));

            var ledgerPath = Path.Combine(_artifactRoot, "seedance-cancel-ledger.jsonl");
            var ledger = new JsonlVideoJobLedger(ledgerPath);
            ledger.Append(prior);
            var cancelModels = new List<string>();
            _provider.OnCancelForModel = (modelId, handle) =>
            {
                cancelModels.Add(modelId);
                Assert.Equal(FalVideoCapabilities.SeedanceI2v, modelId);
                Assert.Equal("seedance-request-2", handle.ProviderJobId);
                Assert.Null(handle.CancelUrl);
                return FakeVideoProvider.CancelOk();
            };
            _provider.OnCancel = _ =>
                throw new InvalidOperationException("Legacy cancel should not be called.");

            var mgr = Manager(registry: registry, ledger: ledger);

            var cancel = await mgr.CancelAsync(jobId, CancellationToken.None);

            Assert.Equal(VideoJobState.Cancelled, cancel.State);
            Assert.Null(cancel.Error);
            Assert.Contains(FalVideoCapabilities.SeedanceI2v, cancelModels);

            var ledgerJson = File.ReadAllText(ledgerPath);
            Assert.DoesNotContain("status_url", ledgerJson);
            Assert.DoesNotContain("response_url", ledgerJson);
            Assert.DoesNotContain("cancel_url", ledgerJson);
            Assert.DoesNotContain("queue.fal.run", ledgerJson);
        }

        // ─── F1b (review pass 3): in-flight branch terminal short-circuit ──

        [Fact]
        public async Task Cancel_in_flight_when_BG_just_wrote_terminal_short_circuits_without_provider_call()
        {
            // F1b: probing _runningJobs first (F1) only protects the
            // not-running branch. Inside the in-flight branch, the BG
            // task can write a terminal ledger record between the
            // _runningJobs probe and the in-flight branch's ledger read,
            // leaving the branch with a "live" probe and a "terminal"
            // ledger view. Calling provider.CancelAsync now would tell
            // the user the job was Cancelled when it actually Completed —
            // wrong outcome plus a paid unneeded cancel request.
            //
            // Setup uses a hang-gate to keep _runningJobs entry alive
            // while a Complete record is appended to the ledger out of
            // band, simulating the precise interleaving.

            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);

            var hangGate = new TaskCompletionSource<bool>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            var submitStarted = new TaskCompletionSource<bool>(
                TaskCreationOptions.RunContinuationsAsynchronously);

            // Provider's SubmitAsync blocks → BG task stays in flight.
            _provider.OnSubmit = (_, _) =>
            {
                submitStarted.TrySetResult(true);
                hangGate.Task.GetAwaiter().GetResult();
                return FakeVideoProvider.SubmitQueued("op-never-needed");
            };
            _provider.OnGetStatus = _ => FakeVideoProvider.StatusInFlight();

            var providerCancelCalls = 0;
            _provider.OnCancel = _ =>
            {
                providerCancelCalls++;
                return FakeVideoProvider.CancelOk();
            };

            using var mgr = Manager();
            try
            {
                await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);

                // Wait until SubmitAsync's initial Queued record is in
                // the ledger AND _runningJobs entry is live. SubmitAsync
                // synchronously appends the initial record + adds to
                // _runningJobs before returning, so a single check
                // suffices.
                Assert.Contains(_ledger.AllRecords, r => r.JobId == jobId);
                await WaitForSignalAsync(
                    submitStarted.Task,
                    "Background job did not enter provider submit.");

                // Simulate the race: BG task transitioned through Polling
                // (persisting provider_job_id) and on to Complete in the
                // ledger, but hasn't removed itself from _runningJobs
                // yet (provider.SubmitAsync is still blocked at hangGate).
                //
                // The persisted provider_job_id on the terminal record is
                // load-bearing: without F1b's terminal short-circuit, the
                // in-flight branch would read this ProviderJobId and call
                // provider.CancelAsync. The Polling-then-Complete sequence
                // ensures the terminal record CARRIES that handle, so the
                // test would observe a provider call (and report the wrong
                // outcome) if the protection regressed.
                var initial = _ledger.AllRecords.Last(r => r.JobId == jobId);
                Assert.Equal(VideoJobState.Submitting, initial.State);
                var polling = VideoJobRecordFactory.WithState(
                    initial, VideoJobState.Polling, _clock.UtcNow(),
                    providerJobId: "operations/race-complete-target");
                _ledger.Append(polling);

                var artifactId = Guid.NewGuid();
                var complete = VideoJobRecordFactory.WithState(
                    polling, VideoJobState.Complete, _clock.UtcNow(),
                    resultArtifactId: artifactId);
                _ledger.Append(complete);

                // Sanity: the terminal record really does carry a
                // provider handle, so we know the test exercises the
                // exact branch the fix protects.
                Assert.Equal("operations/race-complete-target", complete.ProviderJobId);

                var beforeCount = _ledger.AllRecords.Count;

                // Cancel: in-flight branch fires (_runningJobs has entry),
                // ledger read returns Complete + provider_job_id, but the
                // terminal short-circuit fires before ProviderJobId is
                // read → no provider call, returns Ok(Complete).
                var result = await mgr.CancelAsync(jobId, CancellationToken.None);

                Assert.Equal(VideoJobState.Complete, result.State);
                Assert.Null(result.Error);
                Assert.Equal(0, providerCancelCalls);
                Assert.Equal(beforeCount, _ledger.AllRecords.Count);
            }
            finally
            {
                // Always release the gate so the hung BG task can
                // proceed; mgr.Dispose() will then cancel it cleanly.
                hangGate.SetResult(true);
            }
        }

        [Fact]
        public async Task Cancel_in_flight_when_BG_just_wrote_Error_short_circuits_without_provider_call()
        {
            // Same race as F1b, but BG produced Error instead of Complete.
            // Same protection should fire.
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);

            var hangGate = new TaskCompletionSource<bool>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            var submitStarted = new TaskCompletionSource<bool>(
                TaskCreationOptions.RunContinuationsAsynchronously);

            _provider.OnSubmit = (_, _) =>
            {
                submitStarted.TrySetResult(true);
                hangGate.Task.GetAwaiter().GetResult();
                return FakeVideoProvider.SubmitQueued("op-x");
            };
            _provider.OnGetStatus = _ => FakeVideoProvider.StatusInFlight();
            var providerCancelCalls = 0;
            _provider.OnCancel = _ =>
            {
                providerCancelCalls++;
                return FakeVideoProvider.CancelOk();
            };

            using var mgr = Manager();
            try
            {
                await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
                Assert.Contains(_ledger.AllRecords, r => r.JobId == jobId);
                await WaitForSignalAsync(
                    submitStarted.Task,
                    "Background job did not enter provider submit.");

                // Same persisted-ProviderJobId discipline as the Complete
                // variant — terminal record carries the handle the bug
                // would have used.
                var initial = _ledger.AllRecords.Last(r => r.JobId == jobId);
                Assert.Equal(VideoJobState.Submitting, initial.State);
                var polling = VideoJobRecordFactory.WithState(
                    initial, VideoJobState.Polling, _clock.UtcNow(),
                    providerJobId: "operations/race-error-target");
                _ledger.Append(polling);

                var errored = VideoJobRecordFactory.WithState(
                    polling, VideoJobState.Error, _clock.UtcNow(),
                    error: new VideoJobError(
                        VideoErrorCode.ExecutionFailed, "boom", Retryable: false));
                _ledger.Append(errored);

                Assert.Equal("operations/race-error-target", errored.ProviderJobId);

                var beforeCount = _ledger.AllRecords.Count;

                var result = await mgr.CancelAsync(jobId, CancellationToken.None);

                Assert.Equal(VideoJobState.Error, result.State);
                Assert.Null(result.Error);
                Assert.Equal(0, providerCancelCalls);
                Assert.Equal(beforeCount, _ledger.AllRecords.Count);
            }
            finally
            {
                hangGate.SetResult(true);
            }
        }

        // ─── F1 (review pass 2): cancel race — no overwrite of terminal ──

        [Fact]
        public async Task Cancel_after_BG_completes_does_not_overwrite_Complete_with_Cancelled()
        {
            // Race scenario: at the moment CancelAsync starts, the BG
            // task has just finished — Complete is in the ledger, the
            // _runningJobs entry has been removed. CancelAsync MUST NOT
            // persist a Cancelled record on top of the Complete state.
            //
            // The fix structurally probes _runningJobs FIRST, then reads
            // the ledger. With _runningJobs empty (BG finished) and the
            // ledger holding Complete, the not-running branch's terminal
            // short-circuit fires before any provider call or overwrite.
            var jobId = Guid.NewGuid();

            // Pre-state mirrors what the BG task would have written:
            // initial submit + transition to Polling + terminal Complete.
            var initial = VideoJobRecordFactory.From(
                jobId, T2vRequest(), _resolvedModel,
                EstimateFor(T2vRequest()),
                VideoJobState.Submitting, _clock.UtcNow());
            var polling = VideoJobRecordFactory.WithState(
                initial, VideoJobState.Polling, _clock.UtcNow(),
                providerJobId: "operations/raced");
            var artId = Guid.NewGuid();
            var complete = VideoJobRecordFactory.WithState(
                polling, VideoJobState.Complete, _clock.UtcNow(),
                resultArtifactId: artId);
            _ledger.Append(initial);
            _ledger.Append(polling);
            _ledger.Append(complete);

            var providerCancelCalls = 0;
            _provider.OnCancel = _ =>
            {
                providerCancelCalls++;
                return FakeVideoProvider.CancelOk();
            };

            var beforeCount = _ledger.AllRecords.Count;
            var mgr = Manager();
            var result = await mgr.CancelAsync(jobId, CancellationToken.None);

            // Terminal short-circuit: returns Ok(Complete), no provider
            // call, no ledger write.
            Assert.Equal(VideoJobState.Complete, result.State);
            Assert.Null(result.Error);
            Assert.Equal(0, providerCancelCalls);
            Assert.Equal(beforeCount, _ledger.AllRecords.Count);

            // Latest state in ledger remains Complete with the artifact.
            var latest = _ledger.AllRecords.Last(r => r.JobId == jobId);
            Assert.Equal(VideoJobState.Complete, latest.State);
            Assert.Equal(artId, latest.ResultArtifactId);
        }

        [Fact]
        public async Task Cancel_after_BG_errors_does_not_overwrite_Error_with_Cancelled()
        {
            // Same race protection applies to all terminal states except
            // Interrupted (which IS still cancellable for cost cleanup).
            var jobId = Guid.NewGuid();

            var initial = VideoJobRecordFactory.From(
                jobId, T2vRequest(), _resolvedModel,
                EstimateFor(T2vRequest()),
                VideoJobState.Submitting, _clock.UtcNow());
            var errored = VideoJobRecordFactory.WithState(
                initial, VideoJobState.Error, _clock.UtcNow(),
                providerJobId: "operations/race-err",
                error: new VideoJobError(
                    VideoErrorCode.ExecutionFailed, "boom", Retryable: false));
            _ledger.Append(initial);
            _ledger.Append(errored);

            var providerCancelCalls = 0;
            _provider.OnCancel = _ =>
            {
                providerCancelCalls++;
                return FakeVideoProvider.CancelOk();
            };

            var beforeCount = _ledger.AllRecords.Count;
            var mgr = Manager();
            var result = await mgr.CancelAsync(jobId, CancellationToken.None);

            Assert.Equal(VideoJobState.Error, result.State);
            Assert.Null(result.Error);
            Assert.Equal(0, providerCancelCalls);
            Assert.Equal(beforeCount, _ledger.AllRecords.Count);
        }

        [Fact]
        public async Task Cancel_interrupted_no_remote_returns_Interrupted_without_appending_Cancelled()
        {
            // Interrupted without a provider_job_id has no remote handle
            // to clean up — surface the persisted terminal state. (Prior
            // logic appended a Cancelled record in this branch, which
            // overwrote the Interrupted snapshot — same family of bug as
            // F1 but for Interrupted state specifically.)
            var jobId = Guid.NewGuid();

            var prior = VideoJobRecordFactory.From(
                jobId, T2vRequest(), _resolvedModel,
                EstimateFor(T2vRequest()),
                VideoJobState.Polling, _clock.UtcNow());
            prior = VideoJobRecordFactory.WithState(
                prior, VideoJobState.Interrupted, _clock.UtcNow(),
                error: new VideoJobError(
                    VideoErrorCode.Interrupted, "x", Retryable: true));
            _ledger.Append(prior);

            var beforeCount = _ledger.AllRecords.Count;
            var mgr = Manager();
            var result = await mgr.CancelAsync(jobId, CancellationToken.None);

            Assert.Equal(VideoJobState.Interrupted, result.State);
            Assert.Null(result.Error);
            Assert.Equal(beforeCount, _ledger.AllRecords.Count);
        }

        [Fact]
        public async Task Cancel_when_provider_not_registered_returns_typed_Fail()
        {
            // The other side of H1: if the provider name itself is no
            // longer registered (the entire provider was unbundled, not
            // just one model deprecated), we cannot cancel remotely. Fail
            // typed, surface the missing-provider name in the message.
            var jobId = Guid.NewGuid();

            var realModel = TestVideoFixtures.VeoLiteResolved(_provider);
            var validReq = TestVideoFixtures.DefaultT2vRequest();
            var prior = VideoJobRecordFactory.From(
                jobId, validReq, realModel, EstimateFor(validReq),
                VideoJobState.Polling, _clock.UtcNow())
                with { Provider = "ghost-provider" };  // forced
            prior = VideoJobRecordFactory.WithState(
                prior, VideoJobState.Interrupted, _clock.UtcNow(),
                providerJobId: "operations/orphan",
                error: new VideoJobError(
                    VideoErrorCode.Interrupted, "x", Retryable: true));
            _ledger.Append(prior);

            var mgr = Manager();
            var result = await mgr.CancelAsync(jobId, CancellationToken.None);

            Assert.NotNull(result.Error);
            Assert.Equal(VideoErrorCode.InvalidRequest, result.Error!.Code);
            Assert.Contains("ghost-provider", result.Error.Message);
        }

        // ─── FetchResult ──────────────────────────────────────────────

        [Fact]
        public async Task FetchResult_complete_job_returns_artifact_files()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();

            var mgr = Manager();
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            await WaitForTerminalAsync(mgr, jobId);

            var fetch = await mgr.FetchResultAsync(jobId, CancellationToken.None);

            Assert.Equal(VideoJobState.Complete, fetch.State);
            Assert.NotNull(fetch.ResultArtifactId);
            Assert.NotNull(fetch.Files);
            Assert.Single(fetch.Files!);
            Assert.Equal("video", fetch.Files![0].Role);
        }

        [Fact]
        public async Task FetchResult_unknown_job_returns_Fail()
        {
            var mgr = Manager();

            var result = await mgr.FetchResultAsync(Guid.NewGuid(), CancellationToken.None);

            Assert.NotNull(result.Error);
            Assert.Equal(VideoErrorCode.InvalidRequest, result.Error!.Code);
        }

        // ─── Helpers ──────────────────────────────────────────────────

        private void ConfigureProviderHappyPath()
        {
            _provider.OnSubmit = (_, _) => FakeVideoProvider.SubmitQueued("op-123");
            _provider.OnGetStatus = handle =>
                FakeVideoProvider.StatusComplete(handle, "https://veo/result/x");
            _provider.OnFetchResult = _ =>
                FakeVideoProvider.ResultOk(FakeMp4, "video/mp4");
            _provider.OnCancel = _ => FakeVideoProvider.CancelOk();
        }

        private static DefaultVideoProviderRegistry RegistryWithSeedance(
            IVideoProvider provider) =>
            new(new[]
            {
                new FalVideoProviderRegistration(provider),
            });

        private static VideoGenerationRequest SeedanceI2vRequest(
            MediaRef startFrame) =>
            new(
                Model: FalVideoCapabilities.SeedanceI2v,
                Mode: VideoMode.I2V,
                DurationSeconds: 6,
                Resolution: "720p",
                AspectRatio: "16:9",
                Prompt: "seedance prompt should stay out of transport leakage",
                StartFrame: startFrame,
                EndFrame: null,
                ReferenceFrames: null,
                Seed: null,
                Options: new FalVideoOptions(),
                NumberOfVideos: 1);

        private static void AssertNoFalSourceTransportMarkers(string text)
        {
            Assert.DoesNotContain(
                "https://v3.fal.media/files/rook/seedance-sources",
                text);
            Assert.DoesNotContain("api.fal.ai", text);
            Assert.DoesNotContain("rest.fal.ai", text);
            Assert.DoesNotContain("image_url", text);
            Assert.DoesNotContain("end_image_url", text);
            Assert.DoesNotContain("data:image", text);
        }

        private static byte[] PngBytes() =>
            new byte[]
            {
                0x89, 0x50, 0x4E, 0x47,
                0x0D, 0x0A, 0x1A, 0x0A,
                1, 2, 3, 4,
            };

        private static GenProviderResultEnvelope NonVideoSuccessEnvelope()
        {
            var emptyMetadata = new Dictionary<string, JsonNode>();
            return new GenProviderResultEnvelope(
                new[]
                {
                    new GenResultArtifact(
                        Role: "image",
                        Body: new GenInlineArtifactBody(new byte[] { 1, 2, 3, 4 }),
                        DeclaredMimeType: "image/png",
                        ProviderMetadata: emptyMetadata),
                },
                emptyMetadata);
        }

        private static GenProviderResultEnvelope VideoSuccessEnvelope(
            byte[] bytes,
            string mimeType)
        {
            var emptyMetadata = new Dictionary<string, JsonNode>();
            return new GenProviderResultEnvelope(
                new[]
                {
                    new GenResultArtifact(
                        Role: VideoMediaRoles.Video,
                        Body: new GenInlineArtifactBody(bytes),
                        DeclaredMimeType: mimeType,
                        ProviderMetadata: emptyMetadata),
                },
                emptyMetadata);
        }
    }

    internal sealed class FakePosterProducer : IVideoPosterSidecarProducer
    {
        private readonly ArtifactStore _store;

        public FakePosterProducer(ArtifactStore store)
        {
            _store = store;
        }

        public List<Guid> ArtifactIds { get; } = new();

        public Func<Artifact, CancellationToken, Task<VideoPosterSidecarResult>>
            OnPublishAsync { get; set; } =
                (artifact, _) => Task.FromResult(
                    VideoPosterSidecarResult.From(
                        VideoPosterSidecarResultCode.Published,
                        artifact.Id));

        public Task<VideoPosterSidecarResult> TryPublishPosterAsync(
            Guid artifactId,
            CancellationToken cancellationToken)
        {
            ArtifactIds.Add(artifactId);
            return OnPublishAsync(_store.Get(artifactId)!, cancellationToken);
        }
    }

    internal sealed class FakeFrameProducer : IVideoFrameSidecarProducer
    {
        private readonly ArtifactStore _store;

        public FakeFrameProducer(ArtifactStore store)
        {
            _store = store;
        }

        public List<Guid> ArtifactIds { get; } = new();

        public Func<Artifact, CancellationToken, Task<VideoFrameSidecarResult>>
            OnPublishAsync { get; set; } =
                (artifact, _) => Task.FromResult(
                    Result(
                        artifact.Id,
                        VideoFrameSidecarRoleResultCode.Published,
                        VideoFrameSidecarRoleResultCode.Published));

        public Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
            Guid artifactId,
            CancellationToken cancellationToken)
        {
            ArtifactIds.Add(artifactId);
            return OnPublishAsync(_store.Get(artifactId)!, cancellationToken);
        }

        public Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
            Guid artifactId,
            IReadOnlyList<string> roles,
            CancellationToken cancellationToken)
            => TryPublishFrameSidecarsAsync(artifactId, cancellationToken);

        public static VideoFrameSidecarResult Result(
            Guid artifactId,
            VideoFrameSidecarRoleResultCode startCode,
            VideoFrameSidecarRoleResultCode endCode)
            => new(
                artifactId,
                new[]
                {
                    VideoFrameSidecarRoleResult.From(
                        VideoMediaRoles.StartFrame,
                        Rook.Services.Vision.Video.Extraction.VideoFrameSelector.First,
                        startCode),
                    VideoFrameSidecarRoleResult.From(
                        VideoMediaRoles.EndFrame,
                        Rook.Services.Vision.Video.Extraction.VideoFrameSelector.Last,
                        endCode),
                });
    }

    // Tiny media resolver for tests: synchronous, configurable.
    internal sealed class FakeVideoMediaResolver
        : IMediaResolver
    {
        public Func<MediaRef, ResolvedMedia>? OnResolve { get; set; }

        public Task<MediaResolutionResult> ResolveAllAsync(
            IReadOnlyList<MediaRef> refs,
            CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            var resolved = new Dictionary<MediaRef, ResolvedMedia>();
            foreach (var mediaRef in refs)
            {
                try
                {
                    resolved[mediaRef] = OnResolve?.Invoke(mediaRef)
                        ?? new ResolvedMedia(
                            Bytes: new byte[] { 0x89, 0x50, 0x4E, 0x47 },
                            MimeType: "image/png");
                }
                catch (NotSupportedException ex)
                {
                    return Task.FromResult(
                        MediaResolutionResult.Fail(
                            new GenerationError(
                                GenErrorCode.InvalidRequest,
                                ex.Message,
                                Retryable: false,
                                Field: "MediaRef")));
                }
            }

            return Task.FromResult(MediaResolutionResult.Ok(resolved));
        }
    }

    internal sealed class FailingEstimator : IVideoCostEstimator
    {
        private readonly Rook.Services.Vision.Generation.GenerationError _error;

        public FailingEstimator(Rook.Services.Vision.Generation.GenerationError error)
        {
            _error = error;
        }

        public VideoCostEstimateResult Estimate(
            ResolvedVideoModel model,
            VideoGenerationRequest request) =>
            VideoCostEstimateResult.Fail(_error);
    }

    internal sealed class StaticVideoResponseHandler : HttpMessageHandler
    {
        private readonly HttpStatusCode _statusCode;
        private readonly byte[] _bytes;
        private readonly string? _mimeType;

        public StaticVideoResponseHandler(
            HttpStatusCode statusCode,
            byte[]? bytes = null,
            string? mimeType = null)
        {
            _statusCode = statusCode;
            _bytes = bytes ?? Array.Empty<byte>();
            _mimeType = mimeType;
        }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            var response = new HttpResponseMessage(_statusCode);
            if (_statusCode == HttpStatusCode.OK)
            {
                response.Content = new ByteArrayContent(_bytes);
                if (!string.IsNullOrWhiteSpace(_mimeType))
                    response.Content.Headers.ContentType =
                        new System.Net.Http.Headers.MediaTypeHeaderValue(_mimeType);
            }

            return Task.FromResult(response);
        }
    }

    internal sealed class BlockingVideoResponseHandler : HttpMessageHandler
    {
        private readonly TaskCompletionSource<bool> _requestStarted =
            new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);

        public Task WaitForRequestAsync() => _requestStarted.Task;

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            _requestStarted.TrySetResult(true);
            await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken)
                .ConfigureAwait(false);
            throw new InvalidOperationException("Blocking handler should only exit by cancellation.");
        }
    }
}
