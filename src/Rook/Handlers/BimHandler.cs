using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using Rook.Bim;

namespace Rook.Handlers
{
    public sealed class BimHandler
    {
        private readonly Func<bool> rhinoInsideProvider;
        private readonly Func<object?, JsonNode?> wireSerializer;

        public BimHandler()
            : this(
                () => Rhino.Runtime.HostUtils.RunningAsRhinoInside,
                ToWireData)
        {
        }

        internal BimHandler(Func<bool> rhinoInsideProvider)
            : this(rhinoInsideProvider, ToWireData)
        {
        }

        internal BimHandler(
            Func<bool> rhinoInsideProvider,
            Func<object?, JsonNode?> wireSerializer)
        {
            this.rhinoInsideProvider = rhinoInsideProvider
                ?? throw new ArgumentNullException(nameof(rhinoInsideProvider));
            this.wireSerializer = wireSerializer
                ?? throw new ArgumentNullException(nameof(wireSerializer));
        }

        internal static readonly IReadOnlyList<string> ExpectedBimOps = new[]
        {
            "status",
            "active_document",
            "list_categories",
            "query_elements",
            "element_info",
            "element_parameters",
            "select_elements",
            "clear_selection",
            "export_elements",
            "export_preset",
        };

        private static readonly HashSet<string> ExpectedBimOpSet =
            new HashSet<string>(ExpectedBimOps, StringComparer.Ordinal);

        private static readonly JsonSerializerOptions JsonOptions = CreateJsonOptions();

        public ApiResponse Dispatch(string? body)
        {
            BimDiagnostics.InitializeFromEnvironment();
            var unparsedDiagnostics =
                BimDiagnostics.CreateUncorrelatedContext("unparsed");
            Dictionary<string, JsonElement> args;
            BimDiagnostics.Observe(
                unparsedDiagnostics,
                BimDiagnosticStage.HandlerDeserialize,
                BimDiagnosticOutcome.Start,
                BimDiagnosticFields.None);
            try
            {
                args = ParseObjectBody(body);
                BimDiagnostics.Observe(
                    unparsedDiagnostics,
                    BimDiagnosticStage.HandlerDeserialize,
                    BimDiagnosticOutcome.Success,
                    BimDiagnosticFields.None);
            }
            catch (ArgumentException ex)
            {
                ObserveDeserializeFailure(unparsedDiagnostics, ex);
                return Fail(
                    unparsedDiagnostics,
                    BimErrorCode.InvalidScope,
                    ex.Message,
                    400);
            }
            catch (JsonException ex)
            {
                ObserveDeserializeFailure(unparsedDiagnostics, ex);
                return Fail(
                    unparsedDiagnostics,
                    BimErrorCode.InvalidScope,
                    $"Invalid BIM request JSON: {ex.Message}",
                    400);
            }

            var op = GetStringArg(args, "op");
            if (string.IsNullOrWhiteSpace(op))
            {
                return Fail(
                    unparsedDiagnostics,
                    BimErrorCode.InvalidScope,
                    "BIM request missing required 'op' discriminator.",
                    400);
            }

            if (!ExpectedBimOpSet.Contains(op!))
            {
                return Fail(
                    unparsedDiagnostics,
                    BimErrorCode.InvalidScope,
                    $"Unknown BIM op '{op}'.",
                    400);
            }

            var diagnostics = BimDiagnostics.CreateContext(op!);
            ApiResponse? response = null;
            try
            {
                response = DispatchAcceptedRequest(diagnostics, op!, body);
                return response;
            }
            catch (JsonException ex)
            {
                if (HasSerializationFailure(diagnostics))
                {
                    response = BuildMinimalInternalError(diagnostics, ex);
                }
                else
                {
                    response = Fail(
                        diagnostics,
                        BimErrorCode.InvalidScope,
                        $"Invalid BIM request JSON: {ex.Message}",
                        400);
                }

                return response;
            }
            catch (ArgumentException ex)
            {
                response = HasSerializationFailure(diagnostics)
                    ? BuildMinimalInternalError(diagnostics, ex)
                    : Fail(
                        diagnostics,
                        BimErrorCode.InvalidScope,
                        ex.Message,
                        400);
                return response;
            }
            catch (Exception ex)
            {
                response = BuildMinimalInternalError(diagnostics, ex);
                return response;
            }
            finally
            {
                BimDiagnostics.CompleteRequest(
                    diagnostics,
                    response != null && response.Success
                        ? BimDiagnosticOutcome.Success
                        : BimDiagnosticOutcome.Failure);
            }
        }

        private ApiResponse DispatchAcceptedRequest(
            BimDiagnosticContext diagnostics,
            string op,
            string? body)
        {
            if (string.Equals(op, "status", StringComparison.Ordinal) &&
                !IsRunningAsRhinoInside())
            {
                return DispatchStandaloneStatus(diagnostics);
            }

            RookBimModuleLoader.TryActivate();
            var runtime = RookBimRuntimeRegistry.Current;
            return op switch
            {
                "status" => DispatchStatus(runtime, diagnostics),
                "active_document" => FromBimResponse(
                    diagnostics,
                    "active_document",
                    InvokeRuntime(diagnostics, () => runtime.ActiveDocument(diagnostics))),
                "list_categories" => FromBimResponse(
                    diagnostics,
                    "list_categories",
                    InvokeRuntime(diagnostics, () => runtime.ListCategories(diagnostics))),
                "query_elements" => DispatchQueryElements(runtime, diagnostics, body),
                "element_info" => DispatchTypedRequest<BimElementRequest>(
                    diagnostics,
                    "element_info",
                    body,
                    request => runtime.ElementInfo(diagnostics, request)),
                "element_parameters" => DispatchTypedRequest<BimElementRequest>(
                    diagnostics,
                    "element_parameters",
                    body,
                    request => runtime.ElementParameters(diagnostics, request)),
                "select_elements" => DispatchTypedRequest<BimSelectElementsRequest>(
                    diagnostics,
                    "select_elements",
                    body,
                    request => runtime.SelectElements(diagnostics, request)),
                "clear_selection" => FromBimResponse(
                    diagnostics,
                    "clear_selection",
                    InvokeRuntime(diagnostics, () => runtime.ClearSelection(diagnostics))),
                "export_elements" => DispatchTypedRequest<BimExportElementsRequest>(
                    diagnostics,
                    "export_elements",
                    body,
                    request => runtime.ExportElements(diagnostics, request)),
                "export_preset" => DispatchTypedRequest<BimExportPresetRequest>(
                    diagnostics,
                    "export_preset",
                    body,
                    request => runtime.ExportPreset(diagnostics, request)),
                _ => Fail(
                    diagnostics,
                    BimErrorCode.InvalidScope,
                    $"Unknown BIM op '{op}'.",
                    400),
            };
        }

        private ApiResponse DispatchQueryElements(
            IRookBimRuntime runtime,
            BimDiagnosticContext diagnostics,
            string? body)
        {
            var request = DeserializeRequest<BimQueryElementsRequest>(diagnostics, body);
            var validation = request.Validate();
            if (!validation.Success)
            {
                return Fail(
                    diagnostics,
                    validation.ErrorCode,
                    validation.Message ?? "BIM query validation failed.",
                    400);
            }

            return FromBimResponse(
                diagnostics,
                "query_elements",
                InvokeRuntime(
                    diagnostics,
                    () => runtime.QueryElements(diagnostics, request)));
        }

        private ApiResponse DispatchTypedRequest<T>(
            BimDiagnosticContext diagnostics,
            string op,
            string? body,
            Func<T, BimApiResponse> runtimeCall)
            where T : new()
        {
            var request = DeserializeRequest<T>(diagnostics, body);
            return FromBimResponse(
                diagnostics,
                op,
                InvokeRuntime(diagnostics, () => runtimeCall(request)));
        }

        private static T DeserializeRequest<T>(
            BimDiagnosticContext diagnostics,
            string? body)
            where T : new()
        {
            BimDiagnostics.Observe(
                diagnostics,
                BimDiagnosticStage.HandlerDeserialize,
                BimDiagnosticOutcome.Start,
                BimDiagnosticFields.None);
            try
            {
                var result = string.IsNullOrWhiteSpace(body)
                    ? new T()
                    : JsonSerializer.Deserialize<T>(body!, JsonOptions) ?? new T();
                BimDiagnostics.Observe(
                    diagnostics,
                    BimDiagnosticStage.HandlerDeserialize,
                    BimDiagnosticOutcome.Success,
                    BimDiagnosticFields.None);
                return result;
            }
            catch (Exception ex)
            {
                ObserveDeserializeFailure(diagnostics, ex);
                throw;
            }
        }

        private static void ObserveDeserializeFailure(
            BimDiagnosticContext diagnostics,
            Exception exception)
        {
            BimDiagnostics.ObserveException(
                diagnostics,
                BimDiagnosticStage.HandlerDeserialize,
                exception,
                new BimDiagnosticFields(
                    BimDiagnosticDetailCode.None,
                    null,
                    BimDiagnosticFailureImpact.Production));
        }

        private static bool HasSerializationFailure(
            BimDiagnosticContext diagnostics)
        {
            var snapshot = BimDiagnostics.SnapshotRequest(diagnostics);
            return snapshot.LastStage == BimDiagnosticStage.HandlerSerialize &&
                snapshot.LastOutcome == BimDiagnosticOutcome.Failure;
        }

        private static T InvokeRuntime<T>(
            BimDiagnosticContext diagnostics,
            Func<T> operation)
        {
            BimDiagnostics.Observe(
                diagnostics,
                BimDiagnosticStage.HandlerRuntime,
                BimDiagnosticOutcome.Start,
                BimDiagnosticFields.None);
            try
            {
                var result = operation();
                BimDiagnostics.Observe(
                    diagnostics,
                    BimDiagnosticStage.HandlerRuntime,
                    BimDiagnosticOutcome.Success,
                    BimDiagnosticFields.None);
                return result;
            }
            catch (Exception ex)
            {
                BimDiagnostics.ObserveException(
                    diagnostics,
                    BimDiagnosticStage.HandlerRuntime,
                    ex,
                    new BimDiagnosticFields(
                        BimDiagnosticDetailCode.None,
                        null,
                        BimDiagnosticFailureImpact.Production));
                throw;
            }
        }

        private static Dictionary<string, JsonElement> ParseObjectBody(string? body)
        {
            if (string.IsNullOrWhiteSpace(body))
            {
                return new Dictionary<string, JsonElement>(StringComparer.Ordinal);
            }

            using var document = JsonDocument.Parse(body!);
            if (document.RootElement.ValueKind != JsonValueKind.Object)
            {
                throw new ArgumentException("BIM request body must be a JSON object.");
            }

            var args = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
            foreach (var property in document.RootElement.EnumerateObject())
            {
                args[property.Name] = property.Value.Clone();
            }

            return args;
        }

        private static string? GetStringArg(Dictionary<string, JsonElement> args, string name)
        {
            if (!args.TryGetValue(name, out var value) || value.ValueKind != JsonValueKind.String)
            {
                return null;
            }

            return value.GetString();
        }

        private ApiResponse DispatchStatus(
            IRookBimRuntime runtime,
            BimDiagnosticContext diagnostics)
        {
            var status = InvokeRuntime(
                diagnostics,
                () => runtime.Status(diagnostics));
            PopulateStatusDiagnostics(status);
            var diagnostic = BuildDiagnosticForReason(
                DiagnosticReasonFromStatus(status),
                "status");

            return Ok(diagnostics, status, diagnostic);
        }

        private ApiResponse DispatchStandaloneStatus(
            BimDiagnosticContext diagnostics)
        {
            var status = new BimStatusResponse
            {
                Available = false,
                Runtime = "unavailable",
                ErrorCode = "not_rhino_inside",
                Message = "RookBIM requires Rhino.Inside.Revit host state.",
                Host = "standalone",
                Module = "core",
            };
            PopulateStatusDiagnostics(status);

            return Ok(
                diagnostics,
                status,
                BuildDiagnosticForReason("not_rhino_inside", "status"));
        }

        private bool IsRunningAsRhinoInside()
        {
            try
            {
                return rhinoInsideProvider();
            }
            catch
            {
                return false;
            }
        }

        private ApiResponse FromBimResponse(
            BimDiagnosticContext diagnostics,
            string op,
            BimApiResponse response)
        {
            if (response.Success)
            {
                var data = SerializeForWire(diagnostics, response.Data);
                return new ApiResponse
                {
                    Success = true,
                    Data = data,
                    HttpStatus = response.HttpStatus,
                    Diagnostic = MergeRequestDiagnostic(diagnostics, null),
                };
            }

            return Fail(
                diagnostics,
                response.ErrorCode,
                response.Message ?? "BIM operation failed.",
                response.HttpStatus,
                response.Data,
                BuildDiagnosticForReason(
                    DiagnosticReasonFromResponse(response),
                    op));
        }

        private ApiResponse Ok(
            BimDiagnosticContext diagnostics,
            object? data,
            JsonObject? diagnostic = null)
        {
            var wireData = SerializeForWire(diagnostics, data);
            return new ApiResponse
            {
                Success = true,
                Data = wireData,
                HttpStatus = 200,
                Diagnostic = MergeRequestDiagnostic(diagnostics, diagnostic),
            };
        }

        private ApiResponse Fail(
            BimDiagnosticContext diagnostics,
            BimErrorCode code,
            string message,
            int httpStatus,
            object? details = null,
            JsonObject? diagnostic = null)
        {
            var data = new JsonObject
            {
                ["errorCode"] = MapErrorCode(code),
                ["message"] = message,
            };

            if (details != null)
            {
                data["details"] = SerializeForWire(diagnostics, details);
            }

            return new ApiResponse
            {
                Success = false,
                Data = data,
                HttpStatus = httpStatus,
                Diagnostic = MergeRequestDiagnostic(diagnostics, diagnostic),
            };
        }

        private ApiResponse BuildMinimalInternalError(
            BimDiagnosticContext diagnostics,
            Exception exception)
        {
            var snapshot = BimDiagnostics.SnapshotRequest(diagnostics);
            if (!snapshot.FirstFailureStage.HasValue)
            {
                BimDiagnostics.ObserveException(
                    diagnostics,
                    BimDiagnosticStage.HandlerRuntime,
                    exception,
                    new BimDiagnosticFields(
                        BimDiagnosticDetailCode.None,
                        null,
                        BimDiagnosticFailureImpact.Production));
            }

            return new ApiResponse
            {
                Success = false,
                Data = new JsonObject
                {
                    ["errorCode"] = "internal_error",
                    ["message"] = "BIM dispatch failed.",
                },
                HttpStatus = 500,
                Diagnostic = MergeRequestDiagnostic(diagnostics, null),
            };
        }

        private JsonNode? SerializeForWire(
            BimDiagnosticContext diagnostics,
            object? value)
        {
            BimDiagnostics.Observe(
                diagnostics,
                BimDiagnosticStage.HandlerSerialize,
                BimDiagnosticOutcome.Start,
                BimDiagnosticFields.None);
            try
            {
                var result = wireSerializer(value);
                BimDiagnostics.Observe(
                    diagnostics,
                    BimDiagnosticStage.HandlerSerialize,
                    BimDiagnosticOutcome.Success,
                    BimDiagnosticFields.None);
                return result;
            }
            catch (Exception ex)
            {
                BimDiagnostics.ObserveException(
                    diagnostics,
                    BimDiagnosticStage.HandlerSerialize,
                    ex,
                    new BimDiagnosticFields(
                        BimDiagnosticDetailCode.SerializationFailure,
                        null,
                        BimDiagnosticFailureImpact.Production));
                throw;
            }
        }

        private static void PopulateStatusDiagnostics(BimStatusResponse status)
        {
            var snapshot = BimDiagnostics.SnapshotStatus();
            status.CoreVersion = snapshot.CoreVersion;
            status.CoreCommit = snapshot.CoreCommit;
            status.ModuleVersion = snapshot.ModuleVersion;
            status.ModuleCommit = snapshot.ModuleCommit;
            status.DiagnosticsEnabled = snapshot.Enabled;
            status.SinkState = BimDiagnosticJsonEncoder.ToWire(snapshot.SinkState);
            status.DroppedCount = snapshot.DroppedCount;
            status.SinkFailureCode =
                BimDiagnosticJsonEncoder.ToWire(snapshot.FailureCode);
        }

        private static JsonObject? MergeRequestDiagnostic(
            BimDiagnosticContext diagnostics,
            JsonObject? diagnostic)
        {
            if (!diagnostics.Enabled || diagnostics.CorrelationId == null)
            {
                return diagnostic;
            }

            var request = BimDiagnostics.SnapshotRequest(diagnostics);
            var status = BimDiagnostics.SnapshotStatus();
            diagnostic ??= new JsonObject();
            diagnostic["correlationId"] = diagnostics.CorrelationId;
            diagnostic["lastStage"] = request.LastStage.HasValue
                ? BimDiagnosticJsonEncoder.ToWire(request.LastStage.Value)
                : null;
            diagnostic["lastOutcome"] = request.LastOutcome.HasValue
                ? BimDiagnosticJsonEncoder.ToWire(request.LastOutcome.Value)
                : null;
            diagnostic["lastItemIndex"] = request.LastItemIndex;
            diagnostic["firstFailureStage"] = request.FirstFailureStage.HasValue
                ? BimDiagnosticJsonEncoder.ToWire(request.FirstFailureStage.Value)
                : null;
            diagnostic["firstFailureExceptionType"] =
                request.FirstFailureExceptionType;
            diagnostic["firstFailureHResult"] = request.FirstFailureHResult;
            diagnostic["requestDroppedCount"] = request.RequestDroppedCount;
            diagnostic["traceComplete"] = request.TraceComplete;
            diagnostic["sinkState"] =
                BimDiagnosticJsonEncoder.ToWire(status.SinkState);
            diagnostic["droppedCount"] = status.DroppedCount;
            return diagnostic;
        }

        private static JsonNode? ToWireData(object? data)
        {
            if (data == null)
            {
                return null;
            }

            return JsonSerializer.SerializeToNode(data, JsonOptions);
        }

        internal static string MapErrorCode(BimErrorCode code)
        {
            return code switch
            {
                BimErrorCode.RookBimUnavailable => "rookbim_unavailable",
                BimErrorCode.NotRhinoInside => "not_rhino_inside",
                BimErrorCode.RevitUnavailable => "revit_unavailable",
                BimErrorCode.NoActiveDocument => "no_active_document",
                BimErrorCode.NoActiveView => "no_active_view",
                BimErrorCode.InvalidScope => "invalid_scope",
                BimErrorCode.UnboundedDocumentQuery => "unbounded_document_query",
                BimErrorCode.InvalidCategory => "invalid_category",
                BimErrorCode.AmbiguousCategory => "ambiguous_category",
                BimErrorCode.CategoryNotQueryable => "category_not_queryable",
                BimErrorCode.QueryLimitExceeded => "query_limit_exceeded",
                BimErrorCode.AmbiguousParameter => "ambiguous_parameter",
                BimErrorCode.ElementNotFound => "element_not_found",
                BimErrorCode.DocumentMismatch => "document_mismatch",
                BimErrorCode.LinkedElementUnsupported => "linked_element_unsupported",
                BimErrorCode.CapabilityUnavailable => "capability_unavailable",
                BimErrorCode.SelectionFailed => "selection_failed",
                BimErrorCode.QueryTruncated => "query_truncated",
                BimErrorCode.OutputPathInvalid => "output_path_invalid",
                BimErrorCode.NoExportableGeometry => "no_exportable_geometry",
                BimErrorCode.ExportFailed => "export_failed",
                BimErrorCode.UnknownPreset => "unknown_preset",
                BimErrorCode.NoCategoriesResolved => "no_categories_resolved",
                BimErrorCode.InternalError => "internal_error",
                BimErrorCode.None => "internal_error",
                _ => "internal_error",
            };
        }

        private static string? DiagnosticReasonFromStatus(BimStatusResponse status)
        {
            if (string.Equals(status.ErrorCode, "rookbim_unavailable", StringComparison.Ordinal))
            {
                return DiagnosticReasonFromRegistrySource(RookBimRuntimeRegistry.Source);
            }

            return status.ErrorCode;
        }

        private static string? DiagnosticReasonFromResponse(BimApiResponse response)
        {
            var errorCode = MapErrorCode(response.ErrorCode);
            if (string.Equals(errorCode, "rookbim_unavailable", StringComparison.Ordinal))
            {
                return DiagnosticReasonFromRegistrySource(RookBimRuntimeRegistry.Source);
            }

            return errorCode;
        }

        private static string? DiagnosticReasonFromRegistrySource(string source)
        {
            return source switch
            {
                "core-fallback" => "rookbim_runtime_not_activated",
                "module-not-found" => "rookbim_module_not_found",
                "module-load-failed" => "rookbim_module_load_failed",
                _ => null,
            };
        }

        private static JsonObject? BuildDiagnosticForReason(string? reasonCode, string op)
        {
            if (string.IsNullOrWhiteSpace(reasonCode))
            {
                return null;
            }

            string failureKind;
            string ownedBy;
            string evidenceSource;
            bool retryable;
            bool userActionRequired;
            string recommendedNextStep;

            switch (reasonCode)
            {
                case "not_rhino_inside":
                    failureKind = "host_blocked";
                    ownedBy = "rookbim";
                    evidenceSource = "rookbim_host_runtime";
                    retryable = false;
                    userActionRequired = true;
                    recommendedNextStep = "Open Rhino through Rhino.Inside.Revit, then retry.";
                    break;
                case "rookbim_runtime_not_activated":
                    failureKind = "dependency_unavailable";
                    ownedBy = "managed";
                    evidenceSource = "managed_rookbim_runtime_registry";
                    retryable = true;
                    userActionRequired = false;
                    recommendedNextStep = "Wait for RookBIM runtime activation, then retry.";
                    break;
                case "rookbim_module_not_found":
                    failureKind = "dependency_unavailable";
                    ownedBy = "managed";
                    evidenceSource = "managed_rookbim_module_loader";
                    retryable = false;
                    userActionRequired = true;
                    recommendedNextStep = "Verify the RookBIM module payload is present, then restart Rhino.";
                    break;
                case "rookbim_module_load_failed":
                    failureKind = "dependency_degraded";
                    ownedBy = "managed";
                    evidenceSource = "managed_rookbim_module_loader";
                    retryable = true;
                    userActionRequired = true;
                    recommendedNextStep = "Inspect RookBIM module load diagnostics, then restart Rhino.";
                    break;
                case "no_active_document":
                    failureKind = "operation_unavailable";
                    ownedBy = "rookbim";
                    evidenceSource = "rookbim_revit_runtime";
                    retryable = true;
                    userActionRequired = true;
                    recommendedNextStep = "Open an active Revit document, then retry.";
                    break;
                default:
                    return null;
            }

            return new JsonObject
            {
                ["schemaVersion"] = 1,
                ["domainId"] = "bim.rhino_inside_revit",
                ["route"] = RouteForOp(op),
                ["operation"] = op,
                ["reasonCode"] = reasonCode,
                ["failureKind"] = failureKind,
                ["retryable"] = retryable,
                ["userActionRequired"] = userActionRequired,
                ["diagnosticRoute"] = DiagnosticRoute(),
                ["recommendedNextStep"] = recommendedNextStep,
                ["ownedBy"] = ownedBy,
                ["evidenceSource"] = evidenceSource,
                ["emittedBy"] = "managed_route",
            };
        }

        private static JsonObject DiagnosticRoute()
        {
            return new JsonObject
            {
                ["method"] = "GET",
                ["path"] = "/capabilities",
                ["domainId"] = "bim.rhino_inside_revit",
            };
        }

        private static string RouteForOp(string op)
        {
            return op switch
            {
                "status" => "GET /bim/status",
                "active_document" => "GET /bim/active-document",
                "list_categories" => "GET /bim/categories",
                "query_elements" => "POST /bim/query-elements",
                "element_info" => "POST /bim/element-info",
                "element_parameters" => "POST /bim/element-parameters",
                "select_elements" => "POST /bim/select-elements",
                "clear_selection" => "POST /bim/clear-selection",
                "export_elements" => "POST /bim/export-elements",
                "export_preset" => "POST /bim/export-preset",
                _ => "POST /bim",
            };
        }

        private static JsonSerializerOptions CreateJsonOptions()
        {
            var options = new JsonSerializerOptions
            {
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            };
            options.Converters.Add(new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower));
            return options;
        }
    }
}
