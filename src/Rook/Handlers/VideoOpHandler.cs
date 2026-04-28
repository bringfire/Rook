using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rhino;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;

// Both Generation.JobPricing (modality-neutral; used by typed pricing
// model outputs) and Video.JobPricing (durable ledger record type) exist
// in PR-2's coexistence period. The HTTP boundary projects the ledger
// shape, so unqualified `JobPricing` here MUST resolve to the video one.
using JobPricing = Rook.Services.Vision.Video.JobPricing;

namespace Rook.Handlers
{
    /// <summary>
    /// Single validation boundary for the V2 video routes. Dispatched
    /// through the <c>vision_dispatch</c> bridge callback (ABI v14)
    /// alongside the image-side <see cref="VisionHandler"/>; the
    /// trampoline (<c>NativeGhBridgeRegistrar.HandleVisionDispatch</c>)
    /// peeks the long-form op string and routes to the appropriate
    /// dispatcher on this handler.
    ///
    /// Threading model:
    /// <list type="bullet">
    ///   <item><see cref="DispatchAsync"/> — async, threadpool. Used by
    ///         <c>submit_video_job</c> / <c>cancel_video_job</c>.
    ///         <c>SubmitAsync</c> resolves media bytes (disk reads) and
    ///         kicks off a background task; <c>CancelAsync</c> makes a
    ///         provider HTTP call. 180 s ceiling matches the
    ///         async-bridge timeout in the trampoline.</item>
    ///   <item><see cref="DispatchOffUi"/> — sync, threadpool. Used by
    ///         <c>get_video_job</c> / <c>get_video_job_result</c> /
    ///         <c>estimate_video_job</c>. Reads from the in-memory cache
    ///         + ledger; pure-CPU pricing. 30 s ceiling.</item>
    /// </list>
    ///
    /// HTTP status mapping is explicit per <see cref="VideoErrorCode"/>
    /// — <c>InvalidRequest</c> → 400, <c>UnsupportedMedia</c> → 415,
    /// <c>DependencyUnavailable</c> → 503, <c>ExecutionFailed</c> → 500,
    /// <c>Cancelled</c> / <c>Interrupted</c> → 200 (terminal-state read
    /// is a successful read). Status is determined by the code, not by
    /// <see cref="VideoJobError.Retryable"/>: a retryable
    /// <c>ExecutionFailed</c> is still 500.
    ///
    /// V2 contract: HTTP submit/estimate accept artifact_id media refs
    /// only. Path-kind refs are rejected at <see cref="ParseMediaRef"/>
    /// with <c>InvalidRequest</c> + <c>field:"kind"</c>. The domain
    /// still represents path refs, but V2's adapter boundary is the
    /// rejection point and <see cref="ArtifactOnlyVideoMediaResolver"/>
    /// is the defense-in-depth layer.
    /// </summary>
    public class VideoOpHandler
    {
        public const string OpSubmit = "submit_video_job";
        public const string OpStatus = "get_video_job";
        public const string OpCancel = "cancel_video_job";
        public const string OpResult = "get_video_job_result";
        public const string OpEstimate = "estimate_video_job";

        // V3 introduced these as bridge-only read ops (VisionWebSurface
        // .OpRoutes only). PR-V4 promotes them to native HTTP + MCP
        // parity per the parity rule: every video op now has a native
        // route, an MCP tool, and a bridge op. The C# handler arm is
        // unchanged — V4 just lights up the trampoline allowlist
        // entry and the C++ route handler.
        public const string OpListJobs = "list_video_jobs";
        public const string OpListModels = "list_video_models";

        /// <summary>
        /// Default <c>limit</c> for <see cref="OpListJobs"/> when the
        /// caller omits the field. Mirrors <c>list_artifacts</c>'s
        /// default-100/hard-max-500 shape but smaller — the queue panel
        /// scope is "active + recent" not full history.
        /// </summary>
        public const int DefaultListJobsLimit = 50;

        private readonly IVideoJobManager _manager;
        private readonly IVideoProviderRegistry _registry;
        private readonly IVideoCostEstimator _estimator;

        public VideoOpHandler(
            IVideoJobManager manager,
            IVideoProviderRegistry registry,
            IVideoCostEstimator estimator)
        {
            _manager = manager ?? throw new ArgumentNullException(nameof(manager));
            _registry = registry ?? throw new ArgumentNullException(nameof(registry));
            _estimator = estimator ?? throw new ArgumentNullException(nameof(estimator));
        }

        // ─── Async dispatcher (submit, cancel) ───────────────────────────

        public async Task<ApiResponse> DispatchAsync(
            string? body, CancellationToken cancellationToken = default)
        {
            Dictionary<string, JsonElement> args;
            try { args = ParseObjectBody(body); }
            catch (ArgumentException ex)
            {
                return FailInvalidRequest(ex.Message);
            }

            var op = GetStringArg(args, "op");
            if (string.IsNullOrEmpty(op))
                return FailInvalidRequest("Video request missing required 'op' discriminator.");

            try
            {
                return op switch
                {
                    OpSubmit => await SubmitAsync(args, cancellationToken).ConfigureAwait(false),
                    OpCancel => await CancelAsync(args, cancellationToken).ConfigureAwait(false),
                    OpStatus or OpResult or OpEstimate or OpListJobs or OpListModels => FailInvalidRequest(
                        $"op '{op}' must be routed through the off-UI dispatcher, not the async dispatcher."),
                    _ => FailInvalidRequest($"Unknown video op '{op}'."),
                };
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine(
                    $"Rook Video: unhandled error in async op '{op}': {ex.GetType().Name}: {ex.Message}");
                return FailExecutionFailed($"Video op '{op}' failed unexpectedly.");
            }
        }

        // ─── Off-UI sync dispatcher (status, result, estimate) ───────────

        public ApiResponse DispatchOffUi(string? body)
        {
            Dictionary<string, JsonElement> args;
            try { args = ParseObjectBody(body); }
            catch (ArgumentException ex)
            {
                return FailInvalidRequest(ex.Message);
            }

            var op = GetStringArg(args, "op");
            if (string.IsNullOrEmpty(op))
                return FailInvalidRequest("Video request missing required 'op' discriminator.");

            try
            {
                return op switch
                {
                    OpStatus => GetStatus(args),
                    OpResult => GetResult(args),
                    OpEstimate => Estimate(args),
                    OpListJobs => ListJobs(args),
                    OpListModels => ListModels(),
                    OpSubmit or OpCancel => FailInvalidRequest(
                        $"op '{op}' must be routed through the async dispatcher, not the off-UI dispatcher."),
                    _ => FailInvalidRequest($"Unknown video op '{op}'."),
                };
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine(
                    $"Rook Video: unhandled error in off-UI op '{op}': {ex.GetType().Name}: {ex.Message}");
                return FailExecutionFailed($"Video op '{op}' failed unexpectedly.");
            }
        }

        // ─── Per-op handlers ─────────────────────────────────────────────

        private async Task<ApiResponse> SubmitAsync(
            Dictionary<string, JsonElement> args, CancellationToken ct)
        {
            var (request, parseErr) = ParseGenerationRequest(args);
            if (parseErr is not null) return FailWithError(parseErr);

            var result = await _manager.SubmitAsync(request!, ct).ConfigureAwait(false);

            if (result.Error is not null)
                return FailWithError(result.Error);

            return Ok(new Dictionary<string, object?>
            {
                ["job_id"] = result.JobId!.Value.ToString("D"),
                ["state"] = StateToString(result.State),
            });
        }

        private async Task<ApiResponse> CancelAsync(
            Dictionary<string, JsonElement> args, CancellationToken ct)
        {
            if (!TryParseJobId(args, out var jobId, out var parseErr))
                return FailWithError(parseErr!);

            var result = await _manager.CancelAsync(jobId, ct).ConfigureAwait(false);

            if (result.Error is not null)
                return FailWithError(result.Error);

            return Ok(new Dictionary<string, object?>
            {
                ["job_id"] = jobId.ToString("D"),
                ["state"] = StateToString(result.State),
            });
        }

        private ApiResponse GetStatus(Dictionary<string, JsonElement> args)
        {
            if (!TryParseJobId(args, out var jobId, out var parseErr))
                return FailWithError(parseErr!);

            var result = _manager.GetStatusAsync(jobId, default)
                .GetAwaiter().GetResult();

            // Outer-failure semantics: only InvalidRequest at this level
            // means the operation failed (e.g., unknown jobId). Other
            // error codes (Cancelled, Interrupted, ExecutionFailed)
            // accompany terminal-state reads and ride inside a successful
            // response — the caller wanted the state and got it.
            if (result.Error is { Code: VideoErrorCode.InvalidRequest })
                return FailWithError(result.Error);

            return Ok(new Dictionary<string, object?>
            {
                ["job_id"] = jobId.ToString("D"),
                ["state"] = StateToString(result.State),
                ["progress"] = result.Progress is null ? null : ProgressToObj(result.Progress),
                ["result_artifact_id"] = result.ResultArtifactId?.ToString("D"),
                ["error"] = result.Error is null ? null : ErrorToObj(result.Error),
            });
        }

        private ApiResponse GetResult(Dictionary<string, JsonElement> args)
        {
            if (!TryParseJobId(args, out var jobId, out var parseErr))
                return FailWithError(parseErr!);

            var result = _manager.FetchResultAsync(jobId, default)
                .GetAwaiter().GetResult();

            if (result.Error is not null)
                return FailWithError(result.Error);

            var files = new List<Dictionary<string, object?>>(result.Files!.Count);
            foreach (var f in result.Files!)
            {
                files.Add(new Dictionary<string, object?>
                {
                    ["role"] = f.Role,
                    ["path"] = f.Path,
                });
            }

            return Ok(new Dictionary<string, object?>
            {
                ["job_id"] = jobId.ToString("D"),
                ["state"] = StateToString(result.State),
                ["result_artifact_id"] = result.ResultArtifactId!.Value.ToString("D"),
                ["files"] = files,
            });
        }

        private ApiResponse Estimate(Dictionary<string, JsonElement> args)
        {
            var (request, parseErr) = ParseGenerationRequest(args);
            if (parseErr is not null) return FailWithError(parseErr);

            if (!_registry.TryResolve(request!.Model, out var model))
            {
                return FailWithError(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: $"Unknown model: '{request.Model}'.",
                    Retryable: false,
                    Field: nameof(VideoGenerationRequest.Model)));
            }

            var result = _estimator.Estimate(model, request);
            if (!result.Success)
                return FailWithError(result.Error!);

            var estimate = result.Estimate!;
            var breakdown = new List<Dictionary<string, object?>>(estimate.Breakdown.Count);
            foreach (var row in estimate.Breakdown)
            {
                breakdown.Add(new Dictionary<string, object?>
                {
                    ["label"] = row.Label,
                    ["dollars_usd"] = row.DollarsUsd,
                });
            }

            return Ok(new Dictionary<string, object?>
            {
                ["dollars_usd"] = estimate.DollarsUsd,
                ["model"] = estimate.Model,
                ["resolution"] = estimate.Resolution,
                ["duration_seconds"] = estimate.DurationSeconds,
                ["number_of_videos"] = estimate.NumberOfVideos,
                ["breakdown"] = breakdown,
                ["pricing"] = PricingToObj(estimate.Pricing),
            });
        }

        // ─── List ops (PR-V3) ────────────────────────────────────────────

        private ApiResponse ListJobs(Dictionary<string, JsonElement> args)
        {
            // Strict-parse the optional limit. Absent → default; integer
            // ≥1 → used (clamped by the manager); anything else (string,
            // negative, fractional, wrong type) → InvalidRequest with
            // field:"limit". This is intentionally stricter than
            // TryGetInt's "default to 0 on bad input" behavior — the
            // contract for limit is positive integer or absent.
            var (limitParsed, limitErr) = TryGetOptionalPositiveInt(args, "limit");
            if (limitErr is not null) return FailWithError(limitErr);
            var limit = limitParsed ?? DefaultListJobsLimit;

            var result = _manager.ListJobsAsync(limit, default).GetAwaiter().GetResult();

            var jobs = new List<Dictionary<string, object?>>(result.Jobs.Count);
            foreach (var entry in result.Jobs)
                jobs.Add(JobListEntryToObj(entry));

            var warnings = new List<Dictionary<string, object?>>(result.Warnings.Count);
            foreach (var w in result.Warnings)
                warnings.Add(WarningToObj(w));

            return Ok(new Dictionary<string, object?>
            {
                ["jobs"] = jobs,
                ["warnings"] = warnings,
                ["applied_limit"] = result.AppliedLimit,
            });
        }

        private ApiResponse ListModels()
        {
            var descriptors = _registry.EnumerateAllModels();
            var models = new List<Dictionary<string, object?>>(descriptors.Count);
            foreach (var d in descriptors)
                models.Add(ModelDescriptorToObj(d));

            return Ok(new Dictionary<string, object?>
            {
                ["models"] = models,
            });
        }

        private static Dictionary<string, object?> JobListEntryToObj(JobListEntry entry) =>
            new()
            {
                ["job_id"] = entry.JobId.ToString("D"),
                ["state"] = StateToString(entry.State),
                // ISO 8601 with offset — preserves the persisted invariant.
                // DateTimeOffset.ToString("o") is the round-trip format;
                // callers parse with new Date(...) on the JS side.
                ["updated_at"] = entry.UpdatedAt.ToString("o", CultureInfo.InvariantCulture),
                ["request_summary"] = new Dictionary<string, object?>
                {
                    ["model"] = entry.Summary.Model,
                    ["mode"] = ModeToString(entry.Summary.Mode),
                    ["duration_seconds"] = entry.Summary.DurationSeconds,
                    ["resolution"] = entry.Summary.Resolution,
                    ["aspect_ratio"] = entry.Summary.AspectRatio,
                },
                ["result_artifact_id"] = entry.ResultArtifactId?.ToString("D"),
                ["error"] = entry.Error is null ? null : ErrorToObj(entry.Error),
            };

        private static Dictionary<string, object?> WarningToObj(LedgerWarning w) =>
            // PR-V3 wire shape per signed-off scope: {line, reason, field}.
            // Drop the synthesized Message — `reason` already encodes the
            // same information as a snake_case enum, and the smaller
            // surface keeps the wire contract tight. Domain-side
            // LedgerWarning still carries Message for in-process logging.
            new()
            {
                ["line"] = w.LineNumber,
                ["reason"] = LedgerReasonToString(w.Reason),
                ["field"] = w.FieldPath,
            };

        private static Dictionary<string, object?> ModelDescriptorToObj(VideoModelDescriptor d) =>
            new()
            {
                ["model_id"] = d.ModelId,
                ["provider_name"] = d.ProviderName,
                ["pricing_kind"] = PricingKindToString(d.PricingKind),
                ["pricing_source"] = d.PricingSource,
                ["capability"] = CapabilityToObj(d.Capability),
            };

        private static Dictionary<string, object?> CapabilityToObj(VideoCapability c)
        {
            var modes = new List<string>(c.Modes.Count);
            foreach (var m in c.Modes) modes.Add(ModeToString(m));

            return new Dictionary<string, object?>
            {
                ["id"] = c.Id,
                ["name"] = c.Name,
                ["status"] = c.Status,
                ["resolutions"] = c.Resolutions,
                ["durations"] = c.Durations,
                ["aspect_ratios"] = c.AspectRatios,
                ["modes"] = modes,
                ["supports_reference_images"] = c.SupportsReferenceImages,
                ["max_reference_images"] = c.MaxReferenceImages,
                ["must_8s_with"] = c.Must8sWith,
            };
        }

        private static string ModeToString(VideoMode mode) => mode switch
        {
            VideoMode.T2V => "t2v",
            VideoMode.I2V => "i2v",
            VideoMode.Interp => "interp",
            _ => mode.ToString().ToLowerInvariant(),
        };

        private static string PricingKindToString(PricingKind kind) => kind switch
        {
            PricingKind.PerSecond => "per_second",
            PricingKind.PerGeneration => "per_generation",
            PricingKind.External => "external",
            _ => kind.ToString().ToLowerInvariant(),
        };

        private static string LedgerReasonToString(LedgerReadErrorReason reason) => reason switch
        {
            LedgerReadErrorReason.MalformedJson => "malformed_json",
            LedgerReadErrorReason.UnsupportedSchemaVersion => "unsupported_schema_version",
            LedgerReadErrorReason.UnknownPricingKind => "unknown_pricing_kind",
            LedgerReadErrorReason.MissingRequiredField => "missing_required_field",
            _ => reason.ToString().ToLowerInvariant(),
        };

        // ─── Request parsing ─────────────────────────────────────────────

        private static bool TryParseJobId(
            Dictionary<string, JsonElement> args,
            out Guid jobId,
            out VideoJobError? error)
        {
            jobId = Guid.Empty;
            var raw = GetStringArg(args, "job_id");
            if (string.IsNullOrEmpty(raw))
            {
                error = new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: "Missing required 'job_id' field.",
                    Retryable: false,
                    Field: "job_id");
                return false;
            }

            if (!Guid.TryParseExact(raw, "D", out var parsed) || parsed == Guid.Empty)
            {
                error = new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: $"'job_id' must be a non-empty GUID in 'D' format, got '{raw}'.",
                    Retryable: false,
                    Field: "job_id");
                return false;
            }

            jobId = parsed;
            error = null;
            return true;
        }

        private static (VideoGenerationRequest? Request, VideoJobError? Error)
            ParseGenerationRequest(Dictionary<string, JsonElement> args)
        {
            var model = GetStringArg(args, "model");
            if (string.IsNullOrEmpty(model))
                return (null, BadField("model", "Missing required 'model' field."));

            var modeStr = GetStringArg(args, "mode") ?? string.Empty;
            if (!TryParseMode(modeStr, out var mode))
                return (null, BadField("mode", $"'mode' must be one of t2v|i2v|interp, got '{modeStr}'."));

            if (!TryGetInt(args, "duration_seconds", out var duration))
                return (null, BadField("duration_seconds", "Missing or invalid 'duration_seconds' (must be int)."));

            var resolution = GetStringArg(args, "resolution");
            if (string.IsNullOrEmpty(resolution))
                return (null, BadField("resolution", "Missing required 'resolution' field."));

            var aspect = GetStringArg(args, "aspect_ratio");
            if (string.IsNullOrEmpty(aspect))
                return (null, BadField("aspect_ratio", "Missing required 'aspect_ratio' field."));

            var prompt = GetStringArg(args, "prompt"); // optional

            VideoMediaRef? startFrame = null, endFrame = null;
            var (startEl, startErr) = GetOptionalObject(args, "start_frame");
            if (startErr is not null) return (null, startErr);
            if (startEl is JsonElement startE)
            {
                var (mr, mrErr) = ParseMediaRef(startE, "start_frame");
                if (mrErr is not null) return (null, mrErr);
                startFrame = mr;
            }

            var (endEl, endErr) = GetOptionalObject(args, "end_frame");
            if (endErr is not null) return (null, endErr);
            if (endEl is JsonElement endE)
            {
                var (mr, mrErr) = ParseMediaRef(endE, "end_frame");
                if (mrErr is not null) return (null, mrErr);
                endFrame = mr;
            }

            List<VideoMediaRef>? referenceFrames = null;
            var (refsEl, refsErr) = GetOptionalArray(args, "reference_frames");
            if (refsErr is not null) return (null, refsErr);
            if (refsEl is JsonElement refsE)
            {
                referenceFrames = new List<VideoMediaRef>(refsE.GetArrayLength());
                int idx = 0;
                foreach (var item in refsE.EnumerateArray())
                {
                    var (mr, mrErr) = ParseMediaRef(item, $"reference_frames[{idx}]");
                    if (mrErr is not null) return (null, mrErr);
                    referenceFrames.Add(mr!);
                    idx++;
                }
            }

            int? seed = null;
            if (TryGetInt(args, "seed", out var seedVal)) seed = seedVal;

            // Options is required and provider-specific. V2 wires Veo as
            // the only provider; the typed VeoOptions is the only shape
            // accepted today. Future providers extend by adding a parser
            // arm here keyed on the resolved provider.
            var (optionsEl, optionsObjErr) = GetOptionalObject(args, "options");
            if (optionsObjErr is not null) return (null, optionsObjErr);
            if (optionsEl is null)
                return (null, BadField("options",
                    "Missing required 'options' field (typed provider options)."));

            var (options, optErr) = ParseVeoOptions(optionsEl.Value);
            if (optErr is not null) return (null, optErr);

            int numberOfVideos = 1;
            if (TryGetInt(args, "number_of_videos", out var nVids))
                numberOfVideos = nVids;

            var request = new VideoGenerationRequest(
                Model: model!,
                Mode: mode,
                DurationSeconds: duration,
                Resolution: resolution!,
                AspectRatio: aspect!,
                Prompt: prompt,
                StartFrame: startFrame,
                EndFrame: endFrame,
                ReferenceFrames: referenceFrames,
                Seed: seed,
                Options: options!,
                NumberOfVideos: numberOfVideos);

            return (request, null);
        }

        /// <summary>
        /// V2 boundary: media refs accepted on the HTTP wire are
        /// artifact_id ONLY. Wire shape per v3.1 D2.1 + scope v3 §4:
        /// <c>{ "kind": "artifact_id", "artifact_id": "&lt;uuid&gt;",
        /// "role": "&lt;role&gt;" }</c>. Path-kind refs are rejected
        /// here with <c>field: "kind"</c> (matches the scope contract
        /// exactly so caller-facing diagnostics are stable). This is
        /// the load-bearing rule — the unauthenticated native HTTP
        /// surface MUST NOT accept arbitrary local paths that could
        /// exfiltrate user images via the Veo provider.
        ///
        /// Field-error naming: the V2 path-kind rejection uses bare
        /// <c>"kind"</c> per the v3 contract; other diagnostic errors
        /// (missing kind, bad GUID, bad role) use the dotted form
        /// <c>"&lt;path&gt;.&lt;subfield&gt;"</c> so callers can
        /// disambiguate which media ref had the problem.
        /// </summary>
        private static (VideoMediaRef? Ref, VideoJobError? Error) ParseMediaRef(
            JsonElement el, string fieldPath)
        {
            if (el.ValueKind != JsonValueKind.Object)
                return (null, BadField(fieldPath,
                    $"'{fieldPath}' must be a JSON object."));

            string? kind = null;
            if (el.TryGetProperty("kind", out var kindEl)
                && kindEl.ValueKind == JsonValueKind.String)
            {
                kind = kindEl.GetString();
            }

            if (string.IsNullOrEmpty(kind))
                return (null, BadField($"{fieldPath}.kind",
                    $"'{fieldPath}.kind' is required and must be a string."));

            // V2 rejection point — bare "kind" field name per scope v3 §4.
            if (string.Equals(kind, "path", StringComparison.Ordinal))
                return (null, BadField("kind",
                    "Path media refs are not supported by the V2 HTTP API. " +
                    "Submit artifact_id refs instead."));

            if (!string.Equals(kind, "artifact_id", StringComparison.Ordinal))
                return (null, BadField($"{fieldPath}.kind",
                    $"'{fieldPath}.kind' must be 'artifact_id', got '{kind}'."));

            // The contract field is "artifact_id" (matches the kind
            // discriminator). Prior versions of this handler read "value"
            // — that was wrong; Codex flagged the schema mismatch.
            string? rawId = null;
            if (el.TryGetProperty("artifact_id", out var idEl)
                && idEl.ValueKind == JsonValueKind.String)
            {
                rawId = idEl.GetString();
            }

            if (string.IsNullOrEmpty(rawId)
                || !Guid.TryParseExact(rawId, "D", out var artifactId)
                || artifactId == Guid.Empty)
            {
                return (null, BadField($"{fieldPath}.artifact_id",
                    $"'{fieldPath}.artifact_id' must be a non-empty GUID in 'D' format."));
            }

            string? role = null;
            if (el.TryGetProperty("role", out var roleEl)
                && roleEl.ValueKind == JsonValueKind.String)
            {
                role = roleEl.GetString();
            }

            try
            {
                return (VideoMediaRef.ForArtifact(artifactId, role), null);
            }
            catch (ArgumentException ex)
            {
                return (null, BadField($"{fieldPath}.role", ex.Message));
            }
        }

        private static (ProviderOptions? Options, VideoJobError? Error) ParseVeoOptions(
            JsonElement el)
        {
            if (el.ValueKind != JsonValueKind.Object)
                return (null, BadField("options", "'options' must be a JSON object."));

            string? raw = null;
            if (el.TryGetProperty("person_generation", out var pgEl)
                && pgEl.ValueKind == JsonValueKind.String)
            {
                raw = pgEl.GetString();
            }

            if (string.IsNullOrEmpty(raw))
                return (null, BadField("options.person_generation",
                    "'options.person_generation' is required and must be a string."));

            return raw!.ToLowerInvariant() switch
            {
                "dont_allow" => (new VeoOptions(PersonGenerationPolicy.DontAllow), null),
                "allow_adult" => (new VeoOptions(PersonGenerationPolicy.AllowAdult), null),
                "allow_all" => (new VeoOptions(PersonGenerationPolicy.AllowAll), null),
                _ => (null, BadField("options.person_generation",
                        $"'options.person_generation' must be one of " +
                        $"dont_allow|allow_adult|allow_all, got '{raw}'.")),
            };
        }

        private static bool TryParseMode(string s, out VideoMode mode)
        {
            switch (s.ToLowerInvariant())
            {
                case "t2v": mode = VideoMode.T2V; return true;
                case "i2v": mode = VideoMode.I2V; return true;
                case "interp": mode = VideoMode.Interp; return true;
                default: mode = default; return false;
            }
        }

        // ─── Response shaping ────────────────────────────────────────────

        private static string StateToString(VideoJobState state) => state switch
        {
            VideoJobState.Queued => "queued",
            VideoJobState.Submitting => "submitting",
            VideoJobState.Polling => "polling",
            VideoJobState.Downloading => "downloading",
            VideoJobState.Saving => "saving",
            VideoJobState.Complete => "complete",
            VideoJobState.Error => "error",
            VideoJobState.Cancelled => "cancelled",
            VideoJobState.Interrupted => "interrupted",
            _ => state.ToString().ToLowerInvariant(),
        };

        private static string ErrorCodeToString(VideoErrorCode code) =>
            ErrorCodeToString(VideoProviderOutcomeAdapters.ToGenerationError(
                new VideoJobError(code, string.Empty, Retryable: false)).Code);

        private static string ErrorCodeToString(GenerationErrorCode code) => code switch
        {
            GenerationErrorCode.InvalidRequest => "invalid_request",
            GenerationErrorCode.UnsupportedMedia => "unsupported_media",
            GenerationErrorCode.DependencyUnavailable => "dependency_unavailable",
            GenerationErrorCode.ExecutionFailed => "execution_failed",
            GenerationErrorCode.Cancelled => "cancelled",
            GenerationErrorCode.Interrupted => "interrupted",
            GenerationErrorCode.QuotaExceeded => "quota_exceeded",
            GenerationErrorCode.ContentPolicy => "content_policy",
            _ => code.ToString().ToLowerInvariant(),
        };

        private static Dictionary<string, object?> ErrorToObj(VideoJobError err) =>
            ErrorToObj(VideoProviderOutcomeAdapters.ToGenerationError(err));

        private static Dictionary<string, object?> ErrorToObj(GenerationError err) =>
            new()
            {
                ["code"] = ErrorCodeToString(err.Code),
                ["message"] = err.Message,
                ["retryable"] = err.Retryable,
                ["field"] = err.Field,
            };

        private static Dictionary<string, object?> ProgressToObj(VideoJobProgress p) =>
            new()
            {
                ["pct"] = p.Pct,
                ["stage"] = p.Stage,
                ["message"] = p.Message,
            };

        private static Dictionary<string, object?> PricingToObj(JobPricing p) =>
            new()
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

        // ─── Status mapping (GenerationErrorCode → HTTP) ─────────────────

        /// <summary>
        /// Maps the typed error code to an HTTP status. By code only —
        /// retryable is orthogonal metadata, not part of the status
        /// decision (a retryable ExecutionFailed is still 500).
        /// </summary>
        internal static int MapStatusFromCode(VideoErrorCode code) =>
            MapStatusFromCode(VideoProviderOutcomeAdapters.ToGenerationError(
                new VideoJobError(code, string.Empty, Retryable: false)).Code);

        internal static int MapStatusFromCode(GenerationErrorCode code) => code switch
        {
            GenerationErrorCode.InvalidRequest => 400,
            GenerationErrorCode.UnsupportedMedia => 415,
            GenerationErrorCode.DependencyUnavailable => 503,
            GenerationErrorCode.ExecutionFailed => 500,
            GenerationErrorCode.Cancelled => 200,
            GenerationErrorCode.Interrupted => 200,
            GenerationErrorCode.QuotaExceeded => 429,
            GenerationErrorCode.ContentPolicy => 422,
            _ => 500,
        };

        // ─── Result envelope helpers ─────────────────────────────────────

        private static ApiResponse Ok(object? data) =>
            new() { Success = true, Data = data, HttpStatus = 200 };

        private static ApiResponse FailWithError(VideoJobError err) =>
            FailWithError(VideoProviderOutcomeAdapters.ToGenerationError(err));

        private static ApiResponse FailWithError(GenerationError err) =>
            new()
            {
                Success = false,
                Data = ErrorToObj(err),
                HttpStatus = MapStatusFromCode(err.Code),
            };

        private static ApiResponse FailInvalidRequest(string message) =>
            FailWithError(new VideoJobError(
                Code: VideoErrorCode.InvalidRequest,
                Message: message,
                Retryable: false));

        private static ApiResponse FailExecutionFailed(string message) =>
            FailWithError(new VideoJobError(
                Code: VideoErrorCode.ExecutionFailed,
                Message: message,
                Retryable: false));

        private static VideoJobError BadField(string field, string message) =>
            new(Code: VideoErrorCode.InvalidRequest,
                Message: message,
                Retryable: false,
                Field: field);

        // ─── JSON arg helpers ────────────────────────────────────────────

        private static Dictionary<string, JsonElement> ParseObjectBody(string? body)
        {
            if (string.IsNullOrWhiteSpace(body))
                return new Dictionary<string, JsonElement>();

            try
            {
                using var doc = JsonDocument.Parse(body!);
                if (doc.RootElement.ValueKind != JsonValueKind.Object)
                    throw new ArgumentException(
                        "Video request body must be a JSON object.");

                var dict = new Dictionary<string, JsonElement>();
                foreach (var prop in doc.RootElement.EnumerateObject())
                    dict[prop.Name] = prop.Value.Clone();
                return dict;
            }
            catch (JsonException ex)
            {
                throw new ArgumentException($"Invalid JSON body: {ex.Message}");
            }
        }

        private static string? GetStringArg(
            Dictionary<string, JsonElement> args, string key)
        {
            if (!args.TryGetValue(key, out var el)) return null;
            return el.ValueKind == JsonValueKind.String ? el.GetString() : null;
        }

        private static bool TryGetInt(
            Dictionary<string, JsonElement> args, string key, out int value)
        {
            value = 0;
            if (!args.TryGetValue(key, out var el)) return false;
            if (el.ValueKind != JsonValueKind.Number) return false;
            return el.TryGetInt32(out value);
        }

        /// <summary>
        /// Strict optional-positive-int reader. Distinguishes:
        /// <list type="bullet">
        ///   <item>absent (key not in the JSON object) → <c>(null, null)</c>;</item>
        ///   <item>integer ≥ 1 → <c>(value, null)</c>;</item>
        ///   <item>any other shape — explicit JSON <c>null</c>, string
        ///         <c>"50"</c>, <c>0</c>, <c>-1</c>, fractional, boolean —
        ///         <c>(null, InvalidRequest)</c> with <c>field = key</c>.</item>
        /// </list>
        /// PR-V3 Codex review: only <i>absent</i> falls through to the
        /// caller's default; <i>explicit null</i> is a present-but-empty
        /// value and must be rejected like any other wrong type. The v3
        /// contract is "positive integer or absent"; null is neither.
        /// </summary>
        private static (int? Value, VideoJobError? Error) TryGetOptionalPositiveInt(
            Dictionary<string, JsonElement> args, string key)
        {
            if (!args.TryGetValue(key, out var el)) return (null, null);
            if (el.ValueKind != JsonValueKind.Number)
                return (null, BadField(key,
                    $"'{key}' must be a positive integer when present " +
                    $"(got {el.ValueKind})."));
            if (!el.TryGetInt32(out var value))
                return (null, BadField(key,
                    $"'{key}' must fit in a 32-bit signed integer."));
            if (value < 1)
                return (null, BadField(key,
                    $"'{key}' must be ≥ 1 (got {value})."));
            return (value, null);
        }

        /// <summary>
        /// Read an optional JSON object field. Returns
        /// <c>(null, null)</c> when the key is absent or explicitly
        /// null (legitimate "no value" shapes), <c>(null, error)</c>
        /// when the key is present with a non-object value (caller
        /// sent malformed payload — must surface as <c>InvalidRequest</c>
        /// rather than be silently treated as absent). Codex review of
        /// step 4: silent wrong-type skipping changes request meaning
        /// invisibly.
        /// </summary>
        private static (JsonElement? Element, VideoJobError? Error) GetOptionalObject(
            Dictionary<string, JsonElement> args, string key)
        {
            if (!args.TryGetValue(key, out var el)) return (null, null);
            if (el.ValueKind == JsonValueKind.Null) return (null, null);
            if (el.ValueKind != JsonValueKind.Object)
                return (null, BadField(key,
                    $"'{key}' must be a JSON object when present " +
                    $"(got {el.ValueKind})."));
            return (el, null);
        }

        /// <summary>
        /// Read an optional JSON array field. Same absent-vs-wrong-type
        /// semantics as <see cref="GetOptionalObject"/>.
        /// </summary>
        private static (JsonElement? Element, VideoJobError? Error) GetOptionalArray(
            Dictionary<string, JsonElement> args, string key)
        {
            if (!args.TryGetValue(key, out var el)) return (null, null);
            if (el.ValueKind == JsonValueKind.Null) return (null, null);
            if (el.ValueKind != JsonValueKind.Array)
                return (null, BadField(key,
                    $"'{key}' must be a JSON array when present " +
                    $"(got {el.ValueKind})."));
            return (el, null);
        }
    }
}
