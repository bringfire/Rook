// CurvesHandler.h
//
// POST /curve/join              — Join multiple curves
// POST /curve/explode           — Explode polycurve into segments
// POST /curve/divide            — Divide curve by count or length
// POST /curve/extend            — Extend curve at start/end
// POST /curve/trim              — Trim curve to sub-domain
// POST /curve/split             — Split curve at parameter or point
// POST /curve/rebuild           — Rebuild curve with new point count/degree
// POST /curve/fillet            — Fillet between two curves
// POST /curve/project           — Project curves onto breps
// POST /curve/pull              — Pull curve to brep face
// POST /curve/offset            — Offset curve in a plane
// POST /curve/offset-on-surface — Offset curve along a surface

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleCurveJoin(const httplib::Request& req, httplib::Response& res);
void HandleCurveExplode(const httplib::Request& req, httplib::Response& res);
void HandleCurveDivide(const httplib::Request& req, httplib::Response& res);
void HandleCurveExtend(const httplib::Request& req, httplib::Response& res);
void HandleCurveTrim(const httplib::Request& req, httplib::Response& res);
void HandleCurveSplit(const httplib::Request& req, httplib::Response& res);
void HandleCurveRebuild(const httplib::Request& req, httplib::Response& res);
void HandleCurveFillet(const httplib::Request& req, httplib::Response& res);
void HandleCurveProject(const httplib::Request& req, httplib::Response& res);
void HandleCurvePull(const httplib::Request& req, httplib::Response& res);
void HandleCurveOffset(const httplib::Request& req, httplib::Response& res);
void HandleCurveOffsetOnSurface(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
