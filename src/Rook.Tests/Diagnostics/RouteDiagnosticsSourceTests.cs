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
        public void SliceOne_DoesNotAdoptDiagnosticsAcrossAllVisionRoutes()
        {
            var visionSource = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
            var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");
            var catalogAndSource = visionSource + header;

            Assert.Single(FindAll(visionSource, "BuildVisionDispatchCallbackUnavailable("));
            Assert.DoesNotContain("viewport_capture_callback_unavailable", catalogAndSource);
            Assert.DoesNotContain("block_mutation_callback_unavailable", catalogAndSource);
            Assert.DoesNotContain("bim_dispatch_callback_unavailable", catalogAndSource);
            Assert.DoesNotContain("gh_bridge_callback_unavailable", catalogAndSource);
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
