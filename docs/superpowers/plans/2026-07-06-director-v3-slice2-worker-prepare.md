# Director v3 Slice 2: Worker Prepare + Member Map + Resolved Motion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open a Director take package's `scene.3dm` as the active document, destructively explode the declared actor-source block instances with provenance recorded at creation time, prove 100% coverage of claimed actor members, verify manifest evidence, and write `member_map.json` + `resolved_motion.json` into the package.

**Architecture:** One new native route (`POST /director/prepare-take`, new file `DirectorPrepareHandler.cpp` following the `DirectorReplayHandler` decomposition precedent) performs the destructive explode-with-provenance on the UI thread. One new Python module (`director_worker_prepare.py`, mirroring Slice 1's `director_take_package.py`) orchestrates: package validation → hash verification → document open guards → display-mode presence → native prepare → coverage/evidence verification → artifact writes. One new MCP tool (`rhino_director_prepare_take`) exposes it.

**Tech Stack:** C++ Rhino SDK (RookNative), Python 3 asyncio + pytest (mcp_server), MCP tool registration in `server.py`.

**Spec:** `docs/superpowers/specs/2026-07-06-director-v3-snapshot-boundary-design.md` — Decision 2 step 1 ("Prepare (destructive, allowed) — with provenance recorded at explode time"), plus the scene_manifest contract section. Slice 1 (merged, `d5ecea0e`) produced the packages this slice consumes.

## Global Constraints

Every task's requirements implicitly include this section.

**Non-negotiable identity contract (spec Decision 2, Codex Slice-2 guardrail):**
- Mapping keys are `(definition_object_index, definition_object_id)` plus occurrence paths for nested instances, recorded **at explode time** in the native loop — never post-hoc matching.
- Tight bbox / type / layer / name from `scene_manifest.json` are **verification evidence only**, never identity or mapping keys.
- 100% coverage of claimed actor members or hard failure `prepare_coverage_incomplete` reporting **every** skipped definition object with a reason. No silent `continue` (the v2 spike's 890→880 gap).
- Every created object gets a **fresh UUID** (`attrs.m_uuid = ON_nil_uuid` before add — the proven idiom at `BlocksHandler.cpp:4192`); the source definition-object UUID is recorded as a separate member-map field.
- Nested `InstanceReference` members are handled by **explicit recursion** emitting occurrence-path-keyed entries (`"3"`, `"3/0"`, `"3/0/2"` — definition-object indices joined by `/`) — never the generic geometry-add path.
- `resolved_motion.json` derivation fails on any unmapped member (`motion_member_unmapped`) and pins the member-map hash it was derived from. v3 motion targets are **canonical members only** (`actor_set_id` or `actor_member_id` strings); raw object UUIDs are rejected.

**Safety contract:**
- Destructive prepare must never run against anything but the opened take copy. Belt: Python compares the active document path to the package's `scene.3dm` before calling prepare (`wrong_document`). Braces: the native route receives `expectedDocumentPath` and refuses to run on a mismatch.
- Native `/document/open` **clears the current doc's modified flag to suppress the save dialog** (`DocumentOpsHandler.cpp:124`), silently discarding unsaved edits. Python must refuse to switch documents while the live doc is modified (`document_not_saved`).
- Native `/document/open` on a path that is already the active document may **no-op and report `alreadyOpen: true`** (`DocumentOpsHandler.cpp:162-172`), and because the handler cleared the modified flag first, a no-op leaves a mutated copy looking clean. Therefore: (a) when the copy is already the active document, prepare still issues a reopen, and (b) the decisive pristine gate is **object-level** — every actor-set source instance must exist in the (re)opened copy (`take_copy_not_pristine` otherwise). Dirty-flag checks alone cannot detect a mutated copy.

**Slice boundary:** No compile, no capture, no worker lifecycle/orchestration (Slices 3–4). Single-instance live gate: open `scene.3dm` as the active doc in the user's one Rhino. `compile_motion` / `director_compiler.py` are NOT modified.

**Slice 2 error taxonomy** (exact `code` strings, `DirectorWorkerPrepareError`):

| code | meaning |
|------|---------|
| `invalid_input` | bad tool arguments (missing/blank `package_root`) |
| `package_invalid` | missing package files, unparseable JSON, wrong schema/phase, malformed motion.json shape |
| `package_hash_mismatch` | motion/scene/camera/manifest hash or byte-size disagrees with manifest/status |
| `document_not_saved` | live doc has unsaved edits; switching would discard them |
| `document_open_failed` | `/document` or `/document/open` native failure |
| `wrong_document` | active doc after open is not the package's scene.3dm |
| `take_copy_not_pristine` | an actor-set source instance is missing from the opened copy — the copy was mutated (e.g. a prior prepare) and could not be freshly reloaded |
| `display_mode_missing` | a manifest-required display mode is absent in this Rhino |
| `prepare_route_failed` | `/director/prepare-take` envelope failure (includes native-side wrong-document refusal) |
| `prepare_coverage_incomplete` | any claimed member missing/skipped/identity-mismatched |
| `prepare_verification_failed` | type/layer/name/tight-bbox evidence mismatch |
| `motion_member_unmapped` | motion target/group member not a canonical actor_set_id/actor_member_id |

**Process constraints:**
- Native build: `cmd /c scripts\build-native.bat` (never raw msbuild). Deploy: `cmd /c scripts\deploy-native.bat` with Rhino closed; only the human launches/closes Rhino; verify with `rhino_ping`.
- Python tests: `cd mcp_server && python -m pytest tests/test_director_worker_prepare.py -v`.
- Pinned MCP surface counts change 438→439. Grep for the existing pinned number in `mcp_server/tests/test_server_tool_profiles.py` AND grep `rhino_director_package_take` across `mcp_server/src` and `mcp_server/tests` — the new tool must appear at **every** analogous site (targeting, profiles, tool groups, count pins). Update pin comments, don't accrete changelogs.
- Commit after every green test cycle; conventional-commit messages.

## Native Contract: `POST /director/prepare-take`

Request (camelCase, matching native JSON style):

```json
{
  "expectedDocumentPath": "C:/temp/takes/take1/scene.3dm",
  "actorSets": [
    {"actorSetId": "setA", "instanceId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
  ]
}
```

Success response `data`:

```json
{
  "documentPath": "C:\\temp\\takes\\take1\\scene.3dm",
  "actorSets": [
    {
      "actorSetId": "setA",
      "instanceId": "aaaaaaaa-...",
      "definitionName": "S2LiveOuter",
      "instanceDeleted": true,
      "members": [
        {
          "index": 0,
          "definitionObjectId": "11111111-...",
          "type": "Brep",
          "layer": "Default",
          "name": "",
          "defBbox": {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0]},
          "bboxMethod": "tight_object",
          "created": [
            {"occurrencePath": "0", "definitionObjectId": "11111111-...",
             "createdObjectId": "99999999-...", "type": "Brep"}
          ],
          "skipped": []
        },
        {
          "index": 1,
          "definitionObjectId": "22222222-...",
          "type": "InstanceReference",
          "layer": "Default",
          "name": "",
          "defBbox": {"min": [2.0, 0.0, 0.0], "max": [3.0, 1.0, 1.0]},
          "bboxMethod": "tight_object",
          "created": [
            {"occurrencePath": "1/0", "definitionObjectId": "33333333-...",
             "createdObjectId": "88888888-...", "type": "Brep"}
          ],
          "skipped": []
        }
      ]
    }
  ]
}
```

Rules:
- `defBbox` is the member's **definition-space** tight bbox via `defObj->GetTightBoundingBox(...)` — the identical call `/block/objects-detailed` used to produce the manifest evidence (`BlocksHandler.cpp:3506`), so package-time and prepare-time values compare exactly (same doubles, same geometry — the copy came from save-copy).
- Skip reasons (exact strings): `null_definition_object`, `geometry_duplicate_failed`, `nesting_too_deep`, `nested_definition_not_found`, `circular_nested_definition`, `unsupported_geometry_type:<ON class name>`.
- Definition objects with null geometry get a member entry with a skip and no bbox; they were never manifest members (objects-detailed skips them too), so Python ignores them for coverage.
- Wrong document → `WriteResult` failure with `data.reason = "wrong_document"` (surfaces via `SendErrorData`).
- After a member loop completes, the source instance object is deleted; failure to delete throws (the copy is disposable — recovery is re-open `scene.3dm`).

## Package Artifact Schemas (written by this slice)

`member_map.json`:

```json
{
  "schema_version": 1,
  "metadata_kind": "director_member_map",
  "take_id": "take1",
  "package_id": "take1-abc123def456",
  "prepared_at_utc": "2026-07-06T00:00:00+00:00",
  "scene_manifest_sha256": "<status.json's scene_manifest_sha256>",
  "actor_sets": [
    {
      "actor_set_id": "setA",
      "source_top_level_object_id": "aaaaaaaa-...",
      "exploded_instance_id": "aaaaaaaa-...",
      "members": [
        {
          "actor_member_id": "setA_member_0000",
          "definition_object_index": 0,
          "definition_object_id": "11111111-...",
          "member_type": "Brep",
          "created_object_ids": ["99999999-..."],
          "occurrences": [
            {"occurrence_path": "0", "definition_object_id": "11111111-...",
             "created_object_id": "99999999-...", "type": "Brep"}
          ]
        }
      ]
    }
  ]
}
```

**motion.json shape (the real compiler vocabulary — see `director_compiler.py:56` `resolve_compiler_timeline` and `:102` `expand_targets`, and the Slice 1 fixture `test_director_take_package.py:112`):**

```json
{
  "timeline": {"fps": 24, "frame_count": 48},
  "groups": {"roof": ["setA"]},
  "motion": [
    {"target": "roof", "keyframes": [{"t": 1, "translate": [0, 0, 8000]}]},
    {"target": "setA_member_0001", "keyframes": [{"t": 1, "translate": [0, 0, 100]}]}
  ]
}
```

`timeline` is the fps/duration **dict** (never a track list); `motion` is the track **array** whose entries carry `target` + `keyframes`.

`resolved_motion.json` = `motion.json` copied verbatim except: `groups` values become lists of created object UUIDs (canonical names expanded, order-preserving dedupe); every `motion[].target` that is a canonical name (not already a group) gets a synthesized group of that name; plus `metadata_kind: "director_resolved_motion"`, `schema_version: 1`, and `derived_from: {member_map_sha256, motion_json_sha256, scene_manifest_sha256}`. The `timeline` dict, keyframe bodies, easing, and every other motion key pass through untouched — their semantics belong to the Slice 3 file-backed compiler.

`status.json` update: `phase: "prepared"`, fresh `heartbeat_utc`, `evidence` merged with `{member_map_sha256, resolved_motion_sha256}`. Re-running prepare after a fresh re-open of scene.3dm overwrites `member_map.json` / `resolved_motion.json` (created UUIDs are new each run — that is correct; the hash pin makes the pairing unambiguous).

---

### Task 1: Native `/director/prepare-take` route

**Files:**
- Create: `src/RookNative/Handlers/DirectorPrepareHandler.h`
- Create: `src/RookNative/Handlers/DirectorPrepareHandler.cpp`
- Modify: `src/RookNative/RookServer.h` (declaration next to `HandleDirectorReplay`)
- Modify: `src/RookNative/RookServer.cpp` (route registration next to `/director/replay` at ~line 997; member forwarder next to the other director forwarders)
- Modify: `src/RookNative/RookNative.vcxproj` and `src/RookNative/RookNative.vcxproj.filters` (entries adjacent to the `DirectorReplayHandler` ones at vcxproj lines 136/275, filters lines 87/176)

**Interfaces:**
- Consumes: shared helpers `ParseBodyAndDocSn` (`Infrastructure/JsonHelpers.h`), `ResolveDoc`/`UuidToString`/`WideToUtf8`/`Utf8ToWide` (`Models/DocumentHelpers.h`), `ParseUuid` (`JsonHelpers.h`), `Rook::Infrastructure::GetLayerFullPath` (`Infrastructure/LayerHelpers.h` — namespace-qualified; same wire format as the BlocksHandler file-local static that produced the manifest), `UndoScope` (`Infrastructure/UndoScope.h`), `WriteResult` (`Infrastructure/WriteResult.h`), `CMainThreadDispatcher` (`Threading/MainThreadDispatcher.h`).
- Produces: the Native Contract above, consumed by Task 2's `_run_prepare`.

- [ ] **Step 1: Write the header**

```cpp
#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleDirectorPrepareTake(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
```

- [ ] **Step 2: Write DirectorPrepareHandler.cpp**

Mirror the include block style of `DirectorReplayHandler.cpp` (stdafx first). Full file:

```cpp
// DirectorPrepareHandler.cpp — Director v3 Slice 2 worker prepare.
//
// POST /director/prepare-take: explode declared actor-source block instances
// in the OPENED TAKE COPY with provenance recorded at creation time. The
// mapping key is (definition_object_index, definition_object_id) plus the
// occurrence path for nested instances — recorded DURING the explode, never
// matched post-hoc. Destructive by design; callers must pass
// expectedDocumentPath and the handler refuses any other active document.
// Spec: docs/superpowers/specs/2026-07-06-director-v3-snapshot-boundary-design.md

#include "stdafx.h"
#include "Handlers/DirectorPrepareHandler.h"
#include "Threading/MainThreadDispatcher.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/LayerHelpers.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/WriteResult.h"
#include "Models/DocumentHelpers.h"
#include "RookServer.h"
#include <cctype>
#include <set>
#include <string>
#include <vector>

namespace Rook {
namespace Handlers {

namespace {

constexpr int kMaxNestingDepth = 8;

// Must stay in lockstep with BlocksHandler.cpp's GetObjectTypeName —
// scene_manifest.json "expected.type" strings are produced there and
// compared for equality by director_worker_prepare.py.
std::string MemberTypeName(const CRhinoObject* obj)
{
    if (!obj) return "Unknown";
    const ON_Geometry* geom = obj->Geometry();
    if (CRhinoInstanceObject::Cast(obj)) return "InstanceReference";
    if (ON_Brep::Cast(geom)) return "Brep";
    if (ON_Mesh::Cast(geom)) return "Mesh";
    if (ON_Curve::Cast(geom)) return "Curve";
    if (ON_Point::Cast(geom)) return "Point";
    if (ON_Text::Cast(geom)) return "Text";
    return "Other";
}

// Same type coverage as BlocksHandler.cpp's AddGeometryToDoc. Unsupported
// geometry returns nullptr and the caller records a typed skip reason —
// never a silent continue.
const CRhinoObject* AddPreparedGeometry(CRhinoDoc* pDoc,
    const ON_Geometry* geom, const ON_3dmObjectAttributes* attrs)
{
    if (const ON_Curve* curve = ON_Curve::Cast(geom))
        return pDoc->AddCurveObject(*curve, attrs);
    if (const ON_Brep* brep = ON_Brep::Cast(geom))
        return pDoc->AddBrepObject(*brep, attrs);
    if (const ON_Mesh* mesh = ON_Mesh::Cast(geom))
        return pDoc->AddMeshObject(*mesh, attrs);
    if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom))
    {
        ON_Brep* brep = ext->BrepForm();
        if (brep)
        {
            const CRhinoObject* obj = pDoc->AddBrepObject(*brep, attrs);
            delete brep;
            return obj;
        }
    }
    if (const ON_Point* pt = ON_Point::Cast(geom))
        return pDoc->AddPointObject(pt->point, attrs);
    if (const ON_Surface* srf = ON_Surface::Cast(geom))
    {
        ON_Brep* brep = srf->BrepForm();
        if (brep)
        {
            const CRhinoObject* obj = pDoc->AddBrepObject(*brep, attrs);
            delete brep;
            return obj;
        }
    }
    return nullptr;
}

std::string NormalizePathForCompare(std::string s)
{
    for (char& c : s)
    {
        if (c == '\\') c = '/';
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return s;
}

void AddSkip(nlohmann::json& skipped, const std::string& path,
             const std::string& defObjId, const std::string& reason)
{
    skipped.push_back({{"occurrencePath", path},
                       {"definitionObjectId", defObjId},
                       {"reason", reason}});
}

// Recursively explode one definition object into top-level document objects.
// `accumXform` maps the object's local (definition) space to world space.
// `path` is the occurrence path of definition-object indices from the
// top-level member down ("3", "3/0", "3/0/2"). `visitedDefs` guards cycles
// per recursion branch (same pattern as BuildNestedHierarchy).
void ExplodeDefinitionObject(CRhinoDoc* pDoc, const CRhinoObject* defObj,
    const ON_Xform& accumXform, const std::string& path,
    std::set<int>& visitedDefs, int depth,
    nlohmann::json& created, nlohmann::json& skipped)
{
    if (!defObj || !defObj->Geometry())
    {
        AddSkip(skipped, path,
                defObj ? UuidToString(defObj->Attributes().m_uuid) : "",
                "null_definition_object");
        return;
    }
    const std::string defObjId = UuidToString(defObj->Attributes().m_uuid);

    if (const CRhinoInstanceObject* nestedInst = CRhinoInstanceObject::Cast(defObj))
    {
        if (depth >= kMaxNestingDepth)
        {
            AddSkip(skipped, path, defObjId, "nesting_too_deep");
            return;
        }
        const CRhinoInstanceDefinition* nestedDef = nestedInst->InstanceDefinition();
        if (!nestedDef)
        {
            AddSkip(skipped, path, defObjId, "nested_definition_not_found");
            return;
        }
        if (visitedDefs.count(nestedDef->Index()))
        {
            AddSkip(skipped, path, defObjId, "circular_nested_definition");
            return;
        }
        std::set<int> childVisited = visitedDefs;
        childVisited.insert(nestedDef->Index());
        const ON_Xform childXform = accumXform * nestedInst->InstanceXform();
        for (int j = 0; j < nestedDef->ObjectCount(); ++j)
        {
            ExplodeDefinitionObject(pDoc, nestedDef->Object(j), childXform,
                path + "/" + std::to_string(j), childVisited, depth + 1,
                created, skipped);
        }
        return;
    }

    ON_Geometry* dupGeom = defObj->Geometry()->Duplicate();
    if (!dupGeom)
    {
        AddSkip(skipped, path, defObjId, "geometry_duplicate_failed");
        return;
    }
    dupGeom->Transform(accumXform);

    ON_3dmObjectAttributes attrs = defObj->Attributes();
    attrs.m_uuid = ON_nil_uuid;  // fresh UUID mandate (spec Decision 2)
    const CRhinoObject* newObj = AddPreparedGeometry(pDoc, dupGeom, &attrs);
    if (!newObj)
    {
        const ON_ClassId* classId = defObj->Geometry()->ClassId();
        const std::string cls = classId ? classId->ClassName() : "unknown";
        AddSkip(skipped, path, defObjId, "unsupported_geometry_type:" + cls);
        delete dupGeom;
        return;
    }
    delete dupGeom;

    created.push_back({{"occurrencePath", path},
                       {"definitionObjectId", defObjId},
                       {"createdObjectId", UuidToString(newObj->Attributes().m_uuid)},
                       {"type", MemberTypeName(newObj)}});
}

} // anonymous namespace

void HandleDirectorPrepareTake(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("expectedDocumentPath") || !body["expectedDocumentPath"].is_string()
        || body["expectedDocumentPath"].get<std::string>().empty())
    {
        CRookServer::SendError(res, "expectedDocumentPath is required");
        return;
    }
    const std::string expectedPath = body["expectedDocumentPath"].get<std::string>();

    if (!body.contains("actorSets") || !body["actorSets"].is_array()
        || body["actorSets"].empty())
    {
        CRookServer::SendError(res, "actorSets must be a non-empty array");
        return;
    }

    struct ActorSetRequest { std::string actorSetId; ON_UUID instanceId; };
    std::vector<ActorSetRequest> actorSets;
    for (const auto& entry : body["actorSets"])
    {
        if (!entry.is_object() || !entry.contains("actorSetId")
            || !entry["actorSetId"].is_string())
        {
            CRookServer::SendError(res, "actorSets entries need actorSetId");
            return;
        }
        ActorSetRequest asr;
        asr.actorSetId = entry["actorSetId"].get<std::string>();
        try { asr.instanceId = ParseUuid(entry, "instanceId"); }
        catch (const std::invalid_argument& ex)
        {
            CRookServer::SendError(res, ex.what());
            return;
        }
        actorSets.push_back(std::move(asr));
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, expectedPath, actorSets]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        // Braces half of the safety contract: never explode in anything but
        // the take copy the caller thinks is open (Python holds the belt).
        ON_wString docPathW = pDoc->GetPathName();
        const std::string docPath = WideToUtf8(docPathW);
        if (NormalizePathForCompare(docPath) != NormalizePathForCompare(expectedPath))
        {
            WriteResult wr;
            wr.success = false;
            wr.data["reason"] = "wrong_document";
            wr.data["documentPath"] = docPath;
            wr.data["expectedDocumentPath"] = expectedPath;
            return wr;
        }

        UndoScope undo(pDoc, L"Director prepare take");

        nlohmann::json actorSetsJson = nlohmann::json::array();
        for (const auto& asr : actorSets)
        {
            const CRhinoObject* obj = pDoc->LookupObject(asr.instanceId);
            if (!obj)
                throw std::invalid_argument(
                    "actor set '" + asr.actorSetId + "': instance not found");
            const CRhinoInstanceObject* pInstObj = CRhinoInstanceObject::Cast(obj);
            if (!pInstObj)
                throw std::invalid_argument(
                    "actor set '" + asr.actorSetId + "': object is not a block instance");
            const CRhinoInstanceDefinition* pDef = pInstObj->InstanceDefinition();
            if (!pDef)
                throw std::runtime_error(
                    "actor set '" + asr.actorSetId + "': could not resolve instance definition");

            const ON_Xform instXform = pInstObj->InstanceXform();
            nlohmann::json members = nlohmann::json::array();

            for (int i = 0; i < pDef->ObjectCount(); ++i)
            {
                const CRhinoObject* defObj = pDef->Object(i);
                nlohmann::json member;
                member["index"] = i;
                nlohmann::json created = nlohmann::json::array();
                nlohmann::json skipped = nlohmann::json::array();

                if (!defObj || !defObj->Geometry())
                {
                    // Not a manifest member (objects-detailed skips these too);
                    // reported so nothing is ever silently dropped.
                    member["definitionObjectId"] =
                        defObj ? UuidToString(defObj->Attributes().m_uuid) : "";
                    AddSkip(skipped, std::to_string(i),
                            member["definitionObjectId"].get<std::string>(),
                            "null_definition_object");
                    member["created"] = created;
                    member["skipped"] = skipped;
                    members.push_back(std::move(member));
                    continue;
                }

                const ON_3dmObjectAttributes& defAttrs = defObj->Attributes();
                member["definitionObjectId"] = UuidToString(defAttrs.m_uuid);
                member["type"] = MemberTypeName(defObj);
                // Shared helper lives in Rook::Infrastructure — this handler
                // is in Rook::Handlers, so it MUST be qualified (BlocksHandler
                // only calls it unqualified via its own file-local static).
                // Same wire format either way: GetLayerPathName -> UTF-8.
                member["layer"] = Infrastructure::GetLayerFullPath(pDoc, defAttrs.m_layer_index);
                member["name"] = WideToUtf8(defAttrs.m_name);

                // Definition-space tight bbox — the identical call
                // /block/objects-detailed used for the manifest evidence.
                ON_BoundingBox bbox;
                const bool tight = defObj->GetTightBoundingBox(bbox) && bbox.IsValid();
                if (tight)
                {
                    member["defBbox"]["min"] = { bbox.Min().x, bbox.Min().y, bbox.Min().z };
                    member["defBbox"]["max"] = { bbox.Max().x, bbox.Max().y, bbox.Max().z };
                    member["bboxMethod"] = "tight_object";
                }
                else
                {
                    ON_BoundingBox loose = defObj->BoundingBox();
                    if (loose.IsValid())
                    {
                        member["defBbox"]["min"] = { loose.Min().x, loose.Min().y, loose.Min().z };
                        member["defBbox"]["max"] = { loose.Max().x, loose.Max().y, loose.Max().z };
                        member["bboxMethod"] = "loose_fallback";
                    }
                    else
                    {
                        member["bboxMethod"] = "unavailable";
                    }
                }

                // Fresh visited set per top-level member: the same nested
                // definition appearing under two sibling members is legal;
                // cycles only matter within one recursion chain.
                std::set<int> visited;
                visited.insert(pDef->Index());
                ExplodeDefinitionObject(pDoc, defObj, instXform,
                    std::to_string(i), visited, 0, created, skipped);

                member["created"] = std::move(created);
                member["skipped"] = std::move(skipped);
                members.push_back(std::move(member));
            }

            // Destructive removal of the source occurrence — legal only
            // because this is the disposable copy (path-gated above).
            const bool deleted = pDoc->DeleteObject(
                CRhinoObjRef(pDoc->RuntimeSerialNumber(), asr.instanceId));
            if (!deleted)
                throw std::runtime_error(
                    "actor set '" + asr.actorSetId + "': failed to delete source instance");

            nlohmann::json setJson;
            setJson["actorSetId"] = asr.actorSetId;
            setJson["instanceId"] = UuidToString(asr.instanceId);
            setJson["definitionName"] = WideToUtf8(pDef->Name());
            setJson["instanceDeleted"] = true;
            setJson["members"] = std::move(members);
            actorSetsJson.push_back(std::move(setJson));
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["documentPath"] = docPath;
        wr.data["actorSets"] = std::move(actorSetsJson);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

} // namespace Handlers
} // namespace Rook
```

Note for the implementer: if `ON_Text::Cast` in `MemberTypeName` fails to compile in this handler's include context, drop that one line and return `"Other"` for text — but first check how `BlocksHandler.cpp` gets it to compile (it uses the same cast at line ~256). If `pDoc->GetPathName()` does not compile, use the same document-path call `DocumentOpsHandler.cpp` line ~160 uses on `pNewDoc`. If `WriteResult` has no `error` member requirement here, mirror how `HandleBlockExplode` builds success/failure results.

- [ ] **Step 3: Register the route**

In `src/RookNative/RookServer.h`: grep `HandleDirectorReplay` and add the sibling declaration:

```cpp
void HandleDirectorPrepareTake(const httplib::Request& req, httplib::Response& res);
```

In `src/RookNative/RookServer.cpp`, next to the `/director/replay` registration (~line 997):

```cpp
m_server->Post("/director/prepare-take", [this](const httplib::Request& req, httplib::Response& res) {
    HandleDirectorPrepareTake(req, res);
});
```

And the member forwarder — grep `CRookServer::HandleDirectorReplay(` in `RookServer.cpp` and mirror the sibling forwarder body exactly (including its `Rook::McpRequestGuard guard;` line if the siblings carry one — copy what the neighbors do, adding the include of `Handlers/DirectorPrepareHandler.h` next to the `DirectorReplayHandler.h` include):

```cpp
void CRookServer::HandleDirectorPrepareTake(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;
    Rook::Handlers::HandleDirectorPrepareTake(req, res);
}
```

- [ ] **Step 4: vcxproj wiring**

Add next to the `DirectorReplayHandler` entries:
- `RookNative.vcxproj`: `<ClCompile Include="Handlers\DirectorPrepareHandler.cpp" />` (near line 136) and `<ClInclude Include="Handlers\DirectorPrepareHandler.h" />` (near line 275).
- `RookNative.vcxproj.filters`: mirror the two `DirectorReplayHandler` filter entries (lines ~87 and ~176) with the same `<Filter>` values.

- [ ] **Step 5: Build**

Run: `cmd /c scripts\build-native.bat`
Expected: build succeeds with zero errors. (No native unit harness exists; the compile gate + Task 4's live gate are the tests, same as Slice 1.)

- [ ] **Step 6: Commit**

```bash
git add src/RookNative/Handlers/DirectorPrepareHandler.h src/RookNative/Handlers/DirectorPrepareHandler.cpp src/RookNative/RookServer.h src/RookNative/RookServer.cpp src/RookNative/RookNative.vcxproj src/RookNative/RookNative.vcxproj.filters
git commit -m "feat(native): director prepare-take route with explode provenance"
```

---

### Task 2: `director_worker_prepare.py` (TDD)

**Files:**
- Create: `mcp_server/src/rook/director_worker_prepare.py`
- Modify: `mcp_server/src/rook/director_take_package.py` (promote three private helpers to public names; keep aliases)
- Test: `mcp_server/tests/test_director_worker_prepare.py`

**Interfaces:**
- Consumes: Slice 1 package layout (`scene_manifest.json` exactly as `package_take` writes it — see the real builder in `director_take_package.py:302-319`); native routes `/document` GET, `/document/open` POST, `/display-modes` GET, `/director/prepare-take` POST (Task 1 contract); shared helpers `sha256_file`, `canonical_json_text`, `write_canonical_json`, `utc_now_iso` from `director_take_package`.
- Produces: `async def prepare_take(arguments, *, call_native=call_rhino, port=None, now_fn=utc_now_iso) -> dict` raising `DirectorWorkerPrepareError(code, message)` with `.to_data()`; `member_map.json` + `resolved_motion.json` + updated `status.json` in the package. Task 3's MCP dispatch and Slice 3's file-backed compiler consume these.

- [ ] **Step 1: Promote the Slice 1 helpers**

In `director_take_package.py`, rename `_utc_now`→`utc_now_iso`, `_sha256_file`→`sha256_file`, `_write_json`→`write_canonical_json`, add `canonical_json_text`, and keep backward-compat aliases so nothing else moves:

```python
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_text(payload: dict[str, Any]) -> str:
    """The ONE serialization all package hashes are computed over."""
    return json.dumps(payload, indent=2, sort_keys=True)


def write_canonical_json(path: Path, payload: dict[str, Any]) -> str:
    text = canonical_json_text(payload)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Backward-compat aliases (internal call sites + any test references).
_utc_now = utc_now_iso
_sha256_file = sha256_file
_write_json = write_canonical_json
```

Update the `package_take` signature default `now_fn=_utc_now` to `now_fn=utc_now_iso` (alias keeps old references working). Run the Slice 1 suite to prove no regression:

Run: `cd mcp_server && python -m pytest tests/test_director_take_package.py -v`
Expected: all pass (13 tests + 1 dispatch test).

- [ ] **Step 2: Write the failing tests**

`mcp_server/tests/test_director_worker_prepare.py` — complete file:

```python
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from rook import director_worker_prepare as dwp
from rook.director_take_package import canonical_json_text, write_canonical_json

pytestmark = pytest.mark.asyncio

LIVE_DOC_PATH = "C:/work/live_project.3dm"

MEMBER0_ID = "11111111-1111-1111-1111-111111111111"
MEMBER1_ID = "22222222-2222-2222-2222-222222222222"
NESTED_LEAF_ID = "33333333-3333-3333-3333-333333333333"
INSTANCE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CREATED0_ID = "99999999-9999-9999-9999-999999999999"
CREATED1_ID = "88888888-8888-8888-8888-888888888888"


def make_manifest(scene_sha: str, scene_bytes: int, motion_sha: str) -> dict:
    return {
        "schema_version": 1,
        "metadata_kind": "director_take_package_manifest",
        "take_id": "take1",
        "created_at_utc": "2026-07-06T00:00:00+00:00",
        "source_document": {"path": LIVE_DOC_PATH, "modified_at_package_time": False,
                            "object_count": 10, "units": "Millimeters"},
        "scene": {"file": "scene.3dm", "mechanism": "save_copy", "evidence": {},
                  "bytes": scene_bytes, "sha256": scene_sha},
        "actor_sets": [{
            "actor_set_id": "setA",
            "block_name": "S2Outer",
            "source_top_level_object_id": INSTANCE_ID,
            "source_instance": {"instance_id": INSTANCE_ID},
            "member_count": 2,
            "members": [
                {"actor_member_id": "setA_member_0000",
                 "definition_object_index": 0,
                 "definition_object_id": MEMBER0_ID,
                 "expected": {"type": "Brep", "layer": "Default", "name": ""},
                 "bbox_evidence": {"bbox_method": "tight_object",
                                   "bbox_space": "definition_object",
                                   "min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0],
                                   "rounding_policy": "round_to_4_decimal_places",
                                   "validation_strength": "tight_bbox"}},
                {"actor_member_id": "setA_member_0001",
                 "definition_object_index": 1,
                 "definition_object_id": MEMBER1_ID,
                 "expected": {"type": "InstanceReference", "layer": "Default", "name": ""},
                 "bbox_evidence": {"bbox_method": "tight_object",
                                   "bbox_space": "definition_object",
                                   "min": [2.0, 0.0, 0.0], "max": [3.0, 1.0, 1.0],
                                   "rounding_policy": "round_to_4_decimal_places",
                                   "validation_strength": "tight_bbox"}},
            ],
        }],
        "display_mode_requirements": [
            {"name": "Shaded", "id": "mode-1", "settings_fingerprint": None}],
        "hashes": {"motion_json_sha256": motion_sha, "camera_json_sha256": None,
                   "scene_3dm_sha256": scene_sha, "scene_3dm_bytes": scene_bytes},
    }


def make_motion() -> dict:
    # The REAL compiler vocabulary (director_compiler.py:56/:102; Slice 1
    # fixture test_director_take_package.py:112): timeline is the fps dict,
    # motion is the track array.
    return {
        "timeline": {"fps": 24, "frame_count": 48},
        "groups": {"roof": ["setA"]},
        "motion": [
            {"target": "roof", "keyframes": [{"t": 1, "translate": [0, 0, 8000]}]},
            {"target": "setA_member_0001",
             "keyframes": [{"t": 1, "translate": [0, 0, 100]}]},
        ],
    }


def make_package(tmp_path: Path, *, motion: dict | None = None,
                 tamper: str | None = None) -> Path:
    root = tmp_path / "take1"
    root.mkdir()
    scene = root / "scene.3dm"
    scene.write_bytes(b"fake-3dm-bytes")
    motion = motion if motion is not None else make_motion()
    motion_text = canonical_json_text(motion)
    (root / "motion.json").write_text(motion_text, encoding="utf-8")
    motion_sha = hashlib.sha256(motion_text.encode("utf-8")).hexdigest()
    scene_sha = hashlib.sha256(b"fake-3dm-bytes").hexdigest()
    manifest = make_manifest(scene_sha, len(b"fake-3dm-bytes"), motion_sha)
    manifest_sha = write_canonical_json(root / "scene_manifest.json", manifest)
    write_canonical_json(root / "status.json", {
        "schema_version": 1, "package_id": "take1-abc123def456", "take_id": "take1",
        "phase": "packaged", "heartbeat_utc": "2026-07-06T00:00:00+00:00",
        "scene_manifest_sha256": manifest_sha,
        "evidence": {"scene_mechanism": "save_copy"}})

    if tamper == "motion":
        (root / "motion.json").write_text(motion_text + " ", encoding="utf-8")
    elif tamper == "scene":
        scene.write_bytes(b"fake-3dm-bytes-tampered")
    elif tamper == "manifest":
        text = (root / "scene_manifest.json").read_text(encoding="utf-8")
        (root / "scene_manifest.json").write_text(text + " ", encoding="utf-8")
    return root


def make_prepare_payload(root: Path, **overrides: Any) -> dict:
    member0 = {
        "index": 0, "definitionObjectId": MEMBER0_ID, "type": "Brep",
        "layer": overrides.get("member0_layer", "Default"), "name": "",
        "defBbox": overrides.get(
            "member0_bbox", {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0]}),
        "bboxMethod": "tight_object",
        "created": [{"occurrencePath": "0", "definitionObjectId": MEMBER0_ID,
                     "createdObjectId": CREATED0_ID, "type": "Brep"}],
        "skipped": [],
    }
    member1 = {
        "index": 1, "definitionObjectId": MEMBER1_ID, "type": "InstanceReference",
        "layer": "Default", "name": "",
        "defBbox": {"min": [2.0, 0.0, 0.0], "max": [3.0, 1.0, 1.0]},
        "bboxMethod": "tight_object",
        "created": [{"occurrencePath": "1/0", "definitionObjectId": NESTED_LEAF_ID,
                     "createdObjectId": CREATED1_ID, "type": "Brep"}],
        "skipped": [],
    }
    if overrides.get("member1_skip"):
        member1["created"] = []
        member1["skipped"] = [{"occurrencePath": "1/0",
                               "definitionObjectId": NESTED_LEAF_ID,
                               "reason": "unsupported_geometry_type:ON_SubD"}]
    members = [member0, member1]
    if overrides.get("drop_member1"):
        members = [member0]
    return {
        "documentPath": str(root / "scene.3dm"),
        "actorSets": [{"actorSetId": "setA", "instanceId": INSTANCE_ID,
                       "definitionName": "S2Outer", "instanceDeleted": True,
                       "members": members}],
    }


def make_fake_native(root: Path, *, live_modified: bool = False,
                     open_ok: bool = True, opened_path: str | None = None,
                     start_on_scene: bool = False,
                     instance_missing: bool = False,
                     modes: tuple[str, ...] = ("Shaded",),
                     prepare_ok: bool = True,
                     prepare_payload: dict | None = None):
    """Stateful fake: /document reports the live doc until /document/open
    succeeds, then reports the opened path. start_on_scene=True simulates a
    take copy already being the active document (the re-prepare scenario);
    instance_missing=True simulates a mutated copy (source instance gone)."""
    scene_path = str(root / "scene.3dm")
    state = {"opened": start_on_scene, "calls": []}

    async def fake(endpoint: str, method: str, data: dict | None = None, *,
                   port: int | None = None) -> dict:
        state["calls"].append((endpoint, method, data))
        if endpoint == "/document" and method == "GET":
            if state["opened"]:
                return {"success": True, "data": {
                    "path": opened_path or scene_path, "modified": False,
                    "objectCount": 10}}
            return {"success": True, "data": {
                "path": LIVE_DOC_PATH, "modified": live_modified,
                "objectCount": 10}}
        if endpoint == "/document/open":
            if not open_ok:
                return {"success": False, "data": {"error": "open failed"}}
            state["opened"] = True
            return {"success": True, "data": {"path": data["path"]}}
        if endpoint == "/block/instances":
            instances = [] if instance_missing else [{"id": INSTANCE_ID}]
            return {"success": True, "data": {"instances": instances}}
        if endpoint == "/display-modes":
            return {"success": True, "data": {
                "modes": [{"name": n, "id": f"mode-{i}"}
                          for i, n in enumerate(modes, start=1)]}}
        if endpoint == "/director/prepare-take":
            if not prepare_ok:
                return {"success": False, "data": {"reason": "wrong_document"}}
            return {"success": True,
                    "data": prepare_payload or make_prepare_payload(root)}
        raise AssertionError(f"unexpected native call: {endpoint}")

    fake.state = state
    return fake


async def expect_error(coro, code: str) -> dwp.DirectorWorkerPrepareError:
    with pytest.raises(dwp.DirectorWorkerPrepareError) as exc_info:
        await coro
    assert exc_info.value.code == code, exc_info.value
    return exc_info.value


async def test_missing_package_root_rejected(tmp_path):
    fake = make_fake_native(tmp_path)
    await expect_error(dwp.prepare_take({}, call_native=fake), "invalid_input")


async def test_missing_manifest_rejected(tmp_path):
    root = make_package(tmp_path)
    (root / "scene_manifest.json").unlink()
    fake = make_fake_native(root)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "package_invalid")


async def test_bad_phase_rejected(tmp_path):
    root = make_package(tmp_path)
    status = json.loads((root / "status.json").read_text(encoding="utf-8"))
    status["phase"] = "captured"
    write_canonical_json(root / "status.json", status)
    fake = make_fake_native(root)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "package_invalid")


async def test_motion_hash_mismatch_rejected(tmp_path):
    root = make_package(tmp_path, tamper="motion")
    fake = make_fake_native(root)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "package_hash_mismatch")


async def test_scene_hash_mismatch_rejected(tmp_path):
    root = make_package(tmp_path, tamper="scene")
    fake = make_fake_native(root)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "package_hash_mismatch")


async def test_manifest_tamper_rejected(tmp_path):
    root = make_package(tmp_path, tamper="manifest")
    fake = make_fake_native(root)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "package_hash_mismatch")


async def test_modified_live_document_blocks_open(tmp_path):
    root = make_package(tmp_path)
    fake = make_fake_native(root, live_modified=True)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "document_not_saved")
    # The guard must fire BEFORE any /document/open call.
    assert not any(c[0] == "/document/open" for c in fake.state["calls"])


async def test_open_failure_surfaces(tmp_path):
    root = make_package(tmp_path)
    fake = make_fake_native(root, open_ok=False)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "document_open_failed")


async def test_wrong_document_after_open(tmp_path):
    root = make_package(tmp_path)
    fake = make_fake_native(root, opened_path="C:/somewhere/else.3dm")
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "wrong_document")


async def test_reprepare_forces_reopen_of_open_copy(tmp_path):
    # Re-prepare scenario: the take copy is ALREADY the active document
    # (e.g. a previous prepare ran in this session). A fresh reopen must be
    # issued anyway — the in-memory copy may be mutated, and the dirty flag
    # is unreliable (native /document/open force-clears it).
    root = make_package(tmp_path)
    fake = make_fake_native(root, start_on_scene=True)
    result = await dwp.prepare_take({"package_root": str(root)}, call_native=fake)
    assert result["phase"] == "prepared"
    assert any(c[0] == "/document/open" for c in fake.state["calls"]), (
        "same-path prepare must force a fresh reopen of scene.3dm")


async def test_mutated_copy_rejected_as_not_pristine(tmp_path):
    # If the source instance is gone after (re)open — a prior prepare
    # exploded it and the reopen no-opped (alreadyOpen) — prepare must
    # refuse before any destructive call.
    root = make_package(tmp_path)
    fake = make_fake_native(root, start_on_scene=True, instance_missing=True)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "take_copy_not_pristine")
    assert not any(c[0] == "/director/prepare-take"
                   for c in fake.state["calls"])


async def test_missing_display_mode_rejected(tmp_path):
    root = make_package(tmp_path)
    fake = make_fake_native(root, modes=("Wireframe",))
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "display_mode_missing")


async def test_prepare_route_failure_surfaces(tmp_path):
    root = make_package(tmp_path)
    fake = make_fake_native(root, prepare_ok=False)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "prepare_route_failed")


async def test_coverage_incomplete_on_skip(tmp_path):
    root = make_package(tmp_path)
    fake = make_fake_native(
        root, prepare_payload=make_prepare_payload(root, member1_skip=True))
    err = await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "prepare_coverage_incomplete")
    assert "unsupported_geometry_type:ON_SubD" in str(err)
    assert "setA_member_0001" in str(err)


async def test_coverage_incomplete_on_missing_member(tmp_path):
    root = make_package(tmp_path)
    fake = make_fake_native(
        root, prepare_payload=make_prepare_payload(root, drop_member1=True))
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "prepare_coverage_incomplete")


async def test_verification_failure_on_bbox_mismatch(tmp_path):
    root = make_package(tmp_path)
    payload = make_prepare_payload(
        root, member0_bbox={"min": [0.0, 0.0, 0.0], "max": [1.5, 1.0, 1.0]})
    fake = make_fake_native(root, prepare_payload=payload)
    err = await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "prepare_verification_failed")
    assert "setA_member_0000" in str(err)


async def test_verification_failure_on_layer_mismatch(tmp_path):
    root = make_package(tmp_path)
    payload = make_prepare_payload(root, member0_layer="OtherLayer")
    fake = make_fake_native(root, prepare_payload=payload)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "prepare_verification_failed")


async def test_happy_path_writes_all_artifacts(tmp_path):
    root = make_package(tmp_path)
    fake = make_fake_native(root)
    result = await dwp.prepare_take(
        {"package_root": str(root)}, call_native=fake,
        now_fn=lambda: "2026-07-06T01:00:00+00:00")

    assert result["phase"] == "prepared"
    assert result["actor_sets"] == [{
        "actor_set_id": "setA", "member_count": 2, "created_object_count": 2}]

    member_map = json.loads((root / "member_map.json").read_text(encoding="utf-8"))
    assert member_map["metadata_kind"] == "director_member_map"
    members = member_map["actor_sets"][0]["members"]
    # Fresh UUID proof: created id differs from the definition-object id.
    assert members[0]["created_object_ids"] == [CREATED0_ID]
    assert members[0]["created_object_ids"][0] != members[0]["definition_object_id"]
    # Nested provenance: occurrence path keys the nested leaf.
    assert members[1]["occurrences"][0]["occurrence_path"] == "1/0"
    assert members[1]["occurrences"][0]["definition_object_id"] == NESTED_LEAF_ID

    member_map_text = (root / "member_map.json").read_text(encoding="utf-8")
    member_map_sha = hashlib.sha256(member_map_text.encode("utf-8")).hexdigest()
    assert result["member_map_sha256"] == member_map_sha

    resolved = json.loads((root / "resolved_motion.json").read_text(encoding="utf-8"))
    assert resolved["metadata_kind"] == "director_resolved_motion"
    # Group "roof" contained canonical set id "setA" -> all created ids.
    assert resolved["groups"]["roof"] == [CREATED0_ID, CREATED1_ID]
    # Bare canonical target became a synthesized group.
    assert resolved["groups"]["setA_member_0001"] == [CREATED1_ID]
    assert resolved["derived_from"]["member_map_sha256"] == member_map_sha
    # Untouched motion keys pass through — timeline is the fps DICT, never
    # rewritten (real compiler vocabulary).
    assert resolved["timeline"] == {"fps": 24, "frame_count": 48}
    assert resolved["motion"] == make_motion()["motion"]

    status = json.loads((root / "status.json").read_text(encoding="utf-8"))
    assert status["phase"] == "prepared"
    assert status["evidence"]["member_map_sha256"] == member_map_sha


async def test_unmapped_motion_target_rejected(tmp_path):
    motion = make_motion()
    motion["motion"].append(
        {"target": "not_a_member", "keyframes": [{"t": 1}]})
    root = make_package(tmp_path, motion=motion)
    fake = make_fake_native(root)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "motion_member_unmapped")
    # Failed derivation must not leave partial artifacts.
    assert not (root / "member_map.json").exists()
    assert not (root / "resolved_motion.json").exists()


async def test_raw_uuid_motion_target_rejected(tmp_path):
    motion = make_motion()
    motion["groups"]["roof"] = ["44444444-4444-4444-4444-444444444444"]
    root = make_package(tmp_path, motion=motion)
    fake = make_fake_native(root)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "motion_member_unmapped")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd mcp_server && python -m pytest tests/test_director_worker_prepare.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rook.director_worker_prepare'` (or import errors on the promoted helpers if Step 1 was skipped).

- [ ] **Step 4: Write the module**

`mcp_server/src/rook/director_worker_prepare.py` — complete file:

```python
"""Director v3 Slice 2: worker prepare + member map + resolved motion.

Spec: docs/superpowers/specs/2026-07-06-director-v3-snapshot-boundary-design.md
(Decision 2, step 1). Opens a take package's scene.3dm as the active document
(the disposable copy — destructive explode is legal there), validates the
package against scene_manifest.json, explodes declared actor-source instances
via POST /director/prepare-take (provenance recorded at creation time),
proves 100% coverage of claimed members, verifies type/layer/name/tight-bbox
evidence, writes member_map.json, and derives resolved_motion.json.

Mapping keys are (definition_object_index, definition_object_id) plus
occurrence paths for nested instances. Tight bbox / type / layer / name are
VERIFICATION evidence only — never identity.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .bridge import call_rhino
from .director_take_package import (
    PACKAGE_SCHEMA_VERSION,
    canonical_json_text,
    sha256_file,
    utc_now_iso,
)

MEMBER_MAP_SCHEMA_VERSION = 1


class DirectorWorkerPrepareError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

    def to_data(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self)}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _norm_path(value: str) -> str:
    return str(Path(value)).replace("\\", "/").casefold()


async def _native(call_native, endpoint: str, method: str, data: dict | None,
                  port: int | None, error_code: str) -> Any:
    envelope = await call_native(endpoint, method, data, port=port)
    if not isinstance(envelope, dict) or not envelope.get("success"):
        detail = envelope.get("data") if isinstance(envelope, dict) else envelope
        raise DirectorWorkerPrepareError(error_code, f"{endpoint} failed: {detail}")
    return envelope.get("data")


def _load_package(package_root_arg: Any) -> dict[str, Any]:
    if not isinstance(package_root_arg, str) or not package_root_arg.strip():
        raise DirectorWorkerPrepareError("invalid_input", "package_root is required")
    root = Path(package_root_arg).expanduser().resolve()
    if not root.is_dir():
        raise DirectorWorkerPrepareError(
            "package_invalid", f"not a package directory: {root}")
    for required in ("scene_manifest.json", "scene.3dm", "motion.json", "status.json"):
        if not (root / required).is_file():
            raise DirectorWorkerPrepareError(
                "package_invalid", f"package is missing {required}")
    try:
        manifest = json.loads((root / "scene_manifest.json").read_text(encoding="utf-8"))
        status = json.loads((root / "status.json").read_text(encoding="utf-8"))
        motion = json.loads((root / "motion.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DirectorWorkerPrepareError(
            "package_invalid", f"unparseable package JSON: {exc}") from exc
    if (manifest.get("schema_version") != PACKAGE_SCHEMA_VERSION
            or manifest.get("metadata_kind") != "director_take_package_manifest"):
        raise DirectorWorkerPrepareError(
            "package_invalid", "unrecognized scene_manifest.json schema")
    if status.get("phase") not in ("packaged", "prepared"):
        raise DirectorWorkerPrepareError(
            "package_invalid",
            f"package phase {status.get('phase')!r} is not preparable")
    if not isinstance(manifest.get("actor_sets"), list) or not manifest["actor_sets"]:
        raise DirectorWorkerPrepareError(
            "package_invalid", "scene_manifest.json has no actor_sets")
    return {"root": root, "manifest": manifest, "status": status, "motion": motion}


def _verify_package_hashes(pkg: dict[str, Any]) -> None:
    root, manifest, status = pkg["root"], pkg["manifest"], pkg["status"]
    hashes = manifest.get("hashes") or {}
    mismatches: list[str] = []

    motion_sha = _sha256_text((root / "motion.json").read_text(encoding="utf-8"))
    if motion_sha != hashes.get("motion_json_sha256"):
        mismatches.append("motion.json")

    scene = root / "scene.3dm"
    if (sha256_file(scene) != hashes.get("scene_3dm_sha256")
            or scene.stat().st_size != hashes.get("scene_3dm_bytes")):
        mismatches.append("scene.3dm")

    camera_sha = hashes.get("camera_json_sha256")
    if camera_sha is not None:
        camera = root / "camera.json"
        if not camera.is_file() or _sha256_text(
                camera.read_text(encoding="utf-8")) != camera_sha:
            mismatches.append("camera.json")

    manifest_sha = _sha256_text(
        (root / "scene_manifest.json").read_text(encoding="utf-8"))
    if manifest_sha != status.get("scene_manifest_sha256"):
        mismatches.append("scene_manifest.json")

    if mismatches:
        raise DirectorWorkerPrepareError(
            "package_hash_mismatch",
            "package artifacts disagree with recorded hashes: "
            + ", ".join(mismatches))


async def _open_scene_document(call_native, pkg: dict[str, Any],
                               port: int | None) -> None:
    scene_path = pkg["root"] / "scene.3dm"
    live = await _native(call_native, "/document", "GET", None, port,
                         "document_open_failed")
    already_on_scene = (
        _norm_path(live.get("path") or "") == _norm_path(str(scene_path)))
    if not already_on_scene and bool(live.get("modified")):
        # Switching documents discards unsaved edits: native /document/open
        # clears the modified flag to suppress the save dialog
        # (DocumentOpsHandler.cpp:124). Refuse on a dirty live document.
        raise DirectorWorkerPrepareError(
            "document_not_saved",
            "the current document has unsaved changes; opening the take "
            "copy would silently discard them — save the document first")
    # ALWAYS (re)open — including when the copy is already active. A prior
    # prepare may have mutated the in-memory copy, and the modified flag is
    # unreliable here (native /document/open force-clears it before opening,
    # and its same-path branch can no-op with alreadyOpen=true —
    # DocumentOpsHandler.cpp:162-172). The object-level pristine gate below
    # (_verify_take_copy_pristine) is the decisive check for a no-op reopen.
    await _native(call_native, "/document/open", "POST",
                  {"path": str(scene_path)}, port, "document_open_failed")
    after = await _native(call_native, "/document", "GET", None, port,
                          "document_open_failed")
    if _norm_path(after.get("path") or "") != _norm_path(str(scene_path)):
        raise DirectorWorkerPrepareError(
            "wrong_document",
            f"active document is {after.get('path')!r}; expected the take "
            f"copy {scene_path}")


async def _verify_take_copy_pristine(call_native, manifest: dict[str, Any],
                                     port: int | None) -> None:
    """Object-level pristine gate: every actor-set source instance must
    exist in the opened copy. A prior prepare deletes the source instances,
    so their absence proves the copy is mutated (flag checks cannot — see
    _open_scene_document). Mirrors Slice 1's /block/instances resolution."""
    for actor in manifest["actor_sets"]:
        data = await _native(call_native, "/block/instances", "POST",
                             {"name": actor["block_name"]}, port,
                             "take_copy_not_pristine")
        ids = {inst.get("id") for inst in data.get("instances") or []}
        if actor["source_top_level_object_id"] not in ids:
            raise DirectorWorkerPrepareError(
                "take_copy_not_pristine",
                f"actor set {actor['actor_set_id']!r}: source instance "
                f"{actor['source_top_level_object_id']} is missing from the "
                "opened copy — the copy was mutated (e.g. a prior prepare) "
                "and the reopen did not reload it; close the document in "
                "Rhino and re-run prepare")


async def _verify_display_modes(call_native, manifest: dict[str, Any],
                                port: int | None) -> None:
    data = await _native(call_native, "/display-modes", "GET", None, port,
                         "display_mode_missing")
    available = {m.get("name") for m in data.get("modes", [])}
    required = [r.get("name") for r in manifest.get("display_mode_requirements") or []]
    missing = [name for name in required if name not in available]
    if missing:
        raise DirectorWorkerPrepareError(
            "display_mode_missing",
            f"required display modes not present in this Rhino: {missing}")


async def _run_prepare(call_native, pkg: dict[str, Any],
                       port: int | None) -> dict[str, Any]:
    manifest = pkg["manifest"]
    actor_sets = [
        {"actorSetId": a["actor_set_id"],
         "instanceId": a["source_top_level_object_id"]}
        for a in manifest["actor_sets"]
    ]
    return await _native(
        call_native, "/director/prepare-take", "POST",
        {"expectedDocumentPath": str(pkg["root"] / "scene.3dm"),
         "actorSets": actor_sets},
        port, "prepare_route_failed")


def _verify_and_map(manifest: dict[str, Any],
                    prepare_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Coverage proof + evidence verification. Returns member-map actor sets.

    Coverage failures (missing/skipped/identity mismatch) and verification
    failures (type/layer/name/bbox evidence) are collected exhaustively so a
    single failed run reports every problem, then coverage wins precedence.
    """
    by_set = {s.get("actorSetId"): s for s in prepare_data.get("actorSets") or []}
    coverage: list[str] = []
    verification: list[str] = []
    map_sets: list[dict[str, Any]] = []

    for actor in manifest["actor_sets"]:
        set_id = actor["actor_set_id"]
        prepared = by_set.get(set_id)
        if prepared is None:
            coverage.append(f"{set_id}: absent from prepare response")
            continue
        members_by_index = {m.get("index"): m for m in prepared.get("members") or []}
        map_members: list[dict[str, Any]] = []

        for member in actor["members"]:
            mid = member["actor_member_id"]
            idx = member["definition_object_index"]
            got = members_by_index.get(idx)
            if got is None:
                coverage.append(f"{mid}: no prepare entry for definition index {idx}")
                continue
            if got.get("definitionObjectId") != member["definition_object_id"]:
                coverage.append(
                    f"{mid}: definition object id changed "
                    f"({member['definition_object_id']} -> "
                    f"{got.get('definitionObjectId')}) — take copy does not "
                    "match the manifest")
                continue
            for skip in got.get("skipped") or []:
                coverage.append(
                    f"{mid}: skipped {skip.get('occurrencePath')}: "
                    f"{skip.get('reason')}")
            created = got.get("created") or []
            if not created:
                coverage.append(f"{mid}: no objects created")

            expected = member["expected"]
            if got.get("type") != expected.get("type"):
                verification.append(
                    f"{mid}: type {got.get('type')!r} != expected "
                    f"{expected.get('type')!r}")
            if got.get("layer") != expected.get("layer"):
                verification.append(
                    f"{mid}: layer {got.get('layer')!r} != expected "
                    f"{expected.get('layer')!r}")
            if (got.get("name") or "") != (expected.get("name") or ""):
                verification.append(f"{mid}: name mismatch")
            evidence = member["bbox_evidence"]
            if got.get("bboxMethod") != "tight_object":
                verification.append(
                    f"{mid}: bboxMethod {got.get('bboxMethod')!r} is not "
                    "tight_object")
            else:
                bbox = got.get("defBbox") or {}
                got_min = [round(v, 4) for v in bbox.get("min") or []]
                got_max = [round(v, 4) for v in bbox.get("max") or []]
                if got_min != evidence["min"] or got_max != evidence["max"]:
                    verification.append(
                        f"{mid}: definition-space tight bbox mismatch "
                        f"({got_min}/{got_max} != "
                        f"{evidence['min']}/{evidence['max']})")

            map_members.append({
                "actor_member_id": mid,
                "definition_object_index": idx,
                "definition_object_id": member["definition_object_id"],
                "member_type": expected.get("type"),
                "created_object_ids": [c["createdObjectId"] for c in created],
                "occurrences": [
                    {"occurrence_path": c.get("occurrencePath"),
                     "definition_object_id": c.get("definitionObjectId"),
                     "created_object_id": c.get("createdObjectId"),
                     "type": c.get("type")}
                    for c in created
                ],
            })

        map_sets.append({
            "actor_set_id": set_id,
            "source_top_level_object_id": actor["source_top_level_object_id"],
            "exploded_instance_id": prepared.get("instanceId"),
            "members": map_members,
        })

    if coverage:
        raise DirectorWorkerPrepareError(
            "prepare_coverage_incomplete", "; ".join(coverage))
    if verification:
        raise DirectorWorkerPrepareError(
            "prepare_verification_failed", "; ".join(verification))
    return map_sets


def _derive_resolved_motion(motion: dict[str, Any],
                            map_sets: list[dict[str, Any]],
                            derived_from: dict[str, Any]) -> dict[str, Any]:
    lookup: dict[str, list[str]] = {}
    for actor in map_sets:
        set_ids: list[str] = []
        for member in actor["members"]:
            lookup[member["actor_member_id"]] = list(member["created_object_ids"])
            set_ids.extend(member["created_object_ids"])
        lookup[actor["actor_set_id"]] = set_ids

    def expand(names: list[Any], context: str) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for name in names:
            ids = lookup.get(name) if isinstance(name, str) else None
            if ids is None:
                raise DirectorWorkerPrepareError(
                    "motion_member_unmapped",
                    f"{context}: {name!r} is not a canonical actor_set_id or "
                    "actor_member_id (v3 motion targets are canonical members "
                    "only — raw object UUIDs are not allowed)")
            for oid in ids:
                if oid not in seen:
                    seen.add(oid)
                    out.append(oid)
        return out

    # Real compiler vocabulary (director_compiler.py:56/:102): timeline is
    # the fps/duration DICT (passes through untouched); motion is the track
    # ARRAY whose entries carry target + keyframes.
    if not isinstance(motion.get("timeline"), dict):
        raise DirectorWorkerPrepareError(
            "package_invalid", "motion.json timeline must be an object")

    groups_in = motion.get("groups") or {}
    if not isinstance(groups_in, dict):
        raise DirectorWorkerPrepareError(
            "package_invalid", "motion.json groups must be an object")
    resolved_groups: dict[str, list[str]] = {}
    for name, members in groups_in.items():
        if not isinstance(members, list) or not members:
            raise DirectorWorkerPrepareError(
                "package_invalid",
                f"motion.json group {name!r} must be a non-empty list")
        resolved_groups[name] = expand(members, f"group {name!r}")

    tracks = motion.get("motion")
    if not isinstance(tracks, list) or not tracks:
        raise DirectorWorkerPrepareError(
            "package_invalid", "motion.json must contain a non-empty motion array")
    for track in tracks:
        if not isinstance(track, dict):
            raise DirectorWorkerPrepareError(
                "package_invalid", "motion.json motion entries must be objects")
        target = track.get("target")
        if not isinstance(target, str) or not target:
            raise DirectorWorkerPrepareError(
                "package_invalid",
                "motion.json motion entries need a string target")
        if target in resolved_groups:
            continue
        resolved_groups[target] = expand([target], f"target {target!r}")

    resolved = dict(motion)
    resolved["groups"] = resolved_groups
    resolved["metadata_kind"] = "director_resolved_motion"
    resolved["schema_version"] = MEMBER_MAP_SCHEMA_VERSION
    resolved["derived_from"] = derived_from
    return resolved


async def prepare_take(arguments: dict[str, Any], *, call_native=call_rhino,
                       port: int | None = None,
                       now_fn=utc_now_iso) -> dict[str, Any]:
    pkg = _load_package(arguments.get("package_root"))
    _verify_package_hashes(pkg)
    await _open_scene_document(call_native, pkg, port)
    await _verify_take_copy_pristine(call_native, pkg["manifest"], port)
    await _verify_display_modes(call_native, pkg["manifest"], port)
    prepare_data = await _run_prepare(call_native, pkg, port)
    map_sets = _verify_and_map(pkg["manifest"], prepare_data)

    manifest_sha = pkg["status"].get("scene_manifest_sha256")
    member_map = {
        "schema_version": MEMBER_MAP_SCHEMA_VERSION,
        "metadata_kind": "director_member_map",
        "take_id": pkg["manifest"]["take_id"],
        "package_id": pkg["status"].get("package_id"),
        "prepared_at_utc": now_fn(),
        "scene_manifest_sha256": manifest_sha,
        "actor_sets": map_sets,
    }
    # Hash before writing so a failed resolved-motion derivation leaves no
    # partial artifacts (all-or-nothing writes below).
    member_map_text = canonical_json_text(member_map)
    member_map_sha = _sha256_text(member_map_text)

    resolved = _derive_resolved_motion(pkg["motion"], map_sets, {
        "member_map_sha256": member_map_sha,
        "motion_json_sha256": pkg["manifest"]["hashes"]["motion_json_sha256"],
        "scene_manifest_sha256": manifest_sha,
    })
    resolved_text = canonical_json_text(resolved)
    resolved_sha = _sha256_text(resolved_text)

    (pkg["root"] / "member_map.json").write_text(member_map_text, encoding="utf-8")
    (pkg["root"] / "resolved_motion.json").write_text(resolved_text, encoding="utf-8")

    status = dict(pkg["status"])
    status["phase"] = "prepared"
    status["heartbeat_utc"] = now_fn()
    status["evidence"] = {**(status.get("evidence") or {}),
                          "member_map_sha256": member_map_sha,
                          "resolved_motion_sha256": resolved_sha}
    status_text = canonical_json_text(status)
    (pkg["root"] / "status.json").write_text(status_text, encoding="utf-8")

    return {
        "package_root": str(pkg["root"]),
        "take_id": member_map["take_id"],
        "package_id": member_map["package_id"],
        "phase": "prepared",
        "actor_sets": [
            {"actor_set_id": s["actor_set_id"],
             "member_count": len(s["members"]),
             "created_object_count": sum(
                 len(m["created_object_ids"]) for m in s["members"])}
            for s in map_sets
        ],
        "member_map_sha256": member_map_sha,
        "resolved_motion_sha256": resolved_sha,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd mcp_server && python -m pytest tests/test_director_worker_prepare.py tests/test_director_take_package.py -v`
Expected: 20 new tests PASS + all Slice 1 tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/director_worker_prepare.py mcp_server/src/rook/director_take_package.py mcp_server/tests/test_director_worker_prepare.py
git commit -m "feat(director): worker prepare with member map + resolved motion"
```

---

### Task 3: `rhino_director_prepare_take` MCP tool + classification

**Files:**
- Modify: `mcp_server/src/rook/server.py` (Tool definition + dispatch)
- Modify: every classification/profile/count site that mentions `rhino_director_package_take` — find them ALL with `rg -n "rhino_director_package_take" mcp_server/src mcp_server/tests` and mirror each one, with ONE deliberate exception below.
- Test: `mcp_server/tests/test_director_worker_prepare.py` (append dispatch test), `mcp_server/tests/test_server_tool_profiles.py` (pins 438→439)

**Interfaces:**
- Consumes: `director_worker_prepare.prepare_take` + `DirectorWorkerPrepareError` (Task 2).
- Produces: MCP tool `rhino_director_prepare_take` with `inputSchema` requiring `package_root` (string); success envelope `{"success": true, "data": <prepare_take return>}`, failure `{"success": false, "data": {"code", "message"}}` — identical envelope discipline to `rhino_director_package_take`.

- [ ] **Step 1: Write the failing dispatch test**

Append to `mcp_server/tests/test_director_worker_prepare.py`, mirroring the existing `rhino_director_package_take` dispatch test in `tests/test_director_take_package.py` (same patching style, same envelope assertions — read that test first and keep the structure identical):

```python
async def test_mcp_dispatch_prepare_take():
    from unittest.mock import AsyncMock, patch

    from rook import server

    with patch.object(server.director_worker_prepare, "prepare_take",
                      new_callable=AsyncMock) as mock_prepare:
        mock_prepare.return_value = {"phase": "prepared", "take_id": "take1"}
        result = await server.call_tool(
            "rhino_director_prepare_take", {"package_root": "C:/takes/take1"})
    payload = json.loads(result[0].text)
    assert payload["success"] is True
    assert payload["data"]["phase"] == "prepared"
    mock_prepare.assert_awaited_once()
```

If the Slice 1 dispatch test imports/patches differently (module attribute vs direct import), copy its exact mechanics — the test above is the shape, the Slice 1 test is the authority.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_director_worker_prepare.py::test_mcp_dispatch_prepare_take -v`
Expected: FAIL (unknown tool).

- [ ] **Step 3: Register the tool**

In `server.py`, grep `rhino_director_package_take` and mirror both its Tool definition and its dispatch branch. Tool definition:

```python
Tool(
    name="rhino_director_prepare_take",
    description=(
        "Director v3 worker prepare (Slice 2). Opens a take package's "
        "scene.3dm as the ACTIVE document (destructive on the copy: explodes "
        "declared actor-source block instances), records provenance-at-"
        "creation member mapping, proves 100% member coverage, verifies "
        "manifest evidence, writes member_map.json and resolved_motion.json "
        "into the package, and advances status.json to phase 'prepared'. "
        "Refuses to run if the current document has unsaved changes "
        "(switching documents would discard them)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "package_root": {
                "type": "string",
                "description": "Take package directory created by "
                               "rhino_director_package_take",
            },
        },
        "required": ["package_root"],
    },
),
```

Dispatch branch (mirror the package_take branch's import style, port handling, and error serialization exactly):

```python
if name == "rhino_director_prepare_take":
    try:
        data = await director_worker_prepare.prepare_take(arguments, port=port)
        return _text_result({"success": True, "data": data})
    except director_worker_prepare.DirectorWorkerPrepareError as exc:
        return _text_result({"success": False, "data": exc.to_data()})
```

(The helper names above are illustrative — use whatever the `rhino_director_package_take` branch actually uses; it is the authority.)

- [ ] **Step 4: Classify the tool everywhere**

Run `rg -n "rhino_director_package_take" mcp_server/src mcp_server/tests`. For each hit, add `rhino_director_prepare_take` at the analogous site — with ONE exception: `rhino_director_prepare_take` is **destructive** (explodes objects, switches documents), so it must NOT be added to any read-only set (`_RHINO_READ_TOOLS` in `targeting.py` or any read-only profile list where package_take appears because packaging is read-only). Expected sites:
- `mcp_server/src/rook/targeting.py` — `_ALL_KNOWN_TOOLS` yes; `_RHINO_READ_TOOLS` **no**.
- `mcp_server/src/rook/agent/tool_groups.py` — director group yes.
- Any `mcp_tool_profiles.py` classification — mirror with write/destructive semantics.
- `mcp_server/tests/test_server_tool_profiles.py` — pinned counts 438→439 (grep the pinned number; update every pin and its comment; if a read-only-count assertion balances reads + excluded == full, the new tool lands on the excluded side).

- [ ] **Step 5: Run the full affected suites**

Run: `cd mcp_server && python -m pytest tests/test_director_worker_prepare.py tests/test_server_tool_profiles.py tests/test_director_take_package.py -v`
Expected: all PASS (21 in the new file: 20 from Task 2 + 1 dispatch).

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/server.py mcp_server/src/rook/targeting.py mcp_server/src/rook/agent/tool_groups.py mcp_server/tests/test_director_worker_prepare.py mcp_server/tests/test_server_tool_profiles.py
git commit -m "feat(mcp): rhino_director_prepare_take tool + classification"
```

(Include `mcp_tool_profiles.py` in the add list if Step 4 touched it.)

---

### Task 4: Live gate

**Files:**
- Test: `mcp_server/tests/test_director_worker_prepare_live.py`

**Interfaces:**
- Consumes: everything above, deployed to a live Rhino (native rebuild + deploy REQUIRED — Task 1's route must exist in the loaded plugin). Native routes `/block/create` (`{name, ids, basePoint, replaceWithInstance}` — returns the created instance; read `HandleBlockCreate`'s response fields before asserting), `/document`, `/document/open`; helpers `_require_host`/`_post`/`_get` and `_create_brep` from `tests/conftest.py` exactly as `test_director_take_package_live.py` uses them (read that file first — it is the template).
- Produces: the Slice 2 live proof; resolves nothing further (Slice 3 owns compile).

**Why this flow is safe (document this in the test docstring):** the gate verifies the live doc is UNMODIFIED before touching anything. Fixture objects are then created in the live doc (dirtying it), the package is built (save-copy works on a dirty doc), and `/document/open` switches to the take copy — deliberately discarding the only unsaved changes, which are the fixture itself. Re-opening the original path at the end restores the user's document to its saved state with zero residue. No undo bookkeeping needed.

**Environment gates:** `pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]` plus an explicit opt-in — skip unless `os.environ.get("ROOK_S2_DOC_SWITCH") == "1"` — because this test switches the active document twice. The controller sets the env var only after the human confirms the open Rhino may switch documents.

- [ ] **Step 1: Write the live test**

`mcp_server/tests/test_director_worker_prepare_live.py` — complete file:

```python
"""Slice 2 live gate: package -> open copy -> prepare -> verify -> restore.

DOCUMENT-SWITCHING TEST. Requires ROOK_S2_DOC_SWITCH=1 and an unmodified
live document. Fixture objects are created in the live doc and deliberately
discarded by the document switch (they are the only unsaved changes — the
gate refuses to run otherwise), so the user's document is restored to its
saved state with zero residue.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from rook import director_take_package as dtp
from rook import director_worker_prepare as dwp
from .conftest import _create_brep

pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


def _require_opt_in() -> None:
    if os.environ.get("ROOK_S2_DOC_SWITCH") != "1":
        pytest.skip("Set ROOK_S2_DOC_SWITCH=1 to allow document switching.")


def _require_host() -> str:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")
    return base_url  # type: ignore[return-value]


async def _post(route: str, body: dict[str, Any]) -> dict[str, Any]:
    base_url = _require_host()
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{base_url}{route}", json=body)
    return resp.json()


async def _get(route: str) -> dict[str, Any]:
    base_url = _require_host()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{base_url}{route}")
    return resp.json()


async def _doc() -> dict[str, Any]:
    envelope = await _get("/document")
    assert envelope.get("success"), envelope
    return envelope["data"]


async def _make_block(name: str, object_ids: list[str]) -> dict[str, Any]:
    envelope = await _post("/block/create", {
        "name": name, "ids": object_ids, "basePoint": [0.0, 0.0, 0.0],
        "replaceWithInstance": True})
    assert envelope.get("success"), envelope
    return envelope["data"]


def _instance_id_from_create(data: dict[str, Any]) -> str:
    # Read the actual response shape of /block/create in the live plugin;
    # prefer an explicit instance id field, else fall back to
    # /block/instances lookup by block name.
    for key in ("instanceId", "instance_id", "id"):
        if isinstance(data.get(key), str):
            return data[key]
    raise AssertionError(f"no instance id in /block/create response: {data}")


async def _instance_id(block_name: str) -> str:
    envelope = await _post("/block/instances", {"name": block_name})
    assert envelope.get("success"), envelope
    instances = envelope["data"].get("instances") or []
    assert len(instances) == 1, instances
    return instances[0]["id"]


async def test_prepare_round_trip_with_nested_block(tmp_path):
    _require_opt_in()
    before = await _doc()
    if before.get("modified"):
        pytest.skip("Live document has unsaved changes; save it first — the "
                    "gate discards unsaved edits by design.")
    original_path = before.get("path") or ""
    assert original_path, "live document must have a path to restore to"

    run = uuid4().hex[:8]
    inner_name = f"S2LiveInner_{run}"
    outer_name = f"S2LiveOuter_{run}"

    # Fixture: inner block (one box), then outer block containing the inner
    # instance + a second box -> outer definition has a Brep member and an
    # InstanceReference member (the nested-recursion proof).
    inner_box = await _create_brep([0.0, 0.0, 0.0], [1.0, 1.0, 1.0],
                                   f"s2_inner_{run}")
    await _make_block(inner_name, [inner_box])
    inner_instance = await _instance_id(inner_name)
    outer_box = await _create_brep([2.0, 0.0, 0.0], [3.0, 1.0, 1.0],
                                   f"s2_outer_{run}")
    await _make_block(outer_name, [outer_box, inner_instance])
    outer_instance = await _instance_id(outer_name)

    # Package the take (read-only on the live doc; save-copy handles dirty).
    motion = {
        "timeline": {"fps": 24, "frame_count": 48},
        "groups": {"all": ["s2live"]},
        "motion": [
            {"target": "all",
             "keyframes": [{"t": 1, "translate": [0, 0, 100]}]},
            {"target": "s2live_member_0001",
             "keyframes": [{"t": 1, "translate": [0, 0, 50]}]},
        ],
    }
    package = await dtp.package_take({
        "take_id": f"s2live_{run}",
        "output_root": str(tmp_path),
        "actor_sets": [{"actor_set_id": "s2live", "block_name": outer_name,
                        "source_top_level_object_id": outer_instance}],
        "motion": motion,
        "display_modes": ["Shaded"],
    })
    package_root = package["package_root"]
    manifest = json.loads(
        (Path(package_root) / "scene_manifest.json").read_text(encoding="utf-8"))
    member_types = [m["expected"]["type"]
                    for m in manifest["actor_sets"][0]["members"]]
    assert "InstanceReference" in member_types, member_types

    # Prepare: switches to the copy, explodes, maps, resolves.
    result = await dwp.prepare_take({"package_root": package_root})
    assert result["phase"] == "prepared"
    (summary,) = result["actor_sets"]
    assert summary["member_count"] == len(manifest["actor_sets"][0]["members"])
    assert summary["created_object_count"] >= 2

    member_map = json.loads(
        (Path(package_root) / "member_map.json").read_text(encoding="utf-8"))
    members = member_map["actor_sets"][0]["members"]
    nested = [m for m in members if m["member_type"] == "InstanceReference"]
    assert nested, "nested member missing from member map"
    nested_paths = [o["occurrence_path"] for o in nested[0]["occurrences"]]
    assert all("/" in p for p in nested_paths), nested_paths
    for m in members:
        assert m["created_object_ids"], m
        assert m["definition_object_id"] not in m["created_object_ids"], (
            "created object reused the definition-object UUID — fresh-UUID "
            "mandate violated")

    # Created objects really exist in the opened copy.
    all_created = [oid for m in members for oid in m["created_object_ids"]]
    states = await _post("/director/object-states", {"object_ids": all_created})
    assert states.get("success"), states
    assert len(states["data"].get("objects") or []) == len(all_created)

    resolved = json.loads(
        (Path(package_root) / "resolved_motion.json").read_text(encoding="utf-8"))
    assert set(resolved["groups"]["all"]) == set(all_created)
    assert resolved["derived_from"]["member_map_sha256"] == (
        result["member_map_sha256"])

    status = json.loads(
        (Path(package_root) / "status.json").read_text(encoding="utf-8"))
    assert status["phase"] == "prepared"

    # Restore the user's document (fixture evaporates: it was never saved).
    restore = await _post("/document/open", {"path": original_path})
    assert restore.get("success"), restore
    after = await _doc()
    assert (after.get("path") or "").lower() == original_path.lower()
```

Adjust `_instance_id_from_create` usage or drop it if `/block/instances` lookup (used above) is sufficient — the lookup path is the one actually exercised; delete the unused helper before committing if it stays unused.

- [ ] **Step 2: Deploy handoff (controller + human)**

1. Human closes Rhino.
2. Run: `cmd /c scripts\deploy-native.bat`
3. Human reopens Rhino and the working document; controller verifies with `rhino_ping`.

- [ ] **Step 3: Run the gate**

Human confirms the open Rhino may switch documents (the fixture flow above). Then:

Run: `cd mcp_server && set ROOK_S2_DOC_SWITCH=1 && python -m pytest tests/test_director_worker_prepare_live.py -v`
Expected: 1 passed. On failure: diagnose, fix, re-run (a failed run may leave the take copy open — re-open the original document via `rhino_document_ops` open before re-running).

- [ ] **Step 4: Scale proof (controller-driven, optional but planned)**

With the human's Pearson document open and saved: run `rhino_director_package_take` on the 890-member roof block (`3D_BLOCK_ARCH_ROOF_0502 UPLIFT ROOF - VERTICAL`, instance `a28cbdb5-51fa-46b2-b18b-ab880b54ded7`), then `rhino_director_prepare_take` on the package. Success = phase `prepared` with 100% coverage (every member mapped — the v2 spike lost 10 of 890 here). If any member fails coverage with `unsupported_geometry_type:*`, record the exact reasons — that is the Slice 2 follow-up list, not a reason to widen this slice. Restore the Pearson doc via `/document/open` afterwards.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/tests/test_director_worker_prepare_live.py
git commit -m "test(director): slice 2 live gate — prepare round trip with nested block"
```

---

## Self-Review Notes (writing-plans checklist)

- **Spec coverage:** Decision 2 step 1 fully covered (provenance at explode time ✓ Task 1; fresh UUIDs ✓ Task 1; nested recursion with occurrence paths ✓ Task 1; skip reporting + 100% coverage ✓ Tasks 1–2; resolved_motion with member-map hash pin ✓ Task 2; evidence-not-identity ✓ Task 2). Display-mode presence check included as read-only validation (spec plan-shape item 2); the fail-hard *capture-time* verification with fingerprints remains Slice 4.
- **Deliberate exclusions (slice boundary):** no compile, no capture, no worker lifecycle, no `.ini` fingerprints, no SubD/text/hatch/point-cloud add support (typed skip reasons surface real demand first — YAGNI).
- **Type consistency:** `prepare_take(arguments, *, call_native, port, now_fn)` matches Slice 1's `package_take` shape; camelCase on the native wire, snake_case in package artifacts, matching Slice 1 conventions.
- **Known risk, accepted:** `/block/objects-detailed` bbox for nested InstanceReference members must label `tight_object` for packaging to succeed on nested fixtures — `CRhinoInstanceObject::GetTightBoundingBox` resolves through the nested definition, and the Slice 1 live gate already proved tight-bbox packaging on a real block. If the live gate hits `tight_bbox_unavailable` at packaging, that is a Slice 1 evidence gap to report, not to silently patch here.

## Codex Review Round 1 (2026-07-06) — amendments applied

1. **Motion schema corrected (P1):** plan had invented `timeline`-as-track-list; real vocabulary is `{"timeline": {fps,...}, "groups": {...}, "motion": [tracks]}` (`director_compiler.py:56/:102`, Slice 1 fixture). `_derive_resolved_motion`, all test fixtures, and the live-gate motion now use the real shape; `timeline` dict passes through untouched.
2. **Re-prepare on a mutated copy blocked (P1, hardened beyond the finding):** verified that native `/document/open` force-clears the modified flag and its same-path branch can no-op with `alreadyOpen: true` — so a dirty-flag branch cannot detect a mutated copy. Fix: unconditional reopen when the copy is already active, plus a decisive **object-level pristine gate** (`_verify_take_copy_pristine`: every actor-set source instance must exist in the opened copy, via `/block/instances`; `take_copy_not_pristine` otherwise). `/director/object-states` was rejected for this check because it throws on missing ids. Two new unit tests.
3. **Layer helper qualified (P2):** `Rook::Infrastructure::GetLayerFullPath` — the handler lives in `Rook::Handlers`, so unqualified lookup never reaches it (BlocksHandler only works unqualified via its own file-local static).
4. **`rg` over `grep -rn` in Task 3 commands (P3).**
