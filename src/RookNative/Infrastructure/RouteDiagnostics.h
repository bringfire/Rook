// RouteDiagnostics.h
//
// Phase 2 additive route diagnostics. Header-only by design so Slice 1
// does not require .vcxproj or .vcxproj.filters edits.

#pragma once

#include <string>

namespace Rook {
namespace Diagnostics {

constexpr int kRouteDiagnosticSchemaVersion = 1;

enum class FailureKind
{
    DomainUnavailable,
    HostBlocked,
    DependencyUnavailable,
    DependencyDegraded,
    OperationUnavailable,
    ConfigurationRequired,
    AuthorizationRequired,
    Unknown,
};

inline const char* FailureKindToString(FailureKind kind)
{
    switch (kind)
    {
    case FailureKind::DomainUnavailable:
        return "domain_unavailable";
    case FailureKind::HostBlocked:
        return "host_blocked";
    case FailureKind::DependencyUnavailable:
        return "dependency_unavailable";
    case FailureKind::DependencyDegraded:
        return "dependency_degraded";
    case FailureKind::OperationUnavailable:
        return "operation_unavailable";
    case FailureKind::ConfigurationRequired:
        return "configuration_required";
    case FailureKind::AuthorizationRequired:
        return "authorization_required";
    case FailureKind::Unknown:
    default:
        return "unknown";
    }
}

struct RouteDiagnostic
{
    std::string domainId;
    std::string route;
    std::string operation;
    std::string reasonCode;
    FailureKind failureKind = FailureKind::Unknown;
    bool retryable = false;
    bool userActionRequired = false;
    std::string recommendedNextStep;
    std::string ownedBy;
    std::string evidenceSource;
    std::string emittedBy;
    std::string state;
};

inline nlohmann::json ToJson(const RouteDiagnostic& diagnostic)
{
    nlohmann::json result;
    result["schemaVersion"] = kRouteDiagnosticSchemaVersion;
    result["domainId"] = diagnostic.domainId;
    result["route"] = diagnostic.route;
    result["operation"] = diagnostic.operation;
    result["reasonCode"] = diagnostic.reasonCode;
    result["failureKind"] = FailureKindToString(diagnostic.failureKind);
    result["retryable"] = diagnostic.retryable;
    result["userActionRequired"] = diagnostic.userActionRequired;

    nlohmann::json diagnosticRoute;
    diagnosticRoute["method"] = "GET";
    diagnosticRoute["path"] = "/capabilities";
    diagnosticRoute["domainId"] = diagnostic.domainId;
    result["diagnosticRoute"] = diagnosticRoute;

    if (!diagnostic.recommendedNextStep.empty())
        result["recommendedNextStep"] = diagnostic.recommendedNextStep;

    result["ownedBy"] = diagnostic.ownedBy;
    result["evidenceSource"] = diagnostic.evidenceSource;
    result["emittedBy"] = diagnostic.emittedBy;

    if (!diagnostic.state.empty())
        result["state"] = diagnostic.state;

    return result;
}

inline nlohmann::json BuildVisionDispatchCallbackUnavailable(
    const std::string& route,
    const std::string& operation)
{
    RouteDiagnostic diagnostic;
    diagnostic.domainId = "vision.media";
    diagnostic.route = route;
    diagnostic.operation = operation;
    diagnostic.reasonCode = "vision_dispatch_callback_unavailable";
    diagnostic.failureKind = FailureKind::DomainUnavailable;
    diagnostic.retryable = true;
    diagnostic.userActionRequired = false;
    diagnostic.recommendedNextStep =
        "Wait for companion startup, then retry. If it remains unavailable, inspect /capabilities.";
    diagnostic.ownedBy = "native";
    diagnostic.evidenceSource = "native_callback_registration";
    diagnostic.emittedBy = "native_route";
    diagnostic.state = "not_loaded";
    return ToJson(diagnostic);
}

} // namespace Diagnostics
} // namespace Rook
