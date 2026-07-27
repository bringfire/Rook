using System;
using System.Collections.Generic;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading.Tasks;

namespace Rook.Handlers
{
    public sealed class BimCreationGuidProbeAsyncStart
    {
        internal BimCreationGuidProbeAsyncStart(string operationId, string state, string? failureCode)
        {
            OperationId = operationId;
            State = state;
            FailureCode = failureCode;
        }

        public string OperationId { get; }
        public string State { get; }
        public string? FailureCode { get; }
    }

    public sealed class BimCreationGuidProbeAsyncPoll
    {
        internal BimCreationGuidProbeAsyncPoll(string operationId, string state, bool? success,
            int? httpStatus, string? dataJson, string? failureCode, string? exceptionType,
            int? hresult)
        {
            OperationId = operationId;
            State = state;
            Success = success;
            HttpStatus = httpStatus;
            DataJson = dataJson;
            FailureCode = failureCode;
            ExceptionType = exceptionType;
            HResult = hresult;
        }

        public string OperationId { get; }
        public string State { get; }
        public bool? Success { get; }
        public int? HttpStatus { get; }
        public string? DataJson { get; }
        public string? FailureCode { get; }
        public string? ExceptionType { get; }
        public int? HResult { get; }
    }

    public static class BimCreationGuidProbeAsyncFacade
    {
        private static readonly BimCreationGuidProbeAsyncCoordinator Coordinator =
            new BimCreationGuidProbeAsyncCoordinator(
                body => new BimHandler().Dispatch(body),
                work => Task.Run(work),
                () => DateTime.UtcNow);

        public static BimCreationGuidProbeAsyncStart Start(string action, string? caseId)
        {
            return Coordinator.Start(action, caseId);
        }

        public static BimCreationGuidProbeAsyncPoll Poll(string operationId)
        {
            return Coordinator.Poll(operationId);
        }
    }

    internal sealed class BimCreationGuidProbeAsyncCoordinator
    {
        private const int MaximumDataBytes = 256 * 1024;
        private const int MaximumExceptionTypeLength = 256;
        private static readonly TimeSpan Watchdog = TimeSpan.FromSeconds(10);
        private static readonly HashSet<string> Actions = new HashSet<string>(StringComparer.Ordinal)
        {
            "begin", "capture", "complete", "abort",
        };
        private static readonly HashSet<string> Cases = new HashSet<string>(StringComparer.Ordinal)
        {
            "saved_project_initial", "saved_project_reopen", "file_central", "file_local",
            "file_local_reopen", "copied_central", "detached", "saved_family",
            "unsaved_project", "unsaved_family", "replacement_same_path",
        };
        private static readonly HashSet<string> AllowedErrorCodes =
            new HashSet<string>(StringComparer.Ordinal)
            {
                "capability_unavailable", "invalid_scope", "no_active_document",
                "not_rhino_inside", "internal_error",
            };

        private readonly object sync = new object();
        private readonly Func<string, ApiResponse> dispatch;
        private readonly Action<Action> launch;
        private readonly Func<DateTime> utcNow;
        private OperationSlot? slot;

        internal BimCreationGuidProbeAsyncCoordinator(Func<string, ApiResponse> dispatch,
            Action<Action> launch, Func<DateTime> utcNow)
        {
            this.dispatch = dispatch ?? throw new ArgumentNullException(nameof(dispatch));
            this.launch = launch ?? throw new ArgumentNullException(nameof(launch));
            this.utcNow = utcNow ?? throw new ArgumentNullException(nameof(utcNow));
        }

        internal BimCreationGuidProbeAsyncStart Start(string action, string? caseId)
        {
            if (!TryBuildRequest(action, caseId, out var requestBody))
            {
                return new BimCreationGuidProbeAsyncStart(
                    string.Empty, "invalid", "probe_request_invalid");
            }

            string operationId;
            lock (sync)
            {
                if (slot != null)
                {
                    return new BimCreationGuidProbeAsyncStart(
                        string.Empty, "busy", "probe_busy");
                }

                operationId = Guid.NewGuid().ToString("D");
                slot = new OperationSlot(operationId, utcNow());
            }

            try
            {
                launch(() => RunWorker(operationId, requestBody));
            }
            catch (Exception ex) when (!IsProcessFatal(ex))
            {
                Publish(operationId, WorkerFailure(operationId, ex.GetType(), ex.HResult));
            }

            return new BimCreationGuidProbeAsyncStart(operationId, "accepted", null);
        }

        internal BimCreationGuidProbeAsyncPoll Poll(string operationId)
        {
            if (string.IsNullOrWhiteSpace(operationId))
            {
                return NotFound(operationId ?? string.Empty);
            }

            lock (sync)
            {
                if (slot == null || !string.Equals(slot.OperationId, operationId, StringComparison.Ordinal))
                {
                    return NotFound(operationId);
                }

                if (slot.TimedOut)
                {
                    return TimedOut(operationId);
                }

                if (slot.Terminal != null)
                {
                    var terminal = slot.Terminal;
                    slot = null;
                    return terminal;
                }

                if (utcNow() - slot.StartedUtc >= Watchdog)
                {
                    slot.TimedOut = true;
                    return TimedOut(operationId);
                }

                return new BimCreationGuidProbeAsyncPoll(operationId, "pending",
                    null, null, null, null, null, null);
            }
        }

        private void RunWorker(string operationId, string requestBody)
        {
            try
            {
                var response = dispatch(requestBody);
                Publish(operationId, Project(operationId, response));
            }
            catch (Exception ex) when (!IsProcessFatal(ex))
            {
                Publish(operationId, WorkerFailure(operationId, ex.GetType(), ex.HResult));
            }
        }

        private void Publish(string operationId, BimCreationGuidProbeAsyncPoll terminal)
        {
            lock (sync)
            {
                if (slot == null || slot.TimedOut ||
                    !string.Equals(slot.OperationId, operationId, StringComparison.Ordinal))
                {
                    return;
                }

                if (utcNow() - slot.StartedUtc >= Watchdog)
                {
                    slot.TimedOut = true;
                    return;
                }

                slot.Terminal = terminal;
            }
        }

        private static BimCreationGuidProbeAsyncPoll Project(string operationId, ApiResponse response)
        {
            if (response == null)
            {
                return ShapeInvalid(operationId, null);
            }

            JsonNode data;
            if (response.Success)
            {
                if (!(response.Data is JsonNode safeData))
                {
                    return ShapeInvalid(operationId, response.HttpStatus);
                }

                data = safeData.DeepClone();
            }
            else
            {
                var errorCode = ExtractErrorCode(response.Data);
                data = new JsonObject { ["errorCode"] = errorCode };
            }

            var json = data.ToJsonString();
            if (Encoding.UTF8.GetByteCount(json) > MaximumDataBytes)
            {
                return new BimCreationGuidProbeAsyncPoll(operationId, "completed", false,
                    response.HttpStatus, null, "probe_response_too_large", null, null);
            }

            return new BimCreationGuidProbeAsyncPoll(operationId, "completed",
                response.Success, response.HttpStatus, json, null, null, null);
        }

        private static string ExtractErrorCode(object? data)
        {
            string? candidate = null;
            if (data is JsonObject objectData &&
                objectData.TryGetPropertyValue("errorCode", out var value) &&
                value is JsonValue jsonValue && jsonValue.TryGetValue<string>(out var stringValue))
            {
                candidate = stringValue;
            }

            return candidate != null && AllowedErrorCodes.Contains(candidate)
                ? candidate : "internal_error";
        }

        private static bool TryBuildRequest(string action, string? caseId, out string requestBody)
        {
            requestBody = string.Empty;
            if (action == null || !Actions.Contains(action))
            {
                return false;
            }

            if (string.Equals(action, "capture", StringComparison.Ordinal))
            {
                if (caseId == null || !Cases.Contains(caseId))
                {
                    return false;
                }
            }
            else if (caseId != null)
            {
                return false;
            }

            requestBody = new JsonObject
            {
                ["op"] = "creation_guid_probe",
                ["action"] = action,
                ["caseId"] = caseId,
            }.ToJsonString();
            return true;
        }

        private static BimCreationGuidProbeAsyncPoll ShapeInvalid(string operationId, int? status)
        {
            return new BimCreationGuidProbeAsyncPoll(operationId, "completed", false,
                status, null, "probe_response_shape_invalid", null, null);
        }

        private static BimCreationGuidProbeAsyncPoll WorkerFailure(
            string operationId, Type exceptionType, int hresult)
        {
            var value = exceptionType.FullName ?? exceptionType.Name;
            if (value.Length > MaximumExceptionTypeLength)
            {
                value = value.Substring(0, MaximumExceptionTypeLength);
            }

            return new BimCreationGuidProbeAsyncPoll(operationId, "worker_failed", false,
                null, null, "probe_worker_failed", value, hresult);
        }

        private static BimCreationGuidProbeAsyncPoll TimedOut(string operationId)
        {
            return new BimCreationGuidProbeAsyncPoll(operationId, "timed_out", false,
                null, null, "probe_worker_timed_out", null, null);
        }

        private static BimCreationGuidProbeAsyncPoll NotFound(string operationId)
        {
            return new BimCreationGuidProbeAsyncPoll(operationId, "not_found", null,
                null, null, "probe_poll_not_found", null, null);
        }

        private static bool IsProcessFatal(Exception exception)
        {
            return exception is OutOfMemoryException || exception is StackOverflowException ||
                exception is AccessViolationException || exception is AppDomainUnloadedException ||
                exception is BadImageFormatException || exception is CannotUnloadAppDomainException ||
                exception is System.Threading.ThreadAbortException;
        }

        private sealed class OperationSlot
        {
            internal OperationSlot(string operationId, DateTime startedUtc)
            {
                OperationId = operationId;
                StartedUtc = startedUtc;
            }

            internal string OperationId { get; }
            internal DateTime StartedUtc { get; }
            internal bool TimedOut { get; set; }
            internal BimCreationGuidProbeAsyncPoll? Terminal { get; set; }
        }
    }
}
