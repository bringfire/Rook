using System;
using System.Collections.Generic;
using Rook.Bim;

namespace Rook.Capabilities
{
    internal sealed record CapabilityEvidence(
        string Kind,
        string Name,
        bool Value);

    internal sealed record CapabilityDomainStatus(
        string DomainId,
        bool Declared,
        string Installed,
        bool Loaded,
        string State,
        bool Ready,
        string? ReasonCode,
        bool Retryable,
        string StateSource,
        string Message,
        IReadOnlyList<string> Routes,
        IReadOnlyList<string> Operations,
        IReadOnlyList<string> Diagnostics,
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
                BuildUnprobedDomain(
                    "vision.media",
                    startupComplete,
                    "vision_dispatch_evidence_unavailable_phase1",
                    "visionDispatch"),
                BuildUnprobedDomain(
                    "viewport.capture",
                    startupComplete,
                    "viewport_capture_tier3_evidence_unavailable_phase1",
                    "viewportCaptureTier3"),
                BuildUnprobedDomain(
                    "block.definition_mutation",
                    startupComplete,
                    "block_definition_mutation_evidence_unavailable_phase1",
                    "blockDefinitionMutation"),
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
                return Domain(
                    domainId,
                    loaded: false,
                    "not_loaded",
                    ready: false,
                    "startup_not_complete");
            }

            return localRegistered
                ? Domain(
                    domainId,
                    loaded: true,
                    "ready",
                    ready: true,
                    reasonCode: null,
                    evidence: new[]
                    {
                        Evidence(ManagedCompanionRuntime, "startupComplete", startupComplete),
                        Evidence(ManagedCompanionRuntime, "panelsRegistered", localRegistered),
                    })
                : Domain(
                    domainId,
                    loaded: true,
                    "unavailable",
                    ready: false,
                    unavailableReason,
                    evidence: new[]
                    {
                        Evidence(ManagedCompanionRuntime, "startupComplete", startupComplete),
                        Evidence(ManagedCompanionRuntime, "panelsRegistered", localRegistered),
                    });
        }

        private static CapabilityDomainStatus BuildUnprobedDomain(
            string domainId,
            bool startupComplete,
            string reasonCode,
            string domainEvidenceName)
        {
            if (!startupComplete)
            {
                return Domain(
                    domainId,
                    loaded: false,
                    "not_loaded",
                    ready: false,
                    "startup_not_complete",
                    evidence: UnprobedEvidence(startupComplete, domainEvidenceName));
            }

            return Domain(
                domainId,
                loaded: false,
                "unknown",
                ready: false,
                reasonCode,
                $"Phase 1 managed status does not probe {domainEvidenceName}; use native /capabilities for route-level readiness.",
                evidence: UnprobedEvidence(startupComplete, domainEvidenceName));
        }

        private static CapabilityDomainStatus BuildBimDomain(
            bool rhinoInside,
            bool startupComplete,
            bool bridgeRegistered)
        {
            if (!bridgeRegistered)
            {
                return BimDomain(
                    "bim.rhino_inside_revit",
                    loaded: false,
                    "not_loaded",
                    ready: false,
                    "bim_dispatch_callback_not_registered",
                    evidence: BimEvidence(rhinoInside, startupComplete, bridgeRegistered));
            }

            if (!rhinoInside)
            {
                return BimDomain(
                    "bim.rhino_inside_revit",
                    loaded: false,
                    "blocked_by_host",
                    ready: false,
                    "not_rhino_inside",
                    evidence: BimEvidence(rhinoInside, startupComplete, bridgeRegistered));
            }

            if (!startupComplete)
            {
                return BimDomain(
                    "bim.rhino_inside_revit",
                    loaded: false,
                    "not_loaded",
                    ready: false,
                    "startup_not_complete",
                    evidence: BimEvidence(rhinoInside, startupComplete, bridgeRegistered));
            }

            var source = RookBimRuntimeRegistry.Source;
            if (string.Equals(source, "core-fallback", StringComparison.Ordinal))
            {
                return BimDomain(
                    "bim.rhino_inside_revit",
                    loaded: false,
                    "not_loaded",
                    ready: false,
                    "rookbim_runtime_not_activated",
                    evidence: BimEvidence(rhinoInside, startupComplete, bridgeRegistered));
            }

            if (string.Equals(source, "module-not-found", StringComparison.Ordinal))
            {
                return BimDomain(
                    "bim.rhino_inside_revit",
                    loaded: false,
                    "missing_dependency",
                    ready: false,
                    "rookbim_module_not_found",
                    evidence: BimEvidence(rhinoInside, startupComplete, bridgeRegistered));
            }

            if (string.Equals(source, "module-load-failed", StringComparison.Ordinal))
            {
                return BimDomain(
                    "bim.rhino_inside_revit",
                    loaded: false,
                    "failed",
                    ready: false,
                    "rookbim_module_load_failed",
                    evidence: BimEvidence(rhinoInside, startupComplete, bridgeRegistered));
            }

            return BimDomain(
                "bim.rhino_inside_revit",
                loaded: true,
                "unknown",
                ready: false,
                "bim_status_not_probed_phase1",
                "Use /bim/status to check active document and Revit API readiness.",
                BimEvidence(rhinoInside, startupComplete, bridgeRegistered));
        }

        private static CapabilityDomainStatus BimDomain(
            string domainId,
            bool loaded,
            string state,
            bool ready,
            string? reasonCode,
            string? message = null,
            IReadOnlyList<CapabilityEvidence>? evidence = null)
        {
            return Domain(
                domainId,
                loaded,
                state,
                ready,
                reasonCode,
                message,
                routes: new[]
                {
                    "GET /bim/status",
                    "GET /bim/active-document",
                    "GET /bim/categories",
                    "POST /bim/query-elements",
                },
                operations: new[]
                {
                    "status",
                    "active_document",
                    "list_categories",
                    "query_elements",
                },
                diagnostics: new[] { "GET /bim/status" },
                evidence: evidence,
                stateSource: ManagedRookBimStatusProvider);
        }

        private static CapabilityDomainStatus Domain(
            string domainId,
            bool loaded,
            string state,
            bool ready,
            string? reasonCode,
            string? message = null,
            IReadOnlyList<string>? routes = null,
            IReadOnlyList<string>? operations = null,
            IReadOnlyList<string>? diagnostics = null,
            IReadOnlyList<CapabilityEvidence>? evidence = null,
            string stateSource = ManagedCompanionRuntime)
        {
            return new CapabilityDomainStatus(
                domainId,
                Declared: true,
                Installed: "unknown",
                Loaded: loaded,
                State: state,
                Ready: ready,
                ReasonCode: reasonCode,
                Retryable: false,
                StateSource: stateSource,
                Message: message ?? string.Empty,
                Routes: routes ?? Array.Empty<string>(),
                Operations: operations ?? Array.Empty<string>(),
                Diagnostics: diagnostics ?? Array.Empty<string>(),
                Evidence: evidence ?? new[]
                {
                    Evidence(ManagedCompanionRuntime, "startupComplete", loaded),
                });
        }

        private static IReadOnlyList<CapabilityEvidence> BimEvidence(
            bool rhinoInside,
            bool startupComplete,
            bool bridgeRegistered)
        {
            return new[]
            {
                Evidence(ManagedCompanionRuntime, "startupComplete", startupComplete),
                Evidence("callback", "bimDispatch", bridgeRegistered),
                Evidence("host", "rhinoInside", rhinoInside),
            };
        }

        private static IReadOnlyList<CapabilityEvidence> UnprobedEvidence(
            bool startupComplete,
            string domainEvidenceName)
        {
            return new[]
            {
                Evidence(ManagedCompanionRuntime, "startupComplete", startupComplete),
                Evidence("status_provider", domainEvidenceName, false),
            };
        }

        private static CapabilityEvidence Evidence(
            string kind,
            string name,
            bool value)
        {
            return new CapabilityEvidence(kind, name, value);
        }
    }
}
