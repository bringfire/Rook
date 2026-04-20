// UserTextHandler.h
//
// Phase 2 typed user-text routes. Established by PR-9
// (/usertext/object-set + /usertext/object-get). PR-10 extends this
// handler with document-level routes (/usertext/document-set +
// /usertext/document-get) and activates the reserved-prefix denylist on
// the document write.
//
// Substrate: direct-sdk (native C++) — see UserTextHandler.cpp header
// for the full Rule 6 rationale (per plan:
// rook_docs/2026-04-19-typed-route-phase2-plan.md §"Worked Example:
// /usertext/object-set").
//
// Family convention: object-level routes operate on an object's
// ON_3dmObjectAttributes user-string store via SetUserString /
// GetUserString / GetUserStringKeys; document-level routes (PR-10)
// operate on CRhinoDoc user strings via the same verbs. Object-level
// routes are NOT gated by the reserved-prefix denylist (attributes are
// per-object storage with no cross-subsystem namespace contract); only
// document-level writes are gated.
//
// Delete is out of scope for PR-9. Empty-string values are REJECTED
// (invalid_input) to prevent sneak-delete through the set route — the
// SDK treats attrs.SetUserString(key, "") as a delete sentinel, so
// accepting empty strings would silently deliver delete semantics
// before the explicit /usertext/object-delete surface is designed.
// A follow-up route introduces the sanctioned delete path.

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

// POST /usertext/object-set — Write user strings (arbitrary key/value
// metadata) on a document object's attributes.
//
// Required: id (uuid-string of a document object), userStrings (JSON
//           object of {string: non-empty-string} pairs — empty-string
//           values are rejected, see below).
// Empty userStrings ({}): idempotent no-op. Returns the object's
// current user-string map unchanged, without opening an UndoScope or
// calling Redraw (declared no-ops leave no fingerprint).
//
// Empty-string value ({"key": ""}): REJECTED with invalid_input and
// a key-specific message. OpenNURBS treats empty values as a delete
// sentinel at the attribute level, and delete is out of scope for
// PR-9 (see file-header comment); rejecting at the handler avoids a
// sneak-delete path through /usertext/object-set until the explicit
// /usertext/object-delete surface lands.
//
// Non-string values (e.g. number, null, nested object): rejected with
// structured invalid_input whose message names the offending key —
// "userStrings['<key>'] must be a string". Deliberate strict-attrs-
// by-day-one posture; diverges from the legacy block-handler path at
// BlocksHandler.cpp:2550-2551 which silently coerces non-strings to
// "" — typed Phase 2 routes do not inherit that leniency.
//
// Response: {id, userStrings: {...}} — the FULL post-mutation
// user-string map, read back from the live object's persisted
// attributes via LookupObject-after-ModifyObjectAttributes (mirrors
// BlocksHandler.cpp:2565 pattern). Not a synthesis from the request
// body. Callers can verify what persisted without a follow-up read,
// including keys set by prior calls that this request did not touch.
//
// Error codes: invalid_input (missing/malformed id, missing
// userStrings, non-object userStrings, non-string value,
// empty-string value), not_found (unknown object id — structured
// via StructuredError), operation_failed (ModifyObjectAttributes
// returned false).
//
// Strict-attrs bundle (name/layer/color/visible): NOT accepted. This
// route mutates the attribute user-string store only; it does not
// accept attribute-bundle inputs. A separate route handles
// attribute-bundle mutation.
void HandleUserTextObjectSet(const httplib::Request& req, httplib::Response& res);

// POST /usertext/object-get — Read all user strings on a document
// object's attributes.
//
// Required: id (uuid-string of a document object).
// Response: {id, userStrings: {...}} — empty object {} if the
// object has no user strings set. Keys returned in SDK enumeration
// order (not guaranteed stable across Rhino versions).
//
// Error codes: invalid_input (missing/malformed id), not_found
// (unknown object id — structured via StructuredError).
void HandleUserTextObjectGet(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
