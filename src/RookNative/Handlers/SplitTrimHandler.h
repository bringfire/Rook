// SplitTrimHandler.h
//
// POST /split/brep  — Split brep by cutters or plane
// POST /trim/brep   — Trim brep, keep one side
// POST /split/face  — Split a single brep face

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleSplitBrep(const httplib::Request& req, httplib::Response& res);
void HandleTrimBrep(const httplib::Request& req, httplib::Response& res);
void HandleSplitFace(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
