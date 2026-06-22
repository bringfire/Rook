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
    public void NativeBridge_RoutesCleanupPreparedImportThroughOffUiDispatch()
    {
        // The native import handler emits a cleanup_prepared_import op on post-prepare failure. The
        // managed bridge must accept it as an off-UI op; otherwise it is rejected 400 and prepared OBJ
        // bundles leak. Assert the case is grouped with the other off-UI dispatch ops.
        var managed = File.ReadAllText(Path.Combine(
            RepoRoot,
            "src",
            "Rook",
            "InternalBridge",
            "NativeGhBridgeRegistrar.cs"));

        var recordCase = managed.IndexOf(
            "case ReconstructionOpHandler.OpRecordImport:",
            System.StringComparison.Ordinal);
        Assert.True(recordCase >= 0, "Reconstruction off-UI dispatch group not found.");

        var cleanupCase = managed.IndexOf(
            "case ReconstructionOpHandler.OpCleanupPreparedImport:",
            System.StringComparison.Ordinal);
        // The off-UI callback that follows the reconstruction case labels (ExecuteOffUiApiResponseCallback
        // also appears in earlier dispatch switches, so search from the record case forward).
        var offUiCall = managed.IndexOf(
            "return ExecuteOffUiApiResponseCallback",
            recordCase,
            System.StringComparison.Ordinal);

        Assert.True(offUiCall > recordCase, "Off-UI callback should follow the off-UI case labels.");
        Assert.InRange(cleanupCase, recordCase, offUiCall);
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

    [Fact]
    public void ReconstructionDispatchFailures_UseStructuredFailureEnvelope()
    {
        var text = File.ReadAllText(Path.Combine(
            RepoRoot,
            "src",
            "RookNative",
            "Handlers",
            "GrasshopperProxyHandler.cpp"));
        var forward = ExtractFunction(text, "void ForwardReconstructionDispatch");

        Assert.Contains("SendReconstructionDispatchError", text);
        Assert.Contains("\"code\"", text);
        Assert.Contains("\"message\"", text);
        Assert.Contains("\"retryable\"", text);
        Assert.DoesNotContain("CRookServer::SendError(", forward);
    }

    [Fact]
    public void ReconstructionImportPrepareFailures_UseStructuredFailureEnvelope()
    {
        var text = File.ReadAllText(Path.Combine(
            RepoRoot,
            "src",
            "RookNative",
            "Handlers",
            "ImportExportHandler.cpp"));
        var prepare = ExtractFunction(text, "static bool TryPrepareReconstructionImport");

        Assert.Contains("SendReconstructionImportFailure", prepare);
        Assert.Contains("\"code\"", text);
        Assert.Contains("\"message\"", text);
        Assert.Contains("\"retryable\"", text);
        Assert.DoesNotContain("CRookServer::SendError(", prepare);
    }

    [Fact]
    public void ReconstructionImport_DelegatesObjBundleStagingToManagedPrepare()
    {
        var text = File.ReadAllText(Path.Combine(
            RepoRoot,
            "src",
            "RookNative",
            "Handlers",
            "ImportExportHandler.cpp"));
        var handler = ExtractFunction(text, "void HandleReconstructionImport");

        Assert.Contains("body[\"import_id\"] = importId;", handler);
        Assert.DoesNotContain("StageReconstructionImportBundle", text);
        Assert.DoesNotContain("copy_file", handler);
    }

    [Fact]
    public void ReconstructionImport_RecordsStagedAndSourcePaths()
    {
        var text = File.ReadAllText(Path.Combine(
            RepoRoot,
            "src",
            "RookNative",
            "Handlers",
            "ImportExportHandler.cpp"));
        var handler = ExtractFunction(text, "void HandleReconstructionImport");

        Assert.Contains("{\"path\", importResult.data[\"path\"]}", handler);
        Assert.Contains("recordBody[\"source_path\"]", handler);
    }

    [Fact]
    public void ReconstructionImport_CleansPreparedBundleBeforePreRecordFailureReturns()
    {
        var text = File.ReadAllText(Path.Combine(
            RepoRoot,
            "src",
            "RookNative",
            "Handlers",
            "ImportExportHandler.cpp"));
        var handler = ExtractFunction(text, "void HandleReconstructionImport");

        Assert.Contains("CleanupPreparedReconstructionImport(plan);", handler);
        Assert.Contains("if (!importResult.data.contains(\"imported_ids\"))", handler);
        Assert.True(
            handler.IndexOf("CleanupPreparedReconstructionImport(plan);", System.StringComparison.Ordinal)
            < handler.IndexOf("if (!importResult.data.contains(\"imported_ids\"))", System.StringComparison.Ordinal),
            "Cleanup helper should be available before the pre-record failure branch.");
        var failureBranch = handler.Substring(handler.IndexOf("if (!importResult.data.contains(\"imported_ids\"))", System.StringComparison.Ordinal));
        Assert.Contains("CleanupPreparedReconstructionImport(plan);", failureBranch);
        Assert.True(
            failureBranch.IndexOf("CleanupPreparedReconstructionImport(plan);", System.StringComparison.Ordinal)
            < failureBranch.IndexOf("return;", System.StringComparison.Ordinal),
            "Pre-record import failure should cleanup before returning.");
    }

    [Fact]
    public void ReconstructionImport_CleansPreparedBundleBeforePostPrepareValidationReturns()
    {
        var text = File.ReadAllText(Path.Combine(
            RepoRoot,
            "src",
            "RookNative",
            "Handlers",
            "ImportExportHandler.cpp"));
        var handler = ExtractFunction(text, "void HandleReconstructionImport");

        AssertCleanupBeforeReturn(
            handler,
            "if (path.empty() || assetRole.empty())",
            "Malformed prepared import plan should cleanup before returning.");
        AssertCleanupBeforeReturn(
            handler,
            "if (!pathErr.empty() || !fs::exists(path))",
            "Invalid prepared import path should cleanup before returning.");
    }

    private static void AssertCleanupBeforeReturn(
        string handler,
        string branchStart,
        string message)
    {
        var branchIndex = handler.IndexOf(branchStart, System.StringComparison.Ordinal);
        Assert.True(branchIndex >= 0, $"Missing branch '{branchStart}'.");
        var branch = handler.Substring(branchIndex);
        var cleanupIndex = branch.IndexOf("CleanupPreparedReconstructionImport(plan);", System.StringComparison.Ordinal);
        var returnIndex = branch.IndexOf("return;", System.StringComparison.Ordinal);
        Assert.True(cleanupIndex >= 0, message);
        Assert.True(cleanupIndex < returnIndex, message);
    }

    [Fact]
    public void NativeBridge_RoutesImportPackageThroughAsyncDispatch()
    {
        // The deadlock invariant must hold on the native dispatch surface too:
        // OpImportPackage belongs in the ASYNC group (with submit/status/cancel),
        // not the off-UI group.
        var managed = File.ReadAllText(Path.Combine(
            RepoRoot, "src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs"));
        var fn = ExtractFunction(managed, "int HandleReconstructionDispatch(");

        var submitIdx = fn.IndexOf("case ReconstructionOpHandler.OpSubmit:", System.StringComparison.Ordinal);
        var asyncCallIdx = fn.IndexOf(
            "(reqJson, ct) => RookSubsystemRoot.Instance.Reconstruction.DispatchAsync",
            System.StringComparison.Ordinal);
        var importIdx = fn.IndexOf("case ReconstructionOpHandler.OpImportPackage:", System.StringComparison.Ordinal);

        Assert.True(importIdx >= 0, "OpImportPackage case not found in HandleReconstructionDispatch.");
        Assert.True(importIdx > submitIdx && importIdx < asyncCallIdx,
            "OpImportPackage must sit in the async dispatch branch (after OpSubmit, before the async DispatchAsync lambda).");
    }

    private static string ExtractFunction(string source, string signature)
    {
        var start = source.IndexOf(signature, System.StringComparison.Ordinal);
        Assert.True(start >= 0, $"Missing signature '{signature}'.");
        var brace = source.IndexOf('{', start);
        Assert.True(brace >= 0, $"Missing function body for '{signature}'.");

        var depth = 0;
        for (var i = brace; i < source.Length; i++)
        {
            if (source[i] == '{') depth++;
            else if (source[i] == '}')
            {
                depth--;
                if (depth == 0)
                    return source.Substring(start, i - start + 1);
            }
        }

        throw new System.InvalidOperationException($"Could not extract '{signature}'.");
    }

    private static string RepoRoot
        => Path.GetFullPath(Path.Combine(System.AppContext.BaseDirectory, "..", "..", "..", "..", ".."));
}
