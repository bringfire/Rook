// IntersectionHandler.h
//
// POST /intersect/curves         — Curve-curve intersections
// POST /intersect/curve-surface  — Curve-surface intersections
// POST /intersect/curve-brep     — Curve-brep intersections
// POST /intersect/breps          — Brep-brep intersections
// POST /intersect/plane          — Plane-brep intersections
// POST /road/intersection/candidates — Candidate intersection analysis for two curves
// POST /road/intersection/analyze    — Candidate selection + profile-aware read-only analysis
// POST /road/intersection/commit     — Token-validated write of 2D analysis artifacts
// POST /road/intersection/resolve    — Orchestrated analyze + commit for one or all candidates

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleIntersectCurves(const httplib::Request& req, httplib::Response& res);
void HandleIntersectCurveSurface(const httplib::Request& req, httplib::Response& res);
void HandleIntersectCurveBrep(const httplib::Request& req, httplib::Response& res);
void HandleIntersectBreps(const httplib::Request& req, httplib::Response& res);
void HandleIntersectPlane(const httplib::Request& req, httplib::Response& res);
void HandleRoadIntersectionCandidates(const httplib::Request& req, httplib::Response& res);
void HandleRoadIntersectionAnalyze(const httplib::Request& req, httplib::Response& res);
void HandleRoadIntersectionCommit(const httplib::Request& req, httplib::Response& res);
void HandleRoadIntersectionResolve(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
