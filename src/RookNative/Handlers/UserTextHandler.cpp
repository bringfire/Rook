// UserTextHandler.cpp
//
// Phase 2 typed user-text routes. See plan:
//   rook_docs/2026-04-19-typed-route-phase2-plan.md
//   §"Worked Example: /usertext/object-set" (PR-9) +
//   PR-10 extension block (/usertext/document-* + reserved-prefix
//   denylist + `reserved_namespace` error code).
//
// Substrate: direct-sdk (native C++).
//   - Native owns: HTTP entry, JSON parse, schema validation, attribute
//     user-string mutation (ON_3dmObjectAttributes::SetUserString) via
//     pDoc->ModifyObjectAttributes, post-write readback via LookupObject,
//     response envelope.
//   - Managed owns nothing here.
//
// Substrate rationale (per gap-analysis 2026-04-19 decision + PR-9
// scope pass, binding under Decision Record Rule 6):
//   (a) RookNative is the public HTTP surface; managed is internal
//       companion. Typed routes belong on the public substrate.
//   (b) ON_3dmObjectAttributes::SetUserString / GetUserString /
//       GetUserStringKeys are raw SDK — no RhinoCommon affordance
//       needed. The block-user-strings path at BlocksHandler.cpp:2551
//       and the per-object block set at BlocksHandler.cpp:3714 prove
//       the pattern works direct-native.
//   (c) Routing through managed would introduce a new bridge_unavailable
//       / 503 mode for operations that have no bridge dependency today.
//
// Strict posture: Phase 2 typed routes enforce strict value validation
// from day one. Non-string values in the userStrings map are rejected
// with a key-specific invalid_input message, rather than silently
// coerced to "" as the legacy block-handler path does at
// BlocksHandler.cpp:2550-2551. Callers that want lax coercion can
// continue to use the block-specific routes; /usertext/* is strict.
//
// Empty-string values are ALSO rejected with invalid_input at BOTH
// levels (object and document). Empirical findings 2026-04-19:
//   - Attribute level: ON_3dmObjectAttributes::SetUserString(key, "")
//     treats the empty string as a delete sentinel — the key is
//     removed from the attribute user-string store, not persisted.
//   - Document level: pDoc->SetUserString(key, "") has the SAME
//     delete behavior (probed via RhinoDoc.Strings.SetString(k, "")
//     during the PR-10 empirical pre-flight: count dropped 1→0,
//     GetValue returned None, key absent from enumeration).
// Accepting empty-string writes at either level would silently
// deliver delete semantics through the set surfaces before the
// explicit /usertext/object-delete and /usertext/document-delete
// routes are designed — with different response/error contracts
// from what the eventual delete routes will provide. PR-9 and PR-10
// both reject empty strings at the handler and require callers to
// wait for the sanctioned delete surface.
//
// Reserved-prefix denylist (PR-10, /usertext/document-set only):
// document-level writes reject keys whose prefix matches any entry
// in kReservedPrefixes (anon-namespace constant table). Violations
// surface the route-local error code `reserved_namespace` with a
// message that names the offending prefix, the subsystem that owns
// it, and where possible the sanctioned alternative. Rejection is
// WHOLESALE: all keys are validated BEFORE any SetUserString call,
// so a mixed map cannot produce partial writes. Object-level writes
// are NOT gated (per-object attribute storage has no cross-subsystem
// namespace contract today). Reads at both levels are unrestricted
// so operators can inspect reserved keys for diagnostics.
//
// Response echo policy: success payloads for /usertext/object-set are
// the EFFECTIVE post-mutation user-string map, read back from the live
// object's persisted attributes via LookupObject-after-
// ModifyObjectAttributes (mirrors BlocksHandler.cpp:2565). This is
// deliberately NOT a synthesis from the request body — it surfaces
// keys set by prior calls that the current request did not touch,
// giving callers visibility into the full persisted state without a
// follow-up /usertext/object-get read.
//
// Declared-no-op policy: if `userStrings` is an empty object {}, the
// handler returns the current map unchanged without opening an
// UndoScope or calling Redraw. Declared no-ops leave no fingerprint.
// All reads still dispatch through CMainThreadDispatcher per the
// Rhino UI-thread contract (Threading/MainThreadDispatcher.h).

#include "stdafx.h"
#include "Handlers/UserTextHandler.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/WriteResult.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <nlohmann/json.hpp>
#include <set>
#include <string>
#include <unordered_set>
#include <vector>

namespace Rook {
namespace Handlers {

namespace {

constexpr size_t kMaxUserTextObjectSetBatchItems = 500;

// Structured-error carrier. Mirrors AnnotationHandler.cpp:75-90 (and
// ArrayHandler.cpp:46-63) so the top-level catch can emit specific
// codes (e.g. "not_found") without routing through std::invalid_argument
// (which the catch maps uniformly to "invalid_input").
struct StructuredError : public std::exception
{
    StructuredError(std::string codeIn, std::string messageIn)
        : code(std::move(codeIn)), message(std::move(messageIn)),
          whatCache(code + ": " + message)
    {
    }

    const char* what() const noexcept override { return whatCache.c_str(); }

    std::string code;
    std::string message;

private:
    std::string whatCache;
};

struct DirtyUserTextOperationError : public std::exception
{
    DirtyUserTextOperationError(ON_UUID idIn,
                                std::string operationIn,
                                std::string messageIn)
        : id(idIn),
          operation(std::move(operationIn)),
          message(std::move(messageIn)),
          whatCache(operation + ": " + message)
    {
    }

    const char* what() const noexcept override { return whatCache.c_str(); }

    ON_UUID id;
    std::string operation;
    std::string message;

private:
    std::string whatCache;
};

struct UserTextSetBatchItem
{
    ON_UUID id = ON_nil_uuid;
    nlohmann::json userStrings = nlohmann::json::object();
};

// Resolve `id` on `pDoc`. Throws StructuredError with explicit code
// the top-level catch translates into a structured error envelope.
// Mirrors AnnotationHandler.cpp's ExtractArcFromCurveId resolution
// rhythm.
const CRhinoObject* LookupObjectStrict(const ON_UUID& id, CRhinoDoc* pDoc)
{
    const CRhinoObject* obj = pDoc->LookupObject(id);
    if (!obj)
        throw StructuredError("not_found",
            "Object not found: " + UuidToString(id));
    return obj;
}

// Validate `userStrings` is a JSON object of string→non-empty-string
// pairs. Throws std::invalid_argument (mapped to invalid_input by the
// top-level catch) on:
//   - missing field
//   - non-object type
//   - any non-string value (key-specific message)
//   - any empty-string value (key-specific message — empty strings
//     would delete the key via SDK convention at BOTH the attribute
//     and document level; delete is out of scope for PR-9/PR-10; see
//     file-header comment)
// Empty object {} is accepted — callers use it as an idempotent no-op.
//
// `deleteRouteHint` is the name of the sanctioned delete route the
// caller should wait for (e.g. "/usertext/object-delete" for object
// routes, "/usertext/document-delete" for document routes). Appended
// to the empty-string error message so callers see the right
// forward-reference.
void ValidateUserStringsObjectStrict(const nlohmann::json& body,
                                     const char* deleteRouteHint)
{
    if (!body.contains("userStrings"))
        throw std::invalid_argument("Missing required field: userStrings");
    if (!body["userStrings"].is_object())
        throw std::invalid_argument("'userStrings' must be an object");

    for (auto it = body["userStrings"].begin(); it != body["userStrings"].end(); ++it)
    {
        if (!it.value().is_string())
        {
            throw std::invalid_argument(
                "userStrings['" + it.key() + "'] must be a string");
        }
        if (it.value().get<std::string>().empty())
        {
            throw std::invalid_argument(
                std::string("userStrings['") + it.key() + "'] must be non-empty "
                "(empty-string values delete the key under the SDK "
                "contract; delete is not yet supported — wait for "
                + deleteRouteHint + ")");
        }
    }
}

void RejectDuplicateUuid(std::unordered_set<std::string>& seen,
                         const std::string& id)
{
    if (!seen.insert(id).second)
        throw std::invalid_argument("Duplicate object id: " + id);
}

void ValidateBatchUserStringsObjectStrict(const nlohmann::json& userStrings,
                                          size_t itemIndex)
{
    if (!userStrings.is_object())
    {
        throw std::invalid_argument(
            "items[" + std::to_string(itemIndex) + "].userStrings must be an object");
    }

    for (auto it = userStrings.begin(); it != userStrings.end(); ++it)
    {
        const std::string key = it.key();
        const auto& valueJson = it.value();
        if (key.empty())
        {
            throw std::invalid_argument(
                "items[" + std::to_string(itemIndex) + "].userStrings keys must be non-empty");
        }
        if (!valueJson.is_string())
        {
            throw std::invalid_argument(
                "items[" + std::to_string(itemIndex) + "].userStrings['"
                + key + "'] must be a string");
        }
        const std::string value = valueJson.get<std::string>();
        if (value.empty())
        {
            throw std::invalid_argument(
                "items[" + std::to_string(itemIndex) + "].userStrings['"
                + key + "'] must be non-empty");
        }
    }
}

std::vector<UserTextSetBatchItem> ParseUserTextSetBatchItems(
    const nlohmann::json& body)
{
    if (!body.contains("items") || !body["items"].is_array())
        throw std::invalid_argument("Missing or invalid array: items");

    const auto& items = body["items"];
    if (items.empty())
        throw std::invalid_argument("'items' must contain at least one object");
    if (items.size() > kMaxUserTextObjectSetBatchItems)
        throw std::invalid_argument("'items' cannot exceed 500 objects");

    std::vector<UserTextSetBatchItem> parsed;
    parsed.reserve(items.size());
    std::unordered_set<std::string> seen;
    seen.reserve(items.size());

    for (size_t i = 0; i < items.size(); ++i)
    {
        if (!items[i].is_object())
        {
            throw std::invalid_argument(
                "items[" + std::to_string(i) + "] must be an object");
        }
        if (!items[i].contains("id") || !items[i]["id"].is_string())
        {
            throw std::invalid_argument(
                "items[" + std::to_string(i) + "].id must be a string UUID");
        }

        const std::string idText = items[i]["id"].get<std::string>();
        ON_UUID id = ON_UuidFromString(idText.c_str());
        if (ON_UuidIsNil(id))
            throw std::invalid_argument("Invalid UUID format: " + idText);

        RejectDuplicateUuid(seen, UuidToString(id));

        if (!items[i].contains("userStrings"))
        {
            throw std::invalid_argument(
                "items[" + std::to_string(i) + "] missing required field: userStrings");
        }
        ValidateBatchUserStringsObjectStrict(items[i]["userStrings"], i);

        UserTextSetBatchItem item;
        item.id = id;
        item.userStrings = items[i]["userStrings"];
        parsed.push_back(std::move(item));
    }

    return parsed;
}

bool ParseOptionalRedraw(const nlohmann::json& body)
{
    if (!body.contains("redraw"))
        return true;
    if (!body["redraw"].is_boolean())
        throw std::invalid_argument("'redraw' must be a boolean");
    return body["redraw"].get<bool>();
}

// Reserved-prefix denylist table for document-level user-string writes.
// Only /usertext/document-set gates on this — object-level writes and
// both read routes are unrestricted.
//
// First-match short-circuit: when a key matches multiple prefixes (not
// expected today but possible if the table grows), the first matching
// entry is the one surfaced in the error message. Consistent with
// PR-9's first-offender validation style on non-string/empty-string.
struct ReservedPrefix
{
    const char* prefix;
    const char* owner;
    const char* redirect;  // sanctioned alternative route, or empty
};

static constexpr ReservedPrefix kReservedPrefixes[] = {
    {"RookBlock::",
     "block-definition metadata (BlocksHandler)",
     "/block/user-strings"},
    // Future Rook*:: reservations append here as they appear.
};

// Validate no key in `userStrings` has a reserved prefix. Throws
// StructuredError("reserved_namespace", ...) on first violation so
// the top-level catch emits the route-local error code rather than
// collapsing to invalid_input. Rejection is WHOLESALE at the caller:
// this runs on the worker thread BEFORE UndoScope / SetUserString,
// so a mixed map cannot produce partial writes. Assumes caller has
// already run ValidateUserStringsObjectStrict so keys are known to
// be strings mapping to non-empty strings.
void ValidateNoReservedPrefixes(const nlohmann::json& body)
{
    for (auto it = body["userStrings"].begin(); it != body["userStrings"].end(); ++it)
    {
        const std::string& key = it.key();
        for (const auto& entry : kReservedPrefixes)
        {
            const size_t plen = std::strlen(entry.prefix);
            if (key.size() < plen) continue;
            if (key.compare(0, plen, entry.prefix) != 0) continue;

            std::string msg = "Key prefix '";
            msg += entry.prefix;
            msg += "' is reserved for ";
            msg += entry.owner;
            if (entry.redirect && *entry.redirect)
            {
                msg += "; use ";
                msg += entry.redirect;
                msg += " instead";
            }
            throw StructuredError("reserved_namespace", std::move(msg));
        }
    }
}

// Validate `keys` is a JSON array of non-empty strings, and build an
// ordered deduped vector preserving first-seen request order. Used by
// both /usertext/object-delete and /usertext/document-delete.
//
// Design points:
//   - First-seen order (NOT sorted) — the deletedKeys audit field
//     reflects the order the caller asked for, which is a cleaner
//     contract than sorted (Codex scope review 2026-04-20).
//   - Silent dedupe — `["a", "a", "b"]` resolves to `["a", "b"]`.
//     Duplicate keys aren't meaningful in delete semantics and
//     rejecting them would add friction to plausible caller patterns
//     (builder-style accumulation). Easy to tighten later.
//   - Empty array `[]` is accepted — the caller uses it as an
//     idempotent no-op (parallel to set routes' empty userStrings {}).
//     The handler short-circuits before opening an UndoScope.
//
// Throws std::invalid_argument (mapped to invalid_input) on:
//   - missing `keys` field
//   - non-array type
//   - any non-string element (index-specific message)
//   - any empty-string element (index-specific message)
std::vector<std::string> ValidateKeysArrayStrict(const nlohmann::json& body)
{
    if (!body.contains("keys"))
        throw std::invalid_argument("Missing required field: keys");
    if (!body["keys"].is_array())
        throw std::invalid_argument("'keys' must be an array of strings");

    std::vector<std::string> requestedUnique;
    std::unordered_set<std::string> seen;
    const auto& arr = body["keys"];
    for (size_t i = 0; i < arr.size(); ++i)
    {
        if (!arr[i].is_string())
        {
            throw std::invalid_argument(
                std::string("keys[") + std::to_string(i) + "] must be a string");
        }
        const std::string key = arr[i].get<std::string>();
        if (key.empty())
        {
            throw std::invalid_argument(
                std::string("keys[") + std::to_string(i) + "] must be non-empty");
        }
        if (seen.insert(key).second)
            requestedUnique.push_back(key);
    }
    return requestedUnique;
}

// Validate no element in `keys` has a reserved prefix. Delete-side
// analog of ValidateNoReservedPrefixes (which operates on the
// userStrings map). Throws StructuredError("reserved_namespace", ...)
// on first violation; rejection is wholesale (runs on the worker
// thread BEFORE UndoScope / SetUserString).
//
// `actionHint` anchors the error message to the delete-specific
// surface on the sanctioned route. For RookBlock:: this expands to
// "/block/user-strings with action=delete" rather than just
// "/block/user-strings" — matches the mutation semantics the caller
// actually wants.
void ValidateNoReservedPrefixesInKeys(
    const std::vector<std::string>& keys,
    const char* actionHint)
{
    for (const std::string& key : keys)
    {
        for (const auto& entry : kReservedPrefixes)
        {
            const size_t plen = std::strlen(entry.prefix);
            if (key.size() < plen) continue;
            if (key.compare(0, plen, entry.prefix) != 0) continue;

            std::string msg = "Key prefix '";
            msg += entry.prefix;
            msg += "' is reserved for ";
            msg += entry.owner;
            if (entry.redirect && *entry.redirect)
            {
                msg += "; use ";
                msg += entry.redirect;
                if (actionHint && *actionHint)
                {
                    msg += " with ";
                    msg += actionHint;
                }
                msg += " instead";
            }
            throw StructuredError("reserved_namespace", std::move(msg));
        }
    }
}

// Serialize every user string on `attrs` into a JSON object. Local
// equivalent of the file-static SerializeAttributeUserStrings in
// BlocksHandler.cpp:729; kept local here because a cross-file shared
// helper is a separate promotion refactor (PR-4 rhythm — promote on
// third caller).
nlohmann::json SerializeUserStringsFromAttributes(const ON_3dmObjectAttributes& attrs)
{
    nlohmann::json userStrings = nlohmann::json::object();
    ON_ClassArray<ON_wString> keys;
    attrs.GetUserStringKeys(keys);
    for (int i = 0; i < keys.Count(); ++i)
    {
        ON_wString value;
        if (attrs.GetUserString(keys[i], value))
            userStrings[WideToUtf8(keys[i])] = WideToUtf8(value);
    }
    return userStrings;
}

// Serialize every user string on `pDoc` into a JSON object. Doc-level
// analog of SerializeUserStringsFromAttributes; uses the CRhinoDoc
// GetUserStringKeys / GetUserString API that matches the block-handler
// document-user-strings read path at BlocksHandler.cpp:3032-3047.
nlohmann::json SerializeUserStringsFromDoc(const CRhinoDoc* pDoc)
{
    nlohmann::json userStrings = nlohmann::json::object();
    ON_ClassArray<ON_wString> keys;
    pDoc->GetUserStringKeys(keys);
    for (int i = 0; i < keys.Count(); ++i)
    {
        ON_wString value;
        if (pDoc->GetUserString(keys[i], value))
            userStrings[WideToUtf8(keys[i])] = WideToUtf8(value);
    }
    return userStrings;
}

// Shared top-level exception mapper. Called from both handlers'
// try/catch. Emits {errorCode, errorMessage} envelopes that the
// MCP layer surfaces as structured failures.
void EmitStructuredError(httplib::Response& res,
                         const char* code,
                         const std::string& message)
{
    nlohmann::json err = {
        {"errorCode", code},
        {"errorMessage", message},
    };
    CRookServer::SendErrorData(res, err);
}

void EmitDirtyUserTextOperationError(httplib::Response& res,
                                     const DirtyUserTextOperationError& ex)
{
    nlohmann::json err = {
        {"errorCode", "operation_failed"},
        {"errorMessage", ex.message},
        {"id", UuidToString(ex.id)},
        {"operation", ex.operation},
        {"message", ex.message},
        {"dirty_partial_state", true},
    };
    CRookServer::SendErrorData(res, err);
}

} // namespace

// --- POST /usertext/object-set ------------------------------------------

void HandleUserTextObjectSet(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto invalidInput = [&](const std::string& message) {
        EmitStructuredError(res, "invalid_input", message);
    };

    // Worker-thread schema validation (Rule 2).

    ON_UUID id;
    try
    {
        id = ParseUuid(body, "id");
    }
    catch (const std::invalid_argument& ex)
    {
        invalidInput(ex.what());
        return;
    }

    try
    {
        ValidateUserStringsObjectStrict(body, "/usertext/object-delete");
    }
    catch (const std::invalid_argument& ex)
    {
        invalidInput(ex.what());
        return;
    }

    const bool isNoOp = body["userStrings"].empty();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body, id, isNoOp]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = LookupObjectStrict(id, pDoc);

        // Declared-no-op path: empty userStrings means the caller is
        // asking for the current persisted map without mutation. Skip
        // UndoScope and Redraw so no-ops leave no fingerprint in the
        // undo stack. Still dispatched through the UI thread for the
        // LookupObject + attribute read.
        if (isNoOp)
        {
            WriteResult wr;
            wr.success = true;
            wr.data["id"] = UuidToString(id);
            wr.data["userStrings"] =
                SerializeUserStringsFromAttributes(obj->Attributes());
            return wr;
        }

        UndoScope undo(pDoc, L"Set Object User Strings");

        ON_3dmObjectAttributes attrs = obj->Attributes();
        for (auto it = body["userStrings"].begin(); it != body["userStrings"].end(); ++it)
        {
            attrs.SetUserString(
                Utf8ToWide(it.key()),
                Utf8ToWide(it.value().get<std::string>()));
        }

        if (!pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs))
            throw StructuredError("operation_failed",
                "Failed to modify object attributes");

        pDoc->Redraw();

        // Read back the persisted map from a fresh lookup — mirrors
        // BlocksHandler.cpp:2565. Assuming the post-modify pointer
        // reflects the committed attrs is not contract; re-lookup is.
        const CRhinoObject* updated = pDoc->LookupObject(id);
        if (!updated)
            throw StructuredError("operation_failed",
                "Object disappeared after ModifyObjectAttributes");

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(id);
        wr.data["userStrings"] =
            SerializeUserStringsFromAttributes(updated->Attributes());
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const StructuredError& ex)
    {
        EmitStructuredError(res, ex.code.c_str(), ex.message);
    }
    catch (const std::invalid_argument& ex)
    {
        invalidInput(ex.what());
    }
    catch (const std::exception& ex)
    {
        EmitStructuredError(res, "operation_failed", ex.what());
    }
}

// --- POST /usertext/object-set-batch ------------------------------------

void HandleUserTextObjectSetBatch(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::vector<UserTextSetBatchItem> items;
    bool redraw = true;
    try
    {
        items = ParseUserTextSetBatchItems(body);
        redraw = ParseOptionalRedraw(body);
    }
    catch (const std::invalid_argument& ex)
    {
        EmitStructuredError(res, "invalid_input", ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, items, redraw]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        for (const UserTextSetBatchItem& item : items)
            (void)LookupObjectStrict(item.id, pDoc);

        UndoScope undo(pDoc, L"Set Object User Strings Batch");

        int modifiedCount = 0;
        int skippedCount = 0;
        nlohmann::json results = nlohmann::json::array();

        for (const UserTextSetBatchItem& item : items)
        {
            const CRhinoObject* obj = LookupObjectStrict(item.id, pDoc);
            const nlohmann::json currentUserStrings =
                SerializeUserStringsFromAttributes(obj->Attributes());

            bool unchanged = true;
            for (auto it = item.userStrings.begin(); it != item.userStrings.end(); ++it)
            {
                if (!currentUserStrings.contains(it.key())
                    || !currentUserStrings[it.key()].is_string()
                    || currentUserStrings[it.key()].get<std::string>()
                        != it.value().get<std::string>())
                {
                    unchanged = false;
                    break;
                }
            }

            std::string status = "unchanged";
            if (unchanged)
            {
                ++skippedCount;
            }
            else
            {
                ON_3dmObjectAttributes attrs = obj->Attributes();
                for (auto it = item.userStrings.begin(); it != item.userStrings.end(); ++it)
                {
                    attrs.SetUserString(
                        Utf8ToWide(it.key()),
                        Utf8ToWide(it.value().get<std::string>()));
                }

                if (!pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs))
                {
                    throw DirtyUserTextOperationError(
                        item.id,
                        "set_object_user_strings_batch",
                        "Failed to modify object attributes");
                }

                status = "modified";
                ++modifiedCount;
            }

            const CRhinoObject* updated = LookupObjectStrict(item.id, pDoc);
            const nlohmann::json postUserStrings =
                SerializeUserStringsFromAttributes(updated->Attributes());

            nlohmann::json result;
            result["id"] = UuidToString(item.id);
            result["status"] = status;
            result["userStrings"] = postUserStrings;
            results.push_back(std::move(result));
        }

        if (redraw && modifiedCount > 0)
            pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["requestedCount"] = static_cast<int>(items.size());
        wr.data["modifiedCount"] = modifiedCount;
        wr.data["skippedCount"] = skippedCount;
        wr.data["results"] = std::move(results);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const DirtyUserTextOperationError& ex)
    {
        EmitDirtyUserTextOperationError(res, ex);
    }
    catch (const StructuredError& ex)
    {
        EmitStructuredError(res, ex.code.c_str(), ex.message);
    }
    catch (const std::invalid_argument& ex)
    {
        EmitStructuredError(res, "invalid_input", ex.what());
    }
    catch (const std::exception& ex)
    {
        EmitStructuredError(res, "operation_failed", ex.what());
    }
}

// --- POST /usertext/object-get ------------------------------------------

void HandleUserTextObjectGet(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto invalidInput = [&](const std::string& message) {
        EmitStructuredError(res, "invalid_input", message);
    };

    ON_UUID id;
    try
    {
        id = ParseUuid(body, "id");
    }
    catch (const std::invalid_argument& ex)
    {
        invalidInput(ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, id]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = LookupObjectStrict(id, pDoc);

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(id);
        wr.data["userStrings"] =
            SerializeUserStringsFromAttributes(obj->Attributes());
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const StructuredError& ex)
    {
        EmitStructuredError(res, ex.code.c_str(), ex.message);
    }
    catch (const std::invalid_argument& ex)
    {
        invalidInput(ex.what());
    }
    catch (const std::exception& ex)
    {
        EmitStructuredError(res, "operation_failed", ex.what());
    }
}

// --- POST /usertext/document-set ----------------------------------------

void HandleUserTextDocumentSet(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto invalidInput = [&](const std::string& message) {
        EmitStructuredError(res, "invalid_input", message);
    };

    // Worker-thread schema validation (Rule 2). Base shape/value
    // checks first, then reserved-prefix denylist — both run BEFORE
    // UI-thread dispatch, per Codex scope pass directive. Atomic
    // wholesale rejection: no partial writes when any key fails.

    try
    {
        ValidateUserStringsObjectStrict(body, "/usertext/document-delete");
    }
    catch (const std::invalid_argument& ex)
    {
        invalidInput(ex.what());
        return;
    }

    try
    {
        ValidateNoReservedPrefixes(body);
    }
    catch (const StructuredError& ex)
    {
        EmitStructuredError(res, ex.code.c_str(), ex.message);
        return;
    }

    const bool isNoOp = body["userStrings"].empty();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body, isNoOp]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        // Declared-no-op path: empty userStrings returns the current
        // persisted map without mutation. Skip UndoScope and Redraw so
        // no-ops leave no fingerprint in the undo stack. Read still
        // runs on the UI thread per the Rhino threading contract.
        if (isNoOp)
        {
            WriteResult wr;
            wr.success = true;
            wr.data["userStrings"] = SerializeUserStringsFromDoc(pDoc);
            return wr;
        }

        UndoScope undo(pDoc, L"Set Document User Strings");

        for (auto it = body["userStrings"].begin(); it != body["userStrings"].end(); ++it)
        {
            const bool ok = pDoc->SetUserString(
                Utf8ToWide(it.key()),
                Utf8ToWide(it.value().get<std::string>()));
            if (!ok)
                throw StructuredError("operation_failed",
                    std::string("Failed to set document user string '")
                    + it.key() + "'");
        }

        pDoc->Redraw();

        // Read back the persisted map after mutation. Doc-level
        // analog of the LookupObject-after-ModifyObjectAttributes
        // rhythm in the object-set handler: response echoes what is
        // actually persisted, not what was requested.
        WriteResult wr;
        wr.success = true;
        wr.data["userStrings"] = SerializeUserStringsFromDoc(pDoc);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const StructuredError& ex)
    {
        EmitStructuredError(res, ex.code.c_str(), ex.message);
    }
    catch (const std::invalid_argument& ex)
    {
        invalidInput(ex.what());
    }
    catch (const std::exception& ex)
    {
        EmitStructuredError(res, "operation_failed", ex.what());
    }
}

// --- POST /usertext/object-delete ---------------------------------------
//
// Delete N user-string keys from an object's attribute user-string
// store. Uses the empty-string delete sentinel characterized by
// test_usertext_object_live.py:194 — ON_3dmObjectAttributes::
// SetUserString(key, "") removes the key rather than persisting an
// empty value. Contract-internal derivation of deletedKeys (pre/post
// diff) means the handler does NOT depend on SDK return-value
// semantics for the delete path.
//
// Request: {id: uuid, keys: [string, ...]}
//   - keys array deduplicated silently, preserving first-seen order
//   - empty keys [] is an idempotent no-op (skips UndoScope, returns
//     current state with deletedKeys: [])
//
// Response: {id, userStrings: {...post-state...}, deletedKeys: [...]}
//   - deletedKeys reflects caller's first-seen order of unique keys
//     that were actually present pre-mutation and absent post-mutation
//   - Requested keys not present pre-mutation → NOT in deletedKeys
//     (idempotent delete — asking to remove a non-existent key is
//     not an error)
//
// Error codes: invalid_input (missing/malformed id or keys,
// non-string/empty keys element), not_found (unknown id),
// operation_failed (ModifyObjectAttributes returned false).

void HandleUserTextObjectDelete(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto invalidInput = [&](const std::string& message) {
        EmitStructuredError(res, "invalid_input", message);
    };

    ON_UUID id;
    try
    {
        id = ParseUuid(body, "id");
    }
    catch (const std::invalid_argument& ex)
    {
        invalidInput(ex.what());
        return;
    }

    std::vector<std::string> requestedUnique;
    try
    {
        requestedUnique = ValidateKeysArrayStrict(body);
    }
    catch (const std::invalid_argument& ex)
    {
        invalidInput(ex.what());
        return;
    }

    const bool isNoOp = requestedUnique.empty();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, id, requestedUnique, isNoOp]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = LookupObjectStrict(id, pDoc);

        // Declared-no-op: empty keys means "report current state." Skip
        // UndoScope and Redraw so no-ops leave no fingerprint.
        if (isNoOp)
        {
            WriteResult wr;
            wr.success = true;
            wr.data["id"] = UuidToString(id);
            wr.data["userStrings"] =
                SerializeUserStringsFromAttributes(obj->Attributes());
            wr.data["deletedKeys"] = nlohmann::json::array();
            return wr;
        }

        // Snapshot pre-state key-set for the deletedKeys audit. We only
        // need set-membership, not values, so iterate the attribute
        // user-string keys once.
        ON_ClassArray<ON_wString> preKeys;
        obj->Attributes().GetUserStringKeys(preKeys);
        std::set<std::string> preSet;
        for (int i = 0; i < preKeys.Count(); ++i)
            preSet.insert(WideToUtf8(preKeys[i]));

        UndoScope undo(pDoc, L"Delete Object User Strings");

        ON_3dmObjectAttributes attrs = obj->Attributes();
        for (const std::string& key : requestedUnique)
        {
            // Empty-string sentinel deletes the key at the attribute
            // level. Characterized by test_usertext_object_live.py:194.
            attrs.SetUserString(Utf8ToWide(key), L"");
        }

        if (!pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs))
            throw StructuredError("operation_failed",
                "Failed to modify object attributes");

        pDoc->Redraw();

        // Post-state from a fresh lookup — mirrors set rhythm.
        const CRhinoObject* updated = pDoc->LookupObject(id);
        if (!updated)
            throw StructuredError("operation_failed",
                "Object disappeared after ModifyObjectAttributes");

        ON_ClassArray<ON_wString> postKeys;
        updated->Attributes().GetUserStringKeys(postKeys);
        std::set<std::string> postSet;
        for (int i = 0; i < postKeys.Count(); ++i)
            postSet.insert(WideToUtf8(postKeys[i]));

        // Failure detection: a key that was present pre-mutation and
        // remains present post-mutation is a FAILED delete. Surface
        // as operation_failed — NOT silently omitted from deletedKeys
        // (which would make "delete failed" indistinguishable from
        // "key was absent before the call"). Codex review 2026-04-20.
        std::vector<std::string> survivedExisting;
        for (const std::string& key : requestedUnique)
        {
            if (preSet.count(key) && postSet.count(key))
                survivedExisting.push_back(key);
        }
        if (!survivedExisting.empty())
        {
            std::string msg = "Delete failed for key(s): ";
            for (size_t i = 0; i < survivedExisting.size(); ++i)
            {
                if (i > 0) msg += ", ";
                msg += "'" + survivedExisting[i] + "'";
            }
            msg += " (requested keys still present after mutation)";
            throw StructuredError("operation_failed", std::move(msg));
        }

        // deletedKeys = requested ∩ (pre \ post), iterated in
        // requestedUnique order to preserve first-seen ordering.
        nlohmann::json deletedKeys = nlohmann::json::array();
        for (const std::string& key : requestedUnique)
        {
            if (preSet.count(key) && !postSet.count(key))
                deletedKeys.push_back(key);
        }

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(id);
        wr.data["userStrings"] =
            SerializeUserStringsFromAttributes(updated->Attributes());
        wr.data["deletedKeys"] = std::move(deletedKeys);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const StructuredError& ex)
    {
        EmitStructuredError(res, ex.code.c_str(), ex.message);
    }
    catch (const std::invalid_argument& ex)
    {
        invalidInput(ex.what());
    }
    catch (const std::exception& ex)
    {
        EmitStructuredError(res, "operation_failed", ex.what());
    }
}

// --- POST /usertext/document-delete -------------------------------------
//
// Delete N user-string keys from the active document's user-string
// store. Uses the empty-string delete sentinel characterized by
// test_usertext_document_live.py:11 — pDoc->SetUserString(k, "")
// removes the key rather than persisting an empty value.
// Contract-internal derivation of deletedKeys (pre/post diff) means
// the handler does NOT depend on SDK return-value semantics.
//
// Request: {keys: [string, ...]}  (no id field — document-level scope)
//   - keys array deduplicated silently, preserving first-seen order
//   - empty keys [] is an idempotent no-op
//
// Reserved-prefix denylist applies here (writes are gated). Keys with
// a reserved prefix (e.g. "RookBlock::") are rejected wholesale with
// `reserved_namespace`; the error message anchors the caller at the
// sanctioned delete surface: "use /block/user-strings with
// action=delete instead" (see BlocksHandler.cpp:3080 for the actual
// delete handler that owns that prefix).
//
// Response: {userStrings: {...post-state...}, deletedKeys: [...]}
//   - Caller-order audit via pre/post diff — same shape as
//     object-delete minus the id field (acceptance gate #2).

void HandleUserTextDocumentDelete(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto invalidInput = [&](const std::string& message) {
        EmitStructuredError(res, "invalid_input", message);
    };

    std::vector<std::string> requestedUnique;
    try
    {
        requestedUnique = ValidateKeysArrayStrict(body);
    }
    catch (const std::invalid_argument& ex)
    {
        invalidInput(ex.what());
        return;
    }

    try
    {
        // Anchor the redirect message to the DELETE action on the
        // sanctioned route, not just the route itself. The route
        // parameter-multiplexes get/set/delete via `action` — delete
        // callers should be pointed at the delete action specifically
        // (BlocksHandler.cpp:3080 is where that action is handled).
        ValidateNoReservedPrefixesInKeys(requestedUnique, "action=delete");
    }
    catch (const StructuredError& ex)
    {
        EmitStructuredError(res, ex.code.c_str(), ex.message);
        return;
    }

    const bool isNoOp = requestedUnique.empty();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, requestedUnique, isNoOp]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        if (isNoOp)
        {
            WriteResult wr;
            wr.success = true;
            wr.data["userStrings"] = SerializeUserStringsFromDoc(pDoc);
            wr.data["deletedKeys"] = nlohmann::json::array();
            return wr;
        }

        // Snapshot pre-state key-set for the deletedKeys audit.
        ON_ClassArray<ON_wString> preKeys;
        pDoc->GetUserStringKeys(preKeys);
        std::set<std::string> preSet;
        for (int i = 0; i < preKeys.Count(); ++i)
            preSet.insert(WideToUtf8(preKeys[i]));

        UndoScope undo(pDoc, L"Delete Document User Strings");

        for (const std::string& key : requestedUnique)
        {
            // Empty-string sentinel deletes at the document level too.
            // Characterized by test_usertext_document_live.py:11 and
            // documented in UserTextHandler.h:26-37.
            (void)pDoc->SetUserString(Utf8ToWide(key), L"");
        }

        pDoc->Redraw();

        ON_ClassArray<ON_wString> postKeys;
        pDoc->GetUserStringKeys(postKeys);
        std::set<std::string> postSet;
        for (int i = 0; i < postKeys.Count(); ++i)
            postSet.insert(WideToUtf8(postKeys[i]));

        // Failure detection: requested key present pre AND post =
        // failed delete. Surface as operation_failed. See
        // HandleUserTextObjectDelete for rationale (Codex 2026-04-20).
        std::vector<std::string> survivedExisting;
        for (const std::string& key : requestedUnique)
        {
            if (preSet.count(key) && postSet.count(key))
                survivedExisting.push_back(key);
        }
        if (!survivedExisting.empty())
        {
            std::string msg = "Delete failed for key(s): ";
            for (size_t i = 0; i < survivedExisting.size(); ++i)
            {
                if (i > 0) msg += ", ";
                msg += "'" + survivedExisting[i] + "'";
            }
            msg += " (requested keys still present after mutation)";
            throw StructuredError("operation_failed", std::move(msg));
        }

        nlohmann::json deletedKeys = nlohmann::json::array();
        for (const std::string& key : requestedUnique)
        {
            if (preSet.count(key) && !postSet.count(key))
                deletedKeys.push_back(key);
        }

        WriteResult wr;
        wr.success = true;
        wr.data["userStrings"] = SerializeUserStringsFromDoc(pDoc);
        wr.data["deletedKeys"] = std::move(deletedKeys);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const StructuredError& ex)
    {
        EmitStructuredError(res, ex.code.c_str(), ex.message);
    }
    catch (const std::invalid_argument& ex)
    {
        invalidInput(ex.what());
    }
    catch (const std::exception& ex)
    {
        EmitStructuredError(res, "operation_failed", ex.what());
    }
}

// --- POST /usertext/document-get ----------------------------------------

void HandleUserTextDocumentGet(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    (void)body;  // document-get takes no input fields; body accepted
                 // but unused (empty body and `{}` both work per
                 // ParseBodyAndDocSn normalization).

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        WriteResult wr;
        wr.success = true;
        wr.data["userStrings"] = SerializeUserStringsFromDoc(pDoc);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const StructuredError& ex)
    {
        EmitStructuredError(res, ex.code.c_str(), ex.message);
    }
    catch (const std::exception& ex)
    {
        EmitStructuredError(res, "operation_failed", ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
