using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Vision;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Image.Jobs;
using Rook.Tests.Services.Vision.Image;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Jobs
{
    public class ImageJobManagerTests : IDisposable
    {
        private readonly string _root;
        private readonly ArtifactStore _artifactStore;
        private readonly FakeImageJobClock _clock = new();
        private readonly FakeImageJobIdGenerator _idGenerator = new();
        private readonly FakeImageProvider _provider = new();
        private readonly FakeImageJobLedger _ledger = new();
        private readonly IImageProviderRegistry _registry;

        public ImageJobManagerTests()
        {
            _root = Path.Combine(
                Path.GetTempPath(),
                $"rook-image-job-manager-{Guid.NewGuid():N}");
            _artifactStore = new ArtifactStore(Path.Combine(_root, "artifacts"));
            _registry = Registry(_provider);
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        [Fact]
        public async Task SubmitAsync_SyncProvider_CompletesAndWritesArtifact()
        {
            using var manager = Manager();

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

            Assert.Equal(ImageJobState.Queued, submit.State);
            Assert.Equal(ImageJobState.Complete, status.State);
            var artifact = _artifactStore.Get(status.ResultArtifactId!.Value);
            Assert.NotNull(artifact);
            Assert.Equal(VisionHandler.ArtifactKindGeneratedImage, artifact!.Kind);
            Assert.Equal("image", Assert.Single(artifact.Files).Role);
            Assert.Equal(new byte[] { 1, 2, 3 }, File.ReadAllBytes(
                _artifactStore.GetBlobAbsolutePath(artifact.Id, ImageMediaRoles.Image)));
        }

        [Fact]
        public async Task SubmitAsync_AppendsQueuedLedgerRecordBeforeBackgroundWork()
        {
            using var manager = Manager();

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);

            Assert.Equal(ImageJobState.Queued, submit.State);
            var queued = Assert.Single(
                _ledger.AllRecords,
                r => r.JobId == submit.JobId);
            Assert.Equal(ImageJobState.Queued, queued.State);
            Assert.Equal(GeminiImageCapabilities.ProviderName, queued.Provider);
            Assert.Equal(GeminiImageCapabilities.DefaultModel, queued.Model);
            Assert.Null(queued.ProviderJobId);
            await WaitForTerminalAsync(manager, submit.JobId!.Value);
        }

        [Fact]
        public async Task SubmitAsync_WhenInitialLedgerAppendFails_DoesNotCallProviderOrTrackRunningJob()
        {
            _ledger.BeforeAppend = _ => throw new IOException("ledger unavailable");
            using var manager = Manager();

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);

            Assert.Equal(ImageJobState.Error, submit.State);
            Assert.NotNull(submit.Error);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, submit.Error!.Code);
            Assert.DoesNotContain("Submit", _provider.Calls);
            await WaitForRunningJobCountAsync(manager, 0);
        }

        [Fact]
        public async Task SubmitAsync_AsyncProvider_PollsFetchesThenMaterializes()
        {
            _provider.OnSubmit = (_, _) => FakeImageProvider.Queued("job-123");
            var statusCalls = 0;
            _provider.OnGetStatus = handle =>
                ++statusCalls == 1
                    ? FakeImageProvider.Running()
                    : FakeImageProvider.Complete(handle);
            _provider.OnFetchResult = _ =>
                FakeImageProvider.ImageResult(new byte[] { 4, 5, 6 });
            using var manager = Manager(pollInterval: TimeSpan.FromMilliseconds(1));

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

            Assert.Equal(ImageJobState.Complete, status.State);
            Assert.Contains("Submit", _provider.Calls);
            Assert.Contains("GetStatus", _provider.Calls);
            Assert.Contains("FetchResult", _provider.Calls);
            Assert.Equal(new byte[] { 4, 5, 6 }, File.ReadAllBytes(
                _artifactStore.GetBlobAbsolutePath(
                    status.ResultArtifactId!.Value,
                ImageMediaRoles.Image)));
        }

        [Fact]
        public async Task AsyncSubmit_PersistsOnlyProviderJobIdOnPolling()
        {
            _provider.OnSubmit = (_, _) => new QueuedSubmitOutcome(new ProviderJobHandle(
                "prediction-789",
                statusUrl: new Uri("https://api.replicate.com/v1/predictions/prediction-789"),
                cancelUrl: new Uri("https://api.replicate.com/v1/predictions/prediction-789/cancel"),
                cancelHttpMethod: "POST",
                providerResultToken: "https://replicate.delivery/out.png"));
            _provider.OnGetStatus = _ => FakeImageProvider.Running();
            using var manager = Manager(pollInterval: TimeSpan.FromSeconds(5));

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            await WaitForStateAsync(manager, submit.JobId!.Value, ImageJobState.Polling);

            var polling = _ledger.AllRecords.Last(r => r.JobId == submit.JobId.Value);
            Assert.Equal(ImageJobState.Polling, polling.State);
            Assert.Equal("prediction-789", polling.ProviderJobId);
            var serialized = System.Text.Json.JsonSerializer.Serialize(polling);
            Assert.DoesNotContain("api.replicate.com", serialized);
            Assert.DoesNotContain("replicate.delivery", serialized);
        }

        [Fact]
        public async Task PollingLedgerAppendFailure_AttemptsProviderCancelAndStopsPolling()
        {
            _provider.OnSubmit = (_, _) => FakeImageProvider.Queued("prediction-fail-ledger");
            var cancelCalls = 0;
            _provider.OnCancel = handle =>
            {
                cancelCalls++;
                Assert.Equal("prediction-fail-ledger", handle.ProviderJobId);
                return new CanceledOutcome();
            };
            _ledger.BeforeAppend = record =>
            {
                if (record.State == ImageJobState.Polling)
                    throw new IOException("cannot persist provider id");
            };
            using var manager = Manager();

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

            Assert.Equal(ImageJobState.Error, status.State);
            Assert.Equal(1, cancelCalls);
            Assert.DoesNotContain(_ledger.AllRecords, r =>
                r.JobId == submit.JobId.Value && r.State == ImageJobState.Polling);
        }

        [Fact]
        public async Task TerminalProviderErrorAppendFailure_ReportsLedgerFailureInsteadOfUnpersistedProviderError()
        {
            var providerError = new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                "provider status failed",
                Retryable: true);
            _provider.OnSubmit = (_, _) => FakeImageProvider.Queued("job-status-error");
            _provider.OnGetStatus = _ => FakeImageProvider.StatusFailed(providerError);
            var failedProviderErrorAppend = false;
            _ledger.BeforeAppend = record =>
            {
                if (!failedProviderErrorAppend
                    && record.State == ImageJobState.Error
                    && record.Error?.Message == providerError.Message)
                {
                    failedProviderErrorAppend = true;
                    throw new IOException("cannot persist provider error");
                }
            };
            using var manager = Manager();

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            await WaitForRunningJobCountAsync(manager, 0);
            var status = await manager.GetStatusAsync(
                submit.JobId!.Value,
                CancellationToken.None);
            var list = await manager.ListJobsAsync(10, CancellationToken.None);

            Assert.True(failedProviderErrorAppend);
            Assert.Equal(ImageJobState.Error, status.State);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, status.Error!.Code);
            Assert.Contains("Image job ledger is unavailable", status.Error.Message);
            Assert.DoesNotContain(providerError.Message, status.Error.Message);
            var listed = Assert.Single(list.Jobs, j => j.JobId == submit.JobId.Value);
            Assert.Equal(status.Error.Message, listed.Error!.Message);
            var latest = _ledger.AllRecords.Last(r => r.JobId == submit.JobId.Value);
            Assert.Equal(ImageJobState.Error, latest.State);
            Assert.Equal(status.Error.Message, latest.Error!.Message);
        }

        [Fact]
        public async Task CompleteTransition_AppendsSingleDurableComplete()
        {
            using var manager = Manager();

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

            Assert.Equal(ImageJobState.Complete, status.State);
            var complete = Assert.Single(_ledger.AllRecords, r =>
                r.JobId == submit.JobId.Value && r.State == ImageJobState.Complete);
            Assert.Equal(status.ResultArtifactId, complete.ResultArtifactId);
        }

        [Fact]
        public async Task SubmitAsync_UsesExplicitResolvedModelForUnregisteredModel()
        {
            var provider = new FakeImageProvider();
            var model = "gemini-future-image-preview";
            using var manager = Manager();

            var submit = await manager.SubmitAsync(
                Start(model, SyntheticResolvedModel(provider, model)),
                CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

            Assert.Equal(ImageJobState.Complete, status.State);
            Assert.Contains("Submit", provider.Calls);
            Assert.DoesNotContain("Submit", _provider.Calls);
        }

        [Fact]
        public async Task ProviderCompleteIsNotJobCompleteUntilMaterializationSucceeds()
        {
            _provider.OnSubmit = (_, _) => FakeImageProvider.Queued("job-remote-fail");
            _provider.OnGetStatus = handle => FakeImageProvider.Complete(handle);
            _provider.OnFetchResult = _ =>
                FakeImageProvider.RemoteImageResult(
                    "https://cdn.example.test/out.png",
                    declaredMime: "image/png");
            var materializer = new ImageArtifactMaterializer(
                new StaticImageResponseHandler(HttpStatusCode.ServiceUnavailable));
            using var manager = Manager(materializer: materializer);

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

            Assert.Equal(ImageJobState.Error, status.State);
            Assert.Null(status.ResultArtifactId);
            Assert.Empty(_artifactStore.List());
        }

        [Fact]
        public async Task RemoteProviderOwnedArtifactUsesAuthenticatedRequestFactory()
        {
            _provider.OnSubmit = (_, _) => new SyncSubmitOutcome(
                FakeImageProvider.RemoteImageResult(
                    "https://api.example.test/files/out.png",
                    declaredMime: "image/png",
                    requiresAuthenticatedFetch: true));
            var handler = new CapturingImageResponseHandler();
            var selectorCalls = 0;
            using var manager = Manager(
                materializer: new ImageArtifactMaterializer(handler),
                selector: (_, artifact) =>
                {
                    selectorCalls++;
                    return requestedArtifact =>
                    {
                        var request = new HttpRequestMessage(
                            HttpMethod.Get,
                            ((RemoteArtifactBody)requestedArtifact.Body).Url);
                        request.Headers.Authorization =
                            new AuthenticationHeaderValue("Bearer", "r8-token");
                        return ImageArtifactFetchRequest.Created(request);
                    };
                });

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

            Assert.Equal(ImageJobState.Complete, status.State);
            Assert.Equal(1, selectorCalls);
            Assert.Equal("Bearer", handler.Authorization!.Scheme);
            Assert.Equal("r8-token", handler.Authorization.Parameter);
        }

        [Fact]
        public async Task PublicFalStyleArtifactDoesNotUseAuthenticatedRequestFactory()
        {
            _provider.OnSubmit = (_, _) => new SyncSubmitOutcome(
                FakeImageProvider.RemoteImageResult(
                    "https://fal.media/files/out.png",
                    declaredMime: "image/png"));
            var handler = new CapturingImageResponseHandler();
            var selectorCalls = 0;
            using var manager = Manager(
                materializer: new ImageArtifactMaterializer(handler),
                selector: (_, __) =>
                {
                    selectorCalls++;
                    return _ => throw new InvalidOperationException(
                        "Public artifacts must not use authenticated fetch.");
                });

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

            Assert.Equal(ImageJobState.Complete, status.State);
            Assert.Equal(0, selectorCalls);
            Assert.Null(handler.Authorization);
        }

        [Fact]
        public async Task CancelAsync_WithProviderHandle_CallsProviderCancel()
        {
            _provider.OnSubmit = (_, _) => FakeImageProvider.Queued("job-cancel");
            _provider.OnGetStatus = _ => FakeImageProvider.Running();
            var cancelCalls = 0;
            _provider.OnCancel = _ =>
            {
                cancelCalls++;
                return new CanceledOutcome();
            };
            using var manager = Manager(pollInterval: TimeSpan.FromSeconds(5));

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            await WaitForStateAsync(manager, submit.JobId!.Value, ImageJobState.Polling);
            var cancel = await manager.CancelAsync(submit.JobId.Value, CancellationToken.None);

            Assert.Equal(ImageJobState.Cancelled, cancel.State);
            Assert.Equal(1, cancelCalls);
        }

        [Fact]
        public async Task CancelAsync_ImmediatelyAfterSubmit_CleansRunningJob()
        {
            _provider.OnSubmit = (_, _) => FakeImageProvider.Queued("job-cancel-queued");
            _provider.OnGetStatus = _ => FakeImageProvider.Running();
            using var manager = Manager(pollInterval: TimeSpan.FromSeconds(5));

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var cancel = await manager.CancelAsync(submit.JobId!.Value, CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId.Value);

            Assert.Equal(ImageJobState.Cancelled, cancel.State);
            Assert.Equal(ImageJobState.Cancelled, status.State);
            await WaitForRunningJobCountAsync(manager, 0);
        }

        [Fact]
        public async Task CancelAsync_ImmediatelyAfterSubmit_AppendsDurableCancelled()
        {
            _provider.OnSubmit = (_, _) => FakeImageProvider.Queued("job-cancel-ledger");
            _provider.OnGetStatus = _ => FakeImageProvider.Running();
            using var manager = Manager(pollInterval: TimeSpan.FromSeconds(5));

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var cancel = await manager.CancelAsync(submit.JobId!.Value, CancellationToken.None);

            Assert.Equal(ImageJobState.Cancelled, cancel.State);
            var cancelled = Assert.Single(_ledger.AllRecords, r =>
                r.JobId == submit.JobId.Value && r.State == ImageJobState.Cancelled);
            Assert.Equal(GenerationErrorCode.Cancelled, cancelled.Error!.Code);
        }

        [Fact]
        public async Task CancelAsync_WhenDurableCancelledAppendFails_ReturnsFailure()
        {
            _provider.OnSubmit = (_, _) => FakeImageProvider.Queued("job-cancel-append-fail");
            _provider.OnGetStatus = _ => FakeImageProvider.Running();
            _ledger.BeforeAppend = record =>
            {
                if (record.State == ImageJobState.Cancelled)
                    throw new IOException("cannot persist cancellation");
            };
            using var manager = Manager(pollInterval: TimeSpan.FromSeconds(5));

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var cancel = await manager.CancelAsync(submit.JobId!.Value, CancellationToken.None);

            Assert.Equal(ImageJobState.Error, cancel.State);
            Assert.NotNull(cancel.Error);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, cancel.Error!.Code);
            Assert.DoesNotContain(_ledger.AllRecords, r =>
                r.JobId == submit.JobId.Value && r.State == ImageJobState.Cancelled);
            var status = await manager.GetStatusAsync(
                submit.JobId.Value,
                CancellationToken.None);
            Assert.Equal(ImageJobState.Error, status.State);
            var list = await manager.ListJobsAsync(10, CancellationToken.None);
            var listed = Assert.Single(
                list.Jobs,
                job => job.JobId == submit.JobId.Value);
            Assert.Equal(ImageJobState.Error, listed.State);
        }

        [Fact]
        public async Task CancelAsync_WhenProviderAlreadyTerminal_DoesNotStampLocalCancelled()
        {
            _provider.OnSubmit = (_, _) => FakeImageProvider.Queued("job-already-terminal");
            _provider.OnGetStatus = _ => FakeImageProvider.Running();
            _provider.OnCancel = _ =>
                new AlreadyTerminalOutcome(GenerationLifecycleState.Completed);
            using var manager = Manager(pollInterval: TimeSpan.FromSeconds(5));

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            await WaitForStateAsync(manager, submit.JobId!.Value, ImageJobState.Polling);
            var cancel = await manager.CancelAsync(submit.JobId.Value, CancellationToken.None);
            var status = await manager.GetStatusAsync(submit.JobId.Value, CancellationToken.None);

            Assert.Equal(ImageJobState.Polling, cancel.State);
            Assert.Equal(ImageJobState.Polling, status.State);
        }

        [Theory]
        [InlineData(ImageJobState.Complete)]
        [InlineData(ImageJobState.Error)]
        public async Task CancelAsync_WhenRemoteCancelRacesWithTerminalRecord_DoesNotOverwriteTerminal(
            ImageJobState terminalState)
        {
            using var manager = Manager();
            var jobId = Guid.Parse("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");
            var handle = new ProviderJobHandle("job-race-terminal");
            var polling = new ImageJobRecord(
                jobId,
                ImageJobState.Polling,
                GeminiImageCapabilities.DefaultModel,
                GeminiImageCapabilities.ProviderName,
                DateTimeOffset.UtcNow,
                DateTimeOffset.UtcNow,
                providerHandle: handle);
            SetRecord(manager, polling);
            _provider.OnCancel = _ =>
            {
                SetRecord(manager, TerminalRecord(jobId, terminalState, handle));
                return new CanceledOutcome();
            };

            var cancel = await manager.CancelAsync(jobId, CancellationToken.None);
            var status = await manager.GetStatusAsync(jobId, CancellationToken.None);

            Assert.Equal(terminalState, cancel.State);
            Assert.Equal(terminalState, status.State);
        }

        [Fact]
        public async Task CancelAsync_WhenTerminalRecordLandsDuringFinalLocalCancel_DoesNotOverwriteTerminal()
        {
            using var manager = Manager();
            var jobId = Guid.Parse("bbbbbbbb-cccc-dddd-eeee-ffffffffffff");
            var polling = new ImageJobRecord(
                jobId,
                ImageJobState.Polling,
                GeminiImageCapabilities.DefaultModel,
                GeminiImageCapabilities.ProviderName,
                DateTimeOffset.UtcNow,
                DateTimeOffset.UtcNow);
            SetRecord(manager, polling);
            manager.BeforeLocalCancelTryUpdateForTests = id =>
            {
                var handle = new ProviderJobHandle("job-final-window");
                SetRecord(manager, TerminalRecord(id, ImageJobState.Complete, handle));
            };

            var cancel = await manager.CancelAsync(jobId, CancellationToken.None);
            var status = await manager.GetStatusAsync(jobId, CancellationToken.None);

            Assert.Equal(ImageJobState.Complete, cancel.State);
            Assert.Equal(ImageJobState.Complete, status.State);
        }

        [Fact]
        public async Task CancelAsync_WhenProviderCancelThrows_ReturnsFailureAndPreservesLocalState()
        {
            _provider.OnSubmit = (_, _) => FakeImageProvider.Queued("job-cancel-throws");
            _provider.OnGetStatus = _ => FakeImageProvider.Running();
            _provider.OnCancel = _ =>
                throw new InvalidOperationException("cancel transport down");
            using var manager = Manager(pollInterval: TimeSpan.FromSeconds(5));

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            await WaitForStateAsync(manager, submit.JobId!.Value, ImageJobState.Polling);
            var cancel = await manager.CancelAsync(submit.JobId.Value, CancellationToken.None);
            var status = await manager.GetStatusAsync(submit.JobId.Value, CancellationToken.None);

            Assert.Equal(ImageJobState.Error, cancel.State);
            Assert.NotNull(cancel.Error);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, cancel.Error!.Code);
            Assert.True(cancel.Error.Retryable);
            Assert.Contains("cancel transport down", cancel.Error.Message);
            Assert.Equal(ImageJobState.Polling, status.State);
        }

        [Fact]
        public async Task CancelAsync_WhenProviderCancelTimesOutWithoutCallerCancellation_ReturnsFailureAndPreservesLocalState()
        {
            _provider.OnSubmit = (_, _) => FakeImageProvider.Queued("job-cancel-timeout");
            _provider.OnGetStatus = _ => FakeImageProvider.Running();
            _provider.OnCancel = _ => throw new TaskCanceledException("provider timeout");
            using var manager = Manager(pollInterval: TimeSpan.FromSeconds(5));

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            await WaitForStateAsync(manager, submit.JobId!.Value, ImageJobState.Polling);
            var cancel = await manager.CancelAsync(submit.JobId.Value, CancellationToken.None);
            var status = await manager.GetStatusAsync(submit.JobId.Value, CancellationToken.None);

            Assert.Equal(ImageJobState.Error, cancel.State);
            Assert.NotNull(cancel.Error);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, cancel.Error!.Code);
            Assert.True(cancel.Error.Retryable);
            Assert.Contains("provider timeout", cancel.Error.Message);
            Assert.Equal(ImageJobState.Polling, status.State);
        }

        [Fact]
        public async Task CancelAsync_DuringMaterialization_CancelsLocalFetchAndAttemptsProviderCancel()
        {
            _provider.OnSubmit = (_, _) => FakeImageProvider.Queued("job-materializing");
            _provider.OnGetStatus = handle => FakeImageProvider.Complete(handle);
            _provider.OnFetchResult = _ =>
                FakeImageProvider.RemoteImageResult(
                    "https://cdn.example.test/out.png",
                    declaredMime: "image/png");
            var cancelCalls = 0;
            _provider.OnCancel = _ =>
            {
                cancelCalls++;
                return new CanceledOutcome();
            };
            var handler = new BlockingImageResponseHandler();
            using var manager = Manager(
                materializer: new ImageArtifactMaterializer(handler));

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            await WaitForSignalAsync(
                handler.WaitForRequestAsync(),
                "Image materialization request did not start.");
            var cancel = await manager.CancelAsync(submit.JobId!.Value, CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId.Value);

            Assert.Equal(ImageJobState.Cancelled, cancel.State);
            Assert.Equal(ImageJobState.Cancelled, status.State);
            Assert.Equal(1, cancelCalls);
        }

        [Fact]
        public async Task CancelAsync_DuringMaterialization_WhenProviderAlreadyTerminal_CancelsLocalFetch()
        {
            _provider.OnSubmit = (_, _) => FakeImageProvider.Queued("job-materializing-terminal");
            _provider.OnGetStatus = handle => FakeImageProvider.Complete(handle);
            _provider.OnFetchResult = _ =>
                FakeImageProvider.RemoteImageResult(
                    "https://cdn.example.test/out.png",
                    declaredMime: "image/png");
            var cancelCalls = 0;
            _provider.OnCancel = _ =>
            {
                cancelCalls++;
                return new AlreadyTerminalOutcome(GenerationLifecycleState.Completed);
            };
            var handler = new BlockingImageResponseHandler();
            using var manager = Manager(
                materializer: new ImageArtifactMaterializer(handler));

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            await WaitForSignalAsync(
                handler.WaitForRequestAsync(),
                "Image materialization request did not start.");
            var cancel = await manager.CancelAsync(submit.JobId!.Value, CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId.Value);

            Assert.Equal(ImageJobState.Cancelled, cancel.State);
            Assert.Equal(ImageJobState.Cancelled, status.State);
            Assert.Equal(1, cancelCalls);
            await WaitForArtifactCountAsync(0);
        }

        [Fact]
        public async Task CompleteTransition_WhenCancelledRecordWinsFinalRace_DoesNotOverwriteCancelled()
        {
            using var manager = Manager();
            manager.BeforeCompleteTransitionForTests = id =>
            {
                SetRecord(manager, new ImageJobRecord(
                    id,
                    ImageJobState.Cancelled,
                    GeminiImageCapabilities.DefaultModel,
                    GeminiImageCapabilities.ProviderName,
                    DateTimeOffset.MaxValue,
                    DateTimeOffset.MaxValue,
                    error: new GenerationError(
                        GenerationErrorCode.Cancelled,
                        "Image job cancelled.",
                        Retryable: false)));
            };

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

            Assert.Equal(ImageJobState.Cancelled, status.State);
            Assert.Null(status.ResultArtifactId);
            await WaitForArtifactCountAsync(0);
        }

        [Fact]
        public async Task FetchResultAsync_CompleteStateVerifiesArtifactStillExists()
        {
            using var manager = Manager();
            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            var complete = await WaitForTerminalAsync(manager, submit.JobId!.Value);
            Assert.True(_artifactStore.Delete(complete.ResultArtifactId!.Value));

            var fetch = await manager.FetchResultAsync(
                submit.JobId.Value,
                CancellationToken.None);

            Assert.Equal(ImageJobState.Error, fetch.State);
            Assert.NotNull(fetch.Error);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, fetch.Error!.Code);
        }

        [Fact]
        public async Task StatusAndList_SurviveNewManagerOverSameLedger()
        {
            using (var first = Manager())
            {
                var submit = await first.SubmitAsync(Start(), CancellationToken.None);
                _ = await WaitForTerminalAsync(first, submit.JobId!.Value);
            }
            using var second = Manager();

            var jobs = await second.ListJobsAsync(10, CancellationToken.None);
            var record = Assert.Single(jobs.Jobs);
            var status = await second.GetStatusAsync(record.JobId, CancellationToken.None);

            Assert.Equal(ImageJobState.Complete, record.State);
            Assert.Equal(ImageJobState.Complete, status.State);
            Assert.NotNull(status.ResultArtifactId);
        }

        [Fact]
        public async Task FetchResultAsync_AfterRestart_VerifiesArtifactExists()
        {
            Guid jobId;
            Guid artifactId;
            using (var first = Manager())
            {
                var submit = await first.SubmitAsync(Start(), CancellationToken.None);
                var complete = await WaitForTerminalAsync(first, submit.JobId!.Value);
                jobId = submit.JobId.Value;
                artifactId = complete.ResultArtifactId!.Value;
            }
            using var second = Manager();

            var fetch = await second.FetchResultAsync(jobId, CancellationToken.None);

            Assert.Equal(ImageJobState.Complete, fetch.State);
            Assert.Equal(artifactId, fetch.ResultArtifactId);
            Assert.Equal($"/blob/{artifactId:D}/image", Assert.Single(fetch.Files!).Path);
        }

        [Fact]
        public async Task FetchResultAsync_AfterRestartMissingArtifact_ReturnsDependencyUnavailable()
        {
            Guid jobId;
            Guid artifactId;
            using (var first = Manager())
            {
                var submit = await first.SubmitAsync(Start(), CancellationToken.None);
                var complete = await WaitForTerminalAsync(first, submit.JobId!.Value);
                jobId = submit.JobId.Value;
                artifactId = complete.ResultArtifactId!.Value;
            }
            Assert.True(_artifactStore.Delete(artifactId));
            using var second = Manager();

            var fetch = await second.FetchResultAsync(jobId, CancellationToken.None);

            Assert.Equal(ImageJobState.Error, fetch.State);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, fetch.Error!.Code);
            Assert.Equal("result_artifact_id", fetch.Error.Field);
        }

        [Theory]
        [InlineData(ImageJobState.Queued)]
        [InlineData(ImageJobState.Submitting)]
        [InlineData(ImageJobState.Polling)]
        [InlineData(ImageJobState.Materializing)]
        public void ReconcileInterruptedJobs_MarksPriorNonTerminalRecordsInterrupted(
            ImageJobState state)
        {
            var jobId = Guid.NewGuid();
            var initial = ImageJobLedgerRecordFactory.FromInitial(
                jobId,
                GeminiImageCapabilities.ProviderName,
                GeminiImageCapabilities.DefaultModel,
                state,
                _clock.UtcNow());
            var stale = state == ImageJobState.Polling
                ? ImageJobLedgerRecordFactory.WithState(
                    initial,
                    state,
                    initial.UpdatedAt.AddSeconds(1),
                    providerJobId: "provider-job-1")
                : initial;
            _ledger.Append(stale);
            using var manager = Manager();

            manager.ReconcileInterruptedJobs();

            var latest = _ledger.AllRecords.Last(r => r.JobId == jobId);
            Assert.Equal(ImageJobState.Interrupted, latest.State);
            Assert.Equal(stale.ProviderJobId, latest.ProviderJobId);
            Assert.Equal(GenerationErrorCode.Interrupted, latest.Error!.Code);
            Assert.DoesNotContain("Submit", _provider.Calls);
            Assert.DoesNotContain("GetStatus", _provider.Calls);
        }

        [Fact]
        public void ReconcileInterruptedJobs_DoesNotTouchTerminalRecords()
        {
            var jobId = Guid.NewGuid();
            var complete = ImageJobLedgerRecordFactory.WithState(
                ImageJobLedgerRecordFactory.FromInitial(
                    jobId,
                    GeminiImageCapabilities.ProviderName,
                    GeminiImageCapabilities.DefaultModel,
                    ImageJobState.Queued,
                    _clock.UtcNow()),
                ImageJobState.Complete,
                _clock.UtcNow().AddSeconds(1),
                resultArtifactId: Guid.NewGuid());
            _ledger.Append(complete);
            using var manager = Manager();

            manager.ReconcileInterruptedJobs();

            Assert.Single(_ledger.AllRecords, r => r.JobId == jobId);
        }

        [Fact]
        public async Task CancelAsync_AfterRestartInterruptedWithProviderJobId_CallsProviderCancelAndAppendsCancelled()
        {
            var jobId = Guid.NewGuid();
            var interrupted = ImageJobLedgerRecordFactory.WithState(
                ImageJobLedgerRecordFactory.FromInitial(
                    jobId,
                    GeminiImageCapabilities.ProviderName,
                    GeminiImageCapabilities.DefaultModel,
                    ImageJobState.Polling,
                    _clock.UtcNow()),
                ImageJobState.Interrupted,
                _clock.UtcNow().AddSeconds(1),
                providerJobId: "provider-job-cancel",
                error: new GenerationError(
                    GenerationErrorCode.Interrupted,
                    "interrupted",
                    Retryable: true));
            _ledger.Append(interrupted);
            var cancelCalls = 0;
            _provider.OnCancel = handle =>
            {
                cancelCalls++;
                Assert.Equal("provider-job-cancel", handle.ProviderJobId);
                Assert.Null(handle.CancelUrl);
                Assert.Null(handle.StatusUrl);
                Assert.Null(handle.ProviderResultToken);
                return new CanceledOutcome();
            };
            using var manager = Manager();

            var result = await manager.CancelAsync(jobId, CancellationToken.None);

            Assert.Equal(ImageJobState.Cancelled, result.State);
            Assert.Equal(1, cancelCalls);
            Assert.Equal(
                ImageJobState.Cancelled,
                _ledger.AllRecords.Last(r => r.JobId == jobId).State);
        }

        [Fact]
        public async Task CancelAsync_AfterRestartInterruptedWithoutProviderJobId_ReturnsInterruptedUnchanged()
        {
            var jobId = Guid.NewGuid();
            var interrupted = ImageJobLedgerRecordFactory.WithState(
                ImageJobLedgerRecordFactory.FromInitial(
                    jobId,
                    GeminiImageCapabilities.ProviderName,
                    GeminiImageCapabilities.DefaultModel,
                    ImageJobState.Polling,
                    _clock.UtcNow()),
                ImageJobState.Interrupted,
                _clock.UtcNow().AddSeconds(1),
                error: new GenerationError(
                    GenerationErrorCode.Interrupted,
                    "interrupted",
                    Retryable: true));
            _ledger.Append(interrupted);
            using var manager = Manager();

            var result = await manager.CancelAsync(jobId, CancellationToken.None);

            Assert.Equal(ImageJobState.Interrupted, result.State);
            Assert.DoesNotContain("Cancel", _provider.Calls);
            Assert.Single(_ledger.AllRecords, r => r.JobId == jobId);
        }

        [Fact]
        public async Task CancelAsync_AfterRestartRemoteCancelSucceedsButCancelledAppendFails_ReturnsFailureAndLeavesInterrupted()
        {
            var jobId = Guid.NewGuid();
            var interrupted = ImageJobLedgerRecordFactory.WithState(
                ImageJobLedgerRecordFactory.FromInitial(
                    jobId,
                    GeminiImageCapabilities.ProviderName,
                    GeminiImageCapabilities.DefaultModel,
                    ImageJobState.Polling,
                    _clock.UtcNow()),
                ImageJobState.Interrupted,
                _clock.UtcNow().AddSeconds(1),
                providerJobId: "provider-job-cancel-append-fails",
                error: new GenerationError(
                    GenerationErrorCode.Interrupted,
                    "interrupted",
                    Retryable: true));
            _ledger.Append(interrupted);
            _provider.OnCancel = _ => new CanceledOutcome();
            _ledger.BeforeAppend = record =>
            {
                if (record.State == ImageJobState.Cancelled)
                    throw new IOException("cancelled append failed");
            };
            using var manager = Manager();

            var result = await manager.CancelAsync(jobId, CancellationToken.None);

            Assert.Equal(ImageJobState.Error, result.State);
            Assert.NotNull(result.Error);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, result.Error!.Code);
            Assert.Equal(
                ImageJobState.Interrupted,
                _ledger.AllRecords.Last(r => r.JobId == jobId).State);
        }

        [Fact]
        public async Task GeneratePathStillRejectsAsyncProviderOutsideJobManager()
        {
            var inputPath = Path.Combine(_root, "input.png");
            Directory.CreateDirectory(_root);
            File.WriteAllBytes(inputPath, new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00 });
            _provider.OnSubmit = (_, _) => FakeImageProvider.Queued("job-outside-manager");
            var handler = new VisionHandler(
                _artifactStore,
                new EmptyGenerationSecretStore(),
                new PromptEnhancer(),
                new ViewportHandler(),
                _registry);
            var args = VisionHandler.ParseObjectBody($$"""
                {
                  "prompt": "red cube",
                  "input_image_path": {{JsonValue.Create(inputPath)!.ToJsonString()}},
                  "model": "{{GeminiImageCapabilities.DefaultModel}}",
                  "resolution": "1K",
                  "aspect_ratio": "1:1"
                }
                """);

            var response = await handler.GenerateAsync(args, CancellationToken.None);

            Assert.False(response.Success);
            Assert.Equal(
                "Image generation failed. Provider returned an async job.",
                Assert.IsType<string>(response.Data));
        }

        private ImageJobManager Manager(
            TimeSpan? pollInterval = null,
            ImageArtifactMaterializer? materializer = null,
            ImageArtifactRequestFactorySelector? selector = null,
            IImageJobLedger? ledger = null) =>
            new(
                registry: _registry,
                artifactStore: _artifactStore,
                clock: _clock,
                idGenerator: _idGenerator,
                pollInterval: pollInterval ?? TimeSpan.FromMilliseconds(1),
                maxConcurrentJobs: ImageJobManager.DefaultMaxConcurrentJobs,
                materializer: materializer,
                requestFactorySelector: selector,
                ledger: ledger ?? _ledger);

        private static ImageJobStartRequest Start(
            string model = GeminiImageCapabilities.DefaultModel,
            ResolvedImageModel? resolvedModel = null) =>
            new(
                new ImageGenerationRequest(
                    Model: model,
                    Prompt: "red cube",
                    Resolution: "1K",
                    AspectRatio: "",
                    NumberOfImages: 1,
                    ReferenceImages: null,
                    Options: new GeminiImageOptions()),
                new Dictionary<MediaRef, ResolvedMedia>(),
                Array.Empty<Guid>(),
                resolvedModel);

        private static ResolvedImageModel SyntheticResolvedModel(
            IImageProvider provider,
            string model) =>
            new(
                ModelId: model,
                ProviderName: GeminiImageCapabilities.ProviderName,
                SubmissionMode: ImageSubmissionMode.Sync,
                Provider: provider,
                Capability: new ImageCapability(
                    Id: model,
                    Name: model,
                    Status: "preview",
                    Resolutions: new[] { "1K" },
                    AspectRatios: new[] { "1:1" },
                    MaxReferenceImages: 0,
                    SupportsImageToImage: true,
                    SupportsTextToImage: true),
                PricingModel: new GeminiImagePricingModel(),
                OptionsCodec: new GeminiImageOptionsCodec());

        private async Task<ImageJobStatusResult> WaitForTerminalAsync(
            ImageJobManager manager,
            Guid jobId)
        {
            var deadline = DateTime.UtcNow.AddSeconds(5);
            ImageJobStatusResult? last = null;
            while (DateTime.UtcNow < deadline)
            {
                last = await manager.GetStatusAsync(jobId, CancellationToken.None);
                if (IsTerminal(last.State)) return last;
                await Task.Delay(10);
            }

            throw new TimeoutException(
                $"Job did not reach terminal state. Last state: {last?.State}.");
        }

        private static async Task WaitForStateAsync(
            ImageJobManager manager,
            Guid jobId,
            ImageJobState expected)
        {
            var deadline = DateTime.UtcNow.AddSeconds(5);
            while (DateTime.UtcNow < deadline)
            {
                var status = await manager.GetStatusAsync(jobId, CancellationToken.None);
                if (status.State == expected) return;
                await Task.Delay(10);
            }

            throw new TimeoutException($"Job did not reach state {expected}.");
        }

        private static async Task WaitForSignalAsync(
            Task signal,
            string timeoutMessage)
        {
            var timeout = Task.Delay(TimeSpan.FromSeconds(2));
            if (await Task.WhenAny(signal, timeout) != signal)
                throw new TimeoutException(timeoutMessage);

            await signal.ConfigureAwait(false);
        }

        private async Task WaitForArtifactCountAsync(int expected)
        {
            var deadline = DateTimeOffset.UtcNow.AddSeconds(2);
            while (DateTimeOffset.UtcNow < deadline)
            {
                if (_artifactStore.List().Count == expected)
                    return;

                await Task.Delay(10);
            }

            Assert.Equal(expected, _artifactStore.List().Count);
        }

        private static async Task WaitForRunningJobCountAsync(
            ImageJobManager manager,
            int expected)
        {
            var deadline = DateTimeOffset.UtcNow.AddSeconds(2);
            while (DateTimeOffset.UtcNow < deadline)
            {
                if (RunningJobCount(manager) == expected)
                    return;

                await Task.Delay(10);
            }

            Assert.Equal(expected, RunningJobCount(manager));
        }

        private ImageJobRecord TerminalRecord(
            Guid jobId,
            ImageJobState state,
            ProviderJobHandle handle)
        {
            if (state == ImageJobState.Complete)
            {
                var artifact = _artifactStore.Create(
                    VisionHandler.ArtifactKindGeneratedImage,
                    new[]
                    {
                        new BlobInput(ImageMediaRoles.Image, new byte[] { 1 }, "png"),
                    });
                return new ImageJobRecord(
                    jobId,
                    ImageJobState.Complete,
                    GeminiImageCapabilities.DefaultModel,
                    GeminiImageCapabilities.ProviderName,
                    DateTimeOffset.UtcNow.AddMilliseconds(1),
                    DateTimeOffset.UtcNow.AddMilliseconds(1),
                    providerHandle: handle,
                    resultArtifactId: artifact.Id);
            }

            return new ImageJobRecord(
                jobId,
                ImageJobState.Error,
                GeminiImageCapabilities.DefaultModel,
                GeminiImageCapabilities.ProviderName,
                DateTimeOffset.UtcNow.AddMilliseconds(1),
                DateTimeOffset.UtcNow.AddMilliseconds(1),
                providerHandle: handle,
                error: new GenerationError(
                    GenerationErrorCode.ExecutionFailed,
                    "terminal provider error",
                    Retryable: false));
        }

        private static void SetRecord(
            ImageJobManager manager,
            ImageJobRecord record)
        {
            var field = typeof(ImageJobManager).GetField(
                "_records",
                BindingFlags.NonPublic | BindingFlags.Instance);
            var records = Assert.IsType<ConcurrentDictionary<Guid, ImageJobRecord>>(
                field!.GetValue(manager));
            records[record.JobId] = record;
        }

        private static int RunningJobCount(ImageJobManager manager)
        {
            var field = typeof(ImageJobManager).GetField(
                "_runningJobs",
                BindingFlags.NonPublic | BindingFlags.Instance);
            var running = field!.GetValue(manager)!;
            var count = running.GetType().GetProperty("Count");
            return Assert.IsType<int>(count!.GetValue(running));
        }

        private static bool IsTerminal(ImageJobState state) =>
            state is ImageJobState.Complete
              or ImageJobState.Error
              or ImageJobState.Cancelled
              or ImageJobState.Interrupted;

        private static IImageProviderRegistry Registry(IImageProvider provider) =>
            new DefaultImageProviderRegistry(new[]
            {
                new TestImageProviderRegistration(provider),
            });

        private sealed class TestImageProviderRegistration : IImageProviderRegistration
        {
            public TestImageProviderRegistration(IImageProvider provider)
            {
                Provider = provider;
            }

            public string ProviderName => GeminiImageCapabilities.ProviderName;
            public ImageSubmissionMode SubmissionMode => ImageSubmissionMode.Sync;
            public IImageProvider Provider { get; }
            public IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec { get; }
                = new GeminiImageOptionsCodec();
            public IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> Models { get; }
                = new Dictionary<string, (ImageCapability, IPricingModel<ImageGenerationRequest, ImageCapability>)>
                {
                    [GeminiImageCapabilities.DefaultModel] = (
                        GeminiImageCapabilities.Models[GeminiImageCapabilities.DefaultModel],
                        new GeminiImagePricingModel()),
                };
            public IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; }
                = Array.Empty<ProviderSecretRequirement>();
        }

        private sealed class EmptyGenerationSecretStore : IGenerationSecretStore
        {
            public string? GetSecret(string secretKey) => null;
            public void SetSecret(string secretKey, string value) { }
            public void RemoveSecret(string secretKey) { }
            public bool HasSecret(string secretKey) => false;
            public string? GetPreview(string secretKey) => null;
        }

        private sealed class StaticImageResponseHandler : HttpMessageHandler
        {
            private readonly HttpStatusCode _statusCode;

            public StaticImageResponseHandler(HttpStatusCode statusCode)
            {
                _statusCode = statusCode;
            }

            protected override Task<HttpResponseMessage> SendAsync(
                HttpRequestMessage request,
                CancellationToken cancellationToken)
            {
                var response = new HttpResponseMessage(_statusCode);
                if (_statusCode == HttpStatusCode.OK)
                {
                    response.Content = new ByteArrayContent(new byte[] { 9, 8, 7 });
                    response.Content.Headers.ContentType =
                        new MediaTypeHeaderValue("image/png");
                }

                return Task.FromResult(response);
            }
        }

        private sealed class CapturingImageResponseHandler : HttpMessageHandler
        {
            public AuthenticationHeaderValue? Authorization { get; private set; }

            protected override Task<HttpResponseMessage> SendAsync(
                HttpRequestMessage request,
                CancellationToken cancellationToken)
            {
                Authorization = request.Headers.Authorization;
                var response = new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 9, 8, 7 }),
                };
                response.Content.Headers.ContentType =
                    new MediaTypeHeaderValue("image/png");
                return Task.FromResult(response);
            }
        }

        private sealed class BlockingImageResponseHandler : HttpMessageHandler
        {
            private readonly TaskCompletionSource<bool> _requestStarted =
                new(TaskCreationOptions.RunContinuationsAsynchronously);

            public Task WaitForRequestAsync() => _requestStarted.Task;

            protected override async Task<HttpResponseMessage> SendAsync(
                HttpRequestMessage request,
                CancellationToken cancellationToken)
            {
                _requestStarted.TrySetResult(true);
                await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken)
                    .ConfigureAwait(false);
                throw new InvalidOperationException(
                    "Blocking handler should exit only through cancellation.");
            }
        }
    }
}
