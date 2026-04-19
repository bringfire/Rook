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

// POST /annotation/text — Create a 2D text annotation.
//
// Required: text (non-empty string).
// Optional: point ([x,y,z], default origin), height (> 0, default 1.0),
//           font (string, default document default), bold (bool, default
//           false), italic (bool, default false),
//           name / layer / color / visible (strict attribute bundle).
//
// Font-characteristic failures fall back to the document default font —
// the success payload echoes the EFFECTIVE applied typography (font,
// bold, italic, height) read from the created annotation, not the request.
void HandleText(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
