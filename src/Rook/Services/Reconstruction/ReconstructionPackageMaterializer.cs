using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json.Nodes;
using Rook.Artifacts;

namespace Rook.Services.Reconstruction;

public interface IReconstructionFileDownloader
{
    byte[] Download(Uri uri);
}

public sealed class HttpReconstructionFileDownloader : IReconstructionFileDownloader
{
    private readonly HttpClient _client;

    public HttpReconstructionFileDownloader(HttpClient? client = null)
    {
        _client = client ?? new HttpClient { Timeout = TimeSpan.FromMinutes(5) };
    }

    public byte[] Download(Uri uri)
    {
        if (uri is null) throw new ArgumentNullException(nameof(uri));
        if (!uri.IsAbsoluteUri || uri.Scheme != Uri.UriSchemeHttps)
            throw new ArgumentException("Reconstruction download URI must be absolute HTTPS.", nameof(uri));

        return _client.GetByteArrayAsync(uri).GetAwaiter().GetResult();
    }
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
        AddModelFile(
            blobs,
            ReconstructionFileRoles.ModelGlb,
            ReadFile(root["model_glb"]) ?? ReadFile(Prop(root["model_urls"], "glb")));
        AddModelFile(
            blobs,
            ReconstructionFileRoles.ModelObj,
            ReadFile(root["model_obj"]) ?? ReadFile(Prop(root["model_urls"], "obj")));
        AddModelFile(
            blobs,
            ReconstructionFileRoles.MaterialMtl,
            ReadFile(root["material_mtl"]) ?? ReadFile(Prop(root["model_urls"], "mtl")));
        AddFile(
            blobs,
            ReconstructionFileRoles.Texture,
            ReadFile(root["texture"]) ?? ReadFile(Prop(root["texture_urls"], "texture")));
        AddFile(blobs, ReconstructionFileRoles.Thumbnail, ReadFile(root["thumbnail"]));

        AddModelFileFallbacks(root["model_urls"], blobs);
        AddTextureFileFallbacks(root["texture_urls"], blobs);
    }

    private void AddModelFileFallbacks(JsonNode? node, List<BlobInput> blobs)
    {
        foreach (var file in EnumerateFiles(node))
        {
            var role = RoleForModelFile(file);
            if (role is not null)
                AddFile(blobs, role, file);
        }
    }

    private void AddModelFile(List<BlobInput> blobs, string fallbackRole, ProviderFile? file)
    {
        if (file is null || string.IsNullOrWhiteSpace(file.Url)) return;
        AddFile(blobs, RoleForModelFile(file) ?? fallbackRole, file);
    }

    private void AddTextureFileFallbacks(JsonNode? node, List<BlobInput> blobs)
    {
        foreach (var file in EnumerateFiles(node))
        {
            var role = RoleForTextureFile(file);
            if (role is not null)
                AddFile(blobs, role, file);
        }
    }

    private void AddFile(List<BlobInput> blobs, string role, ProviderFile? file)
    {
        if (file is null || string.IsNullOrWhiteSpace(file.Url)) return;
        if (blobs.Any(b => string.Equals(b.Role, role, StringComparison.Ordinal))) return;

        var uri = new Uri(file.Url, UriKind.Absolute);
        blobs.Add(new BlobInput(role, _downloader.Download(uri), ExtensionFor(file, role)));
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
        return RoleForModelExtension(System.IO.Path.GetExtension(file.FileName ?? string.Empty))
            ?? RoleForModelContentType(file.ContentType)
            ?? RoleForModelExtension(System.IO.Path.GetExtension(new Uri(file.Url).AbsolutePath));
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

    private static string? RoleForTextureFile(ProviderFile file)
    {
        var lower = ((file.FileName ?? string.Empty) + " " + new Uri(file.Url).AbsolutePath).ToLowerInvariant();
        if (lower.Contains("normal")) return "texture_normal";
        if (lower.Contains("roughness")) return "texture_roughness";
        if (lower.Contains("metallic")) return "texture_metallic";
        if (lower.Contains("base") || lower.Contains("albedo") || lower.Contains("color"))
            return "texture_base_color";
        return ReconstructionFileRoles.Texture;
    }

    private static string ExtensionFor(ProviderFile file, string role)
    {
        var ext = System.IO.Path.GetExtension(file.FileName ?? string.Empty)
            .TrimStart('.')
            .ToLowerInvariant();
        if (!string.IsNullOrWhiteSpace(ext)) return ext;

        ext = System.IO.Path.GetExtension(new Uri(file.Url).AbsolutePath)
            .TrimStart('.')
            .ToLowerInvariant();
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

    private sealed record ProviderFile(string Url, string? FileName, string? ContentType);

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
