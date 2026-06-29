// ObjectsHandler.h

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleObjects(const httplib::Request& req, httplib::Response& res);
void HandleObjectVisibility(const httplib::Request& req, httplib::Response& res);
void HandleObjectSetLayer(const httplib::Request& req, httplib::Response& res);
void HandleObjectHistory(const httplib::Request& req, httplib::Response& res);
void HandleObjectsWithHistory(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
