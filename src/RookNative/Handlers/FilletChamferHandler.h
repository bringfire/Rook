// FilletChamferHandler.h
//
// POST /fillet  — Fillet edges of a brep
// POST /chamfer — Chamfer edges of a brep
// POST /offset  — Offset a curve or brep surface

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleFillet(const httplib::Request& req, httplib::Response& res);
void HandleChamfer(const httplib::Request& req, httplib::Response& res);
void HandleOffset(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
