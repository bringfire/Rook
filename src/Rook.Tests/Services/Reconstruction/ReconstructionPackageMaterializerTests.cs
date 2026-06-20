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

public sealed class ReconstructionPackageMaterializerTests : IDisposable
{
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
    public async Task MaterializeAsync_NoModelAsset_FailsAndCreatesNoPackage()
    {
        var store = new ArtifactStore(NewTempRoot());
        var envelope = new ProviderResultEnvelope(
            new[] { Remote(ReconstructionFileRoles.Thumbnail, "https://example.test/thumb.png") },
            new Dictionary<string, JsonNode> { ["provider_result_json"] = new JsonObject() });

        var result = await new ReconstructionPackageMaterializer(store, new FakeDownloader())
            .MaterializeAsync(Guid.NewGuid(), Array.Empty<Guid>(), "fal", "m", envelope, CancellationToken.None);

        Assert.False(result.Success);
        Assert.Null(result.Package);
        Assert.Equal(GenerationErrorCode.ExecutionFailed, result.Error!.Code);
        Assert.Empty(store.List());
    }

    [Fact]
    public async Task MaterializeAsync_HunyuanEnvelope_WritesRoleBlobsAndSidecars()
    {
        var store = new ArtifactStore(NewTempRoot());
        var source = store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var downloader = new FakeDownloader
        {
            Files =
            {
                ["https://example.test/model.glb"] = new byte[] { 10 },
                ["https://example.test/model.obj"] = new byte[] { 11 },
                ["https://example.test/material.mtl"] = new byte[] { 12 },
                ["https://example.test/texture.png"] = new byte[] { 13 },
                ["https://example.test/thumb.png"] = new byte[] { 14 },
            },
        };
        var envelope = FalReconstructionResultMapper.ToEnvelope(JsonNode.Parse("""
        {
          "model_urls": {
            "glb": {"url": "https://example.test/model.glb"},
            "obj": {"url": "https://example.test/model.obj"},
            "mtl": {"url": "https://example.test/material.mtl"}
          },
          "texture": {"url": "https://example.test/texture.png"},
          "thumbnail": {"url": "https://example.test/thumb.png"}
        }
        """)!);

        var result = await new ReconstructionPackageMaterializer(store, downloader)
            .MaterializeAsync(Guid.NewGuid(), new[] { source.Id }, "fal", "m", envelope, CancellationToken.None);

        Assert.True(result.Success);
        var package = result.Package!;
        Assert.Equal(ReconstructionArtifactKinds.Package, package.Kind);
        Assert.Contains(package.Files, f => f.Role == ReconstructionFileRoles.ModelGlb);
        Assert.Contains(package.Files, f => f.Role == ReconstructionFileRoles.ModelObj);
        Assert.Contains(package.Files, f => f.Role == ReconstructionFileRoles.MaterialMtl);
        Assert.Contains(package.Files, f => f.Role == ReconstructionFileRoles.Texture);
        Assert.Contains(package.Files, f => f.Role == ReconstructionFileRoles.Thumbnail);
        Assert.Contains(package.Files, f => f.Role == ReconstructionFileRoles.ProviderResultJson);
        Assert.Contains(package.Files, f => f.Role == ReconstructionFileRoles.ImportManifest);
        Assert.Contains(source.Id, package.ParentIds);

        // role blob extension parity with the pre-convergence materializer
        Assert.Contains(package.Files, f => f.Role == ReconstructionFileRoles.ModelGlb && f.Path.EndsWith(".glb", StringComparison.Ordinal));

        var manifest = JsonNode.Parse(File.ReadAllText(
            store.GetBlobAbsolutePath(package.Id, ReconstructionFileRoles.ImportManifest)))!;
        Assert.Equal("model_glb", manifest["preferred_asset"]!.GetValue<string>());
        Assert.Equal("provider_default", manifest["placement"]!["units_policy"]!.GetValue<string>());

        // provider_result_json sidecar preserves the raw fal body (import route depends on this)
        var providerJson = JsonNode.Parse(File.ReadAllText(
            store.GetBlobAbsolutePath(package.Id, ReconstructionFileRoles.ProviderResultJson)))!;
        Assert.Equal(
            "https://example.test/model.glb",
            providerJson["model_urls"]!["glb"]!["url"]!.GetValue<string>());
    }

    [Fact]
    public async Task MaterializeAsync_DownloadFailure_ReturnsTypedErrorNoPackage()
    {
        var store = new ArtifactStore(NewTempRoot());
        var envelope = new ProviderResultEnvelope(
            new[] { Remote(ReconstructionFileRoles.ModelGlb, "https://example.test/missing.glb") },
            new Dictionary<string, JsonNode> { ["provider_result_json"] = new JsonObject() });

        var result = await new ReconstructionPackageMaterializer(store, new FakeDownloader())
            .MaterializeAsync(Guid.NewGuid(), Array.Empty<Guid>(), "fal", "m", envelope, CancellationToken.None);

        Assert.False(result.Success);
        Assert.Null(result.Package);
        Assert.Equal(GenerationErrorCode.DependencyUnavailable, result.Error!.Code);
        Assert.Empty(store.List());
    }

    private static ResultArtifact Remote(string role, string url)
        => new(role, new RemoteArtifactBody(new Uri(url)), null, new Dictionary<string, JsonNode>());

    private string NewTempRoot()
    {
        var root = Path.Combine(Path.GetTempPath(), $"rook-reconstruction-package-{Guid.NewGuid():N}");
        _roots.Add(root);
        return root;
    }

    private sealed class FakeDownloader : IReconstructionRemoteAssetDownloader
    {
        public Dictionary<string, byte[]> Files { get; } = new();

        public Task<ReconstructionDownloadResult> DownloadAsync(Uri url, string role, CancellationToken ct)
        {
            if (Files.TryGetValue(url.ToString(), out var bytes))
                return Task.FromResult(new ReconstructionDownloadResult(true, bytes, "application/octet-stream", null));
            return Task.FromResult(new ReconstructionDownloadResult(
                false,
                null,
                null,
                new GenerationError(GenerationErrorCode.DependencyUnavailable, $"missing {url}", Retryable: true)));
        }
    }
}
