using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Reconstruction.Fal;

/// <summary>
/// Production-owned mapper from a fal reconstruction result JSON body to the shared
/// <see cref="ProviderResultEnvelope"/>. ALL fal-result-shape knowledge — role detection,
/// <c>model_glb</c>-URL-ending-in-<c>.obj</c> normalization, texture subroles, provider
/// filenames/content-types, and per-asset extension derivation — lives here. It was formerly
/// embedded in <c>ReconstructionPackageMaterializer</c>; convergence moved fal-shape parsing to the
/// provider boundary. The provider's <c>FetchResultAsync</c> and any test that needs a package
/// fixture both go through this single seam, so behavior stays identical across the refactor.
///
/// <para>Each produced <see cref="ResultArtifact"/> carries a <c>RemoteArtifactBody</c> plus
/// <see cref="ResultArtifact.ProviderMetadata"/> entries (<c>file_extension</c>, and when present
/// <c>file_name</c>/<c>content_type</c>) so the materializer can name blobs exactly as the
/// pre-convergence code did. The raw result JSON is preserved verbatim by callers as
/// <c>provider_result_json</c> so the (untouched) import route keeps recovering original
/// provider filenames.</para>
/// </summary>
public static class FalReconstructionResultMapper
{
    /// <summary>
    /// Build a success envelope. Requires at least one recognizable asset (the envelope invariant);
    /// callers that may receive an empty result should call <see cref="MapArtifacts"/> and branch
    /// to a failure outcome before constructing the envelope.
    /// </summary>
    public static ProviderResultEnvelope ToEnvelope(JsonNode resultJson)
    {
        if (resultJson is null) throw new ArgumentNullException(nameof(resultJson));

        var artifacts = MapArtifacts(resultJson);
        var meta = new Dictionary<string, JsonNode>
        {
            ["provider_result_json"] = resultJson.DeepClone(),
        };
        return new ProviderResultEnvelope(artifacts, meta);
    }

    /// <summary>
    /// Detect role'd remote artifacts from a fal result body. First-writer-wins per role, ordered
    /// model_glb, model_obj, material_mtl, texture, thumbnail, then the BiRefNet image/mask, then
    /// model_urls fallbacks, then texture_urls fallbacks — matching the pre-convergence materializer
    /// exactly for 3D bodies (which carry no image/mask_image).
    /// </summary>
    public static IReadOnlyList<ResultArtifact> MapArtifacts(JsonNode resultJson)
    {
        if (resultJson is null) throw new ArgumentNullException(nameof(resultJson));

        var root = resultJson.AsObject();
        var byRole = new Dictionary<string, ResultArtifact>(StringComparer.Ordinal);
        var order = new List<string>();

        AddModel(byRole, order, ReconstructionFileRoles.ModelGlb,
            ReadFile(root["model_glb"]) ?? ReadFile(Prop(root["model_urls"], "glb")));
        AddModel(byRole, order, ReconstructionFileRoles.ModelObj,
            ReadFile(root["model_obj"]) ?? ReadFile(Prop(root["model_urls"], "obj")));
        AddModel(byRole, order, ReconstructionFileRoles.MaterialMtl,
            ReadFile(root["material_mtl"]) ?? ReadFile(Prop(root["model_urls"], "mtl")));

        // Classify the top-level `texture` field (not a generic role — run it through
        // ClassifyTextureRole so the mapper and the resolver agree on the stored role).
        var topTexture = ReadFile(root["texture"]);
        if (topTexture is not null)
            Add(byRole, order, ClassifyTextureRole(topTexture.FileName, topTexture.Url), topTexture);

        // model_urls.texture — classify for the same reason; first-writer-wins coalesces duplicates.
        var modelUrlsTexture = ReadFile(Prop(root["model_urls"], "texture"));
        if (modelUrlsTexture is not null)
            Add(byRole, order, ClassifyTextureRole(modelUrlsTexture.FileName, modelUrlsTexture.Url), modelUrlsTexture);

        Add(byRole, order, ReconstructionFileRoles.Thumbnail, ReadFile(root["thumbnail"]));

        // BiRefNet (background-removal) output. The verified fal-ai/birefnet/v2 shape is
        // { "image": { "url": ... }, "mask_image": { "url": ... } }: image is the background-removed
        // image and mask_image is the optional alpha mask. 3D bodies carry no top-level image/mask_image,
        // so this is inert for them.
        Add(byRole, order, ReconstructionFileRoles.Image, ReadFile(root["image"]));
        Add(byRole, order, ReconstructionFileRoles.Mask, ReadFile(root["mask_image"]));

        foreach (var file in EnumerateFiles(root["model_urls"]))
        {
            var role = RoleForModelFile(file);
            if (role is not null) Add(byRole, order, role, file);
        }

        foreach (var file in EnumerateFiles(root["texture_urls"]))
            Add(byRole, order, RoleForTextureFile(file), file);

        return order.Select(role => byRole[role]).ToList();
    }

    private static void AddModel(
        Dictionary<string, ResultArtifact> byRole,
        List<string> order,
        string fallbackRole,
        ProviderFile? file)
    {
        if (file is null || string.IsNullOrWhiteSpace(file.Url)) return;
        Add(byRole, order, RoleForModelFile(file) ?? fallbackRole, file);
    }

    private static void Add(
        Dictionary<string, ResultArtifact> byRole,
        List<string> order,
        string role,
        ProviderFile? file)
    {
        if (file is null || string.IsNullOrWhiteSpace(file.Url)) return;
        if (byRole.ContainsKey(role)) return;
        if (!Uri.TryCreate(file.Url, UriKind.Absolute, out var uri)) return;
        if (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps) return;

        var metadata = new Dictionary<string, JsonNode>
        {
            ["file_extension"] = ExtensionFor(file, role),
        };
        if (!string.IsNullOrWhiteSpace(file.FileName))
            metadata["file_name"] = file.FileName!;
        if (!string.IsNullOrWhiteSpace(file.ContentType))
            metadata["content_type"] = file.ContentType!;

        byRole[role] = new ResultArtifact(
            role,
            new RemoteArtifactBody(uri),
            string.IsNullOrWhiteSpace(file.ContentType) ? null : file.ContentType,
            metadata);
        order.Add(role);
    }

    private static ProviderFile? ReadFile(JsonNode? node)
    {
        if (node is JsonValue value && value.TryGetValue<string>(out var text))
            return new ProviderFile(text, null, null);
        if (node is JsonObject obj
            && Prop(obj, "url") is JsonValue url
            && url.TryGetValue<string>(out var nested))
        {
            return new ProviderFile(
                nested,
                ReadString(obj, "file_name"),
                ReadString(obj, "content_type"));
        }
        return null;
    }

    private static IEnumerable<ProviderFile> EnumerateFiles(JsonNode? node)
    {
        if (node is JsonObject obj)
        {
            foreach (var kvp in obj)
            {
                var file = ReadFile(kvp.Value);
                if (file is not null && !string.IsNullOrWhiteSpace(file.Url)) yield return file;
            }
        }
        else if (node is JsonArray arr)
        {
            foreach (var item in arr)
            {
                var file = ReadFile(item);
                if (file is not null && !string.IsNullOrWhiteSpace(file.Url)) yield return file;
            }
        }
    }

    private static JsonNode? Prop(JsonNode? node, string name)
        => node is JsonObject obj && obj.TryGetPropertyValue(name, out var value)
            ? value
            : null;

    private static string? ReadString(JsonNode? node, string name)
    {
        if (Prop(node, name) is JsonValue value && value.TryGetValue<string>(out var text))
            return text;
        return null;
    }

    private static string? RoleForModelFile(ProviderFile file)
    {
        return RoleForModelExtension(Path.GetExtension(file.FileName ?? string.Empty))
            ?? RoleForModelContentType(file.ContentType)
            ?? RoleForModelExtension(UrlExtension(file.Url));
    }

    private static string? RoleForModelExtension(string? extension)
    {
        return extension?.ToLowerInvariant() switch
        {
            ".glb" => ReconstructionFileRoles.ModelGlb,
            ".obj" => ReconstructionFileRoles.ModelObj,
            ".mtl" => ReconstructionFileRoles.MaterialMtl,
            ".fbx" => "model_fbx",
            ".usdz" => "model_usdz",
            ".stl" => "model_stl",
            _ => null,
        };
    }

    private static string? RoleForModelContentType(string? contentType)
    {
        return contentType?.ToLowerInvariant() switch
        {
            "model/gltf-binary" => ReconstructionFileRoles.ModelGlb,
            "model/obj" => ReconstructionFileRoles.ModelObj,
            "application/wavefront-obj" => ReconstructionFileRoles.ModelObj,
            "model/vnd.usdz+zip" => "model_usdz",
            _ => null,
        };
    }

    private static string RoleForTextureFile(ProviderFile file)
        => ClassifyTextureRole(file.FileName, file.Url);

    /// <summary>
    /// Classify a fal texture map to a detailed reconstruction role (texture_base_color,
    /// texture_normal, texture_roughness, texture_metallic) from its provider filename + URL path,
    /// falling back to the generic <see cref="ReconstructionFileRoles.Texture"/>. Shared with the import
    /// handler's provider-filename resolution so a detailed texture blob and its provider filename are
    /// keyed under the same role.
    /// </summary>
    public static string ClassifyTextureRole(string? fileName, string? url)
    {
        var lower = ((fileName ?? string.Empty) + " " + UrlPath(url ?? string.Empty)).ToLowerInvariant();
        if (lower.Contains("normal")) return "texture_normal";
        if (lower.Contains("roughness")) return "texture_roughness";
        if (lower.Contains("metallic")) return "texture_metallic";
        if (lower.Contains("base") || lower.Contains("albedo") || lower.Contains("color"))
            return "texture_base_color";
        return ReconstructionFileRoles.Texture;
    }

    private static string ExtensionFor(ProviderFile file, string role)
    {
        var ext = Path.GetExtension(file.FileName ?? string.Empty)
            .TrimStart('.')
            .ToLowerInvariant();
        if (!string.IsNullOrWhiteSpace(ext)) return ext;

        ext = UrlExtension(file.Url).TrimStart('.').ToLowerInvariant();
        if (!string.IsNullOrWhiteSpace(ext)) return ext;

        if (string.Equals(file.ContentType, "model/obj", StringComparison.OrdinalIgnoreCase)) return "obj";
        if (string.Equals(file.ContentType, "model/gltf-binary", StringComparison.OrdinalIgnoreCase)) return "glb";
        if (string.Equals(file.ContentType, "image/jpeg", StringComparison.OrdinalIgnoreCase)) return "jpg";
        if (string.Equals(file.ContentType, "image/png", StringComparison.OrdinalIgnoreCase)) return "png";
        if (role == ReconstructionFileRoles.MaterialMtl) return "mtl";
        if (role == ReconstructionFileRoles.ModelGlb) return "glb";
        if (role == ReconstructionFileRoles.ModelObj) return "obj";
        if (role == ReconstructionFileRoles.Thumbnail ||
            role.StartsWith("texture", StringComparison.Ordinal))
            return "png";
        return "bin";
    }

    private static string UrlExtension(string url)
        => Uri.TryCreate(url, UriKind.Absolute, out var uri)
            ? Path.GetExtension(uri.AbsolutePath)
            : string.Empty;

    private static string UrlPath(string url)
        => Uri.TryCreate(url, UriKind.Absolute, out var uri)
            ? uri.AbsolutePath
            : url;

    private sealed record ProviderFile(string Url, string? FileName, string? ContentType);
}
