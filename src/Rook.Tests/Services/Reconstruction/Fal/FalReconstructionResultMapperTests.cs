using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Reconstruction;
using Rook.Services.Reconstruction.Fal;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Reconstruction.Fal;

public sealed class FalReconstructionResultMapperTests
{
    [Fact]
    public void MapArtifacts_BirefnetBody_YieldsImageAndMaskRoles()
    {
        var body = JsonNode.Parse("""
        {
          "image": {"url": "https://example.test/out.png"},
          "mask_image": {"url": "https://example.test/mask.png"}
        }
        """)!;

        var artifacts = FalReconstructionResultMapper.MapArtifacts(body);

        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.Image);
        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.Mask);
        var image = artifacts.Single(a => a.Role == ReconstructionFileRoles.Image);
        var remote = Assert.IsType<RemoteArtifactBody>(image.Body);
        Assert.Equal("https://example.test/out.png", remote.Url.ToString());
    }

    [Fact]
    public void MapArtifacts_BirefnetBody_NoMaskImage_YieldsImageOnly()
    {
        var body = JsonNode.Parse("""{ "image": {"url": "https://example.test/out.png"} }""")!;

        var artifacts = FalReconstructionResultMapper.MapArtifacts(body);

        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.Image);
        Assert.DoesNotContain(artifacts, a => a.Role == ReconstructionFileRoles.Mask);
    }

    [Fact]
    public void MapArtifacts_3dBody_YieldsModelRoles_AndNoImageOrMask()
    {
        var body = JsonNode.Parse("""
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

        var artifacts = FalReconstructionResultMapper.MapArtifacts(body);

        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.ModelGlb);
        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.ModelObj);
        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.MaterialMtl);
        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.Texture);
        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.Thumbnail);
        Assert.DoesNotContain(artifacts, a => a.Role == ReconstructionFileRoles.Image);
        Assert.DoesNotContain(artifacts, a => a.Role == ReconstructionFileRoles.Mask);
    }
}
