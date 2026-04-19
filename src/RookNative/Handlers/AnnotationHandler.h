// AnnotationHandler.h
//
// Phase 2 typed annotation-creation routes. Established by PR-1
// (/annotation/text). Subsequent PRs extend this header with
// dim-linear, dim-aligned, dim-radius/diameter, dim-angle, leader, dot,
// and (contingent on an SDK spike) hatch.
//
// Substrate: direct-sdk (native C++) — see AnnotationHandler.cpp header
// for the full Rule 6 rationale and the gap-analysis 2026-04-19 decision
// that moved this family off managed-bridge reuse.
//
// See rook_docs/2026-04-19-typed-route-phase2-plan.md §"Worked Example:
// /annotation/text" for the canonical execution-block spec and acceptance
// gate for the family.

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

// POST /annotation/dim-aligned — Create an ALIGNED dimension between
// two points.
//
// ALIGNED semantics (ON::AnnotationType::Aligned, serialized as
// "AlignedDimension" per GeometryHandler.cpp:25): measures the direct
// Euclidean distance between start and end, with the dim plane tilting
// to match the start→end direction. Contrast with LINEAR (PR-2), which
// measures the projection onto a user-specified direction. A dim
// between [0,0,0] and [10,5,0] returns ~11.18 (slant), not 10.0.
//
// Required: start ([x,y,z]), end ([x,y,z]), offset (number, perpendicular
//           distance from the midpoint in the dim plane).
// Optional: name / layer / color / visible (strict bundle).
// Explicitly rejected: `direction` is invalid_input on this route —
//   ALIGNED has no projection direction; use /annotation/dim-linear if
//   you want a projection parameter.
//
// Response echoes annotationType (from the live object, post-insertion)
// plus measuredValue = (end - start).Length() — computed from geometry
// math, never parsed from PlainText.
void HandleDimAligned(const httplib::Request& req, httplib::Response& res);

// POST /annotation/dim-linear — Create a LINEAR dimension between two
// points, measured along a user-specified projection direction.
//
// LINEAR semantics (ON::AnnotationType::Rotated, serialized as
// "LinearDimension" per GeometryHandler.cpp:30): measures the projected
// distance of (end - start) onto the `direction` vector. Contrast with
// ALIGNED (PR-3), which measures the direct Euclidean distance. A
// horizontal dim of two points differing in both X and Y returns the
// X-projection, not the slant distance.
//
// Required: start ([x,y,z]), end ([x,y,z]), offset (number, perpendicular
//           distance from the start-end midpoint in the dim plane).
// Optional: direction ([x,y,z], default [1,0,0] world X; must be
//           non-zero — Unitize-fail semantics reused from the legacy
//           factory), name / layer / color / visible (strict bundle).
//
// Response echoes annotationType (from the live object's
// AnnotationType(), post-insertion) plus measuredValue (the projection
// used to construct the dim — never parsed from PlainText, which is
// presentation, not contract).
void HandleDimLinear(const httplib::Request& req, httplib::Response& res);

// POST /annotation/text — Create a 2D text annotation.
//
// Required: text (non-empty string).
// Optional: point ([x,y,z], exactly 3 numbers, default [0,0,0]),
//           height (> 0, default 1.0),
//           font (string family name, default "Arial"; if the requested
//                 font cannot be applied, falls back to the document
//                 default font),
//           bold (bool, default false), italic (bool, default false),
//           name / layer / color / visible (strict attribute bundle —
//           malformed types surface as invalid_input, not silent-drop).
//
// The success payload echoes the EFFECTIVE applied typography (font,
// bold, italic, height) read from the created annotation, not the
// request. Font-fallback cases are observable without a follow-up read.
void HandleText(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
