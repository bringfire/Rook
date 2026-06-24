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

    [Fact]
    public void MapArtifacts_MeshyShape_ClassifiesModelsAndTextures()
    {
        // REAL fal Meshy v6 shape (captured from live job cacbc3c4 / provider_result_json): top-level
        // model_glb + model_urls{glb,obj,fbx,usdz,stl} + texture_urls as an array of PBR-slot objects.
        // The base_color file is named "texture_0.png" (NOT self-describing), so the slot key — not the
        // filename — must drive the role. The earlier flat-shape fixture was a fiction the live smoke
        // exposed: the mapper dropped Meshy's textures and result_missing_texture fired falsely.
        var body = JsonNode.Parse("""
        {
          "model_glb": { "url": "https://cdn.fal/m.glb", "file_name": "model.glb" },
          "model_urls": {
            "glb":  { "url": "https://cdn.fal/m.glb" },
            "obj":  { "url": "https://cdn.fal/m.obj",  "file_name": "model.obj" },
            "fbx":  { "url": "https://cdn.fal/m.fbx",  "file_name": "model.fbx" },
            "usdz": { "url": "https://cdn.fal/m.usdz", "file_name": "model.usdz" },
            "stl":  { "url": "https://cdn.fal/m.stl",  "file_name": "model.stl" }
          },
          "texture_urls": [
            { "base_color": { "url": "https://cdn.fal/texture_0.png", "file_name": "texture_0.png" },
              "metallic": null,
              "normal": { "url": "https://cdn.fal/texture_0_normal.png", "file_name": "texture_0_normal.png" },
              "roughness": null }
          ]
        }
        """)!;

        var roles = FalReconstructionResultMapper.MapArtifacts(body).Select(a => a.Role).ToList();

        Assert.Contains(ReconstructionFileRoles.ModelGlb, roles);
        Assert.Contains(ReconstructionFileRoles.ModelObj, roles);
        Assert.Contains("model_fbx", roles);
        Assert.Contains("model_usdz", roles);
        Assert.Contains("model_stl", roles);
        Assert.Contains("texture_base_color", roles);  // from the base_color SLOT KEY, not the filename
        Assert.Contains("texture_normal", roles);
    }

    [Fact]
    public void MapArtifacts_MeshyGeometryOnly_HasModelNoTexture()
    {
        var body = JsonNode.Parse("""{ "model_glb": { "url": "https://cdn.fal/m.glb", "file_name": "m.glb" } }""")!;

        var artifacts = FalReconstructionResultMapper.MapArtifacts(body);

        Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.ModelGlb);
        Assert.DoesNotContain(artifacts, a => a.Role.StartsWith("texture", System.StringComparison.Ordinal));
    }
}
