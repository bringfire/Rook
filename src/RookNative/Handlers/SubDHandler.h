// SubDHandler.h
//
// POST /subd/box          — Create SubD box primitive
// POST /subd/sphere       — Create SubD sphere primitive
// POST /subd/cylinder     — Create SubD cylinder primitive
// POST /subd/from-mesh    — Convert mesh to SubD
// POST /subd/from-surface — Convert surface/brep to SubD
// POST /subd/subdivide    — Global subdivision (N levels)
// POST /subd/crease       — Set edge crease tags
// POST /subd/to-brep      — Convert SubD to brep
// POST /subd/to-mesh      — Convert SubD to mesh

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleSubDBox(const httplib::Request& req, httplib::Response& res);
void HandleSubDSphere(const httplib::Request& req, httplib::Response& res);
void HandleSubDCylinder(const httplib::Request& req, httplib::Response& res);
void HandleSubDFromMesh(const httplib::Request& req, httplib::Response& res);
void HandleSubDFromSurface(const httplib::Request& req, httplib::Response& res);
void HandleSubDSubdivide(const httplib::Request& req, httplib::Response& res);
void HandleSubDCrease(const httplib::Request& req, httplib::Response& res);
void HandleSubDToBrep(const httplib::Request& req, httplib::Response& res);
void HandleSubDToMesh(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
