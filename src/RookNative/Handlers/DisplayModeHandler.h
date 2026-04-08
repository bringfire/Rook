// DisplayModeHandler.h
//
// GET  /display-modes  — List all display modes (built-in + custom)
// POST /display-mode   — Set active viewport display mode persistently

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleGetDisplayModes(const httplib::Request& req, httplib::Response& res);
void HandleSetDisplayMode(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
