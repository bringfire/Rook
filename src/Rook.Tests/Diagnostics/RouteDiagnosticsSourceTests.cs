using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Diagnostics
{
    public class RouteDiagnosticsSourceTests
    {
        [Fact]
        public void RouteDiagnosticsHelper_DefinesFixedFailureKindEnumAndDiagnosticShape()
        {
            var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");

            Assert.Contains("enum class FailureKind", header);
            Assert.Contains("DomainUnavailable", header);
            Assert.Contains("HostBlocked", header);
            Assert.Contains("DependencyUnavailable", header);
            Assert.Contains("DependencyDegraded", header);
            Assert.Contains("OperationUnavailable", header);
            Assert.Contains("ConfigurationRequired", header);
            Assert.Contains("AuthorizationRequired", header);
            Assert.Contains("Unknown", header);

            Assert.Contains("\"schemaVersion\"", header);
            Assert.Contains("\"domainId\"", header);
            Assert.Contains("\"route\"", header);
            Assert.Contains("\"operation\"", header);
            Assert.Contains("\"reasonCode\"", header);
            Assert.Contains("\"failureKind\"", header);
            Assert.Contains("\"retryable\"", header);
            Assert.Contains("\"userActionRequired\"", header);
            Assert.Contains("\"diagnosticRoute\"", header);
            Assert.Contains("\"recommendedNextStep\"", header);
            Assert.Contains("\"method\"", header);
            Assert.Contains("\"path\"", header);
            Assert.Contains("\"domainId\"", header);
        }

        [Fact]
        public void RouteDiagnosticsHelper_TracksCatalogMetadataForSliceOneReasonCode()
        {
            var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");

            Assert.Contains("BuildVisionDispatchCallbackUnavailable", header);
            Assert.Contains("\"vision_dispatch_callback_unavailable\"", header);
            Assert.Contains("\"vision.media\"", header);
            Assert.Contains("\"ownedBy\"", header);
            Assert.Contains("\"native\"", header);
            Assert.Contains("\"evidenceSource\"", header);
            Assert.Contains("\"native_callback_registration\"", header);
            Assert.Contains("\"emittedBy\"", header);
            Assert.Contains("\"native_route\"", header);
            Assert.Contains("\"/capabilities\"", header);
        }

        [Fact]
        public void ViewportCaptureCallbackUnavailableDiagnostic_UsesReviewedCatalogMetadata()
        {
            var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");
            var helper = ExtractFunction(header, "BuildViewportCaptureCallbackUnavailable");

            Assert.Contains("\"viewport.capture\"", helper);
            Assert.Contains("\"viewport_capture_callback_unavailable\"", helper);
            Assert.Contains("FailureKind::DomainUnavailable", helper);
            Assert.Contains("\"native\"", helper);
            Assert.Contains("\"native_callback_registration\"", helper);
            Assert.Contains("\"native_route\"", helper);
            Assert.Contains("\"not_loaded\"", helper);
            Assert.Contains("diagnostic.retryable = true;", helper);
            Assert.Contains("diagnostic.userActionRequired = false;", helper);
        }

        [Fact]
        public void BlockMutationProxyDiagnostics_UseReviewedCatalogMetadata()
        {
            var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");
            var unavailable = ExtractFunction(header, "BuildBlockMutationManagedProxyUnavailable");
            var forwardFailed = ExtractFunction(header, "BuildBlockMutationManagedProxyForwardFailed");

            Assert.Contains("\"block.definition_mutation\"", unavailable);
            Assert.Contains("\"block_mutation_managed_proxy_unavailable\"", unavailable);
            Assert.Contains("FailureKind::DependencyUnavailable", unavailable);
            Assert.Contains("\"native\"", unavailable);
            Assert.Contains("\"native_managed_proxy_discovery\"", unavailable);
            Assert.Contains("\"native_route\"", unavailable);
            Assert.Contains("diagnostic.retryable = true;", unavailable);
            Assert.Contains("diagnostic.userActionRequired = false;", unavailable);
            Assert.DoesNotContain("diagnostic.state", unavailable);

            Assert.Contains("\"block.definition_mutation\"", forwardFailed);
            Assert.Contains("\"block_mutation_managed_proxy_forward_failed\"", forwardFailed);
            Assert.Contains("FailureKind::DependencyDegraded", forwardFailed);
            Assert.Contains("\"native\"", forwardFailed);
            Assert.Contains("\"native_managed_proxy_transport\"", forwardFailed);
            Assert.Contains("\"native_route\"", forwardFailed);
            Assert.Contains("diagnostic.retryable = true;", forwardFailed);
            Assert.Contains("diagnostic.userActionRequired = false;", forwardFailed);
            Assert.DoesNotContain("diagnostic.state", forwardFailed);
        }

        [Fact]
        public void BimDispatchCallbackUnavailableDiagnostic_UsesReviewedCatalogMetadata()
        {
            var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");
            var helper = ExtractFunction(header, "BuildBimDispatchCallbackUnavailable");

            Assert.Contains("\"bim.rhino_inside_revit\"", helper);
            Assert.Contains("\"bim_dispatch_callback_unavailable\"", helper);
            Assert.Contains("FailureKind::DomainUnavailable", helper);
            Assert.Contains("\"native\"", helper);
            Assert.Contains("\"native_callback_registration\"", helper);
            Assert.Contains("\"native_route\"", helper);
            Assert.Contains("\"not_loaded\"", helper);
            Assert.Contains("diagnostic.retryable = true;", helper);
            Assert.Contains("diagnostic.userActionRequired = false;", helper);
        }

        [Fact]
        public void RouteDiagnosticsHelper_KeepsSchemaVersionIndependentFromCapabilitiesSchema()
        {
            var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");
            var serverSource = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            var capabilitiesDocument = ExtractFunction(serverSource, "BuildRookCapabilitiesDocument");

            Assert.Contains("kRouteDiagnosticSchemaVersion = 1", header);
            Assert.DoesNotContain("kRouteDiagnosticSchemaVersion", capabilitiesDocument);
        }

        [Fact]
        public void RookServer_AddsDiagnosticAsTopLevelSiblingWithoutReplacingLegacyData()
        {
            var header = ReadSourceFile("src", "RookNative", "RookServer.h");
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            var stringHelper = ExtractFunction(source, "CRookServer::SendErrorWithDiagnostic");
            var structuredDataHelper = ExtractFunction(source, "CRookServer::SendErrorDataWithDiagnostic");

            Assert.Contains("SendErrorWithDiagnostic", header);
            Assert.Contains("SendErrorDataWithDiagnostic", header);
            Assert.Equal(1, CountOccurrences(header, "static void SendErrorWithDiagnostic("));
            Assert.Equal(1, CountOccurrences(source, "void CRookServer::SendErrorWithDiagnostic("));
            Assert.Contains("envelope[\"success\"] = false;", stringHelper);
            Assert.Contains("envelope[\"data\"] = message;", stringHelper);
            Assert.Contains("envelope[\"diagnostic\"] = diagnostic;", stringHelper);
            Assert.DoesNotContain("envelope[\"data\"] = diagnostic;", stringHelper);
            Assert.DoesNotContain("legacyMessage", stringHelper);

            Assert.Contains("envelope[\"success\"] = false;", structuredDataHelper);
            Assert.Contains("envelope[\"data\"] = data;", structuredDataHelper);
            Assert.Contains("envelope[\"diagnostic\"] = diagnostic;", structuredDataHelper);
            Assert.DoesNotContain("envelope[\"data\"] = diagnostic;", structuredDataHelper);
        }

        [Fact]
        public void RouteDiagnostics_DoNotIntroduceProjectFileOrBroadArchitectureChanges()
        {
            var project = ReadSourceFile("src", "RookNative", "RookNative.vcxproj");
            var filters = ReadSourceFile("src", "RookNative", "RookNative.vcxproj.filters");
            var nativePlugin = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
            var serverSource = ReadSourceFile("src", "RookNative", "RookServer.cpp");

            Assert.DoesNotContain("RouteDiagnostics.cpp", project);
            Assert.DoesNotContain("RouteDiagnostics.cpp", filters);
            Assert.DoesNotContain("installed-modules.json", serverSource);
            Assert.Contains("StartCompanionLoadDeferred();", nativePlugin);
            Assert.DoesNotContain("DispatchPolicy::CommandControl", ExtractFunction(nativePlugin, "StartCompanionLoadDeferred"));
        }

        [Fact]
        public void RouteDiagnosticReasonCodes_DoNotUseBroadFallbackCodesAsCatalogEntries()
        {
            var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");

            Assert.DoesNotContain("\"bridge_unavailable\"", header);
            Assert.DoesNotContain("\"plugin_not_ready\"", header);
            Assert.DoesNotContain("\"service_failed\"", header);
            Assert.DoesNotContain("\"not_available\"", header);
            Assert.DoesNotContain("\"managed_dependency_unavailable\"", header);
        }

        [Fact]
        public void NativeSources_DoNotUseCapabilitiesAsGenericRoutePreflight()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
            var helper = ExtractFunction(source, "ForwardVisionDispatch");

            Assert.DoesNotContain("BuildRookCapabilitiesDocument", helper);
            Assert.DoesNotContain("HandleCapabilities", helper);
            Assert.DoesNotContain("/capabilities", helper);
        }

        [Fact]
        public void RouteDiagnostics_DoNotMintUnsafeCallbackBimOrGhReasonCodes()
        {
            var visionSource = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
            var viewportSource = ReadSourceFile("src", "RookNative", "Handlers", "ViewportHandler.cpp");
            var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");
            var catalogAndSource = visionSource + viewportSource + header;

            Assert.Contains("vision_dispatch_callback_unavailable", catalogAndSource);
            Assert.Contains("viewport_capture_callback_unavailable", catalogAndSource);
            Assert.Contains("bim_dispatch_callback_unavailable", catalogAndSource);
            Assert.DoesNotContain("block_mutation_callback_unavailable", catalogAndSource);
            Assert.DoesNotContain("gh_bridge_callback_unavailable", catalogAndSource);
            Assert.DoesNotContain("\"bim_unavailable\"", catalogAndSource);
            Assert.DoesNotContain("\"bridge_unavailable\"", catalogAndSource);
            Assert.DoesNotContain("\"managed_dependency_unavailable\"", catalogAndSource);
        }

        [Fact]
        public void Phase2C_DoesNotIntroduceBroadOrAliasBimDiagnosticReasonCodes()
        {
            var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");
            var bimHandler = ReadSourceFile("src", "Rook", "Handlers", "BimHandler.cs");
            var nativeBim = ExtractFunction(header, "BuildBimDispatchCallbackUnavailable");
            var managedBim = ExtractFunctionBySignature(
                bimHandler,
                "private static JsonObject? BuildDiagnosticForReason(");
            var catalog = nativeBim + managedBim;

            Assert.DoesNotContain("\"rookbim_unavailable\"", catalog);
            Assert.DoesNotContain("\"bim_unavailable\"", catalog);
            Assert.DoesNotContain("\"bridge_unavailable\"", catalog);
            Assert.DoesNotContain("\"managed_dependency_unavailable\"", catalog);
            Assert.DoesNotContain("\"rookbim_module_not_activated\"", catalog);
            Assert.DoesNotContain("\"no_active_revit_document\"", catalog);
            Assert.DoesNotContain("\"missing_revit_api\"", catalog);
        }

        [Fact]
        public void BlockMutationDiagnostics_DoNotBypassManagedProxyFallbackWithOptionalContext()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
            var helper = ExtractFunction(source, "DispatchManagedCompanionRouteOrProxy");

            Assert.Contains("const ProxyDiagnosticContext* diagnosticContext", helper);
            Assert.Contains("callback != nullptr", helper);
            Assert.Contains("DispatchGrasshopperRoute(req, res, path, callback);", helper);
            Assert.Contains("ProxyManagedRequest(req, res, path, isPost", helper);
            Assert.Contains("ProxyManagedRequest(req, res, path, isPost, diagnosticContext);", helper);

            var callbackIndex = helper.IndexOf("DispatchGrasshopperRoute(req, res, path, callback);", StringComparison.Ordinal);
            var proxyIndex = helper.IndexOf("ProxyManagedRequest(req, res, path, isPost", StringComparison.Ordinal);
            Assert.True(callbackIndex >= 0, "Callback dispatch branch must remain present.");
            Assert.True(proxyIndex > callbackIndex, "Managed proxy fallback must remain after callback selection.");

            var beforeProxy = helper.Substring(0, proxyIndex);
            Assert.DoesNotContain("SendErrorWithDiagnostic", beforeProxy);
            Assert.DoesNotContain("SendErrorDataWithDiagnostic", beforeProxy);
        }

        [Theory]
        [InlineData("HandleManagedBlockSetLayers", "\"/block/set-layers\"")]
        [InlineData("HandleManagedBlockSetLayersBatch", "\"/block/set-layers-batch\"")]
        [InlineData("HandleManagedBlockSetMaterials", "\"/block/set-materials\"")]
        [InlineData("HandleManagedBlockSetMaterialsBatch", "\"/block/set-materials-batch\"")]
        [InlineData("HandleManagedBlockSetObjectColors", "\"/block/set-object-colors\"")]
        [InlineData("HandleManagedBlockSetObjectColorsBatch", "\"/block/set-object-colors-batch\"")]
        [InlineData("HandleManagedBlockSetObjectNames", "\"/block/set-object-names\"")]
        [InlineData("HandleManagedBlockSetObjectNamesBatch", "\"/block/set-object-names-batch\"")]
        [InlineData("HandleManagedBlockSetObjectUserStrings", "\"/block/set-object-user-strings\"")]
        [InlineData("HandleManagedBlockSetObjectUserStringsBatch", "\"/block/set-object-user-strings-batch\"")]
        [InlineData("HandleManagedBlockReplaceObjectGeometry", "\"/block/replace-object-geometry\"")]
        [InlineData("HandleManagedBlockReplaceObjectGeometryBatch", "\"/block/replace-object-geometry-batch\"")]
        [InlineData("HandleManagedBlockTransformObject", "\"/block/transform-object\"")]
        [InlineData("HandleManagedBlockTransformObjectBatch", "\"/block/transform-object-batch\"")]
        public void BlockMutationHandlers_KeepManagedProxyFallbackOwnership(string handlerName, string route)
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
            var handler = ExtractFunction(source, handlerName);

            Assert.Contains("BuildBlockMutationProxyDiagnosticContext(", handler);
            Assert.Contains("DispatchManagedCompanionRouteOrProxy(req, res,", handler);
            Assert.Contains(route, handler);
            Assert.Contains("&diagnosticContext", handler);
            Assert.DoesNotContain("SendErrorWithDiagnostic", handler);
            Assert.DoesNotContain("SendErrorDataWithDiagnostic", handler);
        }

        [Fact]
        public void BlockMutationDiagnostics_OnlyBlockHandlersPassDiagnosticContext()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");

            Assert.Contains("struct ProxyDiagnosticContext", source);
            Assert.Contains("BuildBlockMutationProxyDiagnosticContext", source);

            var uvPlanar = ExtractFunction(source, "HandleManagedUvPlanar");
            var gameExport = ExtractFunction(source, "HandleManagedGameExportPrepare");
            var proxyCompanion = ExtractFunction(source, "ProxyManagedCompanionRequest");
            var transformInstanceBatch = ExtractFunction(source, "HandleManagedBlockTransformInstanceBatch");

            Assert.DoesNotContain("BuildBlockMutationProxyDiagnosticContext", uvPlanar);
            Assert.DoesNotContain("&diagnosticContext", uvPlanar);
            Assert.DoesNotContain("BuildBlockMutationProxyDiagnosticContext", gameExport);
            Assert.DoesNotContain("&diagnosticContext", gameExport);
            Assert.DoesNotContain("BuildBlockMutationProxyDiagnosticContext", proxyCompanion);
            Assert.DoesNotContain("&diagnosticContext", proxyCompanion);
            Assert.Contains("DispatchManagedCompanionRouteOrProxy(req, res,", transformInstanceBatch);
            Assert.Contains("\"/block/transform-instance-batch\"", transformInstanceBatch);
            Assert.DoesNotContain("BuildBlockMutationProxyDiagnosticContext", transformInstanceBatch);
            Assert.DoesNotContain("&diagnosticContext", transformInstanceBatch);
        }

        [Fact]
        public void NonBlockProxyFailures_KeepLegacyEnvelopeWhenContextAbsent()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
            var proxyCompanion = ExtractFunction(source, "ProxyManagedCompanionRequest");
            var normalized = source.Replace("\r\n", "\n");
            const string marker =
                "void SendProxyFailure(\n" +
                "    httplib::Response& res,\n" +
                "    int status,\n" +
                "    const std::string& message,\n" +
                "    const nlohmann::json* diagnostic)\n" +
                "{";
            var start = normalized.IndexOf(marker, StringComparison.Ordinal);
            Assert.True(start >= 0, "SendProxyFailure implementation must use the reviewed diagnostic-aware signature.");
            var end = normalized.IndexOf("\nvoid CopyManagedResponse", start, StringComparison.Ordinal);
            Assert.True(end > start, "SendProxyFailure implementation must remain before CopyManagedResponse.");
            var sendProxyFailure = normalized.Substring(start, end - start);

            Assert.Contains("if (diagnostic != nullptr)", sendProxyFailure);
            Assert.Contains("CRookServer::SendErrorWithDiagnostic(res, message, *diagnostic);", sendProxyFailure);
            Assert.Contains("envelope[\"success\"] = false;", sendProxyFailure);
            Assert.Contains("envelope[\"data\"] = message;", sendProxyFailure);
            Assert.Contains("res.status = status;", sendProxyFailure);
            Assert.Contains("res.set_content(envelope.dump(), \"application/json\");", sendProxyFailure);

            Assert.Contains("ProxyManagedRequest(req, res, path, isPost);", proxyCompanion);
            Assert.DoesNotContain("&diagnosticContext", proxyCompanion);
        }

        [Fact]
        public void ManagedBlockHandlers_DoNotMintPhase2BReasonCodes()
        {
            var blocks = ReadSourceFile("src", "Rook", "Handlers", "BlocksHandler.cs");

            Assert.DoesNotContain("block_mutation_managed_proxy_unavailable", blocks);
            Assert.DoesNotContain("block_mutation_managed_proxy_forward_failed", blocks);
            Assert.DoesNotContain("RouteDiagnostic", blocks);
            Assert.Contains("new ApiResponse { Success = false, Data =", blocks);
        }

        [Fact]
        public void BlockMutationDiagnostics_DoNotInspectSuccessfulManagedProxyResponses()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
            var forward = ExtractFunction(source, "TryForwardGrasshopperRequest");

            Assert.Contains("res.status = statusCode;", forward);
            Assert.Contains("res.set_content(responseBody, contentType.empty() ? \"application/json\" : contentType.c_str());", forward);

            Assert.DoesNotContain("SendErrorWithDiagnostic", forward);
            Assert.DoesNotContain("SendErrorDataWithDiagnostic", forward);
            Assert.DoesNotContain("BuildBlockMutationManagedProxyUnavailable", forward);
            Assert.DoesNotContain("BuildBlockMutationManagedProxyForwardFailed", forward);
            Assert.DoesNotContain("nlohmann::json::parse", forward);
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

        private static string ExtractFunctionBySignature(string source, string signature)
        {
            var signatureStart = source.IndexOf(signature, StringComparison.Ordinal);
            if (signatureStart < 0)
                throw new InvalidOperationException("Function not found: " + signature);

            var bodyStart = source.IndexOf('{', signatureStart);
            if (bodyStart < 0)
                throw new InvalidOperationException("Function body not found: " + signature);

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

            throw new InvalidOperationException("Function body did not close: " + signature);
        }

        private static int CountOccurrences(string source, string value)
        {
            var count = 0;
            var index = 0;
            while ((index = source.IndexOf(value, index, StringComparison.Ordinal)) >= 0)
            {
                count++;
                index += value.Length;
            }

            return count;
        }

        private static string[] FindAll(string source, string needle)
        {
            var matches = new System.Collections.Generic.List<string>();
            var index = 0;
            while (true)
            {
                index = source.IndexOf(needle, index, StringComparison.Ordinal);
                if (index < 0)
                    return matches.ToArray();
                matches.Add(needle);
                index += needle.Length;
            }
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
    }
}
