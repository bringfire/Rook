// SelectionHandler.h
//
// GET  /selection — Get currently selected objects
// POST /select    — Select/deselect objects by various criteria

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleGetSelection(const httplib::Request& req, httplib::Response& res);
void HandleSelect(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
