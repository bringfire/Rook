using System;
using System.Collections.Generic;
using Rook.Bim;

namespace Rook.Capabilities
{
    internal sealed record CapabilityEvidence(
        string StateSource,
        string? ReasonCode = null,
        string? Message = null);

    internal sealed record CapabilityDomainStatus(
        string DomainId,
        string State,
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
            if (!rhinoInside)
            {
                return Create(
                    "bim.rhino_inside_revit",
                    "blocked_by_host",
                    ManagedRookBimStatusProvider,
                    "not_rhino_inside");
            }

            if (!bridgeRegistered)
            {
                return Create(
                    "bim.rhino_inside_revit",
                    "not_loaded",
                    ManagedRookBimStatusProvider,
                    "bim_dispatch_callback_not_registered");
            }

            if (!startupComplete)
            {
                return Create(
                    "bim.rhino_inside_revit",
                    "not_loaded",
                    ManagedRookBimStatusProvider,
                    "startup_not_complete");
            }

            BimStatusResponse status;
            try
            {
                status = RookBimRuntimeRegistry.Current.Status();
            }
            catch (Exception ex)
            {
                return Create(
                    "bim.rhino_inside_revit",
                    "unavailable",
                    ManagedRookBimStatusProvider,
                    "rookbim_status_provider_failed",
                    $"{ex.GetType().Name}: {ex.Message}");
            }

            var reasonCode = NullIfWhiteSpace(status.ErrorCode);
            if (string.Equals(reasonCode, "not_rhino_inside", StringComparison.Ordinal))
            {
                return Create(
                    "bim.rhino_inside_revit",
                    "blocked_by_host",
                    ManagedRookBimStatusProvider,
                    "not_rhino_inside",
                    status.Message);
            }

            return status.Available
                ? Create(
                    "bim.rhino_inside_revit",
                    "available",
                    ManagedRookBimStatusProvider,
                    null,
                    status.Message)
                : Create(
                    "bim.rhino_inside_revit",
                    "unavailable",
                    ManagedRookBimStatusProvider,
                    reasonCode ?? "rookbim_unavailable",
                    status.Message);
        }

        private static CapabilityDomainStatus Create(
            string domainId,
            string state,
            string stateSource,
            string? reasonCode,
            string? message = null)
        {
            return new CapabilityDomainStatus(
                domainId,
                state,
                stateSource,
                reasonCode,
                new[]
                {
                    new CapabilityEvidence(stateSource, reasonCode, message),
                });
        }

        private static string? NullIfWhiteSpace(string? value)
        {
            return string.IsNullOrWhiteSpace(value) ? null : value;
        }
    }
}
