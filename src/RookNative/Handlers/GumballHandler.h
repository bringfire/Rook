// GumballHandler.h
//
// AI Gumball endpoints: activate, deactivate, status, history.
// Persistent gumball mode for AI-driven transform workflows.

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleGumballActivate(const httplib::Request& req, httplib::Response& res);
void HandleGumballDeactivate(const httplib::Request& req, httplib::Response& res);
void HandleGumballStatus(const httplib::Request& req, httplib::Response& res);
void HandleGumballHistory(const httplib::Request& req, httplib::Response& res);
void HandleGumballSettings(const httplib::Request& req, httplib::Response& res);
void HandleGumballExtrude(const httplib::Request& req, httplib::Response& res);
void HandleGumballCut(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
