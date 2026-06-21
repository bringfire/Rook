using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Reconstruction;
using Rook.Services.Reconstruction.Fal;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionJobManagerTests : IDisposable
{
    private const string HunyuanModelId = "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d";

    private readonly List<string> _roots = new();
    private readonly List<ReconstructionJobManager> _managers = new();

    public void Dispose()
    {
        // Drain background loops BEFORE deleting the temp dirs they write into.
        foreach (var manager in _managers)
        {
            try { manager.Dispose(); }
            catch { /* idempotent best-effort teardown */ }
        }

        foreach (var root in _roots)
        {
            if (Directory.Exists(root))
                Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task Submit_QueuesJobAndRecordsProviderPollingHandle()
    {
        var fixture = CreateFixture();
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var result = await fixture.Manager.SubmitAsync(Request(source.Id), CancellationToken.None);

        Assert.True(result.Success);
        Assert.Equal(ReconstructionJobState.Queued, result.Job!.State);
        Assert.Single(fixture.Publisher.Published);
        Assert.Single(fixture.Provider.SubmitRequests);

        var status = fixture.Manager.Status(result.Job.JobId);
        Assert.True(status.Success);
        Assert.Equal(ReconstructionJobStage.Polling, status.Job!.Stage);
        Assert.Equal("req-123", status.Job.ProviderJobId);
        Assert.Equal("https://queue.fal.run/status/req-123", status.Job.ProviderStatusUrl);
        Assert.Equal("https://queue.fal.run/response/req-123", status.Job.ProviderResponseUrl);
        Assert.Equal("https://queue.fal.run/cancel/req-123", status.Job.ProviderCancelUrl);
        Assert.Equal("PUT", status.Job.ProviderCancelHttpMethod);
        Assert.False(status.ResultAvailable);
    }

    [Fact]
    public async Task Submit_ProviderFailedSubmit_RecordsTypedTerminalError()
    {
        var fixture = CreateFixture();
        fixture.Provider.SubmitOutcome = new FailedSubmitOutcome(new GenerationError(
            GenerationErrorCode.DependencyUnavailable, "fal request failed with HTTP 401.", Retryable: false));
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var result = await fixture.Manager.SubmitAsync(Request(source.Id), CancellationToken.None);

        Assert.False(result.Success);
        Assert.Equal("provider_unavailable", result.Failure!.Code);
        var status = fixture.Manager.List(10).Jobs.Single();
        Assert.Equal(ReconstructionJobState.Error, status.State);
        Assert.Equal("provider_unavailable", status.Error!.Code);
    }

    [Fact]
    public async Task Submit_Publisher_ReceivesResolvedBytesAndMime_NotAPath()
    {
        var fixture = CreateFixture();
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        await fixture.Manager.SubmitAsync(Request(source.Id), CancellationToken.None);

        var published = Assert.Single(fixture.Publisher.Published);
        Assert.Equal(new byte[] { 1, 2, 3 }, published.Bytes); // resolved blob bytes, not a path
        Assert.Equal("image/png", published.Mime);             // derived from the validated .png extension
        Assert.EndsWith(".png", published.FileName);
    }

    [Fact]
    public async Task Cancel_PollingJob_AttemptsRemoteCancelAndRecordsCancellationRequested()
    {
        var fixture = CreateFixture();
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var submit = await fixture.Manager.SubmitAsync(Request(source.Id), CancellationToken.None);

        var cancel = await fixture.Manager.CancelAsync(submit.Job!.JobId, CancellationToken.None);

        Assert.Equal(ReconstructionJobState.CancellationRequested, cancel.State);
        Assert.Equal(new[] { "req-123" }, fixture.Provider.CancelCalls);
        var status = fixture.Manager.Status(submit.Job.JobId);
        Assert.Equal(ReconstructionJobState.CancellationRequested, status.Job!.State);
    }

    [Fact]
    public async Task StatusAsync_CancellationRequestedWithNonterminalProvider_PreservesCancellationRequested()
    {
        var fixture = CreateFixture();
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var submit = await fixture.Manager.SubmitAsync(Request(source.Id), CancellationToken.None);
        await fixture.Manager.CancelAsync(submit.Job!.JobId, CancellationToken.None);

        var status = await fixture.Manager.StatusAsync(submit.Job.JobId, CancellationToken.None);

        Assert.True(status.Success);
        Assert.Equal(ReconstructionJobState.CancellationRequested, status.Job!.State);
        Assert.Equal(ReconstructionJobStage.Polling, status.Job.Stage);
    }

    [Fact]
    public async Task PollActiveJob_StatusComplete_FetchesResultAndMaterializesPackage()
    {
        var fixture = CreateFixture();
        fixture.Provider.StatusComplete.Enqueue(true);
        fixture.Provider.ResultJson = GlbResultJson;
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 9, 8, 7 };
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var submit = await fixture.Manager.SubmitAsync(Request(source.Id), CancellationToken.None);

        await fixture.Manager.PollActiveJobAsync(submit.Job!.JobId, CancellationToken.None);

        Assert.Equal(new[] { "req-123" }, fixture.Provider.ResultCalls);
        var status = fixture.Manager.Status(submit.Job.JobId);
        Assert.True(status.Success);
        Assert.Equal(ReconstructionJobState.Complete, status.Job!.State);
        Assert.Equal(ReconstructionJobStage.Complete, status.Job.Stage);
        Assert.True(status.ResultAvailable);
        Assert.NotNull(status.Job.ResultArtifactId);
        var package = fixture.Store.Get(status.Job.ResultArtifactId!.Value);
        Assert.NotNull(package);
        Assert.Equal(ReconstructionArtifactKinds.Package, package!.Kind);
    }

    [Fact]
    public async Task StatusAsync_PollingJob_PollsProviderAndMaterializesPackage()
    {
        var fixture = CreateFixture();
        fixture.Provider.StatusComplete.Enqueue(true);
        fixture.Provider.ResultJson = GlbResultJson;
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 9, 8, 7 };
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var submit = await fixture.Manager.SubmitAsync(Request(source.Id), CancellationToken.None);

        await fixture.Manager.StatusAsync(submit.Job!.JobId, CancellationToken.None);
        var status = fixture.Manager.Status(submit.Job.JobId);

        Assert.True(status.Success);
        Assert.Equal(ReconstructionJobState.Complete, status.Job!.State);
        Assert.Equal(ReconstructionJobStage.Complete, status.Job.Stage);
        Assert.True(status.ResultAvailable);
        Assert.Equal(new[] { "req-123" }, fixture.Provider.ResultCalls);
    }

    [Fact]
    public async Task StatusAsync_DownloadFailure_RecordsTypedProviderError_NotOpaquePollFailed()
    {
        var fixture = CreateFixture();
        fixture.Provider.StatusComplete.Enqueue(true);
        fixture.Provider.ResultJson = JsonNode.Parse("""
        {
          "model_urls": {
            "glb": {"url": "https://example.test/missing.glb"}
          }
        }
        """)!;
        // No downloader entry for missing.glb → the disciplined downloader returns a typed failure.
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var submit = await fixture.Manager.SubmitAsync(Request(source.Id), CancellationToken.None);

        await fixture.Manager.StatusAsync(submit.Job!.JobId, CancellationToken.None);
        var status = fixture.Manager.Status(submit.Job.JobId);

        Assert.True(status.Success);
        Assert.Equal(ReconstructionJobState.Error, status.Job!.State);
        Assert.Equal("provider_unavailable", status.Job.Error!.Code);   // typed, not opaque "poll_failed"
        Assert.True(status.Job.Error.Retryable);
    }

    [Fact]
    public async Task StatusAsync_ConcurrentCompletionPolls_MaterializesOnce()
    {
        var fixture = CreateFixture();
        fixture.Provider.FixedStatusComplete = true;
        fixture.Provider.ResultStarted = new TaskCompletionSource<bool>();
        fixture.Provider.ReleaseResult = new TaskCompletionSource<bool>();
        fixture.Provider.ResultJson = GlbResultJson;
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 9, 8, 7 };
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var submit = await fixture.Manager.SubmitAsync(Request(source.Id), CancellationToken.None);

        var first = fixture.Manager.StatusAsync(submit.Job!.JobId, CancellationToken.None);
        var entered = await Task.WhenAny(fixture.Provider.ResultStarted.Task, Task.Delay(TimeSpan.FromSeconds(5)));
        Assert.Same(fixture.Provider.ResultStarted.Task, entered);
        var second = fixture.Manager.StatusAsync(submit.Job.JobId, CancellationToken.None);

        fixture.Provider.ReleaseResult.SetResult(true);
        var statuses = await Task.WhenAll(first, second);

        Assert.All(statuses, status => Assert.Equal(ReconstructionJobState.Complete, status.Job!.State));
        Assert.Equal(1, fixture.Provider.ResultCallCount);
        Assert.Single(fixture.Provider.ResultCalls);
    }

    [Fact]
    public async Task Submit_BackgroundLoop_DrivesJobToCompleteWithoutOnDemandPoll()
    {
        var fixture = CreateFixture(pollInterval: TimeSpan.FromMilliseconds(5));
        fixture.Provider.StatusComplete.Enqueue(false);   // first poll: in-progress
        fixture.Provider.StatusComplete.Enqueue(true);    // second poll: completed
        fixture.Provider.ResultJson = GlbResultJson;
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 9, 8, 7 };
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var submit = await fixture.Manager.SubmitAsync(Request(source.Id), CancellationToken.None);

        // No StatusAsync call here — the background loop alone must drive the job to completion.
        await WaitUntil(
            () => fixture.Manager.Status(submit.Job!.JobId).Job!.State == ReconstructionJobState.Complete,
            2000);

        var status = fixture.Manager.Status(submit.Job!.JobId);
        Assert.Equal(ReconstructionJobState.Complete, status.Job!.State);
        Assert.True(status.ResultAvailable);
        Assert.Equal(new[] { "req-123" }, fixture.Provider.ResultCalls);
    }

    [Fact]
    public async Task ConcurrentStatusAndBackgroundPoll_ProduceExactlyOneMaterialization()
    {
        var fixture = CreateFixture(pollInterval: TimeSpan.FromMilliseconds(1));
        fixture.Provider.FixedStatusComplete = true;
        fixture.Provider.ResultJson = GlbResultJson;
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 9, 8, 7 };
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var submit = await fixture.Manager.SubmitAsync(Request(source.Id), CancellationToken.None);
        var jobId = submit.Job!.JobId;

        // Hammer on-demand polling concurrently with the background loop.
        await Task.WhenAll(Enumerable.Range(0, 8)
            .Select(_ => fixture.Manager.StatusAsync(jobId, CancellationToken.None)));
        await WaitUntil(
            () => fixture.Manager.Status(jobId).Job!.State == ReconstructionJobState.Complete,
            2000);

        Assert.Equal(ReconstructionJobState.Complete, fixture.Manager.Status(jobId).Job!.State);
        Assert.Equal(1, fixture.Provider.ResultCallCount);   // exactly one fetch
        Assert.Equal(1, fixture.Downloader.DownloadCount);   // exactly one materialization
    }

    [Fact]
    public async Task Dispose_CancellationAwareProvider_ReturnsPromptly_NoPostDisposeWork()
    {
        var fixture = CreateFixture(pollInterval: TimeSpan.FromMilliseconds(5));
        fixture.Provider.BlockStatusUntilCancelled = true;   // GetStatus blocks on the token forever
        fixture.Provider.ResultJson = GlbResultJson;
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 9, 8, 7 };
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var submit = await fixture.Manager.SubmitAsync(Request(source.Id), CancellationToken.None);
        var jobId = submit.Job!.JobId;
        await WaitUntil(() => fixture.Provider.StatusCallStarted, 1000);   // loop is blocked inside a poll

        var sw = Stopwatch.StartNew();
        fixture.Manager.Dispose();   // cancellation-aware loop must unblock fast and drain
        sw.Stop();

        Assert.True(sw.Elapsed < TimeSpan.FromSeconds(2), $"Dispose took {sw.Elapsed}; cancellation was not observed promptly.");
        Assert.Equal(0, fixture.Downloader.DownloadCount);   // no materialization happened
        Assert.NotEqual(ReconstructionJobState.Complete, fixture.Manager.Status(jobId).Job!.State);
        await Task.Delay(50);
        Assert.NotEqual(ReconstructionJobState.Complete, fixture.Manager.Status(jobId).Job!.State);
    }

    [Fact]
    public async Task Submit_PublisherFailure_RecordsTerminalError()
    {
        var fixture = CreateFixture();
        fixture.Publisher.ThrowOnPublish = true;
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var result = await fixture.Manager.SubmitAsync(Request(source.Id), CancellationToken.None);

        Assert.False(result.Success);
        Assert.Equal("submit_failed", result.Failure!.Code);
        var status = fixture.Manager.List(10).Jobs.Single();
        Assert.Equal(ReconstructionJobState.Error, status.State);
        Assert.Equal(ReconstructionJobStage.Error, status.Stage);
        Assert.Equal("submit_failed", status.Error!.Code);
    }

    [Fact]
    public async Task Submit_RejectsExperimentalAndPreprocessingCatalogModels()
    {
        var fixture = CreateFixture();
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var meshy = await fixture.Manager.SubmitAsync(
            Request(source.Id) with { ModelId = "fal-ai/meshy/v6/image-to-3d" },
            CancellationToken.None);
        var birefnet = await fixture.Manager.SubmitAsync(
            Request(source.Id) with { ModelId = "fal-ai/birefnet" },
            CancellationToken.None);

        Assert.False(meshy.Success);
        Assert.Equal("model_id", meshy.Failure!.Field);
        Assert.False(birefnet.Success);
        Assert.Equal("model_id", birefnet.Failure!.Field);
        Assert.Empty(fixture.Provider.SubmitRequests);
    }

    [Fact]
    public async Task ProviderQuotaFailure_SurfacesRetryableReconstructionFailure_EndToEnd()
    {
        // End-to-end through the REAL provider over a fake transport: submit 200, status 429 with the
        // fal needs-retry header. Exercises FalErrorMapper -> GenerationError(QuotaExceeded, retryable)
        // -> manager AppendError -> ReconstructionErrorMapping.ToFailure -> ReconstructionFailure.
        var root = NewTempRoot();
        var store = new ArtifactStore(Path.Combine(root, "artifacts"));
        var ledger = new JsonlReconstructionJobLedger(Path.Combine(root, "ledger.jsonl"));
        var transport = new FakeFalTransport();
        transport.Posts.Enqueue(new FalHttpResponse(
            200,
            @"{""request_id"":""req-1"",""status_url"":""https://queue.fal.run/status/req-1"",""response_url"":""https://queue.fal.run/response/req-1"",""cancel_url"":""https://queue.fal.run/cancel/req-1""}",
            EmptyHeaders()));
        transport.Gets.Enqueue(new FalHttpResponse(
            429,
            "{}",
            new Dictionary<string, IReadOnlyList<string>> { ["x-fal-needs-retry"] = new[] { "true" } }));
        var downloader = new FakeDownloader();
        var manager = new ReconstructionJobManager(
            store,
            ReconstructionModelCatalog.FromJson(CatalogJson),
            ledger,
            new FalReconstructionProvider(transport),
            new ReconstructionPackageMaterializer(store, downloader),
            new FakeSourceImagePublisher(),
            TimeSpan.FromMilliseconds(2));
        _managers.Add(manager);
        var source = store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var submit = await manager.SubmitAsync(Request(source.Id), CancellationToken.None);
        await WaitUntil(
            () => manager.Status(submit.Job!.JobId).Job!.State == ReconstructionJobState.Error,
            2000);

        var rec = manager.Status(submit.Job!.JobId).Job!;
        Assert.Equal("quota_exceeded", rec.Error!.Code);
        Assert.True(rec.Error.Retryable);
    }

    [Fact]
    public async Task ProviderTransportFailure_DuringSubmit_SurfacesProviderUnavailable_NotSubmitFailed()
    {
        // Real provider over a transport whose submit POST throws a raw HttpRequestException (the fault
        // FalApiClient's JSON path does not wrap). The convergence goal is that this is a typed
        // provider_unavailable, never the opaque submit_failed catch-all.
        var root = NewTempRoot();
        var store = new ArtifactStore(Path.Combine(root, "artifacts"));
        var ledger = new JsonlReconstructionJobLedger(Path.Combine(root, "ledger.jsonl"));
        var transport = new FakeFalTransport { PostException = new HttpRequestException("connection reset") };
        var manager = new ReconstructionJobManager(
            store,
            ReconstructionModelCatalog.FromJson(CatalogJson),
            ledger,
            new FalReconstructionProvider(transport),
            new ReconstructionPackageMaterializer(store, new FakeDownloader()),
            new FakeSourceImagePublisher(),
            TimeSpan.FromMilliseconds(2));
        _managers.Add(manager);
        var source = store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var submit = await manager.SubmitAsync(Request(source.Id), CancellationToken.None);

        Assert.False(submit.Success);
        Assert.Equal("provider_unavailable", submit.Failure!.Code);
        Assert.True(submit.Failure.Retryable);
        var terminal = manager.List(10).Jobs.Single();
        Assert.Equal(ReconstructionJobState.Error, terminal.State);
        Assert.Equal("provider_unavailable", terminal.Error!.Code);
    }

    [Fact]
    public async Task ProviderTransportFailure_DuringStatusPoll_SurfacesProviderUnavailable_NotPollFailed()
    {
        // Submit succeeds (200), but the status GET throws a raw transport fault during polling. Before
        // the convergence this fell through to the manager's opaque poll_failed; it must now be typed.
        var root = NewTempRoot();
        var store = new ArtifactStore(Path.Combine(root, "artifacts"));
        var ledger = new JsonlReconstructionJobLedger(Path.Combine(root, "ledger.jsonl"));
        var transport = new FakeFalTransport { GetException = new HttpRequestException("connection reset") };
        transport.Posts.Enqueue(new FalHttpResponse(
            200,
            @"{""request_id"":""req-1"",""status_url"":""https://queue.fal.run/status/req-1"",""response_url"":""https://queue.fal.run/response/req-1"",""cancel_url"":""https://queue.fal.run/cancel/req-1""}",
            EmptyHeaders()));
        var manager = new ReconstructionJobManager(
            store,
            ReconstructionModelCatalog.FromJson(CatalogJson),
            ledger,
            new FalReconstructionProvider(transport),
            new ReconstructionPackageMaterializer(store, new FakeDownloader()),
            new FakeSourceImagePublisher(),
            TimeSpan.FromMilliseconds(2));
        _managers.Add(manager);
        var source = store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var submit = await manager.SubmitAsync(Request(source.Id), CancellationToken.None);
        await WaitUntil(
            () => manager.Status(submit.Job!.JobId).Job!.State == ReconstructionJobState.Error,
            2000);

        var rec = manager.Status(submit.Job!.JobId).Job!;
        Assert.Equal("provider_unavailable", rec.Error!.Code);   // typed, not opaque "poll_failed"
        Assert.True(rec.Error.Retryable);
    }

    [Fact]
    public async Task Submit_MissingApiKey_RecordsMissingCredential_NotSubmitFailed()
    {
        // Real source publisher + a secret store with no fal key → PublishAsync throws the typed
        // credential exception at the fal edge, which the submit boundary maps to missing_credential.
        var root = NewTempRoot();
        var store = new ArtifactStore(Path.Combine(root, "artifacts"));
        var ledger = new JsonlReconstructionJobLedger(Path.Combine(root, "ledger.jsonl"));
        var manager = new ReconstructionJobManager(
            store,
            ReconstructionModelCatalog.FromJson(CatalogJson),
            ledger,
            new FakeReconstructionProvider(),
            new ReconstructionPackageMaterializer(store, new FakeDownloader()),
            new FalReconstructionSourceImagePublisher(new FalApiClient(), new NullSecretStore()));
        _managers.Add(manager);
        var source = store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var result = await manager.SubmitAsync(Request(source.Id), CancellationToken.None);

        Assert.False(result.Success);
        Assert.Equal("missing_credential", result.Failure!.Code);
        Assert.False(result.Failure.Retryable);
        var terminal = manager.List(10).Jobs.Single();
        Assert.Equal(ReconstructionJobState.Error, terminal.State);
        Assert.Equal("missing_credential", terminal.Error!.Code);
    }

    [Fact]
    public async Task Submit_FalUploadFailure_RecordsProviderUnavailable_NotSubmitFailed()
    {
        // The source-image CDN upload failing (FalApiException) is a provider dependency failure, not a
        // local source-read/IO fault — it must be distinguished from the generic submit_failed path.
        var fixture = CreateFixture();
        fixture.Publisher.ThrowFalApiException = true;
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var result = await fixture.Manager.SubmitAsync(Request(source.Id), CancellationToken.None);

        Assert.False(result.Success);
        Assert.Equal("provider_unavailable", result.Failure!.Code);
        Assert.True(result.Failure.Retryable);
        var status = fixture.Manager.List(10).Jobs.Single();
        Assert.Equal(ReconstructionJobState.Error, status.State);
        Assert.Equal("provider_unavailable", status.Error!.Code);
    }

    [Fact]
    public async Task Cancel_MissingApiKey_ReturnsCancellationRequestedWithMissingCredential_NoThrow()
    {
        // Real provider over a transport with no key. Seed a polling job, then cancel → remote cancel
        // hits Key() → typed missing_credential returned (not an unhandled throw). CancellationRequested
        // is still recorded first.
        var root = NewTempRoot();
        var store = new ArtifactStore(Path.Combine(root, "artifacts"));
        var ledger = new JsonlReconstructionJobLedger(Path.Combine(root, "ledger.jsonl"));
        var manager = new ReconstructionJobManager(
            store,
            ReconstructionModelCatalog.FromJson(CatalogJson),
            ledger,
            new FalReconstructionProvider(new FalApiTransport(new FalApiClient(), () => null)),
            new ReconstructionPackageMaterializer(store, new FakeDownloader()),
            new FakeSourceImagePublisher());
        _managers.Add(manager);

        var jobId = Guid.NewGuid();
        ledger.Append(ReconstructionJobLedgerRecord.Queued(jobId, HunyuanModelId, Guid.NewGuid(), "image") with
        {
            State = ReconstructionJobState.Running,
            Stage = ReconstructionJobStage.Polling,
            ProviderJobId = "req-1",
            ProviderStatusUrl = "https://queue.fal.run/status/req-1",
            ProviderResponseUrl = "https://queue.fal.run/response/req-1",
            ProviderCancelUrl = "https://queue.fal.run/cancel/req-1",
            ProviderCancelHttpMethod = "PUT",
        });

        var cancel = await manager.CancelAsync(jobId, CancellationToken.None);

        Assert.Equal(ReconstructionJobState.CancellationRequested, cancel.State);
        Assert.Equal("missing_credential", cancel.Failure!.Code);
        Assert.False(cancel.Failure.Retryable);
    }

    [Fact]
    public async Task Poll_MissingApiKey_RecordsMissingCredential_NotPollFailed()
    {
        // Real provider over a transport with no key. Seed a polling job directly (submit would itself
        // fail on the missing key), then poll → GetStatus → Key() throws → typed missing_credential.
        var root = NewTempRoot();
        var store = new ArtifactStore(Path.Combine(root, "artifacts"));
        var ledger = new JsonlReconstructionJobLedger(Path.Combine(root, "ledger.jsonl"));
        var manager = new ReconstructionJobManager(
            store,
            ReconstructionModelCatalog.FromJson(CatalogJson),
            ledger,
            new FalReconstructionProvider(new FalApiTransport(new FalApiClient(), () => null)),
            new ReconstructionPackageMaterializer(store, new FakeDownloader()),
            new FakeSourceImagePublisher());
        _managers.Add(manager);

        var jobId = Guid.NewGuid();
        ledger.Append(ReconstructionJobLedgerRecord.Queued(jobId, HunyuanModelId, Guid.NewGuid(), "image") with
        {
            State = ReconstructionJobState.Running,
            Stage = ReconstructionJobStage.Polling,
            ProviderJobId = "req-1",
            ProviderStatusUrl = "https://queue.fal.run/status/req-1",
            ProviderResponseUrl = "https://queue.fal.run/response/req-1",
            ProviderCancelUrl = "https://queue.fal.run/cancel/req-1",
            ProviderCancelHttpMethod = "PUT",
        });

        await manager.PollActiveJobAsync(jobId, CancellationToken.None);

        var rec = manager.Status(jobId).Job!;
        Assert.Equal(ReconstructionJobState.Error, rec.State);
        Assert.Equal("missing_credential", rec.Error!.Code);   // typed, not opaque "poll_failed"
        Assert.False(rec.Error.Retryable);
    }

    [Fact]
    public void ReconcileInterruptedJobs_NonTerminalBecomeInterrupted_PreserveProviderFields_TerminalUntouched()
    {
        var fixture = CreateFixture();

        var runningId = Guid.NewGuid();
        fixture.Ledger.Append(
            ReconstructionJobLedgerRecord.Queued(runningId, HunyuanModelId, Guid.NewGuid(), "image") with
            {
                State = ReconstructionJobState.Running,
                Stage = ReconstructionJobStage.Polling,
                ProviderJobId = "req-9",
                ProviderStatusUrl = "https://queue.fal.run/status/req-9",
                ProviderResponseUrl = "https://queue.fal.run/response/req-9",
                ProviderCancelUrl = "https://queue.fal.run/cancel/req-9",
                ProviderCancelHttpMethod = "PUT",
            });

        var completeId = Guid.NewGuid();
        fixture.Ledger.Append(ReconstructionJobLedgerRecord.Complete(completeId, Guid.NewGuid()));

        fixture.Manager.ReconcileInterruptedJobs();

        var running = fixture.Manager.Status(runningId).Job!;
        Assert.Equal(ReconstructionJobState.Interrupted, running.State);
        Assert.Equal("req-9", running.ProviderJobId);                                  // provider id preserved
        Assert.Equal("https://queue.fal.run/status/req-9", running.ProviderStatusUrl);
        Assert.Equal("https://queue.fal.run/response/req-9", running.ProviderResponseUrl);
        Assert.Equal("https://queue.fal.run/cancel/req-9", running.ProviderCancelUrl);
        Assert.Equal("PUT", running.ProviderCancelHttpMethod);
        Assert.Equal("interrupted", running.Error!.Code);
        Assert.True(running.Error.Retryable);

        var complete = fixture.Manager.Status(completeId).Job!;
        Assert.Equal(ReconstructionJobState.Complete, complete.State);                 // terminal left untouched
    }

    [Fact]
    public void Result_CompleteJobWithDeletedPackage_ReturnsMissingArtifactWarning()
    {
        var fixture = CreateFixture();
        var jobId = Guid.NewGuid();
        fixture.Ledger.Append(ReconstructionJobLedgerRecord.Complete(jobId, Guid.NewGuid()));

        var result = fixture.Manager.Result(jobId);

        Assert.True(result.Success);
        Assert.False(result.ResultAvailable);
        Assert.Contains(result.Warnings, w => w.Code == "result_artifact_missing");
    }

    [Fact]
    public async Task Submit_PbrAndGeometryBothTrue_RejectedBeforeSourceLookup_ProviderAndPublisherNotInvoked()
    {
        var fixture = CreateFixture();
        // Deliberately do NOT create the source artifact. The guard runs before source lookup, so a
        // contradictory request must fail with field "options" (not "source_artifact_id"). That field
        // value is the proof the guard precedes the source check.
        var request = Request(Guid.NewGuid()) with
        {
            Options = JsonNode.Parse(@"{""enable_pbr"":true,""enable_geometry"":true}")!.AsObject(),
        };

        var result = await fixture.Manager.SubmitAsync(request, CancellationToken.None);

        Assert.False(result.Success);
        Assert.Equal("invalid_request", result.Failure!.Code);
        Assert.Equal("options", result.Failure.Field);
        Assert.False(result.Failure.Retryable);
        Assert.Equal(
            "enable_geometry=true requests geometry-only output and cannot be combined with "
            + "enable_pbr=true. Remove enable_geometry to request textured output, or remove "
            + "enable_pbr to request geometry-only output.",
            result.Failure.Message);
        Assert.Empty(fixture.Provider.SubmitRequests);   // no fal job spent
        Assert.Empty(fixture.Publisher.Published);         // no source-image upload
        Assert.Empty(fixture.Manager.List(10).Jobs);       // no ledger record for an invalid request
    }

    [Fact]
    public async Task Submit_EnablePbrTrueOnly_PassesGuard_ReachesProvider()
    {
        var fixture = CreateFixture();
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var request = Request(source.Id) with
        {
            Options = JsonNode.Parse(@"{""enable_pbr"":true}")!.AsObject(),
        };

        var result = await fixture.Manager.SubmitAsync(request, CancellationToken.None);

        Assert.True(result.Success);
        Assert.Single(fixture.Provider.SubmitRequests);    // next fake boundary reached
    }

    [Fact]
    public async Task Submit_EnableGeometryTrueOnly_PassesGuard_ReachesProvider()
    {
        var fixture = CreateFixture();
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var request = Request(source.Id) with
        {
            Options = JsonNode.Parse(@"{""enable_pbr"":false,""enable_geometry"":true}")!.AsObject(),
        };

        var result = await fixture.Manager.SubmitAsync(request, CancellationToken.None);

        Assert.True(result.Success);
        Assert.Single(fixture.Provider.SubmitRequests);
    }

    [Fact]
    public async Task Submit_StringTrueOptions_DoNotTriggerGuard_ReachesProvider()
    {
        var fixture = CreateFixture();
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        // Strings, not JSON booleans — must NOT be coerced into the guard.
        var request = Request(source.Id) with
        {
            Options = JsonNode.Parse(@"{""enable_pbr"":""true"",""enable_geometry"":""true""}")!.AsObject(),
        };

        var result = await fixture.Manager.SubmitAsync(request, CancellationToken.None);

        Assert.True(result.Success);
        Assert.Single(fixture.Provider.SubmitRequests);
    }

    [Fact]
    public async Task Submit_NumericOneOptions_DoNotTriggerGuard_ReachesProvider()
    {
        var fixture = CreateFixture();
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        // Numbers, not JSON booleans — must NOT be coerced into the guard.
        var request = Request(source.Id) with
        {
            Options = JsonNode.Parse(@"{""enable_pbr"":1,""enable_geometry"":1}")!.AsObject(),
        };

        var result = await fixture.Manager.SubmitAsync(request, CancellationToken.None);

        Assert.True(result.Success);
        Assert.Single(fixture.Provider.SubmitRequests);
    }

    [Fact]
    public async Task Submit_EmptyOptions_DoNotTriggerGuard_ReachesProvider()
    {
        var fixture = CreateFixture();
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var request = Request(source.Id) with
        {
            Options = new JsonObject(),
        };

        var result = await fixture.Manager.SubmitAsync(request, CancellationToken.None);

        Assert.True(result.Success);
        Assert.Single(fixture.Provider.SubmitRequests);
    }

    private static ReconstructionModelEntry ModelEntry(bool defaultTextureExpected, bool supportsPbr = true)
    {
        var json = $$"""
        {"schema_version":1,"models":[{
          "model_id":"fal-ai/test","provider":"fal","task":"single_image_to_3d","status":"stable","enabled":true,
          "pipeline_roles":["single_image_to_3d"],"input_types":["image_url"],"output_roles":["model_glb"],
          "preferred_asset_role":"model_glb","fallback_order":["model_glb"],"supports_pbr":{{(supportsPbr ? "true" : "false")}},
          "default_texture_expected":{{(defaultTextureExpected ? "true" : "false")}},
          "preprocessing":{"recommended":false,"required":false},"docs_url":"x"}]}
        """;
        return ReconstructionModelCatalog.FromJson(json).Find("fal-ai/test")!;
    }

    private static JsonObject Opts(string json) => JsonNode.Parse(json)!.AsObject();

    [Fact]
    public void DeriveTextureExpected_GeometryTrue_IsFalse()
        => Assert.False(ReconstructionJobManager.DeriveTextureExpected(Opts(@"{""enable_geometry"":true}"), ModelEntry(true)));

    [Fact]
    public void DeriveTextureExpected_PbrTrue_IsTrue()
        => Assert.True(ReconstructionJobManager.DeriveTextureExpected(Opts(@"{""enable_pbr"":true}"), ModelEntry(false)));

    [Fact]
    public void DeriveTextureExpected_PbrFalse_IsFalse()
        => Assert.False(ReconstructionJobManager.DeriveTextureExpected(Opts(@"{""enable_pbr"":false}"), ModelEntry(true)));

    [Fact]
    public void DeriveTextureExpected_Omitted_UsesCatalogDefaultTrue()
        => Assert.True(ReconstructionJobManager.DeriveTextureExpected(Opts("{}"), ModelEntry(true)));

    [Fact]
    public void DeriveTextureExpected_Omitted_UsesCatalogDefaultFalse()
        => Assert.False(ReconstructionJobManager.DeriveTextureExpected(Opts("{}"), ModelEntry(false)));

    [Fact]
    public void DeriveTextureExpected_NonBool_TreatedAsOmitted_UsesCatalogDefault()
        => Assert.True(ReconstructionJobManager.DeriveTextureExpected(Opts(@"{""enable_pbr"":""true""}"), ModelEntry(true)));

    [Fact]
    public async Task Submit_OmittedOptions_PersistsTextureExpectedFromCatalogDefault()
    {
        var fixture = CreateFixture();
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var request = Request(source.Id) with { Options = new JsonObject() };   // omitted → Hunyuan default true

        var submit = await fixture.Manager.SubmitAsync(request, CancellationToken.None);

        Assert.True(submit.Success);
        Assert.True(fixture.Manager.Status(submit.Job!.JobId).Job!.TextureExpected);
    }

    private static string[] WarningCodes(IReadOnlyList<ReconstructionWarning> ws)
    {
        var codes = new List<string>();
        foreach (var w in ws) codes.Add(w.Code);
        return codes.ToArray();
    }

    [Fact]
    public void BuildTextureWarnings_NotExpected_NoWarning()
        => Assert.Empty(ReconstructionJobManager.BuildTextureWarnings(false, ModelEntry(true, supportsPbr: true), new[] { "model_glb" }));

    [Fact]
    public void BuildTextureWarnings_NullModel_NoWarning()
        => Assert.Empty(ReconstructionJobManager.BuildTextureWarnings(true, null, new[] { "model_glb" }));

    [Fact]
    public void BuildTextureWarnings_Expected_NoPbrSupport_EmitsPbrUnsupported()
    {
        var ws = ReconstructionJobManager.BuildTextureWarnings(true, ModelEntry(true, supportsPbr: false), new[] { "model_glb" });
        Assert.Equal(new[] { "pbr_unsupported_by_model" }, WarningCodes(ws));
    }

    [Fact]
    public void BuildTextureWarnings_Expected_PbrSupported_BareRoles_EmitsMissingTexture()
    {
        var ws = ReconstructionJobManager.BuildTextureWarnings(true, ModelEntry(true, supportsPbr: true), new[] { "model_glb", "model_obj" });
        Assert.Equal(new[] { "result_missing_texture" }, WarningCodes(ws));
    }

    [Fact]
    public void BuildTextureWarnings_Expected_PbrSupported_TexturePresent_NoWarning()
        => Assert.Empty(ReconstructionJobManager.BuildTextureWarnings(true, ModelEntry(true, supportsPbr: true), new[] { "model_glb", "texture_base_color" }));

    [Fact]
    public void BuildTextureWarnings_Expected_PbrSupported_MaterialOnly_NoWarning()
        => Assert.Empty(ReconstructionJobManager.BuildTextureWarnings(true, ModelEntry(true, supportsPbr: true), new[] { "model_obj", "material_mtl" }));

    [Fact]
    public async Task Result_TextureExpected_BarePackage_EmitsMissingTexture()
    {
        var fixture = CreateFixture();
        fixture.Provider.StatusComplete.Enqueue(true);
        fixture.Provider.ResultJson = GlbResultJson;                 // model_glb only → no texture/material
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 9, 8, 7 };
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var submit = await fixture.Manager.SubmitAsync(Request(source.Id), CancellationToken.None);   // enable_pbr:true → expected
        await fixture.Manager.PollActiveJobAsync(submit.Job!.JobId, CancellationToken.None);

        var result = fixture.Manager.Result(submit.Job.JobId);

        Assert.True(result.Success);
        Assert.Contains(result.Warnings, w => w.Code == "result_missing_texture");
    }

    [Fact]
    public void Result_MissingPackage_EmitsArtifactMissingOnly_NoTextureWarning()
    {
        var fixture = CreateFixture();
        var jobId = Guid.NewGuid();
        // Complete job pointing at a non-existent package, with TextureExpected true.
        fixture.Ledger.Append(ReconstructionJobLedgerRecord.Complete(jobId, Guid.NewGuid()) with { TextureExpected = true });

        var result = fixture.Manager.Result(jobId);

        Assert.Contains(result.Warnings, w => w.Code == "result_artifact_missing");
        Assert.DoesNotContain(result.Warnings, w => w.Code == "result_missing_texture");
        Assert.DoesNotContain(result.Warnings, w => w.Code == "pbr_unsupported_by_model");
    }

    private static readonly JsonNode GlbResultJson = JsonNode.Parse("""
    {
      "model_urls": {
        "glb": {"url": "https://example.test/model.glb"}
      }
    }
    """)!;

    private Fixture CreateFixture(TimeSpan? pollInterval = null)
    {
        var root = NewTempRoot();
        var store = new ArtifactStore(Path.Combine(root, "artifacts"));
        var ledger = new JsonlReconstructionJobLedger(Path.Combine(root, "ledger.jsonl"));
        var provider = new FakeReconstructionProvider();
        var downloader = new FakeDownloader();
        var publisher = new FakeSourceImagePublisher();
        var materializer = new ReconstructionPackageMaterializer(store, downloader);
        var manager = new ReconstructionJobManager(
            store,
            ReconstructionModelCatalog.FromJson(CatalogJson),
            ledger,
            provider,
            materializer,
            publisher,
            pollInterval);
        _managers.Add(manager);
        return new Fixture(store, ledger, provider, downloader, publisher, manager);
    }

    private static async Task WaitUntil(Func<bool> condition, int timeoutMs)
    {
        var sw = Stopwatch.StartNew();
        while (sw.ElapsedMilliseconds < timeoutMs)
        {
            if (condition()) return;
            await Task.Delay(10);
        }

        Assert.True(condition(), "Condition was not satisfied within the timeout.");
    }

    private string NewTempRoot()
    {
        var root = Path.Combine(Path.GetTempPath(), $"rook-reconstruction-manager-{Guid.NewGuid():N}");
        _roots.Add(root);
        return root;
    }

    private static ReconstructionSubmitRequest Request(Guid sourceId)
        => new(
            SourceArtifactId: sourceId,
            SourceRole: "image",
            ModelId: HunyuanModelId,
            PreprocessingChain: Array.Empty<ReconstructionPreprocessingStageRequest>(),
            Options: JsonNode.Parse(@"{""enable_pbr"":true,""enable_geometry"":false}")!.AsObject(),
            EstimateRequested: false);

    private sealed record Fixture(
        ArtifactStore Store,
        JsonlReconstructionJobLedger Ledger,
        FakeReconstructionProvider Provider,
        FakeDownloader Downloader,
        FakeSourceImagePublisher Publisher,
        ReconstructionJobManager Manager);

    private sealed class FakeReconstructionProvider : IReconstructionProvider
    {
        private int _resultCallCount;

        public List<ReconstructionProviderSubmitRequest> SubmitRequests { get; } = new();
        public Queue<bool> StatusComplete { get; } = new();   // true → ProviderComplete, else InFlight
        public bool FixedStatusComplete { get; set; }
        public List<string> CancelCalls { get; } = new();
        public List<string> ResultCalls { get; } = new();
        public int ResultCallCount => _resultCallCount;
        public ProviderSubmitOutcome? SubmitOutcome { get; set; }
        public TaskCompletionSource<bool>? ResultStarted { get; set; }
        public TaskCompletionSource<bool>? ReleaseResult { get; set; }
        // Block GetStatus on the cancellation token (never completes on its own); used to prove the
        // background loop observes shutdown cancellation promptly.
        public bool BlockStatusUntilCancelled { get; set; }
        public volatile bool StatusCallStarted;
        public JsonNode ResultJson { get; set; } =
            JsonNode.Parse(@"{""model_urls"":{""glb"":{""url"":""https://example.test/model.glb""}}}")!;

        public Task<ProviderSubmitOutcome> SubmitAsync(
            ReconstructionProviderSubmitRequest request,
            CancellationToken cancellationToken)
        {
            SubmitRequests.Add(request);
            return Task.FromResult(SubmitOutcome ?? new QueuedSubmitOutcome(new ProviderJobHandle(
                "req-123",
                statusUrl: new Uri("https://queue.fal.run/status/req-123"),
                responseUrl: new Uri("https://queue.fal.run/response/req-123"),
                cancelUrl: new Uri("https://queue.fal.run/cancel/req-123"),
                cancelHttpMethod: "PUT")));
        }

        public async Task<ProviderStatusOutcome> GetStatusAsync(
            ProviderJobHandle handle,
            CancellationToken cancellationToken)
        {
            if (BlockStatusUntilCancelled)
            {
                StatusCallStarted = true;
                await Task.Delay(Timeout.Infinite, cancellationToken).ConfigureAwait(false);
            }

            var complete = FixedStatusComplete || (StatusComplete.Count > 0 && StatusComplete.Dequeue());
            return complete
                ? new ProviderCompleteStatusOutcome(handle)
                : new InFlightStatusOutcome(GenerationLifecycleState.Running, null);
        }

        public async Task<ProviderResultOutcome> FetchResultAsync(
            ProviderJobHandle handle,
            CancellationToken cancellationToken)
        {
            Interlocked.Increment(ref _resultCallCount);
            lock (ResultCalls)
            {
                ResultCalls.Add(handle.ProviderJobId);
            }

            ResultStarted?.TrySetResult(true);
            if (ReleaseResult is not null)
                await ReleaseResult.Task.ConfigureAwait(false);
            return new SuccessResultOutcome(FalReconstructionResultMapper.ToEnvelope(ResultJson));
        }

        public Task<ProviderCancelOutcome> CancelAsync(
            ProviderJobHandle handle,
            CancellationToken cancellationToken)
        {
            CancelCalls.Add(handle.ProviderJobId);
            return Task.FromResult<ProviderCancelOutcome>(new CanceledOutcome());
        }
    }

    private sealed class FakeDownloader : IReconstructionRemoteAssetDownloader
    {
        private int _downloadCount;

        public Dictionary<string, byte[]> Files { get; } = new();
        public int DownloadCount => _downloadCount;

        public Task<ReconstructionDownloadResult> DownloadAsync(Uri url, string role, CancellationToken ct)
        {
            Interlocked.Increment(ref _downloadCount);
            if (Files.TryGetValue(url.ToString(), out var bytes))
                return Task.FromResult(new ReconstructionDownloadResult(true, bytes, "application/octet-stream", null));
            return Task.FromResult(new ReconstructionDownloadResult(
                false,
                null,
                null,
                new GenerationError(GenerationErrorCode.DependencyUnavailable, $"missing {url}", Retryable: true)));
        }
    }

    private static Dictionary<string, IReadOnlyList<string>> EmptyHeaders()
        => new();

    // Minimal IFalTransport so the real FalReconstructionProvider can be exercised end-to-end against
    // scripted HTTP responses (used by the GenerationError -> ReconstructionFailure boundary test).
    private sealed class FakeFalTransport : IFalTransport
    {
        public Queue<FalHttpResponse> Posts { get; } = new();
        public Queue<FalHttpResponse> Gets { get; } = new();
        public Queue<FalHttpResponse> Sends { get; } = new();
        // When set, the call throws a raw transport fault (socket/timeout) — the kind FalApiClient's
        // JSON path does not wrap, exercising the provider's typed-failure conversion end-to-end.
        public Exception? PostException { get; set; }
        public Exception? GetException { get; set; }
        public Exception? SendException { get; set; }

        public Task<FalHttpResponse> PostJsonAsync(Uri url, string bodyJson, CancellationToken ct)
            => PostException is not null ? throw PostException : Task.FromResult(Posts.Dequeue());

        public Task<FalHttpResponse> GetAsync(Uri url, CancellationToken ct)
            => GetException is not null ? throw GetException : Task.FromResult(Gets.Dequeue());

        public Task<FalHttpResponse> SendAsync(HttpMethod method, Uri url, string? bodyJson, CancellationToken ct)
            => SendException is not null ? throw SendException : Task.FromResult(Sends.Dequeue());
    }

    private sealed class NullSecretStore : IGenerationSecretStore
    {
        public string? GetSecret(string secretKey) => null;
        public void SetSecret(string secretKey, string value) { }
        public void RemoveSecret(string secretKey) { }
        public bool HasSecret(string secretKey) => false;
        public string? GetPreview(string secretKey) => null;
    }

    private sealed class FakeSourceImagePublisher : IReconstructionSourceImagePublisher
    {
        public List<(byte[] Bytes, string Mime, string FileName)> Published { get; } = new();
        public bool ThrowOnPublish { get; set; }
        // Models a fal CDN upload fault (transport/non-2xx), which FalApiClient surfaces as
        // FalApiException — distinct from a local source-read/IO fault.
        public bool ThrowFalApiException { get; set; }

        public Task<Uri> PublishAsync(
            byte[] bytes,
            string mimeType,
            string fileName,
            CancellationToken ct)
        {
            if (ThrowFalApiException)
                throw new FalApiException("fal CDN upload failed");
            if (ThrowOnPublish)
                throw new InvalidOperationException("publisher failed");

            Published.Add((bytes, mimeType, fileName));
            return Task.FromResult(new Uri("https://rook.local/source.png"));
        }
    }

    private const string CatalogJson = """
    {
      "schema_version": 1,
      "models": [
        {
          "model_id": "fal-ai/meshy/v6/image-to-3d",
          "provider": "fal",
          "task": "single_image_to_3d",
          "status": "experimental",
          "enabled": true,
          "pipeline_roles": ["single_image_to_3d"],
          "input_types": ["image_url"],
          "output_roles": ["model_glb"],
          "preferred_asset_role": "model_glb",
          "fallback_order": ["model_glb"],
          "supports_pbr": true,
          "preprocessing": {"recommended": false, "required": false},
          "docs_url": "https://fal.ai/models/fal-ai/meshy/v6/image-to-3d/api"
        },
        {
          "model_id": "fal-ai/birefnet",
          "provider": "fal",
          "task": "background_removal",
          "status": "experimental",
          "enabled": true,
          "pipeline_roles": ["preprocessing"],
          "input_types": ["image_url"],
          "output_roles": ["preprocessed_image"],
          "preferred_asset_role": "preprocessed_image",
          "fallback_order": ["preprocessed_image"],
          "supports_pbr": false,
          "preprocessing": {"recommended": false, "required": false},
          "docs_url": "https://fal.ai/models/fal-ai/birefnet/api"
        },
        {
          "model_id": "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
          "provider": "fal",
          "task": "single_image_to_3d",
          "status": "stable",
          "enabled": true,
          "pipeline_roles": ["single_image_to_3d"],
          "input_types": ["image_url"],
          "output_roles": ["model_glb", "model_obj", "material_mtl", "texture", "thumbnail"],
          "preferred_asset_role": "model_glb",
          "fallback_order": ["model_glb", "model_obj"],
          "supports_pbr": true,
          "default_texture_expected": true,
          "preprocessing": {"recommended": false, "required": false},
          "docs_url": "https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d/api"
        }
      ]
    }
    """;
}
