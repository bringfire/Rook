using System.Linq;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionSubmitGateTests
{
    private static ReconstructionModelEntry Entry(string json)
        => ReconstructionModelCatalog.FromJson("{\"models\":[" + json + "]}").List(true, true).Single();

    private const string ImageJson = """
        { "model_id": "img", "provider": "fal", "task": "single_image_to_3d", "status": "stable",
          "enabled": true, "pipeline_roles": ["single_image_to_3d"], "input_types": ["image_url"],
          "output_roles": ["model_glb"], "preferred_asset_role": "model_glb", "fallback_order": ["model_glb"],
          "supports_pbr": false, "preprocessing": {"recommended": false, "required": false}, "docs_url": "https://example.test",
          "input": { "mode": "single_image", "source_field": "input_image_url" } }
        """;

    private const string MeshJson = """
        { "model_id": "mesh", "provider": "fal", "task": "mesh_to_mesh_topology", "status": "experimental",
          "enabled": true, "pipeline_roles": ["mesh_to_mesh", "smart_topology"], "input_types": ["model_url"],
          "output_roles": ["model_glb"], "preferred_asset_role": "model_glb", "fallback_order": ["model_glb"],
          "supports_pbr": false, "preprocessing": {"recommended": false, "required": false}, "docs_url": "https://example.test",
          "input": { "mode": "single_model", "source_field": "input_file_url" } }
        """;

    [Fact]
    public void ImageGate_AcceptsImage_RejectsMesh()
    {
        Assert.True(ReconstructionJobManager.IsSubmittableImageModel(Entry(ImageJson), false));
        Assert.False(ReconstructionJobManager.IsSubmittableImageModel(Entry(MeshJson), true));
    }

    [Fact]
    public void MeshGate_AcceptsMesh_RejectsImage()
    {
        Assert.True(ReconstructionJobManager.IsSubmittableMeshModel(Entry(MeshJson), true));
        Assert.False(ReconstructionJobManager.IsSubmittableMeshModel(Entry(ImageJson), true));
    }

    [Fact]
    public void MeshGate_ExperimentalRejectedWithoutOverride()
    {
        Assert.False(ReconstructionJobManager.IsSubmittableMeshModel(Entry(MeshJson), false));
        Assert.True(ReconstructionJobManager.IsSubmittableMeshModel(Entry(MeshJson), true));
    }
}
