using System;
using System.Collections.Generic;
using System.IO;
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
        public List<ReconstructionProviderSubmitRequest> SubmitRequests { get; } = new();
        public Queue<ReconstructionProviderStatusResult> StatusResults { get; } = new();
        public List<string> CancelCalls { get; } = new();
        public List<string> ResultCalls { get; } = new();
        public JsonNode ResultJson { get; set; } = JsonNode.Parse("{}")!;

        public Task<ReconstructionProviderSubmitResult> SubmitAsync(
            ReconstructionProviderSubmitRequest request,
            CancellationToken cancellationToken)
        {
            SubmitRequests.Add(request);
            return Task.FromResult(new ReconstructionProviderSubmitResult(
                "req-123",
                JsonNode.Parse(@"{""request_id"":""req-123""}")!));
        }

        public Task<ReconstructionProviderStatusResult> GetStatusAsync(
            string modelId,
            string providerJobId,
            CancellationToken cancellationToken)
        {
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

        public Task<JsonNode> GetResultAsync(
            string modelId,
            string providerJobId,
            CancellationToken cancellationToken)
        {
            ResultCalls.Add(providerJobId);
            return Task.FromResult(ResultJson);
        }

        public Task<ProviderCancelOutcome> CancelAsync(
            string modelId,
            string providerJobId,
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

        public Task<Uri> PublishAsync(
            Artifact artifact,
            string role,
            string absolutePath,
            CancellationToken ct)
        {
            PublishedPaths.Add(absolutePath);
            return Task.FromResult(new Uri("https://rook.local/source.png"));
        }
    }

    private const string CatalogJson = """
    {
      "schema_version": 1,
      "models": [
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
