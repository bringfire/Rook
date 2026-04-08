// SessionHandler.h
//
// Session recording HTTP endpoint declarations.
// 4 endpoints, 4 route registrations.

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleSessionCurrent(const httplib::Request& req, httplib::Response& res);
void HandleSessionHistory(const httplib::Request& req, httplib::Response& res);
void HandleSessionList(const httplib::Request& req, httplib::Response& res);
void HandleSessionExport(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
