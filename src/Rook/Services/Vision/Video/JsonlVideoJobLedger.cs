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
            if (stateStr is null
                || !Enum.TryParse<VideoJobState>(stateStr, out var state)
                || !Enum.IsDefined(typeof(VideoJobState), state))
                return (null, MissingField(lineNumber, "state"));

            var normalized = TryGetObject(obj, "normalized_request");
            if (normalized is null)
                return (null, MissingField(lineNumber, "normalized_request"));
            var (normalizedReq, normErr) = DeserializeNormalizedRequest(normalized, lineNumber);
            if (normErr is not null) return (null, normErr);

            var pricingObj = TryGetObject(obj, "pricing");
            if (pricingObj is null)
                return (null, MissingField(lineNumber, "pricing"));
            var pricingResult = DeserializePricing(pricingObj, lineNumber);
            if (pricingResult.Error is not null)
                return (null, pricingResult.Error);

            // Optional / nullable fields
            var providerJobId = TryGetString(obj, "provider_job_id");
            var providerResultToken = TryGetString(obj, "provider_result_token");

            // result_artifact_id: malformed string fails closed regardless
            // of state; missing-when-required is enforced state-conditionally
            // below (Codex round 7 finding 2 — Complete records must have it).
            Guid? resultArtifactId = null;
            var artIdStr = TryGetString(obj, "result_artifact_id");
            if (artIdStr is not null)
            {
                if (!Guid.TryParse(artIdStr, out var aid))
                    return (null, MissingField(lineNumber, "result_artifact_id"));
                resultArtifactId = aid;
            }
            if (state == VideoJobState.Complete && resultArtifactId is null)
                return (null, MissingField(lineNumber, "result_artifact_id"));

            VideoJobError? error = null;
            var errorObj = TryGetObject(obj, "error");
            if (errorObj is not null)
            {
                var (deErr, deErrFault) = DeserializeError(errorObj, lineNumber);
                if (deErrFault is not null) return (null, deErrFault);
                error = deErr;
            }

            // Provider options is required and must be a JsonObject. It's
            // the durable contract lane for provider-specific fields
            // (person_generation for Veo; future provider keys). Missing
            // or non-object fails closed (Codex round 7 finding 1) — the
            // record's provider_options must round-trip exactly.
            if (!obj.TryGetPropertyValue("provider_options", out var poNode)
                || poNode is null
                || poNode is not JsonObject providerOptionsRaw)
                return (null, MissingField(lineNumber, "provider_options"));
            var providerOptions = (JsonObject)providerOptionsRaw.DeepClone();

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
                NormalizedRequest: normalizedReq!,
                ProviderOptions: providerOptions,
                Pricing: pricingResult.Pricing!,
                ResultArtifactId: resultArtifactId,
                Error: error,
                CreatedAt: createdAt,
                UpdatedAt: updatedAt,
                Extensions: extensions);

            return (record, null);
        }

        // ─── Deserialize helpers (fail-closed on missing/invalid required) ──
        //
        // Each helper returns (value, error). The main TryDeserialize
        // propagates the error up; the line is recorded as a typed
        // failure rather than silently defaulted. Codex round 6 finding:
        // a malformed durable record must not be admitted as valid just
        // because individual fields had `?? "default"` fallbacks.

        private static (NormalizedRequest? Value, LedgerReadError? Error) DeserializeNormalizedRequest(
            JsonObject obj, int lineNumber)
        {
            var modeStr = TryGetString(obj, "mode");
            if (modeStr is null
                || !Enum.TryParse<VideoMode>(modeStr, out var mode)
                || !Enum.IsDefined(typeof(VideoMode), mode))
                return (null, MissingField(lineNumber, "normalized_request.mode"));

            var duration = TryGetInt(obj, "duration_seconds");
            if (duration is null)
                return (null, MissingField(lineNumber, "normalized_request.duration_seconds"));

            var resolution = TryGetString(obj, "resolution");
            if (resolution is null)
                return (null, MissingField(lineNumber, "normalized_request.resolution"));

            var aspect = TryGetString(obj, "aspect_ratio");
            if (aspect is null)
                return (null, MissingField(lineNumber, "normalized_request.aspect_ratio"));

            var count = TryGetInt(obj, "number_of_videos");
            if (count is null)
                return (null, MissingField(lineNumber, "normalized_request.number_of_videos"));

            // Optional fields
            var prompt = TryGetString(obj, "prompt");
            var seed = TryGetInt(obj, "seed");

            // Optional nested media refs — missing OK, but if present, must validate
            NormalizedMediaRef? startFrame = null;
            if (obj["start_frame"] is JsonObject sf)
            {
                var (m, err) = DeserializeMediaRef(sf, lineNumber, "normalized_request.start_frame");
                if (err is not null) return (null, err);
                startFrame = m;
            }

            NormalizedMediaRef? endFrame = null;
            if (obj["end_frame"] is JsonObject ef)
            {
                var (m, err) = DeserializeMediaRef(ef, lineNumber, "normalized_request.end_frame");
                if (err is not null) return (null, err);
                endFrame = m;
            }

            IReadOnlyList<NormalizedMediaRef>? refs = null;
            if (obj["reference_frames"] is JsonArray refsArr)
            {
                var list = new List<NormalizedMediaRef>(refsArr.Count);
                for (int i = 0; i < refsArr.Count; i++)
                {
                    if (refsArr[i] is not JsonObject mo)
                        return (null, MissingField(
                            lineNumber, $"normalized_request.reference_frames[{i}]"));
                    var (m, err) = DeserializeMediaRef(
                        mo, lineNumber, $"normalized_request.reference_frames[{i}]");
                    if (err is not null) return (null, err);
                    list.Add(m!);
                }
                refs = list;
            }

            var value = new NormalizedRequest(
                Mode: mode,
                DurationSeconds: duration.Value,
                Resolution: resolution,
                AspectRatio: aspect,
                Prompt: prompt,
                StartFrame: startFrame,
                EndFrame: endFrame,
                ReferenceFrames: refs,
                Seed: seed,
                NumberOfVideos: count.Value);

            return (value, null);
        }

        private static (NormalizedMediaRef? Value, LedgerReadError? Error) DeserializeMediaRef(
            JsonObject obj, int lineNumber, string fieldPathPrefix)
        {
            var kindStr = TryGetString(obj, "kind");
            if (kindStr is null
                || !Enum.TryParse<VideoMediaRefKind>(kindStr, out var kind)
                || !Enum.IsDefined(typeof(VideoMediaRefKind), kind))
                return (null, MissingField(lineNumber, fieldPathPrefix + ".kind"));

            var role = TryGetString(obj, "role");
            if (role is null)
                return (null, MissingField(lineNumber, fieldPathPrefix + ".role"));

            // Codex round 7 finding 3: the durable shape MUST match the
            // V1a runtime VideoMediaRef invariants (ForArtifact requires
            // non-empty Guid; ForPath requires non-empty path). A
            // persisted media ref that could never have been constructed
            // through the domain factory is corrupt.

            Guid? artifactId = null;
            var artIdStr = TryGetString(obj, "artifact_id");
            if (artIdStr is not null)
            {
                if (!Guid.TryParse(artIdStr, out var aid) || aid == Guid.Empty)
                    return (null, MissingField(lineNumber, fieldPathPrefix + ".artifact_id"));
                artifactId = aid;
            }

            var path = TryGetString(obj, "path");

            switch (kind)
            {
                case VideoMediaRefKind.Artifact:
                    if (artifactId is null)
                        return (null, MissingField(
                            lineNumber, fieldPathPrefix + ".artifact_id"));
                    break;
                case VideoMediaRefKind.Path:
                    if (string.IsNullOrWhiteSpace(path))
                        return (null, MissingField(
                            lineNumber, fieldPathPrefix + ".path"));
                    break;
            }

            return (new NormalizedMediaRef(
                Kind: kind,
                ArtifactId: artifactId,
                Path: path,
                Role: role), null);
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

            var currency = TryGetString(obj, "currency");
            if (currency is null)
                return (null, MissingField(lineNumber, "pricing.currency"));

            var quantity = TryGetInt(obj, "quantity");
            if (quantity is null)
                return (null, MissingField(lineNumber, "pricing.quantity"));

            var pricingSource = TryGetString(obj, "pricing_source");
            if (pricingSource is null)
                return (null, MissingField(lineNumber, "pricing.pricing_source"));

            return (new JobPricing(
                Kind: kind,
                Currency: currency,
                Quantity: quantity.Value,
                UnitPriceUsd: TryGetDecimal(obj, "unit_price_usd"),
                TotalUsd: TryGetDecimal(obj, "total_usd"),
                PricingSource: pricingSource), null);
        }

        private static (VideoJobError? Value, LedgerReadError? Error) DeserializeError(
            JsonObject obj, int lineNumber)
        {
            var codeStr = TryGetString(obj, "code");
            if (codeStr is null
                || !Enum.TryParse<VideoErrorCode>(codeStr, out var code)
                || !Enum.IsDefined(typeof(VideoErrorCode), code))
                return (null, MissingField(lineNumber, "error.code"));

            var message = TryGetString(obj, "message");
            if (message is null)
                return (null, MissingField(lineNumber, "error.message"));

            var retryable = TryGetBool(obj, "retryable");
            if (retryable is null)
                return (null, MissingField(lineNumber, "error.retryable"));

            return (new VideoJobError(
                Code: code,
                Message: message,
                Retryable: retryable.Value,
                ProviderMessage: TryGetString(obj, "provider_message"),
                Field: TryGetString(obj, "field")), null);
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
