using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json.Nodes;
using Rook.Artifacts;

namespace Rook.Services.Reconstruction;

public interface IReconstructionFileDownloader
{
    byte[] Download(Uri uri);
}

public sealed class ReconstructionPackageMaterializer
{
    private readonly ArtifactStore _store;
    private readonly IReconstructionFileDownloader _downloader;

    public ReconstructionPackageMaterializer(
        ArtifactStore store,
        IReconstructionFileDownloader downloader)
    {
        _store = store ?? throw new ArgumentNullException(nameof(store));
        _downloader = downloader ?? throw new ArgumentNullException(nameof(downloader));
    }

    public Artifact Materialize(
        Guid jobId,
        IReadOnlyList<Guid> sourceArtifactIds,
        string provider,
        string modelId,
        JsonNode providerResultJson)
    {
        if (providerResultJson is null)
            throw new ArgumentNullException(nameof(providerResultJson));

        var blobs = new List<BlobInput>();
        AddProviderFiles(providerResultJson, blobs);

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

        return _store.Create(
            ReconstructionArtifactKinds.Package,
            blobs,
            parentIds: sourceArtifactIds,
            metadata: metadata);
    }

    private void AddProviderFiles(JsonNode providerResultJson, List<BlobInput> blobs)
    {
        var root = providerResultJson.AsObject();
        AddUrl(
            blobs,
            ReconstructionFileRoles.ModelGlb,
            ReadUrl(root["model_glb"]) ?? ReadUrl(Prop(root["model_urls"], "glb")));
        AddUrl(
            blobs,
            ReconstructionFileRoles.ModelObj,
            ReadUrl(root["model_obj"]) ?? ReadUrl(Prop(root["model_urls"], "obj")));
        AddUrl(
            blobs,
            ReconstructionFileRoles.MaterialMtl,
            ReadUrl(root["material_mtl"]) ?? ReadUrl(Prop(root["model_urls"], "mtl")));
        AddUrl(
            blobs,
            ReconstructionFileRoles.Texture,
            ReadUrl(root["texture"]) ?? ReadUrl(Prop(root["texture_urls"], "texture")));
        AddUrl(blobs, ReconstructionFileRoles.Thumbnail, ReadUrl(root["thumbnail"]));

        AddModelUrlFallbacks(root["model_urls"], blobs);
        AddTextureUrlFallbacks(root["texture_urls"], blobs);
    }

    private void AddModelUrlFallbacks(JsonNode? node, List<BlobInput> blobs)
    {
        foreach (var url in EnumerateUrls(node))
        {
            var role = RoleForModelUrl(url);
            if (role is not null)
                AddUrl(blobs, role, url);
        }
    }

    private void AddTextureUrlFallbacks(JsonNode? node, List<BlobInput> blobs)
    {
        foreach (var url in EnumerateUrls(node))
        {
            var role = RoleForTextureUrl(url);
            if (role is not null)
                AddUrl(blobs, role, url);
        }
    }

    private void AddUrl(List<BlobInput> blobs, string role, string? url)
    {
        if (string.IsNullOrWhiteSpace(url)) return;
        if (blobs.Any(b => string.Equals(b.Role, role, StringComparison.Ordinal))) return;

        var uri = new Uri(url, UriKind.Absolute);
        blobs.Add(new BlobInput(role, _downloader.Download(uri), ExtensionFor(uri, role)));
    }

    private static string? ReadUrl(JsonNode? node)
    {
        if (node is JsonValue value && value.TryGetValue<string>(out var text))
            return text;
        if (Prop(node, "url") is JsonValue url && url.TryGetValue<string>(out var nested))
            return nested;
        return null;
    }

    private static IEnumerable<string> EnumerateUrls(JsonNode? node)
    {
        if (node is JsonObject obj)
        {
            foreach (var kvp in obj)
            {
                var url = ReadUrl(kvp.Value);
                if (!string.IsNullOrWhiteSpace(url)) yield return url!;
            }
        }
        else if (node is JsonArray arr)
        {
            foreach (var item in arr)
            {
                var url = ReadUrl(item);
                if (!string.IsNullOrWhiteSpace(url)) yield return url!;
            }
        }
    }

    private static JsonNode? Prop(JsonNode? node, string name)
        => node is JsonObject obj && obj.TryGetPropertyValue(name, out var value)
            ? value
            : null;

    private static string? RoleForModelUrl(string url)
    {
        var ext = System.IO.Path.GetExtension(new Uri(url).AbsolutePath).ToLowerInvariant();
        return ext switch
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

    private static string? RoleForTextureUrl(string url)
    {
        var lower = new Uri(url).AbsolutePath.ToLowerInvariant();
        if (lower.Contains("normal")) return "texture_normal";
        if (lower.Contains("roughness")) return "texture_roughness";
        if (lower.Contains("metallic")) return "texture_metallic";
        if (lower.Contains("base") || lower.Contains("albedo") || lower.Contains("color"))
            return "texture_base_color";
        return ReconstructionFileRoles.Texture;
    }

    private static string ExtensionFor(Uri uri, string role)
    {
        var ext = System.IO.Path.GetExtension(uri.AbsolutePath)
            .TrimStart('.')
            .ToLowerInvariant();
        if (!string.IsNullOrWhiteSpace(ext)) return ext;
        if (role == ReconstructionFileRoles.MaterialMtl) return "mtl";
        if (role == ReconstructionFileRoles.ModelGlb) return "glb";
        if (role == ReconstructionFileRoles.ModelObj) return "obj";
        if (role == ReconstructionFileRoles.Thumbnail ||
            role.StartsWith("texture", StringComparison.Ordinal))
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
