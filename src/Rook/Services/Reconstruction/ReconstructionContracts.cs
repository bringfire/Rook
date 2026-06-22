using System.Collections.Generic;

namespace Rook.Services.Reconstruction;

public static class ReconstructionArtifactKinds
{
    public const string Package = "reconstruction_package";
    public const string PreprocessedImage = "preprocessed_image";

    public static readonly string[] DefaultSourceAllowlist =
    {
        "generated_image",
        "imported_image",
        "captured_viewport",
    };
}

public static class ReconstructionFileRoles
{
    public const string ModelGlb = "model_glb";
    public const string ModelObj = "model_obj";
    public const string MaterialMtl = "material_mtl";
    public const string Texture = "texture";
    public const string Thumbnail = "thumbnail";
    public const string SourceImage = "source_image";
    public const string Image = "image";
    public const string Mask = "mask";
    public const string PreprocessedImage = "preprocessed_image";
    public const string ProviderResultJson = "provider_result_json";
    public const string ImportManifest = "import_manifest";
}

public static class ReconstructionUserTextKeys
{
    public const string PackageId = "rook.reconstruction.package_id";
    public const string JobId = "rook.reconstruction.job_id";
    public const string ImportId = "rook.reconstruction.import_id";
    public const string AssetRole = "rook.reconstruction.asset_role";
}

public enum ReconstructionJobState
{
    Queued,
    Running,
    CancellationRequested,
    Cancelled,
    Complete,
    Error,
    Interrupted,
}

public enum ReconstructionJobStage
{
    Queued,
    Preprocessing,
    Submitting,
    Polling,
    Materializing,
    Complete,
    Error,
    Cancelled,
}

public sealed record ReconstructionWarning(
    string Code,
    string Message,
    IReadOnlyDictionary<string, object?>? Details = null);

public sealed record ReconstructionFailure(
    string Code,
    string Message,
    bool Retryable,
    string? Field,
    IReadOnlyDictionary<string, object?> Details);
