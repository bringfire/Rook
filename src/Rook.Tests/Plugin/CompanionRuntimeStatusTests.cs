using System;
using System.Linq;
using System.Text.Json;
using Rook.Bim;
using Rook.Capabilities;
using Rook.Startup;
using Rook.Tests.Bim;
using Xunit;

namespace Rook.Tests.Plugin
{
    [Collection(RookBimRuntimeRegistryCollection.Name)]
    public class CompanionRuntimeStatusTests
    {
        [Theory]
        [InlineData(@"C:\Users\a\AppData\Roaming\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48\Rook.rhp", "net48")]
        [InlineData(@"C:/Users/a/AppData/Roaming/McNeel/Rhinoceros/8.0/Plug-ins/RookNative/net7.0/Rook.rhp", "net7.0")]
        [InlineData(@"C:\Users\a\AppData\Roaming\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rhp", "net8.0")]
        [InlineData(@"C:\Users\a\AppData\Roaming\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\Rook.rhp", "unknown")]
        public void InferRuntimeChild_UsesRookNativeRuntimePathSegment(
            string assemblyLocation,
            string expected)
        {
            Assert.Equal(
                expected,
                CompanionRuntimeStatus.InferRuntimeChild(assemblyLocation));
        }

        [Fact]
        public void BuildJson_IncludesRuntimeSelfReportFields()
        {
            var onLoadUtc = DateTimeOffset.Parse("2026-05-26T18:00:00Z");
            var startupCompleteUtc = DateTimeOffset.Parse("2026-05-26T18:00:05Z");
            var snapshot = new CompanionRuntimeStatusSnapshot(
                ProcessId: 1234,
                ProcessName: "Revit",
                RhinoInside: true,
                AssemblyLocation: @"C:\Users\a\AppData\Roaming\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48\Rook.rhp",
                TargetFramework: ".NETFramework,Version=v4.8",
                StartupGateAttached: true,
                DeferredLocalStartupComplete: true,
                StartupComplete: true,
                BridgeRegistered: true,
                PanelsRegistered: true,
                CapabilityDomains: CapabilityDomainStatusBuilder.BuildCompanionDomains(
                    rhinoInside: true,
                    startupComplete: true,
                    bridgeRegistered: true,
                    panelsRegistered: true),
                OnLoadUtc: onLoadUtc,
                StartupCompleteUtc: startupCompleteUtc);

            using var document = JsonDocument.Parse(
                CompanionRuntimeStatus.BuildJson(snapshot));
            var root = document.RootElement;

            Assert.Equal(1, root.GetProperty("schemaVersion").GetInt32());
            Assert.Equal(1234, root.GetProperty("processId").GetInt32());
            Assert.Equal("Revit", root.GetProperty("processName").GetString());
            Assert.True(root.GetProperty("rhinoInside").GetBoolean());
            Assert.Equal(snapshot.AssemblyLocation, root.GetProperty("assemblyLocation").GetString());
            Assert.Equal("net48", root.GetProperty("runtimeChild").GetString());
            Assert.Equal(".NETFramework,Version=v4.8", root.GetProperty("targetFramework").GetString());
            Assert.True(root.GetProperty("startupGateAttached").GetBoolean());
            Assert.True(root.GetProperty("deferredLocalStartupComplete").GetBoolean());
            Assert.True(root.GetProperty("startupComplete").GetBoolean());
            Assert.True(root.GetProperty("bridgeRegistered").GetBoolean());
            Assert.True(root.GetProperty("panelsRegistered").GetBoolean());
            Assert.Equal("2026-05-26T18:00:00.0000000+00:00", root.GetProperty("onLoadUtc").GetString());
            Assert.Equal("2026-05-26T18:00:05.0000000+00:00", root.GetProperty("startupCompleteUtc").GetString());

            var capabilityDomains = root.GetProperty("capabilityDomains").EnumerateArray().ToArray();
            var chatUi = capabilityDomains.Single(domain =>
                domain.GetProperty("domainId").GetString() == "chat.ui");
            Assert.True(chatUi.GetProperty("declared").GetBoolean());
            Assert.Equal("unknown", chatUi.GetProperty("installed").GetString());
            Assert.True(chatUi.GetProperty("loaded").GetBoolean());
            Assert.Equal("unknown", chatUi.GetProperty("state").GetString());
            Assert.False(chatUi.GetProperty("ready").GetBoolean());
            Assert.Equal(
                "chat_service_state_not_probed_phase1",
                chatUi.GetProperty("reasonCode").GetString());
            Assert.Equal("managed_companion_runtime", chatUi.GetProperty("stateSource").GetString());
            Assert.Contains(chatUi.GetProperty("evidence").EnumerateArray(), evidence =>
                evidence.GetProperty("kind").GetString() == "managed_companion_runtime" &&
                evidence.GetProperty("name").GetString() == "panelsRegistered" &&
                evidence.GetProperty("value").GetBoolean());

            var vision = capabilityDomains.Single(domain =>
                domain.GetProperty("domainId").GetString() == "vision.media");
            Assert.Equal("unknown", vision.GetProperty("state").GetString());
            Assert.False(vision.GetProperty("ready").GetBoolean());
            Assert.Contains(vision.GetProperty("evidence").EnumerateArray(), evidence =>
                evidence.GetProperty("kind").GetString() == "status_provider" &&
                evidence.GetProperty("name").GetString() == "visionDispatch" &&
                evidence.GetProperty("value").GetBoolean() == false);

            var bim = capabilityDomains.Single(domain =>
                domain.GetProperty("domainId").GetString() == "bim.rhino_inside_revit");
            Assert.True(bim.GetProperty("declared").GetBoolean());
            Assert.False(bim.GetProperty("ready").GetBoolean());
            Assert.Equal("managed_rookbim_status_provider", bim.GetProperty("stateSource").GetString());
        }

        [Fact]
        public void BuildCompanionDomains_ReportsBimHostAndBridgeState()
        {
            var outsideRhinoInside = CapabilityDomainStatusBuilder.BuildCompanionDomains(
                rhinoInside: false,
                startupComplete: true,
                bridgeRegistered: true,
                panelsRegistered: true);
            var outsideBim = outsideRhinoInside.Single(domain =>
                domain.DomainId == "bim.rhino_inside_revit");
            Assert.Equal("blocked_by_host", outsideBim.State);
            Assert.False(outsideBim.Ready);
            Assert.Equal("not_rhino_inside", outsideBim.ReasonCode);
            Assert.Equal("managed_rookbim_status_provider", outsideBim.StateSource);

            var missingBridge = CapabilityDomainStatusBuilder.BuildCompanionDomains(
                rhinoInside: true,
                startupComplete: false,
                bridgeRegistered: false,
                panelsRegistered: true);
            var missingBridgeBim = missingBridge.Single(domain =>
                domain.DomainId == "bim.rhino_inside_revit");
            Assert.Equal("not_loaded", missingBridgeBim.State);
            Assert.False(missingBridgeBim.Ready);
            Assert.Equal("bim_dispatch_callback_not_registered", missingBridgeBim.ReasonCode);
            Assert.Equal("managed_rookbim_status_provider", missingBridgeBim.StateSource);
        }

        [Fact]
        public void BuildCompanionDomains_DoesNotProbeBimRuntimeStatus()
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
                Assert.Contains("/bim/status", bim.Message);
                Assert.Contains(bim.Evidence, evidence =>
                    evidence.Kind == "callback" && evidence.Name == "bimDispatch" && evidence.Value);
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        [Fact]
        public void BuildCompanionDomains_ReportsChatPanelRegistrationFailure()
        {
            var domains = CapabilityDomainStatusBuilder.BuildCompanionDomains(
                rhinoInside: false,
                startupComplete: true,
                bridgeRegistered: false,
                panelsRegistered: false);

            var chat = domains.Single(domain => domain.DomainId == "chat.ui");
            Assert.True(chat.Declared);
            Assert.True(chat.Loaded);
            Assert.Equal("unavailable", chat.State);
            Assert.False(chat.Ready);
            Assert.Equal("panels_not_registered", chat.ReasonCode);
            Assert.Contains(chat.Evidence, evidence =>
                evidence.Kind == "managed_companion_runtime" &&
                evidence.Name == "panelsRegistered" &&
                evidence.Value == false);
        }

        [Theory]
        [InlineData("core-fallback", "not_loaded", "rookbim_runtime_not_activated")]
        [InlineData("module-not-found", "missing_dependency", "rookbim_module_not_found")]
        [InlineData("module-load-failed", "failed", "rookbim_module_load_failed")]
        public void BuildCompanionDomains_MapsBimRegistrySourceWithoutStatusProbe(
            string source,
            string expectedState,
            string expectedReason)
        {
            var runtime = new ThrowingBimRuntime();
            RookBimRuntimeRegistry.Install(runtime, source);

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
                Assert.Equal(expectedState, bim.State);
                Assert.Equal(expectedReason, bim.ReasonCode);
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        private sealed class ThrowingBimRuntime : IRookBimRuntime
        {
            BimApiResponse IRookBimRuntime.CreationGuidProbe(
                BimDiagnosticContext diagnostics, BimCreationGuidProbeRequest request) =>
                throw new NotSupportedException();

            public bool StatusCalled { get; private set; }

            public BimStatusResponse Status(BimDiagnosticContext diagnostics)
            {
                StatusCalled = true;
                throw new InvalidOperationException("Status must not be probed by capability status builder.");
            }

            public BimApiResponse ActiveDocument(BimDiagnosticContext diagnostics)
            {
                throw new NotSupportedException();
            }

            public BimApiResponse ListCategories(BimDiagnosticContext diagnostics)
            {
                throw new NotSupportedException();
            }

            public BimApiResponse QueryElements(BimDiagnosticContext diagnostics, BimQueryElementsRequest request)
            {
                throw new NotSupportedException();
            }

            public BimApiResponse ElementInfo(BimDiagnosticContext diagnostics, BimElementRequest request)
            {
                throw new NotSupportedException();
            }

            public BimApiResponse ElementParameters(BimDiagnosticContext diagnostics, BimElementRequest request)
            {
                throw new NotSupportedException();
            }

            public BimApiResponse SelectElements(BimDiagnosticContext diagnostics, BimSelectElementsRequest request)
            {
                throw new NotSupportedException();
            }

            public BimApiResponse ClearSelection(BimDiagnosticContext diagnostics)
            {
                throw new NotSupportedException();
            }

            public BimApiResponse ExportElements(BimDiagnosticContext diagnostics, BimExportElementsRequest request)
            {
                throw new NotSupportedException();
            }

            public BimApiResponse ExportPreset(BimDiagnosticContext diagnostics, BimExportPresetRequest request)
            {
                throw new NotSupportedException();
            }
        }
    }
}
