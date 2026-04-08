// PromptHandler.h
//
// User interaction prompt HTTP endpoints.
// 5 endpoints for point, object, objects, subobject, and distance picking.

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandlePromptPoint(const httplib::Request& req, httplib::Response& res);
void HandlePromptObject(const httplib::Request& req, httplib::Response& res);
void HandlePromptObjects(const httplib::Request& req, httplib::Response& res);
void HandlePromptSubObject(const httplib::Request& req, httplib::Response& res);
void HandlePromptDistance(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
