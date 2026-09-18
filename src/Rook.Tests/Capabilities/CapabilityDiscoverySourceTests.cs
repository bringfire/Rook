using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Capabilities
{
    public class CapabilityDiscoverySourceTests
    {
        private static readonly string[] RequiredDomains =
        {
            "native.core",
            "native.command_control",
            "gh.bridge",
            "gh.canvas",
            "bim.rhino_inside_revit",
            "chat.ui",
            "vision.media",
            "viewport.capture",
            "block.definition_mutation",
            "mcp.runtime",
            "knowledge.stores",
            "chirp.runtime",
            "licensing.entitlement",
        };

        [Fact]
        public void RookServer_RegistersPublicCapabilitiesRouteOnNativeServer()
        {
            var header = ReadSourceFile("src", "RookNative", "RookServer.h");
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");

            Assert.Contains("void HandleCapabilities(const httplib::Request& req, httplib::Response& res);", header);
            var routeRegistration = ExtractRouteRegistration(source, "m_server->Get(\"/capabilities\"");
            Assert.Contains("HandleCapabilities(req, res);", routeRegistration);
        }

        [Fact]
        public void CapabilityDocument_ContainsRequiredDomainsAndSchemaFields()
        {
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            var capabilityBuilder = ExtractFunction(source, "BuildRookCapabilitiesDocument");

            Assert.Contains("schemaVersion", source);
            Assert.Contains("generatedUtc", source);
            Assert.Contains("domains", source);
            Assert.Contains("domainId", source);
            Assert.Contains("declared", source);
            Assert.Contains("installed", source);
            Assert.Contains("state", source);
            Assert.Contains("stateSource", source);
            Assert.Contains("reasonCode", source);
            Assert.Contains("evidence", source);
            Assert.Contains("companionEvidence", source);
            Assert.Contains("CompanionEvidenceFor(companionStatus", capabilityBuilder);

            foreach (var domain in RequiredDomains)
            {
                Assert.Contains(domain, capabilityBuilder);
            }
        }

        [Fact]
        public void CapabilityRoute_DoesNotAddPublicManagedCapabilitiesServerExport()
        {
            AssertNoCapabilitiesServerExport(ReadSourceFile("src", "RookNative", "RookServer.cpp"));
            AssertNoCapabilitiesServerExport(ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp"));
            AssertNoCapabilitiesServerExport(ReadSourceFile("src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs"));
        }

        [Fact]
        public void Discovery_KeepsLegacyGhCapabilityFieldsAndAddsDomainSummary()
        {
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            var writeDiscovery = ExtractFunction(source, "CRookServer::WriteDiscoveryFile");

            Assert.Contains("\"ghProvider\"", writeDiscovery);
            Assert.Contains("\"ghRoutes\"", writeDiscovery);
            Assert.Contains("\"domainSummary\"", writeDiscovery);
            Assert.Contains("\"liveEndpoint\"", writeDiscovery);
            Assert.Contains("\"/capabilities\"", writeDiscovery);
            Assert.Contains("\"summaryKind\"", writeDiscovery);
            Assert.Contains("\"bootstrap_snapshot\"", writeDiscovery);
            Assert.Contains("\"authoritative\"", writeDiscovery);
            Assert.Contains("false", writeDiscovery);
            Assert.Contains("\"generatedUtc\"", writeDiscovery);
            Assert.Contains("BuildCompactCapabilitySummary", writeDiscovery);
        }

        [Fact]
        public void HostGeneration_IsCreatedOncePerServerLifetime()
        {
            var header = ReadSourceFile("src", "RookNative", "RookServer.h");
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            var constructor = ExtractFunction(source, "CRookServer::CRookServer");
            var start = ExtractFunction(source, "CRookServer::Start");

            Assert.Contains("std::string m_host_generation_id", header);
            Assert.Contains("GenerateHostGenerationId()", constructor);
            Assert.DoesNotContain("GenerateHostGenerationId()", start);
        }

        [Fact]
        public void DiscoveryAndCapabilities_PublishTheSameStoredHostGeneration()
        {
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            var capabilities = ExtractFunction(source, "BuildRookCapabilitiesDocument");
            var liveRoute = ExtractFunction(source, "CRookServer::HandleCapabilities");
            var discovery = ExtractFunction(source, "CRookServer::WriteDiscoveryFile");

            Assert.Contains("document[\"hostGenerationId\"] = hostGenerationId;", capabilities);
            Assert.Contains("m_host_generation_id", liveRoute);
            Assert.Contains("info[\"hostGenerationId\"] = m_host_generation_id;", discovery);
            Assert.Contains("m_host_generation_id", discovery);
        }

        [Fact]
        public void BridgeEvidence_IsGranularByDomain()
        {
            var header = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.h");
            var serverSource = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            var capabilityBuilder = ExtractFunction(serverSource, "BuildRookCapabilitiesDocument");

            Assert.Contains("bool HasGrasshopperCoreRegistration();", header);
            Assert.Contains("bool HasVisionDispatchRegistration();", header);
            Assert.Contains("bool HasBimDispatchRegistration();", header);
            Assert.Contains("bool HasViewportCaptureTier3Registration();", header);
            Assert.Contains("bool HasBlockDefinitionMutationRegistration();", header);

            Assert.Contains("HasGrasshopperCoreRegistration()", capabilityBuilder);
            Assert.Contains("HasVisionDispatchRegistration()", capabilityBuilder);
            Assert.Contains("HasBimDispatchRegistration()", capabilityBuilder);
            Assert.Contains("HasViewportCaptureTier3Registration()", capabilityBuilder);
            Assert.Contains("HasBlockDefinitionMutationRegistration()", capabilityBuilder);
            Assert.DoesNotContain("HasGrasshopperBridgeRegistration()", capabilityBuilder);
            Assert.DoesNotContain("\\\"port\\\",\\\"value\\\":0", capabilityBuilder);
        }

        [Fact]
        public void CapabilityBuilder_UsesUtcAndRealCompactSummary()
        {
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            var capabilityBuilder = ExtractFunction(source, "BuildRookCapabilitiesDocument");

            Assert.Contains("MakeUtcTimestamp()", capabilityBuilder);
            Assert.DoesNotContain("MakeLocalTimestamp()", capabilityBuilder);
            Assert.DoesNotContain("#define BuildCompactCapabilitySummary", source);
            Assert.DoesNotContain("capabilityDocumentJson.find", source);
            Assert.DoesNotContain("pluginVersion\"] = \"1.5.9\"", source);
            Assert.Contains("BuildCompactCapabilitySummary", source);
            Assert.Contains("for (const auto& domain : *domains)", source);
            Assert.Contains("document[\"domains\"] = domains;", source);
            Assert.Contains("kRookNativePluginVersion", source);
        }

        [Fact]
        public void CapabilityPhase_DoesNotChangeCompanionLoadingOrInstallerLayout()
        {
            var nativePlugin = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
            var installer = ReadSourceFile("installer", "RookSetup.iss");
            var deploy = ReadSourceFile("scripts", "deploy-local-testing.ps1");

            Assert.Contains("StartCompanionLoadDeferred();", nativePlugin);
            Assert.DoesNotContain("installed-modules.json", installer);
            Assert.DoesNotContain("installed-modules.json", deploy);
        }

        private static string ExtractFunction(string source, string functionName)
        {
            var signatureStart = source.IndexOf(functionName + "(", StringComparison.Ordinal);
            if (signatureStart < 0)
                throw new InvalidOperationException("Function not found: " + functionName);

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

        private static string ExtractRouteRegistration(string source, string routeStart)
        {
            var registrationStart = source.IndexOf(routeStart, StringComparison.Ordinal);
            if (registrationStart < 0)
                throw new InvalidOperationException("Route registration not found: " + routeStart);

            var parenStart = source.IndexOf('(', registrationStart);
            if (parenStart < 0)
                throw new InvalidOperationException("Route registration call not found: " + routeStart);

            var depth = 0;
            for (var i = parenStart; i < source.Length; i++)
            {
                if (source[i] == '(') depth++;
                else if (source[i] == ')')
                {
                    depth--;
                    if (depth == 0)
                    {
                        var semicolon = source.IndexOf(';', i);
                        if (semicolon < 0)
                            throw new InvalidOperationException("Route registration did not terminate: " + routeStart);

                        return source.Substring(registrationStart, semicolon - registrationStart + 1);
                    }
                }
            }

            throw new InvalidOperationException("Route registration call did not close: " + routeStart);
        }

        private static void AssertNoCapabilitiesServerExport(string source)
        {
            Assert.DoesNotContain("RookRegisterCapabilitiesServer", source);
            Assert.DoesNotContain("RookRegisterCapabilities", source);

            using (var reader = new StringReader(source))
            {
                string? line;
                while ((line = reader.ReadLine()) != null)
                {
                    Assert.False(
                        line.Contains("__declspec(dllexport)") &&
                        line.IndexOf("Capabilit", StringComparison.OrdinalIgnoreCase) >= 0,
                        "Capabilities-specific public native export found: " + line.Trim());
                }
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
