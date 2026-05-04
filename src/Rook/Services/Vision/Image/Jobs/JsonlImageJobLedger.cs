using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Jobs
{
    /// <summary>
    /// Append-only JSONL persistence for image job snapshots.
    /// Each line is a complete record; reads compact by job_id with
    /// last line wins semantics.
    /// </summary>
    public sealed class JsonlImageJobLedger : IImageJobLedger
    {
        private readonly string _filePath;
        private readonly object _lock = new();

        public JsonlImageJobLedger() : this(DefaultPath()) { }

        public JsonlImageJobLedger(string filePath)
        {
            if (string.IsNullOrWhiteSpace(filePath))
                throw new ArgumentException(
                    "filePath must be non-empty.", nameof(filePath));
            _filePath = filePath;
        }

        public string FilePath => _filePath;

        public static string DefaultPath()
        {
            return Path.Combine(RookPaths.SettingsRoot, "image", "job-ledger.jsonl");
        }

        public void Append(ImageJobLedgerRecord record)
        {
            if (record is null) throw new ArgumentNullException(nameof(record));

            var line = SerializeRecord(SanitizeRecord(record));

            lock (_lock)
            {
                var dir = Path.GetDirectoryName(_filePath);
                if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
                    Directory.CreateDirectory(dir);

                using var stream = new FileStream(
                    _filePath,
                    FileMode.Append,
                    FileAccess.Write,
                    FileShare.Read);
                using var writer = new StreamWriter(stream, new UTF8Encoding(false));
                writer.WriteLine(line);
            }
        }

        public ImageJobLedgerReadResult ReadAll()
        {
            if (!File.Exists(_filePath))
                return new ImageJobLedgerReadResult(
                    Array.Empty<ImageJobLedgerRecord>(),
                    Array.Empty<ImageJobLedgerReadError>());

            string[] lines;
            lock (_lock)
            {
                lines = File.ReadAllLines(_filePath, Encoding.UTF8);
            }

            var byJobId = new Dictionary<Guid, ImageJobLedgerRecord>();
            var errors = new List<ImageJobLedgerReadError>();

            for (var i = 0; i < lines.Length; i++)
            {
                var line = lines[i];
                if (string.IsNullOrWhiteSpace(line)) continue;

                var (record, error) = TryDeserialize(line, i + 1);
                if (error is not null)
                {
                    errors.Add(error);
                    continue;
                }

                byJobId[record!.JobId] = record;
            }

            return new ImageJobLedgerReadResult(byJobId.Values.ToArray(), errors);
        }

        private static ImageJobLedgerRecord SanitizeRecord(ImageJobLedgerRecord record)
        {
            return record with
            {
                Error = ImageJobLedgerRecordFactory.SanitizeError(record.Error),
            };
        }

        private static string SerializeRecord(ImageJobLedgerRecord r)
        {
            var obj = new JsonObject
            {
                ["schema_version"] = r.SchemaVersion,
                ["job_id"] = r.JobId.ToString("D"),
                ["provider"] = r.Provider,
                ["model"] = r.Model,
                ["provider_job_id"] = r.ProviderJobId,
                ["state"] = r.State.ToString(),
                ["result_artifact_id"] = r.ResultArtifactId?.ToString("D"),
                ["error"] = r.Error is null ? null : SerializeError(r.Error),
                ["created_at"] = r.CreatedAt.ToString("o", CultureInfo.InvariantCulture),
                ["updated_at"] = r.UpdatedAt.ToString("o", CultureInfo.InvariantCulture),
            };

            return obj.ToJsonString(new JsonSerializerOptions
            {
                WriteIndented = false,
            });
        }

        private static JsonObject SerializeError(GenerationError error)
        {
            var obj = new JsonObject
            {
                ["code"] = error.Code.ToString(),
                ["message"] = error.Message,
                ["retryable"] = error.Retryable,
                ["field"] = error.Field,
                ["provider_error_code"] = error.ProviderErrorCode,
            };
            return obj;
        }

        private static (ImageJobLedgerRecord? Record, ImageJobLedgerReadError? Error)
            TryDeserialize(string line, int lineNumber)
        {
            JsonNode? root;
            try
            {
                root = JsonNode.Parse(line);
            }
            catch (JsonException)
            {
                return (null, Malformed(lineNumber, "Malformed JSON ledger line."));
            }

            if (root is not JsonObject obj)
                return (null, Malformed(
                    lineNumber,
                    "Top-level JSON ledger line must be an object."));

            var schemaVersion = TryGetInt(obj, "schema_version");
            if (schemaVersion is null)
                return (null, MissingField(lineNumber, "schema_version"));
            if (schemaVersion.Value != ImageJobLedgerRecordFactory.CurrentSchemaVersion)
                return (null, new ImageJobLedgerReadError(
                    lineNumber,
                    ImageJobLedgerReadErrorReason.UnsupportedSchemaVersion,
                    "Unsupported image job ledger schema version.",
                    "schema_version"));

            var jobIdText = TryGetString(obj, "job_id");
            if (jobIdText is null
                || !Guid.TryParse(jobIdText, out var jobId)
                || jobId == Guid.Empty)
                return (null, MissingField(lineNumber, "job_id"));

            var provider = TryGetString(obj, "provider");
            if (string.IsNullOrWhiteSpace(provider))
                return (null, MissingField(lineNumber, "provider"));

            var model = TryGetString(obj, "model");
            if (string.IsNullOrWhiteSpace(model))
                return (null, MissingField(lineNumber, "model"));

            var stateText = TryGetString(obj, "state");
            if (stateText is null
                || !Enum.TryParse<ImageJobState>(stateText, out var state)
                || !Enum.IsDefined(typeof(ImageJobState), state))
                return (null, MissingField(lineNumber, "state"));

            var providerJobId = TryGetString(obj, "provider_job_id");

            Guid? resultArtifactId = null;
            var resultArtifactIdText = TryGetString(obj, "result_artifact_id");
            if (resultArtifactIdText is not null)
            {
                if (!Guid.TryParse(resultArtifactIdText, out var parsed)
                    || parsed == Guid.Empty)
                    return (null, MissingField(lineNumber, "result_artifact_id"));
                resultArtifactId = parsed;
            }
            if (state == ImageJobState.Complete && resultArtifactId is null)
                return (null, MissingField(lineNumber, "result_artifact_id"));

            GenerationError? error = null;
            var errorObj = TryGetObject(obj, "error");
            if (errorObj is not null)
            {
                var (parsedError, readError) = DeserializeError(errorObj, lineNumber);
                if (readError is not null) return (null, readError);
                error = parsedError;
            }

            var createdAtText = TryGetString(obj, "created_at");
            var updatedAtText = TryGetString(obj, "updated_at");
            if (createdAtText is null
                || !TryParseTimestamp(createdAtText, out var createdAt))
                return (null, MissingField(lineNumber, "created_at"));
            if (updatedAtText is null
                || !TryParseTimestamp(updatedAtText, out var updatedAt))
                return (null, MissingField(lineNumber, "updated_at"));

            return (new ImageJobLedgerRecord(
                SchemaVersion: schemaVersion.Value,
                JobId: jobId,
                Provider: provider,
                Model: model,
                ProviderJobId: providerJobId,
                State: state,
                ResultArtifactId: resultArtifactId,
                Error: error,
                CreatedAt: createdAt,
                UpdatedAt: updatedAt), null);
        }

        private static (GenerationError? Error, ImageJobLedgerReadError? ReadError)
            DeserializeError(JsonObject obj, int lineNumber)
        {
            var codeText = TryGetString(obj, "code");
            if (codeText is null
                || !Enum.TryParse<GenerationErrorCode>(codeText, out var code)
                || !Enum.IsDefined(typeof(GenerationErrorCode), code))
                return (null, MissingField(lineNumber, "error.code"));

            var message = TryGetString(obj, "message");
            if (message is null)
                return (null, MissingField(lineNumber, "error.message"));

            var retryable = TryGetBool(obj, "retryable");
            if (retryable is null)
                return (null, MissingField(lineNumber, "error.retryable"));

            var error = new GenerationError(
                code,
                message,
                retryable.Value,
                Field: TryGetString(obj, "field"),
                ProviderErrorCode: TryGetString(obj, "provider_error_code"),
                ProviderDetail: null);

            return (ImageJobLedgerRecordFactory.SanitizeError(error), null);
        }

        private static bool TryParseTimestamp(
            string value,
            out DateTimeOffset timestamp)
        {
            return DateTimeOffset.TryParse(
                value,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal,
                out timestamp);
        }

        private static string? TryGetString(JsonObject obj, string key)
        {
            if (!obj.TryGetPropertyValue(key, out var node) || node is null)
                return null;
            try { return node.GetValue<string>(); } catch { return null; }
        }

        private static int? TryGetInt(JsonObject obj, string key)
        {
            if (!obj.TryGetPropertyValue(key, out var node) || node is null)
                return null;
            try { return node.GetValue<int>(); } catch { return null; }
        }

        private static bool? TryGetBool(JsonObject obj, string key)
        {
            if (!obj.TryGetPropertyValue(key, out var node) || node is null)
                return null;
            try { return node.GetValue<bool>(); } catch { return null; }
        }

        private static JsonObject? TryGetObject(JsonObject obj, string key)
        {
            if (!obj.TryGetPropertyValue(key, out var node)) return null;
            return node as JsonObject;
        }

        private static ImageJobLedgerReadError MissingField(
            int lineNumber,
            string fieldPath)
        {
            return new ImageJobLedgerReadError(
                lineNumber,
                ImageJobLedgerReadErrorReason.MissingRequiredField,
                $"Required field missing or malformed: {fieldPath}.",
                fieldPath);
        }

        private static ImageJobLedgerReadError Malformed(
            int lineNumber,
            string message)
        {
            return new ImageJobLedgerReadError(
                lineNumber,
                ImageJobLedgerReadErrorReason.MalformedJson,
                message,
                FieldPath: null);
        }
    }
}
