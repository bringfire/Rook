using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Reconstruction.Fal;

/// <summary>
/// Maps a fal BiRefNet (background-removal) result body to role'd remote artifacts. The verified
/// fal-ai/birefnet/v2 output shape is <c>{ "image": { "url": ... }, "mask_image": { "url": ... } }</c>
/// where <c>image</c> is the background-removed image (required) and <c>mask_image</c> is the optional
/// alpha mask. <c>image.url</c> → role <c>image</c>; <c>mask_image.url</c> → role <c>mask</c>.
///
/// <para>Kept separate from <see cref="FalReconstructionResultMapper"/> (which maps the 3D-package
/// shape and is what the provider's <c>FetchResultAsync</c> runs). For bg-removal the 3D mapper yields
/// no model artifacts, so the preprocess materializer reads the raw body (preserved verbatim under
/// the envelope's <c>provider_result_json</c> key) and runs this mapper instead.</para>
/// </summary>
public static class FalBirefnetResultMapper
{
    /// <summary>
    /// Detect role'd remote artifacts from a BiRefNet result body. Returns the <c>image</c> artifact
    /// first (when an absolute http(s) url is present) and the <c>mask</c> artifact when present.
    /// Empty when no valid <c>image.url</c> is found — the caller treats that as a failure.
    /// </summary>
    public static IReadOnlyList<ResultArtifact> MapArtifacts(JsonNode resultJson)
    {
        if (resultJson is null) throw new ArgumentNullException(nameof(resultJson));

        var root = resultJson.AsObject();
        var artifacts = new List<ResultArtifact>();

        var image = ReadRemote("image", UrlFor(root, "image"));
        if (image is not null) artifacts.Add(image);

        var mask = ReadRemote("mask", UrlFor(root, "mask_image"));
        if (mask is not null) artifacts.Add(mask);

        return artifacts;
    }

    private static ResultArtifact? ReadRemote(string role, string? url)
    {
        if (string.IsNullOrWhiteSpace(url)) return null;
        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri)) return null;
        if (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps) return null;

        return new ResultArtifact(
            role,
            new RemoteArtifactBody(uri),
            null,
            new Dictionary<string, JsonNode>());
    }

    private static string? UrlFor(JsonObject root, string objectKey)
    {
        if (!root.TryGetPropertyValue(objectKey, out var node)) return null;
        if (node is not JsonObject obj) return null;
        if (!obj.TryGetPropertyValue("url", out var urlNode)) return null;
        return urlNode is JsonValue value && value.TryGetValue<string>(out var text) ? text : null;
    }
}
