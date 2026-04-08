// OffsetBrepHandler.h
//
// POST /offset/brep — Offset brep with blend/wall surfaces

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleOffsetBrep(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
