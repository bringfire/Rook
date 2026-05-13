using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using System.Threading;
using Rhino;
using Rook.Services.Vision.MediaImport;

namespace Rook.Handlers
{
    public interface IMediaImportPicker
    {
        IReadOnlyList<string> PickFiles();
    }

    public sealed class EtoMediaImportPicker : IMediaImportPicker
    {
        public IReadOnlyList<string> PickFiles()
        {
            var dlg = new Eto.Forms.OpenFileDialog
            {
                MultiSelect = true,
                Title = "Add Media to Gallery",
            };
            dlg.Filters.Add(new Eto.Forms.FileFilter(
                "Media",
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
                ".mp4",
                ".mov",
                ".webm"));

            var result = dlg.ShowDialog(null);
            if (result != Eto.Forms.DialogResult.Ok)
                return Array.Empty<string>();

            return dlg.Filenames?.ToArray() ?? Array.Empty<string>();
        }
    }

    public sealed class MediaImportOpHandler
    {
        public const string OpStart = "start_media_import";
        public const string OpStatus = "get_media_import_job";
        public const string OpList = "list_media_import_jobs";

        private readonly MediaImportJobManager _manager;
        private readonly IMediaImportPicker _picker;

        public MediaImportOpHandler(
            MediaImportJobManager manager,
            IMediaImportPicker picker)
        {
            _manager = manager ?? throw new ArgumentNullException(nameof(manager));
            _picker = picker ?? throw new ArgumentNullException(nameof(picker));
        }

        public ApiResponse DispatchUi(string? body)
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
                    "Media import request missing required 'op' discriminator.");

            try
            {
                return op switch
                {
                    OpStart => Start(),
                    OpStatus or OpList => FailInvalidRequest(
                        $"op '{op}' must be routed through the off-UI dispatcher, not the UI dispatcher."),
                    _ => FailInvalidRequest($"Unknown media import op '{op}'."),
                };
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine(
                    $"Rook Media Import: unhandled error in UI op '{op}': {ex.GetType().Name}: {ex.Message}");
                return FailExecutionFailed(
                    $"Media import op '{op}' failed unexpectedly.");
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
                    "Media import request missing required 'op' discriminator.");

            try
            {
                return op switch
                {
                    OpStatus => Status(args),
                    OpList => List(),
                    OpStart => FailInvalidRequest(
                        $"op '{op}' must be routed through the UI dispatcher, not the off-UI dispatcher."),
                    _ => FailInvalidRequest($"Unknown media import op '{op}'."),
                };
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine(
                    $"Rook Media Import: unhandled error in off-UI op '{op}': {ex.GetType().Name}: {ex.Message}");
                return FailExecutionFailed(
                    $"Media import op '{op}' failed unexpectedly.");
            }
        }

        private ApiResponse Start()
        {
            var paths = _picker.PickFiles();
            var result = _manager.StartAsync(paths, CancellationToken.None)
                .GetAwaiter().GetResult();

            if (!result.Created)
            {
                if (result.FailureCode == MediaImportStartFailureCode.EmptySelection)
                {
                    return Ok(new Dictionary<string, object?>
                    {
                        ["created"] = false,
                        ["reason"] = "empty_selection",
                        ["message"] = result.Message,
                    });
                }

                return FailStart(result.FailureCode, result.Message);
            }

            return Ok(StartResultToObj(result.Job!));
        }

        private ApiResponse Status(Dictionary<string, JsonElement> args)
        {
            if (!TryParseJobId(args, out var jobId, out var parseErr))
                return Fail(parseErr!);

            var job = _manager.GetJob(jobId);
            if (job is null)
                return Fail(BadRequest("job_id", "Unknown media import job."));

            return Ok(JobToObj(job));
        }

        private ApiResponse List()
        {
            var result = _manager.ListJobs();
            var jobs = new List<Dictionary<string, object?>>(result.Jobs.Count);
            foreach (var job in result.Jobs)
                jobs.Add(JobToObj(job));

            return Ok(new Dictionary<string, object?>
            {
                ["jobs"] = jobs,
            });
        }

        private static Dictionary<string, object?> StartResultToObj(
            MediaImportJobSnapshot job)
        {
            var data = JobToObj(job);
            data["created"] = true;
            return data;
        }

        private static Dictionary<string, object?> JobToObj(
            MediaImportJobSnapshot job)
        {
            var files = new List<Dictionary<string, object?>>(job.Items.Count);
            foreach (var item in job.Items)
                files.Add(ItemToObj(item));

            return new Dictionary<string, object?>
            {
                ["job_id"] = job.JobId.ToString("D"),
                ["state"] = JobStateToString(job.State),
                ["created_at"] = job.CreatedAt.ToString(
                    "o",
                    CultureInfo.InvariantCulture),
                ["updated_at"] = job.UpdatedAt.ToString(
                    "o",
                    CultureInfo.InvariantCulture),
                ["files"] = files,
            };
        }

        private static Dictionary<string, object?> ItemToObj(
            MediaImportItemSnapshot item)
        {
            var row = new Dictionary<string, object?>
            {
                ["import_item_id"] = item.ImportItemId.ToString("D"),
                ["basename"] = item.Basename,
                ["status"] = ItemStateToString(item.State),
            };

            if (item.ArtifactId is Guid artifactId)
                row["artifact_id"] = artifactId.ToString("D");
            if (!string.IsNullOrEmpty(item.ArtifactKind))
                row["artifact_kind"] = item.ArtifactKind;
            if (item.FailureCode is MediaImportFailureCode failureCode)
                row["failure_code"] = FailureCodeToString(failureCode);
            if (!string.IsNullOrEmpty(item.Message))
                row["message"] = item.Message;

            return row;
        }

        private static string JobStateToString(MediaImportJobState state) =>
            state switch
            {
                MediaImportJobState.Queued => "queued",
                MediaImportJobState.Running => "running",
                MediaImportJobState.Complete => "complete",
                _ => state.ToString().ToLowerInvariant(),
            };

        private static string ItemStateToString(MediaImportItemState state) =>
            state switch
            {
                MediaImportItemState.Queued => "queued",
                MediaImportItemState.Copying => "copying",
                MediaImportItemState.Probing => "probing",
                MediaImportItemState.ExtractingSidecars => "extracting_sidecars",
                MediaImportItemState.Publishing => "publishing",
                MediaImportItemState.Imported => "imported",
                MediaImportItemState.Failed => "failed",
                _ => state.ToString().ToLowerInvariant(),
            };

        private static string FailureCodeToString(MediaImportFailureCode code) =>
            code switch
            {
                MediaImportFailureCode.UnsupportedMediaType => "unsupported_media_type",
                MediaImportFailureCode.FileNotFound => "file_not_found",
                MediaImportFailureCode.NotRegularFile => "not_regular_file",
                MediaImportFailureCode.FileInaccessible => "file_inaccessible",
                MediaImportFailureCode.FileTooLarge => "file_too_large",
                MediaImportFailureCode.DecodeFailed => "decode_failed",
                MediaImportFailureCode.VideoProbeFailed => "video_probe_failed",
                MediaImportFailureCode.SidecarExtractionFailed => "sidecar_extraction_failed",
                MediaImportFailureCode.CopyFailed => "copy_failed",
                MediaImportFailureCode.PublishFailed => "publish_failed",
                _ => code.ToString().ToLowerInvariant(),
            };

        private static string StartFailureCodeToString(
            MediaImportStartFailureCode code) =>
            code switch
            {
                MediaImportStartFailureCode.EmptySelection => "empty_selection",
                MediaImportStartFailureCode.TooManyFiles => "too_many_files",
                _ => code.ToString().ToLowerInvariant(),
            };

        private static bool TryParseJobId(
            Dictionary<string, JsonElement> args,
            out Guid jobId,
            out Dictionary<string, object?>? error)
        {
            jobId = default;
            error = null;

            var raw = GetStringArg(args, "job_id");
            if (string.IsNullOrWhiteSpace(raw)
                || !Guid.TryParseExact(raw, "D", out jobId)
                || jobId == Guid.Empty)
            {
                error = BadRequest(
                    "job_id",
                    "'job_id' must be a non-empty GUID in 'D' format.");
                return false;
            }

            return true;
        }

        private static ApiResponse Ok(object? data) =>
            new() { Success = true, Data = data, HttpStatus = 200 };

        private static ApiResponse Fail(Dictionary<string, object?> error) =>
            new() { Success = false, Data = error, HttpStatus = 400 };

        private static ApiResponse FailStart(
            MediaImportStartFailureCode? code,
            string? message)
        {
            var safeCode = code ?? MediaImportStartFailureCode.TooManyFiles;
            return Fail(new Dictionary<string, object?>
            {
                ["code"] = StartFailureCodeToString(safeCode),
                ["message"] = message ?? "Media import could not be started.",
                ["retryable"] = false,
            });
        }

        private static ApiResponse FailInvalidRequest(string message) =>
            Fail(BadRequest(null, message));

        private static ApiResponse FailExecutionFailed(string message) =>
            new()
            {
                Success = false,
                Data = new Dictionary<string, object?>
                {
                    ["code"] = "execution_failed",
                    ["message"] = message,
                    ["retryable"] = false,
                },
                HttpStatus = 500,
            };

        private static Dictionary<string, object?> BadRequest(
            string? field,
            string message) =>
            new()
            {
                ["code"] = "invalid_request",
                ["message"] = message,
                ["retryable"] = false,
                ["field"] = field,
            };

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
                        "Media import request body must be a JSON object.");
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
    }
}
