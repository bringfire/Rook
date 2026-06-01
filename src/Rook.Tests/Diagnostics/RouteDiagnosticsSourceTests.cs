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
            var helper = ExtractFunction(source, "CRookServer::SendErrorWithDiagnostic");

            Assert.Contains("SendErrorWithDiagnostic", header);
            Assert.Contains("envelope[\"success\"] = false;", helper);
            Assert.Contains("envelope[\"data\"] = message;", helper);
            Assert.Contains("envelope[\"diagnostic\"] = diagnostic;", helper);
            Assert.DoesNotContain("envelope[\"data\"] = diagnostic;", helper);
            Assert.DoesNotContain("legacyMessage", helper);
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
