// LayerOpsHandler.h
//
// POST   /layers            — Create a layer
// POST   /layers/batch      — Create multiple layers atomically
// DELETE /layers            — Delete a layer
// POST   /layers/visibility — Show/hide a layer
// POST   /layers/lock       — Lock/unlock a layer
// POST   /layers/current    — Set current layer

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

} // namespace Handlers
} // namespace Rook
