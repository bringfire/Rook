using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Reconstruction;
using Rook.Services.Reconstruction.Fal;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Handlers;

public sealed class ReconstructionOpHandlerTests : IDisposable
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
    public async Task DispatchAsync_Models_ReturnsDefaultStableCatalog()
    {
        var fixture = CreateFixture();

        var response = await fixture.Handler.DispatchAsync(
            @"{""op"":""models""}",
            CancellationToken.None);

        Assert.True(response.Success);
        var json = JsonSerializer.Serialize(response.Data);
        Assert.Contains(HunyuanModelId, json);
        Assert.DoesNotContain("fal-ai/meshy/v6/image-to-3d", json);
    }

    [Fact]
    public async Task DispatchAsync_SubmitMissingSource_ReturnsStructuredFailure()
    {
        var fixture = CreateFixture();

        var response = await fixture.Handler.DispatchAsync(
            @"{""op"":""submit_job""}",
            CancellationToken.None);

        Assert.False(response.Success);
        Assert.Equal(400, response.HttpStatus);
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        Assert.Equal("invalid_request", data["code"]);
        Assert.Equal("source_artifact_id", data["field"]);
    }

    [Fact]
    public void DispatchOffUi_PrepareImport_ResolvesPreferredAssetPath()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 1, 2, 3 };
        var package = fixture.Materializer.Materialize(
            Guid.NewGuid(),
            Array.Empty<Guid>(),
            "fal",
            HunyuanModelId,
            JsonNode.Parse("""
            {
              "model_urls": {
                "glb": {"url": "https://example.test/model.glb"}
              }
            }
            """)!);

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"prepare_import\"," +
            $"\"package_id\":\"{package.Id}\"" +
            "}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        Assert.Equal("model_glb", data["asset_role"]);
        Assert.EndsWith("model_glb.glb", Assert.IsType<string>(data["path"]));
    }

    [Fact]
    public void DispatchOffUi_RecordImport_AppendsImportManifestHistory()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 1, 2, 3 };
        var package = fixture.Materializer.Materialize(
            Guid.NewGuid(),
            Array.Empty<Guid>(),
            "fal",
            HunyuanModelId,
            JsonNode.Parse("""
            {
              "model_urls": {
                "glb": {"url": "https://example.test/model.glb"}
              }
            }
            """)!);

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"record_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            "\"asset_role\":\"model_glb\"," +
            "\"imported_ids\":[\"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa\"]," +
            "\"associated\":true" +
            "}");

        Assert.True(response.Success);
        var manifest = JsonNode.Parse(File.ReadAllText(
            fixture.Store.GetBlobAbsolutePath(package.Id, ReconstructionFileRoles.ImportManifest)))!;
        Assert.Equal(
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            manifest["imports"]![0]!["imported_ids"]![0]!.GetValue<string>());
        Assert.True(manifest["imports"]![0]!["associated"]!.GetValue<bool>());
    }

    private Fixture CreateFixture()
    {
        var root = NewTempRoot();
        var store = new ArtifactStore(Path.Combine(root, "artifacts"));
        var ledger = new JsonlReconstructionJobLedger(Path.Combine(root, "ledger.jsonl"));
        var catalog = ReconstructionModelCatalog.FromJson(CatalogJson);
        var provider = new FakeReconstructionProvider();
        var downloader = new FakeFileDownloader();
        var publisher = new FakeSourceImagePublisher();
        var materializer = new ReconstructionPackageMaterializer(store, downloader);
        var manager = new ReconstructionJobManager(
            store,
            catalog,
            ledger,
            provider,
            materializer,
            publisher);
        return new Fixture(
            store,
            downloader,
            materializer,
            new ReconstructionOpHandler(catalog, manager, store));
    }

    private string NewTempRoot()
    {
        var root = Path.Combine(Path.GetTempPath(), $"rook-reconstruction-handler-{Guid.NewGuid():N}");
        _roots.Add(root);
        return root;
    }

    private sealed record Fixture(
        ArtifactStore Store,
        FakeFileDownloader Downloader,
        ReconstructionPackageMaterializer Materializer,
        ReconstructionOpHandler Handler);

    private sealed class FakeReconstructionProvider : IReconstructionProvider
    {
        public Task<ReconstructionProviderSubmitResult> SubmitAsync(
            ReconstructionProviderSubmitRequest request,
            CancellationToken cancellationToken)
            => Task.FromResult(new ReconstructionProviderSubmitResult(
                "req-123",
                JsonNode.Parse(@"{""request_id"":""req-123""}")!));

        public Task<ReconstructionProviderStatusResult> GetStatusAsync(
            string modelId,
            string providerJobId,
            CancellationToken cancellationToken)
            => Task.FromResult(new ReconstructionProviderStatusResult(
                providerJobId,
                ReconstructionProviderLifecycleState.Polling,
                IsTerminal: false,
                IsSuccess: false,
                ProviderStatusJson: JsonNode.Parse("{}")!,
                Error: null));

        public Task<JsonNode> GetResultAsync(
            string modelId,
            string providerJobId,
            CancellationToken cancellationToken)
            => Task.FromResult<JsonNode>(JsonNode.Parse("{}")!);

        public Task<ProviderCancelOutcome> CancelAsync(
            string modelId,
            string providerJobId,
            CancellationToken cancellationToken)
            => Task.FromResult<ProviderCancelOutcome>(new CanceledOutcome());
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
        public Task<Uri> PublishAsync(
            Artifact artifact,
            string role,
            string absolutePath,
            CancellationToken ct)
            => Task.FromResult(new Uri("https://rook.local/source.png"));
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
        },
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
        }
      ]
    }
    """;
}
