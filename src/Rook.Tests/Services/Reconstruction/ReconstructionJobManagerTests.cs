using System;
using System.Collections.Generic;
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

    public void Dispose()
    {
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
        Assert.Single(fixture.Publisher.PublishedPaths);
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
    public async Task PollActiveJob_StatusComplete_GetsResultAndMaterializesPackage()
    {
        var fixture = CreateFixture();
        fixture.Provider.StatusResults.Enqueue(new ReconstructionProviderStatusResult(
            "req-123",
            ReconstructionProviderLifecycleState.Complete,
            IsTerminal: true,
            IsSuccess: true,
            ProviderStatusJson: JsonNode.Parse(@"{""status"":""COMPLETED"",""request_id"":""req-123""}")!,
            Error: null));
        fixture.Provider.ResultJson = JsonNode.Parse("""
        {
          "model_urls": {
            "glb": {"url": "https://example.test/model.glb"}
          }
        }
        """)!;
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
        fixture.Provider.StatusResults.Enqueue(new ReconstructionProviderStatusResult(
            "req-123",
            ReconstructionProviderLifecycleState.Complete,
            IsTerminal: true,
            IsSuccess: true,
            ProviderStatusJson: JsonNode.Parse(@"{""status"":""COMPLETED"",""request_id"":""req-123""}")!,
            Error: null));
        fixture.Provider.ResultJson = JsonNode.Parse("""
        {
          "model_urls": {
            "glb": {"url": "https://example.test/model.glb"}
          }
        }
        """)!;
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
    public async Task StatusAsync_MaterializationFailure_RecordsExceptionMessage()
    {
        var fixture = CreateFixture();
        fixture.Provider.StatusResults.Enqueue(new ReconstructionProviderStatusResult(
            "req-123",
            ReconstructionProviderLifecycleState.Complete,
            IsTerminal: true,
            IsSuccess: true,
            ProviderStatusJson: JsonNode.Parse(@"{""status"":""COMPLETED"",""request_id"":""req-123""}")!,
            Error: null));
        fixture.Provider.ResultJson = JsonNode.Parse("""
        {
          "model_urls": {
            "glb": {"url": "https://example.test/missing.glb"}
          }
        }
        """)!;
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var submit = await fixture.Manager.SubmitAsync(Request(source.Id), CancellationToken.None);

        await fixture.Manager.StatusAsync(submit.Job!.JobId, CancellationToken.None);
        var status = fixture.Manager.Status(submit.Job.JobId);

        Assert.True(status.Success);
        Assert.Equal(ReconstructionJobState.Error, status.Job!.State);
        Assert.Equal("poll_failed", status.Job.Error!.Code);
        Assert.Equal("InvalidOperationException", status.Job.Error.Details["exception_type"]);
        Assert.Contains(
            "Unexpected download URI 'https://example.test/missing.glb'",
            Assert.IsType<string>(status.Job.Error.Details["exception_message"]));
    }

    [Fact]
    public async Task StatusAsync_ConcurrentCompletionPolls_MaterializesOnce()
    {
        var fixture = CreateFixture();
        fixture.Provider.FixedStatusResult = new ReconstructionProviderStatusResult(
            "req-123",
            ReconstructionProviderLifecycleState.Complete,
            IsTerminal: true,
            IsSuccess: true,
            ProviderStatusJson: JsonNode.Parse(@"{""status"":""COMPLETED"",""request_id"":""req-123""}")!,
            Error: null);
        fixture.Provider.ResultStarted = new TaskCompletionSource<bool>();
        fixture.Provider.ReleaseResult = new TaskCompletionSource<bool>();
        fixture.Provider.ResultJson = JsonNode.Parse("""
        {
          "model_urls": {
            "glb": {"url": "https://example.test/model.glb"}
          }
        }
        """)!;
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

    private Fixture CreateFixture()
    {
        var root = NewTempRoot();
        var store = new ArtifactStore(Path.Combine(root, "artifacts"));
        var ledger = new JsonlReconstructionJobLedger(Path.Combine(root, "ledger.jsonl"));
        var provider = new FakeReconstructionProvider();
        var downloader = new FakeFileDownloader();
        var publisher = new FakeSourceImagePublisher();
        var materializer = new ReconstructionPackageMaterializer(store, downloader);
        var manager = new ReconstructionJobManager(
            store,
            ReconstructionModelCatalog.FromJson(CatalogJson),
            ledger,
            provider,
            materializer,
            publisher);
        return new Fixture(store, ledger, provider, downloader, publisher, manager);
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
        FakeFileDownloader Downloader,
        FakeSourceImagePublisher Publisher,
        ReconstructionJobManager Manager);

    private sealed class FakeReconstructionProvider : IReconstructionProvider
    {
        private int _resultCallCount;

        public List<ReconstructionProviderSubmitRequest> SubmitRequests { get; } = new();
        public Queue<ReconstructionProviderStatusResult> StatusResults { get; } = new();
        public List<string> CancelCalls { get; } = new();
        public List<string> ResultCalls { get; } = new();
        public int ResultCallCount => _resultCallCount;
        public ReconstructionProviderStatusResult? FixedStatusResult { get; set; }
        public TaskCompletionSource<bool>? ResultStarted { get; set; }
        public TaskCompletionSource<bool>? ReleaseResult { get; set; }
        public JsonNode ResultJson { get; set; } = JsonNode.Parse("{}")!;

        public Task<ReconstructionProviderSubmitResult> SubmitAsync(
            ReconstructionProviderSubmitRequest request,
            CancellationToken cancellationToken)
        {
            SubmitRequests.Add(request);
            return Task.FromResult(new ReconstructionProviderSubmitResult(
                "req-123",
                new Uri("https://queue.fal.run/status/req-123"),
                new Uri("https://queue.fal.run/response/req-123"),
                new Uri("https://queue.fal.run/cancel/req-123"),
                "PUT",
                JsonNode.Parse(
                    @"{""request_id"":""req-123"",""status_url"":""https://queue.fal.run/status/req-123"",""response_url"":""https://queue.fal.run/response/req-123"",""cancel_url"":""https://queue.fal.run/cancel/req-123""}")!));
        }

        public Task<ReconstructionProviderStatusResult> GetStatusAsync(
            string modelId,
            string providerJobId,
            Uri? providerStatusUrl,
            CancellationToken cancellationToken)
        {
            if (FixedStatusResult is not null)
                return Task.FromResult(FixedStatusResult);

            if (StatusResults.Count > 0)
                return Task.FromResult(StatusResults.Dequeue());

            return Task.FromResult(new ReconstructionProviderStatusResult(
                providerJobId,
                ReconstructionProviderLifecycleState.Polling,
                IsTerminal: false,
                IsSuccess: false,
                ProviderStatusJson: JsonNode.Parse(@"{""status"":""IN_PROGRESS""}")!,
                Error: null));
        }

        public async Task<JsonNode> GetResultAsync(
            string modelId,
            string providerJobId,
            Uri? providerResponseUrl,
            CancellationToken cancellationToken)
        {
            Interlocked.Increment(ref _resultCallCount);
            lock (ResultCalls)
            {
                ResultCalls.Add(providerJobId);
            }

            ResultStarted?.TrySetResult(true);
            if (ReleaseResult is not null)
                await ReleaseResult.Task.ConfigureAwait(false);
            return ResultJson;
        }

        public Task<ProviderCancelOutcome> CancelAsync(
            string modelId,
            string providerJobId,
            Uri? providerCancelUrl,
            string? providerCancelHttpMethod,
            CancellationToken cancellationToken)
        {
            CancelCalls.Add(providerJobId);
            return Task.FromResult<ProviderCancelOutcome>(new CanceledOutcome());
        }
    }

    private sealed class FakeFileDownloader : IReconstructionFileDownloader
    {
        public Dictionary<string, byte[]> Files { get; } = new();

        public byte[] Download(Uri uri)
        {
            if (!Files.TryGetValue(uri.ToString(), out var content))
                throw new InvalidOperationException($"Unexpected download URI '{uri}'.");
            return content;
        }
    }

    private sealed class FakeSourceImagePublisher : IReconstructionSourceImagePublisher
    {
        public List<string> PublishedPaths { get; } = new();
        public bool ThrowOnPublish { get; set; }

        public Task<Uri> PublishAsync(
            Artifact artifact,
            string role,
            string absolutePath,
            CancellationToken ct)
        {
            if (ThrowOnPublish)
                throw new InvalidOperationException("publisher failed");

            PublishedPaths.Add(absolutePath);
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
