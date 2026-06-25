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

public sealed class ReconstructionMeshSubmitFlowTests : IDisposable
{
    private const string MeshyMeshModelId = "fal-ai/meshy/v6/mesh-to-mesh";
    private const string HunyuanImageModelId = "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d";

    private readonly List<string> _roots = new();
    private readonly List<ReconstructionJobManager> _managers = new();

    public void Dispose()
    {
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

    // ── Case A: Happy path ──────────────────────────────────────────────────────────────────────
    // A reconstruction_package with a model_glb blob is submitted through the mesh path.
    // The GLB is uploaded to the fake publisher, the mesh provider receives a submit request
    // with "input_file_url", and a ledger job is created with SourceRole=="model_glb" and
    // Task=="mesh_to_mesh_topology".
    [Fact]
    public async Task SubmitMeshAsync_HappyPath_PublishesGlbAndSubmitsToProvider()
    {
        var fixture = CreateFixture();
        var sourcePackage = fixture.Store.Create(
            ReconstructionArtifactKinds.Package,
            new[] { new BlobInput(ReconstructionFileRoles.ModelGlb, new byte[] { 1, 2, 3 }, "glb") });

        var result = await fixture.Manager.SubmitMeshAsync(
            new ReconstructionMeshSubmitRequest(
                sourcePackage.Id,
                MeshyMeshModelId,
                new JsonObject(),
                AllowExperimentalModel: true),
            CancellationToken.None);

        // Success
        Assert.True(result.Success);

        // Publisher received exactly one item with Mime=="model/gltf-binary"
        var published = Assert.Single(fixture.Publisher.Published);
        Assert.Equal("model/gltf-binary", published.Mime);

        // Provider received exactly one submit request with ViewUrls[0].Field=="input_file_url"
        var submitted = Assert.Single(fixture.Provider.SubmitRequests);
        Assert.Equal("input_file_url", submitted.ViewUrls[0].Field);

        // Provider options contain "input_file_type"=="glb"
        Assert.Equal("glb", submitted.Options["input_file_type"]!.GetValue<string>());

        // Ledger job has SourceRole=="model_glb" and Task=="mesh_to_mesh_topology"
        var job = fixture.Manager.Status(result.Job!.JobId).Job!;
        Assert.Equal(ReconstructionFileRoles.ModelGlb, job.SourceRole);
        Assert.Equal("mesh_to_mesh_topology", job.Task);

        // Lineage: SourceArtifactId == sourcePackage.Id
        Assert.Equal(sourcePackage.Id, job.SourceArtifactId);
    }

    // ── Case B: Image model id → rejected ──────────────────────────────────────────────────────
    // An image model (input_types: ["image_url"]) must be rejected by the mesh path.
    // No ledger job should be created and the publisher should not be called.
    [Fact]
    public async Task SubmitMeshAsync_ImageModelId_Rejected()
    {
        var fixture = CreateFixture();

        var result = await fixture.Manager.SubmitMeshAsync(
            new ReconstructionMeshSubmitRequest(
                Guid.NewGuid(),
                HunyuanImageModelId,
                new JsonObject(),
                AllowExperimentalModel: false),
            CancellationToken.None);

        Assert.False(result.Success);
        Assert.Equal("invalid_request", result.Failure!.Code);
        Assert.Empty(fixture.Manager.List(10).Jobs);
        Assert.Empty(fixture.Publisher.Published);
    }

    // ── Case C: Missing model_glb in package ───────────────────────────────────────────────────
    // A reconstruction_package without a model_glb blob must fail with missing_model_glb.
    // No ledger job should be created and the publisher should not be called.
    [Fact]
    public async Task SubmitMeshAsync_PackageMissingModelGlb_FailsWithMissingModelGlb()
    {
        var fixture = CreateFixture();
        var sourcePackage = fixture.Store.Create(
            ReconstructionArtifactKinds.Package,
            new[] { new BlobInput(ReconstructionFileRoles.ModelObj, new byte[] { 10, 20, 30 }, "obj") });

        var result = await fixture.Manager.SubmitMeshAsync(
            new ReconstructionMeshSubmitRequest(
                sourcePackage.Id,
                MeshyMeshModelId,
                new JsonObject(),
                AllowExperimentalModel: true),
            CancellationToken.None);

        Assert.False(result.Success);
        Assert.Equal("missing_model_glb", result.Failure!.Code);
        Assert.Empty(fixture.Manager.List(10).Jobs);
        Assert.Empty(fixture.Publisher.Published);
    }

    // ── Case D: User-supplied options.input_file_type → rejected ───────────────────────────────
    // input_file_type is a manager-injected key (not a user option). When the user includes it
    // in their options and the model has a catalog options block, the validator rejects it as
    // an unknown option. No ledger job should be created.
    [Fact]
    public async Task SubmitMeshAsync_UserSuppliesInputFileTypeOption_RejectedAsUnknown()
    {
        var fixture = CreateFixture();

        var result = await fixture.Manager.SubmitMeshAsync(
            new ReconstructionMeshSubmitRequest(
                Guid.NewGuid(),
                MeshyMeshModelId,
                new JsonObject { ["input_file_type"] = "glb" },
                AllowExperimentalModel: true),
            CancellationToken.None);

        Assert.False(result.Success);
        Assert.Equal("invalid_request", result.Failure!.Code);
        Assert.Empty(fixture.Manager.List(10).Jobs);
    }

    // ── Case E: Credential missing during upload ────────────────────────────────────────────────
    // When the publisher throws ReconstructionCredentialMissingException the submit result must
    // be missing_credential. A ledger job IS created (it progresses to Submitting before the
    // upload failure) and ends in Error state.
    [Fact]
    public async Task SubmitMeshAsync_CredentialMissingDuringUpload_RecordsMissingCredential()
    {
        var fixture = CreateFixture(throwCredentialMissing: true);
        var sourcePackage = fixture.Store.Create(
            ReconstructionArtifactKinds.Package,
            new[] { new BlobInput(ReconstructionFileRoles.ModelGlb, new byte[] { 1, 2, 3 }, "glb") });

        var result = await fixture.Manager.SubmitMeshAsync(
            new ReconstructionMeshSubmitRequest(
                sourcePackage.Id,
                MeshyMeshModelId,
                new JsonObject(),
                AllowExperimentalModel: true),
            CancellationToken.None);

        Assert.False(result.Success);
        Assert.Equal("missing_credential", result.Failure!.Code);

        // A ledger job exists (created before the upload) and is in Error state
        var jobs = fixture.Manager.List(10).Jobs;
        var job = Assert.Single(jobs);
        Assert.Equal(ReconstructionJobState.Error, job.State);
        Assert.Equal("missing_credential", job.Error!.Code);
    }

    // ── Fixture and helpers ──────────────────────────────────────────────────────────────────────

    private Fixture CreateFixture(bool throwCredentialMissing = false)
    {
        var root = NewTempRoot();
        var store = new ArtifactStore(Path.Combine(root, "artifacts"));
        var ledger = new JsonlReconstructionJobLedger(Path.Combine(root, "ledger.jsonl"));
        var provider = new FakeReconstructionProvider();
        var downloader = new FakeDownloader();
        var publisher = new FakeSourceImagePublisher
        {
            ThrowCredentialMissing = throwCredentialMissing,
        };
        var materializer = new ReconstructionPackageMaterializer(store, downloader);
        var preprocessMaterializer = new ReconstructionPreprocessMaterializer(store, downloader);
        var manager = new ReconstructionJobManager(
            store,
            ReconstructionModelCatalog.FromJson(CatalogJson),
            ledger,
            provider,
            materializer,
            preprocessMaterializer,
            publisher);
        _managers.Add(manager);
        return new Fixture(store, ledger, provider, publisher, manager);
    }

    private string NewTempRoot()
    {
        var root = Path.Combine(Path.GetTempPath(), $"rook-mesh-submit-{Guid.NewGuid():N}");
        _roots.Add(root);
        return root;
    }

    private sealed record Fixture(
        ArtifactStore Store,
        JsonlReconstructionJobLedger Ledger,
        FakeReconstructionProvider Provider,
        FakeSourceImagePublisher Publisher,
        ReconstructionJobManager Manager);

    // ── Fakes ───────────────────────────────────────────────────────────────────────────────────

    private sealed class FakeReconstructionProvider : IReconstructionProvider
    {
        public List<ReconstructionProviderSubmitRequest> SubmitRequests { get; } = new();

        public Task<ProviderSubmitOutcome> SubmitAsync(
            ReconstructionProviderSubmitRequest request,
            CancellationToken cancellationToken)
        {
            SubmitRequests.Add(request);
            return Task.FromResult<ProviderSubmitOutcome>(new QueuedSubmitOutcome(new ProviderJobHandle(
                "req-mesh-1",
                statusUrl: new Uri("https://queue.fal.run/status/req-mesh-1"),
                responseUrl: new Uri("https://queue.fal.run/response/req-mesh-1"),
                cancelUrl: new Uri("https://queue.fal.run/cancel/req-mesh-1"),
                cancelHttpMethod: "PUT")));
        }

        public Task<ProviderStatusOutcome> GetStatusAsync(
            ProviderJobHandle handle,
            CancellationToken cancellationToken)
            => Task.FromResult<ProviderStatusOutcome>(
                new InFlightStatusOutcome(GenerationLifecycleState.Running, null));

        public Task<ProviderResultOutcome> FetchResultAsync(
            ProviderJobHandle handle,
            CancellationToken cancellationToken)
            => Task.FromResult<ProviderResultOutcome>(new FailedResultOutcome(
                new GenerationError(GenerationErrorCode.ExecutionFailed, "not used in flow tests", false)));

        public Task<ProviderCancelOutcome> CancelAsync(
            ProviderJobHandle handle,
            CancellationToken cancellationToken)
            => Task.FromResult<ProviderCancelOutcome>(new CanceledOutcome());
    }

    private sealed class FakeDownloader : IReconstructionRemoteAssetDownloader
    {
        public Task<ReconstructionDownloadResult> DownloadAsync(Uri url, string role, CancellationToken ct)
            => Task.FromResult(new ReconstructionDownloadResult(
                false,
                null,
                null,
                new GenerationError(GenerationErrorCode.DependencyUnavailable, $"missing {url}", Retryable: true)));
    }

    private sealed class FakeSourceImagePublisher : IReconstructionSourceImagePublisher
    {
        public List<(byte[] Bytes, string Mime, string FileName)> Published { get; } = new();
        public bool ThrowCredentialMissing { get; set; }

        public Task<Uri> PublishAsync(
            byte[] bytes,
            string mimeType,
            string fileName,
            CancellationToken ct)
        {
            if (ThrowCredentialMissing)
                throw new ReconstructionCredentialMissingException();

            Published.Add((bytes, mimeType, fileName));
            return Task.FromResult(new Uri("https://rook.local/source.glb"));
        }
    }

    // ── Catalog JSON ─────────────────────────────────────────────────────────────────────────────
    // Contains one image model (to test Case B rejection) and the mesh model under test.
    // The mesh model has an options block with at least one option so the validator can run
    // and reject unknown keys (Case D).
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
          "output_roles": ["model_glb"],
          "preferred_asset_role": "model_glb",
          "fallback_order": ["model_glb"],
          "supports_pbr": false,
          "input": { "mode": "single_image", "source_field": "input_image_url" },
          "preprocessing": { "recommended": false, "required": false },
          "docs_url": "https://example.test"
        },
        {
          "model_id": "fal-ai/meshy/v6/mesh-to-mesh",
          "provider": "fal",
          "task": "mesh_to_mesh_topology",
          "status": "experimental",
          "enabled": true,
          "pipeline_roles": ["mesh_to_mesh", "smart_topology"],
          "input_types": ["model_url"],
          "output_roles": ["model_glb"],
          "preferred_asset_role": "model_glb",
          "fallback_order": ["model_glb"],
          "supports_pbr": false,
          "input": { "mode": "single_model", "source_field": "input_file_url" },
          "options": [
            { "key": "should_texture", "label": "Should Texture", "kind": "boolean", "default": false }
          ],
          "preprocessing": { "recommended": false, "required": false },
          "docs_url": "https://example.test"
        }
      ]
    }
    """;
}
