using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Append-only JSONL persistence for <see cref="VideoJobRecord"/>.
    /// Each line is a complete record snapshot; <see cref="ReadAll"/>
    /// compacts by <c>job_id</c> in file order (last entry wins).
    ///
    /// Schema discipline (v3.1 + Codex rounds 3-4):
    ///   - Snake_case keys throughout (matches ArtifactStore convention)
    ///   - <c>provider_options</c> persisted as opaque JsonObject so
    ///     unknown provider-specific keys round-trip without loss
    ///   - Top-level <c>extensions</c> field captures unknown keys
    ///     (within a known schema_version) for forward-compat
    ///   - Read fails closed (line-scoped) on
    ///     UnsupportedSchemaVersion, UnknownPricingKind,
    ///     MissingRequiredField, MalformedJson; valid prior records are
    ///     still returned.
    ///
    /// Thread safety: single-writer (the manager); the lock here
    /// serializes appends and protects against partial writes during
    /// concurrent reads on the same instance.
    /// </summary>
    public sealed class JsonlVideoJobLedger : IVideoJobLedger
    {
        private static readonly HashSet<string> KnownTopLevelKeys = new(StringComparer.Ordinal)
        {
            "schema_version", "job_id", "provider", "model",
            "provider_job_id", "provider_result_token", "state",
            "normalized_request", "provider_options", "pricing",
            "result_artifact_id", "error",
            "created_at", "updated_at",
        };

        private readonly string _filePath;
        private readonly object _lock = new();

        public JsonlVideoJobLedger() : this(DefaultPath()) { }

        public JsonlVideoJobLedger(string filePath)
        {
            if (string.IsNullOrWhiteSpace(filePath))
                throw new ArgumentException(
                    "filePath must be non-empty.", nameof(filePath));
            _filePath = filePath;
        }

        public string FilePath => _filePath;

        public static string DefaultPath()
        {
            var appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
            return Path.Combine(appData, "Rook", "video", "job-ledger.jsonl");
        }

        public void Append(VideoJobRecord record)
        {
            if (record is null) throw new ArgumentNullException(nameof(record));

            var line = SerializeRecord(record);

            lock (_lock)
            {
                var dir = Path.GetDirectoryName(_filePath);
                if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
                    Directory.CreateDirectory(dir);

                using var stream = new FileStream(
                    _filePath, FileMode.Append, FileAccess.Write, FileShare.Read);
                using var writer = new StreamWriter(stream, new UTF8Encoding(false));
                writer.WriteLine(line);
            }
        }

        public VideoJobLedgerReadResult ReadAll()
        {
            if (!File.Exists(_filePath))
                return new VideoJobLedgerReadResult(
                    Array.Empty<VideoJobRecord>(),
                    Array.Empty<LedgerReadError>());

            string[] lines;
            lock (_lock)
            {
                lines = File.ReadAllLines(_filePath, Encoding.UTF8);
            }

            var byJobId = new Dictionary<Guid, VideoJobRecord>();
            var errors = new List<LedgerReadError>();

            for (int i = 0; i < lines.Length; i++)
            {
                var line = lines[i];
                var lineNumber = i + 1;

                if (string.IsNullOrWhiteSpace(line)) continue;

                var (record, error) = TryDeserialize(line, lineNumber);
                if (error is not null)
                {
                    errors.Add(error);
                    continue;
                }

                // Last entry per job_id wins (file order).
                byJobId[record!.JobId] = record;
            }

            return new VideoJobLedgerReadResult(byJobId.Values.ToArray(), errors);
        }

        // ─── Serialization ────────────────────────────────────────────

        private static string SerializeRecord(VideoJobRecord r)
        {
            var obj = new JsonObject
            {
                ["schema_version"] = r.SchemaVersion,
                ["job_id"] = r.JobId.ToString("D"),
                ["provider"] = r.Provider,
                ["model"] = r.Model,
                ["provider_job_id"] = r.ProviderJobId,
                ["provider_result_token"] = r.ProviderResultToken,
                ["state"] = r.State.ToString(),
                ["normalized_request"] = SerializeNormalizedRequest(r.NormalizedRequest),
                ["provider_options"] = (JsonNode?)(r.ProviderOptions?.DeepClone()),
                ["pricing"] = SerializePricing(r.Pricing),
                ["result_artifact_id"] = r.ResultArtifactId?.ToString("D"),
                ["error"] = r.Error is null ? null : SerializeError(r.Error),
                ["created_at"] = r.CreatedAt.ToString("o", CultureInfo.InvariantCulture),
                ["updated_at"] = r.UpdatedAt.ToString("o", CultureInfo.InvariantCulture),
            };

            // Merge any preserved unknown fields back in. Known keys
            // already present in obj take precedence.
            if (r.Extensions is not null)
            {
                foreach (var kvp in r.Extensions)
                {
                    if (!obj.ContainsKey(kvp.Key))
                        obj[kvp.Key] = kvp.Value?.DeepClone();
                }
            }

            return obj.ToJsonString(new JsonSerializerOptions
            {
                WriteIndented = false,
            });
        }

        private static JsonObject SerializeNormalizedRequest(NormalizedRequest req)
        {
            var refs = req.ReferenceFrames is null ? null : new JsonArray(
                req.ReferenceFrames.Select(SerializeMediaRef).ToArray<JsonNode?>());

            return new JsonObject
            {
                ["mode"] = req.Mode.ToString(),
                ["duration_seconds"] = req.DurationSeconds,
                ["resolution"] = req.Resolution,
                ["aspect_ratio"] = req.AspectRatio,
                ["prompt"] = req.Prompt,
                ["start_frame"] = req.StartFrame is null ? null : SerializeMediaRef(req.StartFrame),
                ["end_frame"] = req.EndFrame is null ? null : SerializeMediaRef(req.EndFrame),
                ["reference_frames"] = refs,
                ["seed"] = req.Seed,
                ["number_of_videos"] = req.NumberOfVideos,
            };
        }

        private static JsonObject SerializeMediaRef(NormalizedMediaRef m) => new()
        {
            ["kind"] = m.Kind.ToString(),
            ["artifact_id"] = m.ArtifactId?.ToString("D"),
            ["path"] = m.Path,
            ["role"] = m.Role,
        };

        private static JsonObject SerializePricing(JobPricing p) => new()
        {
            ["kind"] = p.Kind switch
            {
                PricingKind.PerSecond => "per_second",
                PricingKind.PerGeneration => "per_generation",
                PricingKind.External => "external",
                _ => p.Kind.ToString().ToLowerInvariant(),
            },
            ["currency"] = p.Currency,
            ["quantity"] = p.Quantity,
            ["unit_price_usd"] = p.UnitPriceUsd,
            ["total_usd"] = p.TotalUsd,
            ["pricing_source"] = p.PricingSource,
        };

        private static JsonObject SerializeError(VideoJobError e) => new()
        {
            ["code"] = e.Code.ToString(),
            ["message"] = e.Message,
            ["retryable"] = e.Retryable,
            ["provider_message"] = e.ProviderMessage,
            ["field"] = e.Field,
        };

        // ─── Deserialization ──────────────────────────────────────────

        private static (VideoJobRecord? Record, LedgerReadError? Error) TryDeserialize(
            string line, int lineNumber)
        {
            JsonNode? root;
            try
            {
                root = JsonNode.Parse(line);
            }
            catch (JsonException ex)
            {
                return (null, new LedgerReadError(
                    LineNumber: lineNumber,
                    Reason: LedgerReadErrorReason.MalformedJson,
                    Message: $"JSON parse failed: {ex.Message}",
                    FieldPath: null,
                    OffendingValue: null,
                    RawLineExcerpt: TruncateForExcerpt(line)));
            }

            if (root is not JsonObject obj)
                return (null, new LedgerReadError(
                    LineNumber: lineNumber,
                    Reason: LedgerReadErrorReason.MalformedJson,
                    Message: "Top-level JSON must be an object.",
                    FieldPath: null,
                    OffendingValue: null,
                    RawLineExcerpt: TruncateForExcerpt(line)));

            // Schema version
            int? schemaVersion = TryGetInt(obj, "schema_version");
            if (schemaVersion is null)
                return (null, MissingField(lineNumber, "schema_version"));
            if (schemaVersion.Value != VideoJobRecordFactory.CurrentSchemaVersion)
                return (null, new LedgerReadError(
                    LineNumber: lineNumber,
                    Reason: LedgerReadErrorReason.UnsupportedSchemaVersion,
                    Message: $"Unsupported schema_version: {schemaVersion.Value}.",
                    FieldPath: "schema_version",
                    OffendingValue: schemaVersion.Value.ToString(CultureInfo.InvariantCulture),
                    RawLineExcerpt: null));

            // Required fields
            var jobIdStr = TryGetString(obj, "job_id");
            if (jobIdStr is null || !Guid.TryParse(jobIdStr, out var jobId))
                return (null, MissingField(lineNumber, "job_id"));

            var provider = TryGetString(obj, "provider");
            if (provider is null) return (null, MissingField(lineNumber, "provider"));

            var model = TryGetString(obj, "model");
            if (model is null) return (null, MissingField(lineNumber, "model"));

            var stateStr = TryGetString(obj, "state");
            if (stateStr is null || !Enum.TryParse<VideoJobState>(stateStr, out var state))
                return (null, MissingField(lineNumber, "state"));

            var normalized = TryGetObject(obj, "normalized_request");
            if (normalized is null)
                return (null, MissingField(lineNumber, "normalized_request"));
            var normalizedReq = DeserializeNormalizedRequest(normalized);

            var pricingObj = TryGetObject(obj, "pricing");
            if (pricingObj is null)
                return (null, MissingField(lineNumber, "pricing"));
            var pricingResult = DeserializePricing(pricingObj, lineNumber);
            if (pricingResult.Error is not null)
                return (null, pricingResult.Error);

            // Optional / nullable fields
            var providerJobId = TryGetString(obj, "provider_job_id");
            var providerResultToken = TryGetString(obj, "provider_result_token");

            Guid? resultArtifactId = null;
            var artIdStr = TryGetString(obj, "result_artifact_id");
            if (artIdStr is not null && Guid.TryParse(artIdStr, out var aid))
                resultArtifactId = aid;

            VideoJobError? error = null;
            var errorObj = TryGetObject(obj, "error");
            if (errorObj is not null)
                error = DeserializeError(errorObj);

            // Provider options (opaque JsonObject)
            var providerOptions = (TryGetObject(obj, "provider_options")
                ?.DeepClone() as JsonObject) ?? new JsonObject();

            // Timestamps
            var createdAtStr = TryGetString(obj, "created_at");
            var updatedAtStr = TryGetString(obj, "updated_at");
            if (createdAtStr is null || !DateTimeOffset.TryParse(
                    createdAtStr, CultureInfo.InvariantCulture,
                    DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal,
                    out var createdAt))
                return (null, MissingField(lineNumber, "created_at"));
            if (updatedAtStr is null || !DateTimeOffset.TryParse(
                    updatedAtStr, CultureInfo.InvariantCulture,
                    DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal,
                    out var updatedAt))
                return (null, MissingField(lineNumber, "updated_at"));

            // Extensions: capture any top-level keys outside our known set.
            JsonObject? extensions = null;
            foreach (var kvp in obj)
            {
                if (!KnownTopLevelKeys.Contains(kvp.Key))
                {
                    extensions ??= new JsonObject();
                    extensions[kvp.Key] = kvp.Value?.DeepClone();
                }
            }

            var record = new VideoJobRecord(
                SchemaVersion: schemaVersion.Value,
                JobId: jobId,
                Provider: provider,
                Model: model,
                ProviderJobId: providerJobId,
                ProviderResultToken: providerResultToken,
                State: state,
                NormalizedRequest: normalizedReq,
                ProviderOptions: providerOptions,
                Pricing: pricingResult.Pricing!,
                ResultArtifactId: resultArtifactId,
                Error: error,
                CreatedAt: createdAt,
                UpdatedAt: updatedAt,
                Extensions: extensions);

            return (record, null);
        }

        private static NormalizedRequest DeserializeNormalizedRequest(JsonObject obj)
        {
            var modeStr = TryGetString(obj, "mode");
            Enum.TryParse<VideoMode>(modeStr ?? "T2V", out var mode);

            var refsArr = obj["reference_frames"] as JsonArray;
            IReadOnlyList<NormalizedMediaRef>? refs = null;
            if (refsArr is not null)
            {
                var list = new List<NormalizedMediaRef>(refsArr.Count);
                foreach (var node in refsArr)
                    if (node is JsonObject mo)
                        list.Add(DeserializeMediaRef(mo));
                refs = list;
            }

            return new NormalizedRequest(
                Mode: mode,
                DurationSeconds: TryGetInt(obj, "duration_seconds") ?? 0,
                Resolution: TryGetString(obj, "resolution") ?? "",
                AspectRatio: TryGetString(obj, "aspect_ratio") ?? "",
                Prompt: TryGetString(obj, "prompt"),
                StartFrame: obj["start_frame"] is JsonObject sf ? DeserializeMediaRef(sf) : null,
                EndFrame: obj["end_frame"] is JsonObject ef ? DeserializeMediaRef(ef) : null,
                ReferenceFrames: refs,
                Seed: TryGetInt(obj, "seed"),
                NumberOfVideos: TryGetInt(obj, "number_of_videos") ?? 1);
        }

        private static NormalizedMediaRef DeserializeMediaRef(JsonObject obj)
        {
            var kindStr = TryGetString(obj, "kind") ?? "Artifact";
            Enum.TryParse<VideoMediaRefKind>(kindStr, out var kind);

            Guid? artifactId = null;
            var artIdStr = TryGetString(obj, "artifact_id");
            if (artIdStr is not null && Guid.TryParse(artIdStr, out var aid))
                artifactId = aid;

            return new NormalizedMediaRef(
                Kind: kind,
                ArtifactId: artifactId,
                Path: TryGetString(obj, "path"),
                Role: TryGetString(obj, "role") ?? "image");
        }

        private static (JobPricing? Pricing, LedgerReadError? Error) DeserializePricing(
            JsonObject obj, int lineNumber)
        {
            var kindStr = TryGetString(obj, "kind");
            PricingKind kind;
            switch (kindStr)
            {
                case "per_second": kind = PricingKind.PerSecond; break;
                case "per_generation": kind = PricingKind.PerGeneration; break;
                case "external": kind = PricingKind.External; break;
                default:
                    return (null, new LedgerReadError(
                        LineNumber: lineNumber,
                        Reason: LedgerReadErrorReason.UnknownPricingKind,
                        Message: $"Unknown pricing.kind: '{kindStr}'.",
                        FieldPath: "pricing.kind",
                        OffendingValue: kindStr,
                        RawLineExcerpt: null));
            }

            return (new JobPricing(
                Kind: kind,
                Currency: TryGetString(obj, "currency") ?? "USD",
                Quantity: TryGetInt(obj, "quantity") ?? 0,
                UnitPriceUsd: TryGetDecimal(obj, "unit_price_usd"),
                TotalUsd: TryGetDecimal(obj, "total_usd"),
                PricingSource: TryGetString(obj, "pricing_source") ?? "unknown"),
                null);
        }

        private static VideoJobError DeserializeError(JsonObject obj)
        {
            var codeStr = TryGetString(obj, "code") ?? "ExecutionFailed";
            Enum.TryParse<VideoErrorCode>(codeStr, out var code);

            return new VideoJobError(
                Code: code,
                Message: TryGetString(obj, "message") ?? "",
                Retryable: TryGetBool(obj, "retryable") ?? false,
                ProviderMessage: TryGetString(obj, "provider_message"),
                Field: TryGetString(obj, "field"));
        }

        // ─── JsonObject access helpers (defensive against missing/typed) ──

        private static string? TryGetString(JsonObject obj, string key)
        {
            if (!obj.TryGetPropertyValue(key, out var node) || node is null) return null;
            try { return node.GetValue<string>(); } catch { return null; }
        }

        private static int? TryGetInt(JsonObject obj, string key)
        {
            if (!obj.TryGetPropertyValue(key, out var node) || node is null) return null;
            try { return node.GetValue<int>(); } catch { return null; }
        }

        private static decimal? TryGetDecimal(JsonObject obj, string key)
        {
            if (!obj.TryGetPropertyValue(key, out var node) || node is null) return null;
            try { return node.GetValue<decimal>(); } catch { return null; }
        }

        private static bool? TryGetBool(JsonObject obj, string key)
        {
            if (!obj.TryGetPropertyValue(key, out var node) || node is null) return null;
            try { return node.GetValue<bool>(); } catch { return null; }
        }

        private static JsonObject? TryGetObject(JsonObject obj, string key)
        {
            if (!obj.TryGetPropertyValue(key, out var node)) return null;
            return node as JsonObject;
        }

        private static LedgerReadError MissingField(int lineNumber, string fieldPath) => new(
            LineNumber: lineNumber,
            Reason: LedgerReadErrorReason.MissingRequiredField,
            Message: $"Required field missing or malformed: {fieldPath}.",
            FieldPath: fieldPath,
            OffendingValue: null,
            RawLineExcerpt: null);

        private static string TruncateForExcerpt(string line)
        {
            const int maxLen = 200;
            return line.Length <= maxLen ? line : line.Substring(0, maxLen) + "...";
        }
    }
}
