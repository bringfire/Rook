// MeshHandler.h
//
// POST /mesh/from-brep   — Mesh a brep with meshing params
// POST /mesh/box         — Create mesh box primitive
// POST /mesh/sphere      — Create mesh sphere primitive
// POST /mesh/cylinder    — Create mesh cylinder primitive
// POST /mesh/cone        — Create mesh cone primitive
// POST /mesh/boolean     — Union/difference/intersection of meshes
// POST /mesh/reduce      — Reduce mesh face count
// POST /mesh/quad-remesh — QuadRemesh with target count
// POST /mesh/repair      — Fill holes, rebuild normals, compact
// POST /mesh/smooth      — Laplacian smoothing with iterations
// POST /mesh/weld        — Weld vertices by angle
// POST /mesh/unweld      — Unweld vertices by angle

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleMeshFromBrep(const httplib::Request& req, httplib::Response& res);
void HandleMeshBox(const httplib::Request& req, httplib::Response& res);
void HandleMeshSphere(const httplib::Request& req, httplib::Response& res);
void HandleMeshCylinder(const httplib::Request& req, httplib::Response& res);
void HandleMeshCone(const httplib::Request& req, httplib::Response& res);
void HandleMeshBoolean(const httplib::Request& req, httplib::Response& res);
void HandleMeshReduce(const httplib::Request& req, httplib::Response& res);
void HandleMeshQuadRemesh(const httplib::Request& req, httplib::Response& res);
void HandleMeshRepair(const httplib::Request& req, httplib::Response& res);
void HandleMeshSmooth(const httplib::Request& req, httplib::Response& res);
void HandleMeshWeld(const httplib::Request& req, httplib::Response& res);
void HandleMeshUnweld(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
