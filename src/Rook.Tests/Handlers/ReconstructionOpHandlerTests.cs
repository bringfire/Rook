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
        var summary = Assert.IsType<Dictionary<string, object?>>(data["package"]);
        Assert.Equal(package.Id.ToString("D"), summary["artifact_id"]);
        Assert.Contains("model_glb", Assert.IsAssignableFrom<object[]>(summary["asset_roles"]));
        Assert.Equal("model_glb", summary["preferred_asset_role"]);
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
        var manager = new ReconstructionJobManager(
            store,
            catalog,
            ledger,
            provider,
            materializer,
            publisher);
        _managers.Add(manager);
        return new Fixture(
            store,
            ledger,
            provider,
            downloader,
            materializer,
            new ReconstructionOpHandler(catalog, manager, store));
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
        ReconstructionOpHandler Handler);

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
          "preprocessing": {"recommended": false, "required": false},
          "docs_url": "https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d/api"
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
          "preprocessing": {"recommended": false, "required": false},
          "docs_url": "https://fal.ai/models/fal-ai/meshy/v6/image-to-3d/api"
        }
      ]
    }
    """;
}
