// MaterialsHandler.h
//
// GET    /materials        — List all materials with usage reporting
// POST   /materials        — Create a material
// DELETE /materials        — Delete a material
// POST   /materials/assign — Assign material to object(s) or layer
// POST   /materials/purge  — Purge unused materials

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleGetMaterials(const httplib::Request& req, httplib::Response& res);
void HandleCreateMaterial(const httplib::Request& req, httplib::Response& res);
void HandleDeleteMaterial(const httplib::Request& req, httplib::Response& res);
void HandleAssignMaterial(const httplib::Request& req, httplib::Response& res);
void HandlePurgeMaterials(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
