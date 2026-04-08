// ShapeMetrics.h
//
// Shared shape-metric struct and classification utilities.
// Header-only — no .vcxproj changes required.
// Extracted from CSceneGraph for reuse by BlocksHandler and others.

#pragma once

#include <array>
#include <algorithm>
#include <cmath>
#include <string>

namespace Rook {

// ─── Shape Metrics ─────────────────────────────────────────────
// Derived entirely from axis-aligned bounding box. Ratios are dimensionless.

struct ShapeMetrics {
    double maxDim = 0, midDim = 0, minDim = 0;
    double elongation = 0;    // maxDim / midDim
    double flatness = 0;      // midDim / minDim
    double thinness = 0;      // minDim / maxDim
    double centroidZ = 0;
    double baseZ = 0, topZ = 0;
    std::string primaryAxis;  // "X", "Y", "Z" — axis of maxDim
    std::string thinAxis;     // "X", "Y", "Z" — axis of minDim
    bool isVertical = false;  // thinAxis != "Z"
    bool isHorizontal = false; // thinAxis == "Z"
    double volume = 0;
    double floorArea = 0;
};

// ─── Compute metrics from axis-aligned bounding box ────────────

inline ShapeMetrics ComputeMetrics(const std::array<double,3>& bmin, const std::array<double,3>& bmax)
{
    double dx = bmax[0] - bmin[0];
    double dy = bmax[1] - bmin[1];
    double dz = bmax[2] - bmin[2];

    double dims[3] = { dx, dy, dz };
    std::sort(std::begin(dims), std::end(dims));
    double minDim = (std::max)(dims[0], 0.0001);
    double midDim = (std::max)(dims[1], 0.0001);
    double maxDim = (std::max)(dims[2], 0.0001);

    std::string primaryAxis;
    if (std::abs(maxDim - dz) < 0.0001) primaryAxis = "Z";
    else if (std::abs(maxDim - dy) < 0.0001) primaryAxis = "Y";
    else primaryAxis = "X";

    std::string thinAxis;
    if (std::abs(minDim - dz) < 0.0001) thinAxis = "Z";
    else if (std::abs(minDim - dy) < 0.0001) thinAxis = "Y";
    else thinAxis = "X";

    ShapeMetrics m;
    m.maxDim = maxDim;
    m.midDim = midDim;
    m.minDim = minDim;
    m.elongation = maxDim / midDim;
    m.flatness = midDim / minDim;
    m.thinness = minDim / maxDim;
    m.centroidZ = (bmin[2] + bmax[2]) / 2.0;
    m.baseZ = bmin[2];
    m.topZ = bmax[2];
    m.primaryAxis = primaryAxis;
    m.thinAxis = thinAxis;
    m.isVertical = (thinAxis != "Z");
    m.isHorizontal = (thinAxis == "Z");
    m.volume = dx * dy * dz;
    m.floorArea = dx * dy;
    return m;
}

// ─── Classify shape from metrics ───────────────────────────────

inline std::string DetermineShapeClass(const ShapeMetrics& m)
{
    if (m.flatness > 3.0)
    {
        if (m.thinAxis == "Z") return "horizontal-slab";
        return "vertical-planar";
    }
    if (m.elongation > 3.0)
    {
        if (m.primaryAxis == "Z") return "thin-vertical";
        return "thin-horizontal";
    }
    if (m.elongation < 2.0 && m.flatness < 2.0)
        return "compact";

    return "irregular";
}

} // namespace Rook
