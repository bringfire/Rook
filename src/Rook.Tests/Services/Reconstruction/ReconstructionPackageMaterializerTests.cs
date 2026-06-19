using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json.Nodes;
using Rook.Artifacts;
using Rook.Services.Reconstruction;
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
    public void Materialize_HunyuanPayload_CreatesPackageRolesAndImportManifest()
    {
        var store = new ArtifactStore(NewTempRoot());
        var source = store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var materializer = new ReconstructionPackageMaterializer(
            store,
            new FakeFileDownloader(new Dictionary<string, byte[]>
            {
                ["https://example.test/model.glb"] = new byte[] { 10 },
                ["https://example.test/model.obj"] = new byte[] { 11 },
                ["https://example.test/material.mtl"] = new byte[] { 12 },
                ["https://example.test/texture.png"] = new byte[] { 13 },
                ["https://example.test/thumb.png"] = new byte[] { 14 },
            }));

        var artifact = materializer.Materialize(
            jobId: Guid.NewGuid(),
            sourceArtifactIds: new[] { source.Id },
            provider: "fal",
            modelId: "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
            providerResultJson: HunyuanPayload);

        Assert.Equal("reconstruction_package", artifact.Kind);
        Assert.Contains(artifact.Files, f => f.Role == "model_glb");
        Assert.Contains(artifact.Files, f => f.Role == "model_obj");
        Assert.Contains(artifact.Files, f => f.Role == "material_mtl");
        Assert.Contains(artifact.Files, f => f.Role == "texture");
        Assert.Contains(artifact.Files, f => f.Role == "thumbnail");
        Assert.Contains(artifact.Files, f => f.Role == "provider_result_json");
        Assert.Contains(artifact.Files, f => f.Role == "import_manifest");
        Assert.Contains(source.Id, artifact.ParentIds);

        var manifest = JsonNode.Parse(File.ReadAllText(
            store.GetBlobAbsolutePath(artifact.Id, "import_manifest")))!;
        Assert.Equal("model_glb", manifest["preferred_asset"]!.GetValue<string>());
        Assert.Equal(
            "texture",
            manifest["asset_bindings"]!["model_obj"]!["companion_roles"]![1]!.GetValue<string>());
        Assert.Equal("provider_default", manifest["placement"]!["units_policy"]!.GetValue<string>());
    }

    [Fact]
    public void Materialize_MeshyPayload_PreservesTextureMapRoles()
    {
        var store = new ArtifactStore(NewTempRoot());
        var source = store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var materializer = new ReconstructionPackageMaterializer(
            store,
            new FakeFileDownloader(new Dictionary<string, byte[]>
            {
                ["https://example.test/meshy.glb"] = new byte[] { 1 },
                ["https://example.test/base_color.png"] = new byte[] { 2 },
                ["https://example.test/normal.png"] = new byte[] { 3 },
                ["https://example.test/roughness.png"] = new byte[] { 4 },
            }));

        var artifact = materializer.Materialize(
            jobId: Guid.NewGuid(),
            sourceArtifactIds: new[] { source.Id },
            provider: "fal",
            modelId: "fal-ai/meshy/v6/image-to-3d",
            providerResultJson: MeshyPayload);

        Assert.Contains(artifact.Files, f => f.Role == "model_glb");
        Assert.Contains(artifact.Files, f => f.Role == "texture_base_color");
        Assert.Contains(artifact.Files, f => f.Role == "texture_normal");
        Assert.Contains(artifact.Files, f => f.Role == "texture_roughness");
    }

    private string NewTempRoot()
    {
        var root = Path.Combine(Path.GetTempPath(), $"rook-reconstruction-package-{Guid.NewGuid():N}");
        _roots.Add(root);
        return root;
    }

    private static readonly JsonNode HunyuanPayload = JsonNode.Parse("""
    {
      "model_urls": {
        "glb": {"url": "https://example.test/model.glb"},
        "obj": {"url": "https://example.test/model.obj"},
        "mtl": {"url": "https://example.test/material.mtl"}
      },
      "texture": {"url": "https://example.test/texture.png"},
      "thumbnail": {"url": "https://example.test/thumb.png"}
    }
    """)!;

    private static readonly JsonNode MeshyPayload = JsonNode.Parse("""
    {
      "model_glb": {"url": "https://example.test/meshy.glb"},
      "texture_urls": {
        "base_color": {"url": "https://example.test/base_color.png"},
        "normal": {"url": "https://example.test/normal.png"},
        "roughness": {"url": "https://example.test/roughness.png"}
      }
    }
    """)!;

    private sealed class FakeFileDownloader : IReconstructionFileDownloader
    {
        private readonly IReadOnlyDictionary<string, byte[]> _files;

        public FakeFileDownloader(IReadOnlyDictionary<string, byte[]> files)
        {
            _files = files;
        }

        public byte[] Download(Uri uri)
        {
            if (!_files.TryGetValue(uri.ToString(), out var content))
                throw new InvalidOperationException($"Unexpected download URI '{uri}'.");
            return content;
        }
    }
}
