// GeometryHandler.h

#pragma once

#include "Models/Snapshots.h"  // GeometryDetail, AttributeSnapshot

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleGeometry(const httplib::Request& req, httplib::Response& res);

// Shared capture utilities (used by GeometryHandler and BlocksHandler)
GeometryDetail CaptureGeometryDetail(const CRhinoObject* obj, const ON_Geometry* geom,
                                      const CRhinoDoc* pDoc, std::string& outType);
AttributeSnapshot CaptureAttributes(const ON_3dmObjectAttributes& attrs);

} // namespace Handlers
} // namespace Rook
