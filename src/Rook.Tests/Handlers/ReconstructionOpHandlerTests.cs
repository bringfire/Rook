using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Reconstruction;
using Rook.Services.Reconstruction.Fal;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Handlers;

public sealed class ReconstructionOpHandlerTests : IDisposable
{
    private const string HunyuanModelId = "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d";

    private readonly List<string> _roots = new();
    private readonly List<ReconstructionJobManager> _managers = new();

    public static IEnumerable<object[]> StatusForMappings() => new[]
    {
        // typed failures map to specific non-500 statuses
        new object[] { ReconstructionErrorMapping.MissingCredentialFailure(), 400 },
        new object[] { MappedFailure(GenerationErrorCode.QuotaExceeded), 429 },
        new object[] { MappedFailure(GenerationErrorCode.DependencyUnavailable), 503 },
        new object[] { MappedFailure(GenerationErrorCode.ContentPolicy), 422 },
        // guards: an existing 400 arm stays 400; the default arm stays 500
        new object[] { MappedFailure(GenerationErrorCode.InvalidRequest), 400 },
        new object[] { MappedFailure(GenerationErrorCode.ExecutionFailed), 500 }, // -> provider_failed
    };

    private static ReconstructionFailure MappedFailure(GenerationErrorCode code)
        => ReconstructionErrorMapping.ToFailure(new GenerationError(code, "x", Retryable: false));

    [Theory]
    [MemberData(nameof(StatusForMappings))]
    public void StatusFor_MapsTypedFailureToHttpStatus(ReconstructionFailure failure, int expected)
    {
        Assert.Equal(expected, ReconstructionOpHandler.StatusFor(failure));
    }

    public void Dispose()
    {
        // Drain background loops BEFORE deleting the temp dirs they write into.
        foreach (var manager in _managers)
        {
            try { manager.Dispose(); }
            catch { /* idempotent best-effort teardown */ }
        }

        foreach (var root in _roots)
        {
            if (Directory.Exists(root))
                Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task DispatchAsync_Models_ReturnsDefaultStableCatalog()
    {
        var fixture = CreateFixture();

        var response = await fixture.Handler.DispatchAsync(
            @"{""op"":""models""}",
            CancellationToken.None);

        Assert.True(response.Success);
        var json = JsonSerializer.Serialize(response.Data);
        Assert.Contains(HunyuanModelId, json);
        Assert.DoesNotContain("fal-ai/meshy/v6/image-to-3d", json);
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        Assert.False(Assert.IsType<bool>(data["include_experimental"]));
        Assert.False(Assert.IsType<bool>(data["include_hidden"]));
        Assert.Empty(Assert.IsAssignableFrom<object[]>(data["warnings"]));
    }

    [Fact]
    public async Task Models_ExposesOptionsAndCapabilityFlags_ForPro()
    {
        var fixture = CreateFixture();
        var response = await fixture.Handler.DispatchAsync(
            @"{""op"":""models"",""include_experimental"":true}", CancellationToken.None);

        Assert.True(response.Success);
        var json = JsonSerializer.Serialize(response.Data);
        Assert.Contains("fal-ai/hunyuan-3d/v3.1/pro/image-to-3d", json);
        Assert.Contains("\"supports_multi_view\":true", json);
        Assert.Contains("\"supports_single_image\":true", json);
        Assert.Contains("\"generate_type\"", json);
        Assert.Contains("\"allowed_values\"", json);
        Assert.Contains("\"face_count\"", json);
    }

    [Fact]
    public async Task Models_BirefnetExcluded_ByCapabilityFilter()
    {
        var fixture = CreateFixture();
        var response = await fixture.Handler.DispatchAsync(
            @"{""op"":""models"",""include_experimental"":true,""include_hidden"":true}", CancellationToken.None);

        var json = JsonSerializer.Serialize(response.Data);
        Assert.DoesNotContain("fal-ai/birefnet/v2", json);   // no model_glb/model_obj role
    }

    [Fact]
    public async Task DispatchAsync_SubmitMissingSource_ReturnsStructuredFailure()
    {
        var fixture = CreateFixture();

        var response = await fixture.Handler.DispatchAsync(
            @"{""op"":""submit_job""}",
            CancellationToken.None);

        Assert.False(response.Success);
        Assert.Equal(400, response.HttpStatus);
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        Assert.Equal("invalid_request", data["code"]);
        Assert.Equal("source_artifact_id", data["field"]);
    }

    [Fact]
    public async Task DispatchOffUi_PrepareImport_ResolvesPreferredAssetPath()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 1, 2, 3 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_urls": {
            "glb": {"url": "https://example.test/model.glb"}
          }
        }
        """)!);

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"prepare_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            "\"import_id\":\"cccccccc-cccc-cccc-cccc-cccccccccccc\"" +
            "}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        Assert.Equal("model_glb", data["asset_role"]);
        Assert.EndsWith("model_glb.glb", Assert.IsType<string>(data["path"]));
    }

    [Fact]
    public async Task DispatchOffUi_PrepareImport_GlbWithTextureCarriesMaterialRepair()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 1, 2, 3 };
        fixture.Downloader.Files["https://example.test/texture.png"] = new byte[] { 7, 8, 9 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_urls": {
            "glb": {"url": "https://example.test/model.glb"}
          },
          "texture": {"url": "https://example.test/texture.png", "file_name": "texture_20250901.png"}
        }
        """)!);

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"prepare_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            "\"import_id\":\"cccccccc-cccc-cccc-cccc-cccccccccccc\"" +
            "}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        Assert.Equal("model_glb", data["asset_role"]);
        var repair = Assert.IsType<Dictionary<string, object?>>(data["material_repair"]);
        Assert.Equal("Rook Reconstruction cccccccc", repair["material_name"]);
        var maps = Assert.IsAssignableFrom<IReadOnlyList<object?>>(repair["maps"]);
        var baseMap = Assert.IsType<Dictionary<string, object?>>(Assert.Single(maps));
        Assert.Equal("base_color", baseMap["channel"]);
        Assert.Equal("texture", baseMap["role"]);
        Assert.Equal("texture_20250901.png", baseMap["file_name"]);
        Assert.EndsWith("texture.png", Assert.IsType<string>(baseMap["path"]));
    }

    [Fact]
    public async Task DispatchOffUi_PrepareImport_AppendsNormalMapWhenPresent()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/m.glb"] = new byte[] { 1, 2, 3 };
        fixture.Downloader.Files["https://example.test/base.png"] = new byte[] { 4, 5, 6 };
        fixture.Downloader.Files["https://example.test/normal.png"] = new byte[] { 7, 8, 9 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_glb": {"url": "https://example.test/m.glb"},
          "texture_urls": [
            {
              "base_color": {"url": "https://example.test/base.png", "file_name": "texture_0.png"},
              "normal":     {"url": "https://example.test/normal.png", "file_name": "texture_0_normal.png"},
              "metallic":   null,
              "roughness":  null
            }
          ]
        }
        """)!);

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"prepare_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            "\"import_id\":\"cccccccc-cccc-cccc-cccc-cccccccccccc\"" +
            "}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        var repair = Assert.IsType<Dictionary<string, object?>>(data["material_repair"]);
        var maps = Assert.IsAssignableFrom<IReadOnlyList<object?>>(repair["maps"]);
        Assert.Equal(2, maps.Count);

        var baseMap = Assert.IsType<Dictionary<string, object?>>(maps[0]);
        Assert.Equal("base_color", baseMap["channel"]);
        Assert.Equal("texture_base_color", baseMap["role"]);

        var normalMap = Assert.IsType<Dictionary<string, object?>>(maps[1]);
        Assert.Equal("normal", normalMap["channel"]);
        Assert.Equal("texture_normal", normalMap["role"]);
        // file_name falls back to the role-named blob: ProviderFileNamesByRole does not surface
        // the slot-normal's original provider name, and FileNameForRole derives it from the path.
        // The field is informational; native material binding uses `path`, not `file_name`.
        Assert.Equal("texture_normal.png", normalMap["file_name"]);
        Assert.EndsWith("texture_normal.png", Assert.IsType<string>(normalMap["path"]));
    }

    [Fact]
    public async Task DispatchOffUi_PrepareImport_AppendsAllPbrMapsWhenPresent()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/m.glb"] = new byte[] { 1, 2, 3 };
        fixture.Downloader.Files["https://example.test/base.png"] = new byte[] { 4, 5, 6 };
        fixture.Downloader.Files["https://example.test/normal.png"] = new byte[] { 7, 8, 9 };
        fixture.Downloader.Files["https://example.test/rough.png"] = new byte[] { 10, 11, 12 };
        fixture.Downloader.Files["https://example.test/metal.png"] = new byte[] { 13, 14, 15 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_glb": {"url": "https://example.test/m.glb"},
          "texture_urls": [
            {
              "base_color": {"url": "https://example.test/base.png",   "file_name": "texture_0.png"},
              "normal":     {"url": "https://example.test/normal.png", "file_name": "texture_0_normal.png"},
              "roughness":  {"url": "https://example.test/rough.png",  "file_name": "texture_0_roughness.png"},
              "metallic":   {"url": "https://example.test/metal.png",  "file_name": "texture_0_metallic.png"}
            }
          ]
        }
        """)!);

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"prepare_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            "\"import_id\":\"cccccccc-cccc-cccc-cccc-cccccccccccc\"" +
            "}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        var repair = Assert.IsType<Dictionary<string, object?>>(data["material_repair"]);
        var maps = Assert.IsAssignableFrom<IReadOnlyList<object?>>(repair["maps"]);
        Assert.Equal(4, maps.Count);

        var expected = new[]
        {
            ("base_color", "texture_base_color"),
            ("normal",     "texture_normal"),
            ("roughness",  "texture_roughness"),
            ("metallic",   "texture_metallic"),
        };
        for (var i = 0; i < expected.Length; i++)
        {
            var entry = Assert.IsType<Dictionary<string, object?>>(maps[i]);
            Assert.Equal(expected[i].Item1, entry["channel"]);
            Assert.Equal(expected[i].Item2, entry["role"]);
        }
    }

    [Fact]
    public async Task DispatchOffUi_PrepareImport_NoBaseColorYieldsNoMaterialRepair()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/m.glb"] = new byte[] { 1, 2, 3 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        { "model_glb": {"url": "https://example.test/m.glb"} }
        """)!);

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"prepare_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            "\"import_id\":\"cccccccc-cccc-cccc-cccc-cccccccccccc\"" +
            "}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        Assert.False(data.ContainsKey("material_repair"));
    }

    [Fact]
    public async Task DispatchOffUi_PrepareImport_DefaultFallsBackToObjWithCompanions()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.obj"] = new byte[] { 1, 2, 3 };
        fixture.Downloader.Files["https://example.test/material.mtl"] = new byte[] { 4, 5, 6 };
        fixture.Downloader.Files["https://example.test/texture.png"] = new byte[] { 7, 8, 9 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_urls": {
            "obj": {"url": "https://example.test/model.obj"},
            "mtl": {"url": "https://example.test/material.mtl"}
          },
          "texture": {"url": "https://example.test/texture.png"}
        }
        """)!);

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"prepare_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            "\"import_id\":\"cccccccc-cccc-cccc-cccc-cccccccccccc\"" +
            "}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        Assert.Equal("model_obj", data["asset_role"]);
        Assert.Equal("model.obj", data["file_name"]);
        var importPath = Assert.IsType<string>(data["path"]);
        Assert.EndsWith(
            Path.Combine("import_bundle_cccccccccccccccccccccccccccccccc", "model.obj"),
            importPath);
        Assert.EndsWith("model_obj.obj", Assert.IsType<string>(data["source_path"]));
        var companions = Assert.IsAssignableFrom<object[]>(data["companion_files"]);
        Assert.Equal(2, companions.Length);
        var material = Assert.Single(
            companions.Select(item => Assert.IsType<Dictionary<string, object?>>(item)),
            item => item["role"]?.Equals("material_mtl") == true);
        var texture = Assert.Single(
            companions.Select(item => Assert.IsType<Dictionary<string, object?>>(item)),
            item => item["role"]?.Equals("texture") == true);
        Assert.Equal("material.mtl", material["file_name"]);
        Assert.Equal("texture.png", texture["file_name"]);
        Assert.True(File.Exists(importPath));
        Assert.True(File.Exists(Path.Combine(Path.GetDirectoryName(importPath)!, "material.mtl")));
        Assert.True(File.Exists(Path.Combine(Path.GetDirectoryName(importPath)!, "texture.png")));
    }

    [Fact]
    public async Task DispatchOffUi_PrepareImport_StagesDetailedTextureRolesForObj()
    {
        // PBR packages carry detailed texture roles (texture_base_color, texture_normal, …) but no
        // generic `texture` blob. The OBJ companion set must still include those images, or the model
        // imports without its maps.
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.obj"] = new byte[] { 1, 2, 3 };
        fixture.Downloader.Files["https://example.test/material.mtl"] = new byte[] { 4, 5, 6 };
        fixture.Downloader.Files["https://example.test/base_color.png"] = new byte[] { 7, 8, 9 };
        fixture.Downloader.Files["https://example.test/normal.png"] = new byte[] { 10, 11, 12 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_urls": {
            "obj": {"url": "https://example.test/model.obj"},
            "mtl": {"url": "https://example.test/material.mtl"}
          },
          "texture_urls": {
            "base_color": {"url": "https://example.test/base_color.png"},
            "normal": {"url": "https://example.test/normal.png"}
          }
        }
        """)!);

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"prepare_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            "\"import_id\":\"ffffffff-ffff-ffff-ffff-ffffffffffff\"" +
            "}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        Assert.Equal("model_obj", data["asset_role"]);
        var companions = Assert.IsAssignableFrom<object[]>(data["companion_files"])
            .Select(item => Assert.IsType<Dictionary<string, object?>>(item))
            .ToList();
        Assert.Contains(companions, c => c["role"]?.Equals("material_mtl") == true);
        Assert.Contains(companions, c => c["role"]?.Equals("texture_base_color") == true);
        Assert.Contains(companions, c => c["role"]?.Equals("texture_normal") == true);

        // every companion is physically staged next to the OBJ under its returned file name
        var importPath = Assert.IsType<string>(data["path"]);
        var bundleDir = Path.GetDirectoryName(importPath)!;
        foreach (var companion in companions)
            Assert.True(File.Exists(Path.Combine(bundleDir, Assert.IsType<string>(companion["file_name"]))));
    }

    [Fact]
    public async Task DispatchOffUi_PrepareImport_PreservesDetailedTextureProviderFilename()
    {
        // The .mtl references the provider's texture filename (e.g. albedo.png). The staged companion
        // for a detailed texture role must carry that provider filename, not the blob role name
        // (texture_base_color.png), or the OBJ imports with the image present but unresolved.
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.obj"] = new byte[] { 1, 2, 3 };
        fixture.Downloader.Files["https://example.test/material.mtl"] = new byte[] { 4, 5, 6 };
        fixture.Downloader.Files["https://cdn.example.test/download?id=base"] = new byte[] { 7, 8, 9 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_urls": {
            "obj": {"url": "https://example.test/model.obj"},
            "mtl": {"url": "https://example.test/material.mtl"}
          },
          "texture_urls": {
            "base_color": {"url": "https://cdn.example.test/download?id=base", "file_name": "albedo.png"}
          }
        }
        """)!);

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"prepare_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            "\"import_id\":\"ffffffff-ffff-ffff-ffff-ffffffffffff\"" +
            "}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        var companions = Assert.IsAssignableFrom<object[]>(data["companion_files"])
            .Select(item => Assert.IsType<Dictionary<string, object?>>(item))
            .ToList();
        var baseColor = Assert.Single(companions, c => c["role"]?.Equals("texture_base_color") == true);
        Assert.Equal("albedo.png", baseColor["file_name"]);   // provider filename, not the blob role name

        var importPath = Assert.IsType<string>(data["path"]);
        Assert.True(File.Exists(Path.Combine(Path.GetDirectoryName(importPath)!, "albedo.png")));
    }

    [Fact]
    public async Task DispatchOffUi_PrepareImport_RootModelGlbObjDoesNotMasqueradeAsGlb()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/hunyuan.obj"] = new byte[] { 1, 2, 3 };
        fixture.Downloader.Files["https://example.test/material.mtl"] = new byte[] { 4, 5, 6 };
        fixture.Downloader.Files["https://example.test/texture.png"] = new byte[] { 7, 8, 9 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_glb": {"url": "https://example.test/hunyuan.obj"},
          "model_urls": {
            "mtl": {"url": "https://example.test/material.mtl"}
          },
          "texture": {"url": "https://example.test/texture.png"}
        }
        """)!);

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"prepare_import\"," +
            $"\"package_id\":\"{package.Id}\"" +
            "}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        Assert.Equal("model_obj", data["asset_role"]);
        var companions = Assert.IsAssignableFrom<object[]>(data["companion_files"]);
        Assert.Equal(2, companions.Length);
    }

    [Fact]
    public async Task DispatchOffUi_PrepareImport_ObjFilenameCollisionFailsAndCleansBundle()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.obj"] = new byte[] { 1, 2, 3 };
        fixture.Downloader.Files["https://example.test/material.mtl"] = new byte[] { 4, 5, 6 };
        fixture.Downloader.Files["https://example.test/texture.png"] = new byte[] { 7, 8, 9 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_urls": {
            "obj": {"url": "https://example.test/model.obj"},
            "mtl": {"url": "https://example.test/material.mtl", "file_name": "shared-name.dat"}
          },
          "texture": {"url": "https://example.test/texture.png", "file_name": "shared-name.dat"}
        }
        """)!);

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"prepare_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            "\"import_id\":\"dddddddd-dddd-dddd-dddd-dddddddddddd\"" +
            "}");

        Assert.False(response.Success);
        Assert.Equal(400, response.HttpStatus);
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        Assert.Equal("filename_collision", data["code"]);
        Assert.False(Assert.IsType<bool>(data["retryable"]));
        var bundleDir = Path.Combine(
            Path.GetDirectoryName(fixture.Store.GetBlobAbsolutePath(package.Id, ReconstructionFileRoles.ModelObj))!,
            "import_bundle_dddddddddddddddddddddddddddddddd");
        Assert.False(Directory.Exists(bundleDir));
    }

    [Fact]
    public async Task DispatchOffUi_CleanupPreparedImport_RemovesPreparedObjBundle()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.obj"] = new byte[] { 1, 2, 3 };
        fixture.Downloader.Files["https://example.test/material.mtl"] = new byte[] { 4, 5, 6 };
        fixture.Downloader.Files["https://example.test/texture.png"] = new byte[] { 7, 8, 9 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_urls": {
            "obj": {"url": "https://example.test/model.obj"},
            "mtl": {"url": "https://example.test/material.mtl"}
          },
          "texture": {"url": "https://example.test/texture.png"}
        }
        """)!);
        const string importId = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee";
        var prepare = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"prepare_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            $"\"import_id\":\"{importId}\"" +
            "}");
        Assert.True(prepare.Success, JsonSerializer.Serialize(prepare.Data));
        var prepareData = Assert.IsType<Dictionary<string, object?>>(prepare.Data);
        var importPath = Assert.IsType<string>(prepareData["path"]);
        var bundleDir = Path.GetDirectoryName(importPath)!;
        Assert.True(Directory.Exists(bundleDir));

        var cleanup = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"cleanup_prepared_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            $"\"import_id\":\"{importId}\"," +
            $"\"path\":{JsonSerializer.Serialize(importPath)}" +
            "}");

        Assert.True(cleanup.Success, JsonSerializer.Serialize(cleanup.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(cleanup.Data);
        Assert.Equal(package.Id.ToString("D"), data["package_id"]);
        Assert.Equal(importId, data["import_id"]);
        Assert.True(Assert.IsType<bool>(data["removed"]));
        Assert.False(Directory.Exists(bundleDir));
    }

    [Fact]
    public async Task DispatchOffUi_CleanupPreparedImport_RejectsPathOutsideExpectedBundle()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.obj"] = new byte[] { 1, 2, 3 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_urls": {
            "obj": {"url": "https://example.test/model.obj"}
          }
        }
        """)!);
        var modelPath = fixture.Store.GetBlobAbsolutePath(package.Id, ReconstructionFileRoles.ModelObj);

        var cleanup = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"cleanup_prepared_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            "\"import_id\":\"eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee\"," +
            $"\"path\":{JsonSerializer.Serialize(modelPath)}" +
            "}");

        Assert.False(cleanup.Success);
        Assert.Equal(400, cleanup.HttpStatus);
        var data = Assert.IsType<Dictionary<string, object?>>(cleanup.Data);
        Assert.Equal("invalid_request", data["code"]);
        Assert.False(Assert.IsType<bool>(data["retryable"]));
    }

    [Fact]
    public async Task DispatchOffUi_PrepareImport_AllowsExplicitObjDebugOverride()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.obj"] = new byte[] { 1, 2, 3 };
        fixture.Downloader.Files["https://example.test/material.mtl"] = new byte[] { 4, 5, 6 };
        fixture.Downloader.Files["https://example.test/texture.png"] = new byte[] { 7, 8, 9 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_urls": {
            "obj": {"url": "https://example.test/model.obj"},
            "mtl": {"url": "https://example.test/material.mtl"}
          },
          "texture": {"url": "https://example.test/texture.png"}
        }
        """)!);

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"prepare_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            "\"assetRole\":\"model_obj\"" +
            "}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        Assert.Equal("model_obj", data["asset_role"]);
        Assert.Equal(2, Assert.IsAssignableFrom<object[]>(data["companion_files"]).Length);
    }

    [Fact]
    public async Task DispatchAsync_Status_PollsAndReturnsWrappedJob()
    {
        var fixture = CreateFixture();
        fixture.Provider.StatusComplete.Enqueue(true);
        fixture.Provider.ResultJson = JsonNode.Parse("""
        {
          "model_urls": {
            "glb": {"url": "https://example.test/model.glb"}
          }
        }
        """)!;
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 1, 2, 3 };
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var submit = await fixture.Handler.DispatchAsync(
            "{" +
            $"\"op\":\"submit_job\",\"source_artifact_id\":\"{source.Id}\"," +
            $"\"model_id\":\"{HunyuanModelId}\"" +
            "}",
            CancellationToken.None);
        var submitData = Assert.IsType<Dictionary<string, object?>>(submit.Data);

        var response = await fixture.Handler.DispatchAsync(
            "{" +
            "\"op\":\"job_status\"," +
            $"\"job_id\":\"{submitData["job_id"]}\"" +
            "}",
            CancellationToken.None);

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        var job = Assert.IsType<Dictionary<string, object?>>(data["job"]);
        Assert.Equal("complete", job["state"]);
        Assert.True(Assert.IsType<bool>(data["result_available"]));
        Assert.Empty(Assert.IsAssignableFrom<object[]>(data["warnings"]));
        Assert.Equal(new[] { "req-123" }, fixture.Provider.ResultCalls);
    }

    [Fact]
    public async Task DispatchOffUi_Result_ReturnsCompactPackageSummary()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 1, 2, 3 };
        var jobId = Guid.NewGuid();
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_urls": {
            "glb": {"url": "https://example.test/model.glb"}
          }
        }
        """)!, jobId);
        fixture.Ledger.Append(ReconstructionJobLedgerRecord.Complete(jobId, package.Id));

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"job_result\"," +
            $"\"job_id\":\"{jobId}\"" +
            "}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        Assert.True(Assert.IsType<bool>(data["result_available"]));
        Assert.Equal("reconstruction_package", data["result_kind"]);   // 3D job: typed kind present, package unchanged
        var summary = Assert.IsType<Dictionary<string, object?>>(data["package"]);
        Assert.Equal(package.Id.ToString("D"), summary["artifact_id"]);
        Assert.Contains("model_glb", Assert.IsAssignableFrom<object[]>(summary["asset_roles"]));
        Assert.Equal("model_glb", summary["preferred_asset_role"]);
        Assert.Equal("model_glb", summary["resolved_import_role"]);
    }

    [Fact]
    public void Result_RemoveBackgroundJob_ResultKindPreprocessedImage_PackageNull()
    {
        // bg-removal result must NOT masquerade as a 3D package: result_kind=preprocessed_image,
        // image-role metadata present, package null.
        var fixture = CreateFixture();
        var preprocessed = fixture.Store.Create(
            ReconstructionArtifactKinds.PreprocessedImage,
            new[]
            {
                new BlobInput("image", new byte[] { 1, 2, 3 }, "png"),
                new BlobInput("mask", new byte[] { 4, 5, 6 }, "png"),
            });
        var jobId = Guid.NewGuid();
        fixture.Ledger.Append(
            ReconstructionJobLedgerRecord.Complete(jobId, preprocessed.Id, "remove_background"));

        var response = fixture.Handler.DispatchOffUi(
            $"{{\"op\":\"job_result\",\"job_id\":\"{jobId}\"}}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        Assert.Equal("preprocessed_image", data["result_kind"]);
        Assert.Null(data["package"]);
        var roles = Assert.IsAssignableFrom<object[]>(data["asset_roles"]);
        Assert.Contains("image", roles);
        Assert.Contains("mask", roles);
    }

    [Fact]
    public async Task Result_ResolvedImportRole_PreferredPresent_EqualsPreferred()
    {
        // glb delivered → manifest preferred_asset (model_glb) is present → resolver returns preferred.
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 1, 2, 3 };
        var jobId = Guid.NewGuid();
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        { "model_urls": { "glb": {"url": "https://example.test/model.glb"} } }
        """)!, jobId);
        fixture.Ledger.Append(ReconstructionJobLedgerRecord.Complete(jobId, package.Id));

        var response = fixture.Handler.DispatchOffUi(
            $"{{\"op\":\"job_result\",\"job_id\":\"{jobId}\"}}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        var summary = Assert.IsType<Dictionary<string, object?>>(data["package"]);
        Assert.Equal("model_glb", summary["preferred_asset_role"]);
        Assert.Equal("model_glb", summary["resolved_import_role"]);
    }

    [Fact]
    public async Task Result_ResolvedImportRole_PreferredMissing_FallbackPresent_EqualsFallback()
    {
        // obj+mtl+texture delivered, NO glb → preferred (model_glb) absent → fallback resolves to model_obj.
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.obj"] = new byte[] { 1, 2, 3 };
        fixture.Downloader.Files["https://example.test/material.mtl"] = new byte[] { 4, 5, 6 };
        fixture.Downloader.Files["https://example.test/texture.png"] = new byte[] { 7, 8, 9 };
        var jobId = Guid.NewGuid();
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_urls": {
            "obj": {"url": "https://example.test/model.obj"},
            "mtl": {"url": "https://example.test/material.mtl"}
          },
          "texture": {"url": "https://example.test/texture.png"}
        }
        """)!, jobId);
        fixture.Ledger.Append(ReconstructionJobLedgerRecord.Complete(jobId, package.Id));

        var response = fixture.Handler.DispatchOffUi(
            $"{{\"op\":\"job_result\",\"job_id\":\"{jobId}\"}}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        var summary = Assert.IsType<Dictionary<string, object?>>(data["package"]);
        Assert.Equal("model_glb", summary["preferred_asset_role"]);          // catalog preference, absent here
        Assert.Equal("model_obj", summary["resolved_import_role"]);          // what import will actually use
        Assert.NotEqual(summary["preferred_asset_role"], summary["resolved_import_role"]);
    }

    [Fact]
    public async Task Result_ResolvedImportRole_DegenerateManifest_IsNull_AndDoesNotThrow()
    {
        // DEFENSIVE case — NOT a normal package. The materializer guarantees glb|obj, and the static
        // manifest's fallback_order lists both, so a naturally materialized package can never resolve to
        // null. We force a malformed/degenerate manifest (preferred names an absent role, fallback empty)
        // to prove the resolver returns null without throwing and the op still succeeds.
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.obj"] = new byte[] { 1, 2, 3 };
        var jobId = Guid.NewGuid();
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        { "model_urls": { "obj": {"url": "https://example.test/model.obj"} } }
        """)!, jobId);
        fixture.Ledger.Append(ReconstructionJobLedgerRecord.Complete(jobId, package.Id));

        var manifestPath = fixture.Store.GetBlobAbsolutePath(package.Id, ReconstructionFileRoles.ImportManifest);
        File.WriteAllText(manifestPath, "{\"schema_version\":1,\"preferred_asset\":\"model_glb\",\"fallback_order\":[]}");

        var response = fixture.Handler.DispatchOffUi(
            $"{{\"op\":\"job_result\",\"job_id\":\"{jobId}\"}}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        var summary = Assert.IsType<Dictionary<string, object?>>(data["package"]);
        Assert.Null(summary["resolved_import_role"]);
    }

    [Fact]
    public async Task DispatchOffUi_Result_TextureExpectedBarePackage_SerializesMissingTextureWarning()
    {
        // Pins the UI-facing contract: the result op must serialize the degraded-texture warning so the
        // UI reads result.warnings[] rather than inferring degradation from raw asset_roles.
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 1, 2, 3 };
        var jobId = Guid.NewGuid();
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_urls": {
            "glb": {"url": "https://example.test/model.glb"}
          }
        }
        """)!, jobId);   // bare package: model_glb only, no texture/material
        // Complete() blanks model_id (which would null the catalog lookup and suppress the warning), so
        // build the terminal record from Queued with a real model id and TextureExpected = true.
        fixture.Ledger.Append(
            ReconstructionJobLedgerRecord.Queued(jobId, HunyuanModelId, Guid.NewGuid(), "image", textureExpected: true)
                with
                {
                    State = ReconstructionJobState.Complete,
                    Stage = ReconstructionJobStage.Complete,
                    ResultArtifactId = package.Id,
                    ResultAvailable = true,
                });

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"job_result\"," +
            $"\"job_id\":\"{jobId}\"" +
            "}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        var warnings = Assert.IsAssignableFrom<object[]>(data["warnings"]);
        var warning = Assert.IsType<Dictionary<string, object?>>(Assert.Single(warnings));
        Assert.Equal("result_missing_texture", warning["code"]);
        var details = Assert.IsType<Dictionary<string, object?>>(warning["details"]);
        Assert.Equal(HunyuanModelId, details["model_id"]);
        Assert.Contains("model_glb", Assert.IsAssignableFrom<object[]>(details["delivered_roles"]));
    }

    [Fact]
    public async Task DispatchOffUi_RecordImport_AppendsImportManifestHistory()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 1, 2, 3 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_urls": {
            "glb": {"url": "https://example.test/model.glb"}
          }
        }
        """)!);

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"record_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            "\"asset_role\":\"model_glb\"," +
            "\"path\":\"C:/Rook/import_bundle_123/model.obj\"," +
            "\"source_path\":\"C:/Rook/model_obj.obj\"," +
            "\"imported_ids\":[\"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa\"]," +
            "\"associated\":true" +
            "}");

        Assert.True(response.Success);
        var manifest = JsonNode.Parse(File.ReadAllText(
            fixture.Store.GetBlobAbsolutePath(package.Id, ReconstructionFileRoles.ImportManifest)))!;
        Assert.Equal(
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            manifest["imports"]![0]!["imported_ids"]![0]!.GetValue<string>());
        Assert.True(manifest["imports"]![0]!["associated"]!.GetValue<bool>());
        Assert.Equal("C:/Rook/import_bundle_123/model.obj", manifest["imports"]![0]!["path"]!.GetValue<string>());
        Assert.Equal("C:/Rook/model_obj.obj", manifest["imports"]![0]!["source_path"]!.GetValue<string>());
    }

    [Fact]
    public async Task DispatchOffUi_RecordImport_ReplacesExistingImportId()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 1, 2, 3 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_urls": {
            "glb": {"url": "https://example.test/model.glb"}
          }
        }
        """)!);
        const string importId = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";

        fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"record_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            $"\"import_id\":\"{importId}\"," +
            "\"asset_role\":\"model_glb\"," +
            "\"imported_ids\":[\"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa\"]," +
            "\"associated\":false" +
            "}");
        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"record_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            $"\"import_id\":\"{importId}\"," +
            "\"asset_role\":\"model_glb\"," +
            "\"imported_ids\":[\"cccccccc-cccc-cccc-cccc-cccccccccccc\"]," +
            "\"associated\":true" +
            "}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var manifest = JsonNode.Parse(File.ReadAllText(
            fixture.Store.GetBlobAbsolutePath(package.Id, ReconstructionFileRoles.ImportManifest)))!;
        var imports = manifest["imports"]!.AsArray();
        Assert.Single(imports);
        Assert.Equal(
            "cccccccc-cccc-cccc-cccc-cccccccccccc",
            imports[0]!["imported_ids"]![0]!.GetValue<string>());
        Assert.True(imports[0]!["associated"]!.GetValue<bool>());
    }

    private static async Task<Artifact> BuildPackageAsync(Fixture fixture, JsonNode resultJson, Guid? jobId = null)
    {
        var result = await fixture.Materializer.MaterializeAsync(
            jobId ?? Guid.NewGuid(),
            Array.Empty<Guid>(),
            "fal",
            HunyuanModelId,
            FalReconstructionResultMapper.ToEnvelope(resultJson),
            CancellationToken.None);
        Assert.True(result.Success, JsonSerializer.Serialize(result.Error));
        return result.Package!;
    }

    [Fact]
    public async Task ResolvedImportRole_MatchesPrepareImportAssetRole_ForSamePackage()
    {
        // The load-bearing promise: the panel's "Import will use" role equals the role the import plan
        // will use. Same package, no requested assetRole — preferred (model_glb) missing, fallback
        // (model_obj) present, i.e. the live textured-Hunyuan shape.
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/model.obj"] = new byte[] { 1, 2, 3 };
        fixture.Downloader.Files["https://example.test/material.mtl"] = new byte[] { 4, 5, 6 };
        fixture.Downloader.Files["https://example.test/texture.png"] = new byte[] { 7, 8, 9 };
        var jobId = Guid.NewGuid();
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_urls": {
            "obj": {"url": "https://example.test/model.obj"},
            "mtl": {"url": "https://example.test/material.mtl"}
          },
          "texture": {"url": "https://example.test/texture.png"}
        }
        """)!, jobId);
        fixture.Ledger.Append(ReconstructionJobLedgerRecord.Complete(jobId, package.Id));

        // Panel-side prediction (job_result → package summary).
        var resultResponse = fixture.Handler.DispatchOffUi(
            $"{{\"op\":\"job_result\",\"job_id\":\"{jobId}\"}}");
        Assert.True(resultResponse.Success, JsonSerializer.Serialize(resultResponse.Data));
        var resultData = Assert.IsType<Dictionary<string, object?>>(resultResponse.Data);
        var summary = Assert.IsType<Dictionary<string, object?>>(resultData["package"]);
        var predicted = Assert.IsType<string>(summary["resolved_import_role"]);
        Assert.Equal("model_obj", predicted);

        // Import-plan role for the SAME package, no assetRole override.
        var prepareResponse = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"prepare_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            "\"import_id\":\"cafe1234-cafe-cafe-cafe-cafecafecafe\"" +
            "}");
        Assert.True(prepareResponse.Success, JsonSerializer.Serialize(prepareResponse.Data));
        var prepareData = Assert.IsType<Dictionary<string, object?>>(prepareResponse.Data);

        // The promise: prediction == plan role.
        Assert.Equal(predicted, prepareData["asset_role"]);
    }

    [Fact]
    public async Task ImportPackage_Async_RoutesToClient_AndReturnsData()
    {
        var fixture = CreateFixture();
        var pkg = Guid.NewGuid();
        var body = $"{{\"op\":\"import_package\",\"package_id\":\"{pkg:D}\"}}";

        var resp = await fixture.Handler.DispatchAsync(body);

        Assert.True(resp.Success);
        Assert.Equal(pkg, fixture.ImportClient.LastPackageId);
        // Adapter must relay the client's data shape unchanged — no double-wrap, no dropped fields.
        var data = Assert.IsType<JsonObject>(resp.Data);
        Assert.Equal("model_obj", (string?)data["asset_role"]);
        Assert.NotNull(data["imported_ids"]);
        Assert.Equal(1, data["imported_ids"]!.AsArray().Count);
    }

    [Fact]
    public void ImportPackage_OffUi_IsRejected_WithoutInvokingClient()
    {
        var fixture = CreateFixture();
        var body = $"{{\"op\":\"import_package\",\"package_id\":\"{Guid.NewGuid():D}\"}}";

        var resp = fixture.Handler.DispatchOffUi(body);

        Assert.False(resp.Success);
        Assert.Equal(400, resp.HttpStatus);
        // Structured invalid-op failure (must route through async dispatcher) — NOT an accidental client run.
        var data = Assert.IsType<Dictionary<string, object?>>(resp.Data);
        Assert.Equal("invalid_request", data["code"]);
        Assert.Null(fixture.ImportClient.LastPackageId);   // client must NOT be invoked off-UI
    }

    [Fact]
    public void RemoveBackground_OffUi_IsRejected()
    {
        // remove_background is an async op; the off-UI dispatcher must reject it (400 invalid_request),
        // mirroring import_package — it must never run off the UI dispatch path.
        var fixture = CreateFixture();
        var body = $"{{\"op\":\"remove_background\",\"source_artifact_id\":\"{Guid.NewGuid():D}\"}}";

        var resp = fixture.Handler.DispatchOffUi(body);

        Assert.False(resp.Success);
        Assert.Equal(400, resp.HttpStatus);
        var data = Assert.IsType<Dictionary<string, object?>>(resp.Data);
        Assert.Equal("invalid_request", data["code"]);
    }

    [Fact]
    public void ModelsOp_Excludes_RemoveBackgroundTasks()
    {
        // The reconstruct picker must list only 3D-producing models. With experimental+hidden included,
        // the remove_background (birefnet) entry is present in the raw catalog but must be filtered out,
        // while 3D models (hunyuan) remain and now carry the new input/prompt descriptors.
        var fixture = CreateFixture();

        var response = fixture.Handler.DispatchOffUi(
            @"{""op"":""models"",""include_experimental"":true,""include_hidden"":true}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        var models = Assert.IsAssignableFrom<object[]>(data["models"])
            .Select(m => Assert.IsType<Dictionary<string, object?>>(m))
            .ToArray();

        Assert.All(models, m =>
        {
            Assert.DoesNotContain("birefnet", Assert.IsType<string>(m["model_id"]));
            Assert.NotEqual("remove_background", Assert.IsType<string>(m["task"]));
        });

        var hunyuan = Assert.Single(
            models, m => Assert.IsType<string>(m["model_id"]) == HunyuanModelId);
        // 3D entries now expose the descriptive capability metadata.
        Assert.True(hunyuan.ContainsKey("input"));
        Assert.True(hunyuan.ContainsKey("prompt"));
    }

    [Fact]
    public void DispatchOffUi_AssembleViewSet_ReachesAssembler()
    {
        var spy = new RecordingViewSetAssembler();
        var handler = BuildHandler(assembler: spy);
        var body = """{"op":"assemble_view_set","views":[{"slot":"front","artifact_id":"00000000-0000-0000-0000-000000000001"}]}""";

        var resp = handler.DispatchOffUi(body);

        Assert.True(spy.Called);
        Assert.Equal(200, resp.HttpStatus);   // spy returns success
    }

    [Fact]
    public async Task DispatchAsync_AssembleViewSet_IsRejectedAsUnknown_NotAsync()
    {
        var spy = new RecordingViewSetAssembler();
        var handler = BuildHandler(assembler: spy);
        var body = """{"op":"assemble_view_set","views":[]}""";

        var resp = await handler.DispatchAsync(body);

        // assemble_view_set is off-UI only; it must NOT be handled by the async dispatcher.
        Assert.False(spy.Called);
        Assert.Equal(400, resp.HttpStatus);
    }

    // ─── Task 3: handler envelope tests ──────────────────────────────────────

    [Fact]
    public void AssembleViewSet_Success_ReturnsSpecEnvelope()
    {
        var store = NewStore();
        var a = SeedImageArtifact(store, "generated_image");
        var handler = BuildHandler(store: store, assembler: new ReconstructionViewSetAssembler(store));
        var body = $$"""{"op":"assemble_view_set","views":[{"slot":"front","artifact_id":"{{a.Id:D}}"}]}""";

        var resp = handler.DispatchOffUi(body);

        Assert.Equal(200, resp.HttpStatus);
        var data = (IDictionary<string, object?>)resp.Data!;
        Assert.NotNull(data["view_set_artifact_id"]);
        Assert.Equal("reconstruction_view_set", data["kind"]);
        Assert.Equal(new[] { "front", "left", "right", "back" }, ((IEnumerable<string>)data["slots_expected"]!).ToArray());
        Assert.Equal(new[] { "front" }, ((IEnumerable<string>)data["slots_present"]!).ToArray());
        Assert.Equal(false, data["complete"]);
        Assert.NotNull(data["views"]);
        Assert.Equal(new[] { a.Id.ToString("D") }, ((IEnumerable<string>)data["parent_ids"]!).ToArray());
        Assert.Empty((IEnumerable<object?>)data["warnings"]!);
    }

    [Fact]
    public void AssembleViewSet_UnknownSlot_Returns400WithReason()   // assembler-side reject
    {
        var store = NewStore();
        var a = SeedImageArtifact(store, "generated_image");
        var handler = BuildHandler(store: store, assembler: new ReconstructionViewSetAssembler(store));
        var body = $$"""{"op":"assemble_view_set","views":[{"slot":"frnot","artifact_id":"{{a.Id:D}}"}]}""";

        var resp = handler.DispatchOffUi(body);

        Assert.Equal(400, resp.HttpStatus);
        var data = (IDictionary<string, object?>)resp.Data!;
        Assert.Equal("invalid_view_set", data["code"]);
        var details = (IReadOnlyDictionary<string, object?>)data["details"]!;
        Assert.Equal("unknown_slot", details["reason"]);
    }

    [Fact]
    public void AssembleViewSet_ParseFailure_SerializesEnvelope()   // parser-side reject
    {
        var store = NewStore();
        var a = SeedImageArtifact(store, "generated_image");
        var handler = BuildHandler(store: store, assembler: new ReconstructionViewSetAssembler(store));
        // provenance as an array is a parser-level structural reject.
        var body = $$"""{"op":"assemble_view_set","views":[{"slot":"front","artifact_id":"{{a.Id:D}}","provenance":[]}]}""";

        var resp = handler.DispatchOffUi(body);

        Assert.Equal(400, resp.HttpStatus);
        var data = (IDictionary<string, object?>)resp.Data!;
        Assert.Equal("invalid_provenance", data["code"]);
        var details = (IReadOnlyDictionary<string, object?>)data["details"]!;
        Assert.Equal("provenance_not_object", details["reason"]);
    }

    [Fact]
    public void AssembleViewSet_ViewsEchoProvenanceIntact()   // provenance round-trip / serialization hazard
    {
        var store = NewStore();
        var a = SeedImageArtifact(store, "generated_image");
        var handler = BuildHandler(store: store, assembler: new ReconstructionViewSetAssembler(store));
        // provenance is a JSON object with a known key/value.
        var body = "{\"op\":\"assemble_view_set\",\"views\":[{\"slot\":\"front\",\"artifact_id\":\"" + a.Id.ToString("D") + "\",\"provenance\":{\"camera\":\"orbit\",\"distance\":10}}]}";

        var resp = handler.DispatchOffUi(body);

        Assert.Equal(200, resp.HttpStatus);
        var data = (IDictionary<string, object?>)resp.Data!;
        var views = (IEnumerable<IReadOnlyDictionary<string, object?>>)data["views"]!;
        var row = views.Single();
        // provenance key must be present and be a JsonObject (not a type name, not null)
        Assert.True(row.ContainsKey("provenance"), "views[0] must contain 'provenance' key");
        var prov = Assert.IsType<JsonObject>(row["provenance"]);
        // content survives the handler round-trip intact
        Assert.Equal("orbit", prov["camera"]?.GetValue<string>());
        Assert.Equal(10, prov["distance"]?.GetValue<int>());
        // Verify it also round-trips through JsonSerializer (the HTTP boundary path)
        var json = JsonSerializer.Serialize(new { data = resp.Data });
        Assert.Contains("\"camera\"", json);
        Assert.Contains("\"orbit\"", json);
    }

    [Fact]
    public void AssembleViewSet_DoesNotWriteLedger()
    {
        var store = NewStore();
        var a = SeedImageArtifact(store, "generated_image");
        var root = NewTempRoot();
        var ledger = new JsonlReconstructionJobLedger(Path.Combine(root, "ledger.jsonl"));
        var handler = BuildHandler(store: store, assembler: new ReconstructionViewSetAssembler(store), ledger: ledger);

        handler.DispatchOffUi($$"""{"op":"assemble_view_set","views":[{"slot":"front","artifact_id":"{{a.Id:D}}"}]}""");

        // The assemble_view_set op writes a view_set artifact but must NOT write any
        // job-ledger record (the reconstruction job ledger is a separate JSONL file).
        Assert.Equal(0, ledger.List(10).Jobs.Count);
        // Confirm exactly one new artifact (the view_set) was created as a sanity check.
        Assert.Equal(2, store.List().Count);   // 1 seeded image + 1 view_set
    }

    [Theory]
    [InlineData("invalid_view_set")]
    [InlineData("invalid_provenance")]
    public void StatusFor_NewViewSetCodes_Return400(string code)
    {
        var failure = new ReconstructionFailure(code, "test", false, null, new Dictionary<string, object?>());
        Assert.Equal(400, ReconstructionOpHandler.StatusFor(failure));
    }

    // Seed helpers for view-set handler tests.
    private ArtifactStore NewStore()
    {
        var root = NewTempRoot();
        return new ArtifactStore(Path.Combine(root, "artifacts"));
    }

    private static Artifact SeedImageArtifact(ArtifactStore store, string kind, string role = "image")
        => store.Create(
            kind,
            new[] { new BlobInput(role, new byte[] { 0xFF, 0xD8, 0xFF }, "png") });

    private ReconstructionOpHandler BuildHandler(
        IReconstructionViewSetAssembler? assembler = null,
        ArtifactStore? store = null,
        JsonlReconstructionJobLedger? ledger = null)
    {
        var root = NewTempRoot();
        store ??= new ArtifactStore(Path.Combine(root, "artifacts"));
        ledger ??= new JsonlReconstructionJobLedger(Path.Combine(root, "ledger.jsonl"));
        var catalog = ReconstructionModelCatalog.FromJson(CatalogJson);
        var provider = new FakeReconstructionProvider();
        var downloader = new FakeDownloader();
        var publisher = new FakeSourceImagePublisher();
        var materializer = new ReconstructionPackageMaterializer(store, downloader);
        var preprocessMaterializer = new ReconstructionPreprocessMaterializer(store, downloader);
        var manager = new ReconstructionJobManager(
            store,
            catalog,
            ledger,
            provider,
            materializer,
            preprocessMaterializer,
            publisher);
        _managers.Add(manager);
        assembler ??= new ReconstructionViewSetAssembler(store);
        return new ReconstructionOpHandler(catalog, manager, store, assembler);
    }

    private Fixture CreateFixture()
    {
        var root = NewTempRoot();
        var store = new ArtifactStore(Path.Combine(root, "artifacts"));
        var ledger = new JsonlReconstructionJobLedger(Path.Combine(root, "ledger.jsonl"));
        var catalog = ReconstructionModelCatalog.FromJson(CatalogJson);
        var provider = new FakeReconstructionProvider();
        var downloader = new FakeDownloader();
        var publisher = new FakeSourceImagePublisher();
        var materializer = new ReconstructionPackageMaterializer(store, downloader);
        var preprocessMaterializer = new ReconstructionPreprocessMaterializer(store, downloader);
        var manager = new ReconstructionJobManager(
            store,
            catalog,
            ledger,
            provider,
            materializer,
            preprocessMaterializer,
            publisher);
        _managers.Add(manager);
        var importClient = new FakeImportClient();
        return new Fixture(
            store,
            ledger,
            provider,
            downloader,
            materializer,
            new ReconstructionOpHandler(catalog, manager, store, new ReconstructionViewSetAssembler(store), importClient),
            importClient);
    }

    private string NewTempRoot()
    {
        var root = Path.Combine(Path.GetTempPath(), $"rook-reconstruction-handler-{Guid.NewGuid():N}");
        _roots.Add(root);
        return root;
    }

    private sealed record Fixture(
        ArtifactStore Store,
        JsonlReconstructionJobLedger Ledger,
        FakeReconstructionProvider Provider,
        FakeDownloader Downloader,
        ReconstructionPackageMaterializer Materializer,
        ReconstructionOpHandler Handler,
        FakeImportClient ImportClient);

    private sealed class FakeImportClient : IReconstructionImportClient
    {
        public Guid? LastPackageId;
        public NativeImportOutcome Outcome = NativeImportOutcome.Ok(new JsonObject
        {
            ["asset_role"] = "model_obj",
            ["imported_ids"] = new JsonArray { "id-1" },
        });

        public Task<NativeImportOutcome> ImportAsync(Guid packageId, CancellationToken ct)
        {
            LastPackageId = packageId;
            return Task.FromResult(Outcome);
        }
    }

    private sealed class FakeReconstructionProvider : IReconstructionProvider
    {
        public Queue<bool> StatusComplete { get; } = new();
        public List<string> ResultCalls { get; } = new();
        public JsonNode ResultJson { get; set; } =
            JsonNode.Parse(@"{""model_urls"":{""glb"":{""url"":""https://example.test/model.glb""}}}")!;

        public Task<ProviderSubmitOutcome> SubmitAsync(
            ReconstructionProviderSubmitRequest request,
            CancellationToken cancellationToken)
            => Task.FromResult<ProviderSubmitOutcome>(new QueuedSubmitOutcome(new ProviderJobHandle(
                "req-123",
                statusUrl: new Uri("https://queue.fal.run/status/req-123"),
                responseUrl: new Uri("https://queue.fal.run/response/req-123"),
                cancelUrl: new Uri("https://queue.fal.run/cancel/req-123"),
                cancelHttpMethod: "PUT")));

        public Task<ProviderStatusOutcome> GetStatusAsync(
            ProviderJobHandle handle,
            CancellationToken cancellationToken)
        {
            var complete = StatusComplete.Count > 0 && StatusComplete.Dequeue();
            return Task.FromResult<ProviderStatusOutcome>(complete
                ? new ProviderCompleteStatusOutcome(handle)
                : new InFlightStatusOutcome(GenerationLifecycleState.Running, null));
        }

        public Task<ProviderResultOutcome> FetchResultAsync(
            ProviderJobHandle handle,
            CancellationToken cancellationToken)
        {
            ResultCalls.Add(handle.ProviderJobId);
            return Task.FromResult<ProviderResultOutcome>(
                new SuccessResultOutcome(FalReconstructionResultMapper.ToEnvelope(ResultJson)));
        }

        public Task<ProviderCancelOutcome> CancelAsync(
            ProviderJobHandle handle,
            CancellationToken cancellationToken)
            => Task.FromResult<ProviderCancelOutcome>(new CanceledOutcome());
    }

    private sealed class FakeDownloader : IReconstructionRemoteAssetDownloader
    {
        public Dictionary<string, byte[]> Files { get; } = new();

        public Task<ReconstructionDownloadResult> DownloadAsync(Uri url, string role, CancellationToken ct)
        {
            if (Files.TryGetValue(url.ToString(), out var bytes))
                return Task.FromResult(new ReconstructionDownloadResult(true, bytes, "application/octet-stream", null));
            return Task.FromResult(new ReconstructionDownloadResult(
                false,
                null,
                null,
                new GenerationError(GenerationErrorCode.DependencyUnavailable, $"missing {url}", Retryable: true)));
        }
    }

    private sealed class FakeSourceImagePublisher : IReconstructionSourceImagePublisher
    {
        public Task<Uri> PublishAsync(
            byte[] bytes,
            string mimeType,
            string fileName,
            CancellationToken ct)
            => Task.FromResult(new Uri("https://rook.local/source.png"));
    }

    internal sealed class RecordingViewSetAssembler : IReconstructionViewSetAssembler
    {
        public bool Called { get; private set; }

        public ReconstructionViewSetOutcome Assemble(ReconstructionViewSetRequest request)
        {
            Called = true;
            // Create a real artifact so the handler's full envelope path succeeds.
            var tmpRoot = Path.Combine(Path.GetTempPath(), $"rook-spy-{Guid.NewGuid():N}");
            var store = new ArtifactStore(tmpRoot);
            var artifact = store.Create(
                ReconstructionArtifactKinds.ViewSet,
                new[] { new BlobInput("front", new byte[] { 0xFF }, "png") });
            return new ReconstructionViewSetOutcome(
                true,
                artifact,
                new[] { "front", "left", "right", "back" },
                new[] { "front" },
                false,
                System.Array.Empty<System.Collections.Generic.IReadOnlyDictionary<string, object?>>(),
                null);
        }
    }

    private const string CatalogJson = """
    {
      "schema_version": 1,
      "models": [
        {
          "model_id": "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
          "provider": "fal",
          "task": "single_image_to_3d",
          "status": "stable",
          "enabled": true,
          "pipeline_roles": ["single_image_to_3d"],
          "input_types": ["image_url"],
          "output_roles": ["model_glb", "model_obj", "material_mtl", "texture", "thumbnail"],
          "preferred_asset_role": "model_glb",
          "fallback_order": ["model_glb", "model_obj"],
          "supports_pbr": true,
          "input": {"mode": "single_image", "source_field": "input_image_url"},
          "preprocessing": {"recommended": false, "required": false},
          "docs_url": "https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d/api"
        },
        {
          "model_id": "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
          "provider": "fal",
          "task": "single_image_to_3d",
          "status": "experimental",
          "enabled": true,
          "pipeline_roles": ["single_image_to_3d"],
          "input_types": ["image_url"],
          "output_roles": ["model_glb", "model_obj", "material_mtl", "model_fbx", "model_usdz", "texture", "thumbnail"],
          "preferred_asset_role": "model_glb",
          "fallback_order": ["model_glb", "model_obj"],
          "supports_pbr": true,
          "default_texture_expected": true,
          "input": {
            "mode": "multi_view_labeled",
            "source_field": "input_image_url",
            "view_slots": [
              { "role": "front",       "field": "input_image_url",       "required": true  },
              { "role": "back",        "field": "back_image_url",        "required": false },
              { "role": "left",        "field": "left_image_url",        "required": false },
              { "role": "right",       "field": "right_image_url",       "required": false },
              { "role": "top",         "field": "top_image_url",         "required": false },
              { "role": "bottom",      "field": "bottom_image_url",      "required": false },
              { "role": "left_front",  "field": "left_front_image_url",  "required": false },
              { "role": "right_front", "field": "right_front_image_url", "required": false }
            ]
          },
          "options": [
            { "key": "generate_type", "label": "Generate Type", "kind": "enum",
              "default": "Normal", "allowed_values": ["Normal", "Geometry"] },
            { "key": "enable_pbr", "label": "Enable PBR", "kind": "boolean",
              "default": false, "ignored_when": { "key": "generate_type", "equals": "Geometry" } },
            { "key": "face_count", "label": "Face Count", "kind": "integer",
              "default": 500000, "min": 40000, "max": 1500000, "step": 10000 }
          ],
          "preprocessing": {"recommended": false, "required": false},
          "docs_url": "https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/pro/image-to-3d/api"
        },
        {
          "model_id": "fal-ai/meshy/v6/image-to-3d",
          "provider": "fal",
          "task": "single_image_to_3d",
          "status": "experimental",
          "enabled": true,
          "pipeline_roles": ["single_image_to_3d"],
          "input_types": ["image_url"],
          "output_roles": ["model_glb"],
          "preferred_asset_role": "model_glb",
          "fallback_order": ["model_glb"],
          "supports_pbr": true,
          "input": {"mode": "single_image", "source_field": "input_image_url"},
          "prompt": {"supported": true, "required": false, "kind": "texture"},
          "preprocessing": {"recommended": false, "required": false},
          "docs_url": "https://fal.ai/models/fal-ai/meshy/v6/image-to-3d/api"
        },
        {
          "model_id": "fal-ai/birefnet/v2",
          "provider": "fal",
          "task": "remove_background",
          "status": "experimental",
          "enabled": true,
          "pipeline_roles": ["preprocess_remove_background"],
          "input_types": ["image_url"],
          "output_roles": ["image", "mask"],
          "preferred_asset_role": "image",
          "fallback_order": ["image"],
          "supports_pbr": false,
          "input": {"mode": "single_image", "source_field": "image_url"},
          "preprocessing": {"recommended": false, "required": false},
          "docs_url": "https://fal.ai/models/fal-ai/birefnet/v2/api"
        }
      ]
    }
    """;
}
