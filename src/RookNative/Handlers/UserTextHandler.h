// UserTextHandler.h
//
// Phase 2 typed user-text routes.
//   - PR-9 established /usertext/object-set + /usertext/object-get
//     on per-object ON_3dmObjectAttributes user strings.
//   - PR-10 extends this handler with document-level routes
//     (/usertext/document-set + /usertext/document-get), activates
//     the reserved-prefix denylist on the document write, and
//     introduces the first Phase 2 route-local error code
//     (reserved_namespace).
//
// Substrate: direct-sdk (native C++) — see UserTextHandler.cpp header
// for the full Rule 6 rationale. Not re-declared for PR-10 per the
// PR-9 plan's acceptance gate #1 ("PR-10 should extend the same
// handler without re-declaring substrate").
//
// Family convention: object-level routes operate on an object's
// ON_3dmObjectAttributes user-string store via SetUserString /
// GetUserString / GetUserStringKeys; document-level routes operate on
// CRhinoDoc user strings via the same verbs. Object-level routes are
// NOT gated by the reserved-prefix denylist (attributes are per-object
// storage with no cross-subsystem namespace contract); only
// document-level WRITES are gated. Reads remain unrestricted at both
// levels so operators can inspect reserved keys for diagnostics.
//
// Delete is out of scope for PR-9 AND PR-10. Empty-string values are
// REJECTED (invalid_input) at both levels to prevent sneak-delete
// through the set routes — empirical verification 2026-04-19:
//   - Attribute level: attrs.SetUserString(key, "") deletes the key.
//   - Document level:  pDoc->SetUserString(key, "") ALSO deletes the
//     key (probed via RhinoDoc.Strings.SetString(k, "") which maps
//     directly to the native call: count drops 1→0, GetValue returns
//     None, key absent from enumeration).
// Accepting empty strings at either level would silently deliver
// delete semantics before the explicit /usertext/object-delete and
// /usertext/document-delete routes are designed. A follow-up PR
// introduces the sanctioned delete paths.

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

// POST /usertext/document-set — Write user strings (arbitrary
// key/value metadata) on the active document. Document-level scope:
// no `id` field in the request or response.
//
// Required: userStrings (JSON object of {string: non-empty-string}
//           pairs — empty-string values are rejected, see below).
//
// Empty userStrings ({}): idempotent no-op. Returns the document's
// current user-string map unchanged, without opening an UndoScope or
// calling Redraw (declared no-ops leave no fingerprint).
//
// Empty-string value ({"key": ""}): REJECTED with invalid_input and
// a key-specific message. OpenNURBS treats pDoc->SetUserString(k, "")
// as a delete sentinel at the document level (empirically confirmed
// 2026-04-19); rejecting at the handler avoids a sneak-delete path
// through /usertext/document-set until the explicit
// /usertext/document-delete surface lands.
//
// Reserved-prefix denylist (WRITES ONLY — document-get is
// unrestricted): keys whose prefix matches any entry in
// UserTextHandler.cpp's kReservedPrefixes table are REJECTED with
// the new route-local error code `reserved_namespace`. The error
// message names the offending prefix, the subsystem that owns it,
// and where possible points the caller at the sanctioned alternative.
// Current table:
//   - "RookBlock::" — owned by block-definition metadata
//     (BlocksHandler); callers should use /block/user-strings.
// Reads (/usertext/document-get, /usertext/object-get) bypass the
// denylist so operators can inspect reserved keys for diagnostics.
//
// Rejection is WHOLESALE: the handler validates EVERY key in the
// request map before opening an UndoScope or calling SetUserString.
// A mixed map like {allowed: "v", "RookBlock::X": "v"} fails with
// reserved_namespace on the reserved key AND does not write the
// allowed key either. This prevents silent partial-success footguns
// and matches the validate-before-mutate rhythm from PR-9.
//
// Response: {userStrings: {...}} — full post-mutation map read back
// via pDoc->GetUserStringKeys. No `id` field (plan acceptance gate
// #2: "Object routes echo `id`; doc routes do not").
//
// Error codes: invalid_input (missing/malformed userStrings,
// non-object userStrings, non-string value, empty-string value),
// reserved_namespace (key prefix is reserved — first-match
// short-circuit, error message names the prefix and owner),
// operation_failed (pDoc->SetUserString returned false).
void HandleUserTextDocumentSet(const httplib::Request& req, httplib::Response& res);

// POST /usertext/document-get — Read all user strings on the active
// document. No id field; scope is the active document.
//
// Body: accepts empty body (no content) AND empty JSON object `{}`.
// ParseBodyAndDocSn already normalizes empty bodies to `{}`.
//
// Response: {userStrings: {...}} — ALL keys, including any reserved-
// prefix keys present in the document. Reads are deliberately
// unrestricted so operators can inspect reserved namespaces for
// diagnostics. No `id` field.
//
// Error codes: base set only — operation_failed is unreachable for
// a pure read, so in practice this route returns success or nothing
// meaningful to classify.
void HandleUserTextDocumentGet(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
