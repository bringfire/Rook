using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook.Bim;
using Rook.Handlers;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class BimHandlerTests
    {
        private static readonly string[] Phase1Ops =
        {
            "status",
            "active_document",
            "query_elements",
            "element_info",
            "element_parameters",
            "select_elements",
            "clear_selection",
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
        public void NativeRegistrar_SourceDeclaresBimDispatchCallback()
        {
            var source = ReadSourceFile("src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs");

            Assert.Contains("BridgeAbiVersion = 15", source);
            Assert.Contains("BimDispatchCallback = HandleBimDispatch", source);
            Assert.Contains("private static int HandleBimDispatch(", source);
            Assert.Contains("private static int ExecuteBimDispatchCallback(", source);
            Assert.Contains("public IntPtr BimDispatch;", source);
            Assert.Contains("BimDispatch = Marshal.GetFunctionPointerForDelegate(BimDispatchCallback)", source);
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
        }
    }
}
