// AnalysisHandler.h
//
// POST /analysis/curvature-curve   — Curvature at curve parameter
// POST /analysis/curvature-surface — Curvature at surface UV point
// POST /analysis/draft-angle       — Draft angle per brep face
// POST /analysis/closest-point     — Closest point on any geometry
// POST /analysis/curve-point-at    — Point at curve parameter
// POST /analysis/curve-tangent     — Tangent at curve parameter
// POST /analysis/curve-frame       — Frame (plane) at curve parameter
// POST /analysis/surface-normal    — Normal at surface UV point
// POST /analysis/brep-edges        — List brep edges with topology
// POST /analysis/brep-faces        — List brep faces with area/normal
// POST /analysis/brep-vertices     — List brep vertices with edges
// POST /analysis/is-closed         — Check if geometry is closed/solid
// POST /analysis/is-valid          — Validate geometry with log

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleCurvatureCurve(const httplib::Request& req, httplib::Response& res);
void HandleCurvatureSurface(const httplib::Request& req, httplib::Response& res);
void HandleDraftAngle(const httplib::Request& req, httplib::Response& res);
void HandleClosestPoint(const httplib::Request& req, httplib::Response& res);
void HandleCurvePointAt(const httplib::Request& req, httplib::Response& res);
void HandleCurveTangent(const httplib::Request& req, httplib::Response& res);
void HandleCurveFrame(const httplib::Request& req, httplib::Response& res);
void HandleSurfaceNormal(const httplib::Request& req, httplib::Response& res);
void HandleBrepEdges(const httplib::Request& req, httplib::Response& res);
void HandleBrepFaces(const httplib::Request& req, httplib::Response& res);
void HandleBrepVertices(const httplib::Request& req, httplib::Response& res);
void HandleIsClosed(const httplib::Request& req, httplib::Response& res);
void HandleIsValid(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
