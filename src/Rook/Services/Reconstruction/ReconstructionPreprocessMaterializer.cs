using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Reconstruction.Fal;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Reconstruction;

/// <summary>
/// Materializes a background-removal (preprocess) job's result into a derived
/// <c>preprocessed_image</c> artifact linked to its source (<c>parent_ids = [source]</c>) — never
/// modifying the source. The shared <see cref="FalReconstructionResultMapper"/> now recognizes the
/// BiRefNet body (<c>image</c> / <c>mask_image</c>), so the provider boundary already produced the
/// <c>image</c> (required) and <c>mask</c> (optional) role'd artifacts in the envelope. This
/// materializer consumes <c>envelope.Artifacts</c> directly (like
/// <see cref="ReconstructionPackageMaterializer"/>), downloads each remote asset through the
/// disciplined <see cref="IReconstructionRemoteAssetDownloader"/>, and writes a single
/// <c>preprocessed_image</c> artifact carrying the <c>image</c> (and <c>mask</c>) role blobs.
///
/// <para>Mirrors <see cref="ReconstructionMaterializeResult"/> (the artifact lands in the same
/// <c>Package</c> field the manager reads <c>ResultArtifactId</c> from). A missing <c>image</c>
/// artifact is a typed <see cref="GenerationError"/> failure, not a hollow artifact.</para>
/// </summary>
public sealed class ReconstructionPreprocessMaterializer
{
    private readonly ArtifactStore _store;
    private readonly IReconstructionRemoteAssetDownloader _downloader;

    public ReconstructionPreprocessMaterializer(
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

        // The shared mapper recognizes the BiRefNet body, so the provider boundary already produced the
        // image (required) + mask (optional) role'd artifacts. Consume them from the envelope directly.
        var hasImage = envelope.Artifacts.Any(a => a.Role == ReconstructionFileRoles.Image);
        if (!hasImage)
            return new ReconstructionMaterializeResult(false, null, new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                "Background-removal result contained no image asset.",
                Retryable: false));

        var blobs = new List<BlobInput>();
        foreach (var artifact in envelope.Artifacts)
        {
            if (artifact.Role != ReconstructionFileRoles.Image
                && artifact.Role != ReconstructionFileRoles.Mask)
                continue;
            if (blobs.Any(b => string.Equals(b.Role, artifact.Role, StringComparison.Ordinal)))
                continue;
            if (artifact.Body is not RemoteArtifactBody remote)
                continue;

            var download = await _downloader
                .DownloadAsync(remote.Url, artifact.Role, ct)
                .ConfigureAwait(false);
            if (!download.Success)
                return new ReconstructionMaterializeResult(false, null, download.Error);

            blobs.Add(new BlobInput(
                artifact.Role,
                download.Bytes!,
                ExtensionFor(download.MimeType)));
        }

        var metadata = new Dictionary<string, JsonNode?>
        {
            ["provider"] = JsonValue.Create(provider),
            ["model_id"] = JsonValue.Create(modelId),
            ["job_id"] = JsonValue.Create(jobId.ToString("D")),
            ["asset_roles"] = ToJsonArray(blobs.Select(b => b.Role)),
        };

        var artifactRecord = _store.Create(
            ReconstructionArtifactKinds.PreprocessedImage,
            blobs,
            parentIds: sourceArtifactIds,
            metadata: metadata);
        return new ReconstructionMaterializeResult(true, artifactRecord, null);
    }

    // Background-removal assets are always images (png/jpg/webp). Default to png when the download did
    // not declare an image MIME — BiRefNet emits PNG with alpha.
    private static string ExtensionFor(string? mimeType) => mimeType?.ToLowerInvariant() switch
    {
        "image/jpeg" => "jpg",
        "image/webp" => "webp",
        _ => "png",
    };

    private static JsonArray ToJsonArray(IEnumerable<string> values)
    {
        var array = new JsonArray();
        foreach (var value in values)
            array.Add(value);
        return array;
    }
}
