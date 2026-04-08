// GeometryOpsHandler.h

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleDelete(const httplib::Request& req, httplib::Response& res);
void HandleTransform(const httplib::Request& req, httplib::Response& res);
void HandleCopy(const httplib::Request& req, httplib::Response& res);
void HandleUndo(const httplib::Request& req, httplib::Response& res);
void HandleRedo(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
