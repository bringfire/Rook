// GumballContextHandler.h
//
// AI Gumball v2 endpoints: context, align, appearance.
// Phase 6A additions to the gumball system.

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleGumballContext(const httplib::Request& req, httplib::Response& res);
void HandleGumballAlign(const httplib::Request& req, httplib::Response& res);
void HandleGumballAppearance(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
