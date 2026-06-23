using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Artifacts;
using Rook.Services.Reconstruction.Fal;

namespace Rook.Services.Reconstruction;

/// <summary>
/// Maps a fal <c>provider_result_json</c> to a role → original-provider-filename dictionary,
/// using the same <see cref="FalReconstructionResultMapper.ClassifyTextureRole"/> authority
/// as the result mapper. Both sites must assign the same role to the same provider texture file
/// so that <c>FileNameForRole(role)</c> resolves the MTL-referenced provider name (e.g.
/// <c>texture_pbr_v128_metallic.png</c>) instead of a blob-role-derived fallback.
/// </summary>
public static class ReconstructionProviderFileNames
{
    /// <summary>
    /// Build a role → provider-filename map from a parsed <c>provider_result_json</c>
    /// object and the artifact whose blobs are the reference set.
    /// </summary>
    public static Dictionary<string, string> ProviderFileNamesByRole(
        JsonObject providerResultJson,
        Artifact package)
    {
        if (providerResultJson is null) throw new ArgumentNullException(nameof(providerResultJson));
        if (package is null) throw new ArgumentNullException(nameof(package));

        var names = new Dictionary<string, string>(StringComparer.Ordinal);

        AddProviderFileName(names, package, ReconstructionFileRoles.ModelGlb,     providerResultJson["model_glb"],     normalizeModelRole: true);
        AddProviderFileName(names, package, ReconstructionFileRoles.ModelObj,     providerResultJson["model_obj"],     normalizeModelRole: true);
        AddProviderFileName(names, package, ReconstructionFileRoles.MaterialMtl,  providerResultJson["material_mtl"],  normalizeModelRole: true);
        AddProviderFileName(names, package, ReconstructionFileRoles.Thumbnail,    providerResultJson["thumbnail"],     normalizeModelRole: false);

        // Classify the top-level `texture` via the same authority as the result mapper —
        // NOT as a generic `texture` role. This is the load-bearing fix: the mapper now
        // stores the file under the classified role, so the resolver must key it the same way
        // or FileNameForRole misses and staging falls back to a role-derived blob name.
        var topTexture = ReadProviderFile(providerResultJson["texture"]);
        if (topTexture is not null)
        {
            var classifiedRole = FalReconstructionResultMapper.ClassifyTextureRole(topTexture.FileName, topTexture.Url);
            AddProviderFileName(names, package, classifiedRole, providerResultJson["texture"], normalizeModelRole: false);
        }

        if (providerResultJson["model_urls"] is JsonObject modelUrls)
        {
            foreach (var kvp in modelUrls)
            {
                // model_urls.texture: classify like the top-level texture, not as a model key.
                if (string.Equals(kvp.Key, "texture", StringComparison.Ordinal))
                {
                    var f = ReadProviderFile(kvp.Value);
                    if (f is not null)
                    {
                        var classifiedRole = FalReconstructionResultMapper.ClassifyTextureRole(f.FileName, f.Url);
                        AddProviderFileName(names, package, classifiedRole, kvp.Value, normalizeModelRole: false);
                    }
                    continue;
                }
                AddProviderFileName(names, package, FallbackRoleForModelUrlKey(kvp.Key), kvp.Value, normalizeModelRole: true);
            }
        }

        if (providerResultJson["texture_urls"] is JsonObject textureUrls)
        {
            foreach (var kvp in textureUrls)
            {
                // Detailed texture maps are stored by the result mapper under detailed roles via
                // FalReconstructionResultMapper.ClassifyTextureRole. Key the provider filename under
                // that SAME role so FileNameForRole resolves the real .mtl-referenced name (e.g.
                // albedo.png) instead of falling back to the blob role name (texture_base_color.png).
                var textureFile = ReadProviderFile(kvp.Value);
                if (textureFile is null) continue;
                var textureRole = FalReconstructionResultMapper.ClassifyTextureRole(
                    textureFile.FileName, textureFile.Url);
                AddProviderFileName(names, package, textureRole, kvp.Value, normalizeModelRole: false);
            }
        }

        return names;
    }

    private static void AddProviderFileName(
        Dictionary<string, string> names,
        Artifact package,
        string? fallbackRole,
        JsonNode? node,
        bool normalizeModelRole)
    {
        if (string.IsNullOrWhiteSpace(fallbackRole)) return;
        var file = ReadProviderFile(node);
        if (file is null) return;

        var role = normalizeModelRole
            ? RoleForProviderModelFile(file) ?? fallbackRole
            : fallbackRole;
        if (!HasRole(package, role) || names.ContainsKey(role)) return;

        var fileName = SafeProviderFileName(file.FileName)
            ?? SafeProviderUrlFileName(file.Url);
        if (!string.IsNullOrWhiteSpace(fileName))
            names[role] = fileName!;
    }

    private static ProviderFile? ReadProviderFile(JsonNode? node)
    {
        if (node is JsonValue value && value.TryGetValue<string>(out var url))
            return new ProviderFile(url, null, null);
        if (node is JsonObject obj
            && obj.TryGetPropertyValue("url", out var urlNode)
            && urlNode is JsonValue urlValue
            && urlValue.TryGetValue<string>(out var nestedUrl))
        {
            return new ProviderFile(
                nestedUrl,
                ReadString(obj, "file_name"),
                ReadString(obj, "content_type"));
        }
        return null;
    }

    private static string? FallbackRoleForModelUrlKey(string key)
        => key switch
        {
            "glb" => ReconstructionFileRoles.ModelGlb,
            "obj" => ReconstructionFileRoles.ModelObj,
            "mtl" => ReconstructionFileRoles.MaterialMtl,
            "fbx" => "model_fbx",
            "usdz" => "model_usdz",
            "stl" => "model_stl",
            _ => null,
        };

    private static string? RoleForProviderModelFile(ProviderFile file)
        => RoleForModelExtension(Path.GetExtension(file.FileName ?? string.Empty))
            ?? RoleForModelContentType(file.ContentType)
            ?? RoleForModelExtension(Path.GetExtension(new Uri(file.Url).AbsolutePath));

    private static string? RoleForModelExtension(string? extension)
        => extension?.ToLowerInvariant() switch
        {
            ".glb" => ReconstructionFileRoles.ModelGlb,
            ".obj" => ReconstructionFileRoles.ModelObj,
            ".mtl" => ReconstructionFileRoles.MaterialMtl,
            ".fbx" => "model_fbx",
            ".usdz" => "model_usdz",
            ".stl" => "model_stl",
            _ => null,
        };

    private static string? RoleForModelContentType(string? contentType)
        => contentType?.ToLowerInvariant() switch
        {
            "model/gltf-binary" => ReconstructionFileRoles.ModelGlb,
            "model/obj" => ReconstructionFileRoles.ModelObj,
            "application/wavefront-obj" => ReconstructionFileRoles.ModelObj,
            "model/vnd.usdz+zip" => "model_usdz",
            _ => null,
        };

    private static string? SafeProviderFileName(string? fileName)
    {
        if (string.IsNullOrWhiteSpace(fileName)) return null;
        var safe = Path.GetFileName(fileName);
        return string.IsNullOrWhiteSpace(safe) || safe == "." || safe == ".."
            ? null
            : safe;
    }

    private static string? SafeProviderUrlFileName(string? url)
    {
        if (string.IsNullOrWhiteSpace(url)
            || !Uri.TryCreate(url, UriKind.Absolute, out var uri))
        {
            return null;
        }
        return SafeProviderFileName(Uri.UnescapeDataString(Path.GetFileName(uri.AbsolutePath)));
    }

    // Trivial pure predicate — kept private here so the handler's copy (still referenced by
    // other handler call sites) is not disturbed. One-line duplication is fine.
    private static bool HasRole(Artifact artifact, string role)
        => artifact.Files.Any(f => string.Equals(f.Role, role, StringComparison.Ordinal));

    private static string? ReadString(JsonObject obj, string name)
        => obj.TryGetPropertyValue(name, out var node)
            && node is JsonValue value
            && value.TryGetValue<string>(out var text)
                ? text
                : null;

    private sealed record ProviderFile(string Url, string? FileName, string? ContentType);
}
