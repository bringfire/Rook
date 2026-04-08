// MeasureHandler.h
//
// GET|POST /measure/distance — Point or object distance
// GET|POST /measure/area     — Surface/mesh area
// GET|POST /measure/volume   — Solid volume
// GET|POST /measure/length   — Curve length
// GET|POST /measure/bbox     — Bounding box dimensions
// GET|POST /measure/centroid — Centroid position

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleMeasureDistance(const httplib::Request& req, httplib::Response& res);
void HandleMeasureArea(const httplib::Request& req, httplib::Response& res);
void HandleMeasureVolume(const httplib::Request& req, httplib::Response& res);
void HandleMeasureLength(const httplib::Request& req, httplib::Response& res);
void HandleMeasureBbox(const httplib::Request& req, httplib::Response& res);
void HandleMeasureCentroid(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
