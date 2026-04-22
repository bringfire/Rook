using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Rook
{
    /// <summary>
    /// Persistent, section-based settings store backed by a single JSON file
    /// at <see cref="RookPaths.SettingsFile"/> (overridable for tests).
    ///
    /// Sections are typed: callers serialize their own shape via
    /// <see cref="LoadSection{T}"/> / <see cref="SaveSection{T}"/>. The store
    /// preserves unrelated sections on every write.
    ///
    /// Single-writer assumption — no cross-process locking in v1. Revisit if
    /// a second writer appears.
    ///
    /// Failure semantics:
    /// <list type="bullet">
    ///   <item>file missing → <see cref="LoadSection{T}"/> returns <c>null</c></item>
    ///   <item>section missing → <see cref="LoadSection{T}"/> returns <c>null</c></item>
    ///   <item>malformed file JSON → throws (does not silently overwrite)</item>
    ///   <item>malformed section payload → throws</item>
    /// </list>
    /// </summary>
    public sealed class RookSettingsStore
    {
        private const string SchemaVersionField = "schemaVersion";
        private const string SectionsField = "sections";
        private const int CurrentSchemaVersion = 1;

        private static readonly JsonSerializerOptions WriteOptions = new()
        {
            WriteIndented = true,
        };

        private readonly string _filePath;
        private readonly string _directory;

        public RookSettingsStore() : this(null) { }

        public RookSettingsStore(string? overridePath)
        {
            _filePath = overridePath ?? RookPaths.SettingsFile;
            _directory = Path.GetDirectoryName(_filePath)
                ?? throw new ArgumentException(
                    "Settings path must include a directory.", nameof(overridePath));
        }

        public T? LoadSection<T>(string sectionName) where T : class
        {
            ValidateSectionName(sectionName);

            var sections = ReadSections();
            if (sections is null) return null;

            if (!sections.TryGetPropertyValue(sectionName, out var sectionNode) || sectionNode is null)
                return null;

            return JsonSerializer.Deserialize<T>(sectionNode.ToJsonString());
        }

        public void SaveSection<T>(string sectionName, T value) where T : class
        {
            ValidateSectionName(sectionName);
            if (value is null) throw new ArgumentNullException(nameof(value));

            var root = ReadRoot();
            JsonObject sections;

            if (root is null)
            {
                root = new JsonObject
                {
                    [SchemaVersionField] = CurrentSchemaVersion,
                    [SectionsField] = new JsonObject(),
                };
                sections = (JsonObject)root[SectionsField]!;
            }
            else if (!root.ContainsKey(SectionsField))
            {
                sections = new JsonObject();
                root[SectionsField] = sections;
            }
            else if (root[SectionsField] is JsonObject existing)
            {
                sections = existing;
            }
            else
            {
                // Present but non-object → corrupt schema. Refuse to overwrite.
                throw new InvalidDataException(
                    $"Settings file '{_filePath}' has '{SectionsField}' field that is not a JSON object.");
            }

            sections[sectionName] = JsonSerializer.SerializeToNode(value);

            WriteRoot(root);
        }

        public bool SectionExists(string sectionName)
        {
            ValidateSectionName(sectionName);

            var sections = ReadSections();
            return sections is not null && sections.ContainsKey(sectionName);
        }

        // ─── internals ──────────────────────────────────────────────

        private JsonObject? ReadRoot()
        {
            if (!File.Exists(_filePath)) return null;

            string content = File.ReadAllText(_filePath);
            var node = JsonNode.Parse(content);

            if (node is JsonObject root) return root;

            throw new InvalidDataException(
                $"Settings file '{_filePath}' root is not a JSON object.");
        }

        private JsonObject? ReadSections()
        {
            var root = ReadRoot();
            if (root is null) return null;

            // Sections field absent → optional, treat as empty.
            if (!root.ContainsKey(SectionsField)) return null;

            if (root[SectionsField] is JsonObject sections) return sections;

            // Present but non-object (string, array, null, etc.) → corrupt schema.
            throw new InvalidDataException(
                $"Settings file '{_filePath}' has '{SectionsField}' field that is not a JSON object.");
        }

        private void WriteRoot(JsonObject root)
        {
            Directory.CreateDirectory(_directory);

            string tmpPath = _filePath + ".tmp";
            string serialized = root.ToJsonString(WriteOptions);
            File.WriteAllText(tmpPath, serialized);

            if (File.Exists(_filePath))
            {
                File.Replace(tmpPath, _filePath, destinationBackupFileName: null);
            }
            else
            {
                File.Move(tmpPath, _filePath);
            }
        }

        private static void ValidateSectionName(string sectionName)
        {
            if (string.IsNullOrWhiteSpace(sectionName))
            {
                throw new ArgumentException(
                    "Section name must be non-null and non-whitespace.", nameof(sectionName));
            }
        }
    }
}
