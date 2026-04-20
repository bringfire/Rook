// ManagedCreateDispatch.cpp
//
// Promoted from SurfaceHandler.cpp anonymous namespace in Phase 2 PR-4
// (Rule 6 promotion-on-third-caller). See header for rationale.

#include "stdafx.h"
#include "Infrastructure/ManagedCreateDispatch.h"
#include "Handlers/GrasshopperProxyHandler.h"
#include "RookServer.h"
// nlohmann/json and httplib already pulled in via stdafx.h

namespace Rook {
namespace Infrastructure {

void EmitNormalized(httplib::Response& res,
                    const std::string& managedResponseJson,
                    int managedStatus)
{
    auto parsed = nlohmann::json::parse(managedResponseJson, nullptr, false);
    if (parsed.is_discarded() || !parsed.is_object() || !parsed.contains("success"))
    {
        nlohmann::json err = {
            {"errorCode", "operation_failed"},
            {"errorMessage", "Managed response could not be parsed"},
        };
        CRookServer::SendErrorData(res, err);
        return;
    }

    const bool ok = parsed.value("success", false);
    if (ok)
    {
        res.status = (managedStatus >= 200 && managedStatus < 300) ? managedStatus : 200;
        const nlohmann::json& data = parsed.value("data", nlohmann::json(nullptr));
        CRookServer::SendSuccess(res, data);
        return;
    }

    // Managed failure. Preserve structured data if managed already returned an
    // object; otherwise wrap a string message into the structured shape.
    const auto& data = parsed.contains("data") ? parsed["data"] : nlohmann::json("Unknown managed error");
    if (data.is_object() && data.contains("errorCode"))
    {
        CRookServer::SendErrorData(res, data);
        return;
    }

    std::string message;
    if (data.is_string())
        message = data.get<std::string>();
    else
        message = data.dump();

    nlohmann::json err = {
        {"errorCode", "operation_failed"},
        {"errorMessage", message},
    };
    CRookServer::SendErrorData(res, err);
}

void DispatchToManagedCreate(const std::string& bodyJson,
                             httplib::Response& res)
{
    std::string responseJson;
    int managedStatus = 0;
    std::string bridgeError;
    const auto result = Rook::Handlers::InvokeManagedCreateWithBody(
        bodyJson, responseJson, managedStatus, bridgeError);

    switch (result)
    {
    case Rook::Handlers::ManagedCreateInvokeResult::Ok:
        EmitNormalized(res, responseJson, managedStatus);
        return;
    case Rook::Handlers::ManagedCreateInvokeResult::Unavailable:
    {
        nlohmann::json err = {
            {"errorCode", "bridge_unavailable"},
            {"errorMessage", "Managed Grasshopper/Rhino bridge is not registered for this Rhino process."},
        };
        res.status = 503;
        nlohmann::json envelope = {{"success", false}, {"data", err}};
        res.set_content(envelope.dump(), "application/json");
        return;
    }
    case Rook::Handlers::ManagedCreateInvokeResult::Failed:
    default:
    {
        nlohmann::json err = {
            {"errorCode", "operation_failed"},
            {"errorMessage", bridgeError.empty() ? std::string("Managed bridge invocation failed") : bridgeError},
        };
        res.status = 500;
        nlohmann::json envelope = {{"success", false}, {"data", err}};
        res.set_content(envelope.dump(), "application/json");
        return;
    }
    }
}

} // namespace Infrastructure
} // namespace Rook
