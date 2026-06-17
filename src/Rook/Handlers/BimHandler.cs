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

        public BimHandler()
            : this(() => Rhino.Runtime.HostUtils.RunningAsRhinoInside)
        {
        }

        internal BimHandler(Func<bool> rhinoInsideProvider)
        {
            this.rhinoInsideProvider = rhinoInsideProvider
                ?? throw new ArgumentNullException(nameof(rhinoInsideProvider));
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
            Dictionary<string, JsonElement> args;
            try
            {
                args = ParseObjectBody(body);
            }
            catch (ArgumentException ex)
            {
                return Fail(BimErrorCode.InvalidScope, ex.Message, 400);
            }
            catch (JsonException ex)
            {
                return Fail(BimErrorCode.InvalidScope, $"Invalid BIM request JSON: {ex.Message}", 400);
            }

            var op = GetStringArg(args, "op");
            if (string.IsNullOrWhiteSpace(op))
            {
                return Fail(
                    BimErrorCode.InvalidScope,
                    "BIM request missing required 'op' discriminator.",
                    400);
            }

            if (!ExpectedBimOpSet.Contains(op!))
            {
                return Fail(
                    BimErrorCode.InvalidScope,
                    $"Unknown BIM op '{op}'.",
                    400);
            }

            if (string.Equals(op, "status", StringComparison.Ordinal) && !IsRunningAsRhinoInside())
            {
                return DispatchStandaloneStatus();
            }

            RookBimModuleLoader.TryActivate();

            try
            {
                var runtime = RookBimRuntimeRegistry.Current;
                return op switch
                {
                    "status" => DispatchStatus(runtime),
                    "active_document" => FromBimResponse("active_document", runtime.ActiveDocument()),
                    "list_categories" => FromBimResponse("list_categories", runtime.ListCategories()),
                    "query_elements" => DispatchQueryElements(runtime, body),
                    "element_info" => FromBimResponse(
                        "element_info",
                        runtime.ElementInfo(DeserializeRequest<BimElementRequest>(body))),
                    "element_parameters" => FromBimResponse(
                        "element_parameters",
                        runtime.ElementParameters(DeserializeRequest<BimElementRequest>(body))),
                    "select_elements" => FromBimResponse(
                        "select_elements",
                        runtime.SelectElements(DeserializeRequest<BimSelectElementsRequest>(body))),
                    "clear_selection" => FromBimResponse("clear_selection", runtime.ClearSelection()),
                    "export_elements" => FromBimResponse(
                        "export_elements",
                        runtime.ExportElements(DeserializeRequest<BimExportElementsRequest>(body))),
                    "export_preset" => FromBimResponse(
                        "export_preset",
                        runtime.ExportPreset(DeserializeRequest<BimExportPresetRequest>(body))),
                    _ => Fail(BimErrorCode.InvalidScope, $"Unknown BIM op '{op}'.", 400),
                };
            }
            catch (JsonException ex)
            {
                return Fail(BimErrorCode.InvalidScope, $"Invalid BIM request JSON: {ex.Message}", 400);
            }
            catch (ArgumentException ex)
            {
                return Fail(BimErrorCode.InvalidScope, ex.Message, 400);
            }
            catch (Exception ex)
            {
                return Fail(BimErrorCode.InternalError, $"BIM dispatch failed: {ex.Message}", 500);
            }
        }

        private static ApiResponse DispatchQueryElements(IRookBimRuntime runtime, string? body)
        {
            var request = DeserializeRequest<BimQueryElementsRequest>(body);
            var validation = request.Validate();
            if (!validation.Success)
            {
                return Fail(
                    validation.ErrorCode,
                    validation.Message ?? "BIM query validation failed.",
                    400);
            }

            return FromBimResponse("query_elements", runtime.QueryElements(request));
        }

        private static T DeserializeRequest<T>(string? body)
            where T : new()
        {
            if (string.IsNullOrWhiteSpace(body))
            {
                return new T();
            }

            return JsonSerializer.Deserialize<T>(body!, JsonOptions) ?? new T();
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

        private static ApiResponse DispatchStatus(IRookBimRuntime runtime)
        {
            var status = runtime.Status();
            var diagnostic = BuildDiagnosticForReason(
                DiagnosticReasonFromStatus(status),
                "status");

            return Ok(status, diagnostic);
        }

        private ApiResponse DispatchStandaloneStatus()
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

            return Ok(
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

        private static ApiResponse FromBimResponse(string op, BimApiResponse response)
        {
            if (response.Success)
            {
                return new ApiResponse
                {
                    Success = true,
                    Data = ToWireData(response.Data),
                    HttpStatus = response.HttpStatus,
                };
            }

            return Fail(
                response.ErrorCode,
                response.Message ?? "BIM operation failed.",
                response.HttpStatus,
                response.Data,
                BuildDiagnosticForReason(
                    DiagnosticReasonFromResponse(response),
                    op));
        }

        private static ApiResponse Ok(object? data, JsonObject? diagnostic = null)
        {
            return new ApiResponse
            {
                Success = true,
                Data = ToWireData(data),
                HttpStatus = 200,
                Diagnostic = diagnostic,
            };
        }

        private static ApiResponse Fail(
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
                data["details"] = ToWireData(details);
            }

            return new ApiResponse
            {
                Success = false,
                Data = data,
                HttpStatus = httpStatus,
                Diagnostic = diagnostic,
            };
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
