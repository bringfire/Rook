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
/// modifying the source. The 3D provider result envelope yields no model artifacts for a BiRefNet
/// body, so this materializer reads the raw fal body preserved verbatim under the envelope's
/// <c>provider_result_json</c> key, maps it via <see cref="FalBirefnetResultMapper"/>
/// (<c>image</c> required, <c>mask</c> optional), downloads each asset through the disciplined
/// <see cref="IReconstructionRemoteAssetDownloader"/>, and writes a single artifact carrying the
/// <c>image</c> (and <c>mask</c>) role blobs.
///
/// <para>Mirrors <see cref="ReconstructionMaterializeResult"/> (the artifact lands in the same
/// <c>Package</c> field the manager reads <c>ResultArtifactId</c> from). A missing <c>image.url</c>
/// is a typed <see cref="GenerationError"/> failure, not a hollow artifact.</para>
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

        // The 3D MapArtifacts yields nothing for a BiRefNet body, so read the raw fal body the provider
        // preserved verbatim and map it through the bg-removal mapper.
        var rawBody = envelope.EnvelopeMetadata.TryGetValue("provider_result_json", out var pj)
            ? pj
            : new JsonObject();
        var artifacts = FalBirefnetResultMapper.MapArtifacts(rawBody);

        var hasImage = artifacts.Any(a => a.Role == "image");
        if (!hasImage)
            return new ReconstructionMaterializeResult(false, null, new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                "Background-removal result has no image asset (image.url).",
                Retryable: false));

        var blobs = new List<BlobInput>();
        foreach (var artifact in artifacts)
        {
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
            ReconstructionFileRoles.PreprocessedImage,
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
