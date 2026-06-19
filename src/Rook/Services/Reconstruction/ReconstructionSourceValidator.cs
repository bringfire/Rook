using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using Rook.Artifacts;

namespace Rook.Services.Reconstruction;

public sealed record ReconstructionSourceValidationResult(
    bool Success,
    string? AbsolutePath,
    IReadOnlyList<ReconstructionWarning> Warnings,
    ReconstructionFailure? Failure);

public static class ReconstructionSourceValidator
{
    private const long MaxBytes = 8L * 1024L * 1024L;
    private static readonly HashSet<string> AllowedExtensions = new(
        new[] { ".png", ".jpg", ".jpeg", ".webp" },
        StringComparer.OrdinalIgnoreCase);
    private static readonly HashSet<string> AllowedKinds = new(
        ReconstructionArtifactKinds.DefaultSourceAllowlist,
        StringComparer.Ordinal);

    public static ReconstructionSourceValidationResult Validate(
        ArtifactStore store,
        Artifact artifact,
        string role)
    {
        if (!AllowedKinds.Contains(artifact.Kind))
        {
            return Fail(
                "invalid_source_artifact",
                $"Artifact kind '{artifact.Kind}' is not a supported reconstruction source.",
                "source_artifact_id");
        }

        if (string.Equals(
                artifact.Kind,
                ReconstructionArtifactKinds.Package,
                StringComparison.Ordinal))
        {
            return Fail(
                "invalid_source_artifact",
                "reconstruction_package artifacts are not valid v1 sources.",
                "source_artifact_id");
        }

        if (!artifact.Files.Any(f => string.Equals(f.Role, role, StringComparison.Ordinal)))
        {
            return Fail(
                "invalid_source_role",
                $"Source role '{role}' does not exist on artifact '{artifact.Id:D}'.",
                "source_role");
        }

        string path;
        try
        {
            path = store.GetBlobAbsolutePath(artifact.Id, role);
        }
        catch (Exception ex)
        {
            return Fail(
                "invalid_source_role",
                ex.Message,
                "source_role");
        }

        var extension = Path.GetExtension(path);
        if (!AllowedExtensions.Contains(extension))
        {
            return Fail(
                "invalid_source_file",
                "Source image must be PNG, JPEG, or WebP.",
                "source_role");
        }

        var length = new FileInfo(path).Length;
        if (length > MaxBytes)
        {
            return Fail(
                "invalid_source_file",
                "Source image exceeds the 8 MB v1 reconstruction limit.",
                "source_role");
        }

        var warnings = new List<ReconstructionWarning>();
        try
        {
            using var image = Image.FromFile(path);
            if (image.Width < 128 || image.Height < 128 || image.Width > 5000 || image.Height > 5000)
            {
                return Fail(
                    "invalid_source_dimensions",
                    "Source image dimensions must be between 128 and 5000 pixels.",
                    "source_role");
            }
        }
        catch (Exception ex)
        {
            warnings.Add(new ReconstructionWarning(
                "source_dimensions_unreadable",
                "Source image dimensions could not be read during cheap validation.",
                new Dictionary<string, object?> { ["error"] = ex.Message }));
        }

        return new ReconstructionSourceValidationResult(true, path, warnings, null);
    }

    private static ReconstructionSourceValidationResult Fail(
        string code,
        string message,
        string field)
        => new(
            false,
            null,
            Array.Empty<ReconstructionWarning>(),
            new ReconstructionFailure(
                code,
                message,
                false,
                field,
                new Dictionary<string, object?>()));
}
