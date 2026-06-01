using System;
using System.Collections.Generic;
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
            Assert.Contains("m_server->Get(\"/capabilities\"", source);
            Assert.Contains("HandleCapabilities(req, res);", source);
            Assert.DoesNotContain("RookRegisterCapabilitiesServer", source);
        }

        [Fact]
        public void CapabilityDocument_ContainsRequiredDomainsAndSchemaFields()
        {
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");

            Assert.Contains("BuildRookCapabilitiesDocument", source);
            Assert.Contains("\"schemaVersion\"", source);
            Assert.Contains("\"generatedUtc\"", source);
            Assert.Contains("\"domains\"", source);
            Assert.Contains("\"domainId\"", source);
            Assert.Contains("\"declared\"", source);
            Assert.Contains("\"installed\"", source);
            Assert.Contains("\"state\"", source);
            Assert.Contains("\"stateSource\"", source);
            Assert.Contains("\"reasonCode\"", source);
            Assert.Contains("\"evidence\"", source);

            foreach (var domain in RequiredDomains)
            {
                Assert.Contains(domain, source);
            }
        }

        [Fact]
        public void Discovery_KeepsLegacyGhCapabilityFieldsAndAddsDomainSummary()
        {
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            var writeDiscovery = ExtractFunction(source, "CRookServer::WriteDiscoveryFile");

            Assert.Contains("\"ghProvider\"", writeDiscovery);
            Assert.Contains("\"ghRoutes\"", writeDiscovery);
            Assert.Contains("\"domainSummary\"", writeDiscovery);
            Assert.Contains("BuildCompactCapabilitySummary", writeDiscovery);
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
