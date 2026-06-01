using System;
using System.IO;
using System.Linq;
using Rook.Bim;
using Rook.Capabilities;
using Xunit;

namespace Rook.Tests.Capabilities
{
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

            Assert.Equal("blocked_by_host", bim.State);
            Assert.Equal("not_rhino_inside", bim.ReasonCode);
            Assert.Equal("managed_rookbim_status_provider", bim.StateSource);
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

            Assert.Equal("not_loaded", bim.State);
            Assert.Equal("bim_dispatch_callback_not_registered", bim.ReasonCode);
            Assert.Equal("managed_rookbim_status_provider", bim.StateSource);
            Assert.DoesNotContain(bim.State, new[] { "available", "ready" });
            Assert.Contains(bim.Evidence, evidence =>
                evidence.ReasonCode == "bim_dispatch_callback_not_registered");
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
                Assert.Equal("unknown", bim.State);
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
        }
    }
}
