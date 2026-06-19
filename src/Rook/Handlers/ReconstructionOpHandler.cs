using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rhino;
using Rook.Artifacts;
using Rook.Services.Reconstruction;

namespace Rook.Handlers
{
    public sealed class ReconstructionOpHandler
    {
        public const string OpModels = "models";
        public const string OpSubmit = "submit_job";
        public const string OpListJobs = "list_jobs";
        public const string OpStatus = "job_status";
        public const string OpCancel = "cancel_job";
        public const string OpResult = "job_result";
        public const string OpPrepareImport = "prepare_import";
        public const string OpRecordImport = "record_import";

        public const int DefaultListJobsLimit = 50;

        private readonly ReconstructionModelCatalog _catalog;
        private readonly ReconstructionJobManager _manager;
        private readonly ArtifactStore _store;

        public ReconstructionOpHandler(
            ReconstructionModelCatalog catalog,
            ReconstructionJobManager manager,
            ArtifactStore store)
        {
            _catalog = catalog ?? throw new ArgumentNullException(nameof(catalog));
            _manager = manager ?? throw new ArgumentNullException(nameof(manager));
            _store = store ?? throw new ArgumentNullException(nameof(store));
        }

        public async Task<ApiResponse> DispatchAsync(
            string? body,
            CancellationToken cancellationToken = default)
        {
            Dictionary<string, JsonElement> args;
            try { args = ParseObjectBody(body); }
            catch (ArgumentException ex)
            {
                return Fail(Failure("invalid_request", ex.Message, "body"), 400);
            }

            var op = GetStringArg(args, "op");
            if (string.IsNullOrEmpty(op))
                return Fail(Failure("invalid_request", "Reconstruction request missing required 'op' discriminator.", "op"), 400);

            try
            {
                return op switch
                {
                    OpSubmit => await SubmitAsync(body, cancellationToken).ConfigureAwait(false),
                    OpCancel => await CancelAsync(args, cancellationToken).ConfigureAwait(false),
                    OpModels or OpListJobs or OpStatus or OpResult or OpPrepareImport or OpRecordImport =>
                        DispatchOffUi(body),
                    _ => Fail(Failure("invalid_request", $"Unknown reconstruction op '{op}'.", "op"), 400),
                };
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine(
                    $"Rook Reconstruction: unhandled error in async op '{op}': {ex.GetType().Name}: {ex.Message}");
                return Fail(
                    Failure("execution_failed", $"Reconstruction op '{op}' failed unexpectedly.", null, retryable: true),
                    500);
            }
        }

        public ApiResponse DispatchOffUi(string? body)
        {
            Dictionary<string, JsonElement> args;
            try { args = ParseObjectBody(body); }
            catch (ArgumentException ex)
            {
                return Fail(Failure("invalid_request", ex.Message, "body"), 400);
            }

            var op = GetStringArg(args, "op");
            if (string.IsNullOrEmpty(op))
                return Fail(Failure("invalid_request", "Reconstruction request missing required 'op' discriminator.", "op"), 400);

            try
            {
                return op switch
                {
                    OpModels => Models(args),
                    OpListJobs => ListJobs(args),
                    OpStatus => Status(args),
                    OpResult => Result(args),
                    OpPrepareImport => PrepareImport(args),
                    OpRecordImport => RecordImport(args),
                    OpSubmit or OpCancel => Fail(
                        Failure("invalid_request", $"op '{op}' must be routed through the async dispatcher, not the off-UI dispatcher.", "op"),
                        400),
                    _ => Fail(Failure("invalid_request", $"Unknown reconstruction op '{op}'.", "op"), 400),
                };
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine(
                    $"Rook Reconstruction: unhandled error in off-UI op '{op}': {ex.GetType().Name}: {ex.Message}");
                return Fail(
                    Failure("execution_failed", $"Reconstruction op '{op}' failed unexpectedly.", null, retryable: true),
                    500);
            }
        }

        private ApiResponse Models(Dictionary<string, JsonElement> args)
        {
            var includeExperimental = GetBoolArg(args, "include_experimental") ?? false;
            var includeHidden = GetBoolArg(args, "include_hidden") ?? false;
            return Ok(new Dictionary<string, object?>
            {
                ["models"] = _catalog
                    .List(includeExperimental, includeHidden)
                    .Select(ModelToObj)
                    .ToArray(),
            });
        }

        private async Task<ApiResponse> SubmitAsync(string? body, CancellationToken ct)
        {
            var parsed = ReconstructionSubmitRequestParser.Parse(body);
            if (!parsed.Success)
                return Fail(parsed.Failure!, StatusFor(parsed.Failure!));

            var result = await _manager.SubmitAsync(parsed.Request!, ct)
                .ConfigureAwait(false);
            if (!result.Success)
                return Fail(result.Failure!, StatusFor(result.Failure!));

            return Ok(JobToObj(result.Job!));
        }

        private ApiResponse ListJobs(Dictionary<string, JsonElement> args)
        {
            var limit = TryGetOptionalPositiveInt(args, "limit", out var limitFailure);
            if (limitFailure is not null) return Fail(limitFailure, 400);

            var result = _manager.List(limit ?? DefaultListJobsLimit);
            return Ok(new Dictionary<string, object?>
            {
                ["jobs"] = result.Jobs.Select(JobToObj).ToArray(),
                ["warnings"] = result.Warnings.Select(WarningToObj).ToArray(),
                ["applied_limit"] = result.AppliedLimit,
            });
        }

        private ApiResponse Status(Dictionary<string, JsonElement> args)
        {
            if (!TryParseJobId(args, out var jobId, out var failure))
                return Fail(failure!, 400);

            var result = _manager.Status(jobId);
            if (!result.Success)
                return Fail(result.Failure!, StatusFor(result.Failure!));

            var job = JobToObj(result.Job!);
            job["result_available"] = result.ResultAvailable;
            return Ok(job);
        }

        private async Task<ApiResponse> CancelAsync(
            Dictionary<string, JsonElement> args,
            CancellationToken ct)
        {
            if (!TryParseJobId(args, out var jobId, out var failure))
                return Fail(failure!, 400);

            var result = await _manager.CancelAsync(jobId, ct).ConfigureAwait(false);
            if (result.Failure is not null)
                return Fail(result.Failure, StatusFor(result.Failure));

            return Ok(new Dictionary<string, object?>
            {
                ["job_id"] = jobId.ToString("D"),
                ["state"] = StateToString(result.State),
            });
        }

        private ApiResponse Result(Dictionary<string, JsonElement> args)
        {
            if (!TryParseJobId(args, out var jobId, out var failure))
                return Fail(failure!, 400);

            var result = _manager.Result(jobId);
            if (!result.Success)
                return Fail(result.Failure!, StatusFor(result.Failure!));

            return Ok(new Dictionary<string, object?>
            {
                ["job_id"] = result.JobId.ToString("D"),
                ["result_artifact_id"] = result.ResultArtifactId?.ToString("D"),
                ["result_available"] = result.ResultAvailable,
                ["warnings"] = result.Warnings.Select(WarningToObj).ToArray(),
            });
        }

        private ApiResponse PrepareImport(Dictionary<string, JsonElement> args)
        {
            if (!TryParseGuid(args, "package_id", out var packageId, out var failure))
                return Fail(failure!, 400);

            var package = _store.Get(packageId);
            if (package is null)
                return Fail(Failure("not_found", "Reconstruction package was not found.", "package_id"), 404);
            if (!string.Equals(package.Kind, ReconstructionArtifactKinds.Package, StringComparison.Ordinal))
                return Fail(Failure("invalid_request", "Artifact is not a reconstruction package.", "package_id"), 400);

            var manifest = ReadImportManifest(packageId, out failure);
            if (failure is not null) return Fail(failure, StatusFor(failure));

            var requestedRole = GetStringArg(args, "assetRole")
                ?? GetStringArg(args, "asset_role");
            var assetRole = ResolveAssetRole(package, manifest!, requestedRole, out failure);
            if (failure is not null) return Fail(failure, StatusFor(failure));

            return Ok(new Dictionary<string, object?>
            {
                ["package_id"] = packageId.ToString("D"),
                ["job_id"] = ReadString(package.Metadata, "job_id"),
                ["asset_role"] = assetRole,
                ["path"] = _store.GetBlobAbsolutePath(packageId, assetRole!),
                ["targetLayer"] = GetStringArg(args, "targetLayer"),
                ["companion_files"] = CompanionFiles(package, manifest!, assetRole!).ToArray(),
            });
        }

        private ApiResponse RecordImport(Dictionary<string, JsonElement> args)
        {
            if (!TryParseGuid(args, "package_id", out var packageId, out var failure))
                return Fail(failure!, 400);

            var package = _store.Get(packageId);
            if (package is null)
                return Fail(Failure("not_found", "Reconstruction package was not found.", "package_id"), 404);
            if (!string.Equals(package.Kind, ReconstructionArtifactKinds.Package, StringComparison.Ordinal))
                return Fail(Failure("invalid_request", "Artifact is not a reconstruction package.", "package_id"), 400);

            var manifest = ReadImportManifest(packageId, out failure);
            if (failure is not null) return Fail(failure, StatusFor(failure));

            var importId = GetStringArg(args, "import_id");
            if (!Guid.TryParse(importId, out var parsedImportId) || parsedImportId == Guid.Empty)
                parsedImportId = Guid.NewGuid();

            var imports = manifest!["imports"] as JsonArray;
            if (imports is null)
            {
                imports = new JsonArray();
                manifest["imports"] = imports;
            }

            imports.Add(new JsonObject
            {
                ["import_id"] = parsedImportId.ToString("D"),
                ["job_id"] = GetStringArg(args, "job_id"),
                ["asset_role"] = GetStringArg(args, "asset_role") ?? GetStringArg(args, "assetRole"),
                ["imported_ids"] = ReadStringArray(args, "imported_ids"),
                ["associated"] = GetBoolArg(args, "associated") ?? false,
                ["association_error"] = GetStringArg(args, "association_error"),
                ["recorded_at"] = DateTimeOffset.UtcNow.ToString("O", CultureInfo.InvariantCulture),
            });

            var replaced = _store.ReplaceJsonBlob(
                packageId,
                ReconstructionFileRoles.ImportManifest,
                manifest);
            if (!replaced.Success)
            {
                return Fail(
                    Failure(
                        "import_history_failed",
                        replaced.Message ?? "Import history could not be recorded.",
                        null,
                        retryable: true),
                    500);
            }

            return Ok(new Dictionary<string, object?>
            {
                ["package_id"] = packageId.ToString("D"),
                ["import_id"] = parsedImportId.ToString("D"),
                ["recorded"] = true,
            });
        }

        private JsonObject? ReadImportManifest(
            Guid packageId,
            out ReconstructionFailure? failure)
        {
            failure = null;
            try
            {
                return JsonNode.Parse(File.ReadAllText(
                    _store.GetBlobAbsolutePath(
                        packageId,
                        ReconstructionFileRoles.ImportManifest))) as JsonObject
                    ?? throw new JsonException("import_manifest must be a JSON object.");
            }
            catch (Exception ex) when (ex is IOException or JsonException or InvalidOperationException)
            {
                failure = Failure(
                    "invalid_package",
                    "Reconstruction package import_manifest could not be read.",
                    "package_id",
                    retryable: false);
                return null;
            }
        }

        private static string? ResolveAssetRole(
            Artifact package,
            JsonObject manifest,
            string? requestedRole,
            out ReconstructionFailure? failure)
        {
            failure = null;
            if (!string.IsNullOrWhiteSpace(requestedRole))
            {
                if (HasRole(package, requestedRole!))
                    return requestedRole;
                failure = Failure("invalid_request", "Requested assetRole does not exist in the package.", "assetRole");
                return null;
            }

            var preferred = ReadString(manifest, "preferred_asset");
            if (!string.IsNullOrWhiteSpace(preferred) && HasRole(package, preferred!))
                return preferred;

            if (manifest["fallback_order"] is JsonArray fallbackOrder)
            {
                foreach (var roleNode in fallbackOrder)
                {
                    if (roleNode is JsonValue value
                        && value.TryGetValue<string>(out var role)
                        && HasRole(package, role))
                    {
                        return role;
                    }
                }
            }

            failure = Failure("invalid_package", "No importable model asset exists in the package.", "package_id");
            return null;
        }

        private IEnumerable<Dictionary<string, object?>> CompanionFiles(
            Artifact package,
            JsonObject manifest,
            string assetRole)
        {
            var companions = manifest["asset_bindings"]?[assetRole]?["companion_roles"] as JsonArray;
            if (companions is null) yield break;

            foreach (var roleNode in companions)
            {
                if (roleNode is not JsonValue value ||
                    !value.TryGetValue<string>(out var role) ||
                    !HasRole(package, role))
                {
                    continue;
                }

                yield return new Dictionary<string, object?>
                {
                    ["role"] = role,
                    ["path"] = _store.GetBlobAbsolutePath(package.Id, role),
                };
            }
        }

        private static Dictionary<string, object?> ModelToObj(ReconstructionModelEntry model)
            => new()
            {
                ["model_id"] = model.ModelId,
                ["provider"] = model.Provider,
                ["task"] = model.Task,
                ["status"] = model.Status,
                ["enabled"] = model.Enabled,
                ["pipeline_roles"] = model.PipelineRoles,
                ["input_types"] = model.InputTypes,
                ["output_roles"] = model.OutputRoles,
                ["preferred_asset_role"] = model.PreferredAssetRole,
                ["fallback_order"] = model.FallbackOrder,
                ["supports_pbr"] = model.SupportsPbr,
                ["preprocessing"] = new Dictionary<string, object?>
                {
                    ["recommended"] = model.Preprocessing.Recommended,
                    ["required"] = model.Preprocessing.Required,
                },
                ["docs_url"] = model.DocsUrl,
            };

        private static Dictionary<string, object?> JobToObj(ReconstructionJobLedgerRecord job)
            => new()
            {
                ["job_id"] = job.JobId.ToString("D"),
                ["state"] = StateToString(job.State),
                ["stage"] = StageToString(job.Stage),
                ["provider"] = job.Provider,
                ["model_id"] = job.ModelId,
                ["provider_job_id"] = job.ProviderJobId,
                ["source_artifact_id"] = job.SourceArtifactId == Guid.Empty
                    ? null
                    : job.SourceArtifactId.ToString("D"),
                ["source_role"] = job.SourceRole,
                ["created_at"] = job.CreatedAt.ToString("O", CultureInfo.InvariantCulture),
                ["updated_at"] = job.UpdatedAt.ToString("O", CultureInfo.InvariantCulture),
                ["result_artifact_id"] = job.ResultArtifactId?.ToString("D"),
                ["result_available"] = job.ResultAvailable,
                ["error"] = job.Error is null ? null : FailureToObj(job.Error),
            };

        private static Dictionary<string, object?> WarningToObj(ReconstructionWarning warning)
            => new()
            {
                ["code"] = warning.Code,
                ["message"] = warning.Message,
                ["details"] = warning.Details,
            };

        private static Dictionary<string, object?> FailureToObj(ReconstructionFailure failure)
            => new()
            {
                ["code"] = failure.Code,
                ["message"] = failure.Message,
                ["retryable"] = failure.Retryable,
                ["field"] = failure.Field,
                ["details"] = failure.Details,
            };

        private static ApiResponse Ok(object? data)
            => new() { Success = true, Data = data, HttpStatus = 200 };

        private static ApiResponse Fail(ReconstructionFailure failure, int status)
            => new() { Success = false, Data = FailureToObj(failure), HttpStatus = status };

        private static int StatusFor(ReconstructionFailure failure)
            => failure.Code switch
            {
                "not_found" => 404,
                "invalid_json" or "invalid_request" or "invalid_source_role"
                    or "invalid_source_artifact" or "invalid_source_file" => 400,
                _ => 500,
            };

        private static ReconstructionFailure Failure(
            string code,
            string message,
            string? field,
            bool retryable = false)
            => new(code, message, retryable, field, new Dictionary<string, object?>());

        private static Dictionary<string, JsonElement> ParseObjectBody(string? body)
        {
            if (string.IsNullOrWhiteSpace(body))
                throw new ArgumentException("Request body is required.");

            Dictionary<string, JsonElement>? args;
            try
            {
                args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body!);
            }
            catch (JsonException ex)
            {
                throw new ArgumentException(ex.Message, ex);
            }

            return args ?? throw new ArgumentException("Request body must be a JSON object.");
        }

        private static string? GetStringArg(
            Dictionary<string, JsonElement> args,
            string name)
            => args.TryGetValue(name, out var el) && el.ValueKind == JsonValueKind.String
                ? el.GetString()
                : null;

        private static bool? GetBoolArg(Dictionary<string, JsonElement> args, string name)
            => args.TryGetValue(name, out var el) && el.ValueKind == JsonValueKind.True
                ? true
                : args.TryGetValue(name, out el) && el.ValueKind == JsonValueKind.False
                    ? false
                    : null;

        private static int? TryGetOptionalPositiveInt(
            Dictionary<string, JsonElement> args,
            string name,
            out ReconstructionFailure? failure)
        {
            failure = null;
            if (!args.TryGetValue(name, out var el))
                return null;

            if (el.ValueKind == JsonValueKind.Number && el.TryGetInt32(out var value) && value > 0)
                return value;

            failure = Failure("invalid_request", $"{name} must be a positive integer.", name);
            return null;
        }

        private static bool TryParseJobId(
            Dictionary<string, JsonElement> args,
            out Guid jobId,
            out ReconstructionFailure? failure)
            => TryParseGuid(args, "job_id", out jobId, out failure);

        private static bool TryParseGuid(
            Dictionary<string, JsonElement> args,
            string field,
            out Guid value,
            out ReconstructionFailure? failure)
        {
            value = Guid.Empty;
            var raw = GetStringArg(args, field);
            if (string.IsNullOrWhiteSpace(raw))
            {
                failure = Failure("invalid_request", $"{field} is required.", field);
                return false;
            }

            if (!Guid.TryParse(raw, out value) || value == Guid.Empty)
            {
                failure = Failure("invalid_request", $"{field} must be a non-empty GUID.", field);
                return false;
            }

            failure = null;
            return true;
        }

        private static JsonArray ReadStringArray(Dictionary<string, JsonElement> args, string name)
        {
            var array = new JsonArray();
            if (!args.TryGetValue(name, out var el) || el.ValueKind != JsonValueKind.Array)
                return array;

            foreach (var item in el.EnumerateArray())
            {
                if (item.ValueKind == JsonValueKind.String)
                    array.Add(item.GetString());
            }

            return array;
        }

        private static bool HasRole(Artifact artifact, string role)
            => artifact.Files.Any(f => string.Equals(f.Role, role, StringComparison.Ordinal));

        private static string? ReadString(JsonObject obj, string name)
            => obj.TryGetPropertyValue(name, out var node)
                && node is JsonValue value
                && value.TryGetValue<string>(out var text)
                    ? text
                    : null;

        private static string? ReadString(
            IReadOnlyDictionary<string, JsonNode?> values,
            string name)
            => values.TryGetValue(name, out var node)
                && node is JsonValue value
                && value.TryGetValue<string>(out var text)
                    ? text
                    : null;

        private static string StateToString(ReconstructionJobState state)
            => state switch
            {
                ReconstructionJobState.CancellationRequested => "cancellation_requested",
                _ => state.ToString().ToLowerInvariant(),
            };

        private static string StageToString(ReconstructionJobStage stage)
            => stage.ToString().ToLowerInvariant();
    }
}
