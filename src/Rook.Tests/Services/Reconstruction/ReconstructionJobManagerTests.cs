using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Reconstruction;
using Rook.Services.Reconstruction.Fal;
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

    private sealed class FakeSourceImagePublisher : IReconstructionSourceImagePublisher
    {
        public List<(byte[] Bytes, string Mime, string FileName)> Published { get; } = new();
        public bool ThrowOnPublish { get; set; }

        public Task<Uri> PublishAsync(
            byte[] bytes,
            string mimeType,
            string fileName,
            CancellationToken ct)
        {
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
          "preprocessing": {"recommended": false, "required": false},
          "docs_url": "https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d/api"
        }
      ]
    }
    """;
}
