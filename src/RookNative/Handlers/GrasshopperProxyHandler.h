// GrasshopperProxyHandler.h

#pragma once
#include <string>

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void ClearGrasshopperBridgeRegistration();
bool HasGrasshopperBridgeRegistration();
bool HasCanvasGraphProtocol();
bool HasCanvasGraphNavigation();
bool TryHandleManagedCreate(const httplib::Request& req, httplib::Response& res);

// Invokes the managed CreateGeometry bridge callback with a prepared JSON body
// (caller is responsible for injecting required fields such as "type"). On
// success, populates responseJson + statusCode with the raw managed response
// and returns kOk. Does not modify res — the caller parses the response and
// applies any envelope normalization (used by /surface/* typed routes to
// rewrite managed string errors into structured {errorCode, errorMessage}).
enum class ManagedCreateInvokeResult
{
    Ok,
    Unavailable,
    Failed,
};

ManagedCreateInvokeResult InvokeManagedCreateWithBody(
    const std::string& requestJson,
    std::string& responseJson,
    int& statusCode,
    std::string& error);

// Invokes the managed Tier 3 viewport capture bridge callback. Tier 3 is
// SDK-backed (view.CaptureToBitmap) and managed-only; native /viewport falls
// back to this helper when captureBackend == "tier3". Same contract as
// InvokeManagedCreateWithBody: populates responseJson + statusCode with the
// raw managed response on Ok.
ManagedCreateInvokeResult InvokeViewportCaptureTier3WithBody(
    const std::string& requestJson,
    std::string& responseJson,
    int& statusCode,
    std::string& error);

// Invokes the managed vision_dispatch bridge callback. Single
// generic dispatch for all /vision/* routes — the op discriminator is
// carried in the request JSON and routed inside VisionHandler.cs. Keeps
// VisionHandler.cs as the single validation boundary and avoids one
// callback slot per vision route.
ManagedCreateInvokeResult InvokeVisionDispatchWithBody(
    const std::string& requestJson,
    std::string& responseJson,
    int& statusCode,
    std::string& error);

// Invokes the managed bim_dispatch bridge callback. Native /bim/* routes
// inject only the op discriminator and forward the opaque JSON body to the
// managed BIM handler.
ManagedCreateInvokeResult InvokeBimDispatchWithBody(
    const std::string& requestJson,
    std::string& responseJson,
    int& statusCode,
    std::string& error);
void HandleBimStatus(const httplib::Request& req, httplib::Response& res);
void HandleBimActiveDocument(const httplib::Request& req, httplib::Response& res);
void HandleBimCategories(const httplib::Request& req, httplib::Response& res);
void HandleBimQueryElements(const httplib::Request& req, httplib::Response& res);
void HandleBimElementInfo(const httplib::Request& req, httplib::Response& res);
void HandleBimElementParameters(const httplib::Request& req, httplib::Response& res);
void HandleBimSelectElements(const httplib::Request& req, httplib::Response& res);
void HandleBimClearSelection(const httplib::Request& req, httplib::Response& res);
void HandleManagedUvPlanar(const httplib::Request& req, httplib::Response& res);
void HandleManagedGameExportPrepare(const httplib::Request& req, httplib::Response& res);
void ProxyManagedCompanionRequest(
    const httplib::Request& req,
    httplib::Response& res,
    const std::string& path,
    bool isPost);
void HandleMake2d(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperStatus(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperDocument(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperQuery(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperSelection(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperCategories(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperLibrary(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperGetValue(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperSetValue(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperSetScript(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperScriptParams(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperConnections(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperDelete(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperPreview(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperClear(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperOpenDocument(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperNewDocument(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperMove(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperGroup(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperGroups(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperGroupResize(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperCluster(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperExploreSelection(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperExploreCluster(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperBatchComponentInfo(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperCreateComponent(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperCreateSlider(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperCreatePanel(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperComponent(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperInspectOutput(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperErrors(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperConnect(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperDisconnect(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperSetReference(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperGetReference(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperClearReference(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperSolve(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperSnapshot(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperEdit(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperUndo(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperCanvasFocus(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperCanvasZoom(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperCanvasImage(const httplib::Request& req, httplib::Response& res);
void HandleGrasshopperBakeOutput(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockSetLayers(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockSetLayersBatch(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockSetMaterials(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockSetMaterialsBatch(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockSetObjectColors(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockSetObjectColorsBatch(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockSetObjectNames(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockSetObjectNamesBatch(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockSetObjectUserStrings(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockSetObjectUserStringsBatch(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockTransformInstanceBatch(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockReplaceObjectGeometry(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockReplaceObjectGeometryBatch(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockTransformObject(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockTransformObjectBatch(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
