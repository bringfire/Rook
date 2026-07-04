using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class NativeBimDispatchSourceTests
    {
        [Theory]
        [InlineData("Get", "/bim/status", "HandleBimStatus", "status")]
        [InlineData("Get", "/bim/active-document", "HandleBimActiveDocument", "active_document")]
        [InlineData("Get", "/bim/categories", "HandleBimCategories", "list_categories")]
        [InlineData("Post", "/bim/query-elements", "HandleBimQueryElements", "query_elements")]
        [InlineData("Post", "/bim/element-info", "HandleBimElementInfo", "element_info")]
        [InlineData("Post", "/bim/element-parameters", "HandleBimElementParameters", "element_parameters")]
        [InlineData("Post", "/bim/select-elements", "HandleBimSelectElements", "select_elements")]
        [InlineData("Post", "/bim/clear-selection", "HandleBimClearSelection", "clear_selection")]
        [InlineData("Post", "/bim/export-elements", "HandleBimExportElements", "export_elements")]
        public void RookServer_RegistersBimRoutesWithCanonicalOps(
            string method,
            string route,
            string handlerName,
            string op)
        {
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            var proxySource = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
            var handler = ExtractFunction(proxySource, handlerName);

            Assert.Contains($"m_server->{method}(\"{route}\"", source);
            Assert.Contains($"Rook::Handlers::{handlerName}", source);
            Assert.Contains($"ForwardBimDispatch(req, res, \"{HttpVerb(method)} {route}\", \"{op}\"", handler);
        }

        [Fact]
        public void RookServer_BimRoutesInjectOpAndForwardOpaqueJson()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
            var helper = ExtractFunction(source, "ForwardBimDispatch");

            Assert.Contains("body[\"op\"] = op;", helper);
            Assert.Contains("InvokeBimDispatchWithBody(body.dump(), responseJson, statusCode, error)", helper);
            Assert.DoesNotContain("HandleBimDispatch", helper);
            Assert.DoesNotContain("BimHandler", helper);
        }

        [Fact]
        public void RookServer_BimRoutesRejectInvalidPostJsonWithOpHeader()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
            var helper = ExtractFunction(source, "ParseBimPostBody");

            Assert.Contains("if (req.body.empty())", helper);
            Assert.Contains("body = nlohmann::json::object();", helper);
            Assert.Contains("body.is_object()", helper);
            Assert.Contains("res.set_header(\"X-Rook-Bim-Op\", op);", helper);
            Assert.Contains("400,", helper);
            Assert.Contains("\"invalid_scope\"", helper);
        }

        [Fact]
        public void RookServer_BimDispatchErrorsUseStructuredDataEnvelope()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
            var helper = ExtractFunction(source, "SendBimDispatchError");

            Assert.Contains("const std::string& errorCode", helper);
            Assert.Contains("data[\"errorCode\"] = errorCode;", helper);
            Assert.Contains("data[\"message\"] = message;", helper);
            Assert.Contains("envelope[\"data\"] = data;", helper);
            Assert.DoesNotContain("envelope[\"data\"] = message;", helper);
        }

        [Fact]
        public void RookServer_BimDispatchErrorCallSitesUseStableErrorCodes()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
            var parseHelper = ExtractFunction(source, "ParseBimPostBody");
            var forwardHelper = ExtractFunction(source, "ForwardBimDispatch");

            Assert.Contains("\"invalid_scope\"", parseHelper);
            Assert.Contains("\"rookbim_unavailable\"", forwardHelper);
            Assert.Contains("\"internal_error\"", forwardHelper);
        }

        [Fact]
        public void RookServer_BimUnavailableBranchAddsDiagnosticAndPreservesLegacyTransport()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
            var forward = ExtractFunction(source, "ForwardBimDispatch");
            var sendError = ExtractFunction(source, "SendBimDispatchError");

            Assert.Contains("BuildBimDispatchCallbackUnavailable(route, op)", forward);
            Assert.Contains("ManagedCreateInvokeResult::Unavailable", forward);
            Assert.Contains("\"rookbim_unavailable\"", forward);
            Assert.Contains("503,", forward);
            Assert.Contains("&diagnostic", forward);
            Assert.Contains("envelope[\"diagnostic\"] = *diagnostic;", sendError);
            Assert.Contains("res.set_header(\"X-Rook-Bim-Op\", op);", sendError);
        }

        [Fact]
        public void RookServer_BimFailedAndParseBranchesRemainLegacyLocal()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
            var forward = ExtractFunction(source, "ForwardBimDispatch");
            var parse = ExtractFunction(source, "ParseBimPostBody");

            var failedBranchStart = forward.IndexOf("case ManagedCreateInvokeResult::Failed:", StringComparison.Ordinal);
            Assert.True(failedBranchStart >= 0, "ForwardBimDispatch must keep a Failed branch.");
            var failedBranch = forward.Substring(failedBranchStart);

            Assert.Contains("\"internal_error\"", failedBranch);
            Assert.DoesNotContain("BuildBimDispatchCallbackUnavailable", failedBranch);
            Assert.DoesNotContain("SendErrorWithDiagnostic", failedBranch);
            Assert.DoesNotContain("SendErrorDataWithDiagnostic", failedBranch);

            Assert.Contains("\"invalid_scope\"", parse);
            Assert.DoesNotContain("BuildBimDispatchCallbackUnavailable", parse);
            Assert.DoesNotContain("SendErrorWithDiagnostic", parse);
            Assert.DoesNotContain("SendErrorDataWithDiagnostic", parse);
        }

        [Fact]
        public void RookServer_BimSuccessDispatchRemainsOpaquePassThrough()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
            var forward = ExtractFunction(source, "ForwardBimDispatch");

            var okBranchStart = forward.IndexOf("case ManagedCreateInvokeResult::Ok:", StringComparison.Ordinal);
            var unavailableBranchStart = forward.IndexOf("case ManagedCreateInvokeResult::Unavailable:", StringComparison.Ordinal);
            Assert.True(okBranchStart >= 0, "ForwardBimDispatch must keep an Ok branch.");
            Assert.True(unavailableBranchStart > okBranchStart, "Unavailable branch must follow Ok branch.");
            var okBranch = forward.Substring(okBranchStart, unavailableBranchStart - okBranchStart);

            Assert.Contains("res.status = statusCode;", okBranch);
            Assert.Contains("res.set_content(responseJson, \"application/json\");", okBranch);
            Assert.Contains("res.set_header(\"X-Rook-Bim-Op\", op);", okBranch);
            Assert.DoesNotContain("nlohmann::json::parse", okBranch);
            Assert.DoesNotContain("data.errorCode", okBranch);
            Assert.DoesNotContain("BuildBim", okBranch);
        }

        [Fact]
        public void RookServer_ErrorHandlerDoesNotOverwriteStructuredRoute404Bodies()
        {
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            var handler = ExtractLambdaBody(source, "set_error_handler");

            Assert.Contains("res.body.empty()", handler);
            Assert.Contains("Unknown endpoint", handler);
        }

        [Fact]
        public void NativeBimSources_DoNotExposeForbiddenRoutesOrApiReferences()
        {
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            source += ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.h");
            source += ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");

            Assert.DoesNotContain("/revit", source, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("/rhino/bim", source, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("/rookbim", source, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("Autodesk.", source, StringComparison.Ordinal);
            Assert.DoesNotContain("RevitAPI", source, StringComparison.Ordinal);
            Assert.DoesNotContain("RhinoInside.Revit", source, StringComparison.Ordinal);
        }

        [Fact]
        public void NativeBridge_DeclaresBimDispatchSlotUnderCurrentAbi()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");

            // ABI tracks the current bridge contract; it was bumped to 17 by the CanvasDirector
            // dispatch slot. The BIM dispatch slot must remain declared under that ABI.
            Assert.Contains("kGhBridgeAbiVersion = 17", source);
            Assert.Contains("GhBridgeCallbackFn vision_dispatch = nullptr;", source);
            Assert.Contains("GhBridgeCallbackFn canvas_director_dispatch = nullptr;", source);
            Assert.Contains("GhBridgeCallbackFn bim_dispatch = nullptr;", source);
            Assert.Contains("registration.bim_dispatch != nullptr", source);
            Assert.Contains("InvokeBimDispatchWithBody", source);
            Assert.Contains("\"BIM dispatch callback is not registered.\"", source);
        }

        [Fact]
        public void ManagedBridge_RegistersBimDispatchSlotUnderCurrentAbi()
        {
            var source = ReadSourceFile("src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs");

            Assert.Contains("BridgeAbiVersion = 17", source);
            Assert.Contains("public IntPtr VisionDispatch;", source);
            Assert.Contains("public IntPtr CanvasDirectorDispatch;", source);
            Assert.Contains("public IntPtr BimDispatch;", source);
            Assert.Contains("CanvasDirectorDispatch = Marshal.GetFunctionPointerForDelegate(CanvasDirectorDispatchCallback)", source);
            Assert.Contains("BimDispatch = Marshal.GetFunctionPointerForDelegate(BimDispatchCallback)", source);
            Assert.Contains("BimDispatchCallback = HandleBimDispatch", source);
        }

        [Fact]
        public void RookNative_StartsCompanionDeferredLoadInRhinoInsideForBimBridge()
        {
            var source = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
            var onLoad = ExtractFunction(source, "CRookNativePlugin::OnLoadPlugIn");

            Assert.Contains("StartCompanionLoadDeferred();", onLoad);
            Assert.DoesNotContain("skipping companion deferred load", onLoad);
            Assert.DoesNotContain("companion will register via its own startup hooks if loaded", onLoad);
        }

        private static string ExtractFunction(string source, string functionName)
        {
            var signatureStart = source.IndexOf(functionName + "(", StringComparison.Ordinal);
            if (signatureStart < 0)
                throw new InvalidOperationException("Function not found: " + functionName);

            while (signatureStart > 0 && source[signatureStart - 1] != '\n')
                signatureStart--;

            var bodyStart = source.IndexOf('{', signatureStart);
            if (bodyStart < 0)
                throw new InvalidOperationException("Function body not found: " + functionName);

            var depth = 0;
            for (var i = bodyStart; i < source.Length; i++)
            {
                if (source[i] == '{') depth++;
                else if (source[i] == '}')
                {
                    depth--;
                    if (depth == 0)
                        return source.Substring(signatureStart, i - signatureStart + 1);
                }
            }

            throw new InvalidOperationException("Function body did not close: " + functionName);
        }

        private static string ExtractLambdaBody(string source, string marker)
        {
            var markerIndex = source.IndexOf(marker, StringComparison.Ordinal);
            if (markerIndex < 0)
                throw new InvalidOperationException("Marker not found: " + marker);

            var bodyStart = source.IndexOf('{', markerIndex);
            if (bodyStart < 0)
                throw new InvalidOperationException("Lambda body not found: " + marker);

            var depth = 0;
            for (var i = bodyStart; i < source.Length; i++)
            {
                if (source[i] == '{') depth++;
                else if (source[i] == '}')
                {
                    depth--;
                    if (depth == 0)
                        return source.Substring(bodyStart, i - bodyStart + 1);
                }
            }

            throw new InvalidOperationException("Lambda body did not close: " + marker);
        }

        private static string HttpVerb(string method) =>
            string.Equals(method, "Get", StringComparison.Ordinal) ? "GET" : "POST";

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
    }
}
