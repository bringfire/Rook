using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Reconstruction;
using Rook.Services.Reconstruction.Fal;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Reconstruction.Fal;

public sealed class FalReconstructionResultMapperTests
{
    // The literal provider_result_json returned by fal-ai/hunyuan-3d/v3.1/rapid for the
    // failing live job (96a7179f). Keyed in both mapper and resolver tests so the
    // classifier-agreement invariant can be verified against the same fixture.
    private const string LiteralHunyuanRapidResultJson = """
        {
          "model_glb":   { "url": "https://fal.media/files/95befe79/model.obj",
                           "content_type": "model/obj",
                           "file_name": "95befe79_model.obj" },
          "material_mtl":{ "url": "https://fal.media/files/95befe79/material.mtl",
                           "content_type": "text/plain",
                           "file_name": "material.mtl" },
          "texture":     { "url": "https://fal.media/files/95befe79/texture_pbr_v128_metallic.png",
                           "content_type": "image/png",
                           "file_name": "texture_pbr_v128_metallic.png" },
          "thumbnail":   { "url": "https://fal.media/files/95befe79/preview.png",
                           "file_name": "preview.png" },
          "model_urls":  {
            "glb":     null,
            "fbx":     null,
            "obj":     { "url": "https://fal.media/files/95befe79/model.obj",
                         "content_type": "model/obj",
                         "file_name": "95befe79_model.obj" },
            "mtl":     { "url": "https://fal.media/files/95befe79/material.mtl",
                         "content_type": "text/plain",
                         "file_name": "material.mtl" },
            "texture": { "url": "https://fal.media/files/95befe79/texture_pbr_v128_metallic.png",
                         "content_type": "image/png",
                         "file_name": "texture_pbr_v128_metallic.png" },
            "usdz":    null
          }
        }
        """;

    [Fact]
    public void MapArtifacts_TopLevelTexture_ClassifiedByFilename_NotGeneric()
    {
        var json = JsonNode.Parse(LiteralHunyuanRapidResultJson);
        var artifacts = FalReconstructionResultMapper.MapArtifacts(json!);
        Assert.Contains(artifacts, a => a.Role == "texture_metallic");
        Assert.DoesNotContain(artifacts, a => a.Role == ReconstructionFileRoles.Texture);     // no generic
        Assert.DoesNotContain(artifacts, a => a.Role == "texture_base_color");                 // no diffuse
        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.ModelObj);
        Assert.DoesNotContain(artifacts, a => a.Role == ReconstructionFileRoles.ModelGlb);
    }


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
