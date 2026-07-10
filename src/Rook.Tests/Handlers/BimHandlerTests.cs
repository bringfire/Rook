using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook.Bim;
using Rook.Handlers;
using Rook.Tests.Bim;
using Xunit;

namespace Rook.Tests.Handlers
{
    [Collection(RookBimRuntimeRegistryCollection.Name)]
    public class BimHandlerTests
    {
        private static readonly string[] Phase1Ops =
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

        [Fact]
        public void ExpectedBimOps_HasExactlyPhase1Ops()
        {
            Assert.Equal(Phase1Ops, BimHandler.ExpectedBimOps);
        }

        [Fact]
        public void Dispatch_UnknownOp_ReturnsStructured400()
        {
            var handler = new BimHandler();

            var response = handler.Dispatch("{\"op\":\"write_wall\"}");
            var data = ToJsonElement(response.Data);

            Assert.Equal(400, response.HttpStatus);
            Assert.False(response.Success);
            Assert.Equal("invalid_scope", data.GetProperty("errorCode").GetString());
            Assert.Contains("Unknown BIM op", data.GetProperty("message").GetString());
        }

        [Fact]
        public void Dispatch_Status_ReturnsStructuredUnavailableRuntime()
        {
            RookBimRuntimeRegistry.ResetForTests();
            var handler = new BimHandler();

            var response = handler.Dispatch("{\"op\":\"status\"}");
            var data = ToJsonElement(response.Data);

            Assert.Equal(200, response.HttpStatus);
            Assert.True(response.Success);
            Assert.False(data.GetProperty("available").GetBoolean());
            Assert.Contains(
                data.GetProperty("errorCode").GetString(),
                new[] { "rookbim_unavailable", "not_rhino_inside" });
        }

        [Fact]
        public void Dispatch_Status_AddsNotRhinoInsideDiagnosticFromRuntimeStatus()
        {
            RookBimRuntimeRegistry.Install(
                new StatusRuntime("not_rhino_inside", "RookBIM requires RhinoInside.Revit and RevitAPIUI to be loaded."),
                "RookBim.dll");

            try
            {
                var handler = new BimHandler(() => true);
                var response = handler.Dispatch("{\"op\":\"status\"}");
                var data = ToJsonElement(response.Data);

                Assert.Equal(200, response.HttpStatus);
                Assert.True(response.Success);
                Assert.Equal("not_rhino_inside", data.GetProperty("errorCode").GetString());
                AssertDiagnostic(
                    response,
                    "not_rhino_inside",
                    "host_blocked",
                    "rookbim",
                    "rookbim_host_runtime",
                    "managed_route",
                    "status");
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        [Fact]
        public void Dispatch_Status_UsesStandaloneHostEvidenceBeforeModuleActivation()
        {
            RookBimRuntimeRegistry.ResetForTests();
            var handler = new BimHandler(() => false);

            var response = handler.Dispatch("{\"op\":\"status\"}");
            var data = ToJsonElement(response.Data);

            Assert.Equal("core-fallback", RookBimRuntimeRegistry.Source);
            Assert.Equal(200, response.HttpStatus);
            Assert.True(response.Success);
            Assert.Equal("not_rhino_inside", data.GetProperty("errorCode").GetString());
            Assert.Equal("standalone", data.GetProperty("host").GetString());
            Assert.Equal("core", data.GetProperty("module").GetString());
            AssertDiagnostic(
                response,
                "not_rhino_inside",
                "host_blocked",
                "rookbim",
                "rookbim_host_runtime",
                "managed_route",
                "status");
        }

        [Fact]
        public void Dispatch_NonStatusSuccessDoesNotEmitFailureDiagnostic()
        {
            RookBimRuntimeRegistry.Install(new DetailFailureRuntime(), "test-list-categories");
            try
            {
                var handler = new BimHandler();
                var response = handler.Dispatch("{\"op\":\"list_categories\"}");

                Assert.True(response.Success);
                Assert.Null(response.Diagnostic);
                Assert.Contains("document_category_table", ((JsonNode)response.Data!).ToJsonString());
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        [Theory]
        [InlineData("module-not-found", "rookbim_module_not_found", "dependency_unavailable", "managed_rookbim_module_loader", false, true)]
        [InlineData("module-load-failed", "rookbim_module_load_failed", "dependency_degraded", "managed_rookbim_module_loader", true, true)]
        public void Dispatch_DocumentOperation_AddsModuleReadinessDiagnosticsFromRegistrySource(
            string source,
            string reasonCode,
            string failureKind,
            string evidenceSource,
            bool retryable,
            bool userActionRequired)
        {
            RookBimRuntimeRegistry.Install(
                new RookBimUnavailableRuntime(
                    "rookbim_unavailable",
                    "Configured unavailable runtime message.",
                    "module-loader"),
                source);

            try
            {
                var handler = new BimHandler();
                var response = handler.Dispatch("{\"op\":\"active_document\"}");
                var data = ToJsonElement(response.Data);
                var diagnostic = Diagnostic(response);

                Assert.Equal(503, response.HttpStatus);
                Assert.False(response.Success);
                Assert.Equal("rookbim_unavailable", data.GetProperty("errorCode").GetString());
                Assert.Equal(reasonCode, diagnostic.GetProperty("reasonCode").GetString());
                Assert.Equal(failureKind, diagnostic.GetProperty("failureKind").GetString());
                Assert.Equal("managed", diagnostic.GetProperty("ownedBy").GetString());
                Assert.Equal(evidenceSource, diagnostic.GetProperty("evidenceSource").GetString());
                Assert.Equal("managed_route", diagnostic.GetProperty("emittedBy").GetString());
                Assert.Equal(retryable, diagnostic.GetProperty("retryable").GetBoolean());
                Assert.Equal(userActionRequired, diagnostic.GetProperty("userActionRequired").GetBoolean());
                Assert.Equal("active_document", diagnostic.GetProperty("operation").GetString());
                Assert.False(diagnostic.TryGetProperty("state", out _));
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        [Fact]
        public void Dispatch_DocumentOperation_AddsNoActiveDocumentDiagnosticFromRuntimeResponse()
        {
            RookBimRuntimeRegistry.Install(new NoActiveDocumentRuntime(), "RookBim.dll");

            try
            {
                var handler = new BimHandler();
                var response = handler.Dispatch("{\"op\":\"active_document\"}");
                var data = ToJsonElement(response.Data);

                Assert.Equal(409, response.HttpStatus);
                Assert.False(response.Success);
                Assert.Equal("no_active_document", data.GetProperty("errorCode").GetString());
                AssertDiagnostic(
                    response,
                    "no_active_document",
                    "operation_unavailable",
                    "rookbim",
                    "rookbim_revit_runtime",
                    "managed_route",
                    "active_document");
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        [Fact]
        public void ModuleLoader_ResolvesRookBimNextToLoadedCompanionAssembly()
        {
            var paths = RookBimModuleLoader.ResolveCandidateModulePathsForTests();
            var companionDirectory = Path.GetDirectoryName(typeof(RookBimModuleLoader).Assembly.Location);

            Assert.Contains(Path.Combine(companionDirectory!, "RookBim.dll"), paths);
        }

        [Fact]
        public void ModuleLoader_SourceDoesNotDependOnlyOnAppContextBaseDirectory()
        {
            var source = ReadSourceFile("src", "Rook", "Bim", "RookBimModuleLoader.cs");

            Assert.Contains("typeof(RookBimModuleLoader).Assembly.Location", source);
            Assert.DoesNotContain("Path.Combine(AppContext.BaseDirectory, \"RookBim.dll\");", source);
            Assert.Contains("RookBIM module was not found.", source);
            Assert.Contains("Searched:", source);
        }

        [Fact]
        public void Dispatch_QueryElements_RejectsDocumentScopeWithoutCategory()
        {
            var handler = new BimHandler();

            var response = handler.Dispatch(
                "{\"op\":\"query_elements\",\"scope\":\"document\",\"filters\":[{\"parameter\":\"Fire Rating\",\"operation\":\"not_equals\",\"value\":\"2HR\"}]}");
            var data = ToJsonElement(response.Data);

            Assert.Equal(400, response.HttpStatus);
            Assert.False(response.Success);
            Assert.Equal("unbounded_document_query", data.GetProperty("errorCode").GetString());
            Assert.Contains("document scope requires category", data.GetProperty("message").GetString());
        }

        [Fact]
        public void Dispatch_MalformedJson_ReturnsStructured400()
        {
            var handler = new BimHandler();

            var response = handler.Dispatch("{");
            var data = ToJsonElement(response.Data);

            Assert.Equal(400, response.HttpStatus);
            Assert.False(response.Success);
            Assert.Equal("invalid_scope", data.GetProperty("errorCode").GetString());
            Assert.Contains("Invalid BIM request JSON", data.GetProperty("message").GetString());
        }

        [Fact]
        public void Dispatch_FailureResponse_PreservesRuntimeDetails()
        {
            RookBimRuntimeRegistry.Install(new DetailFailureRuntime(), "test-detail-failure");
            var handler = new BimHandler();

            try
            {
                var response = handler.Dispatch("{\"op\":\"active_document\"}");
                var data = ToJsonElement(response.Data);

                Assert.Equal(409, response.HttpStatus);
                Assert.False(response.Success);
                Assert.Equal("document_mismatch", data.GetProperty("errorCode").GetString());
                Assert.Equal("Document changed.", data.GetProperty("message").GetString());
                Assert.Equal("expected-doc", data.GetProperty("details").GetProperty("expectedDocumentGuid").GetString());
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        [Fact]
        public void Dispatch_ListCategories_UsesRuntime()
        {
            RookBimRuntimeRegistry.Install(new DetailFailureRuntime(), "test-list-categories");
            try
            {
                var handler = new BimHandler();
                var response = handler.Dispatch("{\"op\":\"list_categories\"}");

                Assert.True(response.Success);
                Assert.Contains("document_category_table", ((JsonNode)response.Data!).ToJsonString());
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        [Fact]
        public void MapErrorCode_MapsCategoryResolutionErrors()
        {
            Assert.Equal("ambiguous_category", BimHandler.MapErrorCode(BimErrorCode.AmbiguousCategory));
            Assert.Equal("category_not_queryable", BimHandler.MapErrorCode(BimErrorCode.CategoryNotQueryable));
        }

        [Fact]
        public void Dispatch_CategoryFailure_PreservesResolutionUnderDetails()
        {
            RookBimRuntimeRegistry.Install(new CategoryFailureRuntime(), "test-category-failure");
            try
            {
                var handler = new BimHandler();
                var response = handler.Dispatch("{\"op\":\"query_elements\",\"scope\":\"document\",\"category\":\"Pipe Accessoryz\"}");
                var json = ((JsonNode)response.Data!).ToJsonString();

                Assert.False(response.Success);
                Assert.Contains("\"errorCode\":\"invalid_category\"", json);
                Assert.Contains("\"details\":{\"resolution\":", json);
                Assert.Contains("\"status\":\"invalid\"", json);
                Assert.Contains("\"input\":\"Pipe Accessoryz\"", json);
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        [Fact]
        public void Dispatch_ValidationAndOperationTaxonomyErrorsDoNotEmitPhase2CDiagnostics()
        {
            var handler = new BimHandler();

            var unknownOp = handler.Dispatch("{\"op\":\"write_wall\"}");
            Assert.Null(unknownOp.Diagnostic);
            Assert.Equal("invalid_scope", ToJsonElement(unknownOp.Data).GetProperty("errorCode").GetString());

            var malformed = handler.Dispatch("{");
            Assert.Null(malformed.Diagnostic);
            Assert.Equal("invalid_scope", ToJsonElement(malformed.Data).GetProperty("errorCode").GetString());

            var unbounded = handler.Dispatch(
                "{\"op\":\"query_elements\",\"scope\":\"document\",\"filters\":[{\"parameter\":\"Fire Rating\",\"operation\":\"not_equals\",\"value\":\"2HR\"}]}");
            Assert.Null(unbounded.Diagnostic);
            Assert.Equal("unbounded_document_query", ToJsonElement(unbounded.Data).GetProperty("errorCode").GetString());

            RookBimRuntimeRegistry.Install(new CategoryFailureRuntime(), "test-category-failure");
            try
            {
                var invalidCategory = handler.Dispatch("{\"op\":\"query_elements\",\"scope\":\"document\",\"category\":\"Pipe Accessoryz\"}");
                Assert.Null(invalidCategory.Diagnostic);
                Assert.Equal("invalid_category", ToJsonElement(invalidCategory.Data).GetProperty("errorCode").GetString());
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        [Fact]
        public void ApiResponse_DiagnosticIsOptionalAndBridgeStatusIgnoresIt()
        {
            var response = new ApiResponse
            {
                Success = false,
                Data = "legacy data",
                HttpStatus = 418,
                Diagnostic = new
                {
                    reasonCode = "not_rhino_inside",
                },
            };

            Assert.NotNull(response.Diagnostic);

            var source = ReadSourceFile("src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs");
            var mapBridgeStatusLine = source
                .Split(new[] { "\r\n", "\n" }, StringSplitOptions.None)
                .Single(line => line.IndexOf("MapBridgeStatus(ApiResponse result) =>", StringComparison.Ordinal) >= 0);

            Assert.Contains("result.HttpStatus ?? (result.Success ? 200 : 400)", source);
            Assert.DoesNotContain("Diagnostic", mapBridgeStatusLine);
        }

        [Fact]
        public void ManagedBridge_OnlyBimDispatchSerializesApiResponseDiagnostic()
        {
            var source = ReadSourceFile("src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs");
            var bimDispatch = ExtractFunctionBySignature(source, "private static int ExecuteBimDispatchCallback(");
            var bimEnvelope = ExtractFunctionBySignature(source, "private static string SerializeBimDispatchEnvelope(");
            var apiResponse = ExtractFunctionBySignature(source, "private static int ExecuteApiResponseCallback(");
            var asyncApiResponse = ExtractFunctionBySignature(source, "private static int ExecuteAsyncApiResponseCallback(");
            var offUiApiResponse = ExtractFunctionBySignature(source, "private static int ExecuteOffUiApiResponseCallback(");

            Assert.Contains("SerializeBimDispatchEnvelope(result)", bimDispatch);
            Assert.Contains("result.Diagnostic", bimEnvelope);
            Assert.Contains("envelope[\"diagnostic\"]", bimEnvelope);

            Assert.DoesNotContain("Diagnostic", apiResponse);
            Assert.DoesNotContain("Diagnostic", asyncApiResponse);
            Assert.DoesNotContain("Diagnostic", offUiApiResponse);
            Assert.DoesNotContain("SerializeBimDispatchEnvelope", apiResponse);
            Assert.DoesNotContain("SerializeBimDispatchEnvelope", asyncApiResponse);
            Assert.DoesNotContain("SerializeBimDispatchEnvelope", offUiApiResponse);
        }

        [Fact]
        public void BimHandler_PreservesRookBimUnavailableAsLegacyDataErrorCodeOnly()
        {
            var source = ReadSourceFile("src", "Rook", "Handlers", "BimHandler.cs");
            var mapErrorCode = ExtractFunctionBySignature(source, "internal static string MapErrorCode(");
            var diagnosticBuilder = ExtractFunctionBySignature(source, "private static JsonObject? BuildDiagnosticForReason(");

            Assert.Contains("\"rookbim_unavailable\"", mapErrorCode);
            Assert.DoesNotContain("\"rookbim_unavailable\"", diagnosticBuilder);
        }

        [Fact]
        public void BimHandler_MapsCoreFallbackRegistrySourceToRuntimeNotActivatedDiagnostic()
        {
            var source = ReadSourceFile("src", "Rook", "Handlers", "BimHandler.cs");
            var helper = ExtractFunctionBySignature(source, "private static string? DiagnosticReasonFromRegistrySource(");

            Assert.Contains("\"core-fallback\"", helper);
            Assert.Contains("\"rookbim_runtime_not_activated\"", helper);
            Assert.Contains("\"module-not-found\"", helper);
            Assert.Contains("\"rookbim_module_not_found\"", helper);
            Assert.Contains("\"module-load-failed\"", helper);
            Assert.Contains("\"rookbim_module_load_failed\"", helper);
        }

        [Fact]
        public void NativeRegistrar_SourceDeclaresBimDispatchCallback()
        {
            var source = ReadSourceFile("src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs");

            // ABI v18 appends solve-readiness callbacks; the BIM dispatch callback must still be
            // declared under the current ABI.
            Assert.Contains("BridgeAbiVersion = 18", source);
            Assert.Contains("BimDispatchCallback = HandleBimDispatch", source);
            Assert.Contains("private static int HandleBimDispatch(", source);
            Assert.Contains("private static int ExecuteBimDispatchCallback(", source);
            Assert.Contains("public IntPtr BimDispatch;", source);
            Assert.Contains("BimDispatch = Marshal.GetFunctionPointerForDelegate(BimDispatchCallback)", source);
        }

        private static JsonElement Diagnostic(ApiResponse response)
        {
            Assert.NotNull(response.Diagnostic);
            return ToJsonElement(response.Diagnostic);
        }

        private static void AssertDiagnostic(
            ApiResponse response,
            string reasonCode,
            string failureKind,
            string ownedBy,
            string evidenceSource,
            string emittedBy,
            string operation)
        {
            var diagnostic = Diagnostic(response);
            Assert.Equal(1, diagnostic.GetProperty("schemaVersion").GetInt32());
            Assert.Equal("bim.rhino_inside_revit", diagnostic.GetProperty("domainId").GetString());
            Assert.Equal(reasonCode, diagnostic.GetProperty("reasonCode").GetString());
            Assert.Equal(failureKind, diagnostic.GetProperty("failureKind").GetString());
            Assert.Equal(ownedBy, diagnostic.GetProperty("ownedBy").GetString());
            Assert.Equal(evidenceSource, diagnostic.GetProperty("evidenceSource").GetString());
            Assert.Equal(emittedBy, diagnostic.GetProperty("emittedBy").GetString());
            Assert.Equal(operation, diagnostic.GetProperty("operation").GetString());
            Assert.Equal("/capabilities", diagnostic.GetProperty("diagnosticRoute").GetProperty("path").GetString());
            Assert.Equal("bim.rhino_inside_revit", diagnostic.GetProperty("diagnosticRoute").GetProperty("domainId").GetString());
            Assert.False(diagnostic.TryGetProperty("state", out _));
        }

        private static JsonElement ToJsonElement(object? value)
        {
            var json = JsonSerializer.Serialize(value);
            using var document = JsonDocument.Parse(json);
            return document.RootElement.Clone();
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = Path.Combine(dir.FullName, Path.Combine(pathParts));
                if (File.Exists(candidate))
                    return File.ReadAllText(candidate);
                dir = dir.Parent;
            }

            throw new FileNotFoundException(
                "Could not locate source file " + string.Join("/", pathParts));
        }

        private static string ExtractFunctionBySignature(string source, string signature)
        {
            var signatureStart = source.IndexOf(signature, StringComparison.Ordinal);
            Assert.True(signatureStart >= 0, $"Could not find signature '{signature}'.");
            var bodyStart = source.IndexOf('{', signatureStart);
            Assert.True(bodyStart >= 0, $"Could not find function body for '{signature}'.");

            var depth = 0;
            for (var i = bodyStart; i < source.Length; i++)
            {
                if (source[i] == '{')
                {
                    depth++;
                }
                else if (source[i] == '}')
                {
                    depth--;
                    if (depth == 0)
                    {
                        return source.Substring(signatureStart, i - signatureStart + 1);
                    }
                }
            }

            throw new InvalidOperationException($"Could not extract function '{signature}'.");
        }

        private sealed class StatusRuntime : IRookBimRuntime
        {
            private readonly string errorCode;
            private readonly string message;

            public StatusRuntime(string errorCode, string message)
            {
                this.errorCode = errorCode;
                this.message = message;
            }

            public BimStatusResponse Status()
            {
                return new BimStatusResponse
                {
                    Available = false,
                    Runtime = "rookbim",
                    ErrorCode = errorCode,
                    Message = message,
                    Host = "unknown",
                    Module = "RookBim.dll"
                };
            }

            public BimApiResponse ActiveDocument() => BimApiResponse.Ok(null);
            public BimApiResponse ListCategories() => BimApiResponse.Ok(null);
            public BimApiResponse QueryElements(BimQueryElementsRequest request) => BimApiResponse.Ok(null);
            public BimApiResponse ElementInfo(BimElementRequest request) => BimApiResponse.Ok(null);
            public BimApiResponse ElementParameters(BimElementRequest request) => BimApiResponse.Ok(null);
            public BimApiResponse SelectElements(BimSelectElementsRequest request) => BimApiResponse.Ok(null);
            public BimApiResponse ClearSelection() => BimApiResponse.Ok(null);
            public BimApiResponse ExportElements(BimExportElementsRequest request) => BimApiResponse.Ok(null);
            public BimApiResponse ExportPreset(BimExportPresetRequest request) => BimApiResponse.Ok(null);
        }

        private sealed class NoActiveDocumentRuntime : IRookBimRuntime
        {
            public BimStatusResponse Status()
            {
                return new BimStatusResponse
                {
                    Available = false,
                    Runtime = "rookbim",
                    ErrorCode = "no_active_document",
                    Message = "RookBIM is connected to Revit, but no active document is open.",
                    Host = "revit",
                    Module = "RookBim.dll"
                };
            }

            public BimApiResponse ActiveDocument()
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NoActiveDocument,
                    "No active Revit document is open.",
                    409);
            }

            public BimApiResponse ListCategories() => BimApiResponse.Ok(null);
            public BimApiResponse QueryElements(BimQueryElementsRequest request) => BimApiResponse.Ok(null);
            public BimApiResponse ElementInfo(BimElementRequest request) => BimApiResponse.Ok(null);
            public BimApiResponse ElementParameters(BimElementRequest request) => BimApiResponse.Ok(null);
            public BimApiResponse SelectElements(BimSelectElementsRequest request) => BimApiResponse.Ok(null);
            public BimApiResponse ClearSelection() => BimApiResponse.Ok(null);
            public BimApiResponse ExportElements(BimExportElementsRequest request) => BimApiResponse.Ok(null);
            public BimApiResponse ExportPreset(BimExportPresetRequest request) => BimApiResponse.Ok(null);
        }

        private sealed class DetailFailureRuntime : IRookBimRuntime
        {
            public BimStatusResponse Status()
            {
                return new BimStatusResponse { Available = true, Runtime = "test" };
            }

            public BimApiResponse ActiveDocument()
            {
                return new BimApiResponse
                {
                    Success = false,
                    ErrorCode = BimErrorCode.DocumentMismatch,
                    Message = "Document changed.",
                    HttpStatus = 409,
                    Data = new JsonObject
                    {
                        ["expectedDocumentGuid"] = "expected-doc",
                    },
                };
            }

            public BimApiResponse ListCategories()
            {
                return BimApiResponse.Ok(new BimListCategoriesResult
                {
                    Source = "document_category_table"
                });
            }

            public BimApiResponse QueryElements(BimQueryElementsRequest request)
            {
                return BimApiResponse.Ok(null);
            }

            public BimApiResponse ElementInfo(BimElementRequest request)
            {
                return BimApiResponse.Ok(null);
            }

            public BimApiResponse ElementParameters(BimElementRequest request)
            {
                return BimApiResponse.Ok(null);
            }

            public BimApiResponse SelectElements(BimSelectElementsRequest request)
            {
                return BimApiResponse.Ok(null);
            }

            public BimApiResponse ClearSelection()
            {
                return BimApiResponse.Ok(null);
            }

            public BimApiResponse ExportElements(BimExportElementsRequest request)
            {
                return BimApiResponse.Ok(null);
            }

            public BimApiResponse ExportPreset(BimExportPresetRequest request)
            {
                return BimApiResponse.Ok(null);
            }
        }

        private sealed class CategoryFailureRuntime : IRookBimRuntime
        {
            public BimStatusResponse Status()
            {
                return new BimStatusResponse { Available = true, Runtime = "test" };
            }

            public BimApiResponse ActiveDocument()
            {
                return BimApiResponse.Ok(null);
            }

            public BimApiResponse ListCategories()
            {
                return BimApiResponse.Ok(new BimListCategoriesResult());
            }

            public BimApiResponse QueryElements(BimQueryElementsRequest request)
            {
                var response = BimApiResponse.Fail(
                    BimErrorCode.InvalidCategory,
                    "Unknown Revit category 'Pipe Accessoryz'.",
                    400);
                response.Data = new
                {
                    resolution = new BimCategoryResolution
                    {
                        Status = BimCategoryResolutionStatus.Invalid,
                        Input = "Pipe Accessoryz",
                        NormalizedInput = "pipeaccessoryz"
                    }
                };
                return response;
            }

            public BimApiResponse ElementInfo(BimElementRequest request)
            {
                return BimApiResponse.Ok(null);
            }

            public BimApiResponse ElementParameters(BimElementRequest request)
            {
                return BimApiResponse.Ok(null);
            }

            public BimApiResponse SelectElements(BimSelectElementsRequest request)
            {
                return BimApiResponse.Ok(null);
            }

            public BimApiResponse ClearSelection()
            {
                return BimApiResponse.Ok(null);
            }

            public BimApiResponse ExportElements(BimExportElementsRequest request)
            {
                return BimApiResponse.Ok(null);
            }

            public BimApiResponse ExportPreset(BimExportPresetRequest request)
            {
                return BimApiResponse.Ok(null);
            }
        }
    }
}
