using Rook.Services.Reconstruction.Fal;
using Xunit;

namespace Rook.Tests.Services.Reconstruction.Fal;

public sealed class ObjMaterialReferencesTests
{
    [Fact]
    public void ReferencedMapFileNames_ParsesAllMapsAndStripsOptions()
    {
        var mtl = "newmtl Material\nKd 0.8 0.8 0.8\n"
            + "map_Kd texture_pbr_v128.png\nmap_Pm texture_pbr_v128_metallic.png\n"
            + "map_Pr texture_pbr_v128_roughness.png\nmap_Bump -bm 1.0 texture_pbr_v128_normal.png\n";
        var maps = ObjMaterialReferences.ReferencedMapFileNames(mtl);
        Assert.Equal(new[]{
            "texture_pbr_v128.png","texture_pbr_v128_metallic.png",
            "texture_pbr_v128_roughness.png","texture_pbr_v128_normal.png"}, maps);
    }

    [Fact]
    public void ReferencedMapFileNames_IgnoresBlankCommentNonMapLines()
    {
        var maps = ObjMaterialReferences.ReferencedMapFileNames("# c\n\nnewmtl M\nNs 250\nmap_Kd a.png\n");
        Assert.Equal(new[]{ "a.png" }, maps);
    }
}
