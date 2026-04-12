// LinetypesHandler.h
//
// GET  /linetypes       — List all linetypes with usage reporting
// POST /linetypes/purge — Purge unused linetypes

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleGetLinetypes(const httplib::Request& req, httplib::Response& res);
void HandlePurgeLinetypes(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
