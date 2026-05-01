using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rhino;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Jobs;

namespace Rook.Handlers
{
    /// <summary>
    /// Managed bridge handler for asynchronous image generation jobs.
    /// Routing remains bridge-only for Task 6; native HTTP route wiring is
    /// handled separately at the boundary scan.
    /// </summary>
    public class ImageJobOpHandler
    {
        public const string OpStart = "image_generate_start";
        public const string OpStatus = "image_job_status";
        public const string OpCancel = "image_job_cancel";
        public const string OpResult = "image_job_result";
        public const string OpList = "image_jobs";
        public const int DefaultListLimit = 50;

        private readonly IImageJobManager _manager;
        private readonly VisionHandler _visionHandler;

        public ImageJobOpHandler(
            IImageJobManager manager,
            VisionHandler visionHandler)
        {
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
                    OpStatus or OpResult or OpList => FailInvalidRequest(
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
            var workResult = _visionHandler.BuildImageGenerationWorkItem(args);
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
                return Fail(result.Error);

            return Ok(new Dictionary<string, object?>
            {
                ["job_id"] = result.JobId!.Value.ToString("D"),
                ["state"] = StateToString(result.State),
            });
        }

        private async Task<ApiResponse> CancelAsync(
            Dictionary<string, JsonElement> args,
            CancellationToken ct)
        {
            if (!TryParseJobId(args, out var jobId, out var parseErr))
                return Fail(parseErr!);

            var result = await _manager.CancelAsync(jobId, ct)
                .ConfigureAwait(false);

            if (result.Error is not null)
                return Fail(result.Error);

            return Ok(new Dictionary<string, object?>
            {
                ["job_id"] = jobId.ToString("D"),
                ["state"] = StateToString(result.State),
            });
        }

        private ApiResponse Status(Dictionary<string, JsonElement> args)
        {
            if (!TryParseJobId(args, out var jobId, out var parseErr))
                return Fail(parseErr!);

            var result = _manager.GetStatusAsync(jobId, default)
                .GetAwaiter().GetResult();

            if (result.Error is { Code: GenerationErrorCode.InvalidRequest })
                return Fail(result.Error);

            return Ok(new Dictionary<string, object?>
            {
                ["job_id"] = jobId.ToString("D"),
                ["state"] = StateToString(result.State),
                ["progress"] = result.Progress is null
                    ? null
                    : ProgressToObj(result.Progress),
                ["result_artifact_id"] = result.ResultArtifactId?.ToString("D"),
                ["error"] = result.Error is null ? null : ErrorToObj(result.Error),
            });
        }

        private ApiResponse Result(Dictionary<string, JsonElement> args)
        {
            if (!TryParseJobId(args, out var jobId, out var parseErr))
                return Fail(parseErr!);

            var result = _manager.FetchResultAsync(jobId, default)
                .GetAwaiter().GetResult();

            if (result.Error is not null)
                return Fail(result.Error);

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

            return Ok(new Dictionary<string, object?>
            {
                ["job_id"] = jobId.ToString("D"),
                ["state"] = StateToString(result.State),
                ["result_artifact_id"] =
                    result.ResultArtifactId!.Value.ToString("D"),
                ["files"] = files,
            });
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
                jobs.Add(JobToObj(job));

            return Ok(new Dictionary<string, object?>
            {
                ["jobs"] = jobs,
                ["applied_limit"] = result.AppliedLimit,
            });
        }

        private static Dictionary<string, object?> JobToObj(
            ImageJobRecord job) =>
            new()
            {
                ["job_id"] = job.JobId.ToString("D"),
                ["state"] = StateToString(job.State),
                ["model"] = job.Model,
                ["provider"] = job.Provider,
                ["updated_at"] = job.UpdatedAt.ToString(
                    "o",
                    CultureInfo.InvariantCulture),
                ["result_artifact_id"] = job.ResultArtifactId?.ToString("D"),
                ["error"] = job.Error is null ? null : ErrorToObj(job.Error),
            };

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
                ["percent_complete"] = progress.PercentComplete,
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
            GenerationError error) =>
            new()
            {
                ["code"] = ErrorCodeToString(error.Code),
                ["message"] = error.Message,
                ["retryable"] = error.Retryable,
                ["field"] = error.Field,
            };

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

        private static ApiResponse Fail(GenerationError error) =>
            new()
            {
                Success = false,
                Data = ErrorToObj(error),
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
