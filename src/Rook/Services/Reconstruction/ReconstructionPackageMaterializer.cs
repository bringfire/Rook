using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Reconstruction;

public sealed record ReconstructionMaterializeResult(
    bool Success,
    Artifact? Package,
    GenerationError? Error);

/// <summary>
/// Provider-agnostic package materializer: consumes a shared <see cref="ProviderResultEnvelope"/>
/// (already-roled artifacts produced by the provider boundary), downloads each remote asset via the
/// disciplined <see cref="IReconstructionRemoteAssetDownloader"/>, and writes a
/// <c>reconstruction_package</c> artifact with the model/material/texture role blobs plus the
/// <c>provider_result_json</c> and <c>import_manifest</c> sidecars.
///
/// <para>Enforces the package invariant that at least one model asset (<c>model_glb</c> or
/// <c>model_obj</c>) is present — a thumbnail-only "success" is a failure, returned as a typed
/// <see cref="GenerationError"/> so the manager records a job error rather than a hollow package.</para>
/// </summary>
public sealed class ReconstructionPackageMaterializer
{
    private readonly ArtifactStore _store;
    private readonly IReconstructionRemoteAssetDownloader _downloader;

    public ReconstructionPackageMaterializer(
        ArtifactStore store,
        IReconstructionRemoteAssetDownloader downloader)
    {
        _store = store ?? throw new ArgumentNullException(nameof(store));
        _downloader = downloader ?? throw new ArgumentNullException(nameof(downloader));
    }

    public async Task<ReconstructionMaterializeResult> MaterializeAsync(
        Guid jobId,
        IReadOnlyList<Guid> sourceArtifactIds,
        string provider,
        string modelId,
        ProviderResultEnvelope envelope,
        CancellationToken ct)
    {
        if (envelope is null) throw new ArgumentNullException(nameof(envelope));

        var hasModel = envelope.Artifacts.Any(a =>
            a.Role == ReconstructionFileRoles.ModelGlb || a.Role == ReconstructionFileRoles.ModelObj);
        if (!hasModel)
            return new ReconstructionMaterializeResult(false, null, new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                "Reconstruction package has no model asset (model_glb or model_obj).",
                Retryable: false));

        var blobs = new List<BlobInput>();
        foreach (var artifact in envelope.Artifacts)
        {
            if (blobs.Any(b => string.Equals(b.Role, artifact.Role, StringComparison.Ordinal)))
                continue;

            switch (artifact.Body)
            {
                case RemoteArtifactBody remote:
                    var download = await _downloader
                        .DownloadAsync(remote.Url, artifact.Role, ct)
                        .ConfigureAwait(false);
                    if (!download.Success)
                        return new ReconstructionMaterializeResult(false, null, download.Error);
                    blobs.Add(new BlobInput(
                        artifact.Role,
                        download.Bytes!,
                        ExtensionFor(artifact, download.MimeType)));
                    break;

                case InlineArtifactBody inline:
                    blobs.Add(new BlobInput(
                        artifact.Role,
                        inline.Bytes,
                        ExtensionFor(artifact, artifact.DeclaredMimeType)));
                    break;
            }
        }

        var providerResultJson = envelope.EnvelopeMetadata.TryGetValue("provider_result_json", out var pj)
            ? pj
            : new JsonObject();

        blobs.Add(new BlobInput(
            ReconstructionFileRoles.ProviderResultJson,
            Encoding.UTF8.GetBytes(providerResultJson.ToJsonString()),
            "json"));

        blobs.Add(new BlobInput(
            ReconstructionFileRoles.ImportManifest,
            Encoding.UTF8.GetBytes(BuildInitialImportManifest().ToJsonString()),
            "json"));

        var metadata = new Dictionary<string, JsonNode?>
        {
            ["provider"] = JsonValue.Create(provider),
            ["model_id"] = JsonValue.Create(modelId),
            ["job_id"] = JsonValue.Create(jobId.ToString("D")),
            ["asset_roles"] = ToJsonArray(blobs.Select(b => b.Role)),
        };

        var package = _store.Create(
            ReconstructionArtifactKinds.Package,
            blobs,
            parentIds: sourceArtifactIds,
            metadata: metadata);
        return new ReconstructionMaterializeResult(true, package, null);
    }

    /// <summary>
    /// Resolves a downloaded asset's file extension. Prefers the provider-supplied
    /// <c>file_extension</c> hint (set by <c>FalReconstructionResultMapper</c> so blob naming exactly
    /// matches the pre-convergence behavior the import route depends on); falls back to the
    /// downloaded/declared MIME and finally a role default when an envelope was built without the
    /// mapper (e.g. directly in a test).
    /// </summary>
    private static string ExtensionFor(ResultArtifact artifact, string? mimeType)
    {
        if (artifact.ProviderMetadata.TryGetValue("file_extension", out var hint)
            && hint is JsonValue value
            && value.TryGetValue<string>(out var ext)
            && !string.IsNullOrWhiteSpace(ext))
        {
            return ext;
        }

        var mime = string.IsNullOrWhiteSpace(mimeType) ? artifact.DeclaredMimeType : mimeType;
        return mime?.ToLowerInvariant() switch
        {
            "model/gltf-binary" => "glb",
            "model/obj" => "obj",
            "application/wavefront-obj" => "obj",
            "image/png" => "png",
            "image/jpeg" => "jpg",
            _ => DefaultExtensionForRole(artifact.Role),
        };
    }

    private static string DefaultExtensionForRole(string role)
    {
        if (role == ReconstructionFileRoles.ModelGlb) return "glb";
        if (role == ReconstructionFileRoles.ModelObj) return "obj";
        if (role == ReconstructionFileRoles.MaterialMtl) return "mtl";
        if (role == ReconstructionFileRoles.Thumbnail
            || role.StartsWith("texture", StringComparison.Ordinal))
            return "png";
        return "bin";
    }

    private static JsonObject BuildInitialImportManifest()
        => new()
        {
            ["schema_version"] = 1,
            ["preferred_asset"] = ReconstructionFileRoles.ModelGlb,
            ["fallback_order"] = ToJsonArray(new[]
            {
                ReconstructionFileRoles.ModelGlb,
                ReconstructionFileRoles.ModelObj,
            }),
            ["asset_bindings"] = new JsonObject
            {
                [ReconstructionFileRoles.ModelObj] = new JsonObject
                {
                    ["companion_roles"] = ToJsonArray(new[]
                    {
                        ReconstructionFileRoles.MaterialMtl,
                        ReconstructionFileRoles.Texture,
                    }),
                },
            },
            ["placement"] = new JsonObject
            {
                ["mode"] = "document_default",
                ["transform"] = null,
                ["units_policy"] = "provider_default",
            },
            ["imports"] = new JsonArray(),
        };

    private static JsonArray ToJsonArray(IEnumerable<string> values)
    {
        var array = new JsonArray();
        foreach (var value in values)
            array.Add(value);
        return array;
    }
}
