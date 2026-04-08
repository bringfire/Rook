// TextureMappingHandler.h
//
// POST /material/uv-box       — Apply box UV mapping
// POST /material/uv-planar    — Apply planar UV mapping
// POST /material/uv-cylinder  — Apply cylinder UV mapping
// POST /material/uv-sphere    — Apply spherical UV mapping

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleUvBox(const httplib::Request& req, httplib::Response& res);
void HandleUvPlanar(const httplib::Request& req, httplib::Response& res);
void HandleUvCylinder(const httplib::Request& req, httplib::Response& res);
void HandleUvSphere(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
