using System;
using System.IO;
using System.Linq;
using Rook.Bim;
using Rook.Capabilities;
using Rook.Tests.Bim;
using Xunit;

namespace Rook.Tests.Capabilities
{
    [Collection(RookBimRuntimeRegistryCollection.Name)]
    public class ManagedCapabilityDomainStatusTests
    {
        [Fact]
        public void BuildCompanionDomains_ReportsBimBlockedOutsideRhinoInsideWhenBridgeRegistered()
        {
            var domains = CapabilityDomainStatusBuilder.BuildCompanionDomains(
                rhinoInside: false,
                startupComplete: true,
                bridgeRegistered: true,
                panelsRegistered: true);

            var bim = domains.Single(domain =>
                domain.DomainId == "bim.rhino_inside_revit");

            Assert.True(bim.Declared);
            Assert.Equal("unknown", bim.Installed);
            Assert.Equal("blocked_by_host", bim.State);
            Assert.False(bim.Ready);
            Assert.False(bim.Loaded);
            Assert.Equal("not_rhino_inside", bim.ReasonCode);
            Assert.Equal("managed_rookbim_status_provider", bim.StateSource);
            Assert.Contains("GET /bim/status", bim.Diagnostics);
            Assert.Contains(bim.Evidence, evidence =>
                evidence.Kind == "host" && evidence.Name == "rhinoInside" && evidence.Value == false);
        }

        [Fact]
        public void BuildCompanionDomains_DoesNotClaimBimReadyWhenBridgeMissing()
        {
            var domains = CapabilityDomainStatusBuilder.BuildCompanionDomains(
                rhinoInside: true,
                startupComplete: true,
                bridgeRegistered: false,
                panelsRegistered: true);

            var bim = domains.Single(domain =>
                domain.DomainId == "bim.rhino_inside_revit");

            Assert.True(bim.Declared);
            Assert.Equal("not_loaded", bim.State);
            Assert.False(bim.Ready);
            Assert.False(bim.Loaded);
            Assert.Equal("bim_dispatch_callback_not_registered", bim.ReasonCode);
            Assert.Equal("managed_rookbim_status_provider", bim.StateSource);
            Assert.Contains(bim.Evidence, evidence =>
                evidence.Kind == "callback" && evidence.Name == "bimDispatch" && evidence.Value == false);
        }

        [Fact]
        public void BuildCompanionDomains_DoesNotClaimChatReadyFromPanelRegistrationOnly()
        {
            var domains = CapabilityDomainStatusBuilder.BuildCompanionDomains(
                rhinoInside: false,
                startupComplete: true,
                bridgeRegistered: true,
                panelsRegistered: true);

            var chat = domains.Single(domain => domain.DomainId == "chat.ui");

            Assert.True(chat.Declared);
            Assert.Equal("unknown", chat.Installed);
            Assert.True(chat.Loaded);
            Assert.Equal("unknown", chat.State);
            Assert.False(chat.Ready);
            Assert.Equal("chat_service_state_not_probed_phase1", chat.ReasonCode);
            Assert.Contains(chat.Evidence, evidence =>
                evidence.Kind == "managed_companion_runtime" &&
                evidence.Name == "panelsRegistered" &&
                evidence.Value);
        }

        [Fact]
        public void BuildCompanionDomains_DoesNotClaimUnprobedManagedDomainsReadyFromBroadBridgeState()
        {
            var domains = CapabilityDomainStatusBuilder.BuildCompanionDomains(
                rhinoInside: false,
                startupComplete: true,
                bridgeRegistered: true,
                panelsRegistered: true);

            AssertUnprobedDomain(
                domains,
                "vision.media",
                "vision_dispatch_evidence_unavailable_phase1",
                "visionDispatch");
            AssertUnprobedDomain(
                domains,
                "viewport.capture",
                "viewport_capture_tier3_evidence_unavailable_phase1",
                "viewportCaptureTier3");
            AssertUnprobedDomain(
                domains,
                "block.definition_mutation",
                "block_definition_mutation_evidence_unavailable_phase1",
                "blockDefinitionMutation");
        }

        [Fact]
        public void BuildCompanionDomains_KeepsBimSeparateFromGrasshopperChatAndVision()
        {
            var domainIds = CapabilityDomainStatusBuilder.BuildCompanionDomains(
                    rhinoInside: false,
                    startupComplete: true,
                    bridgeRegistered: true,
                    panelsRegistered: true)
                .Select(domain => domain.DomainId)
                .ToArray();

            Assert.Contains("bim.rhino_inside_revit", domainIds);
            Assert.Contains("chat.ui", domainIds);
            Assert.Contains("vision.media", domainIds);
            Assert.DoesNotContain("gh.bridge", domainIds);
        }

        [Fact]
        public void CapabilityDomainStatus_DoesNotReferenceRevitApis()
        {
            var source = ReadSourceFile("src", "Rook", "Capabilities", "CapabilityDomainStatus.cs");

            Assert.DoesNotContain("Autodesk", source);
            Assert.DoesNotContain("RevitAPI", source);
            Assert.DoesNotContain("RhinoInside.Revit", source);
        }

        [Fact]
        public void BuildCompanionDomains_DoesNotProbeThrowingBimRuntimeStatus()
        {
            var runtime = new ThrowingBimRuntime();
            RookBimRuntimeRegistry.Install(runtime, "RookBim.dll");

            try
            {
                var domains = CapabilityDomainStatusBuilder.BuildCompanionDomains(
                    rhinoInside: true,
                    startupComplete: true,
                    bridgeRegistered: true,
                    panelsRegistered: true);

                var bim = domains.Single(domain =>
                    domain.DomainId == "bim.rhino_inside_revit");

                Assert.False(runtime.StatusCalled);
                Assert.True(bim.Declared);
                Assert.True(bim.Loaded);
                Assert.Equal("unknown", bim.State);
                Assert.False(bim.Ready);
                Assert.Equal("bim_status_not_probed_phase1", bim.ReasonCode);
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
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

        private static void AssertUnprobedDomain(
            System.Collections.Generic.IEnumerable<CapabilityDomainStatus> domains,
            string domainId,
            string reasonCode,
            string evidenceName)
        {
            var domain = domains.Single(item => item.DomainId == domainId);

            Assert.True(domain.Declared);
            Assert.Equal("unknown", domain.Installed);
            Assert.False(domain.Loaded);
            Assert.Equal("unknown", domain.State);
            Assert.False(domain.Ready);
            Assert.Equal(reasonCode, domain.ReasonCode);
            Assert.Contains(domain.Evidence, evidence =>
                evidence.Kind == "status_provider" &&
                evidence.Name == evidenceName &&
                evidence.Value == false);
            Assert.DoesNotContain(domain.Evidence, evidence =>
                evidence.Kind == "callback" && evidence.Name == "managedBridge");
        }

        private sealed class ThrowingBimRuntime : IRookBimRuntime
        {
            public bool StatusCalled { get; private set; }

            public BimStatusResponse Status()
            {
                StatusCalled = true;
                throw new InvalidOperationException("Status must not be probed by capability status builder.");
            }

            public BimApiResponse ActiveDocument()
            {
                throw new NotSupportedException();
            }

            public BimApiResponse ListCategories()
            {
                throw new NotSupportedException();
            }

            public BimApiResponse QueryElements(BimQueryElementsRequest request)
            {
                throw new NotSupportedException();
            }

            public BimApiResponse ElementInfo(BimElementRequest request)
            {
                throw new NotSupportedException();
            }

            public BimApiResponse ElementParameters(BimElementRequest request)
            {
                throw new NotSupportedException();
            }

            public BimApiResponse SelectElements(BimSelectElementsRequest request)
            {
                throw new NotSupportedException();
            }

            public BimApiResponse ClearSelection()
            {
                throw new NotSupportedException();
            }

            public BimApiResponse ExportElements(BimExportElementsRequest request)
            {
                throw new NotSupportedException();
            }

            public BimApiResponse ExportPreset(BimExportPresetRequest request)
            {
                throw new NotSupportedException();
            }
        }
    }
}
