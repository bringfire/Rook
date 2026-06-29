# Exact-ID Object Hygiene Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build three exact-ID mutating Rook tools for object visibility, object layer assignment, and per-object usertext batch stamping.

**Architecture:** Native RookNative owns the Rhino mutations on the main thread, using existing compiled handler files to avoid C++ project-file churn. The Python MCP layer only advertises schemas and forwards exact request bodies through existing bridge/targeting/agent-dispatch paths. Tests pin schemas, route registration, mutating policy, dispatcher reachability, cap boundaries, and live document state changes.

**Tech Stack:** Rhino 8 C++ SDK, httplib, nlohmann/json, RookNative main-thread dispatcher, Python MCP server, pytest.

---

## File Structure

Modify native handlers:

- `src/RookNative/Handlers/ObjectsHandler.h`
  - Declare `HandleObjectVisibility` and `HandleObjectSetLayer`.
- `src/RookNative/Handlers/ObjectsHandler.cpp`
  - Implement `POST /objects/visibility` and `POST /objects/set-layer`.
  - Reuse `ParseBodyAndDocSn`, `ResolveDoc`, `ResolveLayerRef`, `UndoScope`, `ModifyObjectAttributes`, and `ON_3dmObjectAttributes::SetVisible`.
  - Keep all preflight validation before `UndoScope`.
- `src/RookNative/Handlers/UserTextHandler.h`
  - Declare `HandleUserTextObjectSetBatch`.
- `src/RookNative/Handlers/UserTextHandler.cpp`
  - Implement `POST /usertext/object-set-batch` beside the existing strict object usertext routes.
  - Reuse the existing user-string serialization/readback pattern.
- `src/RookNative/RookServer.h`
  - Add CRookServer wrapper declarations for the two `/objects/*` routes, matching the existing objects family style.
- `src/RookNative/RookServer.cpp`
  - Register the three native routes.
  - Add CRookServer wrappers for the two object routes.

Modify MCP/agent wiring:

- `mcp_server/src/rook/server.py`
  - Add three `Tool(...)` schema entries.
  - Add three `call_tool` dispatch cases.
- `mcp_server/src/rook/agent/tool_dispatcher.py`
  - Add the three tools to `BRIDGE_ROUTES`.
- `mcp_server/src/rook/bootstrap/executor.py`
  - Add the three bridge mappings for bootstrap execution.
- `mcp_server/src/rook/targeting.py`
  - Classify all three tools as Rhino-required mutating.
- `mcp_server/src/rook/agent/tool_groups.py`
  - Add a focused mutating `object_hygiene` group.
  - Add `rhino_object_set_layer` to the existing mutating `layers` group.
  - Do not add these tools to readonly groups.

Create tests:

- `mcp_server/tests/test_exact_id_object_hygiene_tools.py`
  - MCP schema, server dispatch, dispatcher bridge, targeting policy, tool-group, and cap-boundary contract tests.
- `mcp_server/tests/test_exact_id_object_hygiene_native_source.py`
  - Source/static native route and implementation tests.
- `mcp_server/tests/test_exact_id_object_hygiene_live.py`
  - Live Rhino state-change tests.

Do not create new native `.cpp`/`.h` files, and do not modify `.vcxproj` or `.vcxproj.filters`.

## Contract Summary

All three tools:

- Accept exact object ids only.
- Reject empty id/item lists.
- Reject duplicate ids.
- Reject more than 500 ids/items.
- Perform whole-request preflight before opening an undo record.
- Mutate under one undo record.
- Return `results`, `requestedCount`, `modifiedCount`, and `skippedCount`.
- Use `status: "modified"` or `status: "unchanged"` on success.
- Return no partial-success result on runtime mutation failure.
- Return `operation_failed` with `id`, `operation`, `message`, and `dirty_partial_state: true` if a runtime mutation failure occurs after mutation begins.

`rhino_object_visibility`:

- Native route: `POST /objects/visibility`.
- Request: `{"object_ids": [...], "visible": true|false, "redraw": true|false?}`.
- Sets object-level visibility via `ON_3dmObjectAttributes::SetVisible`.
- Response per object includes `objectVisible`, `layerVisible`, and `effectivelyVisible`.
  - SDK check: `ON_3dmObjectAttributes::IsVisible()` reads object-level visibility.
  - SDK check: `CRhinoObject::IsVisible()` returns false if the object or its layer is hidden.
- Per-object results use `before` and `after` state objects.

`rhino_object_set_layer`:

- Native route: `POST /objects/set-layer`.
- Request: `{"object_ids": [...], "layer": "Full::Path or unambiguous leaf", "redraw": true|false?}`.
- Missing layer is an error.
- Reuse `ResolveLayerRef`, which resolves exact full path first, then unambiguous leaf, and rejects ambiguous leaf names.
- Response includes `layer: {"input": string, "index": int, "id": string, "path": string}`.
- Per-object results use `before` and `after` state objects.

`rhino_object_usertext_set_batch`:

- Native route: `POST /usertext/object-set-batch`.
- Request: `{"items": [{"id": "...", "userStrings": {"key": "value"}}], "redraw": true|false?}`.
- One item per object id.
- Reject duplicate item ids.
- Reject empty string keys.
- Reject empty string values.
- Reject non-string values.
- Allow empty `userStrings: {}` as an unchanged no-op for that object, matching the single-object route's no-op posture.
- Return full post-mutation `userStrings` for each requested object, bounded to requested objects only.
- Delete semantics stay out of scope.

---

### Task 1: Add Failing MCP Contract Tests

**Files:**
- Create: `mcp_server/tests/test_exact_id_object_hygiene_tools.py`

- [ ] **Step 1: Write the failing MCP contract test file**

Create `mcp_server/tests/test_exact_id_object_hygiene_tools.py` with this content:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from rook import server, targeting
from rook.agent import tool_dispatcher, tool_groups


HYGIENE_TOOLS = {
    "rhino_object_visibility": ("/objects/visibility", "POST"),
    "rhino_object_set_layer": ("/objects/set-layer", "POST"),
    "rhino_object_usertext_set_batch": ("/usertext/object-set-batch", "POST"),
}


@pytest.fixture(autouse=True)
def fake_rhino_discovery(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    monkeypatch.setattr(
        targeting,
        "discover_instances",
        lambda: [
            {
                "host": "127.0.0.1",
                "port": 9950,
                "processId": 7101,
                "pluginType": "native",
            }
        ],
    )
    yield
    targeting.reset_targeting_state_for_tests()


@pytest.mark.asyncio
async def test_hygiene_tools_registered_with_exact_schemas():
    tools = await server.list_tools()
    by_name = {tool.name: tool for tool in tools}

    assert set(HYGIENE_TOOLS).issubset(by_name)

    visibility = by_name["rhino_object_visibility"].inputSchema
    assert visibility["required"] == ["object_ids", "visible"]
    assert visibility["properties"]["object_ids"]["maxItems"] == 500
    assert visibility["properties"]["object_ids"]["minItems"] == 1
    assert visibility["properties"]["visible"]["type"] == "boolean"
    assert "selectors" not in visibility["properties"]

    set_layer = by_name["rhino_object_set_layer"].inputSchema
    assert set_layer["required"] == ["object_ids", "layer"]
    assert set_layer["properties"]["object_ids"]["maxItems"] == 500
    assert set_layer["properties"]["object_ids"]["minItems"] == 1
    assert set_layer["properties"]["layer"]["type"] == "string"
    assert "create" not in set_layer["properties"]

    batch = by_name["rhino_object_usertext_set_batch"].inputSchema
    assert batch["required"] == ["items"]
    assert batch["properties"]["items"]["maxItems"] == 500
    assert batch["properties"]["items"]["minItems"] == 1
    item_schema = batch["properties"]["items"]["items"]
    assert item_schema["required"] == ["id", "userStrings"]
    assert item_schema["properties"]["id"]["type"] == "string"
    assert item_schema["properties"]["userStrings"]["type"] == "object"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,route", sorted(HYGIENE_TOOLS.items()))
async def test_server_call_tool_dispatches_to_native_route(tool_name, route):
    body = {
        "rhino_object_visibility": {
            "object_ids": ["11111111-1111-1111-1111-111111111111"],
            "visible": False,
        },
        "rhino_object_set_layer": {
            "object_ids": ["11111111-1111-1111-1111-111111111111"],
            "layer": "Animation::Actors",
        },
        "rhino_object_usertext_set_batch": {
            "items": [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "userStrings": {"Director::role": "actor"},
                }
            ],
        },
    }[tool_name]

    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"ok": True}}
        await server.call_tool(tool_name, body)

    args, kwargs = mock.call_args
    assert args == (route[0], route[1], body)
    assert kwargs.get("port") == 9950


@pytest.mark.parametrize("tool_name,route", sorted(HYGIENE_TOOLS.items()))
def test_dispatcher_bridge_routes(tool_name, route):
    assert tool_name in tool_dispatcher.BRIDGE_ROUTES
    assert tool_dispatcher.BRIDGE_ROUTES[tool_name] == route


@pytest.mark.parametrize("tool_name", sorted(HYGIENE_TOOLS))
def test_targeting_policy_is_rhino_mutating(tool_name):
    assert targeting.policy_for_tool(tool_name) == targeting.RhinoToolPolicy(
        True, "mutate"
    )


def test_object_hygiene_group_is_mutating_only_and_dispatchable():
    assert "object_hygiene" in tool_groups.TOOL_GROUPS
    assert set(tool_groups.TOOL_GROUPS["object_hygiene"]) == set(HYGIENE_TOOLS)
    assert "object_hygiene" not in tool_groups.READONLY_ALLOWED_GROUPS
    assert "object_hygiene" not in tool_groups.MCP_ONLY_GROUPS

    for tool_name in tool_groups.TOOL_GROUPS["object_hygiene"]:
        assert tool_name in tool_dispatcher.BRIDGE_ROUTES


def test_hygiene_tools_do_not_leak_into_readonly_groups():
    leaked = []
    for group in tool_groups.READONLY_ALLOWED_GROUPS:
        for tool_name in tool_groups.TOOL_GROUPS.get(group, []):
            if tool_name in HYGIENE_TOOLS:
                leaked.append((group, tool_name))
    assert leaked == []


def test_object_set_layer_is_also_available_from_layers_mutating_group():
    assert "rhino_object_set_layer" in tool_groups.TOOL_GROUPS["layers"]
    assert "rhino_object_set_layer" not in tool_groups.TOOL_GROUPS["layers_readonly"]
```

- [ ] **Step 2: Run the MCP contract tests and confirm they fail for missing tools**

Run:

```powershell
python -m pytest mcp_server/tests/test_exact_id_object_hygiene_tools.py -q
```

Expected before implementation:

```text
FAILED ... rhino_object_visibility
FAILED ... rhino_object_set_layer
FAILED ... rhino_object_usertext_set_batch
```

- [ ] **Step 3: Commit the failing tests**

Run:

```powershell
git add mcp_server/tests/test_exact_id_object_hygiene_tools.py
git commit -m "test: pin exact-id object hygiene MCP contracts"
```

Expected:

```text
[codex/director-prepare-take <sha>] test: pin exact-id object hygiene MCP contracts
```

---

### Task 2: Add Failing Native Source Tests

**Files:**
- Create: `mcp_server/tests/test_exact_id_object_hygiene_native_source.py`

- [ ] **Step 1: Write source/static tests for native route registration and required implementation hooks**

Create `mcp_server/tests/test_exact_id_object_hygiene_native_source.py` with this content:

```python
from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
OBJECTS_CPP = REPO_ROOT / "src" / "RookNative" / "Handlers" / "ObjectsHandler.cpp"
OBJECTS_H = REPO_ROOT / "src" / "RookNative" / "Handlers" / "ObjectsHandler.h"
USER_TEXT_CPP = REPO_ROOT / "src" / "RookNative" / "Handlers" / "UserTextHandler.cpp"
USER_TEXT_H = REPO_ROOT / "src" / "RookNative" / "Handlers" / "UserTextHandler.h"
ROOK_SERVER_CPP = REPO_ROOT / "src" / "RookNative" / "RookServer.cpp"
ROOK_SERVER_H = REPO_ROOT / "src" / "RookNative" / "RookServer.h"


def _extract_function(source: str, signature: str) -> str:
    start = source.index(signature)
    body_start = source.index("{", start)
    depth = 0
    for index in range(body_start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"Could not extract function for {signature!r}")


def test_native_handler_declarations_exist():
    objects_header = OBJECTS_H.read_text(encoding="utf-8")
    usertext_header = USER_TEXT_H.read_text(encoding="utf-8")
    server_header = ROOK_SERVER_H.read_text(encoding="utf-8")

    for name in {"HandleObjectVisibility", "HandleObjectSetLayer"}:
        pattern = (
            rf"void\s+{name}\s*\(\s*const\s+httplib::Request&\s+req,\s*"
            rf"httplib::Response&\s+res\s*\)\s*;"
        )
        assert re.search(pattern, objects_header)
        assert re.search(pattern, server_header)

    assert re.search(
        r"void\s+HandleUserTextObjectSetBatch\s*\(\s*const\s+httplib::Request&\s+req,\s*"
        r"httplib::Response&\s+res\s*\)\s*;",
        usertext_header,
    )


def test_native_routes_are_registered():
    source = ROOK_SERVER_CPP.read_text(encoding="utf-8")

    assert 'm_server->Post("/objects/visibility"' in source
    assert "HandleObjectVisibility(req, res);" in source
    assert 'm_server->Post("/objects/set-layer"' in source
    assert "HandleObjectSetLayer(req, res);" in source
    assert 'm_server->Post("/usertext/object-set-batch"' in source
    assert "Rook::Handlers::HandleUserTextObjectSetBatch(req, res);" in source


def test_object_visibility_uses_modify_attributes_not_hide_show_selection_path():
    source = OBJECTS_CPP.read_text(encoding="utf-8")
    body = _extract_function(source, "void HandleObjectVisibility")

    assert "kMaxExactIdObjectBatchSize = 500" in source
    assert "ParseExactObjectIds" in source
    assert "RejectDuplicateUuid" in source
    assert "UndoScope undo(pDoc, L\"Set Object Visibility\")" in body
    assert ".SetVisible(visible)" in body
    assert "ModifyObjectAttributes" in body
    assert "HideObject" not in body
    assert "ShowObject" not in body
    assert "before" in body
    assert "after" in body
    assert "objectVisible" in body
    assert "layerVisible" in body
    assert "effectivelyVisible" in body
    assert "dirty_partial_state" in body


def test_object_set_layer_uses_resolve_layer_ref_and_modify_attributes():
    source = OBJECTS_CPP.read_text(encoding="utf-8")
    body = _extract_function(source, "void HandleObjectSetLayer")

    assert "kMaxExactIdObjectBatchSize = 500" in source
    assert "ResolveLayerRef(pDoc, layerName, \"layer\")" in body
    assert "UndoScope undo(pDoc, L\"Set Object Layer\")" in body
    assert "attrs.m_layer_index = targetLayer.index" in body
    assert "ModifyObjectAttributes" in body
    assert '"layer"' in body
    assert "layerId" in body
    assert "before" in body
    assert "after" in body
    assert "dirty_partial_state" in body


def test_usertext_batch_uses_full_readback_and_batch_cap():
    source = USER_TEXT_CPP.read_text(encoding="utf-8")
    body = _extract_function(source, "void HandleUserTextObjectSetBatch")

    assert "kMaxUserTextObjectSetBatchItems = 500" in source
    assert "ParseUserTextSetBatchItems" in source
    assert "RejectDuplicateUuid" in source
    assert "userStrings key must be non-empty" in source
    assert "must be non-empty" in source
    assert "UndoScope undo(pDoc, L\"Set Object User Strings Batch\")" in body
    assert "ModifyObjectAttributes" in body
    assert "SerializeUserStringsFromAttributes(updated->Attributes())" in body
    assert "dirty_partial_state" in body
```

- [ ] **Step 2: Run the native source tests and confirm they fail for missing routes/functions**

Run:

```powershell
python -m pytest mcp_server/tests/test_exact_id_object_hygiene_native_source.py -q
```

Expected before implementation:

```text
FAILED ... HandleObjectVisibility
FAILED ... HandleObjectSetLayer
FAILED ... HandleUserTextObjectSetBatch
```

- [ ] **Step 3: Commit the failing native source tests**

Run:

```powershell
git add mcp_server/tests/test_exact_id_object_hygiene_native_source.py
git commit -m "test: pin exact-id object hygiene native routes"
```

Expected:

```text
[codex/director-prepare-take <sha>] test: pin exact-id object hygiene native routes
```

---

### Task 3: Implement Native Object Visibility and Layer Handlers

**Files:**
- Modify: `src/RookNative/Handlers/ObjectsHandler.h`
- Modify: `src/RookNative/Handlers/ObjectsHandler.cpp`
- Modify: `src/RookNative/RookServer.h`
- Modify: `src/RookNative/RookServer.cpp`

- [ ] **Step 1: Add handler declarations**

In `src/RookNative/Handlers/ObjectsHandler.h`, add these declarations under the existing objects declarations:

```cpp
void HandleObjectVisibility(const httplib::Request& req, httplib::Response& res);
void HandleObjectSetLayer(const httplib::Request& req, httplib::Response& res);
```

In `src/RookNative/RookServer.h`, add matching wrapper declarations near `HandleObjects`:

```cpp
void HandleObjectVisibility(const httplib::Request& req, httplib::Response& res);
void HandleObjectSetLayer(const httplib::Request& req, httplib::Response& res);
```

- [ ] **Step 2: Add route registrations and wrapper methods**

In `src/RookNative/RookServer.cpp`, register the routes next to the existing `/objects` routes:

```cpp
m_server->Post("/objects/visibility", [this](const httplib::Request& req, httplib::Response& res) {
    HandleObjectVisibility(req, res);
});
m_server->Post("/objects/set-layer", [this](const httplib::Request& req, httplib::Response& res) {
    HandleObjectSetLayer(req, res);
});
```

Add wrapper definitions near the existing `CRookServer::HandleObjects` wrappers:

```cpp
void CRookServer::HandleObjectVisibility(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleObjectVisibility(req, res);
}

void CRookServer::HandleObjectSetLayer(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleObjectSetLayer(req, res);
}
```

- [ ] **Step 3: Add ObjectsHandler includes and helper types**

In `src/RookNative/Handlers/ObjectsHandler.cpp`, add these includes:

```cpp
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/WriteResult.h"

#include <set>
#include <stdexcept>
#include <unordered_set>
```

Inside the anonymous namespace, add these helpers:

```cpp
constexpr size_t kMaxExactIdObjectBatchSize = 500;

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

struct DirtyOperationError : public std::exception
{
    DirtyOperationError(ON_UUID idIn, std::string operationIn, std::string messageIn)
        : id(idIn), operation(std::move(operationIn)), message(std::move(messageIn)),
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

void EmitDirtyOperationError(httplib::Response& res, const DirtyOperationError& ex)
{
    nlohmann::json err = {
        {"errorCode", "operation_failed"},
        {"errorMessage", ex.message},
        {"id", UuidToString(ex.id)},
        {"operation", ex.operation},
        {"dirty_partial_state", true},
    };
    CRookServer::SendErrorData(res, err);
}

void RejectDuplicateUuid(std::unordered_set<std::string>& seen,
                         const std::string& id)
{
    if (seen.find(id) != seen.end())
        throw std::invalid_argument("Duplicate object id: " + id);
    seen.insert(id);
}

std::vector<ON_UUID> ParseExactObjectIds(const nlohmann::json& body,
                                         const char* fieldName,
                                         size_t maxCount)
{
    if (!body.contains(fieldName) || !body[fieldName].is_array())
        throw std::invalid_argument(std::string("Missing or invalid array: ") + fieldName);

    const auto& arr = body[fieldName];
    if (arr.empty())
        throw std::invalid_argument(std::string("'") + fieldName + "' must contain at least one id");
    if (arr.size() > maxCount)
        throw std::invalid_argument(std::string("'") + fieldName + "' cannot exceed 500 ids");

    std::vector<ON_UUID> ids;
    ids.reserve(arr.size());
    std::unordered_set<std::string> seen;

    for (size_t i = 0; i < arr.size(); ++i)
    {
        if (!arr[i].is_string())
            throw std::invalid_argument(std::string(fieldName) + "[" + std::to_string(i) + "] must be a string UUID");

        const std::string idText = arr[i].get<std::string>();
        ON_UUID id = ON_UuidFromString(idText.c_str());
        if (ON_UuidIsNil(id))
            throw std::invalid_argument("Invalid UUID format: " + idText);

        RejectDuplicateUuid(seen, UuidToString(id));
        ids.push_back(id);
    }

    return ids;
}

const CRhinoObject* LookupActiveObjectStrict(CRhinoDoc* pDoc, ON_UUID id)
{
    const CRhinoObject* obj = pDoc->LookupObject(id);
    if (!obj || obj->IsDeleted())
        throw StructuredError("not_found", "Object not found: " + UuidToString(id));
    return obj;
}

nlohmann::json SerializeObjectLayerState(CRhinoDoc* pDoc, const CRhinoObject* obj)
{
    const ON_3dmObjectAttributes& attrs = obj->Attributes();
    const int layerIndex = attrs.m_layer_index;
    bool layerVisible = false;
    std::string layerId;
    std::string layerPath;
    if (layerIndex >= 0 && layerIndex < pDoc->m_layer_table.LayerCount())
    {
        const ON_Layer& layer = pDoc->m_layer_table[layerIndex];
        if (!layer.IsDeleted())
        {
            layerVisible = layer.IsVisible();
            layerId = UuidToString(layer.Id());
            layerPath = Rook::Infrastructure::GetLayerFullPath(pDoc, layerIndex);
        }
    }

    return {
        {"layerIndex", layerIndex},
        {"layerId", layerId},
        {"layerPath", layerPath},
        {"layerVisible", layerVisible},
    };
}

nlohmann::json SerializeObjectHygieneState(CRhinoDoc* pDoc, const CRhinoObject* obj)
{
    nlohmann::json state = SerializeObjectLayerState(pDoc, obj);
    state["id"] = UuidToString(obj->Attributes().m_uuid);
    state["objectVisible"] = obj->Attributes().IsVisible();
    state["effectivelyVisible"] = obj->IsVisible();
    return state;
}
```

- [ ] **Step 4: Implement `HandleObjectVisibility`**

Add this handler in `src/RookNative/Handlers/ObjectsHandler.cpp` after `HandleObjects`:

```cpp
void HandleObjectVisibility(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::vector<ON_UUID> ids;
    bool visible = true;
    bool redraw = true;
    try
    {
        ids = ParseExactObjectIds(body, "object_ids", kMaxExactIdObjectBatchSize);
        if (!body.contains("visible") || !body["visible"].is_boolean())
            throw std::invalid_argument("Missing or invalid boolean: visible");
        visible = body["visible"].get<bool>();
        if (body.contains("redraw"))
        {
            if (!body["redraw"].is_boolean())
                throw std::invalid_argument("'redraw' must be a boolean");
            redraw = body["redraw"].get<bool>();
        }
    }
    catch (const std::invalid_argument& ex)
    {
        EmitStructuredError(res, "invalid_input", ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, ids, visible, redraw]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        std::vector<const CRhinoObject*> objects;
        objects.reserve(ids.size());
        for (ON_UUID id : ids)
            objects.push_back(LookupActiveObjectStrict(pDoc, id));

        UndoScope undo(pDoc, L"Set Object Visibility");

        int modifiedCount = 0;
        int skippedCount = 0;
        nlohmann::json results = nlohmann::json::array();

        for (const CRhinoObject* obj : objects)
        {
            const ON_UUID id = obj->Attributes().m_uuid;
            ON_3dmObjectAttributes attrs = obj->Attributes();
            const bool before = attrs.IsVisible();

            if (before == visible)
            {
                ++skippedCount;
                nlohmann::json beforeState = SerializeObjectHygieneState(pDoc, obj);
                nlohmann::json item = {
                    {"id", UuidToString(id)},
                    {"status", "unchanged"},
                    {"before", beforeState},
                    {"after", beforeState},
                };
                results.push_back(std::move(item));
                continue;
            }

            nlohmann::json beforeState = SerializeObjectHygieneState(pDoc, obj);
            attrs.SetVisible(visible);
            if (!pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs))
                throw DirtyOperationError(id, "visibility", "Failed to modify object visibility");

            const CRhinoObject* updated = LookupActiveObjectStrict(pDoc, id);
            ++modifiedCount;
            nlohmann::json item = {
                {"id", UuidToString(id)},
                {"status", "modified"},
                {"before", beforeState},
                {"after", SerializeObjectHygieneState(pDoc, updated)},
            };
            results.push_back(std::move(item));
        }

        if (redraw)
            pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["requestedCount"] = static_cast<int>(ids.size());
        wr.data["modifiedCount"] = modifiedCount;
        wr.data["skippedCount"] = skippedCount;
        wr.data["visible"] = visible;
        wr.data["results"] = std::move(results);
        return wr;
    });

    try
    {
        auto result = future.get();
        CRookServer::SendSuccess(res, result.data);
    }
    catch (const DirtyOperationError& ex)
    {
        EmitDirtyOperationError(res, ex);
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
```

- [ ] **Step 5: Implement `HandleObjectSetLayer`**

Add this handler in `src/RookNative/Handlers/ObjectsHandler.cpp` after `HandleObjectVisibility`:

```cpp
void HandleObjectSetLayer(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::vector<ON_UUID> ids;
    std::string layerName;
    bool redraw = true;
    try
    {
        ids = ParseExactObjectIds(body, "object_ids", kMaxExactIdObjectBatchSize);
        if (!body.contains("layer") || !body["layer"].is_string())
            throw std::invalid_argument("Missing or invalid string: layer");
        layerName = body["layer"].get<std::string>();
        if (layerName.empty())
            throw std::invalid_argument("'layer' cannot be empty");
        if (body.contains("redraw"))
        {
            if (!body["redraw"].is_boolean())
                throw std::invalid_argument("'redraw' must be a boolean");
            redraw = body["redraw"].get<bool>();
        }
    }
    catch (const std::invalid_argument& ex)
    {
        EmitStructuredError(res, "invalid_input", ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, ids, layerName, redraw]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const auto targetLayer = Rook::Infrastructure::ResolveLayerRef(pDoc, layerName, "layer");

        std::vector<const CRhinoObject*> objects;
        objects.reserve(ids.size());
        for (ON_UUID id : ids)
            objects.push_back(LookupActiveObjectStrict(pDoc, id));

        UndoScope undo(pDoc, L"Set Object Layer");

        int modifiedCount = 0;
        int skippedCount = 0;
        nlohmann::json results = nlohmann::json::array();

        for (const CRhinoObject* obj : objects)
        {
            const ON_UUID id = obj->Attributes().m_uuid;
            ON_3dmObjectAttributes attrs = obj->Attributes();

            if (attrs.m_layer_index == targetLayer.index)
            {
                ++skippedCount;
                nlohmann::json beforeState = SerializeObjectHygieneState(pDoc, obj);
                nlohmann::json item = {
                    {"id", UuidToString(id)},
                    {"status", "unchanged"},
                    {"before", beforeState},
                    {"after", beforeState},
                };
                results.push_back(std::move(item));
                continue;
            }

            nlohmann::json beforeState = SerializeObjectHygieneState(pDoc, obj);
            attrs.m_layer_index = targetLayer.index;
            if (!pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs))
                throw DirtyOperationError(id, "set_layer", "Failed to modify object layer");

            const CRhinoObject* updated = LookupActiveObjectStrict(pDoc, id);
            ++modifiedCount;
            nlohmann::json item = {
                {"id", UuidToString(id)},
                {"status", "modified"},
                {"before", beforeState},
                {"after", SerializeObjectHygieneState(pDoc, updated)},
            };
            results.push_back(std::move(item));
        }

        if (redraw)
            pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["requestedCount"] = static_cast<int>(ids.size());
        wr.data["modifiedCount"] = modifiedCount;
        wr.data["skippedCount"] = skippedCount;
        wr.data["layer"] = {
            {"input", layerName},
            {"index", targetLayer.index},
            {"id", UuidToString(pDoc->m_layer_table[targetLayer.index].Id())},
            {"path", targetLayer.fullPath},
        };
        wr.data["results"] = std::move(results);
        return wr;
    });

    try
    {
        auto result = future.get();
        CRookServer::SendSuccess(res, result.data);
    }
    catch (const DirtyOperationError& ex)
    {
        EmitDirtyOperationError(res, ex);
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
```

- [ ] **Step 6: Run native source tests for object handlers**

Run:

```powershell
python -m pytest mcp_server/tests/test_exact_id_object_hygiene_native_source.py -q
```

Expected after this task:

```text
FAILED ... HandleUserTextObjectSetBatch
```

The object-handler source tests should now pass; usertext batch still fails until Task 4.

- [ ] **Step 7: Commit native object handlers**

Run:

```powershell
git add src/RookNative/Handlers/ObjectsHandler.h src/RookNative/Handlers/ObjectsHandler.cpp src/RookNative/RookServer.h src/RookNative/RookServer.cpp
git commit -m "feat: add exact-id object visibility and layer routes"
```

Expected:

```text
[codex/director-prepare-take <sha>] feat: add exact-id object visibility and layer routes
```

---

### Task 4: Implement Native Usertext Batch Handler

**Files:**
- Modify: `src/RookNative/Handlers/UserTextHandler.h`
- Modify: `src/RookNative/Handlers/UserTextHandler.cpp`
- Modify: `src/RookNative/RookServer.cpp`

- [ ] **Step 1: Add the handler declaration**

In `src/RookNative/Handlers/UserTextHandler.h`, add this declaration after `HandleUserTextObjectSet`:

```cpp
void HandleUserTextObjectSetBatch(const httplib::Request& req, httplib::Response& res);
```

- [ ] **Step 2: Register the native route**

In `src/RookNative/RookServer.cpp`, add this route next to `/usertext/object-set`:

```cpp
m_server->Post("/usertext/object-set-batch", [](const httplib::Request& req, httplib::Response& res) {
    Rook::Handlers::HandleUserTextObjectSetBatch(req, res);
});
```

- [ ] **Step 3: Add batch helper types in UserTextHandler.cpp**

Inside the anonymous namespace in `src/RookNative/Handlers/UserTextHandler.cpp`, add these helpers after `StructuredError`:

```cpp
constexpr size_t kMaxUserTextObjectSetBatchItems = 500;

struct DirtyUserTextOperationError : public std::exception
{
    DirtyUserTextOperationError(ON_UUID idIn, std::string operationIn, std::string messageIn)
        : id(idIn), operation(std::move(operationIn)), message(std::move(messageIn)),
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

void EmitDirtyUserTextOperationError(httplib::Response& res, const DirtyUserTextOperationError& ex)
{
    nlohmann::json err = {
        {"errorCode", "operation_failed"},
        {"errorMessage", ex.message},
        {"id", UuidToString(ex.id)},
        {"operation", ex.operation},
        {"dirty_partial_state", true},
    };
    CRookServer::SendErrorData(res, err);
}

void RejectDuplicateUuid(std::unordered_set<std::string>& seen,
                         const std::string& id)
{
    if (seen.find(id) != seen.end())
        throw std::invalid_argument("Duplicate object id: " + id);
    seen.insert(id);
}

void ValidateBatchUserStrings(const nlohmann::json& item, size_t itemIndex)
{
    if (!item.contains("userStrings") || !item["userStrings"].is_object())
        throw std::invalid_argument("items[" + std::to_string(itemIndex) + "].userStrings must be an object");

    for (auto it = item["userStrings"].begin(); it != item["userStrings"].end(); ++it)
    {
        if (it.key().empty())
            throw std::invalid_argument("userStrings key must be non-empty");
        if (!it.value().is_string())
            throw std::invalid_argument("userStrings['" + it.key() + "'] must be a string");
        if (it.value().get<std::string>().empty())
            throw std::invalid_argument("userStrings['" + it.key() + "'] must be non-empty");
    }
}

std::vector<UserTextSetBatchItem> ParseUserTextSetBatchItems(const nlohmann::json& body)
{
    if (!body.contains("items") || !body["items"].is_array())
        throw std::invalid_argument("Missing or invalid array: items");

    const auto& arr = body["items"];
    if (arr.empty())
        throw std::invalid_argument("'items' must contain at least one object");
    if (arr.size() > kMaxUserTextObjectSetBatchItems)
        throw std::invalid_argument("'items' cannot exceed 500 objects");

    std::vector<UserTextSetBatchItem> parsed;
    parsed.reserve(arr.size());
    std::unordered_set<std::string> seen;

    for (size_t i = 0; i < arr.size(); ++i)
    {
        if (!arr[i].is_object())
            throw std::invalid_argument("items[" + std::to_string(i) + "] must be an object");
        if (!arr[i].contains("id") || !arr[i]["id"].is_string())
            throw std::invalid_argument("items[" + std::to_string(i) + "].id must be a string UUID");

        const std::string idText = arr[i]["id"].get<std::string>();
        ON_UUID id = ON_UuidFromString(idText.c_str());
        if (ON_UuidIsNil(id))
            throw std::invalid_argument("Invalid UUID format: " + idText);

        RejectDuplicateUuid(seen, UuidToString(id));
        ValidateBatchUserStrings(arr[i], i);
        parsed.push_back({ id, arr[i]["userStrings"] });
    }

    return parsed;
}

bool RequestedUserStringsAlreadyApplied(const nlohmann::json& requested,
                                        const nlohmann::json& current)
{
    for (auto it = requested.begin(); it != requested.end(); ++it)
    {
        if (!current.contains(it.key()))
            return false;
        if (!current[it.key()].is_string())
            return false;
        if (current[it.key()].get<std::string>() != it.value().get<std::string>())
            return false;
    }
    return true;
}
```

- [ ] **Step 4: Implement `HandleUserTextObjectSetBatch`**

Add this handler after `HandleUserTextObjectSet` in `src/RookNative/Handlers/UserTextHandler.cpp`:

```cpp
void HandleUserTextObjectSetBatch(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::vector<UserTextSetBatchItem> items;
    bool redraw = true;
    try
    {
        items = ParseUserTextSetBatchItems(body);
        if (body.contains("redraw"))
        {
            if (!body["redraw"].is_boolean())
                throw std::invalid_argument("'redraw' must be a boolean");
            redraw = body["redraw"].get<bool>();
        }
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

        std::vector<const CRhinoObject*> objects;
        objects.reserve(items.size());
        for (const auto& item : items)
            objects.push_back(LookupObjectStrict(item.id, pDoc));

        UndoScope undo(pDoc, L"Set Object User Strings Batch");

        int modifiedCount = 0;
        int skippedCount = 0;
        nlohmann::json results = nlohmann::json::array();

        for (size_t i = 0; i < items.size(); ++i)
        {
            const auto& item = items[i];
            const CRhinoObject* obj = objects[i];
            const nlohmann::json current =
                SerializeUserStringsFromAttributes(obj->Attributes());

            if (RequestedUserStringsAlreadyApplied(item.userStrings, current))
            {
                ++skippedCount;
                results.push_back({
                    {"id", UuidToString(item.id)},
                    {"status", "unchanged"},
                    {"userStrings", current},
                });
                continue;
            }

            ON_3dmObjectAttributes attrs = obj->Attributes();
            for (auto it = item.userStrings.begin(); it != item.userStrings.end(); ++it)
            {
                attrs.SetUserString(
                    Utf8ToWide(it.key()),
                    Utf8ToWide(it.value().get<std::string>()));
            }

            if (!pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs))
                throw DirtyUserTextOperationError(
                    item.id,
                    "usertext_set_batch",
                    "Failed to modify object user strings");

            const CRhinoObject* updated = LookupObjectStrict(item.id, pDoc);
            ++modifiedCount;
            results.push_back({
                {"id", UuidToString(item.id)},
                {"status", "modified"},
                {"userStrings", SerializeUserStringsFromAttributes(updated->Attributes())},
            });
        }

        if (redraw)
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
        CRookServer::SendSuccess(res, result.data);
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
```

- [ ] **Step 5: Run native source tests and fix compile-visible source mismatches**

Run:

```powershell
python -m pytest mcp_server/tests/test_exact_id_object_hygiene_native_source.py -q
```

Expected:

```text
6 passed
```

- [ ] **Step 6: Commit native usertext batch handler**

Run:

```powershell
git add src/RookNative/Handlers/UserTextHandler.h src/RookNative/Handlers/UserTextHandler.cpp src/RookNative/RookServer.cpp
git commit -m "feat: add exact-id object usertext batch route"
```

Expected:

```text
[codex/director-prepare-take <sha>] feat: add exact-id object usertext batch route
```

---

### Task 5: Wire MCP Schemas, Dispatch, Targeting, and Tool Groups

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/src/rook/bootstrap/executor.py`
- Modify: `mcp_server/src/rook/targeting.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`

- [ ] **Step 1: Add MCP tool schemas**

In `mcp_server/src/rook/server.py`, add this tool near `rhino_objects`:

```python
Tool(
    name="rhino_object_visibility",
    description=(
        "Set object-level visibility for exact object ids only. "
        "Does not change layer visibility; visible=true may still be effectively "
        "hidden when the layer is hidden. Rejects empty, duplicate, or over-500 ids."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "object_ids": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 500,
                "description": "Exact document object UUIDs. No selectors or patterns.",
            },
            "visible": {"type": "boolean"},
            "redraw": {"type": "boolean", "description": "Defaults to true."},
            "documentSerialNumber": {"type": "integer"},
        },
        "required": ["object_ids", "visible"],
    },
),
```

Add this tool near layer mutators:

```python
Tool(
    name="rhino_object_set_layer",
    description=(
        "Move exact object ids to an existing layer. The layer reference is an "
        "exact full path or unambiguous leaf name resolved by native layer rules. "
        "Missing or ambiguous layers fail; layers are never auto-created."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "object_ids": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 500,
            },
            "layer": {"type": "string"},
            "redraw": {"type": "boolean", "description": "Defaults to true."},
            "documentSerialNumber": {"type": "integer"},
        },
        "required": ["object_ids", "layer"],
    },
),
```

Add this tool near usertext object tools:

```python
Tool(
    name="rhino_object_usertext_set_batch",
    description=(
        "Set per-object usertext metadata for exact object ids. One item per object id. "
        "Set-only: no delete semantics. Returns full post-mutation userStrings for "
        "requested objects only. Rejects empty, duplicate, or over-500 items."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "minItems": 1,
                "maxItems": 500,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "userStrings": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                        },
                    },
                    "required": ["id", "userStrings"],
                },
            },
            "redraw": {"type": "boolean", "description": "Defaults to true."},
            "documentSerialNumber": {"type": "integer"},
        },
        "required": ["items"],
    },
),
```

- [ ] **Step 2: Add server `call_tool` dispatch cases**

In `mcp_server/src/rook/server.py`, add these match cases near related route families:

```python
case "rhino_object_visibility":
    result = await call_rhino("/objects/visibility", "POST", arguments, port=port)

case "rhino_object_set_layer":
    result = await call_rhino("/objects/set-layer", "POST", arguments, port=port)

case "rhino_object_usertext_set_batch":
    result = await call_rhino("/usertext/object-set-batch", "POST", arguments, port=port)
```

- [ ] **Step 3: Add agent dispatcher bridge routes**

In `mcp_server/src/rook/agent/tool_dispatcher.py`, add:

```python
"rhino_object_visibility": ("/objects/visibility", "POST"),
"rhino_object_set_layer": ("/objects/set-layer", "POST"),
"rhino_object_usertext_set_batch": ("/usertext/object-set-batch", "POST"),
```

Place `rhino_object_visibility` and `rhino_object_set_layer` near Rhino core/layer routes, and `rhino_object_usertext_set_batch` near the usertext routes.

- [ ] **Step 4: Add bootstrap executor mappings**

In `mcp_server/src/rook/bootstrap/executor.py`, add mappings in the native bridge map:

```python
"rhino_object_visibility": ("POST", "/objects/visibility", params),
"rhino_object_set_layer": ("POST", "/objects/set-layer", params),
"rhino_object_usertext_set_batch": ("POST", "/usertext/object-set-batch", params),
```

- [ ] **Step 5: Classify targeting policy as mutating**

In `mcp_server/src/rook/targeting.py`, add the three tools to the Rhino mutating set:

```python
"rhino_object_set_layer",
"rhino_object_usertext_set_batch",
"rhino_object_visibility",
```

Do not add these to the Rhino readonly set.

- [ ] **Step 6: Add mutating tool groups only**

In `mcp_server/src/rook/agent/tool_groups.py`, add:

```python
"object_hygiene": [
    "rhino_object_visibility",
    "rhino_object_set_layer",
    "rhino_object_usertext_set_batch",
],
```

Also add `rhino_object_set_layer` to the existing mutating `layers` group:

```python
"rhino_layer_move_objects", "rhino_object_set_layer", "rhino_layer_merge",
```

Do not add `object_hygiene` to `READONLY_ALLOWED_GROUPS`, and do not add these tools to any readonly group.

- [ ] **Step 7: Run MCP contract tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_exact_id_object_hygiene_tools.py -q
```

Expected:

```text
8 passed
```

- [ ] **Step 8: Run broader static policy tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_lm303_readonly_dispatch.py mcp_server/tests/test_dispatcher_safety.py -q
```

Expected:

```text
passed
```

- [ ] **Step 9: Commit MCP/agent wiring**

Run:

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/src/rook/bootstrap/executor.py mcp_server/src/rook/targeting.py mcp_server/src/rook/agent/tool_groups.py
git commit -m "feat: expose exact-id object hygiene tools"
```

Expected:

```text
[codex/director-prepare-take <sha>] feat: expose exact-id object hygiene tools
```

---

### Task 6: Add Cap-Boundary and Validation Tests

**Files:**
- Modify: `mcp_server/tests/test_exact_id_object_hygiene_tools.py`

- [ ] **Step 1: Add dispatcher-level cap-boundary tests for 501 ids/items**

Append this code to `mcp_server/tests/test_exact_id_object_hygiene_tools.py`:

```python
@pytest.mark.parametrize(
    "tool_name,args",
    [
        (
            "rhino_object_visibility",
            {
                "object_ids": [
                    f"11111111-1111-1111-1111-{i:012d}" for i in range(501)
                ],
                "visible": False,
            },
        ),
        (
            "rhino_object_set_layer",
            {
                "object_ids": [
                    f"11111111-1111-1111-1111-{i:012d}" for i in range(501)
                ],
                "layer": "Animation::Actors",
            },
        ),
        (
            "rhino_object_usertext_set_batch",
            {
                "items": [
                    {
                        "id": f"11111111-1111-1111-1111-{i:012d}",
                        "userStrings": {"Director::role": "actor"},
                    }
                    for i in range(501)
                ],
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_server_dispatch_forwards_501_boundary_to_native(tool_name, args):
    # Schema advertises maxItems=500, but server.call_tool intentionally forwards
    # the body unchanged so native validation remains the authoritative runtime
    # guard for every caller path.
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {
            "success": False,
            "data": {
                "errorCode": "invalid_input",
                "errorMessage": "too many ids",
            },
        }
        await server.call_tool(tool_name, args)

    sent_args, _ = mock.call_args
    assert sent_args[2] is args
```

This test does not prove native rejects 501; it proves the MCP layer does not silently trim or rewrite the payload. Native and live tests cover actual rejection.

- [ ] **Step 2: Add native source cap-boundary assertions**

Append this code to `mcp_server/tests/test_exact_id_object_hygiene_native_source.py`:

```python
def test_batch_caps_are_explicit_500_not_schema_only():
    objects_source = OBJECTS_CPP.read_text(encoding="utf-8")
    usertext_source = USER_TEXT_CPP.read_text(encoding="utf-8")

    assert "kMaxExactIdObjectBatchSize = 500" in objects_source
    assert "cannot exceed 500 ids" in objects_source
    assert "kMaxUserTextObjectSetBatchItems = 500" in usertext_source
    assert "cannot exceed 500 objects" in usertext_source
```

- [ ] **Step 3: Run focused static tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_exact_id_object_hygiene_tools.py mcp_server/tests/test_exact_id_object_hygiene_native_source.py -q
```

Expected:

```text
passed
```

- [ ] **Step 4: Commit validation test coverage**

Run:

```powershell
git add mcp_server/tests/test_exact_id_object_hygiene_tools.py mcp_server/tests/test_exact_id_object_hygiene_native_source.py
git commit -m "test: cover exact-id hygiene batch caps"
```

Expected:

```text
[codex/director-prepare-take <sha>] test: cover exact-id hygiene batch caps
```

---

### Task 7: Add Live Rhino Tests

**Files:**
- Create: `mcp_server/tests/test_exact_id_object_hygiene_live.py`

- [ ] **Step 1: Write live tests for exact state changes and neighbor safety**

Create `mcp_server/tests/test_exact_id_object_hygiene_live.py` with this content:

```python
"""Live-Rhino tests for exact-id object hygiene tools.

Run:
    python -m pytest -m requires_rhino mcp_server/tests/test_exact_id_object_hygiene_live.py -q

Rhino must be running with the current locally deployed RookNative plugin.
These tests reset the active document through the fresh_document fixture.
"""

from __future__ import annotations

from typing import Any

import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


async def _create_point(name: str, x: float = 0.0, layer: str | None = None) -> str:
    from rook.server import _mcp_tool_executor

    args: dict[str, Any] = {
        "type": "POINT",
        "point": [x, 0.0, 0.0],
        "name": name,
    }
    if layer is not None:
        args["layer"] = layer
    res = await _mcp_tool_executor("rhino_create", args)
    assert not _is_error(res), f"rhino_create failed: {res!r}"
    return res["id"]


async def _create_layer(name: str, parent: str | None = None) -> None:
    from rook.server import _mcp_tool_executor

    args: dict[str, Any] = {"name": name}
    if parent:
        args["parent"] = parent
    res = await _mcp_tool_executor("rhino_layer_create", args)
    if _is_error(res):
        assert "already exists" in str(res.get("data", "")), f"layer create failed: {res!r}"


async def _object_snapshot(obj_id: str) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_objects", {"limit": 500})
    assert not _is_error(res), f"rhino_objects failed: {res!r}"
    for obj in res.get("objects", []):
        if obj.get("id") == obj_id:
            return obj
    raise AssertionError(f"Object {obj_id} not found in snapshot {res!r}")


async def _tool(name: str, body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(name, body)
    assert not _is_error(res), f"{name} failed: {res!r}"
    return res


async def _tool_error(name: str, body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(name, body)
    assert _is_error(res), f"{name} unexpectedly succeeded: {res!r}"
    data = res.get("data") if isinstance(res, dict) else None
    assert isinstance(data, dict), f"Expected structured error data: {res!r}"
    return data


async def test_object_visibility_changes_only_requested_ids(fresh_document):
    first = await _create_point("VisibleTargetA", 0)
    second = await _create_point("VisibleTargetB", 1)
    neighbor = await _create_point("VisibleNeighbor", 2)

    res = await _tool(
        "rhino_object_visibility",
        {"object_ids": [first, second], "visible": False},
    )

    assert res["requestedCount"] == 2
    assert res["modifiedCount"] == 2
    assert res["skippedCount"] == 0
    assert {item["id"] for item in res["results"]} == {first, second}
    assert all(item["after"]["objectVisible"] is False for item in res["results"])
    assert all(item["after"]["effectivelyVisible"] is False for item in res["results"])

    assert (await _object_snapshot(first))["visible"] is False
    assert (await _object_snapshot(second))["visible"] is False
    assert (await _object_snapshot(neighbor))["visible"] is True


async def test_object_visibility_unchanged_count(fresh_document):
    obj_id = await _create_point("VisibleAlreadyTrue", 0)

    res = await _tool(
        "rhino_object_visibility",
        {"object_ids": [obj_id], "visible": True},
    )

    assert res["modifiedCount"] == 0
    assert res["skippedCount"] == 1
    assert res["results"][0]["status"] == "unchanged"
    assert res["results"][0]["before"] == res["results"][0]["after"]


async def test_object_set_layer_changes_only_requested_ids(fresh_document):
    await _create_layer("Animation")
    await _create_layer("Actors", parent="Animation")
    target_layer = "Animation::Actors"

    first = await _create_point("LayerTargetA", 0)
    second = await _create_point("LayerTargetB", 1)
    neighbor = await _create_point("LayerNeighbor", 2)

    res = await _tool(
        "rhino_object_set_layer",
        {"object_ids": [first, second], "layer": target_layer},
    )

    assert res["requestedCount"] == 2
    assert res["modifiedCount"] == 2
    assert res["skippedCount"] == 0
    assert res["layer"]["path"] == target_layer
    assert res["layer"]["id"]
    assert all(item["after"]["layerPath"] == target_layer for item in res["results"])

    assert (await _object_snapshot(first))["layer"] == target_layer
    assert (await _object_snapshot(second))["layer"] == target_layer
    assert (await _object_snapshot(neighbor))["layer"] != target_layer


async def test_object_set_layer_missing_layer_rejects_without_mutation(fresh_document):
    obj_id = await _create_point("LayerMissingTarget", 0)
    before = await _object_snapshot(obj_id)

    err = await _tool_error(
        "rhino_object_set_layer",
        {"object_ids": [obj_id], "layer": "MissingLayer__ExactIdHygiene"},
    )

    assert err["errorCode"] == "invalid_input"
    assert (await _object_snapshot(obj_id))["layer"] == before["layer"]


async def test_usertext_batch_sets_requested_objects_and_returns_full_post_state(fresh_document):
    first = await _create_point("UserTextBatchA", 0)
    second = await _create_point("UserTextBatchB", 1)
    neighbor = await _create_point("UserTextBatchNeighbor", 2)

    res = await _tool(
        "rhino_object_usertext_set_batch",
        {
            "items": [
                {"id": first, "userStrings": {"Director::role": "actor", "Director::take": "1"}},
                {"id": second, "userStrings": {"Director::role": "prop"}},
            ]
        },
    )

    assert res["requestedCount"] == 2
    assert res["modifiedCount"] == 2
    assert res["skippedCount"] == 0
    by_id = {item["id"]: item for item in res["results"]}
    assert by_id[first]["userStrings"]["Director::role"] == "actor"
    assert by_id[first]["userStrings"]["Director::take"] == "1"
    assert by_id[second]["userStrings"]["Director::role"] == "prop"

    get_neighbor = await _tool("rhino_usertext_object_get", {"id": neighbor})
    assert get_neighbor["userStrings"] == {}


async def test_usertext_batch_overwrite_and_unchanged_count(fresh_document):
    obj_id = await _create_point("UserTextBatchOverwrite", 0)

    await _tool(
        "rhino_object_usertext_set_batch",
        {"items": [{"id": obj_id, "userStrings": {"Director::role": "actor"}}]},
    )
    res = await _tool(
        "rhino_object_usertext_set_batch",
        {"items": [{"id": obj_id, "userStrings": {"Director::role": "actor"}}]},
    )

    assert res["modifiedCount"] == 0
    assert res["skippedCount"] == 1
    assert res["results"][0]["status"] == "unchanged"


@pytest.mark.parametrize(
    "tool_name,body",
    [
        ("rhino_object_visibility", {"object_ids": [], "visible": False}),
        ("rhino_object_set_layer", {"object_ids": [], "layer": "Default"}),
        ("rhino_object_usertext_set_batch", {"items": []}),
    ],
)
async def test_empty_batches_rejected(fresh_document, tool_name, body):
    err = await _tool_error(tool_name, body)
    assert err["errorCode"] == "invalid_input"


async def test_duplicate_ids_rejected_without_mutation(fresh_document):
    obj_id = await _create_point("DuplicateTarget", 0)

    err = await _tool_error(
        "rhino_object_visibility",
        {"object_ids": [obj_id, obj_id], "visible": False},
    )

    assert err["errorCode"] == "invalid_input"
    assert (await _object_snapshot(obj_id))["visible"] is True


@pytest.mark.parametrize(
    "tool_name,body",
    [
        (
            "rhino_object_visibility",
            {
                "object_ids": [f"11111111-1111-1111-1111-{i:012d}" for i in range(501)],
                "visible": False,
            },
        ),
        (
            "rhino_object_set_layer",
            {
                "object_ids": [f"11111111-1111-1111-1111-{i:012d}" for i in range(501)],
                "layer": "Default",
            },
        ),
        (
            "rhino_object_usertext_set_batch",
            {
                "items": [
                    {
                        "id": f"11111111-1111-1111-1111-{i:012d}",
                        "userStrings": {"Director::role": "actor"},
                    }
                    for i in range(501)
                ],
            },
        ),
    ],
)
async def test_501_boundary_rejected(fresh_document, tool_name, body):
    err = await _tool_error(tool_name, body)
    assert err["errorCode"] == "invalid_input"
```

- [ ] **Step 2: Run live tests against the currently deployed plugin and confirm they fail before local deploy**

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_exact_id_object_hygiene_live.py -q
```

Expected before building/deploying the native plugin:

```text
FAILED ... Unknown tool or native route missing
```

If Rhino is not reachable, expected:

```text
SKIPPED
```

- [ ] **Step 3: Commit live tests**

Run:

```powershell
git add mcp_server/tests/test_exact_id_object_hygiene_live.py
git commit -m "test: add live exact-id object hygiene coverage"
```

Expected:

```text
[codex/director-prepare-take <sha>] test: add live exact-id object hygiene coverage
```

---

### Task 8: Build, Deploy Locally, and Verify

**Files:**
- No source edits unless verification finds a defect.

- [ ] **Step 1: Run focused Python static tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_exact_id_object_hygiene_tools.py mcp_server/tests/test_exact_id_object_hygiene_native_source.py mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_lm303_readonly_dispatch.py -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Build RookNative with the known-good MSVC toolset**

Run:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected:

```text
Build succeeded.
```

- [ ] **Step 3: Deploy locally using the repo's local testing workflow**

Use the existing local deploy skill/workflow for Rook. The execution agent must read `C:/Users/aryan/.codex/skills/deploy-local-testing/SKILL.md` or `C:/Users/aryan/source/repos/Rook/.agents/skills/deploy-local-testing/SKILL.md` before running deploy commands.

Expected outcome:

```text
The installed local Rook runtime uses the freshly built Debug native plugin and matching MCP Python sources.
```

- [ ] **Step 4: Restart or reload RookNative in Rhino**

If Rhino already has an older RookNative loaded, restart Rhino or use the established local reload procedure. Confirm the active plugin is the newly deployed build before live tests.

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_exact_id_object_hygiene_live.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Run the broader related verification suite**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_prepare.py mcp_server/tests/test_director_mcp_tools.py mcp_server/tests/test_director_native_source.py mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_exact_id_object_hygiene_tools.py mcp_server/tests/test_exact_id_object_hygiene_native_source.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit any verification fixes**

If verification required edits, commit them:

```powershell
git add <changed files>
git commit -m "fix: stabilize exact-id object hygiene verification"
```

Expected:

```text
[codex/director-prepare-take <sha>] fix: stabilize exact-id object hygiene verification
```

If no fixes were needed, do not create an empty commit.

---

## Self-Review Checklist

- [ ] Spec coverage: object visibility, object layer assignment, and usertext batch are all represented in native, MCP, dispatcher, targeting, groups, static tests, and live tests.
- [ ] Exact IDs only: no selectors, no patterns, no auto-create layer option, no delete semantics.
- [ ] Caps: all three tools advertise and enforce 500-entry maximum; tests include 501 boundary cases.
- [ ] Preflight: malformed JSON shape, empty lists, duplicate ids, missing objects, and missing/ambiguous layers fail before undo/mutation.
- [ ] Runtime mutation failure: handlers return `operation_failed` with `dirty_partial_state: true`.
- [ ] Usertext response: batch returns full post-mutation `userStrings` per requested object, not before/after diffs.
- [ ] Readonly safety: no new tool appears in readonly groups or readonly targeting policy.
- [ ] Project structure: no new native files and no `.vcxproj` / `.vcxproj.filters` edits.
- [ ] Verification: Python static tests, native build, local deploy, and live Rhino tests all run before completion is claimed.
