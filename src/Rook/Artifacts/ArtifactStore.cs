using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Rook.Artifacts
{
    /// <summary>
    /// Persistent, addressable artifact store backed by a directory tree at
    /// <see cref="RookPaths.ArtifactsRoot"/> (overridable for tests).
    ///
    /// On-disk layout:
    /// <code>
    /// {root}/
    ///   {YYYY-MM-DD}/
    ///     {uuid}/
    ///       manifest.json
    ///       {role}.{ext}      (one per blob)
    ///     {uuid}.tmp/         (transient, invisible to consumers)
    /// </code>
    ///
    /// Identity rules (load-bearing):
    /// <list type="bullet">
    ///   <item>The directory name <c>{uuid}</c> is the artifact's identity.</item>
    ///   <item>The manifest's <c>id</c> field must equal the directory name.</item>
    ///   <item>Day buckets are storage partitions only — not part of identity.</item>
    ///   <item>Two finalized <c>{uuid}</c> directories with the same UUID across
    ///         buckets is corruption, not an "import collision."</item>
    ///   <item><c>.tmp</c> directories are never visible to <see cref="Get"/>,
    ///         <see cref="List"/>, or <see cref="Delete"/>.</item>
    ///   <item>A finalized <c>{uuid}</c> directory missing <c>manifest.json</c>
    ///         is corruption (contradicts the atomic-create commit).</item>
    /// </list>
    ///
    /// v1 has no index. <see cref="Get"/> and <see cref="Delete"/> scan day
    /// buckets — O(buckets). A future <c>manifest.index.json</c> is a
    /// deliberate v2 deferral.
    ///
    /// Single-writer assumption — no cross-process locking in v1.
    /// </summary>
    public sealed class ArtifactStore
    {
        private const int CurrentSchemaVersion = 1;
        private const string ManifestFileName = "manifest.json";
        private const string TempDirSuffix = ".tmp";
        private const string DayKeyFormat = "yyyy-MM-dd";

        private static readonly Regex KindPattern =
            new(@"^[a-z0-9][a-z0-9_-]*$", RegexOptions.Compiled);
        private static readonly Regex RolePattern = KindPattern;
        private static readonly Regex ExtensionPattern =
            new(@"^[a-z0-9]+$", RegexOptions.Compiled);
        private static readonly Regex PathPattern =
            new(@"^[A-Za-z0-9][A-Za-z0-9._-]*$", RegexOptions.Compiled);

        // ISO 8601 datetime with explicit offset (Z or ±HH:MM / ±HHMM).
        // Pre-check before TryParse because RoundtripKind alone accepts
        // offset-less strings and silently treats them as local time.
        private static readonly Regex Iso8601WithOffsetPattern = new(
            @"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})$",
            RegexOptions.Compiled);

        private static readonly JsonSerializerOptions WriteOptions = new()
        {
            WriteIndented = true,
        };

        private readonly string _root;

        public ArtifactStore() : this(null) { }

        public ArtifactStore(string? overrideRoot)
        {
            _root = overrideRoot ?? RookPaths.ArtifactsRoot;
        }

        // ─── public API ─────────────────────────────────────────────

        public Artifact Create(
            string kind,
            IReadOnlyList<BlobInput> blobs,
            IReadOnlyList<Guid>? parentIds = null,
            IReadOnlyDictionary<string, JsonNode?>? metadata = null,
            IReadOnlyDictionary<string, JsonNode?>? flags = null)
        {
            ValidateKindArg(kind);
            ValidateBlobsArg(blobs);

            var id = Guid.NewGuid();
            var now = DateTimeOffset.UtcNow;
            var dayKey = now.ToString(DayKeyFormat, CultureInfo.InvariantCulture);

            var dayDir = Path.Combine(_root, dayKey);
            var idStr = id.ToString("D");
            var finalDir = Path.Combine(dayDir, idStr);
            var tmpDir = finalDir + TempDirSuffix;

            var files = blobs
                .Select(b => new ArtifactFile(b.Role, $"{b.Role}.{b.FileExtension}"))
                .ToList();

            var artifact = new Artifact(
                Id: id,
                Kind: kind,
                CreatedAt: now,
                Files: files,
                ParentIds: parentIds is null
                    ? Array.Empty<Guid>()
                    : new List<Guid>(parentIds),
                Metadata: CloneOrEmpty(metadata),
                Flags: CloneOrEmpty(flags));

            Directory.CreateDirectory(dayDir);

            try
            {
                Directory.CreateDirectory(tmpDir);

                foreach (var blob in blobs)
                {
                    var blobPath = Path.Combine(tmpDir, $"{blob.Role}.{blob.FileExtension}");
                    File.WriteAllBytes(blobPath, blob.Content);
                }

                var manifestPath = Path.Combine(tmpDir, ManifestFileName);
                File.WriteAllText(manifestPath, SerializeManifest(artifact));

                Directory.Move(tmpDir, finalDir);
                return artifact;
            }
            catch
            {
                try
                {
                    if (Directory.Exists(tmpDir))
                        Directory.Delete(tmpDir, recursive: true);
                }
                catch { /* swallow secondary failure */ }

                throw;
            }
        }

        public Artifact? Get(Guid id)
        {
            var dirs = FindFinalizedDirs(id);
            if (dirs.Count == 0) return null;
            if (dirs.Count > 1) throw DuplicateUuid(id);
            return ReadArtifact(dirs[0]);
        }

        public IReadOnlyList<Artifact> List()
        {
            if (!Directory.Exists(_root)) return Array.Empty<Artifact>();

            var seenIds = new HashSet<Guid>();
            var artifacts = new List<Artifact>();

            foreach (var dayDir in Directory.EnumerateDirectories(_root))
            {
                foreach (var artifactDir in Directory.EnumerateDirectories(dayDir))
                {
                    var name = Path.GetFileName(artifactDir);
                    if (name.EndsWith(TempDirSuffix, StringComparison.Ordinal)) continue;

                    if (!Guid.TryParseExact(name, "D", out var id)) continue;

                    if (!seenIds.Add(id)) throw DuplicateUuid(id);

                    artifacts.Add(ReadArtifact(artifactDir));
                }
            }

            return artifacts
                .OrderByDescending(a => a.CreatedAt)
                .ThenBy(a => a.Id)
                .ToList();
        }

        public bool Delete(Guid id)
        {
            var dirs = FindFinalizedDirs(id);
            if (dirs.Count == 0) return false;
            if (dirs.Count > 1) throw DuplicateUuid(id);

            // Validate before deleting — corruption surfaces, not silently cleaned.
            // Force-remove of a corrupt artifact is not a v1 affordance.
            _ = ReadArtifact(dirs[0]);

            Directory.Delete(dirs[0], recursive: true);
            return true;
        }

        public string GetBlobAbsolutePath(Guid id, string role)
        {
            ValidateRoleArg(role);

            var dirs = FindFinalizedDirs(id);
            if (dirs.Count == 0)
                throw new KeyNotFoundException($"Artifact '{id}' not found.");
            if (dirs.Count > 1) throw DuplicateUuid(id);

            var artifact = ReadArtifact(dirs[0]);
            var file = artifact.Files.FirstOrDefault(f => f.Role == role);
            if (file is null)
                throw new KeyNotFoundException($"Role '{role}' not found in artifact '{id}'.");

            var artifactDirCanonical = CanonicalDir(dirs[0]);
            var resolved = Path.GetFullPath(Path.Combine(artifactDirCanonical, file.Path));

            // Belt-and-suspenders: read-time validation already enforced this,
            // but re-check before returning a path the caller will dereference.
            if (!resolved.StartsWith(
                    artifactDirCanonical + Path.DirectorySeparatorChar,
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException(
                    $"Manifest path '{file.Path}' escapes artifact directory.");
            }

            if (!File.Exists(resolved))
            {
                throw new FileNotFoundException(
                    $"Blob '{file.Path}' (role '{role}') not found in artifact '{id}'.",
                    resolved);
            }

            return resolved;
        }

        // ─── internals: scanning & reading ──────────────────────────

        private List<string> FindFinalizedDirs(Guid id)
        {
            var result = new List<string>();
            if (!Directory.Exists(_root)) return result;

            var idStr = id.ToString("D");

            foreach (var dayDir in Directory.EnumerateDirectories(_root))
            {
                var candidate = Path.Combine(dayDir, idStr);
                if (Directory.Exists(candidate)) result.Add(candidate);
            }

            return result;
        }

        private Artifact ReadArtifact(string artifactDir)
        {
            var dirName = Path.GetFileName(artifactDir);
            if (!Guid.TryParseExact(dirName, "D", out var dirId))
            {
                throw new InvalidDataException(
                    $"Artifact directory '{artifactDir}' name is not a valid GUID.");
            }

            var manifestPath = Path.Combine(artifactDir, ManifestFileName);
            if (!File.Exists(manifestPath))
            {
                throw new InvalidDataException(
                    $"Finalized artifact directory '{artifactDir}' is missing '{ManifestFileName}'.");
            }

            var content = File.ReadAllText(manifestPath);
            var node = JsonNode.Parse(content);

            if (node is not JsonObject root)
            {
                throw new InvalidDataException(
                    $"Manifest '{manifestPath}' root is not a JSON object.");
            }

            return ParseAndValidate(root, dirId, manifestPath);
        }

        private Artifact ParseAndValidate(JsonObject root, Guid expectedId, string manifestPath)
        {
            // schema_version
            if (!root.TryGetPropertyValue("schema_version", out var svNode) || svNode is null)
                throw Bad(manifestPath, "schema_version missing");
            int sv;
            try { sv = svNode.GetValue<int>(); }
            catch { throw Bad(manifestPath, "schema_version is not an integer"); }
            if (sv != CurrentSchemaVersion)
                throw Bad(manifestPath, $"schema_version {sv} not supported (expected {CurrentSchemaVersion})");

            // id
            var idStr = ReadStringField(root, "id", manifestPath);
            if (!Guid.TryParseExact(idStr, "D", out var id))
                throw Bad(manifestPath, $"id '{idStr}' is not a valid GUID");
            if (id != expectedId)
                throw Bad(manifestPath, $"id '{id}' does not equal directory name '{expectedId}'");

            // kind
            var kind = ReadStringField(root, "kind", manifestPath);
            if (!KindPattern.IsMatch(kind))
                throw Bad(manifestPath, $"kind '{kind}' does not match required pattern");

            // created_at — require explicit offset (Z or ±HH:MM); reject
            // offset-less strings that DateTimeOffset.TryParse would otherwise
            // silently interpret as local time.
            var caStr = ReadStringField(root, "created_at", manifestPath);
            if (!Iso8601WithOffsetPattern.IsMatch(caStr))
            {
                throw Bad(manifestPath,
                    $"created_at '{caStr}' is not ISO 8601 with explicit offset (Z or ±HH:MM)");
            }
            if (!DateTimeOffset.TryParse(
                    caStr,
                    CultureInfo.InvariantCulture,
                    DateTimeStyles.RoundtripKind,
                    out var createdAt))
            {
                throw Bad(manifestPath, $"created_at '{caStr}' is not a valid ISO 8601 datetime");
            }

            // files
            if (!root.TryGetPropertyValue("files", out var filesNode) || filesNode is null)
                throw Bad(manifestPath, "files missing");
            if (filesNode is not JsonArray filesArray)
                throw Bad(manifestPath, "files is not an array");
            if (filesArray.Count == 0)
                throw Bad(manifestPath, "files is empty");

            var files = new List<ArtifactFile>();
            var seenRoles = new HashSet<string>(StringComparer.Ordinal);
            var artifactDir = Path.GetDirectoryName(manifestPath)!;

            foreach (var fNode in filesArray)
            {
                if (fNode is not JsonObject fObj)
                    throw Bad(manifestPath, "files entry is not an object");

                var role = ReadStringField(fObj, "role", manifestPath, context: "files entry");
                if (!RolePattern.IsMatch(role))
                    throw Bad(manifestPath, $"files entry role '{role}' invalid");
                if (!seenRoles.Add(role))
                    throw Bad(manifestPath, $"files entry role '{role}' duplicated");

                var pathStr = ReadStringField(fObj, "path", manifestPath, context: "files entry");
                ValidateManifestPath(pathStr, artifactDir, manifestPath);

                files.Add(new ArtifactFile(role, pathStr));
            }

            // parent_ids
            if (!root.TryGetPropertyValue("parent_ids", out var pidsNode) || pidsNode is null)
                throw Bad(manifestPath, "parent_ids missing");
            if (pidsNode is not JsonArray pidsArray)
                throw Bad(manifestPath, "parent_ids is not an array");

            var parentIds = new List<Guid>();
            foreach (var pidNode in pidsArray)
            {
                if (pidNode is null)
                    throw Bad(manifestPath, "parent_ids contains null");
                string pidStr;
                try { pidStr = pidNode.GetValue<string>(); }
                catch { throw Bad(manifestPath, "parent_ids contains non-string"); }
                if (!Guid.TryParseExact(pidStr, "D", out var pid))
                    throw Bad(manifestPath, $"parent_ids contains invalid GUID '{pidStr}'");
                parentIds.Add(pid);
            }

            // metadata
            var metadata = ReadDictField(root, "metadata", manifestPath);

            // flags
            var flags = ReadDictField(root, "flags", manifestPath);

            return new Artifact(id, kind, createdAt, files, parentIds, metadata, flags);
        }

        private static string ReadStringField(
            JsonObject obj, string field, string manifestPath, string? context = null)
        {
            var prefix = context is null ? field : $"{context} {field}";
            if (!obj.TryGetPropertyValue(field, out var node) || node is null)
                throw Bad(manifestPath, $"{prefix} missing");
            try { return node.GetValue<string>(); }
            catch { throw Bad(manifestPath, $"{prefix} is not a string"); }
        }

        private static IReadOnlyDictionary<string, JsonNode?> ReadDictField(
            JsonObject root, string field, string manifestPath)
        {
            if (!root.TryGetPropertyValue(field, out var node) || node is null)
                throw Bad(manifestPath, $"{field} missing");
            if (node is not JsonObject obj)
                throw Bad(manifestPath, $"{field} is not an object");
            return JsonObjectToDict(obj);
        }

        private static IReadOnlyDictionary<string, JsonNode?> JsonObjectToDict(JsonObject obj)
        {
            var dict = new Dictionary<string, JsonNode?>(StringComparer.Ordinal);
            foreach (var kvp in obj)
            {
                dict[kvp.Key] = kvp.Value?.DeepClone();
            }
            return dict;
        }

        private static void ValidateManifestPath(string path, string artifactDir, string manifestPath)
        {
            if (string.IsNullOrEmpty(path))
                throw Bad(manifestPath, "files entry path is empty");
            if (!PathPattern.IsMatch(path))
                throw Bad(manifestPath, $"files entry path '{path}' invalid (must be a flat artifact-local filename)");
            if (path.Contains(".."))
                throw Bad(manifestPath, $"files entry path '{path}' contains '..'");

            var artifactDirCanonical = CanonicalDir(artifactDir);
            var resolved = Path.GetFullPath(Path.Combine(artifactDirCanonical, path));

            if (!resolved.StartsWith(
                    artifactDirCanonical + Path.DirectorySeparatorChar,
                    StringComparison.OrdinalIgnoreCase))
            {
                throw Bad(manifestPath, $"files entry path '{path}' escapes artifact directory");
            }
        }

        private static string CanonicalDir(string dir)
            => Path.GetFullPath(dir).TrimEnd(Path.DirectorySeparatorChar);

        private static InvalidDataException Bad(string manifestPath, string reason)
            => new($"Manifest '{manifestPath}': {reason}.");

        private static InvalidDataException DuplicateUuid(Guid id)
            => new($"Duplicate finalized artifact directories found for id '{id}' across day buckets.");

        // ─── internals: serialization ───────────────────────────────

        private static string SerializeManifest(Artifact a)
        {
            var filesArray = new JsonArray();
            foreach (var f in a.Files)
            {
                filesArray.Add(new JsonObject
                {
                    ["role"] = f.Role,
                    ["path"] = f.Path,
                });
            }

            var parentsArray = new JsonArray();
            foreach (var p in a.ParentIds)
            {
                parentsArray.Add(JsonValue.Create(p.ToString("D")));
            }

            var metadataObj = new JsonObject();
            foreach (var kvp in a.Metadata)
            {
                metadataObj[kvp.Key] = kvp.Value?.DeepClone();
            }

            var flagsObj = new JsonObject();
            foreach (var kvp in a.Flags)
            {
                flagsObj[kvp.Key] = kvp.Value?.DeepClone();
            }

            var root = new JsonObject
            {
                ["schema_version"] = CurrentSchemaVersion,
                ["id"] = a.Id.ToString("D"),
                ["kind"] = a.Kind,
                ["created_at"] = a.CreatedAt.ToString("O", CultureInfo.InvariantCulture),
                ["files"] = filesArray,
                ["parent_ids"] = parentsArray,
                ["metadata"] = metadataObj,
                ["flags"] = flagsObj,
            };

            return root.ToJsonString(WriteOptions);
        }

        private static IReadOnlyDictionary<string, JsonNode?> CloneOrEmpty(
            IReadOnlyDictionary<string, JsonNode?>? source)
        {
            if (source is null) return new Dictionary<string, JsonNode?>(StringComparer.Ordinal);
            var dict = new Dictionary<string, JsonNode?>(StringComparer.Ordinal);
            foreach (var kvp in source)
            {
                dict[kvp.Key] = kvp.Value?.DeepClone();
            }
            return dict;
        }

        // ─── argument validation (Create) ───────────────────────────

        private static void ValidateKindArg(string kind)
        {
            if (kind is null) throw new ArgumentNullException(nameof(kind));
            if (string.IsNullOrWhiteSpace(kind))
                throw new ArgumentException("kind must be non-empty.", nameof(kind));
            if (!KindPattern.IsMatch(kind))
                throw new ArgumentException(
                    $"kind '{kind}' does not match required pattern.", nameof(kind));
        }

        private static void ValidateBlobsArg(IReadOnlyList<BlobInput> blobs)
        {
            if (blobs is null) throw new ArgumentNullException(nameof(blobs));
            if (blobs.Count == 0)
                throw new ArgumentException("blobs must be non-empty.", nameof(blobs));

            var seen = new HashSet<string>(StringComparer.Ordinal);
            for (int i = 0; i < blobs.Count; i++)
            {
                var b = blobs[i];
                if (b is null)
                    throw new ArgumentException($"blobs[{i}] is null.", nameof(blobs));
                if (b.Content is null)
                    throw new ArgumentException($"blobs[{i}].Content is null.", nameof(blobs));

                ValidateRoleArg(b.Role);
                ValidateExtensionArg(b.FileExtension);

                if (!seen.Add(b.Role))
                    throw new ArgumentException(
                        $"duplicate blob role '{b.Role}'.", nameof(blobs));
            }
        }

        private static void ValidateRoleArg(string role)
        {
            if (role is null) throw new ArgumentNullException(nameof(role));
            if (string.IsNullOrWhiteSpace(role))
                throw new ArgumentException("role must be non-empty.", nameof(role));
            if (!RolePattern.IsMatch(role))
                throw new ArgumentException(
                    $"role '{role}' does not match required pattern.", nameof(role));
        }

        private static void ValidateExtensionArg(string ext)
        {
            if (ext is null) throw new ArgumentNullException(nameof(ext));
            if (string.IsNullOrWhiteSpace(ext))
                throw new ArgumentException("extension must be non-empty.", nameof(ext));
            if (!ExtensionPattern.IsMatch(ext))
                throw new ArgumentException(
                    $"extension '{ext}' does not match required pattern.", nameof(ext));
        }
    }
}
