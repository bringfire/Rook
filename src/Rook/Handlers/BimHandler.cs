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

            RookBimModuleLoader.TryActivate();

            try
            {
                var runtime = RookBimRuntimeRegistry.Current;
                return op switch
                {
                    "status" => Ok(runtime.Status()),
                    "active_document" => FromBimResponse(runtime.ActiveDocument()),
                    "list_categories" => FromBimResponse(runtime.ListCategories()),
                    "query_elements" => DispatchQueryElements(runtime, body),
                    "element_info" => FromBimResponse(
                        runtime.ElementInfo(DeserializeRequest<BimElementRequest>(body))),
                    "element_parameters" => FromBimResponse(
                        runtime.ElementParameters(DeserializeRequest<BimElementRequest>(body))),
                    "select_elements" => FromBimResponse(
                        runtime.SelectElements(DeserializeRequest<BimSelectElementsRequest>(body))),
                    "clear_selection" => FromBimResponse(runtime.ClearSelection()),
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

            return FromBimResponse(runtime.QueryElements(request));
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

        private static ApiResponse FromBimResponse(BimApiResponse response)
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
                response.Data);
        }

        private static ApiResponse Ok(object? data)
        {
            return new ApiResponse
            {
                Success = true,
                Data = ToWireData(data),
                HttpStatus = 200,
            };
        }

        private static ApiResponse Fail(
            BimErrorCode code,
            string message,
            int httpStatus,
            object? details = null)
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
                BimErrorCode.InternalError => "internal_error",
                BimErrorCode.None => "internal_error",
                _ => "internal_error",
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
