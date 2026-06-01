using System;
using System.Collections.Generic;
using Rook.Bim;

namespace Rook.Capabilities
{
    internal sealed record CapabilityEvidence(
        string StateSource,
        string? ReasonCode = null,
        string? Message = null,
        string? Name = null,
        bool? Value = null);

    internal sealed record CapabilityDomainStatus(
        string DomainId,
        string State,
        bool Ready,
        string StateSource,
        string? ReasonCode,
        IReadOnlyList<CapabilityEvidence> Evidence);

    internal static class CapabilityDomainStatusBuilder
    {
        private const string ManagedCompanionRuntime = "managed_companion_runtime";
        private const string ManagedRookBimStatusProvider = "managed_rookbim_status_provider";

        public static IReadOnlyList<CapabilityDomainStatus> BuildCompanionDomains(
            bool rhinoInside,
            bool startupComplete,
            bool bridgeRegistered,
            bool panelsRegistered)
        {
            return new[]
            {
                BuildManagedDomain(
                    "chat.ui",
                    panelsRegistered,
                    startupComplete,
                    "panels_not_registered"),
                BuildManagedDomain(
                    "vision.media",
                    panelsRegistered,
                    startupComplete,
                    "panels_not_registered"),
                BuildBridgeBackedDomain(
                    "viewport.capture",
                    startupComplete,
                    bridgeRegistered),
                BuildBridgeBackedDomain(
                    "block.definition_mutation",
                    startupComplete,
                    bridgeRegistered),
                BuildBimDomain(rhinoInside, startupComplete, bridgeRegistered),
            };
        }

        private static CapabilityDomainStatus BuildManagedDomain(
            string domainId,
            bool localRegistered,
            bool startupComplete,
            string unavailableReason)
        {
            if (!startupComplete)
            {
                return Create(
                    domainId,
                    "not_loaded",
                    ManagedCompanionRuntime,
                    "startup_not_complete");
            }

            return localRegistered
                ? Create(domainId, "available", ManagedCompanionRuntime, null)
                : Create(domainId, "unavailable", ManagedCompanionRuntime, unavailableReason);
        }

        private static CapabilityDomainStatus BuildBridgeBackedDomain(
            string domainId,
            bool startupComplete,
            bool bridgeRegistered)
        {
            if (!startupComplete)
            {
                return Create(
                    domainId,
                    "not_loaded",
                    ManagedCompanionRuntime,
                    "startup_not_complete");
            }

            return bridgeRegistered
                ? Create(domainId, "available", ManagedCompanionRuntime, null)
                : Create(
                    domainId,
                    "not_loaded",
                    ManagedCompanionRuntime,
                    "managed_bridge_not_registered");
        }

        private static CapabilityDomainStatus BuildBimDomain(
            bool rhinoInside,
            bool startupComplete,
            bool bridgeRegistered)
        {
            if (!bridgeRegistered)
            {
                return Create(
                    "bim.rhino_inside_revit",
                    "not_loaded",
                    ManagedRookBimStatusProvider,
                    "bim_dispatch_callback_not_registered",
                    evidenceName: "bimDispatch",
                    evidenceValue: false);
            }

            if (!rhinoInside)
            {
                return Create(
                    "bim.rhino_inside_revit",
                    "blocked_by_host",
                    ManagedRookBimStatusProvider,
                    "not_rhino_inside");
            }

            if (!startupComplete)
            {
                return Create(
                    "bim.rhino_inside_revit",
                    "not_loaded",
                    ManagedRookBimStatusProvider,
                    "startup_not_complete");
            }

            var source = RookBimRuntimeRegistry.Source;
            if (string.Equals(source, "core-fallback", StringComparison.Ordinal))
            {
                return Create(
                    "bim.rhino_inside_revit",
                    "not_loaded",
                    ManagedRookBimStatusProvider,
                    "rookbim_runtime_not_activated");
            }

            if (string.Equals(source, "module-not-found", StringComparison.Ordinal))
            {
                return Create(
                    "bim.rhino_inside_revit",
                    "missing_dependency",
                    ManagedRookBimStatusProvider,
                    "rookbim_module_not_found");
            }

            if (string.Equals(source, "module-load-failed", StringComparison.Ordinal))
            {
                return Create(
                    "bim.rhino_inside_revit",
                    "failed",
                    ManagedRookBimStatusProvider,
                    "rookbim_module_load_failed");
            }

            return Create(
                "bim.rhino_inside_revit",
                "unknown",
                ManagedRookBimStatusProvider,
                "bim_status_not_probed_phase1",
                "Use /bim/status to check active document and Revit API readiness.");
        }

        private static CapabilityDomainStatus Create(
            string domainId,
            string state,
            string stateSource,
            string? reasonCode,
            string? message = null,
            string? evidenceName = null,
            bool? evidenceValue = null)
        {
            return new CapabilityDomainStatus(
                domainId,
                state,
                string.Equals(state, "available", StringComparison.Ordinal),
                stateSource,
                reasonCode,
                new[]
                {
                    new CapabilityEvidence(stateSource, reasonCode, message, evidenceName, evidenceValue),
                });
        }

    }
}
