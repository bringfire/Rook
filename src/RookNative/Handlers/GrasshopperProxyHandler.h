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
void HandleManagedBlockSetMaterials(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockSetObjectColors(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockSetObjectNames(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockSetObjectUserStrings(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockReplaceObjectGeometry(const httplib::Request& req, httplib::Response& res);
void HandleManagedBlockTransformObject(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
