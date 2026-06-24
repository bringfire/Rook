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
using Rook.Services.Reconstruction.Fal;

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
        public const string OpCleanupPreparedImport = "cleanup_prepared_import";
        public const string OpImportPackage = "import_package";
        public const string OpRemoveBackground = "remove_background";
        public const string OpAssembleViewSet = "assemble_view_set";

        public const int DefaultListJobsLimit = 50;

        private readonly ReconstructionModelCatalog _catalog;
        private readonly ReconstructionJobManager _manager;
        private readonly ArtifactStore _store;
        private readonly IReconstructionViewSetAssembler _viewSetAssembler;
        private readonly IReconstructionImportClient? _importClient;

        public ReconstructionOpHandler(
            ReconstructionModelCatalog catalog,
            ReconstructionJobManager manager,
            ArtifactStore store,
            IReconstructionViewSetAssembler viewSetAssembler,
            IReconstructionImportClient? importClient = null)
        {
            _catalog = catalog ?? throw new ArgumentNullException(nameof(catalog));
            _manager = manager ?? throw new ArgumentNullException(nameof(manager));
            _store = store ?? throw new ArgumentNullException(nameof(store));
            _viewSetAssembler = viewSetAssembler ?? throw new ArgumentNullException(nameof(viewSetAssembler));
            _importClient = importClient;
        }

        // Exposed only so RookSubsystemRoot can dispose the background-execution manager during
        // subsystem teardown (mirrors the image/video subsystems). Not part of the op surface.
        internal ReconstructionJobManager Manager => _manager;

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
                    OpRemoveBackground => await RemoveBackgroundAsync(body, cancellationToken).ConfigureAwait(false),
                    OpStatus => await StatusAsync(args, cancellationToken).ConfigureAwait(false),
                    OpCancel => await CancelAsync(args, cancellationToken).ConfigureAwait(false),
                    OpImportPackage => await ImportAsync(args, cancellationToken).ConfigureAwait(false),
                    OpModels or OpListJobs or OpResult or OpPrepareImport or OpRecordImport or OpCleanupPreparedImport =>
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
                    OpResult => Result(args),
                    OpPrepareImport => PrepareImport(args),
                    OpRecordImport => RecordImport(args),
                    OpCleanupPreparedImport => CleanupPreparedImport(args),
                    OpAssembleViewSet => AssembleViewSet(args, body),
                    OpSubmit or OpStatus or OpCancel or OpImportPackage or OpRemoveBackground => Fail(
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

        // Tasks whose models actually produce 3D output and therefore belong in the reconstruct picker.
        // remove_background (birefnet) is a preprocessing op, not a 3D producer, so it is excluded here.
        // multi_image_to_3d / text_to_3d can be added when those land.
        // A model is a 3D producer for the picker iff it advertises an importable model output role —
        // capability, not task. Keeps birefnet (image/mask only) out while admitting hunyuan/pro/meshy.
        private static readonly string[] ImportableModelRoles = { "model_glb", "model_obj" };

        private static bool ProducesImportable3D(ReconstructionModelEntry m)
            => m.OutputRoles.Any(r => Array.IndexOf(ImportableModelRoles, r) >= 0);

        private ApiResponse Models(Dictionary<string, JsonElement> args)
        {
            var includeExperimental = GetBoolArg(args, "include_experimental") ?? false;
            var includeHidden = GetBoolArg(args, "include_hidden") ?? false;
            return Ok(new Dictionary<string, object?>
            {
                ["models"] = _catalog
                    .List(includeExperimental, includeHidden)
                    .Where(ProducesImportable3D)
                    .Select(ModelToObj)
                    .ToArray(),
                ["include_experimental"] = includeExperimental,
                ["include_hidden"] = includeHidden,
                ["warnings"] = Array.Empty<object>(),
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

        // Explicit background-removal op. Parses the minimal bg-removal request
        // ({source_artifact_id (required), source_role? (default "image"), model_id?}) into a submit
        // request with empty options + empty preprocessing chain, then drives the manager's dedicated
        // remove_background entry. Returns the same job envelope as SubmitAsync on success.
        private async Task<ApiResponse> RemoveBackgroundAsync(string? body, CancellationToken ct)
        {
            Dictionary<string, JsonElement> args;
            try { args = ParseObjectBody(body); }
            catch (ArgumentException ex)
            {
                return Fail(Failure("invalid_request", ex.Message, "body"), 400);
            }

            if (!TryParseGuid(args, "source_artifact_id", out var sourceArtifactId, out var failure))
                return Fail(failure!, 400);

            var sourceRole = GetStringArg(args, "source_role");
            sourceRole = string.IsNullOrWhiteSpace(sourceRole) ? "image" : sourceRole;
            var modelId = GetStringArg(args, "model_id") ?? string.Empty;

            var request = new ReconstructionSubmitRequest(
                sourceArtifactId,
                sourceRole!,
                modelId,
                Array.Empty<ReconstructionPreprocessingStageRequest>(),
                new JsonObject(),
                EstimateRequested: false);

            var result = await _manager.SubmitRemoveBackgroundAsync(request, ct).ConfigureAwait(false);
            if (!result.Success)
                return Fail(result.Failure!, StatusFor(result.Failure!));

            return Ok(JobToObj(result.Job!));
        }

        // Thin adapter to the native importer (loopback client). The native route stays
        // authoritative; this op only forwards {package_id} and relays the unwrapped result.
        private async Task<ApiResponse> ImportAsync(
            Dictionary<string, JsonElement> args,
            CancellationToken ct)
        {
            if (!TryParseGuid(args, "package_id", out var packageId, out var failure))
                return Fail(failure!, 400);
            if (_importClient is null)
                return Fail(Failure("native_unavailable", "Reconstruction import client is not configured.", null, retryable: true), 503);

            var outcome = await _importClient.ImportAsync(packageId, ct).ConfigureAwait(false);
            if (!outcome.Success)
                return Fail(outcome.Failure!, StatusFor(outcome.Failure!));
            return Ok(outcome.Data!);
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

        private async Task<ApiResponse> StatusAsync(
            Dictionary<string, JsonElement> args,
            CancellationToken ct)
        {
            if (!TryParseJobId(args, out var jobId, out var failure))
                return Fail(failure!, 400);

            var result = await _manager.StatusAsync(jobId, ct).ConfigureAwait(false);
            if (!result.Success)
                return Fail(result.Failure!, StatusFor(result.Failure!));

            var job = JobToObj(result.Job!);
            job["result_available"] = result.ResultAvailable;
            return Ok(new Dictionary<string, object?>
            {
                ["job"] = job,
                ["result_available"] = result.ResultAvailable,
                ["warnings"] = Array.Empty<object>(),
            });
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

            // Pure serializer over the manager-owned result kind — never re-infer from artifacts.
            var data = new Dictionary<string, object?>
            {
                ["job_id"] = result.JobId.ToString("D"),
                ["result_artifact_id"] = result.ResultArtifactId?.ToString("D"),
                ["result_available"] = result.ResultAvailable,
                ["result_kind"] = result.ResultKind,
                ["warnings"] = result.Warnings.Select(WarningToObj).ToArray(),
            };
            if (string.Equals(result.ResultKind, ReconstructionArtifactKinds.PreprocessedImage, StringComparison.Ordinal))
            {
                // Non-3D result: image-role metadata, never a 3D package summary.
                data["asset_roles"] = (result.AssetRoles ?? Array.Empty<string>()).ToArray();
                data["package"] = null;
            }
            else
            {
                // 3D package: PackageSummary is built ONLY here (the envelope says it's a package).
                data["package"] = result.ResultArtifactId.HasValue && result.ResultAvailable
                    ? PackageSummary(result.ResultArtifactId.Value)
                    : null;
            }
            return Ok(data);
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
            var providerFileNames = ProviderFileNamesByRole(packageId, package);
            var assetPath = _store.GetBlobAbsolutePath(packageId, assetRole!);
            var importId = ImportIdForPrepare(args);
            var primaryFileName = FileNameForRole(providerFileNames, assetRole!, assetPath);
            var companionFiles = CompanionFiles(package, manifest!, assetRole!, providerFileNames).ToArray();
            var importPath = assetPath;
            string? sourcePath = null;
            if (string.Equals(assetRole, ReconstructionFileRoles.ModelObj, StringComparison.Ordinal)
                && companionFiles.Length > 0)
            {
                var staged = StageObjImportBundle(
                    assetPath,
                    primaryFileName,
                    importId,
                    companionFiles,
                    out failure);
                if (failure is not null) return Fail(failure, StatusFor(failure));
                importPath = staged!;
                sourcePath = assetPath;
            }

            var data = new Dictionary<string, object?>
            {
                ["package_id"] = packageId.ToString("D"),
                ["job_id"] = ReadString(package.Metadata, "job_id"),
                ["import_id"] = importId.ToString("D"),
                ["asset_role"] = assetRole,
                ["path"] = importPath,
                ["file_name"] = primaryFileName,
                ["targetLayer"] = GetStringArg(args, "targetLayer"),
                ["companion_files"] = companionFiles,
            };
            var materialRepair = MaterialRepair(package, importId, providerFileNames);
            if (materialRepair is not null)
                data["material_repair"] = materialRepair;
            if (!string.IsNullOrWhiteSpace(sourcePath))
                data["source_path"] = sourcePath;
            return Ok(data);
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

            var importEntry = new JsonObject
            {
                ["import_id"] = parsedImportId.ToString("D"),
                ["job_id"] = GetStringArg(args, "job_id"),
                ["asset_role"] = GetStringArg(args, "asset_role") ?? GetStringArg(args, "assetRole"),
                ["path"] = GetStringArg(args, "path"),
                ["source_path"] = GetStringArg(args, "source_path"),
                ["imported_ids"] = ReadStringArray(args, "imported_ids"),
                ["associated"] = GetBoolArg(args, "associated") ?? false,
                ["association_error"] = GetStringArg(args, "association_error"),
                ["recorded_at"] = DateTimeOffset.UtcNow.ToString("O", CultureInfo.InvariantCulture),
            };
            var replacedExisting = false;
            for (var i = 0; i < imports.Count; i++)
            {
                if (imports[i] is JsonObject existing
                    && string.Equals(ReadString(existing, "import_id"), parsedImportId.ToString("D"), StringComparison.Ordinal))
                {
                    imports[i] = importEntry;
                    replacedExisting = true;
                    break;
                }
            }

            if (!replacedExisting)
                imports.Add(importEntry);

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
                ["idempotent_replay"] = replacedExisting,
            });
        }

        private ApiResponse CleanupPreparedImport(Dictionary<string, JsonElement> args)
        {
            if (!TryParseGuid(args, "package_id", out var packageId, out var failure))
                return Fail(failure!, 400);
            if (!TryParseGuid(args, "import_id", out var importId, out failure))
                return Fail(failure!, 400);

            var path = GetStringArg(args, "path");
            if (string.IsNullOrWhiteSpace(path))
                return Fail(Failure("invalid_request", "path is required.", "path"), 400);

            var package = _store.Get(packageId);
            if (package is null)
                return Fail(Failure("not_found", "Reconstruction package was not found.", "package_id"), 404);
            if (!string.Equals(package.Kind, ReconstructionArtifactKinds.Package, StringComparison.Ordinal))
                return Fail(Failure("invalid_request", "Artifact is not a reconstruction package.", "package_id"), 400);
            if (package.Files.Count == 0)
                return Fail(Failure("invalid_package", "Reconstruction package has no files.", "package_id"), 400);

            var artifactDir = Path.GetDirectoryName(_store.GetBlobAbsolutePath(packageId, package.Files[0].Role));
            if (string.IsNullOrWhiteSpace(artifactDir))
                return Fail(Failure("invalid_package", "Reconstruction package directory could not be resolved.", "package_id"), 400);

            var expectedBundleDir = Path.GetFullPath(Path.Combine(artifactDir, $"import_bundle_{importId:N}"));
            var requestedPath = Path.GetFullPath(path!);
            var requestedBundleDir = Directory.Exists(requestedPath)
                ? requestedPath
                : Path.GetDirectoryName(requestedPath);
            if (string.IsNullOrWhiteSpace(requestedBundleDir)
                || !string.Equals(
                    Path.GetFullPath(requestedBundleDir),
                    expectedBundleDir,
                    StringComparison.OrdinalIgnoreCase))
            {
                return Fail(
                    Failure("invalid_request", "path is not the prepared import bundle for import_id.", "path"),
                    400);
            }

            if (!Directory.Exists(expectedBundleDir))
            {
                return Ok(new Dictionary<string, object?>
                {
                    ["package_id"] = packageId.ToString("D"),
                    ["import_id"] = importId.ToString("D"),
                    ["bundle_path"] = expectedBundleDir,
                    ["removed"] = false,
                });
            }

            try
            {
                Directory.Delete(expectedBundleDir, recursive: true);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                return Fail(
                    Failure(
                        "cleanup_failed",
                        "Prepared reconstruction import bundle could not be removed.",
                        null,
                        retryable: true),
                    500);
            }

            return Ok(new Dictionary<string, object?>
            {
                ["package_id"] = packageId.ToString("D"),
                ["import_id"] = importId.ToString("D"),
                ["bundle_path"] = expectedBundleDir,
                ["removed"] = true,
            });
        }

        private ApiResponse AssembleViewSet(Dictionary<string, JsonElement> args, string? body)
        {
            var request = ReconstructionViewSetRequest.TryParse(body, out var parseFailure);
            if (request is null)
                return Fail(parseFailure!, StatusFor(parseFailure!));

            var outcome = _viewSetAssembler.Assemble(request);
            if (!outcome.Success)
                return Fail(outcome.Failure!, StatusFor(outcome.Failure!));

            var artifact = outcome.Artifact!;
            return Ok(new Dictionary<string, object?>
            {
                ["view_set_artifact_id"] = artifact.Id.ToString("D"),
                ["kind"] = artifact.Kind,
                ["slots_expected"] = outcome.SlotsExpected,
                ["slots_present"] = outcome.SlotsPresent,
                ["complete"] = outcome.Complete,
                ["parent_ids"] = artifact.ParentIds.Select(p => p.ToString("D")).ToArray(),
                ["views"] = outcome.Views,   // assembler-built rows; same source as artifact metadata (no drift)
                ["warnings"] = Array.Empty<object>(),
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
            string assetRole,
            IReadOnlyDictionary<string, string> providerFileNames)
        {
            var emitted = new HashSet<string>(StringComparer.Ordinal);

            if (manifest["asset_bindings"]?[assetRole]?["companion_roles"] is JsonArray companions)
            {
                foreach (var roleNode in companions)
                {
                    if (roleNode is JsonValue value &&
                        value.TryGetValue<string>(out var role) &&
                        HasRole(package, role) &&
                        emitted.Add(role))
                    {
                        yield return CompanionEntry(package, role, providerFileNames);
                    }
                }
            }

            // The static manifest binds only the generic `texture` companion, but PBR packages carry
            // detailed texture roles (texture_base_color, texture_normal, …) the result mapper emits per
            // map. Stage every texture* role present in the package so an OBJ/MTL bundle imports with all
            // of its images even when no generic `texture` blob exists.
            if (string.Equals(assetRole, ReconstructionFileRoles.ModelObj, StringComparison.Ordinal))
            {
                foreach (var file in package.Files)
                {
                    if (file.Role.StartsWith("texture", StringComparison.Ordinal) && emitted.Add(file.Role))
                        yield return CompanionEntry(package, file.Role, providerFileNames);
                }
            }
        }

        private Dictionary<string, object?> CompanionEntry(
            Artifact package,
            string role,
            IReadOnlyDictionary<string, string> providerFileNames)
        {
            var path = _store.GetBlobAbsolutePath(package.Id, role);
            return new Dictionary<string, object?>
            {
                ["role"] = role,
                ["path"] = path,
                ["file_name"] = FileNameForRole(providerFileNames, role, path),
            };
        }

        private Dictionary<string, object?>? MaterialRepair(
            Artifact package,
            Guid importId,
            IReadOnlyDictionary<string, string> providerFileNames)
        {
            var baseColorRole = BaseColorTextureRole(package);
            if (baseColorRole is null) return null;

            var maps = new List<object?>
            {
                MaterialMapEntry(package, "base_color", baseColorRole, providerFileNames),
            };

            if (HasRole(package, "texture_normal"))
                maps.Add(MaterialMapEntry(package, "normal", "texture_normal", providerFileNames));
            if (HasRole(package, "texture_roughness"))
                maps.Add(MaterialMapEntry(package, "roughness", "texture_roughness", providerFileNames));
            if (HasRole(package, "texture_metallic"))
                maps.Add(MaterialMapEntry(package, "metallic", "texture_metallic", providerFileNames));

            return new Dictionary<string, object?>
            {
                ["material_name"] = "Rook Reconstruction " + importId.ToString("N").Substring(0, 8),
                ["maps"] = maps,
            };
        }

        private Dictionary<string, object?> MaterialMapEntry(
            Artifact package,
            string channel,
            string role,
            IReadOnlyDictionary<string, string> providerFileNames)
        {
            var path = _store.GetBlobAbsolutePath(package.Id, role);
            return new Dictionary<string, object?>
            {
                ["channel"] = channel,
                ["role"] = role,
                ["path"] = path,
                ["file_name"] = FileNameForRole(providerFileNames, role, path),
            };
        }

        private static string? BaseColorTextureRole(Artifact package)
        {
            if (HasRole(package, "texture_base_color"))
                return "texture_base_color";
            if (HasRole(package, ReconstructionFileRoles.Texture))
                return ReconstructionFileRoles.Texture;

            return package.Files
                .Select(f => f.Role)
                .FirstOrDefault(r =>
                    r.StartsWith("texture", StringComparison.Ordinal)
                    && (r.IndexOf("albedo", StringComparison.OrdinalIgnoreCase) >= 0
                        || r.IndexOf("diffuse", StringComparison.OrdinalIgnoreCase) >= 0
                        || r.IndexOf("color", StringComparison.OrdinalIgnoreCase) >= 0));
        }

        private string? StageObjImportBundle(
            string sourcePath,
            string primaryFileName,
            Guid importId,
            IReadOnlyList<Dictionary<string, object?>> companionFiles,
            out ReconstructionFailure? failure)
        {
            failure = null;
            var sourceDir = Path.GetDirectoryName(sourcePath);
            if (string.IsNullOrWhiteSpace(sourceDir) || !File.Exists(sourcePath))
            {
                failure = Failure(
                    "invalid_package",
                    "Reconstruction OBJ source file was not found.",
                    "package_id");
                return null;
            }

            var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            if (!ReserveImportFileName(names, primaryFileName, out failure))
                return null;

            foreach (var companion in companionFiles)
            {
                var companionPath = companion.TryGetValue("path", out var pathObj)
                    ? pathObj as string
                    : null;
                var companionName = companion.TryGetValue("file_name", out var nameObj)
                    ? nameObj as string
                    : null;
                if (string.IsNullOrWhiteSpace(companionPath) || !File.Exists(companionPath))
                {
                    failure = Failure(
                        "invalid_package",
                        "Reconstruction OBJ companion file was not found.",
                        "package_id");
                    return null;
                }
                if (!ReserveImportFileName(names, companionName ?? Path.GetFileName(companionPath), out failure))
                    return null;
            }

            var bundleDir = Path.Combine(sourceDir, $"import_bundle_{importId:N}");
            try
            {
                Directory.CreateDirectory(bundleDir);
                var stagedPrimary = Path.Combine(bundleDir, primaryFileName);
                File.Copy(sourcePath, stagedPrimary, overwrite: false);
                foreach (var companion in companionFiles)
                {
                    var companionPath = (string)companion["path"]!;
                    var companionName = (string)companion["file_name"]!;
                    File.Copy(companionPath, Path.Combine(bundleDir, companionName), overwrite: false);
                }

                return stagedPrimary;
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                TryDeleteDirectory(bundleDir);
                failure = Failure(
                    "import_failed",
                    "Reconstruction OBJ import bundle could not be staged.",
                    null,
                    retryable: true);
                return null;
            }
        }

        private static bool ReserveImportFileName(
            HashSet<string> names,
            string? fileName,
            out ReconstructionFailure? failure)
        {
            failure = null;
            var safeName = SafeProviderFileName(fileName);
            if (string.IsNullOrWhiteSpace(safeName))
            {
                failure = Failure(
                    "invalid_package",
                    "Reconstruction OBJ import bundle contains an invalid filename.",
                    "package_id");
                return false;
            }

            if (names.Add(safeName!))
                return true;

            failure = Failure(
                "filename_collision",
                $"Reconstruction OBJ import bundle contains duplicate provider filename '{safeName}'.",
                "package_id");
            return false;
        }

        private static void TryDeleteDirectory(string path)
        {
            try
            {
                if (Directory.Exists(path))
                    Directory.Delete(path, recursive: true);
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }

        private Dictionary<string, string> ProviderFileNamesByRole(Guid packageId, Artifact package)
        {
            try
            {
                var json = JsonNode.Parse(File.ReadAllText(
                    _store.GetBlobAbsolutePath(packageId, ReconstructionFileRoles.ProviderResultJson))) as JsonObject;
                return json is null ? new() : ReconstructionProviderFileNames.ProviderFileNamesByRole(json, package);
            }
            catch (Exception ex) when (ex is IOException or JsonException or InvalidOperationException)
            {
                return new();
            }
        }

        private static string FileNameForRole(
            IReadOnlyDictionary<string, string> providerFileNames,
            string role,
            string path)
            => providerFileNames.TryGetValue(role, out var fileName) && !string.IsNullOrWhiteSpace(fileName)
                ? fileName
                : Path.GetFileName(path);

        private static string? SafeProviderFileName(string? fileName)
        {
            if (string.IsNullOrWhiteSpace(fileName)) return null;
            var safe = Path.GetFileName(fileName);
            return string.IsNullOrWhiteSpace(safe) || safe == "." || safe == ".."
                ? null
                : safe;
        }

        private Dictionary<string, object?>? PackageSummary(Guid packageId)
        {
            var package = _store.Get(packageId);
            if (package is null)
                return null;

            var preferred = (string?)null;
            var resolvedImportRole = (string?)null;
            var manifest = ReadImportManifest(packageId, out _);
            if (manifest is not null)
            {
                preferred = ReadString(manifest, "preferred_asset");
                // Same resolver the native import path uses (via prepare_import); passive — returns null on
                // an unresolvable package and never throws. Its failure detail is intentionally discarded
                // (out _): null is the whole signal the UI needs, and no failure leaks into job_result.
                resolvedImportRole = ResolveAssetRole(package, manifest, requestedRole: null, out _);
            }

            return new Dictionary<string, object?>
            {
                ["artifact_id"] = package.Id.ToString("D"),
                ["kind"] = package.Kind,
                ["asset_roles"] = package.Files
                    .Select(f => f.Role)
                    .Where(IsAssetRole)
                    .ToArray(),
                ["preferred_asset_role"] = preferred,
                ["resolved_import_role"] = resolvedImportRole,
            };
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
                ["input"] = InputToObj(model.Input),
                ["prompt"] = PromptToObj(model.Prompt),
                ["options"] = model.Options is null ? null : model.Options.Select(OptionToObj).ToArray(),
                ["supports_single_image"] = !string.IsNullOrWhiteSpace(model.Input?.SourceField),
                ["supports_multi_view"] = (model.Input?.ViewSlots?.Length ?? 0) > 1,
                ["docs_url"] = model.DocsUrl,
            };

        private static Dictionary<string, object?> OptionToObj(ReconstructionOptionDescriptor option)
            => new()
            {
                ["key"] = option.Key,
                ["label"] = option.Label,
                ["kind"] = option.Kind,
                ["default"] = option.Default,
                ["allowed_values"] = option.AllowedValues,
                ["min"] = option.Min,
                ["max"] = option.Max,
                ["step"] = option.Step,
                ["ignored_when"] = option.IgnoredWhen is null
                    ? null
                    : new Dictionary<string, object?>
                    {
                        ["key"] = option.IgnoredWhen.Key,
                        ["equals"] = option.IgnoredWhen.EqualsValue,
                    },
            };

        private static Dictionary<string, object?>? InputToObj(ReconstructionInputMetadata? input)
        {
            if (input is null)
                return null;
            var obj = new Dictionary<string, object?>
            {
                ["mode"] = input.Mode,
                ["source_field"] = input.SourceField,
            };
            if (input.ViewSlots is not null)
            {
                obj["view_slots"] = input.ViewSlots
                    .Select(slot => new Dictionary<string, object?>
                    {
                        ["role"] = slot.Role,
                        ["field"] = slot.Field,
                        ["required"] = slot.Required,
                    })
                    .ToArray();
            }
            if (input.Array is not null)
            {
                obj["array"] = new Dictionary<string, object?>
                {
                    ["field"] = input.Array.Field,
                    ["min"] = input.Array.Min,
                    ["max"] = input.Array.Max,
                };
            }
            return obj;
        }

        private static Dictionary<string, object?>? PromptToObj(ReconstructionPromptMetadata? prompt)
            => prompt is null
                ? null
                : new Dictionary<string, object?>
                {
                    ["supported"] = prompt.Supported,
                    ["required"] = prompt.Required,
                    ["kind"] = prompt.Kind,
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

        internal static int StatusFor(ReconstructionFailure failure)
            => failure.Code switch
            {
                "not_found" => 404,
                "invalid_json" or "invalid_request" or "filename_collision" or "invalid_package"
                    or "invalid_source_role"
                    or "invalid_source_artifact" or "invalid_source_file"
                    or "invalid_source_dimensions"
                    or "invalid_view_set" or "invalid_provenance" => 400,
                // Required configuration absent — the request cannot be fulfilled. Not retryable and
                // not a provider outage (provider_unavailable -> 503 covers that); the body carries the
                // remediation text.
                "missing_credential" => 400,
                "quota_exceeded" => 429,
                "provider_unavailable" or "native_unavailable" => 503,
                "content_policy" => 422,
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

        private static Guid ImportIdForPrepare(Dictionary<string, JsonElement> args)
        {
            var raw = GetStringArg(args, "import_id");
            return Guid.TryParse(raw, out var importId) && importId != Guid.Empty
                ? importId
                : Guid.NewGuid();
        }

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

        private static bool IsAssetRole(string role)
            => role.StartsWith("model_", StringComparison.Ordinal)
                || string.Equals(role, ReconstructionFileRoles.MaterialMtl, StringComparison.Ordinal)
                || role.StartsWith("texture", StringComparison.Ordinal)
                || string.Equals(role, ReconstructionFileRoles.Thumbnail, StringComparison.Ordinal);

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
