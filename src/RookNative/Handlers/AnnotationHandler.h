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

// POST /annotation/dot — Create a text dot (camera-facing text label
// anchored at a point).
//
// Category note: text dots are NOT annotations in the SDK sense. ON_TextDot
// subclasses ON_Geometry, not ON_Annotation, and its ObjectType() is
// ON::text_dot (not ON::annotation_object). The response therefore has
// NO `annotationType` field — the shared AnnotationTypeToString helper
// does not apply to dots. The top-level snapshot `type` field is
// "TextDot" (hard-coded in DocumentHelpers.h:127's ON::text_dot branch).
// Dots are still grouped under /annotation/* because they read as
// annotation-family from the user's POV (text labels that stay upright
// and face the camera).
//
// Required: text (non-empty string, primary label), location ([x,y,z]
//           exactly 3 numeric, dot center point).
// Optional: secondaryText (string, shown on hover/click in Rhino UI),
//           heightInPoints (JSON integer ≥ 3; default 14 per
//           ON_TextDot::DefaultHeightInPoints — rejects JSON floats
//           including 24.0, consistent with ArrayHandler's integer
//           posture), fontFace (string; default is whatever
//           ON_TextDot uses when SetFontFace is not called — empirically
//           determined and pinned in the happy-path test), name /
//           layer / color / visible (strict bundle).
//
// Response echoes effective applied values (text, secondaryText,
// heightInPoints, fontFace) read from the live dot object, NOT request
// echoes — PR-1 posture. No measuredValue field (dots have no
// dimensioned numeric quantity). GeometryHandler currently has no
// ON_TextDot branch, so GET /geometry does NOT give dot-specific detail
// (text / font / height) — verification is route-response-only for
// this PR. Richer /geometry support is follow-up hygiene.
void HandleTextDot(const httplib::Request& req, httplib::Response& res);

// POST /annotation/leader — Create a leader (text label with a polyline
// pointing at an annotated location).
//
// Leader semantics (ON::AnnotationType::Leader, wire: "Leader" per
// Rook::Serializer::AnnotationTypeToString). First point in `points` is
// the arrow tip; last point is the text anchor; intermediate points
// form polyline bends.
//
// Plane contract: the leader is constructed with `ON_Plane::World_xy`
// supplied to `CRhinoDoc::AddLeaderObject` as the text/dim-style
// orientation plane. Matches the managed implementation at
// CreateHandler.cs:1185 which also hard-codes World_xy.
//
// The SDK docstring at rhinoSdkDoc.h:3190 claims input points "will be
// projected to the plane," but empirical verification 2026-04-19 shows
// the resulting leader geometry preserves input Z — a leader built from
// points at Z=5 and Z=3 does NOT end up at Z=0. The exact Z behavior
// of input points in the resulting geometry is SDK-governed and is NOT
// part of Rook's published contract. Callers who need explicit 3D or
// non-axis-aligned leader planes should file a feature request for a
// `plane` parameter rather than relying on what the SDK happens to do.
//
// Required: text (non-empty string), points (array of [x,y,z] with at
//           least 2 entries; each point exactly 3 numeric values). No
//           `measuredValue` field in the response — leaders have no
//           dimensioned numeric quantity.
// Optional: name / layer / color / visible (strict bundle).
void HandleLeader(const httplib::Request& req, httplib::Response& res);

// POST /annotation/dim-angle — Create an angular dimension between two
// rays from a common vertex (3-point form).
//
// Angular semantics: ON::AnnotationType::Angular3pt (wire:
// "Angular3ptDimension" per Rook::Serializer::AnnotationTypeToString).
// Empirically verified 2026-04-19: the 3-point ON_DimAngular::Create
// overload produces Angular3pt, not the bare Angular type (which
// corresponds to the line-based two-line intersection overload).
//
// Required: center, start, end, point — all [x,y,z] with exactly 3 entries.
//   center: the angle vertex.
//   start:  endpoint defining the first extension ray from center.
//   end:    endpoint defining the second extension ray.
//   point:  interior of the angular dim arc. REQUIRED — load-bearing
//           for BOTH visual placement AND numeric measurement. Observed
//           Rhino 8 contract (2026-04-19): ON_DimAngular::Measurement()
//           honors the span selected by `point`. Placing `point` inside
//           the principal span returns the principal angle; placing it
//           in the reflex span (the "other way around") returns the
//           reflex angle (360° - principal). A right-angle vertex with
//           `point = [5, 5, 0]` reports 90°; the same vertex with
//           `point = [-5, -5, 0]` reports 270°. The pinned behavior is
//           verified by test_point_selects_angular_span.
// Optional: name / layer / color / visible (strict bundle).
//
// Response measuredValue is read from the constructed ON_DimAngular via
// its SDK Measurement() accessor (converted from radians to degrees).
// NOT parsed from PlainText (presentation is unsafe for numeric
// contract) and NOT computed from a pre-committed acos shortcut: Rhino
// 8's Measurement() honors reflex selection based on `point`, so an
// acos of the ray dot product would silently disagree with what the
// dim actually displays whenever `point` sits in the reflex span.
//
// `center == start` or `center == end` rejected via Unitize-fail posture.
// Colinear rays use a three-step fallback for the plane normal:
// cross(rayA, rayB), then cross(rayA, Z), then cross(rayA, Y). The chain
// fails only if all three collapse. No X-axis attempt is needed because
// rayA ∥ X is already handled by the Z attempt. Matches PR-2/PR-3
// perpendicular-construction rhythm.
void HandleDimAngle(const httplib::Request& req, httplib::Response& res);

// POST /annotation/dim-radius — Create a radial dimension measuring the
// radius of an arc or circle curve.
//
// Radial semantics (ON::AnnotationType::Radius, serialized as
// "RadialDimension" per Serializer::AnnotationTypeToString).
// measuredValue in the response is the arc's radius, computed from the
// extracted geometry (never parsed from PlainText).
//
// Required: curveId (GUID of a Rhino object whose geometry is an arc
//           or a closed circle curve).
// Optional: point ([x,y,z], dim leader text position; default = arc
//           midpoint), name / layer / color / visible (strict bundle).
// Error codes: not_found (unknown curveId), invalid_input (bad GUID or
//           curve is not arc/circle).
void HandleDimRadius(const httplib::Request& req, httplib::Response& res);

// POST /annotation/dim-diameter — Create a diameter dimension on an arc
// or circle curve.
//
// Diameter semantics (ON::AnnotationType::Diameter, serialized as
// "DiameterDimension"). Sibling to /annotation/dim-radius — same input
// shape, same SDK construction path, differs only by the AnnotationType
// enum the underlying ON_DimRadial is built with, and the measuredValue
// (2·radius).
void HandleDimDiameter(const httplib::Request& req, httplib::Response& res);

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
