// UserTextHandler.cpp
//
// Phase 2 typed user-text routes. See plan:
//   rook_docs/2026-04-19-typed-route-phase2-plan.md §"Worked Example:
//   /usertext/object-set" (PR-9).
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
// Empty-string values are ALSO rejected with invalid_input. Empirical
// finding 2026-04-19: ON_3dmObjectAttributes::SetUserString(key, "")
// treats the empty string as a delete sentinel — the key is removed
// from the attribute user-string store, not persisted with an empty
// value. This matches the OpenNURBS document-level delete convention
// (pDoc->SetUserString(k, nullptr) at BlocksHandler.cpp:3090) but
// conflicts with PR-9's plan-doc scope, which defers delete to a
// follow-up /usertext/object-delete route. Rather than silently
// deliver delete semantics through the set surface — with different
// response/error contracts from the eventual explicit delete route —
// PR-9 rejects empty-string values at the handler and requires
// callers to wait for the sanctioned delete surface. If a caller has
// a legitimate need to store empty-string values, the right response
// is to design an opt-in flag on a future revision; until then,
// empty strings are out of contract.
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
#include <string>

namespace Rook {
namespace Handlers {

namespace {

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
//     would delete the key via SDK convention, and delete is out of
//     scope for PR-9; see file-header comment)
// Empty object {} is accepted — callers use it as an idempotent no-op.
void ValidateUserStringsObjectStrict(const nlohmann::json& body)
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
                "userStrings['" + it.key() + "'] must be non-empty "
                "(empty-string values delete the key under the SDK "
                "contract; delete is not yet supported — wait for "
                "/usertext/object-delete)");
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
        ValidateUserStringsObjectStrict(body);
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

} // namespace Handlers
} // namespace Rook
