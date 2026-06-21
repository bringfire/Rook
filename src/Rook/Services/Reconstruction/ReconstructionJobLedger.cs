using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Rook.Services.Reconstruction;

public sealed record ReconstructionPreprocessingStageRecord(
    Guid StageId,
    string Role,
    string Provider,
    string ModelId,
    ReconstructionJobState State,
    Guid InputArtifactId,
    Guid? OutputArtifactId,
    string? ProviderJobId,
    ReconstructionFailure? Error);

public sealed record ReconstructionJobLedgerRecord(
    int SchemaVersion,
    Guid JobId,
    ReconstructionJobState State,
    ReconstructionJobStage Stage,
    string Provider,
    string ModelId,
    string? ProviderJobId,
    string? ProviderStatusUrl,
    string? ProviderResponseUrl,
    string? ProviderCancelUrl,
    string? ProviderCancelHttpMethod,
    Guid SourceArtifactId,
    string SourceRole,
    IReadOnlyList<ReconstructionPreprocessingStageRecord> PreprocessingChain,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt,
    Guid? ResultArtifactId,
    bool ResultAvailable,
    ReconstructionFailure? Error,
    bool TextureExpected)
{
    public const int CurrentSchemaVersion = 2;

    public static ReconstructionJobLedgerRecord Queued(
        Guid jobId,
        string modelId,
        Guid sourceArtifactId,
        string sourceRole,
        bool textureExpected = false)
    {
        var now = DateTimeOffset.UtcNow;
        return new ReconstructionJobLedgerRecord(
            CurrentSchemaVersion,
            jobId,
            ReconstructionJobState.Queued,
            ReconstructionJobStage.Queued,
            "fal",
            modelId,
            null,
            null,
            null,
            null,
            null,
            sourceArtifactId,
            sourceRole,
            Array.Empty<ReconstructionPreprocessingStageRecord>(),
            now,
            now,
            null,
            false,
            null,
            textureExpected);
    }

    public static ReconstructionJobLedgerRecord Complete(Guid jobId, Guid resultArtifactId)
    {
        var now = DateTimeOffset.UtcNow;
        return new ReconstructionJobLedgerRecord(
            CurrentSchemaVersion,
            jobId,
            ReconstructionJobState.Complete,
            ReconstructionJobStage.Complete,
            "fal",
            string.Empty,
            null,
            null,
            null,
            null,
            null,
            Guid.Empty,
            "image",
            Array.Empty<ReconstructionPreprocessingStageRecord>(),
            now,
            now,
            resultArtifactId,
            true,
            null,
            false);
    }
}

public sealed record ReconstructionJobListResult(
    IReadOnlyList<ReconstructionJobLedgerRecord> Jobs,
    int AppliedLimit,
    IReadOnlyList<ReconstructionWarning> Warnings);

public sealed class JsonlReconstructionJobLedger
{
    private readonly string _filePath;
    private readonly object _lock = new();

    public JsonlReconstructionJobLedger(string filePath)
    {
        if (string.IsNullOrWhiteSpace(filePath))
            throw new ArgumentException("filePath must be non-empty.", nameof(filePath));
        _filePath = filePath;
    }

    public string FilePath => _filePath;

    public static string DefaultPath()
        => Path.Combine(RookPaths.SettingsRoot, "reconstruction", "job-ledger.jsonl");

    public void Append(ReconstructionJobLedgerRecord record)
    {
        if (record is null) throw new ArgumentNullException(nameof(record));

        var line = Serialize(record);
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

    public ReconstructionJobListResult List(int limit)
    {
        var appliedLimit = Math.Max(1, limit);
        if (!File.Exists(_filePath))
        {
            return new ReconstructionJobListResult(
                Array.Empty<ReconstructionJobLedgerRecord>(),
                appliedLimit,
                Array.Empty<ReconstructionWarning>());
        }

        string[] lines;
        lock (_lock)
        {
            lines = File.ReadAllLines(_filePath, Encoding.UTF8);
        }

        var warnings = new List<ReconstructionWarning>();
        var byJob = new Dictionary<Guid, ReconstructionJobLedgerRecord>();
        for (var i = 0; i < lines.Length; i++)
        {
            if (string.IsNullOrWhiteSpace(lines[i])) continue;
            var parsed = TryDeserialize(lines[i], i + 1, out var warning);
            if (warning is not null)
            {
                warnings.Add(warning);
                continue;
            }

            var previous = byJob.TryGetValue(parsed!.JobId, out var existing)
                ? existing
                : null;
            byJob[parsed.JobId] = Merge(previous, parsed);
        }

        return new ReconstructionJobListResult(
            byJob.Values
                .OrderByDescending(j => j.UpdatedAt)
                .ThenBy(j => j.JobId)
                .Take(appliedLimit)
                .ToArray(),
            appliedLimit,
            warnings);
    }

    private static ReconstructionJobLedgerRecord Merge(
        ReconstructionJobLedgerRecord? previous,
        ReconstructionJobLedgerRecord current)
    {
        if (previous is null) return current;

        return current with
        {
            Provider = string.IsNullOrWhiteSpace(current.Provider)
                ? previous.Provider
                : current.Provider,
            ModelId = string.IsNullOrWhiteSpace(current.ModelId)
                ? previous.ModelId
                : current.ModelId,
            ProviderJobId = current.ProviderJobId ?? previous.ProviderJobId,
            ProviderStatusUrl = current.ProviderStatusUrl ?? previous.ProviderStatusUrl,
            ProviderResponseUrl = current.ProviderResponseUrl ?? previous.ProviderResponseUrl,
            ProviderCancelUrl = current.ProviderCancelUrl ?? previous.ProviderCancelUrl,
            ProviderCancelHttpMethod = current.ProviderCancelHttpMethod ?? previous.ProviderCancelHttpMethod,
            SourceArtifactId = current.SourceArtifactId == Guid.Empty
                ? previous.SourceArtifactId
                : current.SourceArtifactId,
            SourceRole = string.IsNullOrWhiteSpace(current.SourceRole)
                ? previous.SourceRole
                : current.SourceRole,
            PreprocessingChain = current.PreprocessingChain.Count == 0
                ? previous.PreprocessingChain
                : current.PreprocessingChain,
            CreatedAt = previous.CreatedAt,
        };
    }

    private static string Serialize(ReconstructionJobLedgerRecord record)
    {
        var root = new JsonObject
        {
            ["schema_version"] = record.SchemaVersion,
            ["job_id"] = record.JobId.ToString("D"),
            ["state"] = record.State.ToString(),
            ["stage"] = record.Stage.ToString(),
            ["provider"] = record.Provider,
            ["model_id"] = record.ModelId,
            ["provider_job_id"] = record.ProviderJobId,
            ["provider_status_url"] = record.ProviderStatusUrl,
            ["provider_response_url"] = record.ProviderResponseUrl,
            ["provider_cancel_url"] = record.ProviderCancelUrl,
            ["provider_cancel_http_method"] = record.ProviderCancelHttpMethod,
            ["source_artifact_id"] = record.SourceArtifactId == Guid.Empty
                ? null
                : record.SourceArtifactId.ToString("D"),
            ["source_role"] = record.SourceRole,
            ["created_at"] = record.CreatedAt.ToString("O", CultureInfo.InvariantCulture),
            ["updated_at"] = record.UpdatedAt.ToString("O", CultureInfo.InvariantCulture),
            ["result_artifact_id"] = record.ResultArtifactId?.ToString("D"),
            ["result_available"] = record.ResultAvailable,
            ["texture_expected"] = record.TextureExpected,
            ["preprocessing_chain"] = new JsonArray(record.PreprocessingChain
                .Select(SerializeStage)
                .ToArray<JsonNode?>()),
            ["error"] = record.Error is null ? null : SerializeFailure(record.Error),
        };

        return root.ToJsonString(new JsonSerializerOptions { WriteIndented = false });
    }

    private static JsonObject SerializeStage(ReconstructionPreprocessingStageRecord stage)
        => new()
        {
            ["stage_id"] = stage.StageId.ToString("D"),
            ["role"] = stage.Role,
            ["provider"] = stage.Provider,
            ["model_id"] = stage.ModelId,
            ["state"] = stage.State.ToString(),
            ["input_artifact_id"] = stage.InputArtifactId.ToString("D"),
            ["output_artifact_id"] = stage.OutputArtifactId?.ToString("D"),
            ["provider_job_id"] = stage.ProviderJobId,
            ["error"] = stage.Error is null ? null : SerializeFailure(stage.Error),
        };

    private static JsonObject SerializeFailure(ReconstructionFailure failure)
    {
        var details = new JsonObject();
        foreach (var kvp in failure.Details)
        {
            details[kvp.Key] = kvp.Value is null
                ? null
                : JsonValue.Create(kvp.Value.ToString());
        }

        return new JsonObject
        {
            ["code"] = failure.Code,
            ["message"] = failure.Message,
            ["retryable"] = failure.Retryable,
            ["field"] = failure.Field,
            ["details"] = details,
        };
    }

    private static ReconstructionJobLedgerRecord? TryDeserialize(
        string line,
        int lineNumber,
        out ReconstructionWarning? warning)
    {
        warning = null;
        JsonObject obj;
        try
        {
            obj = JsonNode.Parse(line) as JsonObject
                ?? throw new JsonException("Ledger line must be an object.");
        }
        catch (JsonException ex)
        {
            warning = Warning(lineNumber, "malformed_json", ex.Message);
            return null;
        }

        var schemaVersion = ReadInt(obj, "schema_version");
        if (schemaVersion < 1 || schemaVersion > ReconstructionJobLedgerRecord.CurrentSchemaVersion)
        {
            warning = Warning(lineNumber, "unsupported_schema_version", "Unsupported ledger schema version.");
            return null;
        }

        if (!TryReadGuid(obj, "job_id", out var jobId))
        {
            warning = Warning(lineNumber, "missing_field", "job_id is required.");
            return null;
        }

        if (!Enum.TryParse(ReadString(obj, "state"), out ReconstructionJobState state))
        {
            warning = Warning(lineNumber, "missing_field", "state is required.");
            return null;
        }

        if (!Enum.TryParse(ReadString(obj, "stage"), out ReconstructionJobStage stage))
        {
            warning = Warning(lineNumber, "missing_field", "stage is required.");
            return null;
        }

        TryReadGuid(obj, "source_artifact_id", out var sourceArtifactId);
        TryReadGuid(obj, "result_artifact_id", out var resultArtifactId);

        return new ReconstructionJobLedgerRecord(
            ReconstructionJobLedgerRecord.CurrentSchemaVersion,
            jobId,
            state,
            stage,
            ReadString(obj, "provider") ?? string.Empty,
            ReadString(obj, "model_id") ?? string.Empty,
            ReadString(obj, "provider_job_id"),
            ReadString(obj, "provider_status_url"),
            ReadString(obj, "provider_response_url"),
            ReadString(obj, "provider_cancel_url"),
            ReadString(obj, "provider_cancel_http_method"),
            sourceArtifactId,
            ReadString(obj, "source_role") ?? string.Empty,
            DeserializeStages(obj["preprocessing_chain"]),
            ReadTimestamp(obj, "created_at") ?? DateTimeOffset.UtcNow,
            ReadTimestamp(obj, "updated_at") ?? DateTimeOffset.UtcNow,
            resultArtifactId == Guid.Empty ? null : resultArtifactId,
            ReadBool(obj, "result_available") ?? false,
            DeserializeFailure(obj["error"]),
            ReadBool(obj, "texture_expected") ?? false);
    }

    private static IReadOnlyList<ReconstructionPreprocessingStageRecord> DeserializeStages(JsonNode? node)
    {
        if (node is not JsonArray array)
            return Array.Empty<ReconstructionPreprocessingStageRecord>();

        var stages = new List<ReconstructionPreprocessingStageRecord>();
        foreach (var item in array.OfType<JsonObject>())
        {
            TryReadGuid(item, "stage_id", out var stageId);
            TryReadGuid(item, "input_artifact_id", out var inputArtifactId);
            TryReadGuid(item, "output_artifact_id", out var outputArtifactId);
            Enum.TryParse(ReadString(item, "state"), out ReconstructionJobState state);
            stages.Add(new ReconstructionPreprocessingStageRecord(
                stageId,
                ReadString(item, "role") ?? string.Empty,
                ReadString(item, "provider") ?? string.Empty,
                ReadString(item, "model_id") ?? string.Empty,
                state,
                inputArtifactId,
                outputArtifactId == Guid.Empty ? null : outputArtifactId,
                ReadString(item, "provider_job_id"),
                DeserializeFailure(item["error"])));
        }

        return stages;
    }

    private static ReconstructionFailure? DeserializeFailure(JsonNode? node)
    {
        if (node is not JsonObject obj)
            return null;

        return new ReconstructionFailure(
            ReadString(obj, "code") ?? "unknown",
            ReadString(obj, "message") ?? string.Empty,
            ReadBool(obj, "retryable") ?? false,
            ReadString(obj, "field"),
            DeserializeDetails(obj["details"]));
    }

    private static Dictionary<string, object?> DeserializeDetails(JsonNode? node)
    {
        var result = new Dictionary<string, object?>();
        if (node is not JsonObject obj)
            return result;

        foreach (var kvp in obj)
        {
            result[kvp.Key] = kvp.Value switch
            {
                null => null,
                JsonValue value when value.TryGetValue<string>(out var text) => text,
                JsonValue value when value.TryGetValue<bool>(out var boolean) => boolean,
                JsonValue value when value.TryGetValue<int>(out var integer) => integer,
                JsonValue value when value.TryGetValue<long>(out var longInteger) => longInteger,
                JsonValue value when value.TryGetValue<double>(out var number) => number,
                _ => kvp.Value.ToJsonString(),
            };
        }

        return result;
    }

    private static ReconstructionWarning Warning(int lineNumber, string code, string message)
        => new(
            code,
            message,
            new Dictionary<string, object?> { ["line"] = lineNumber });

    private static string? ReadString(JsonObject obj, string name)
        => obj.TryGetPropertyValue(name, out var node)
            && node is JsonValue value
            && value.TryGetValue<string>(out var text)
                ? text
                : null;

    private static int? ReadInt(JsonObject obj, string name)
        => obj.TryGetPropertyValue(name, out var node)
            && node is JsonValue value
            && value.TryGetValue<int>(out var number)
                ? number
                : null;

    private static bool? ReadBool(JsonObject obj, string name)
        => obj.TryGetPropertyValue(name, out var node)
            && node is JsonValue value
            && value.TryGetValue<bool>(out var flag)
                ? flag
                : null;

    private static bool TryReadGuid(JsonObject obj, string name, out Guid value)
    {
        value = Guid.Empty;
        return Guid.TryParse(ReadString(obj, name), out value);
    }

    private static DateTimeOffset? ReadTimestamp(JsonObject obj, string name)
        => DateTimeOffset.TryParse(
            ReadString(obj, name),
            CultureInfo.InvariantCulture,
            DateTimeStyles.RoundtripKind,
            out var parsed)
                ? parsed
                : null;
}
