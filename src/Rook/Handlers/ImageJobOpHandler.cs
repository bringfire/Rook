using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Video.Framing;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rhino;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Jobs;
using Rook.Services.Vision.Image;

namespace Rook.Handlers
{
    /// <summary>
    /// Shared managed handler for asynchronous image jobs and configured estimates.
    /// Estimate/status/result/history run off the UI thread; submit/cancel are asynchronous.
    /// </summary>
    public class ImageJobOpHandler
    {
        public const string OpEstimate = "image_estimate";
        public const string OpStart = "image_generate_start";
        public const string OpStatus = "image_job_status";
        public const string OpCancel = "image_job_cancel";
        public const string OpResult = "image_job_result";
        public const string OpList = "image_jobs";
        public const int DefaultListLimit = 50;

        private readonly VideoPreparationResources _configuredResources;
        private readonly IImageJobManager _manager;
        private readonly VisionHandler _visionHandler;

        public ImageJobOpHandler(
            IImageJobManager manager,
            VisionHandler visionHandler) : this(manager, visionHandler, VideoPreparationResources.Shared) { }

        internal ImageJobOpHandler(IImageJobManager manager, VisionHandler visionHandler, VideoPreparationResources configuredResources)
        {
            _configuredResources = configuredResources;
            _manager = manager ?? throw new ArgumentNullException(nameof(manager));
            _visionHandler = visionHandler
                ?? throw new ArgumentNullException(nameof(visionHandler));
        }

        public async Task<ApiResponse> DispatchAsync(
            string? body,
            CancellationToken cancellationToken = default)
        {
            Dictionary<string, JsonElement> args;
            try { args = ParseObjectBody(body); }
            catch (ArgumentException ex)
            {
                return FailInvalidRequest(ex.Message);
            }

            var op = GetStringArg(args, "op");
            if (string.IsNullOrEmpty(op))
                return FailInvalidRequest(
                    "Image job request missing required 'op' discriminator.");

            try
            {
                return op switch
                {
                    OpStart => await StartAsync(args, cancellationToken)
                        .ConfigureAwait(false),
                    OpCancel => await CancelAsync(args, cancellationToken)
                        .ConfigureAwait(false),
                    OpStatus or OpResult or OpList or OpEstimate => FailInvalidRequest(
                        $"op '{op}' must be routed through the off-UI dispatcher, not the async dispatcher."),
                    _ => FailInvalidRequest($"Unknown image job op '{op}'."),
                };
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (ArgumentException ex)
            {
                return FailInvalidRequest(ex.Message);
            }
            catch (InvalidOperationException ex)
            {
                return FailInvalidRequest(ex.Message);
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine(
                    $"Rook Image Jobs: unhandled error in async op '{op}': {ex.GetType().Name}: {ex.Message}");
                return FailExecutionFailed(
                    $"Image job op '{op}' failed unexpectedly.");
            }
        }

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
                return FailInvalidRequest(
                    "Image job request missing required 'op' discriminator.");

            try
            {
                return op switch
                {
                    OpEstimate => EstimateConfigured(args),
                    OpStatus => Status(args),
                    OpResult => Result(args),
                    OpList => List(args),
                    OpStart or OpCancel => FailInvalidRequest(
                        $"op '{op}' must be routed through the async dispatcher, not the off-UI dispatcher."),
                    _ => FailInvalidRequest($"Unknown image job op '{op}'."),
                };
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine(
                    $"Rook Image Jobs: unhandled error in off-UI op '{op}': {ex.GetType().Name}: {ex.Message}");
                return FailExecutionFailed(
                    $"Image job op '{op}' failed unexpectedly.");
            }
        }

        private async Task<ApiResponse> StartAsync(
            Dictionary<string, JsonElement> args,
            CancellationToken ct)
        {
            if (IsConfigured(args)) return await StartConfiguredAsync(args, ct).ConfigureAwait(false);
            var workResult = _visionHandler.BuildImageGenerationWorkItem(
                args,
                VisionHandler.ImageGenerationWorkItemOptions.AsyncImageJob);
            if (!workResult.Success)
                return CoerceFailure(workResult.Failure!);
            var work = workResult.WorkItem!;

            var start = new ImageJobStartRequest(
                work.Request,
                work.ResolvedMedia,
                work.ParentArtifactIds,
                work.ResolvedModel);

            var result = await _manager.SubmitAsync(start, ct)
                .ConfigureAwait(false);

            if (result.Error is not null)
                return Fail(result.Error, result.Provider, result.Model, result.Routing, result.FalDispatchState);

            return Ok(WithRouting(new Dictionary<string, object?>
            {
                ["job_id"] = result.JobId!.Value.ToString("D"),
                ["state"] = StateToString(result.State),
            }, result.Provider, result.Model, result.Routing, result.FalDispatchState));
        }

        private bool IsConfigured(Dictionary<string, JsonElement> args) =>
            _visionHandler.ImageRegistry.TryResolve(GetStringArg(args, "model") ?? "", out var model) && model.Provider is IConfiguredGenerationProvider;

        private FalRequestParseResult? ParseConfigured(Dictionary<string, JsonElement> args)
        {
            var catalog = (_visionHandler.ImageRegistry as DefaultImageProviderRegistry)?.Catalog;
            return catalog == null ? null : FalConfiguredRequestParser.Parse(FalConfiguredRequestParser.ToJson(args), catalog, "image");
        }
        private static ApiResponse Unavailable() => new() { Success = false, HttpStatus = 400,
            Data = new Dictionary<string, object?> { ["code"] = "model_unavailable", ["field"] = "model", ["message"] = "Configured model is unavailable." } };
        private ApiResponse EstimateConfigured(Dictionary<string, JsonElement> args)
        {
            if (!IsConfigured(args)) return Unavailable();
            var parsed = ParseConfigured(args);
            if (parsed == null) return Unavailable();
            if (!parsed.Success) return FalConfiguredRequestParser.Failure(parsed);
            var request = parsed.Request!;
            FalMediaSnapshot snapshot;
            using (var resolved = _visionHandler.ResolveConfiguredImageMedia(request.Media.Select(m => m.Input.Source).Distinct().ToArray()))
            {
                if (!resolved.Success) return Fail(resolved.Error!);
                snapshot = FalMediaSnapshot.Capture(request, resolved.Resolved!, _configuredResources);
            }
            using (snapshot)
            {
                var quote = new FalQuoteService().Estimate(request, snapshot);
                return quote.Success ? Ok(quote.Quote!.ToJson()) : Fail(quote.Error!);
            }
        }
        private async Task<ApiResponse> StartConfiguredAsync(Dictionary<string, JsonElement> args, CancellationToken ct)
        {
            var parsed = ParseConfigured(args);
            if (parsed == null) return Unavailable();
            if (!parsed.Success) return FalConfiguredRequestParser.Failure(parsed);
            if (FalSubmitConfirmation.TryParse(FalConfiguredRequestParser.ToJson(args), out var confirmation) is { } error) return Fail(error);
            var normalized = parsed.Request!;
            var refs = normalized.Media.Select(m => m.Input.Source).Distinct().ToArray();
            FalMediaSnapshot snapshot;
            using (var resolved = _visionHandler.ResolveConfiguredImageMedia(refs))
            {
                if (!resolved.Success) return Fail(resolved.Error!);
                snapshot = FalMediaSnapshot.Capture(normalized, resolved.Resolved!, _configuredResources);
            }
            if (snapshot.ValidationError is { } invalid) { snapshot.Dispose(); return Fail(invalid); }
            var fields = normalized.EffectiveRequestFields;
            var shell = new ImageGenerationRequest(normalized.Binding.ModelId,
                FalConfiguredRequestParser.String(fields["prompt"]) ?? "", FalConfiguredRequestParser.String(fields["resolution"]) ?? "",
                FalConfiguredRequestParser.String(fields["aspect_ratio"]) ?? "", 1, refs, new FalModelOptions(parsed.Input!, normalized.Binding.OperationId));
            _visionHandler.ImageRegistry.TryResolve(normalized.Binding.ModelId, out var model);
            // SubmitAsync takes ownership, including rejection. No handler-scoped using may end a running job's media lifetime.
            var result = await _manager.SubmitAsync(new ImageJobStartRequest(shell, new Dictionary<MediaRef, ResolvedMedia>(),
                refs.Select(r => r.ArtifactId!.Value).Distinct().ToArray(), model, configuredRequest: normalized, configuredMedia: snapshot, configuredConfirmation: confirmation), ct).ConfigureAwait(false);
            if (result.Error != null) return Fail(result.Error, result.Provider, result.Model, result.Routing, result.FalDispatchState);
            return Ok(new Dictionary<string, object?> { ["job_id"] = result.JobId!.Value.ToString("D"), ["state"] = StateToString(result.State) });
        }

        private async Task<ApiResponse> CancelAsync(
            Dictionary<string, JsonElement> args,
            CancellationToken ct)
        {
            if (!TryParseJobId(args, out var jobId, out var parseErr))
                return Fail(parseErr!);

            var result = await _manager.CancelAsync(jobId, ct)
                .ConfigureAwait(false);

            var response = result.Error != null ? Fail(result.Error, result.Provider, result.Model, result.Routing, result.FalDispatchState)
                : Ok(WithRouting(new Dictionary<string, object?> { ["job_id"] = jobId.ToString("D"), ["state"] = StateToString(result.State) }, result.Provider, result.Model, result.Routing, result.FalDispatchState));
            var data = (Dictionary<string, object?>)response.Data!;
            if (result.ConfiguredCancellation != null) { data["job_id"] = jobId.ToString("D"); data["state"] = StateToString(result.State); }
            FalConfiguredRequestParser.AddCancellation(data, result.ConfiguredCancellation);
            return response;
        }

        private ApiResponse Status(Dictionary<string, JsonElement> args)
        {
            if (!TryParseJobId(args, out var jobId, out var parseErr))
                return Fail(parseErr!);

            var result = _manager.GetStatusAsync(jobId, default)
                .GetAwaiter().GetResult();

            if (result.Error is { Code: GenerationErrorCode.InvalidRequest })
                return Fail(result.Error, result.Provider, result.Model, result.Routing, result.FalDispatchState);

            return Ok(WithRouting(new Dictionary<string, object?>
            {
                ["job_id"] = jobId.ToString("D"),
                ["state"] = StateToString(result.State),
                ["progress"] = result.Progress is null
                    ? null
                    : ProgressToObj(result.Progress),
                ["result_artifact_id"] = result.ResultArtifactId?.ToString("D"),
                ["error"] = result.Error is null ? null : ErrorToObj(result.Error, result.Provider, result.Model, result.Routing, result.FalDispatchState),
            }, result.Provider, result.Model, result.Routing, result.FalDispatchState));
        }

        private ApiResponse Result(Dictionary<string, JsonElement> args)
        {
            if (!TryParseJobId(args, out var jobId, out var parseErr))
                return Fail(parseErr!);

            var result = _manager.FetchResultAsync(jobId, default)
                .GetAwaiter().GetResult();

            if (result.Error is not null)
                return Fail(result.Error, result.Provider, result.Model, result.Routing, result.FalDispatchState);

            var files = new List<Dictionary<string, object?>>(
                result.Files!.Count);
            foreach (var file in result.Files!)
            {
                files.Add(new Dictionary<string, object?>
                {
                    ["role"] = file.Role,
                    ["path"] = file.Path,
                });
            }

            return Ok(WithRouting(new Dictionary<string, object?>
            {
                ["job_id"] = jobId.ToString("D"),
                ["state"] = StateToString(result.State),
                ["result_artifact_id"] =
                    result.ResultArtifactId!.Value.ToString("D"),
                ["files"] = files,
            }, result.Provider, result.Model, result.Routing, result.FalDispatchState));
        }

        private ApiResponse List(Dictionary<string, JsonElement> args)
        {
            var limit = TryGetPositiveInt(args, "limit")
                ?? DefaultListLimit;

            var result = _manager.ListJobsAsync(limit, default)
                .GetAwaiter().GetResult();

            var jobs = new List<Dictionary<string, object?>>(
                result.Jobs.Count);
            foreach (var job in result.Jobs)
            {
                var row = JobToObj(job);
                if (job.ConfiguredFalExecution is { } read)
                {
                    row[FalExecutionSnapshot.ExtensionKey] = read.PublicJson;
                    var summary = read.Snapshot?.Request.EffectiveRequestFields;
                    if (summary != null) { summary["model"] = job.Model; summary["operation"] = read.Snapshot!.Binding.OperationId; }
                    row["request_summary"] = summary;
                }
                jobs.Add(row);
            }

            return Ok(new Dictionary<string, object?>
            {
                ["jobs"] = jobs,
                ["applied_limit"] = result.AppliedLimit,
            });
        }

        private static Dictionary<string, object?> JobToObj(
            ImageJobRecord job) =>
            WithRouting(new Dictionary<string, object?>()
            {
                ["job_id"] = job.JobId.ToString("D"),
                ["state"] = StateToString(job.State),
                ["model"] = job.Model,
                ["provider_name"] = job.Provider,
                ["updated_at"] = job.UpdatedAt.ToString(
                    "o",
                    CultureInfo.InvariantCulture),
                ["result_artifact_id"] = job.ResultArtifactId?.ToString("D"),
                ["error"] = job.Error is null ? null : ErrorToObj(job.Error, job.Provider, job.Model, job.Routing, job.FalDispatchState),
            }, job.Provider, job.Model, job.Routing, job.FalDispatchState);

        private static Dictionary<string, object?> WithRouting(Dictionary<string, object?> data,
            string? provider, string? model, ImageRoutingContext? routing, ImageFalDispatchState? dispatch)
        {
            ImageFailureProjection.AddRouting(data, provider, model, routing, dispatch);
            return data;
        }

        private static bool TryParseJobId(
            Dictionary<string, JsonElement> args,
            out Guid jobId,
            out GenerationError? error)
        {
            jobId = default;
            error = null;

            var raw = GetStringArg(args, "job_id");
            if (string.IsNullOrWhiteSpace(raw)
                || !Guid.TryParseExact(raw, "D", out jobId)
                || jobId == Guid.Empty)
            {
                error = BadField(
                    "job_id",
                    "'job_id' must be a non-empty GUID in 'D' format.");
                return false;
            }

            return true;
        }

        private static Dictionary<string, object?> ProgressToObj(
            GenerationProgress progress) =>
            new()
            {
                ["pct"] = progress.PercentComplete,
                ["queue_position"] = progress.QueuePosition,
                ["message"] = progress.Message,
            };

        private static string StateToString(ImageJobState state) => state switch
        {
            ImageJobState.Queued => "queued",
            ImageJobState.Submitting => "submitting",
            ImageJobState.Polling => "polling",
            ImageJobState.Materializing => "materializing",
            ImageJobState.Complete => "complete",
            ImageJobState.Error => "error",
            ImageJobState.Cancelled => "cancelled",
            ImageJobState.Interrupted => "interrupted",
            _ => state.ToString().ToLowerInvariant(),
        };

        private static string ErrorCodeToString(GenerationErrorCode code) =>
            code switch
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

        private static Dictionary<string, object?> ErrorToObj(
            GenerationError error, string? provider = null, string? model = null,
            ImageRoutingContext? routing = null, ImageFalDispatchState? dispatch = null)
        {
            if (provider != null && model != null)
            {
                var projected = ImageFailureProjection.Build(error, provider, model, routing, dispatch);
                FalConfiguredRequestParser.AddErrorDetail(projected, error); return projected;
            }
            var safe = ImageJobLedgerRecordFactory.SanitizeError(error)
                ?? error;
            var data = new Dictionary<string, object?>
            {
                ["code"] = ErrorCodeToString(safe.Code),
                ["message"] = safe.Message,
                ["retryable"] = safe.Retryable,
                ["field"] = safe.Field,
            };
            FalConfiguredRequestParser.AddErrorDetail(data, error); return data;
        }

        internal static int MapStatusFromCode(GenerationErrorCode code) =>
            code switch
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

        private static ApiResponse Ok(object? data) =>
            new() { Success = true, Data = data, HttpStatus = 200 };

        private static ApiResponse Fail(GenerationError error, string? provider = null, string? model = null,
            ImageRoutingContext? routing = null, ImageFalDispatchState? dispatch = null) =>
            new()
            {
                Success = false,
                Data = ErrorToObj(error, provider, model, routing, dispatch),
                HttpStatus = MapStatusFromCode(error.Code),
            };

        private static ApiResponse FailInvalidRequest(string message) =>
            Fail(new GenerationError(
                GenerationErrorCode.InvalidRequest,
                message,
                Retryable: false));

        private static ApiResponse FailExecutionFailed(string message) =>
            Fail(new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                message,
                Retryable: false));

        private static GenerationError BadField(
            string field,
            string message) =>
            new(
                GenerationErrorCode.InvalidRequest,
                message,
                Retryable: false,
                Field: field);

        private static ApiResponse CoerceFailure(ApiResponse failure)
        {
            if (failure.Data is GenerationError error)
                return Fail(error);

            if (failure.Data is string message)
                return FailInvalidRequest(message);

            failure.HttpStatus ??= failure.Success ? 200 : 400;
            return failure;
        }

        private static Dictionary<string, JsonElement> ParseObjectBody(
            string? body)
        {
            if (string.IsNullOrWhiteSpace(body))
                return new Dictionary<string, JsonElement>();

            try
            {
                using var doc = JsonDocument.Parse(body!);
                if (doc.RootElement.ValueKind != JsonValueKind.Object)
                {
                    throw new ArgumentException(
                        "Image job request body must be a JSON object.");
                }

                var dict = new Dictionary<string, JsonElement>();
                foreach (var prop in doc.RootElement.EnumerateObject())
                    dict[prop.Name] = prop.Value.Clone();
                return dict;
            }
            catch (JsonException ex)
            {
                throw new ArgumentException(
                    $"Invalid JSON body: {ex.Message}");
            }
        }

        private static string? GetStringArg(
            Dictionary<string, JsonElement> args,
            string key)
        {
            if (!args.TryGetValue(key, out var el)) return null;
            return el.ValueKind == JsonValueKind.String
                ? el.GetString()
                : null;
        }

        private static int? TryGetPositiveInt(
            Dictionary<string, JsonElement> args,
            string key)
        {
            if (!args.TryGetValue(key, out var el)) return null;
            if (el.ValueKind != JsonValueKind.Number) return null;
            if (!el.TryGetInt32(out var value)) return null;
            return value > 0 ? value : null;
        }
    }
}
