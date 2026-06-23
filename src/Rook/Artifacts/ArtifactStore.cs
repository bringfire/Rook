using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
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
    ///         is corruption (contradicts the atomic-create commit).
    ///         Recovery (issue #241): <see cref="List()"/> skips it with a
    ///         warning; <see cref="Delete"/> quarantines it to a sibling
    ///         <c>{root}-quarantine</c> directory.</item>
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
        // Atomic-teardown marker (issue #241): Delete renames the artifact
        // dir to {uuid}.deleting.tmp BEFORE recursive removal. The ".tmp"
        // suffix makes leftovers invisible to Get/List/Delete by the
        // existing rule; the constructor sweeps them best-effort.
        private const string DeletingTempSuffix = ".deleting" + TempDirSuffix;
        private const string QuarantineDirSuffix = "-quarantine";
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
        // Exposed as internal so consumers (e.g. VisionHandler's
        // consume_approved 'since' filter) can apply the same invariant
        // without duplicating the pattern string.
        internal static readonly Regex Iso8601WithOffsetPattern = new(
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
            SweepDeletingTempDirs();
        }

        /// <summary>
        /// Best-effort removal of leftover <c>{uuid}.deleting.tmp</c> dirs
        /// from interrupted deletes (issue #241). Failures are swallowed:
        /// leftovers are invisible to the store and harmless; the next
        /// store construction retries.
        /// </summary>
        private void SweepDeletingTempDirs()
        {
            try
            {
                if (!Directory.Exists(_root)) return;
                foreach (var dayDir in Directory.EnumerateDirectories(_root))
                {
                    foreach (var dir in Directory.EnumerateDirectories(
                                 dayDir, "*" + DeletingTempSuffix))
                    {
                        try { Directory.Delete(dir, recursive: true); }
                        catch { /* still locked — next sweep retries */ }
                    }

                    // Empty GUID dirs are residue from fallback teardown
                    // (delete-pending handles outlived the file unlinks).
                    foreach (var dir in Directory.EnumerateDirectories(dayDir))
                    {
                        try
                        {
                            if (Guid.TryParseExact(Path.GetFileName(dir), "D", out _)
                                && !Directory.EnumerateFileSystemEntries(dir).Any())
                            {
                                Directory.Delete(dir, recursive: false);
                            }
                        }
                        catch { /* best-effort */ }
                    }
                }
            }
            catch { /* sweep must never block store construction */ }
        }

        internal Action<string, string>? AppendBlobManifestReplaceOverrideForTests { get; set; }
        internal Action<string, string>? ReplaceJsonBlobFileReplaceOverrideForTests { get; set; }

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

        public Artifact CreateFromFiles(
            string kind,
            IReadOnlyList<BlobFileInput> files,
            IReadOnlyList<Guid>? parentIds = null,
            IReadOnlyDictionary<string, JsonNode?>? metadata = null,
            IReadOnlyDictionary<string, JsonNode?>? flags = null)
        {
            ValidateKindArg(kind);
            ValidateFileInputsArg(files);

            var id = Guid.NewGuid();
            var now = DateTimeOffset.UtcNow;
            var dayKey = now.ToString(DayKeyFormat, CultureInfo.InvariantCulture);

            var dayDir = Path.Combine(_root, dayKey);
            var idStr = id.ToString("D");
            var finalDir = Path.Combine(dayDir, idStr);
            var tmpDir = finalDir + TempDirSuffix;

            var artifactFiles = files
                .Select(f => new ArtifactFile(f.Role, $"{f.Role}.{f.FileExtension}"))
                .ToList();

            var artifact = new Artifact(
                Id: id,
                Kind: kind,
                CreatedAt: now,
                Files: artifactFiles,
                ParentIds: parentIds is null
                    ? Array.Empty<Guid>()
                    : new List<Guid>(parentIds),
                Metadata: CloneOrEmpty(metadata),
                Flags: CloneOrEmpty(flags));

            Directory.CreateDirectory(dayDir);

            try
            {
                Directory.CreateDirectory(tmpDir);

                foreach (var file in files)
                {
                    var blobPath = Path.Combine(tmpDir, $"{file.Role}.{file.FileExtension}");
                    try
                    {
                        File.Copy(file.SourcePath, blobPath, overwrite: false);
                        ValidateCopiedBlobSize(file, blobPath);
                    }
                    catch (ArtifactBlobSizeException)
                    {
                        throw;
                    }
                    catch (Exception ex) when (
                        ex is IOException ||
                        ex is UnauthorizedAccessException ||
                        ex is NotSupportedException)
                    {
                        throw new ArtifactBlobCopyException(
                            file.Role,
                            file.SourcePath,
                            blobPath,
                            ex);
                    }
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
            => List(out _);

        /// <summary>
        /// Fail-open listing (issue #241): a corrupt artifact directory is
        /// skipped and reported in <paramref name="warnings"/> instead of
        /// throwing — one bad directory must never hide the healthy ones
        /// (it previously bricked the whole Gallery).
        /// </summary>
        public IReadOnlyList<Artifact> List(out IReadOnlyList<string> warnings)
        {
            var collected = new List<string>();
            var items = Enumerate(collected)
                .OrderByDescending(a => a.CreatedAt)
                .ThenBy(a => a.Id)
                .ToList();
            warnings = collected;
            return items;
        }

        internal IEnumerable<Artifact> Enumerate() => Enumerate(null);

        private IEnumerable<Artifact> Enumerate(List<string>? warnings)
        {
            if (!Directory.Exists(_root)) yield break;

            var seenIds = new HashSet<Guid>();
            foreach (var dayDir in Directory.EnumerateDirectories(_root)
                         .OrderByDescending(Path.GetFileName, StringComparer.Ordinal))
            {
                foreach (var artifactDir in Directory.EnumerateDirectories(dayDir)
                             .OrderBy(Path.GetFileName, StringComparer.Ordinal))
                {
                    var name = Path.GetFileName(artifactDir);
                    if (name.EndsWith(TempDirSuffix, StringComparison.Ordinal)) continue;

                    if (!Guid.TryParseExact(name, "D", out var id)) continue;

                    if (!seenIds.Add(id)) throw DuplicateUuid(id);

                    Artifact? artifact;
                    try
                    {
                        artifact = ReadArtifact(artifactDir);
                    }
                    catch (Exception ex) when (
                        ex is InvalidDataException or System.Text.Json.JsonException)
                    {
                        if (!Directory.EnumerateFileSystemEntries(artifactDir).Any())
                        {
                            // Empty GUID dir = deletion residue kept alive by
                            // a delete-pending handle. Silent skip; swept at
                            // the next store construction.
                            artifact = null;
                        }
                        else
                        {
                            // Fail-open: skip and report. Delete(id) on this
                            // artifact quarantines it for recovery.
                            warnings?.Add(
                                $"Skipped unreadable artifact directory '{artifactDir}': {ex.Message}");
                            artifact = null;
                        }
                    }

                    if (artifact is not null)
                        yield return artifact;
                }
            }
        }

        /// <summary>
        /// Delete an artifact. Healthy artifacts are removed via atomic
        /// rename-then-delete: the directory is first renamed to
        /// <c>{uuid}.deleting.tmp</c> (atomic; fails CLEAN with zero
        /// mutation if any blob is held open, e.g. by a WebView2 thumbnail
        /// stream), then recursively deleted — an interrupted removal
        /// leaves only an invisible, sweepable temp dir, never a
        /// manifest-less "corrupt" artifact (issue #241's origin class).
        ///
        /// Corrupt directories (unreadable manifest) are QUARANTINED to a
        /// sibling <c>{root}-quarantine</c> directory instead of refused:
        /// bytes are preserved for diagnosis and the store is restored.
        /// </summary>
        public bool Delete(Guid id)
        {
            var dirs = FindFinalizedDirs(id);
            if (dirs.Count == 0) return false;
            if (dirs.Count > 1) throw DuplicateUuid(id);
            var dir = dirs[0];

            bool corrupt;
            try
            {
                _ = ReadArtifact(dir);
                corrupt = false;
            }
            catch (Exception ex) when (
                ex is InvalidDataException or System.Text.Json.JsonException)
            {
                corrupt = true;
            }

            if (corrupt)
            {
                QuarantineDir(dir, id);
                return true;
            }

            var deleting = dir + DeletingTempSuffix;
            try
            {
                Directory.Move(dir, deleting); // atomic commit point
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                // Open child handles (e.g. WebView2 streaming a gallery
                // thumbnail) deny the parent rename even when the handle
                // carries FileShare.Delete. Fall back to per-file teardown
                // with MANIFEST LAST: blob streams are FileShare.Delete so
                // File.Delete succeeds (POSIX unlink) mid-stream, and the
                // manifest-last ordering means an interruption leaves a
                // still-valid artifact — never a manifest-less corrupt dir
                // (issue #241's origin class). A blob locked without
                // FileShare.Delete throws here BEFORE the manifest is
                // touched, so failure remains zero-mutation for the
                // single-blob case and never strands corruption.
                var manifest = Path.Combine(dir, ManifestFileName);
                foreach (var file in Directory.EnumerateFiles(dir))
                {
                    if (string.Equals(file, manifest, StringComparison.OrdinalIgnoreCase))
                        continue;
                    File.Delete(file);
                }
                File.Delete(manifest);
                try
                {
                    Directory.Delete(dir, recursive: false);
                }
                catch (Exception cleanupEx) when (
                    cleanupEx is IOException or UnauthorizedAccessException)
                {
                    // A delete-pending handle can keep the empty dir alive.
                    // Empty GUID dirs are silently skipped by Enumerate and
                    // swept at the next store construction.
                }
                return true;
            }

            try
            {
                Directory.Delete(deleting, recursive: true);
            }
            catch (IOException)
            {
                // Leftover .deleting.tmp is invisible; swept at next store
                // construction. The artifact is gone from the store either way.
            }
            catch (UnauthorizedAccessException)
            {
            }
            return true;
        }

        private void QuarantineDir(string dir, Guid id)
        {
            var parent = Path.GetDirectoryName(
                _root.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));
            var quarantineRoot = Path.Combine(
                parent ?? _root,
                Path.GetFileName(
                    _root.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar))
                + QuarantineDirSuffix);
            Directory.CreateDirectory(quarantineRoot);

            var target = Path.Combine(quarantineRoot, id.ToString("D"));
            if (Directory.Exists(target))
            {
                target += "-" + DateTimeOffset.UtcNow.ToString(
                    "yyyyMMddHHmmssfff", CultureInfo.InvariantCulture);
            }

            Directory.Move(dir, target);
        }

        /// <summary>
        /// Atomically update a single flag on an existing artifact. Rewrites
        /// the artifact's <c>manifest.json</c> in place; blobs and
        /// directory identity are untouched.
        ///
        /// Atomicity: writes the new manifest to
        /// <c>manifest.json.tmp</c> inside the finalized artifact directory,
        /// then swaps into place via <c>File.Replace</c> (which wraps the
        /// Windows <c>ReplaceFile</c> API and is atomic on NTFS). A crash
        /// between write-and-swap leaves a stray <c>manifest.json.tmp</c>
        /// file that is invisible to <see cref="List"/> (directory
        /// enumeration only) and <see cref="Get"/>/<see cref="Delete"/>
        /// (they read <c>manifest.json</c>); the next <see cref="SetFlag"/>
        /// call overwrites it. A startup sweep for orphans is a v2
        /// affordance.
        ///
        /// Validation re-runs on read before mutation: a manifest that no
        /// longer passes <see cref="ParseAndValidate"/> surfaces as
        /// corruption and the mutation is rejected — we refuse to
        /// write-over an unreadable manifest.
        ///
        /// Idempotent: setting a flag to the value it already holds is a
        /// successful no-op-shaped call (the manifest is re-serialized,
        /// but semantically nothing changes).
        ///
        /// Single-writer assumption holds — no cross-process lock. A v1
        /// race between two concurrent <see cref="SetFlag"/> calls on the
        /// same artifact may lose one update.
        /// </summary>
        /// <param name="id">Artifact identity (matches directory name).</param>
        /// <param name="name">Flag name — snake-case, same pattern as
        /// <c>kind</c>/<c>role</c>.</param>
        /// <param name="value">Flag value. Must be non-null. v1 has no
        /// unset/remove affordance; if a consumer needs to clear a flag,
        /// set it to a sentinel (e.g. <c>false</c>) instead.</param>
        /// <returns>The updated <see cref="Artifact"/>.</returns>
        /// <exception cref="ArgumentNullException">If <paramref name="name"/>
        /// or <paramref name="value"/> is null.</exception>
        /// <exception cref="ArgumentException">If <paramref name="name"/>
        /// fails the flag-name pattern.</exception>
        /// <exception cref="KeyNotFoundException">If no finalized artifact
        /// directory exists for <paramref name="id"/>.</exception>
        /// <exception cref="InvalidDataException">If the current manifest
        /// is corrupt or duplicate UUIDs exist across day buckets.</exception>
        public Artifact SetFlag(Guid id, string name, JsonNode value)
        {
            ValidateFlagNameArg(name);
            if (value is null)
            {
                throw new ArgumentNullException(
                    nameof(value),
                    "SetFlag requires a non-null value; v1 has no unset/remove affordance.");
            }

            var dirs = FindFinalizedDirs(id);
            if (dirs.Count == 0)
                throw new KeyNotFoundException($"Artifact '{id}' not found.");
            if (dirs.Count > 1) throw DuplicateUuid(id);

            var artifactDir = dirs[0];
            var existing = ReadArtifact(artifactDir);

            var newFlags = new Dictionary<string, JsonNode?>(StringComparer.Ordinal);
            foreach (var kvp in existing.Flags)
            {
                newFlags[kvp.Key] = kvp.Value?.DeepClone();
            }
            // DeepClone the incoming value — caller retains ownership of
            // the JsonNode they passed, and we don't want mutations they
            // make later to leak into the stored manifest.
            newFlags[name] = value.DeepClone();

            var updated = new Artifact(
                existing.Id,
                existing.Kind,
                existing.CreatedAt,
                existing.Files,
                existing.ParentIds,
                existing.Metadata,
                newFlags);

            var manifestPath = Path.Combine(artifactDir, ManifestFileName);
            var tmpManifestPath = Path.Combine(artifactDir, ManifestFileName + ".tmp");

            File.WriteAllText(tmpManifestPath, SerializeManifest(updated));

            // File.Replace is atomic on Windows (ReplaceFile API) and
            // requires the destination to exist — which it does, because
            // the directory is finalized. destinationBackupFileName is
            // null: we already have the .tmp-before-replace step for
            // crash safety, no need for a second backup.
            File.Replace(
                sourceFileName: tmpManifestPath,
                destinationFileName: manifestPath,
                destinationBackupFileName: null);

            return updated;
        }

        public AppendBlobResult AppendBlob(
            Guid id,
            string role,
            byte[] content,
            string fileExtension)
        {
            try
            {
                ValidateRoleArg(role);
            }
            catch (Exception ex) when (ex is ArgumentException || ex is ArgumentNullException)
            {
                return AppendBlobResult.Fail(AppendBlobResultCode.InvalidRole, ex.Message);
            }

            try
            {
                ValidateExtensionArg(fileExtension);
            }
            catch (Exception ex) when (ex is ArgumentException || ex is ArgumentNullException)
            {
                return AppendBlobResult.Fail(AppendBlobResultCode.InvalidExtension, ex.Message);
            }

            if (content is null)
            {
                return AppendBlobResult.Fail(
                    AppendBlobResultCode.StagedWriteFailed,
                    "AppendBlob content is null.");
            }

            var dirs = FindFinalizedDirs(id);
            if (dirs.Count == 0)
                return AppendBlobResult.Fail(
                    AppendBlobResultCode.ArtifactNotFound,
                    $"Artifact '{id}' not found.");
            if (dirs.Count > 1)
                return AppendBlobResult.Fail(
                    AppendBlobResultCode.ManifestReadFailed,
                    DuplicateUuid(id).Message);

            var artifactDir = dirs[0];
            Artifact existing;
            try
            {
                existing = ReadArtifact(artifactDir);
            }
            catch (Exception ex)
            {
                return AppendBlobResult.Fail(
                    AppendBlobResultCode.ManifestReadFailed,
                    ex.Message);
            }

            if (existing.Files.Any(f => f.Role == role))
            {
                return AppendBlobResult.Fail(
                    AppendBlobResultCode.DuplicateRole,
                    $"Role '{role}' already exists in artifact '{id}'.");
            }

            var finalFileName = $"{role}.{fileExtension}";
            var finalPath = Path.Combine(artifactDir, finalFileName);
            if (File.Exists(finalPath))
            {
                return AppendBlobResult.Fail(
                    AppendBlobResultCode.FinalFileCollision,
                    $"File '{finalFileName}' already exists in artifact '{id}' without a manifest role.");
            }

            var stagedFileName = $"{role}.{Guid.NewGuid():N}.{fileExtension}.tmp";
            var stagedPath = Path.Combine(artifactDir, stagedFileName);

            try
            {
                File.WriteAllBytes(stagedPath, content);
            }
            catch (Exception ex)
            {
                return AppendBlobResult.Fail(
                    AppendBlobResultCode.StagedWriteFailed,
                    ex.Message);
            }

            try
            {
                File.Move(stagedPath, finalPath);
            }
            catch (Exception ex)
            {
                TryDeleteFile(stagedPath);
                return AppendBlobResult.Fail(
                    AppendBlobResultCode.FinalizeBlobFailed,
                    ex.Message);
            }

            var updatedFiles = existing.Files
                .Concat(new[] { new ArtifactFile(role, finalFileName) })
                .ToList();
            var updated = new Artifact(
                existing.Id,
                existing.Kind,
                existing.CreatedAt,
                updatedFiles,
                existing.ParentIds,
                existing.Metadata,
                existing.Flags);

            var manifestPath = Path.Combine(artifactDir, ManifestFileName);
            var tmpManifestPath = Path.Combine(artifactDir, ManifestFileName + ".tmp");

            try
            {
                File.WriteAllText(tmpManifestPath, SerializeManifest(updated));
                if (AppendBlobManifestReplaceOverrideForTests is not null)
                {
                    AppendBlobManifestReplaceOverrideForTests(tmpManifestPath, manifestPath);
                }
                else
                {
                    File.Replace(
                        sourceFileName: tmpManifestPath,
                        destinationFileName: manifestPath,
                        destinationBackupFileName: null);
                }
            }
            catch (Exception ex)
            {
                TryDeleteFile(tmpManifestPath);
                return AppendBlobResult.Fail(
                    AppendBlobResultCode.ManifestReplaceFailed,
                    ex.Message);
            }

            return AppendBlobResult.Succeeded(updated);
        }

        public ReplaceJsonBlobResult ReplaceJsonBlob(
            Guid id,
            string role,
            JsonNode content)
        {
            try
            {
                ValidateRoleArg(role);
            }
            catch (Exception ex) when (ex is ArgumentException || ex is ArgumentNullException)
            {
                return ReplaceJsonBlobResult.Fail(
                    ReplaceJsonBlobResultCode.InvalidRole,
                    ex.Message);
            }

            if (content is null)
            {
                return ReplaceJsonBlobResult.Fail(
                    ReplaceJsonBlobResultCode.StagedWriteFailed,
                    "ReplaceJsonBlob content is null.");
            }

            var dirs = FindFinalizedDirs(id);
            if (dirs.Count == 0)
                return ReplaceJsonBlobResult.Fail(
                    ReplaceJsonBlobResultCode.ArtifactNotFound,
                    $"Artifact '{id}' not found.");
            if (dirs.Count > 1)
                return ReplaceJsonBlobResult.Fail(
                    ReplaceJsonBlobResultCode.ManifestReadFailed,
                    DuplicateUuid(id).Message);

            var artifactDir = dirs[0];
            Artifact existing;
            try
            {
                existing = ReadArtifact(artifactDir);
            }
            catch (Exception ex)
            {
                return ReplaceJsonBlobResult.Fail(
                    ReplaceJsonBlobResultCode.ManifestReadFailed,
                    ex.Message);
            }

            var file = existing.Files.FirstOrDefault(f => f.Role == role);
            if (file is null)
            {
                return ReplaceJsonBlobResult.Fail(
                    ReplaceJsonBlobResultCode.RoleNotFound,
                    $"Artifact '{id}' has no blob role '{role}'.");
            }

            if (!string.Equals(
                    Path.GetExtension(file.Path),
                    ".json",
                    StringComparison.OrdinalIgnoreCase))
            {
                return ReplaceJsonBlobResult.Fail(
                    ReplaceJsonBlobResultCode.RoleIsNotJson,
                    $"Blob role '{role}' is not a JSON blob.");
            }

            var finalPath = Path.Combine(artifactDir, file.Path);
            var tmpPath = finalPath + ".tmp-" + Guid.NewGuid().ToString("N");

            try
            {
                File.WriteAllText(tmpPath, content.ToJsonString(), Encoding.UTF8);
            }
            catch (Exception ex)
            {
                TryDeleteFile(tmpPath);
                return ReplaceJsonBlobResult.Fail(
                    ReplaceJsonBlobResultCode.StagedWriteFailed,
                    ex.Message);
            }

            try
            {
                if (ReplaceJsonBlobFileReplaceOverrideForTests is not null)
                {
                    ReplaceJsonBlobFileReplaceOverrideForTests(tmpPath, finalPath);
                }
                else
                {
                    File.Replace(
                        sourceFileName: tmpPath,
                        destinationFileName: finalPath,
                        destinationBackupFileName: null);
                }
            }
            catch (Exception ex)
            {
                TryDeleteFile(tmpPath);
                return ReplaceJsonBlobResult.Fail(
                    ReplaceJsonBlobResultCode.FinalizeBlobFailed,
                    ex.Message);
            }

            try
            {
                return ReplaceJsonBlobResult.Succeeded(ReadArtifact(artifactDir));
            }
            catch (Exception ex)
            {
                return ReplaceJsonBlobResult.Fail(
                    ReplaceJsonBlobResultCode.ManifestReadFailed,
                    ex.Message);
            }
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

        private static void TryDeleteFile(string path)
        {
            try
            {
                if (File.Exists(path))
                    File.Delete(path);
            }
            catch { /* best-effort cleanup only */ }
        }

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

        private static void ValidateFileInputsArg(IReadOnlyList<BlobFileInput> files)
        {
            if (files is null) throw new ArgumentNullException(nameof(files));
            if (files.Count == 0)
                throw new ArgumentException("files must be non-empty.", nameof(files));

            var seen = new HashSet<string>(StringComparer.Ordinal);
            for (int i = 0; i < files.Count; i++)
            {
                var f = files[i];
                if (f is null)
                    throw new ArgumentException($"files[{i}] is null.", nameof(files));
                if (f.SourcePath is null)
                    throw new ArgumentException($"files[{i}].SourcePath is null.", nameof(files));

                ValidateRoleArg(f.Role);
                ValidateExtensionArg(f.FileExtension);
                if (f.MaxBytes.HasValue && f.MaxBytes.Value < 0)
                    throw new ArgumentException(
                        $"files[{i}].MaxBytes must be non-negative.",
                        nameof(files));
                if (f.ExpectedBytes.HasValue && f.ExpectedBytes.Value < 0)
                    throw new ArgumentException(
                        $"files[{i}].ExpectedBytes must be non-negative.",
                        nameof(files));

                if (!seen.Add(f.Role))
                    throw new ArgumentException(
                        $"duplicate file role '{f.Role}'.", nameof(files));

                FileAttributes attributes;
                try
                {
                    attributes = File.GetAttributes(f.SourcePath);
                }
                catch (Exception ex) when (
                    ex is FileNotFoundException ||
                    ex is DirectoryNotFoundException)
                {
                    throw new FileNotFoundException(
                        $"Source file '{f.SourcePath}' not found.",
                        f.SourcePath,
                        ex);
                }

                if ((attributes & FileAttributes.Directory) == FileAttributes.Directory)
                    throw new ArgumentException(
                        $"files[{i}].SourcePath must be a file, not a directory.",
                        nameof(files));

                if (!File.Exists(f.SourcePath))
                    throw new FileNotFoundException(
                        $"Source file '{f.SourcePath}' not found.",
                        f.SourcePath);
            }
        }

        private static void ValidateCopiedBlobSize(
            BlobFileInput file,
            string blobPath)
        {
            if (!file.MaxBytes.HasValue && !file.ExpectedBytes.HasValue)
                return;

            var actualBytes = new FileInfo(blobPath).Length;
            if (file.MaxBytes.HasValue && actualBytes > file.MaxBytes.Value)
            {
                throw new ArtifactBlobSizeException(
                    file.Role,
                    blobPath,
                    actualBytes,
                    file.MaxBytes,
                    file.ExpectedBytes);
            }

            if (file.ExpectedBytes.HasValue && actualBytes != file.ExpectedBytes.Value)
            {
                throw new ArtifactBlobSizeException(
                    file.Role,
                    blobPath,
                    actualBytes,
                    file.MaxBytes,
                    file.ExpectedBytes);
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

        private static void ValidateFlagNameArg(string name)
        {
            if (name is null) throw new ArgumentNullException(nameof(name));
            if (string.IsNullOrWhiteSpace(name))
                throw new ArgumentException("flag name must be non-empty.", nameof(name));
            // Flag names reuse the snake-case pattern enforced on kind and
            // role to keep on-disk JSON field naming uniform.
            if (!KindPattern.IsMatch(name))
                throw new ArgumentException(
                    $"flag name '{name}' does not match required pattern.", nameof(name));
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
