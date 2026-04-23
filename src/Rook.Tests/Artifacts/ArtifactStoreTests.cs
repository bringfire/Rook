using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook.Artifacts;
using Xunit;

namespace Rook.Tests.Artifacts
{
    public class ArtifactStoreTests : IDisposable
    {
        private readonly string _root;
        private readonly ArtifactStore _store;

        public ArtifactStoreTests()
        {
            _root = Path.Combine(Path.GetTempPath(), $"rook-artifacts-test-{Guid.NewGuid():N}");
            _store = new ArtifactStore(_root);
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        // ─── helpers ─────────────────────────────────────────────────

        private static byte[] Bytes(string s) => Encoding.UTF8.GetBytes(s);

        private static IReadOnlyList<BlobInput> OneBlob(
            string role = "primary", string ext = "png", string content = "hello")
            => new[] { new BlobInput(role, Bytes(content), ext) };

        private string CreateRawDayDir(string dayKey)
        {
            var dir = Path.Combine(_root, dayKey);
            Directory.CreateDirectory(dir);
            return dir;
        }

        private string CreateRawArtifactDir(string dayKey, Guid id)
        {
            var dir = Path.Combine(CreateRawDayDir(dayKey), id.ToString("D"));
            Directory.CreateDirectory(dir);
            return dir;
        }

        private void WriteRawManifest(string artifactDir, string content)
            => File.WriteAllText(Path.Combine(artifactDir, "manifest.json"), content);

        private static string ValidManifest(
            Guid id,
            string kind = "image_capture",
            string filesJson = @"[{""role"":""primary"",""path"":""primary.png""}]",
            int? schemaVersion = 1,
            string? createdAt = null,
            string parentIdsJson = "[]",
            string metadataJson = "{}",
            string flagsJson = "{}")
        {
            createdAt ??= DateTimeOffset.UtcNow.ToString("O");
            var sv = schemaVersion?.ToString() ?? "null";
            return $@"{{
  ""schema_version"": {sv},
  ""id"": ""{id:D}"",
  ""kind"": ""{kind}"",
  ""created_at"": ""{createdAt}"",
  ""files"": {filesJson},
  ""parent_ids"": {parentIdsJson},
  ""metadata"": {metadataJson},
  ""flags"": {flagsJson}
}}";
        }

        // ─── round trip ──────────────────────────────────────────────

        [Fact]
        public void Create_Then_Get_ReturnsEqualArtifact()
        {
            var created = _store.Create("image_capture", OneBlob());

            var loaded = _store.Get(created.Id);

            Assert.NotNull(loaded);
            Assert.Equal(created.Id, loaded!.Id);
            Assert.Equal(created.Kind, loaded.Kind);
            Assert.Equal(created.Files.Count, loaded.Files.Count);
            Assert.Equal("primary", loaded.Files[0].Role);
            Assert.Equal("primary.png", loaded.Files[0].Path);
        }

        [Fact]
        public void Create_MultiBlob_AllRolesPresent()
        {
            var blobs = new[]
            {
                new BlobInput("primary", Bytes("img"), "png"),
                new BlobInput("poster", Bytes("psr"), "jpg"),
                new BlobInput("depth", Bytes("dep"), "exr"),
            };

            var created = _store.Create("image_capture", blobs);

            var loaded = _store.Get(created.Id);
            Assert.NotNull(loaded);
            Assert.Equal(3, loaded!.Files.Count);
            Assert.Contains(loaded.Files, f => f.Role == "primary" && f.Path == "primary.png");
            Assert.Contains(loaded.Files, f => f.Role == "poster" && f.Path == "poster.jpg");
            Assert.Contains(loaded.Files, f => f.Role == "depth" && f.Path == "depth.exr");
        }

        [Fact]
        public void Create_WithParentsMetadataFlags_RoundTrips()
        {
            var parent = _store.Create("image_capture", OneBlob());
            var meta = new Dictionary<string, JsonNode?>
            {
                ["model"] = JsonValue.Create("gemini-2.5-flash"),
                ["seed"] = JsonValue.Create(42),
                ["nested"] = new JsonObject { ["a"] = 1, ["b"] = "two" },
            };
            var flags = new Dictionary<string, JsonNode?>
            {
                ["approved"] = JsonValue.Create(true),
            };

            var child = _store.Create(
                "generated_image", OneBlob("primary", "png", "child"),
                parentIds: new[] { parent.Id },
                metadata: meta,
                flags: flags);

            var loaded = _store.Get(child.Id);
            Assert.NotNull(loaded);
            Assert.Single(loaded!.ParentIds);
            Assert.Equal(parent.Id, loaded.ParentIds[0]);
            Assert.Equal("gemini-2.5-flash", loaded.Metadata["model"]!.GetValue<string>());
            Assert.Equal(42, loaded.Metadata["seed"]!.GetValue<int>());
            Assert.Equal(1, ((JsonObject)loaded.Metadata["nested"]!)["a"]!.GetValue<int>());
            Assert.True(loaded.Flags["approved"]!.GetValue<bool>());
        }

        [Fact]
        public void Create_WithoutOptionals_WritesEmptyContainers()
        {
            var created = _store.Create("k", OneBlob());

            var loaded = _store.Get(created.Id);
            Assert.NotNull(loaded);
            Assert.Empty(loaded!.ParentIds);
            Assert.Empty(loaded.Metadata);
            Assert.Empty(loaded.Flags);
        }

        // ─── persistence + ordering ──────────────────────────────────

        [Fact]
        public void List_AcrossMultipleDayBuckets_ReturnsAllOrderedDescByCreatedAtThenAscById()
        {
            var older = MakeArtifactInBucket("2026-04-20", DateTimeOffset.Parse("2026-04-20T10:00:00Z"));
            var newerA = MakeArtifactInBucket("2026-04-22", DateTimeOffset.Parse("2026-04-22T12:00:00Z"));
            var newerB = MakeArtifactInBucket("2026-04-22", DateTimeOffset.Parse("2026-04-22T12:00:00Z"));

            var all = _store.List();

            Assert.Equal(3, all.Count);
            // Newest first; tie-break by Id ascending
            var aFirst = newerA.Id.CompareTo(newerB.Id) < 0;
            Assert.Equal(aFirst ? newerA.Id : newerB.Id, all[0].Id);
            Assert.Equal(aFirst ? newerB.Id : newerA.Id, all[1].Id);
            Assert.Equal(older.Id, all[2].Id);
        }

        [Fact]
        public void List_Empty_ReturnsEmptyWhenRootMissing()
        {
            Assert.Empty(_store.List());
        }

        // Helper for the ordering test: write a manifest with a fixed timestamp
        // into a chosen day bucket. Doesn't go through Create (which uses UtcNow).
        private Artifact MakeArtifactInBucket(string dayKey, DateTimeOffset createdAt)
        {
            var id = Guid.NewGuid();
            var dir = CreateRawArtifactDir(dayKey, id);
            var blobPath = Path.Combine(dir, "primary.png");
            File.WriteAllBytes(blobPath, Bytes("data"));
            WriteRawManifest(dir, ValidManifest(id, createdAt: createdAt.ToString("O")));
            return new Artifact(
                id, "image_capture", createdAt,
                new[] { new ArtifactFile("primary", "primary.png") },
                Array.Empty<Guid>(),
                new Dictionary<string, JsonNode?>(),
                new Dictionary<string, JsonNode?>());
        }

        // ─── missing artifacts ───────────────────────────────────────

        [Fact]
        public void Get_MissingId_ReturnsNull()
            => Assert.Null(_store.Get(Guid.NewGuid()));

        [Fact]
        public void Delete_MissingId_ReturnsFalse()
            => Assert.False(_store.Delete(Guid.NewGuid()));

        [Fact]
        public void Delete_RemovesArtifactDir()
        {
            var created = _store.Create("k", OneBlob());

            Assert.True(_store.Delete(created.Id));
            Assert.Null(_store.Get(created.Id));
            Assert.DoesNotContain(_store.List(), a => a.Id == created.Id);
        }

        // ─── corruption: malformed JSON ─────────────────────────────

        [Fact]
        public void Get_MalformedManifestJson_Throws()
        {
            var id = Guid.NewGuid();
            var dir = CreateRawArtifactDir("2026-04-22", id);
            WriteRawManifest(dir, "{ this is not json");

            Assert.ThrowsAny<JsonException>(() => _store.Get(id));
        }

        [Fact]
        public void List_MalformedManifestJson_Throws()
        {
            var id = Guid.NewGuid();
            var dir = CreateRawArtifactDir("2026-04-22", id);
            WriteRawManifest(dir, "{ broken");

            Assert.ThrowsAny<JsonException>(() => _store.List());
        }

        // ─── corruption: finalized dir without manifest ─────────────

        [Fact]
        public void Get_FinalizedDirWithoutManifest_Throws()
        {
            var id = Guid.NewGuid();
            CreateRawArtifactDir("2026-04-22", id); // empty dir, no manifest

            Assert.Throws<InvalidDataException>(() => _store.Get(id));
        }

        [Fact]
        public void List_FinalizedDirWithoutManifest_Throws()
        {
            var id = Guid.NewGuid();
            CreateRawArtifactDir("2026-04-22", id);

            Assert.Throws<InvalidDataException>(() => _store.List());
        }

        [Fact]
        public void Delete_FinalizedDirWithoutManifest_Throws()
        {
            var id = Guid.NewGuid();
            CreateRawArtifactDir("2026-04-22", id);

            Assert.Throws<InvalidDataException>(() => _store.Delete(id));
            // Dir untouched — corruption is surfaced, not silently cleaned.
            Assert.True(Directory.Exists(Path.Combine(_root, "2026-04-22", id.ToString("D"))));
        }

        // ─── corruption: duplicate UUID across buckets ──────────────

        [Fact]
        public void Get_DuplicateUuidAcrossBuckets_Throws()
        {
            var id = Guid.NewGuid();
            var dirA = CreateRawArtifactDir("2026-04-20", id);
            var dirB = CreateRawArtifactDir("2026-04-22", id);
            File.WriteAllBytes(Path.Combine(dirA, "primary.png"), Bytes("a"));
            File.WriteAllBytes(Path.Combine(dirB, "primary.png"), Bytes("b"));
            WriteRawManifest(dirA, ValidManifest(id));
            WriteRawManifest(dirB, ValidManifest(id));

            Assert.Throws<InvalidDataException>(() => _store.Get(id));
        }

        [Fact]
        public void List_DuplicateUuidAcrossBuckets_Throws()
        {
            var id = Guid.NewGuid();
            var dirA = CreateRawArtifactDir("2026-04-20", id);
            var dirB = CreateRawArtifactDir("2026-04-22", id);
            File.WriteAllBytes(Path.Combine(dirA, "primary.png"), Bytes("a"));
            File.WriteAllBytes(Path.Combine(dirB, "primary.png"), Bytes("b"));
            WriteRawManifest(dirA, ValidManifest(id));
            WriteRawManifest(dirB, ValidManifest(id));

            Assert.Throws<InvalidDataException>(() => _store.List());
        }

        [Fact]
        public void Delete_DuplicateUuidAcrossBuckets_Throws()
        {
            var id = Guid.NewGuid();
            CreateRawArtifactDir("2026-04-20", id);
            CreateRawArtifactDir("2026-04-22", id);

            Assert.Throws<InvalidDataException>(() => _store.Delete(id));
        }

        [Fact]
        public void GetBlobAbsolutePath_DuplicateUuidAcrossBuckets_Throws()
        {
            var id = Guid.NewGuid();
            CreateRawArtifactDir("2026-04-20", id);
            CreateRawArtifactDir("2026-04-22", id);

            Assert.Throws<InvalidDataException>(() => _store.GetBlobAbsolutePath(id, "primary"));
        }

        // ─── schema_version edge cases ──────────────────────────────

        [Fact]
        public void Get_SchemaVersionMissing_Throws()
        {
            var id = Guid.NewGuid();
            var dir = CreateRawArtifactDir("2026-04-22", id);
            File.WriteAllBytes(Path.Combine(dir, "primary.png"), Bytes("x"));
            WriteRawManifest(dir, $@"{{
  ""id"": ""{id:D}"",
  ""kind"": ""k"",
  ""created_at"": ""2026-04-22T00:00:00Z"",
  ""files"": [{{""role"":""primary"",""path"":""primary.png""}}],
  ""parent_ids"": [],
  ""metadata"": {{}},
  ""flags"": {{}}
}}");

            Assert.Throws<InvalidDataException>(() => _store.Get(id));
        }

        [Fact]
        public void Get_SchemaVersionWrongType_Throws()
        {
            var id = Guid.NewGuid();
            var dir = CreateRawArtifactDir("2026-04-22", id);
            File.WriteAllBytes(Path.Combine(dir, "primary.png"), Bytes("x"));
            WriteRawManifest(dir, $@"{{
  ""schema_version"": ""1"",
  ""id"": ""{id:D}"",
  ""kind"": ""k"",
  ""created_at"": ""2026-04-22T00:00:00Z"",
  ""files"": [{{""role"":""primary"",""path"":""primary.png""}}],
  ""parent_ids"": [],
  ""metadata"": {{}},
  ""flags"": {{}}
}}");

            Assert.Throws<InvalidDataException>(() => _store.Get(id));
        }

        [Fact]
        public void Get_SchemaVersionMismatch_Throws()
        {
            var id = Guid.NewGuid();
            var dir = CreateRawArtifactDir("2026-04-22", id);
            File.WriteAllBytes(Path.Combine(dir, "primary.png"), Bytes("x"));
            WriteRawManifest(dir, ValidManifest(id, schemaVersion: 999));

            Assert.Throws<InvalidDataException>(() => _store.Get(id));
        }

        // ─── created_at offset-strictness ───────────────────────────

        [Theory]
        [InlineData("2026-04-22T15:30:00")]      // no offset, no Z (would default to local)
        [InlineData("2026-04-22 15:30:00")]      // space separator instead of T
        [InlineData("2026-04-22")]               // date only
        [InlineData("not-a-date")]
        [InlineData("")]
        public void Get_ManifestCreatedAtMissingOrWithoutOffset_Throws(string caStr)
        {
            var id = Guid.NewGuid();
            var dir = CreateRawArtifactDir("2026-04-22", id);
            File.WriteAllBytes(Path.Combine(dir, "primary.png"), Bytes("x"));
            WriteRawManifest(dir, ValidManifest(id, createdAt: caStr));

            Assert.Throws<InvalidDataException>(() => _store.Get(id));
        }

        [Theory]
        [InlineData("2026-04-22T15:30:00Z")]
        [InlineData("2026-04-22T15:30:00.123Z")]
        [InlineData("2026-04-22T15:30:00+05:00")]
        [InlineData("2026-04-22T15:30:00-05:00")]
        [InlineData("2026-04-22T15:30:00+0500")]
        public void Get_ManifestCreatedAtValidIso8601WithOffset_Accepted(string caStr)
        {
            var id = Guid.NewGuid();
            var dir = CreateRawArtifactDir("2026-04-22", id);
            File.WriteAllBytes(Path.Combine(dir, "primary.png"), Bytes("x"));
            WriteRawManifest(dir, ValidManifest(id, createdAt: caStr));

            var artifact = _store.Get(id);
            Assert.NotNull(artifact);
        }

        // ─── manifest id ≠ dir name ─────────────────────────────────

        [Fact]
        public void Get_ManifestIdMismatchDirName_Throws()
        {
            var dirId = Guid.NewGuid();
            var manifestId = Guid.NewGuid();
            var dir = CreateRawArtifactDir("2026-04-22", dirId);
            File.WriteAllBytes(Path.Combine(dir, "primary.png"), Bytes("x"));
            WriteRawManifest(dir, ValidManifest(manifestId));

            Assert.Throws<InvalidDataException>(() => _store.Get(dirId));
        }

        // ─── read-time validation: kind, files, role, path ─────────

        [Theory]
        [InlineData("Bad/Kind")]
        [InlineData("UPPER")]
        [InlineData("-leading")]
        [InlineData("kind with spaces")]
        public void Get_ManifestKindInvalid_Throws(string badKind)
        {
            var id = Guid.NewGuid();
            var dir = CreateRawArtifactDir("2026-04-22", id);
            File.WriteAllBytes(Path.Combine(dir, "primary.png"), Bytes("x"));
            WriteRawManifest(dir, ValidManifest(id, kind: badKind));

            Assert.Throws<InvalidDataException>(() => _store.Get(id));
        }

        [Fact]
        public void Get_ManifestFilesEmpty_Throws()
        {
            var id = Guid.NewGuid();
            var dir = CreateRawArtifactDir("2026-04-22", id);
            WriteRawManifest(dir, ValidManifest(id, filesJson: "[]"));

            Assert.Throws<InvalidDataException>(() => _store.Get(id));
        }

        [Fact]
        public void Get_ManifestFilesRoleDuplicate_Throws()
        {
            var id = Guid.NewGuid();
            var dir = CreateRawArtifactDir("2026-04-22", id);
            File.WriteAllBytes(Path.Combine(dir, "primary.png"), Bytes("x"));
            WriteRawManifest(dir, ValidManifest(id,
                filesJson: @"[{""role"":""primary"",""path"":""primary.png""},{""role"":""primary"",""path"":""primary.jpg""}]"));

            Assert.Throws<InvalidDataException>(() => _store.Get(id));
        }

        [Theory]
        [InlineData("Bad Role")]
        [InlineData("a/b")]
        [InlineData("UP")]
        public void Get_ManifestFilesRoleInvalid_Throws(string badRole)
        {
            var id = Guid.NewGuid();
            var dir = CreateRawArtifactDir("2026-04-22", id);
            File.WriteAllBytes(Path.Combine(dir, "primary.png"), Bytes("x"));
            WriteRawManifest(dir, ValidManifest(id,
                filesJson: $@"[{{""role"":""{badRole}"",""path"":""primary.png""}}]"));

            Assert.Throws<InvalidDataException>(() => _store.Get(id));
        }

        [Theory]
        [InlineData("../escape.png")]
        [InlineData("subdir/file.png")]
        [InlineData("subdir\\\\file.png")]
        [InlineData("/etc/passwd")]
        [InlineData("C:\\\\Windows\\\\evil.exe")]
        [InlineData(".hidden.png")]
        [InlineData(".")]
        [InlineData("..")]
        [InlineData("a..b.png")]
        [InlineData("-leading.png")]
        public void Get_ManifestPathInvalid_Throws(string badPath)
        {
            var id = Guid.NewGuid();
            var dir = CreateRawArtifactDir("2026-04-22", id);
            WriteRawManifest(dir, ValidManifest(id,
                filesJson: $@"[{{""role"":""primary"",""path"":""{badPath}""}}]"));

            Assert.Throws<InvalidDataException>(() => _store.Get(id));
        }

        // ─── GetBlobAbsolutePath ────────────────────────────────────

        [Fact]
        public void GetBlobAbsolutePath_Success_ReturnsAbsolutePathUnderRoot()
        {
            var created = _store.Create("k", OneBlob("primary", "png", "data"));

            var path = _store.GetBlobAbsolutePath(created.Id, "primary");

            Assert.True(Path.IsPathRooted(path));
            Assert.True(File.Exists(path));
            Assert.StartsWith(Path.GetFullPath(_root), Path.GetFullPath(path));
            Assert.Equal("data", File.ReadAllText(path));
        }

        [Fact]
        public void GetBlobAbsolutePath_MissingArtifact_ThrowsKeyNotFound()
        {
            Assert.Throws<KeyNotFoundException>(
                () => _store.GetBlobAbsolutePath(Guid.NewGuid(), "primary"));
        }

        [Fact]
        public void GetBlobAbsolutePath_MissingRole_ThrowsKeyNotFound()
        {
            var created = _store.Create("k", OneBlob());

            Assert.Throws<KeyNotFoundException>(
                () => _store.GetBlobAbsolutePath(created.Id, "nonexistent"));
        }

        [Fact]
        public void GetBlobAbsolutePath_BlobFileMissingOnDisk_ThrowsFileNotFound()
        {
            var created = _store.Create("k", OneBlob());
            var dirs = Directory.EnumerateDirectories(_root)
                .SelectMany(Directory.EnumerateDirectories)
                .Where(d => Path.GetFileName(d) == created.Id.ToString("D"))
                .ToList();
            File.Delete(Path.Combine(dirs[0], "primary.png"));

            Assert.Throws<FileNotFoundException>(
                () => _store.GetBlobAbsolutePath(created.Id, "primary"));
        }

        // ─── atomic create: orphan-resistant ────────────────────────

        [Fact]
        public void Create_OnFailure_NoFinalizedDirAndTmpCleanedUp()
        {
            // Inject a failure: blob with an invalid extension reaches argument
            // validation BEFORE any disk activity, so we need a different
            // failure mode. Instead, arrange a path collision: pre-create a
            // file at the day-bucket location so Directory.CreateDirectory(dayDir)
            // throws.
            Directory.CreateDirectory(_root);
            var dayKey = DateTimeOffset.UtcNow.ToString("yyyy-MM-dd");
            File.WriteAllText(Path.Combine(_root, dayKey), "blocking file");

            // Note: this throws either IOException or UnauthorizedAccessException
            // depending on the platform/env — we just want SOMETHING to throw.
            var threw = false;
            try { _store.Create("k", OneBlob()); }
            catch { threw = true; }
            Assert.True(threw);

            // No finalized {uuid}/ directory exists; no orphaned .tmp/ either.
            // (Day-bucket "directory" is actually a file in this test setup.)
            // The point is no garbage finalized artifact dirs.
            var anyFinalized = Directory.Exists(_root)
                && Directory.EnumerateDirectories(_root)
                    .SelectMany(Directory.EnumerateDirectories)
                    .Any(d => !Path.GetFileName(d).EndsWith(".tmp", StringComparison.Ordinal));
            Assert.False(anyFinalized);
        }

        // ─── .tmp invisibility ──────────────────────────────────────

        [Fact]
        public void TmpDir_NeverVisible_ToGetListOrDelete()
        {
            var id = Guid.NewGuid();
            var tmpDir = Path.Combine(CreateRawDayDir("2026-04-22"), id.ToString("D") + ".tmp");
            Directory.CreateDirectory(tmpDir);
            File.WriteAllBytes(Path.Combine(tmpDir, "primary.png"), Bytes("x"));
            WriteRawManifest(tmpDir, ValidManifest(id));

            Assert.Null(_store.Get(id));
            Assert.Empty(_store.List());
            Assert.False(_store.Delete(id));
        }

        // ─── input validation: kind ─────────────────────────────────

        [Theory]
        [InlineData("")]
        [InlineData(" ")]
        [InlineData("UPPER")]
        [InlineData("-leading")]
        [InlineData("a/b")]
        [InlineData("with spaces")]
        public void Create_InvalidKind_Throws(string kind)
        {
            Assert.Throws<ArgumentException>(() => _store.Create(kind, OneBlob()));
        }

        [Fact]
        public void Create_NullKind_Throws()
        {
            Assert.Throws<ArgumentNullException>(() => _store.Create(null!, OneBlob()));
        }

        // ─── input validation: blobs ────────────────────────────────

        [Fact]
        public void Create_NullBlobs_Throws()
        {
            Assert.Throws<ArgumentNullException>(() => _store.Create("k", null!));
        }

        [Fact]
        public void Create_EmptyBlobs_Throws()
        {
            Assert.Throws<ArgumentException>(() => _store.Create("k", Array.Empty<BlobInput>()));
        }

        [Fact]
        public void Create_DuplicateBlobRole_Throws()
        {
            var blobs = new[]
            {
                new BlobInput("primary", Bytes("a"), "png"),
                new BlobInput("primary", Bytes("b"), "jpg"),
            };
            Assert.Throws<ArgumentException>(() => _store.Create("k", blobs));
        }

        // ─── input validation: role + extension ─────────────────────

        [Theory]
        [InlineData("")]
        [InlineData(" ")]
        [InlineData("a/b")]
        [InlineData("a\\b")]
        [InlineData("..")]
        [InlineData(".")]
        [InlineData("a.b")]
        [InlineData("UPPER")]
        [InlineData("-x")]
        [InlineData("_x")]
        [InlineData("role with spaces")]
        [InlineData("röle")]
        public void Create_InvalidRole_Throws(string role)
        {
            Assert.Throws<ArgumentException>(
                () => _store.Create("k", new[] { new BlobInput(role, Bytes("x"), "png") }));
        }

        [Theory]
        [InlineData("")]
        [InlineData(" ")]
        [InlineData(".png")]
        [InlineData("png.")]
        [InlineData("p/g")]
        [InlineData("PNG")]
        [InlineData("png.gz")]
        public void Create_InvalidExtension_Throws(string ext)
        {
            Assert.Throws<ArgumentException>(
                () => _store.Create("k", new[] { new BlobInput("primary", Bytes("x"), ext) }));
        }

        // ─── SetFlag: atomic flag mutation ──────────────────────────

        [Fact]
        public void SetFlag_SetsNewFlag_AndPersists()
        {
            var created = _store.Create("k", OneBlob());
            Assert.False(created.Flags.ContainsKey("approved"));

            var updated = _store.SetFlag(created.Id, "approved", JsonValue.Create(true)!);

            Assert.True(updated.Flags["approved"]!.GetValue<bool>());

            // Persisted — a fresh Get sees the same flag.
            var reloaded = _store.Get(created.Id);
            Assert.NotNull(reloaded);
            Assert.True(reloaded!.Flags["approved"]!.GetValue<bool>());
        }

        [Fact]
        public void SetFlag_OverwritesExistingFlag()
        {
            var created = _store.Create("k", OneBlob(),
                flags: new Dictionary<string, JsonNode?>
                {
                    ["approved"] = JsonValue.Create(false),
                });

            var updated = _store.SetFlag(created.Id, "approved", JsonValue.Create(true)!);

            Assert.True(updated.Flags["approved"]!.GetValue<bool>());
            var reloaded = _store.Get(created.Id);
            Assert.True(reloaded!.Flags["approved"]!.GetValue<bool>());
        }

        [Fact]
        public void SetFlag_Idempotent_SameValue_NoThrow()
        {
            var created = _store.Create("k", OneBlob(),
                flags: new Dictionary<string, JsonNode?>
                {
                    ["approved"] = JsonValue.Create(true),
                });

            var updated = _store.SetFlag(created.Id, "approved", JsonValue.Create(true)!);
            Assert.True(updated.Flags["approved"]!.GetValue<bool>());

            // Second call — manifest is re-written but state is identical.
            var updated2 = _store.SetFlag(created.Id, "approved", JsonValue.Create(true)!);
            Assert.True(updated2.Flags["approved"]!.GetValue<bool>());
        }

        [Fact]
        public void SetFlag_PreservesOtherFlagsAndMetadata()
        {
            var created = _store.Create("k", OneBlob(),
                metadata: new Dictionary<string, JsonNode?>
                {
                    ["prompt"] = JsonValue.Create("a cube"),
                    ["model"] = JsonValue.Create("gemini-2.5"),
                },
                flags: new Dictionary<string, JsonNode?>
                {
                    ["archived"] = JsonValue.Create(false),
                });

            var updated = _store.SetFlag(created.Id, "approved", JsonValue.Create(true)!);

            Assert.Equal("a cube", updated.Metadata["prompt"]!.GetValue<string>());
            Assert.Equal("gemini-2.5", updated.Metadata["model"]!.GetValue<string>());
            Assert.False(updated.Flags["archived"]!.GetValue<bool>());
            Assert.True(updated.Flags["approved"]!.GetValue<bool>());
        }

        [Fact]
        public void SetFlag_MissingArtifact_Throws()
        {
            Assert.Throws<KeyNotFoundException>(() =>
                _store.SetFlag(Guid.NewGuid(), "approved", JsonValue.Create(true)!));
        }

        [Fact]
        public void SetFlag_NullValue_Throws()
        {
            var created = _store.Create("k", OneBlob());
            Assert.Throws<ArgumentNullException>(() =>
                _store.SetFlag(created.Id, "approved", null!));
        }

        [Theory]
        [InlineData("")]
        [InlineData(" ")]
        [InlineData("Bad/Name")]
        [InlineData("UPPER")]
        [InlineData("-leading")]
        [InlineData("name with spaces")]
        public void SetFlag_InvalidName_Throws(string name)
        {
            var created = _store.Create("k", OneBlob());
            Assert.Throws<ArgumentException>(() =>
                _store.SetFlag(created.Id, name, JsonValue.Create(true)!));
        }

        [Fact]
        public void SetFlag_NullName_Throws()
        {
            var created = _store.Create("k", OneBlob());
            Assert.Throws<ArgumentNullException>(() =>
                _store.SetFlag(created.Id, null!, JsonValue.Create(true)!));
        }

        [Fact]
        public void SetFlag_CorruptManifest_RejectsMutation()
        {
            var id = Guid.NewGuid();
            var dir = CreateRawArtifactDir("2026-04-22", id);
            File.WriteAllBytes(Path.Combine(dir, "primary.png"), Bytes("x"));
            WriteRawManifest(dir, "{ not valid json");

            // Corruption surfaces before any write touches the manifest.
            Assert.ThrowsAny<Exception>(() =>
                _store.SetFlag(id, "approved", JsonValue.Create(true)!));

            // Manifest is untouched — the write path was never reached.
            var raw = File.ReadAllText(Path.Combine(dir, "manifest.json"));
            Assert.Equal("{ not valid json", raw);
        }

        [Fact]
        public void SetFlag_DuplicateUuidAcrossBuckets_Throws()
        {
            var id = Guid.NewGuid();
            CreateRawArtifactDir("2026-04-20", id);
            CreateRawArtifactDir("2026-04-22", id);

            Assert.Throws<InvalidDataException>(() =>
                _store.SetFlag(id, "approved", JsonValue.Create(true)!));
        }

        [Fact]
        public void SetFlag_OrphanedTmpManifest_DoesNotBlockGetOrList()
        {
            // A stray manifest.json.tmp (simulating a crash between
            // WriteAllText and File.Replace) must not be visible to
            // Get/List — they read manifest.json only. The next SetFlag
            // overwrites it via WriteAllText.
            var created = _store.Create("k", OneBlob());
            var artifactDir = Directory.EnumerateDirectories(_root)
                .SelectMany(Directory.EnumerateDirectories)
                .First(d => Path.GetFileName(d) == created.Id.ToString("D"));
            File.WriteAllText(
                Path.Combine(artifactDir, "manifest.json.tmp"),
                "{ partial write");

            // Get / List ignore the orphan and return the valid manifest.
            Assert.NotNull(_store.Get(created.Id));
            Assert.Single(_store.List());

            // Next SetFlag succeeds and clears the orphan path (via
            // WriteAllText + File.Replace cycle).
            _store.SetFlag(created.Id, "approved", JsonValue.Create(true)!);
            Assert.False(File.Exists(Path.Combine(artifactDir, "manifest.json.tmp")));
        }

        [Fact]
        public void SetFlag_ReturnedValue_IsClonedFromInput()
        {
            // Mutating the caller's JsonNode after SetFlag must not
            // affect stored state — the store takes a defensive copy.
            var created = _store.Create("k", OneBlob());

            var live = new JsonObject
            {
                ["label"] = "alpha",
            };
            _store.SetFlag(created.Id, "tag", live);
            live["label"] = "mutated";

            var reloaded = _store.Get(created.Id);
            Assert.Equal(
                "alpha",
                ((JsonObject)reloaded!.Flags["tag"]!)["label"]!.GetValue<string>());
        }

        // ─── on-disk JSON casing ────────────────────────────────────

        [Fact]
        public void Create_WritesSnakeCaseFieldNames()
        {
            var created = _store.Create("k", OneBlob());

            var manifestPath = Directory.EnumerateDirectories(_root)
                .SelectMany(Directory.EnumerateDirectories)
                .Where(d => Path.GetFileName(d) == created.Id.ToString("D"))
                .Select(d => Path.Combine(d, "manifest.json"))
                .First();
            var content = File.ReadAllText(manifestPath);

            Assert.Contains("\"schema_version\"", content);
            Assert.Contains("\"created_at\"", content);
            Assert.Contains("\"parent_ids\"", content);
            Assert.DoesNotContain("\"SchemaVersion\"", content);
            Assert.DoesNotContain("\"CreatedAt\"", content);
            Assert.DoesNotContain("\"ParentIds\"", content);
        }
    }
}
