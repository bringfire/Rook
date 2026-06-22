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

public sealed class ReconstructionPreprocessMaterializerTests : IDisposable
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
    public async Task RemoveBackground_Materializes_LinkedPreprocessedImage_SourceUntouched()
    {
        var store = new ArtifactStore(NewTempRoot());
        var source = store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var downloader = new FakeDownloader
        {
            Files =
            {
                ["https://example.test/out.png"] = new byte[] { 10, 11 },
                ["https://example.test/mask.png"] = new byte[] { 20, 21 },
            },
        };

        // BiRefNet v2 result body: image (object, .url) + optional mask_image (object, .url).
        var envelope = new ProviderResultEnvelope(
            new[] { Remote("image", "https://example.test/out.png") },
            new Dictionary<string, JsonNode>
            {
                ["provider_result_json"] = JsonNode.Parse("""
                {
                  "image": {"url": "https://example.test/out.png"},
                  "mask_image": {"url": "https://example.test/mask.png"}
                }
                """)!,
            });

        var result = await new ReconstructionPreprocessMaterializer(store, downloader)
            .MaterializeAsync(
                Guid.NewGuid(),
                new[] { source.Id },
                "fal",
                "fal-ai/birefnet/v2",
                envelope,
                CancellationToken.None);

        Assert.True(result.Success);
        var artifact = result.Package!;
        Assert.Equal(ReconstructionFileRoles.PreprocessedImage, artifact.Kind);
        Assert.Contains(artifact.Files, f => f.Role == "image");
        Assert.Contains(artifact.Files, f => f.Role == "mask");
        Assert.Equal(new[] { source.Id }, artifact.ParentIds.ToArray());

        // The source artifact is never modified: still present, same single role.
        var sourceAfter = store.Get(source.Id)!;
        Assert.Single(sourceAfter.Files);
        Assert.Equal("image", sourceAfter.Files[0].Role);
    }

    [Fact]
    public async Task RemoveBackground_NoMaskImage_MaterializesImageOnly()
    {
        var store = new ArtifactStore(NewTempRoot());
        var source = store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1 }, "png") });

        var downloader = new FakeDownloader
        {
            Files = { ["https://example.test/out.png"] = new byte[] { 10 } },
        };

        var envelope = new ProviderResultEnvelope(
            new[] { Remote("image", "https://example.test/out.png") },
            new Dictionary<string, JsonNode>
            {
                ["provider_result_json"] = JsonNode.Parse(
                    """{ "image": {"url": "https://example.test/out.png"} }""")!,
            });

        var result = await new ReconstructionPreprocessMaterializer(store, downloader)
            .MaterializeAsync(
                Guid.NewGuid(), new[] { source.Id }, "fal", "fal-ai/birefnet/v2", envelope, CancellationToken.None);

        Assert.True(result.Success);
        Assert.Contains(result.Package!.Files, f => f.Role == "image");
        Assert.DoesNotContain(result.Package!.Files, f => f.Role == "mask");
    }

    [Fact]
    public async Task RemoveBackground_MissingImageUrl_FailsAndCreatesNoArtifact()
    {
        var store = new ArtifactStore(NewTempRoot());
        var envelope = new ProviderResultEnvelope(
            new[] { Remote("image", "https://example.test/out.png") },
            new Dictionary<string, JsonNode>
            {
                ["provider_result_json"] = JsonNode.Parse("""{ "mask_image": {"url": "https://example.test/mask.png"} }""")!,
            });

        var result = await new ReconstructionPreprocessMaterializer(store, new FakeDownloader())
            .MaterializeAsync(
                Guid.NewGuid(), Array.Empty<Guid>(), "fal", "fal-ai/birefnet/v2", envelope, CancellationToken.None);

        Assert.False(result.Success);
        Assert.Null(result.Package);
        Assert.Equal(GenerationErrorCode.ExecutionFailed, result.Error!.Code);
        Assert.Empty(store.List());
    }

    private static ResultArtifact Remote(string role, string url)
        => new(role, new RemoteArtifactBody(new Uri(url)), null, new Dictionary<string, JsonNode>());

    private string NewTempRoot()
    {
        var root = Path.Combine(Path.GetTempPath(), $"rook-reconstruction-preprocess-{Guid.NewGuid():N}");
        _roots.Add(root);
        return root;
    }

    private sealed class FakeDownloader : IReconstructionRemoteAssetDownloader
    {
        public Dictionary<string, byte[]> Files { get; } = new();

        public Task<ReconstructionDownloadResult> DownloadAsync(Uri url, string role, CancellationToken ct)
        {
            if (Files.TryGetValue(url.ToString(), out var bytes))
                return Task.FromResult(new ReconstructionDownloadResult(true, bytes, "image/png", null));
            return Task.FromResult(new ReconstructionDownloadResult(
                false,
                null,
                null,
                new GenerationError(GenerationErrorCode.DependencyUnavailable, $"missing {url}", Retryable: true)));
        }
    }
}
