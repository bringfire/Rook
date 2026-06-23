using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Artifacts;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionProviderFileNamesTests
{
    // The literal provider_result_json returned by fal-ai/hunyuan-3d/v3.1/rapid for the
    // failing live job (96a7179f). Mirrors the constant in FalReconstructionResultMapperTests
    // so the classifier-agreement invariant can be verified against the same fixture.
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
    public void ProviderFileNamesByRole_KeysMetallicUnderClassifiedRole()
    {
        var json = (JsonObject)JsonNode.Parse(LiteralHunyuanRapidResultJson)!;
        var package = PackageWithRoles("model_obj", "material_mtl", "texture_metallic", "thumbnail"); // post-fix layout
        var names = ReconstructionProviderFileNames.ProviderFileNamesByRole(json, package);
        Assert.Equal("texture_pbr_v128_metallic.png", names["texture_metallic"]);
        Assert.False(names.ContainsKey(ReconstructionFileRoles.Texture));   // no generic key
    }

    // Creates a minimal Artifact whose Files list carries exactly the given roles.
    // The Path for each file is a placeholder (role.bin) — only the Role matters for HasRole checks.
    private static Artifact PackageWithRoles(params string[] roles)
    {
        var files = new List<ArtifactFile>();
        foreach (var role in roles)
            files.Add(new ArtifactFile(role, $"{role}.bin"));

        return new Artifact(
            Id: Guid.NewGuid(),
            Kind: ReconstructionArtifactKinds.Package,
            CreatedAt: DateTimeOffset.UtcNow,
            Files: files,
            ParentIds: Array.Empty<Guid>(),
            Metadata: new Dictionary<string, JsonNode?>(),
            Flags: new Dictionary<string, JsonNode?>());
    }
}
