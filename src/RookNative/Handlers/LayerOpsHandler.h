// LayerOpsHandler.h
//
// POST   /layers                — Create a layer
// POST   /layers/batch          — Create multiple layers atomically
// DELETE /layers                — Delete a layer
// POST   /layers/visibility     — Show/hide a layer
// POST   /layers/lock           — Lock/unlock a layer
// POST   /layers/current        — Set current layer
// POST   /layers/properties     — Set any combination of layer properties
// POST   /layers/properties-batch — Best-effort batch of set-properties
// POST   /layers/rename         — Rename a layer
// POST   /layers/move-objects   — Move all objects from one layer to another
// POST   /layers/merge          — Move objects + delete source layer
// GET    /layers/dependencies   — What holds a layer alive

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleCreateLayer(const httplib::Request& req, httplib::Response& res);
void HandleCreateLayersBatch(const httplib::Request& req, httplib::Response& res);
void HandleDeleteLayer(const httplib::Request& req, httplib::Response& res);
void HandleLayerVisibility(const httplib::Request& req, httplib::Response& res);
void HandleLayerLock(const httplib::Request& req, httplib::Response& res);
void HandleLayerCurrent(const httplib::Request& req, httplib::Response& res);
void HandleLayerSetProperties(const httplib::Request& req, httplib::Response& res);
void HandleLayerSetPropertiesBatch(const httplib::Request& req, httplib::Response& res);
void HandleLayerRename(const httplib::Request& req, httplib::Response& res);
void HandleLayerMoveObjects(const httplib::Request& req, httplib::Response& res);
void HandleLayerMerge(const httplib::Request& req, httplib::Response& res);
void HandleLayerDependencies(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
