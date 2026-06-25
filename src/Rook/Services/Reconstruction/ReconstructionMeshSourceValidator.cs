using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Rook.Artifacts;

namespace Rook.Services.Reconstruction;

public sealed record ReconstructionMeshSourceValidationResult(
    string? ModelGlbAbsolutePath,
    Guid SourcePackageId,
    ReconstructionFailure? Failure)
{
    public bool Success => Failure is null;
}

public static class ReconstructionMeshSourceValidator
{
    public static ReconstructionMeshSourceValidationResult Validate(ArtifactStore store, Guid sourcePackageId)
    {
        var artifact = store.Get(sourcePackageId);
        if (artifact is null
            || !string.Equals(artifact.Kind, ReconstructionArtifactKinds.Package, StringComparison.Ordinal))
        {
            return Fail(sourcePackageId, "invalid_source_package",
                "source_package_id must reference an existing reconstruction_package.");
        }

        var hasGlb = artifact.Files.Any(f =>
            string.Equals(f.Role, ReconstructionFileRoles.ModelGlb, StringComparison.Ordinal));
        if (!hasGlb)
        {
            return Fail(sourcePackageId, "missing_model_glb",
                "source package has no model_glb; Smart Topology requires GLB input.");
        }

        var path = store.GetBlobAbsolutePath(sourcePackageId, ReconstructionFileRoles.ModelGlb);
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path) || new FileInfo(path).Length == 0)
        {
            return Fail(sourcePackageId, "invalid_source_package",
                "source package model_glb blob is empty or unreadable.");
        }

        return new ReconstructionMeshSourceValidationResult(path, sourcePackageId, null);
    }

    private static ReconstructionMeshSourceValidationResult Fail(Guid id, string code, string message)
        => new(null, id, new ReconstructionFailure(code, message, false, "source_package_id",
            new Dictionary<string, object?>(StringComparer.Ordinal)));
}
