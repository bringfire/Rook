using System.IO;
using Xunit;

namespace Rook.Tests.Handlers;

public sealed class NativeReconstructionDispatchSourceTests
{
    [Fact]
    public void RookServer_RegistersReconstructionRoutes()
    {
        var text = File.ReadAllText(Path.Combine(RepoRoot, "src", "RookNative", "RookServer.cpp"));

        Assert.Contains(@"""/reconstruction/2d-to-3d/models""", text);
        Assert.Contains(@"""/reconstruction/2d-to-3d/jobs""", text);
        Assert.Contains(@"""/reconstruction/2d-to-3d/import""", text);
    }

    [Fact]
    public void NativeBridge_HasDedicatedReconstructionDispatch()
    {
        var text = File.ReadAllText(Path.Combine(
            RepoRoot,
            "src",
            "RookNative",
            "Handlers",
            "GrasshopperProxyHandler.h"));

        Assert.Contains("HasReconstructionDispatchRegistration", text);
        Assert.Contains("InvokeReconstructionDispatchWithBody", text);
    }

    [Fact]
    public void BridgeAbiVersion_IsBumpedOnBothSides()
    {
        var managed = File.ReadAllText(Path.Combine(
            RepoRoot,
            "src",
            "Rook",
            "InternalBridge",
            "NativeGhBridgeRegistrar.cs"));
        var native = File.ReadAllText(Path.Combine(
            RepoRoot,
            "src",
            "RookNative",
            "Handlers",
            "GrasshopperProxyHandler.cpp"));

        Assert.Contains("BridgeAbiVersion = 16", managed);
        Assert.Contains("kGhBridgeAbiVersion = 16", native);
        Assert.Contains("ReconstructionDispatch", managed);
        Assert.Contains("reconstruction_dispatch", native);
    }

    [Fact]
    public void NativeImportRoute_IsHybridAndStampsReconstructionMetadata()
    {
        var text = File.ReadAllText(Path.Combine(
            RepoRoot,
            "src",
            "RookNative",
            "Handlers",
            "ImportExportHandler.cpp"));

        Assert.Contains("HandleReconstructionImport", text);
        Assert.Contains("ObjectDiffTracker", text);
        Assert.Contains("prepare_import", text);
        Assert.Contains("record_import", text);
        Assert.Contains("rook.reconstruction.package_id", text);
        Assert.Contains("rook.reconstruction.job_id", text);
        Assert.Contains("rook.reconstruction.import_id", text);
        Assert.Contains("rook.reconstruction.asset_role", text);
        Assert.Contains("\"association_failed\"", text);
        Assert.Contains("\"import_history_failed\"", text);
    }

    private static string RepoRoot
        => Path.GetFullPath(Path.Combine(System.AppContext.BaseDirectory, "..", "..", "..", "..", ".."));
}
