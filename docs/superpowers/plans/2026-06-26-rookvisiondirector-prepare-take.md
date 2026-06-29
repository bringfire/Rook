# RookVisionDirector Prepare Take Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build metadata-only `prepare_take` so Rook can produce an audit-grade, replay-independent source evidence archive for every reachable object under selected Rhino source roots.

**Architecture:** `prepare_take` succeeds only if Python produces a complete provenance JSONL stream for every reachable object under the selected roots. Native returns paged Rhino facts; Python owns durable meaning, including source fingerprinting, actor identity, classification, materialization status, audit, manifest, and response. The manifest and response are indexes over the finalized evidence stream, not the source of truth.

**Tech Stack:** Python MCP server under `mcp_server/src/rook`, pytest tests under `mcp_server/tests`, Rhino 8 C++ native handlers under `src/RookNative`, `nlohmann::json`, `cpp-httplib`.

---

## Core Invariant

`prepare_take` succeeds only if Python produces a complete, audit-grade provenance stream for every reachable object under the selected roots. The manifest and response are indexes over that evidence, not the source of truth.

This means:

- Provenance JSONL is the primary artifact.
- Native pages are transient facts.
- Python enriches and appends each page as it arrives.
- Python keeps compact summaries in memory, not one giant inventory list.
- `source_document_key` is storage identity only.
- `source_document_fingerprint` is source fidelity and staleness evidence.
- No Rhino document mutation occurs in this slice.
- No generated actor object, proxy object, duplicate geometry, Director layer, or replay target exists in this slice.

## File Responsibilities

- `mcp_server/src/rook/director_prepare.py`: request parsing, source id resolution, storage resolution, `PrepareEvidenceWriter`, source fingerprinting, page ingestion, audit writing, manifest writing, response shaping, and failure cleanup.
- `mcp_server/src/rook/server.py`: MCP registration and dispatch for `rhino_director_prepare_take`.
- `mcp_server/src/rook/agent/tool_groups.py`: add `rhino_director_prepare_take` to `director` only.
- `mcp_server/tests/test_director_prepare.py`: unit tests for evidence streaming, source keys, fingerprints, summaries, actors, failure cleanup, and response shape.
- `mcp_server/tests/test_director_mcp_tools.py`: MCP schema, dispatch, and tool group tests.
- `mcp_server/tests/test_director_native_source.py`: static tests for native route declaration, `/document` session fields, and route registration.
- `mcp_server/tests/test_director_routes_live.py`: live Rhino smoke tests for paged nested occurrence inventory and end-to-end prepare.
- `src/RookNative/Models/Snapshots.h`: extend `DocumentSnapshot` with document session facts used by unsaved prepare storage.
- `src/RookNative/Handlers/DocumentHandler.cpp`: populate `DocumentSnapshot.documentSessionId` and `isSaved`.
- `src/RookNative/Serialization/RhinoSerializer.cpp`: serialize `documentSessionId` and `isSaved` from `/document`.
- `src/RookNative/Handlers/DirectorHandler.h`: declare `HandleDirectorOccurrenceInventory`.
- `src/RookNative/Handlers/DirectorHandler.cpp`: implement read-only paged occurrence inventory and return Rhino facts only.
- `src/RookNative/RookServer.h`: declare route wrapper.
- `src/RookNative/RookServer.cpp`: register `/director/occurrence-inventory`.

## Public Tool Contract

Tool name:

```text
rhino_director_prepare_take
```

Input:

```json
{
  "scope": "selected_occurrences",
  "source_object_ids": ["11111111-1111-1111-1111-111111111111"],
  "use_current_selection": false,
  "page_size": 500,
  "classify_nested": false,
  "write_markdown_audit": true,
  "portable": false,
  "output_root": null
}
```

Success response:

```json
{
  "take_id": "take_20260626_153012_7b4c",
  "prepare_status": "complete",
  "storage_mode": "global",
  "source_document_key": "doc_6a8f4e2c",
  "source_document_key_scope": "saved_document",
  "source_document_fingerprint": {
    "schema_version": 1,
    "hash": "..."
  },
  "actor_count": 1,
  "provenance_record_count": 42,
  "validation_status": "valid",
  "paths": {
    "take_manifest": "C:/...",
    "provenance_records": "C:/...",
    "audit_report_json": "C:/...",
    "audit_report_markdown": "C:/..."
  },
  "warnings": []
}
```

Errors use `DirectorPrepareError.code`:

- `missing_source_selection`
- `unsupported_scope`
- `invalid_source_object_ids`
- `invalid_storage_options`
- `source_document_unsaved`
- `invalid_page_size`
- `inventory_stale`
- `inventory_session_invalid`
- `inventory_cursor_missing`
- `native_response_invalid`
- `invalid_output_root`
- `missing_unsaved_document_session`
- `missing_source_top_level_object_id`
- `missing_source_object_id`
- `missing_source_snapshot_fact`
- `provenance_hash_mismatch`
- `take_already_exists`

## Storage Contract

- Default: `%LOCALAPPDATA%/Rook/director_takes/<source_document_key>/<take_id>/`
- Custom: `<output_root>/<source_document_key>/<take_id>/`
- Portable: `<3dm folder>/.rook/director_takes/<take_id>/`
- `output_root` plus `portable: true` returns `invalid_storage_options`.
- Unsaved document plus `portable: true` returns `source_document_unsaved`.
- Saved `source_document_key` is based on normalized document path or stable OS file identity if available.
- Unsaved `source_document_key` is based on an explicit generated unsaved-session token keyed by `/document.documentSessionId`.
- Native `/document` must return `documentSessionId` for unsaved documents. That id is a generated document-session handle, not the Rhino runtime serial string.
- `source_document_key` must not include runtime serial, file size, modified time, unit system, selected object ids, block facts, bbox facts, or traversal facts.

## Failure Policy

Slice one deletes temp artifacts on failure by default. It does not quarantine incomplete runs.

Rules:

- All sidecars are written under a temp run directory first.
- A successful run atomically renames the temp run directory to the final take directory.
- If any page fails, if the session becomes stale, or if manifest/audit writing fails, Python removes the temp run directory.
- No finalized manifest may exist with `prepare_status: "complete"` unless the provenance JSONL stream was finalized.
- Quarantine can be added as a debug mode in a separate change. If added, consumers must reject `prepare_status: "incomplete"` unconditionally.

## Task 1: Evidence-Centered Python Tests

**Files:**

- Create: `mcp_server/tests/test_director_prepare.py`
- Create: `mcp_server/src/rook/director_prepare.py`

- [ ] **Step 1: Write the failing test file**

Create `mcp_server/tests/test_director_prepare.py`:

```python
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rook import director_prepare as dp


U1 = "11111111-1111-1111-1111-111111111111"
U2 = "22222222-2222-2222-2222-222222222222"
U3 = "33333333-3333-3333-3333-333333333333"


def _saved_document(**overrides):
    data = {
        "path": "C:/Project/Axon_Pearson_Experimental.3dm",
        "is_saved": True,
        "size": 100,
        "modified_time": "2026-06-26T12:00:00Z",
        "runtime_serial": 99,
        "unit_system": "Meters",
        "documentSessionId": "saved-doc-session",
        "isSaved": True,
    }
    data.update(overrides)
    return data


def _actor_root_record():
    return {
        "record_kind": "actor_root",
        "source_top_level_object_id": U1,
        "source_occurrence_path": [
            {
                "kind": "top_instance",
                "object_id": U1,
                "object_name": "Bridge",
                "object_type": "instance_reference",
                "layer_path": "Model::Bridge",
                "material_ref": {"kind": "layer", "name": "Default"},
                "local_bbox": [[0, 0, 0], [10, 2, 2]],
                "world_transform": dp.IDENTITY_TRANSFORM,
                "world_bbox": [[0, 0, 0], [10, 2, 2]],
            }
        ],
        "object_id": U1,
        "object_name": "Bridge",
        "object_type": "instance_reference",
        "layer_path": "Model::Bridge",
        "material_ref": {"kind": "layer", "name": "Default"},
        "local_bbox": [[0, 0, 0], [10, 2, 2]],
        "world_transform": dp.IDENTITY_TRANSFORM,
        "world_bbox": [[0, 0, 0], [10, 2, 2]],
        "native_role_hint": "instance_reference",
    }


def _definition_record():
    return {
        "record_kind": "definition_object",
        "source_top_level_object_id": U1,
        "source_occurrence_path": [
            {
                "kind": "top_instance",
                "object_id": U1,
                "object_name": "Bridge",
                "object_type": "instance_reference",
                "layer_path": "Model::Bridge",
                "material_ref": {"kind": "layer", "name": "Default"},
                "local_bbox": [[0, 0, 0], [10, 2, 2]],
                "world_transform": dp.IDENTITY_TRANSFORM,
                "world_bbox": [[0, 0, 0], [10, 2, 2]],
            },
            {
                "kind": "definition_object",
                "definition_name": "Bridge_Block",
                "definition_id": "def-bridge",
                "definition_object_index": 0,
                "sibling_ordinal": 0,
                "object_id": U2,
                "object_name": "roof_mass",
                "object_type": "brep",
                "layer_path": "Model::Roof",
                "material_ref": {"kind": "object", "name": "Roof Metal"},
                "local_bbox": [[0, 0, 0], [10, 2, 1]],
                "world_transform": dp.IDENTITY_TRANSFORM,
                "world_bbox": [[0, 0, 2], [10, 2, 3]],
            },
        ],
        "object_id": U2,
        "object_name": "roof_mass",
        "object_type": "brep",
        "layer_path": "Model::Roof",
        "material_ref": {"kind": "object", "name": "Roof Metal"},
        "local_bbox": [[0, 0, 0], [10, 2, 1]],
        "world_transform": dp.IDENTITY_TRANSFORM,
        "world_bbox": [[0, 0, 2], [10, 2, 3]],
        "native_role_hint": "geometry",
    }


def _nested_instance_record(root_id=U1):
    return {
        "record_kind": "nested_instance",
        "source_top_level_object_id": root_id,
        "source_occurrence_path": [
            {
                "kind": "top_instance",
                "object_id": root_id,
                "object_name": "Bridge",
                "object_type": "instance_reference",
                "layer_path": "Model::Bridge",
                "material_ref": {"kind": "layer", "name": "Default"},
                "local_bbox": [[0, 0, 0], [10, 2, 2]],
                "world_transform": dp.IDENTITY_TRANSFORM,
                "world_bbox": [[0, 0, 0], [10, 2, 2]],
            },
            {
                "kind": "nested_instance",
                "definition_name": "Bridge_Block",
                "definition_id": "def-bridge",
                "instance_reference_id": "nested-roof-instance",
                "definition_object_index": 4,
                "sibling_ordinal": 0,
                "object_id": "nested-roof-instance",
                "object_name": "RoofBridge",
                "object_type": "instance_reference",
                "layer_path": "Model::Roof::Bridge",
                "material_ref": {"kind": "block", "name": "Roof Assembly"},
                "local_bbox": [[0, 0, 0], [10, 2, 1]],
                "world_transform": dp.IDENTITY_TRANSFORM,
                "world_bbox": [[0, 0, 2], [10, 2, 3]],
            },
        ],
        "object_id": "nested-roof-instance",
        "object_name": "RoofBridge",
        "object_type": "instance_reference",
        "layer_path": "Model::Roof::Bridge",
        "material_ref": {"kind": "block", "name": "Roof Assembly"},
        "local_bbox": [[0, 0, 0], [10, 2, 1]],
        "world_transform": dp.IDENTITY_TRANSFORM,
        "world_bbox": [[0, 0, 2], [10, 2, 3]],
        "native_role_hint": "instance_reference",
    }


def _definition_record_for_root(root_id):
    record = _definition_record()
    record["source_top_level_object_id"] = root_id
    record["source_occurrence_path"][0] = dict(record["source_occurrence_path"][0])
    record["source_occurrence_path"][0]["object_id"] = root_id
    return record


def _actor_root_record_for_root(root_id, name):
    record = _actor_root_record()
    record["source_top_level_object_id"] = root_id
    record["object_id"] = root_id
    record["object_name"] = name
    record["source_occurrence_path"][0] = dict(record["source_occurrence_path"][0])
    record["source_occurrence_path"][0]["object_id"] = root_id
    record["source_occurrence_path"][0]["object_name"] = name
    return record


def _page(records, *, complete, next_cursor, session_id="inv-test"):
    return {
        "schema_version": 1,
        "inventory_session_id": session_id,
        "source_document_key": "native-doc-key-is-not-durable",
        "inventory_context_fingerprint": {
            "document_runtime_serial": 99,
            "traversal_ordering": "native_table_order_v1",
            "selected_root_count": 1,
        },
        "records": records,
        "next_cursor": next_cursor,
        "complete": complete,
        "warnings": [],
    }


class FakeNative:
    def __init__(self, *, document=None, pages=None, selection=None, output_root=None):
        self.document = document or _saved_document()
        self.pages = list(pages or [])
        self.selection = selection or {"count": 0, "objects": []}
        self.output_root = Path(output_root) if output_root else None
        self.calls = []
        self.inventory_calls = 0

    async def __call__(self, endpoint, method="GET", data=None, port=None):
        self.calls.append((endpoint, method, data, port))
        if endpoint == "/document":
            return {"success": True, "data": self.document}
        if endpoint == "/selection":
            return {"success": True, "data": self.selection}
        if endpoint == "/director/occurrence-inventory":
            if not self.pages:
                raise AssertionError("unexpected occurrence inventory call")
            self.inventory_calls += 1
            if self.output_root is not None and self.inventory_calls == 2:
                jsonl_files = list(self.output_root.rglob("provenance_records.jsonl"))
                assert len(jsonl_files) == 1
                assert len(jsonl_files[0].read_text(encoding="utf-8").splitlines()) == 1
            return {"success": True, "data": self.pages.pop(0)}
        raise AssertionError(f"unexpected endpoint {endpoint}")


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_saved_source_document_key_ignores_volatile_facts():
    first = dp.source_document_key_from_facts(_saved_document())
    second = dp.source_document_key_from_facts(
        _saved_document(size=999, modified_time="2026-06-26T13:00:00Z", runtime_serial=1234, unit_system="Feet")
    )
    assert first == second
    assert first.scope == "saved_document"


def test_unsaved_source_document_key_uses_generated_session_token_not_runtime_serial():
    first = dp.source_document_key_from_facts(
        _saved_document(path=None, is_saved=False, runtime_serial=1),
        unsaved_session_token="generated-session-token",
    )
    second = dp.source_document_key_from_facts(
        _saved_document(path=None, is_saved=False, runtime_serial=999),
        unsaved_session_token="generated-session-token",
    )
    assert first == second
    assert first.value.startswith("unsaved_")
    assert first.scope == "unsaved_session"


def test_unsaved_source_document_key_provider_is_session_scoped():
    doc = _saved_document(path=None, is_saved=False, isSaved=False, documentSessionId="unsaved-a", runtime_serial=1)
    token_a = dp.get_unsaved_session_token(doc)
    token_b = dp.get_unsaved_session_token(dict(doc, runtime_serial=999))
    assert token_a == token_b
    first = dp.source_document_key_from_facts(doc, unsaved_session_token=token_a)
    second = dp.source_document_key_from_facts(dict(doc, runtime_serial=999), unsaved_session_token=token_b)
    assert first == second


def test_unsaved_source_document_key_provider_separates_distinct_unsaved_sessions():
    first_token = dp.get_unsaved_session_token(_saved_document(path=None, is_saved=False, isSaved=False, documentSessionId="unsaved-a"))
    second_token = dp.get_unsaved_session_token(_saved_document(path=None, is_saved=False, isSaved=False, documentSessionId="unsaved-b"))
    assert first_token != second_token
    first = dp.source_document_key_from_facts(
        _saved_document(path=None, is_saved=False, isSaved=False, documentSessionId="unsaved-a"),
        unsaved_session_token=first_token,
    )
    second = dp.source_document_key_from_facts(
        _saved_document(path=None, is_saved=False, isSaved=False, documentSessionId="unsaved-b"),
        unsaved_session_token=second_token,
    )
    assert first != second


@pytest.mark.asyncio
async def test_prepare_take_rejects_missing_selection_before_native_call():
    native = FakeNative()
    with pytest.raises(dp.DirectorPrepareError) as err:
        await dp.prepare_take({"scope": "selected_occurrences"}, call_native=native)
    assert err.value.code == "missing_source_selection"
    assert native.calls == []


@pytest.mark.asyncio
async def test_prepare_take_resolves_current_selection_when_ids_absent(tmp_path):
    native = FakeNative(
        pages=[_page([_actor_root_record()], complete=True, next_cursor=None)],
        selection={"count": 1, "objects": [{"id": U1, "type": "instance_reference"}]},
    )
    await dp.prepare_take(
        {"scope": "selected_occurrences", "use_current_selection": True, "output_root": str(tmp_path)},
        call_native=native,
    )
    assert [call[0] for call in native.calls][:3] == ["/document", "/selection", "/director/occurrence-inventory"]
    assert native.calls[2][2]["source_object_ids"] == [U1]


@pytest.mark.asyncio
async def test_prepare_take_unsaved_document_key_is_session_scoped(tmp_path):
    doc = _saved_document(path=None, is_saved=False, isSaved=False, runtime_serial=100, documentSessionId="unsaved-a")
    first_native = FakeNative(document=doc, pages=[_page([_actor_root_record()], complete=True, next_cursor=None)])
    second_native = FakeNative(document=dict(doc, runtime_serial=200), pages=[_page([_actor_root_record()], complete=True, next_cursor=None)])
    first = await dp.prepare_take(
        {"scope": "selected_occurrences", "source_object_ids": [U1], "output_root": str(tmp_path / "a")},
        call_native=first_native,
    )
    second = await dp.prepare_take(
        {"scope": "selected_occurrences", "source_object_ids": [U1], "output_root": str(tmp_path / "b")},
        call_native=second_native,
    )
    assert first["source_document_key"] == second["source_document_key"]
    assert first["source_document_key_scope"] == "unsaved_session"


@pytest.mark.asyncio
async def test_prepare_take_distinct_unsaved_document_sessions_get_distinct_keys(tmp_path):
    first_native = FakeNative(
        document=_saved_document(path=None, is_saved=False, isSaved=False, documentSessionId="unsaved-a"),
        pages=[_page([_actor_root_record()], complete=True, next_cursor=None)],
    )
    second_native = FakeNative(
        document=_saved_document(path=None, is_saved=False, isSaved=False, documentSessionId="unsaved-b"),
        pages=[_page([_actor_root_record()], complete=True, next_cursor=None)],
    )
    first = await dp.prepare_take(
        {"scope": "selected_occurrences", "source_object_ids": [U1], "output_root": str(tmp_path / "a")},
        call_native=first_native,
    )
    second = await dp.prepare_take(
        {"scope": "selected_occurrences", "source_object_ids": [U1], "output_root": str(tmp_path / "b")},
        call_native=second_native,
    )
    assert first["source_document_key"] != second["source_document_key"]


@pytest.mark.asyncio
async def test_prepare_take_streams_jsonl_before_second_page(tmp_path):
    native = FakeNative(
        output_root=tmp_path,
        pages=[
            _page([_actor_root_record()], complete=False, next_cursor="1"),
            _page([_definition_record()], complete=True, next_cursor=None),
        ],
    )
    out = await dp.prepare_take(
        {"scope": "selected_occurrences", "source_object_ids": [U1], "output_root": str(tmp_path)},
        call_native=native,
    )
    records = _read_jsonl(out["paths"]["provenance_records"])
    assert [record["record_kind"] for record in records] == ["actor_root", "definition_object"]


@pytest.mark.asyncio
async def test_prepare_take_manifest_indexes_finalized_evidence(tmp_path):
    native = FakeNative(
        pages=[
            _page([_actor_root_record()], complete=False, next_cursor="1"),
            _page([_definition_record()], complete=True, next_cursor=None),
        ],
    )
    out = await dp.prepare_take(
        {"scope": "selected_occurrences", "source_object_ids": [U1], "output_root": str(tmp_path)},
        call_native=native,
    )
    manifest = _read_json(out["paths"]["take_manifest"])
    records = _read_jsonl(out["paths"]["provenance_records"])

    assert out["actor_count"] == 1
    assert out["provenance_record_count"] == 2
    assert "ok" not in out
    assert "summary" not in out

    assert "take_manifest" not in manifest["files"]
    assert manifest["files"]["provenance_records"]["sha256"] == _sha256_file(out["paths"]["provenance_records"])
    assert manifest["inventory_summary"]["provenance_jsonl_sha256"] == manifest["files"]["provenance_records"]["sha256"]
    assert manifest["inventory_summary"]["total_records"] == 2
    assert manifest["inventory_summary"]["actor_count"] == 1
    assert manifest["inventory_summary"]["page_count"] == 2
    assert manifest["inventory_summary"]["selected_root_ids"] == [U1]
    assert manifest["inventory_summary"]["role_counts"]["renderable"] == 1
    assert manifest["inventory_summary"]["animation_relevance_counts"]["candidate"] == 1
    assert manifest["inventory_summary"]["warning_counts"] == {}
    assert manifest["inventory_summary"]["referenced_only_count"] == 2
    assert manifest["inventory_summary"]["materialized_count"] == 0

    fingerprint = manifest["source_document_fingerprint"]
    assert fingerprint["schema_version"] == 1
    assert fingerprint["hash"]
    assert fingerprint["document"]["path_normalized"]
    assert fingerprint["source"]["selected_root_ids"] == [U1]
    assert fingerprint["provenance"]["record_count"] == 2

    actor = manifest["actors"][0]
    assert actor["take_id"] == out["take_id"]
    assert actor["actor_kind"] == "source_occurrence"
    assert actor["representation"] == "metadata_only"
    assert actor["source_top_level_object_id"] == U1
    assert actor["source_occurrence_key"].startswith("occ_")
    assert actor["source_occurrence_path"] == records[0]["source_occurrence_path"]
    assert actor["semantic_group"] == "bridge"
    assert actor["classification_status"] == "classified"


@pytest.mark.asyncio
async def test_prepare_take_writes_full_provenance_record_contract(tmp_path):
    native = FakeNative(
        pages=[_page([_actor_root_record(), _nested_instance_record(), _definition_record()], complete=True, next_cursor=None)]
    )
    out = await dp.prepare_take(
        {"scope": "selected_occurrences", "source_object_ids": [U1], "output_root": str(tmp_path)},
        call_native=native,
    )
    records = _read_jsonl(out["paths"]["provenance_records"])
    assert [record["record_kind"] for record in records] == ["actor_root", "nested_instance", "definition_object"]
    for record in records:
        assert record["schema_version"] == 1
        assert record["take_id"] == out["take_id"]
        assert record["actor_id"]
        assert record["provenance_id"]
        assert record["source_occurrence_key"].startswith("occ_")
        assert record["path_hash"]
        assert record["source_occurrence_path"]
        assert record["source_top_level_object_id"] == U1
        assert record["source_object_id_or_definition_object_id"]
        assert record["source_snapshot"]["object_type"] is not None
        assert record["source_snapshot"]["object_name"] is not None
        assert record["source_snapshot"]["layer_path"] is not None
        assert record["source_snapshot"]["material_ref"] is not None
        assert record["source_snapshot"]["local_bbox"] is not None
        assert record["source_snapshot"]["world_bbox"] is not None
        assert record["source_snapshot"]["world_transform"] is not None
        assert record["materialization_status"] == "referenced_only"


@pytest.mark.asyncio
async def test_prepare_take_fails_when_required_snapshot_fact_missing(tmp_path):
    bad = _definition_record()
    bad.pop("local_bbox")
    bad["source_occurrence_path"][-1].pop("local_bbox")
    native = FakeNative(pages=[_page([bad], complete=True, next_cursor=None)])
    with pytest.raises(dp.DirectorPrepareError) as err:
        await dp.prepare_take(
            {"scope": "selected_occurrences", "source_object_ids": [U1], "output_root": str(tmp_path)},
            call_native=native,
        )
    assert err.value.code == "missing_source_snapshot_fact"


@pytest.mark.asyncio
async def test_prepare_take_keeps_nested_records_associated_with_selected_root(tmp_path):
    native = FakeNative(
        pages=[
            _page(
                [
                    _actor_root_record_for_root(U1, "Bridge A"),
                    _definition_record_for_root(U1),
                    _actor_root_record_for_root(U3, "Bridge B"),
                    _definition_record_for_root(U3),
                ],
                complete=True,
                next_cursor=None,
            )
        ]
    )
    out = await dp.prepare_take(
        {"scope": "selected_occurrences", "source_object_ids": [U1, U3], "output_root": str(tmp_path)},
        call_native=native,
    )
    records = _read_jsonl(out["paths"]["provenance_records"])
    actor_by_root = {record["source_top_level_object_id"]: record["actor_id"] for record in records if record["record_kind"] == "actor_root"}
    assert set(actor_by_root) == {U1, U3}
    for record in records:
        assert record["actor_id"] == actor_by_root[record["source_top_level_object_id"]]
    assert out["actor_count"] == 2


@pytest.mark.asyncio
async def test_prepare_take_fails_when_native_record_lacks_source_root(tmp_path):
    bad = _definition_record()
    bad.pop("source_top_level_object_id")
    bad["source_occurrence_path"] = []
    native = FakeNative(pages=[_page([bad], complete=True, next_cursor=None)])
    with pytest.raises(dp.DirectorPrepareError) as err:
        await dp.prepare_take(
            {"scope": "selected_occurrences", "source_object_ids": [U1], "output_root": str(tmp_path)},
            call_native=native,
        )
    assert err.value.code == "missing_source_top_level_object_id"


@pytest.mark.asyncio
async def test_prepare_take_marks_conflicting_semantic_evidence_ambiguous(tmp_path):
    record = _actor_root_record()
    record["object_name"] = "Bridge Roof"
    record["layer_path"] = "Model::Bridge::Roof"
    native = FakeNative(pages=[_page([record], complete=True, next_cursor=None)])
    out = await dp.prepare_take(
        {"scope": "selected_occurrences", "source_object_ids": [U1], "output_root": str(tmp_path)},
        call_native=native,
    )
    root = _read_jsonl(out["paths"]["provenance_records"])[0]
    assert root["classification_status"] == "ambiguous"
    assert root["semantic_group"] is None
    assert [candidate["semantic_group"] for candidate in root["candidate_groups"]] == ["bridge", "roof"]
    assert root["conflicts"]


@pytest.mark.asyncio
async def test_prepare_take_markdown_disabled_shape(tmp_path):
    native = FakeNative(pages=[_page([_actor_root_record()], complete=True, next_cursor=None)])
    out = await dp.prepare_take(
        {
            "scope": "selected_occurrences",
            "source_object_ids": [U1],
            "output_root": str(tmp_path),
            "write_markdown_audit": False,
        },
        call_native=native,
    )
    manifest = _read_json(out["paths"]["take_manifest"])
    assert out["paths"]["audit_report_markdown"] is None
    assert manifest["files"]["audit_report_markdown"] == {"enabled": False, "path": None, "sha256": None}


@pytest.mark.asyncio
async def test_prepare_take_deletes_temp_artifacts_on_inventory_failure(tmp_path):
    class StaleNative(FakeNative):
        async def __call__(self, endpoint, method="GET", data=None, port=None):
            self.calls.append((endpoint, method, data, port))
            if endpoint == "/document":
                return {"success": True, "data": self.document}
            if endpoint == "/director/occurrence-inventory":
                return {"success": False, "data": {"code": "inventory_stale", "message": "document changed"}}
            raise AssertionError(f"unexpected endpoint {endpoint}")

    with pytest.raises(dp.DirectorPrepareError) as err:
        await dp.prepare_take(
            {"scope": "selected_occurrences", "source_object_ids": [U1], "output_root": str(tmp_path)},
            call_native=StaleNative(),
        )
    assert err.value.code == "inventory_stale"
    assert not list(tmp_path.rglob("take_manifest.json"))
    assert not list(tmp_path.rglob("provenance_records.jsonl"))
```

- [ ] **Step 2: Run the tests and confirm the initial failure**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_prepare.py -v
```

Expected:

```text
FAILED
```

The first failure should identify missing `rook.director_prepare` symbols.

## Task 2: Python Request, Storage, Selection, and Fingerprint Primitives

**Files:**

- Modify: `mcp_server/src/rook/director_prepare.py`
- Test: `mcp_server/tests/test_director_prepare.py`

- [ ] **Step 1: Create request and storage primitives**

Create `mcp_server/src/rook/director_prepare.py` with:

```python
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bridge import call_rhino


IDENTITY_TRANSFORM = [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
]


class DirectorPrepareError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SourceDocumentKey:
    value: str
    scope: str


@dataclass(frozen=True)
class PrepareTakeRequest:
    scope: str
    source_object_ids: list[str]
    use_current_selection: bool
    page_size: int
    classify_nested: bool
    write_markdown_audit: bool
    portable: bool
    output_root: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> tuple["PrepareTakeRequest", list[dict[str, str]]]:
        scope = payload.get("scope", "selected_occurrences")
        if scope != "selected_occurrences":
            raise DirectorPrepareError("unsupported_scope", "prepare_take only supports selected_occurrences")

        source_object_ids = payload.get("source_object_ids") or []
        if not isinstance(source_object_ids, list) or any(not isinstance(value, str) or not value for value in source_object_ids):
            raise DirectorPrepareError("invalid_source_object_ids", "source_object_ids must be non-empty strings")

        use_current_selection = bool(payload.get("use_current_selection", False))
        if not source_object_ids and not use_current_selection:
            raise DirectorPrepareError("missing_source_selection", "provide source_object_ids or use_current_selection")

        portable = bool(payload.get("portable", False))
        output_root = payload.get("output_root")
        if output_root is not None and not isinstance(output_root, str):
            raise DirectorPrepareError("invalid_output_root", "output_root must be a string")
        if portable and output_root:
            raise DirectorPrepareError("invalid_storage_options", "portable and output_root are mutually exclusive")

        page_size = int(payload.get("page_size", 500))
        if page_size < 1:
            raise DirectorPrepareError("invalid_page_size", "page_size must be positive")

        warnings: list[dict[str, str]] = []
        if source_object_ids and use_current_selection:
            warnings.append({"code": "explicit_ids_preferred", "message": "source_object_ids were used instead of current selection"})

        return cls(
            scope=scope,
            source_object_ids=source_object_ids,
            use_current_selection=use_current_selection,
            page_size=page_size,
            classify_nested=bool(payload.get("classify_nested", False)),
            write_markdown_audit=bool(payload.get("write_markdown_audit", True)),
            portable=portable,
            output_root=output_root,
        ), warnings


@dataclass(frozen=True)
class StorageResolution:
    storage_mode: str
    final_dir: Path
    temp_dir: Path
```

- [ ] **Step 2: Add stable source key helpers**

Append:

```python
def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _normalized_document_path(path_value: str) -> str:
    return os.path.normcase(os.path.abspath(path_value)).replace("\\", "/")


_UNSAVED_SESSION_TOKENS: dict[str, str] = {}


def unsaved_session_handle_from_document(document: dict[str, Any]) -> str:
    for key in ("documentSessionId", "unsavedDocumentSessionId", "document_session_id", "unsaved_document_session_id", "target_session_id"):
        value = document.get(key)
        if value:
            return str(value)
    raise DirectorPrepareError(
        "missing_unsaved_document_session",
        "unsaved documents require a stable session handle for source_document_key partitioning",
    )


def get_unsaved_session_token(document: dict[str, Any]) -> str:
    handle = unsaved_session_handle_from_document(document)
    if handle not in _UNSAVED_SESSION_TOKENS:
        _UNSAVED_SESSION_TOKENS[handle] = f"unsaved-session-{uuid.uuid4()}"
    return _UNSAVED_SESSION_TOKENS[handle]


def source_document_key_from_facts(
    document: dict[str, Any],
    *,
    unsaved_session_token: str | None = None,
) -> SourceDocumentKey:
    path_value = document.get("path")
    is_saved = bool(document.get("is_saved", bool(path_value)))
    if is_saved and path_value:
        digest = _sha256_text(_normalized_document_path(str(path_value)))[:16]
        return SourceDocumentKey(value=f"doc_{digest}", scope="saved_document")
    token = unsaved_session_token or f"unsaved-session-{uuid.uuid4()}"
    digest = _sha256_text(token)[:16]
    return SourceDocumentKey(value=f"unsaved_{digest}", scope="unsaved_session")
```

- [ ] **Step 3: Add native calls and current selection resolution**

Append:

```python
async def _call_native(call_native, endpoint: str, *, method: str = "GET", data: dict[str, Any] | None = None) -> dict[str, Any]:
    native = call_native or call_rhino
    response = await native(endpoint, method=method, data=data)
    if not isinstance(response, dict):
        raise DirectorPrepareError("native_response_invalid", f"{endpoint} returned a non-object response")
    if response.get("success") is False:
        error_data = response.get("data") if isinstance(response.get("data"), dict) else {}
        raise DirectorPrepareError(str(error_data.get("code") or "native_error"), str(error_data.get("message") or endpoint))
    data_value = response.get("data", response)
    if not isinstance(data_value, dict):
        raise DirectorPrepareError("native_response_invalid", f"{endpoint} returned non-object data")
    return data_value


async def _read_document_facts(call_native) -> dict[str, Any]:
    return await _call_native(call_native, "/document", method="GET", data={})


async def resolve_source_object_ids(call_native, request: PrepareTakeRequest) -> list[str]:
    if request.source_object_ids:
        return request.source_object_ids
    if not request.use_current_selection:
        raise DirectorPrepareError("missing_source_selection", "provide source_object_ids or use_current_selection")
    selection = await _call_native(call_native, "/selection", method="GET", data={})
    objects = selection.get("objects") or []
    ids = [str(item.get("id")) for item in objects if isinstance(item, dict) and item.get("id")]
    if not ids:
        raise DirectorPrepareError("missing_source_selection", "current Rhino selection is empty")
    return ids
```

- [ ] **Step 4: Add storage and source fingerprint builders**

Append:

```python
def _local_appdata_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "Rook" / "director_takes"
    return Path.home() / "AppData" / "Local" / "Rook" / "director_takes"


def resolve_storage(request: PrepareTakeRequest, document: dict[str, Any], source_key: SourceDocumentKey, take_id: str) -> StorageResolution:
    if request.portable:
        doc_path = document.get("path")
        if not doc_path:
            raise DirectorPrepareError("source_document_unsaved", "portable storage requires a saved Rhino document")
        parent = Path(str(doc_path)).parent / ".rook" / "director_takes"
        mode = "document_local"
        final_dir = parent / take_id
    elif request.output_root:
        parent = Path(request.output_root) / source_key.value
        mode = "custom_output_root"
        final_dir = parent / take_id
    else:
        parent = _local_appdata_root() / source_key.value
        mode = "global"
        final_dir = parent / take_id
    return StorageResolution(storage_mode=mode, final_dir=final_dir, temp_dir=parent / f".{take_id}.tmp")


def build_source_document_fingerprint(
    *,
    document: dict[str, Any],
    source_document_key: SourceDocumentKey,
    source_object_ids: list[str],
    inventory_context: dict[str, Any],
    evidence_summary: dict[str, Any],
) -> dict[str, Any]:
    document_part = {
        "path_normalized": _normalized_document_path(str(document.get("path") or "")) if document.get("path") else None,
        "is_saved": bool(document.get("is_saved", bool(document.get("path")))),
        "size": document.get("size"),
        "modified_time": document.get("modified_time"),
        "runtime_serial": document.get("runtime_serial"),
        "unit_system": document.get("unit_system"),
    }
    payload = {
        "schema_version": 1,
        "document": document_part,
        "storage": {
            "source_document_key": source_document_key.value,
            "source_document_key_scope": source_document_key.scope,
        },
        "source": {"selected_root_ids": source_object_ids},
        "inventory_context": inventory_context,
        "provenance": {
            "record_count": evidence_summary["total_records"],
            "actor_count": evidence_summary["actor_count"],
            "provenance_jsonl_sha256": evidence_summary["provenance_jsonl_sha256"],
            "role_counts": evidence_summary["role_counts"],
            "animation_relevance_counts": evidence_summary["animation_relevance_counts"],
        },
    }
    payload["hash"] = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return payload
```

- [ ] **Step 5: Run primitive tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_prepare.py -k "source_document_key or missing_selection or current_selection" -v
```

Expected:

```text
passed
```

## Task 3: PrepareEvidenceWriter

**Files:**

- Modify: `mcp_server/src/rook/director_prepare.py`
- Test: `mcp_server/tests/test_director_prepare.py`

- [ ] **Step 1: Add evidence writer helpers**

Append:

```python
def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_occurrence_key(record: dict[str, Any]) -> str:
    canonical = _canonical_json(record.get("source_occurrence_path") or [])
    return f"occ_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def path_hash(record: dict[str, Any]) -> str:
    canonical = _canonical_json(record.get("source_occurrence_path") or [])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def source_top_level_object_id_from_record(record: dict[str, Any]) -> str:
    explicit = record.get("source_top_level_object_id")
    if explicit:
        return str(explicit)
    path = record.get("source_occurrence_path") or []
    if path and isinstance(path[0], dict) and path[0].get("object_id"):
        return str(path[0]["object_id"])
    raise DirectorPrepareError("missing_source_top_level_object_id", "native inventory record did not identify its selected actor root")


def source_object_id_or_definition_object_id(record: dict[str, Any]) -> str:
    if record.get("object_id"):
        return str(record["object_id"])
    path = record.get("source_occurrence_path") or []
    if path and isinstance(path[-1], dict):
        for key in ("object_id", "instance_reference_id", "definition_id"):
            if path[-1].get(key):
                return str(path[-1][key])
    raise DirectorPrepareError("missing_source_object_id", "native inventory record did not identify its source object")


def _record_or_leaf_path_value(record: dict[str, Any], key: str) -> Any:
    if record.get(key) is not None:
        return record[key]
    path = record.get("source_occurrence_path") or []
    if path and isinstance(path[-1], dict) and path[-1].get(key) is not None:
        return path[-1][key]
    return None


def source_snapshot_from_record(record: dict[str, Any]) -> dict[str, Any]:
    snapshot = {
        "object_type": _record_or_leaf_path_value(record, "object_type"),
        "object_name": _record_or_leaf_path_value(record, "object_name"),
        "layer_path": _record_or_leaf_path_value(record, "layer_path"),
        "material_ref": _record_or_leaf_path_value(record, "material_ref"),
        "local_bbox": _record_or_leaf_path_value(record, "local_bbox"),
        "world_bbox": _record_or_leaf_path_value(record, "world_bbox"),
        "world_transform": _record_or_leaf_path_value(record, "world_transform"),
    }
    missing = [key for key, value in snapshot.items() if value is None]
    if missing:
        raise DirectorPrepareError(
            "missing_source_snapshot_fact",
            f"native inventory record is missing required source snapshot facts: {', '.join(missing)}",
        )
    return snapshot


def build_provenance_record(
    native_record: dict[str, Any],
    *,
    take_id: str,
    actor_id: str,
    classify_nested: bool,
) -> dict[str, Any]:
    root_id = source_top_level_object_id_from_record(native_record)
    normalized = {
        "schema_version": 1,
        "record_kind": native_record.get("record_kind"),
        "take_id": take_id,
        "actor_id": actor_id,
        "provenance_id": str(uuid.uuid4()),
        "source_occurrence_key": source_occurrence_key(native_record),
        "path_hash": path_hash(native_record),
        "source_occurrence_path": native_record.get("source_occurrence_path") or [],
        "source_top_level_object_id": root_id,
        "source_object_id_or_definition_object_id": source_object_id_or_definition_object_id(native_record),
        "source_snapshot": source_snapshot_from_record(native_record),
        "materialization_status": "referenced_only",
    }
    normalized.update(classify_operational_record(native_record))
    normalized.update(classify_semantic_record(native_record, classify_nested=classify_nested))
    return normalized


def _count_increment(counts: dict[str, int], key: object) -> None:
    value = str(key) if key is not None else "unknown"
    counts[value] = counts.get(value, 0) + 1
```

- [ ] **Step 2: Add Python-owned classification**

Append:

```python
def _tokens(*values: object) -> set[str]:
    text = " ".join(str(value or "") for value in values).lower()
    return {token for token in text.replace("-", "_").replace("::", "_").split("_") if token}


def classify_operational_record(record: dict[str, Any]) -> dict[str, str]:
    record_kind = str(record.get("record_kind") or "")
    object_type = str(record.get("object_type") or "").lower()
    role_hint = str(record.get("native_role_hint") or "").lower()
    if record_kind == "nested_instance":
        return {"object_role": "nested_instance", "animation_relevance": "structural_path_node"}
    if object_type in {"brep", "mesh", "extrusion", "surface", "curve"} or role_hint == "geometry":
        return {"object_role": "renderable", "animation_relevance": "candidate"}
    if object_type in {"annotation", "text", "leader", "dimension"}:
        return {"object_role": "annotation", "animation_relevance": "unlikely"}
    if object_type in {"point", "light"}:
        return {"object_role": "helper", "animation_relevance": "unlikely"}
    if role_hint == "construction":
        return {"object_role": "construction", "animation_relevance": "unlikely"}
    return {"object_role": "unknown", "animation_relevance": "unknown"}


def classify_semantic_record(record: dict[str, Any], *, classify_nested: bool) -> dict[str, Any]:
    token_set = _tokens(record.get("object_name"), record.get("layer_path"))
    candidates: list[dict[str, Any]] = []
    if "bridge" in token_set:
        candidates.append({"semantic_group": "bridge", "confidence": 0.9, "evidence": ["token:bridge"]})
    if "roof" in token_set:
        candidates.append({"semantic_group": "roof", "confidence": 0.9, "evidence": ["token:roof"]})
    if len(candidates) > 1:
        return {
            "semantic_group": None,
            "classification_status": "ambiguous",
            "candidate_groups": candidates,
            "evidence": [item for candidate in candidates for item in candidate["evidence"]],
            "conflicts": [{"groups": [candidate["semantic_group"] for candidate in candidates], "reason": "multiple_strong_token_matches"}],
            "classification_source": "rule_based",
        }
    if candidates and (record.get("record_kind") == "actor_root" or classify_nested or candidates[0]["confidence"] >= 0.85):
        return {
            "semantic_group": candidates[0]["semantic_group"],
            "classification_status": "classified",
            "candidate_groups": candidates,
            "evidence": candidates[0]["evidence"],
            "conflicts": [],
            "classification_source": "rule_based",
        }
    return {
        "semantic_group": None,
        "classification_status": "unclassified" if record.get("record_kind") == "actor_root" else "not_evaluated",
        "candidate_groups": [],
        "evidence": [],
        "conflicts": [],
        "classification_source": "rule_based",
    }
```

- [ ] **Step 3: Add `PrepareEvidenceWriter` as the central unit**

Append:

```python
class PrepareEvidenceWriter:
    def __init__(self, *, path: Path, take_id: str, classify_nested: bool):
        self.path = path
        self.take_id = take_id
        self.classify_nested = classify_nested
        self._hash = hashlib.sha256()
        self._handle = path.open("wb")
        self.page_count = 0
        self.total_records = 0
        self.referenced_only_count = 0
        self.materialized_count = 0
        self.actor_count = 0
        self.role_counts: dict[str, int] = {}
        self.animation_relevance_counts: dict[str, int] = {}
        self.warning_counts: dict[str, int] = {}
        self.selected_root_ids: list[str] = []
        self.actor_ids_by_root: dict[str, str] = {}
        self.actors: list[dict[str, Any]] = []
        self.closed = False

    def ingest_page(self, page: dict[str, Any], *, source_object_ids: list[str]) -> None:
        self.page_count += 1
        if not self.selected_root_ids:
            self.selected_root_ids = list(source_object_ids)
        for warning in page.get("warnings") or []:
            if isinstance(warning, dict):
                _count_increment(self.warning_counts, warning.get("code"))
        for record in page.get("records") or []:
            enriched = self._enrich_record(record, source_object_ids=source_object_ids)
            self._append_record(enriched)
            self._update_summary(enriched)

    def _enrich_record(self, record: dict[str, Any], *, source_object_ids: list[str]) -> dict[str, Any]:
        root_id = source_top_level_object_id_from_record(record)
        self.actor_ids_by_root.setdefault(root_id, str(uuid.uuid4()))
        return build_provenance_record(
            record,
            take_id=self.take_id,
            actor_id=self.actor_ids_by_root[root_id],
            classify_nested=self.classify_nested,
        )

    def _append_record(self, record: dict[str, Any]) -> None:
        line = (json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")
        self._handle.write(line)
        self._handle.flush()
        self._hash.update(line)

    def _update_summary(self, record: dict[str, Any]) -> None:
        self.total_records += 1
        if record.get("materialization_status") == "referenced_only":
            self.referenced_only_count += 1
        else:
            self.materialized_count += 1
        _count_increment(self.role_counts, record.get("object_role"))
        _count_increment(self.animation_relevance_counts, record.get("animation_relevance"))
        if record.get("record_kind") == "actor_root":
            self.actor_count += 1
            self.actors.append(
                {
                    "take_id": record["take_id"],
                    "actor_id": record["actor_id"],
                    "actor_kind": "source_occurrence",
                    "representation": "metadata_only",
                    "source_top_level_object_id": record.get("source_top_level_object_id") or record.get("object_id"),
                    "source_occurrence_key": record["source_occurrence_key"],
                    "source_occurrence_path": record.get("source_occurrence_path") or [],
                    "semantic_group": record.get("semantic_group"),
                    "classification_status": record.get("classification_status"),
                }
            )

    def close(self) -> None:
        if not self.closed:
            self._handle.close()
            self.closed = True

    def finalize_summary(self) -> dict[str, Any]:
        self.close()
        provenance_hash = self._hash.hexdigest()
        file_hash = _sha256_file(self.path)
        if provenance_hash != file_hash:
            raise DirectorPrepareError("provenance_hash_mismatch", "streaming provenance hash does not match JSONL file")
        return {
            "total_records": self.total_records,
            "actor_count": self.actor_count,
            "page_count": self.page_count,
            "selected_root_ids": self.selected_root_ids,
            "role_counts": dict(self.role_counts),
            "animation_relevance_counts": dict(self.animation_relevance_counts),
            "warning_counts": dict(self.warning_counts),
            "provenance_jsonl_sha256": provenance_hash,
            "referenced_only_count": self.referenced_only_count,
            "materialized_count": self.materialized_count,
        }
```

- [ ] **Step 4: Run source-key tests while writer tests still fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_prepare.py -k "source_document_key" -v
```

Expected:

```text
passed
```

## Task 4: Streaming Prepare Orchestration

**Files:**

- Modify: `mcp_server/src/rook/director_prepare.py`
- Test: `mcp_server/tests/test_director_prepare.py`

- [ ] **Step 1: Add temp directory and audit helpers**

Append:

```python
def _reset_temp_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=False)


def _delete_temp_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _finalize_temp_dir(temp_dir: Path, final_dir: Path) -> None:
    if final_dir.exists():
        raise DirectorPrepareError("take_already_exists", f"take directory already exists: {final_dir}")
    temp_dir.replace(final_dir)


def _path_string(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def _write_markdown_audit(path: Path, *, take_id: str, evidence_summary: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Director Prepare Take Audit",
        "",
        f"Take: {take_id}",
        f"Actors: {evidence_summary['actor_count']}",
        f"Records: {evidence_summary['total_records']}",
        f"Pages: {evidence_summary['page_count']}",
        f"Warnings: {len(warnings)}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
```

- [ ] **Step 2: Add page ingestion loop**

Append:

```python
async def _ingest_inventory_pages(
    *,
    call_native,
    request: PrepareTakeRequest,
    source_object_ids: list[str],
    writer: PrepareEvidenceWriter,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cursor: str | None = None
    inventory_session_id: str | None = None
    inventory_context: dict[str, Any] = {}
    warnings: list[dict[str, Any]] = []
    while True:
        if inventory_session_id:
            body = {"inventory_session_id": inventory_session_id, "page_size": request.page_size, "cursor": cursor}
        else:
            body = {"source_object_ids": source_object_ids, "page_size": request.page_size, "cursor": None}

        page = await _call_native(call_native, "/director/occurrence-inventory", method="POST", data=body)
        inventory_session_id = str(page.get("inventory_session_id") or inventory_session_id or "")
        inventory_context = {
            "inventory_session_id": inventory_session_id,
            "inventory_context_fingerprint": page.get("inventory_context_fingerprint", {}),
            "native_schema_version": page.get("schema_version"),
        }
        page_warnings = [warning for warning in page.get("warnings") or [] if isinstance(warning, dict)]
        warnings.extend(page_warnings)
        writer.ingest_page(page, source_object_ids=source_object_ids)

        if page.get("complete") is True:
            return inventory_context, warnings
        cursor = page.get("next_cursor")
        if not cursor:
            raise DirectorPrepareError("inventory_cursor_missing", "incomplete inventory page did not include next_cursor")
```

- [ ] **Step 3: Add `prepare_take` with streaming evidence as the center**

Append:

```python
async def prepare_take(payload: dict[str, Any], *, call_native=None) -> dict[str, Any]:
    request, input_warnings = PrepareTakeRequest.from_payload(payload)
    document = await _read_document_facts(call_native)
    unsaved_session_token = None if document.get("path") else get_unsaved_session_token(document)
    source_key = source_document_key_from_facts(document, unsaved_session_token=unsaved_session_token)
    source_object_ids = await resolve_source_object_ids(call_native, request)
    take_id = f"take_{uuid.uuid4().hex[:12]}"
    storage = resolve_storage(request, document, source_key, take_id)

    _reset_temp_dir(storage.temp_dir)
    provenance_path = storage.temp_dir / "provenance_records.jsonl"
    audit_json_path = storage.temp_dir / "audit_report.json"
    audit_md_path = storage.temp_dir / "audit_report.md"
    manifest_path = storage.temp_dir / "take_manifest.json"

    writer = PrepareEvidenceWriter(path=provenance_path, take_id=take_id, classify_nested=request.classify_nested)
    try:
        inventory_context, inventory_warnings = await _ingest_inventory_pages(
            call_native=call_native,
            request=request,
            source_object_ids=source_object_ids,
            writer=writer,
        )
        evidence_summary = writer.finalize_summary()
        all_warnings = input_warnings + inventory_warnings
        for warning in input_warnings:
            _count_increment(evidence_summary["warning_counts"], warning.get("code"))

        source_fingerprint = build_source_document_fingerprint(
            document=document,
            source_document_key=source_key,
            source_object_ids=source_object_ids,
            inventory_context=inventory_context,
            evidence_summary=evidence_summary,
        )

        audit = {
            "schema_version": 1,
            "take_id": take_id,
            "prepare_status": "complete",
            "validation_status": "valid",
            "source_document_fingerprint": source_fingerprint,
            "inventory_summary": evidence_summary,
            "warnings": all_warnings,
        }
        _write_json(audit_json_path, audit)
        if request.write_markdown_audit:
            _write_markdown_audit(audit_md_path, take_id=take_id, evidence_summary=evidence_summary, warnings=all_warnings)

        files = {
            "provenance_records": {"path": "provenance_records.jsonl", "sha256": evidence_summary["provenance_jsonl_sha256"]},
            "audit_report_json": {"path": "audit_report.json", "sha256": _sha256_file(audit_json_path)},
            "audit_report_markdown": (
                {"enabled": True, "path": "audit_report.md", "sha256": _sha256_file(audit_md_path)}
                if request.write_markdown_audit
                else {"enabled": False, "path": None, "sha256": None}
            ),
        }
        manifest = {
            "schema_version": 1,
            "take_id": take_id,
            "prepare_status": "complete",
            "created_at": _utc_now_iso(),
            "generator_version": "rookvisiondirector.prepare_take.v1",
            "storage_mode": storage.storage_mode,
            "source_document_key": source_key.value,
            "source_document_key_scope": source_key.scope,
            "source_document_fingerprint": source_fingerprint,
            "inventory_context_fingerprint": inventory_context.get("inventory_context_fingerprint", {}),
            "input": {
                "scope": request.scope,
                "source_object_ids": source_object_ids,
                "use_current_selection": request.use_current_selection,
                "page_size": request.page_size,
                "classify_nested": request.classify_nested,
                "write_markdown_audit": request.write_markdown_audit,
            },
            "files": files,
            "actors": writer.actors,
            "inventory_summary": evidence_summary,
            "validation_status": "valid",
            "warnings": all_warnings,
        }
        _write_json(manifest_path, manifest)
        _finalize_temp_dir(storage.temp_dir, storage.final_dir)
    except Exception:
        writer.close()
        _delete_temp_dir(storage.temp_dir)
        raise

    final = storage.final_dir
    return {
        "take_id": take_id,
        "prepare_status": "complete",
        "storage_mode": storage.storage_mode,
        "source_document_key": source_key.value,
        "source_document_key_scope": source_key.scope,
        "source_document_fingerprint": source_fingerprint,
        "actor_count": evidence_summary["actor_count"],
        "provenance_record_count": evidence_summary["total_records"],
        "validation_status": "valid",
        "paths": {
            "take_manifest": _path_string(final / "take_manifest.json"),
            "provenance_records": _path_string(final / "provenance_records.jsonl"),
            "audit_report_json": _path_string(final / "audit_report.json"),
            "audit_report_markdown": _path_string(final / "audit_report.md") if request.write_markdown_audit else None,
        },
        "warnings": all_warnings,
    }
```

- [ ] **Step 4: Run prepare tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_prepare.py -v
```

Expected:

```text
passed
```

- [ ] **Step 5: Run memory-shape scan**

Run:

```powershell
rg -n "raw[_]records|enriched[_]records|records[.]extend|return record[s]" mcp_server/src/rook/director_prepare.py
```

Expected:

```text
No output.
```

## Task 5: MCP Tool Registration

**Files:**

- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/tests/test_director_mcp_tools.py`

- [ ] **Step 1: Add failing MCP tests**

Add tests to `mcp_server/tests/test_director_mcp_tools.py` that assert:

```python
def test_prepare_take_tool_registered():
    names = {tool.name for tool in server.TOOLS}
    assert "rhino_director_prepare_take" in names


def test_prepare_take_tool_schema_contains_storage_and_selection_fields():
    tool = next(tool for tool in server.TOOLS if tool.name == "rhino_director_prepare_take")
    props = tool.inputSchema["properties"]
    assert {"scope", "source_object_ids", "use_current_selection", "page_size", "classify_nested", "write_markdown_audit", "portable", "output_root"} <= set(props)


def test_prepare_take_is_director_group_not_readonly():
    assert "rhino_director_prepare_take" in tool_groups.TOOL_GROUPS["director"]
    assert "rhino_director_prepare_take" not in tool_groups.TOOL_GROUPS.get("director_readonly", [])
```

- [ ] **Step 2: Register and dispatch**

Implementation requirements:

- Import `director_prepare` in `server.py`.
- Register `rhino_director_prepare_take` with the schema from the public contract.
- Dispatch by calling `await director_prepare.prepare_take(arguments, call_native=call_rhino)`.
- Add the tool to `TOOL_GROUPS["director"]`.
- Do not add it to `director_readonly`, because it writes sidecar files.

- [ ] **Step 3: Run MCP tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_mcp_tools.py -k prepare_take -v
```

Expected:

```text
passed
```

## Task 6: Native Occurrence Inventory Source Tests

**Files:**

- Modify: `mcp_server/tests/test_director_native_source.py`
- Modify: `src/RookNative/Models/Snapshots.h`
- Modify: `src/RookNative/Handlers/DocumentHandler.cpp`
- Modify: `src/RookNative/Serialization/RhinoSerializer.cpp`
- Modify: `src/RookNative/Handlers/DirectorHandler.h`
- Modify: `src/RookNative/Handlers/DirectorHandler.cpp`
- Modify: `src/RookNative/RookServer.h`
- Modify: `src/RookNative/RookServer.cpp`

- [ ] **Step 1: Add failing native source tests**

Add assertions to `mcp_server/tests/test_director_native_source.py`:

```python
def test_occurrence_inventory_route_declared_and_registered():
    assert "HandleDirectorOccurrenceInventory" in DIRECTOR_HANDLER_H
    assert "HandleDirectorOccurrenceInventory" in ROOK_SERVER_H
    assert '"/director/occurrence-inventory"' in ROOK_SERVER_CPP


def test_occurrence_inventory_route_has_paging_and_session_contract():
    assert "inventory_session_id" in DIRECTOR_HANDLER_CPP
    assert "next_cursor" in DIRECTOR_HANDLER_CPP
    assert "inventory_stale" in DIRECTOR_HANDLER_CPP
    assert "inventory_session_invalid" in DIRECTOR_HANDLER_CPP
    assert "inventory_context_fingerprint" in DIRECTOR_HANDLER_CPP
    assert "source_document_fingerprint" not in DIRECTOR_HANDLER_CPP


def test_document_snapshot_exposes_document_session_contract():
    assert "documentSessionId" in SNAPSHOTS_H
    assert "isSaved" in SNAPSHOTS_H
    assert "documentSessionId" in RHINO_SERIALIZER_CPP
    assert "isSaved" in RHINO_SERIALIZER_CPP
    assert "RuntimeSerialNumber()" in DOCUMENT_HANDLER_CPP
    assert "documentSessionId" in DOCUMENT_HANDLER_CPP
```

The last assertion enforces ownership: native returns traversal context, not durable source fidelity.

- [ ] **Step 2: Run native source tests and confirm failure**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_native_source.py -k "occurrence_inventory or document_snapshot" -v
```

Expected:

```text
FAILED
```

## Task 7: Native Paged Occurrence Inventory Route

**Files:**

- Modify: `src/RookNative/Handlers/DirectorHandler.h`
- Modify: `src/RookNative/Handlers/DirectorHandler.cpp`
- Modify: `src/RookNative/RookServer.h`
- Modify: `src/RookNative/RookServer.cpp`
- Modify: `src/RookNative/Models/Snapshots.h`
- Modify: `src/RookNative/Handlers/DocumentHandler.cpp`
- Modify: `src/RookNative/Serialization/RhinoSerializer.cpp`

- [ ] **Step 1: Extend `/document` with document session facts**

Requirements:

- Add `std::string documentSessionId` to `DocumentSnapshot`.
- Add `bool isSaved` to `DocumentSnapshot`.
- Populate `isSaved` from whether `pDoc->GetPathName()` is non-empty.
- Populate `documentSessionId` for every document.
- For saved documents, `documentSessionId` may be derived from normalized path plus runtime context, but Python must not use it for saved `source_document_key`.
- For unsaved documents, `documentSessionId` must be a generated stable handle for the lifetime of that Rhino document session.
- It is acceptable for native to keep an in-memory map from `CRhinoDoc::RuntimeSerialNumber()` to a generated UUID-like string, but the exposed `documentSessionId` must not be the raw runtime serial string.
- Serialize `documentSessionId` and `isSaved` in `Serializer::SerializeDocument`.
- Do not remove or rename existing `/document` fields.

- [ ] **Step 2: Add occurrence route declarations and registration**

Requirements:

- Declare `Rook::Handlers::HandleDirectorOccurrenceInventory`.
- Declare `CRookServer::HandleDirectorOccurrenceInventory`.
- Register `POST /director/occurrence-inventory` beside the existing Director routes.
- Forward through the same handler pattern as other Director routes.

- [ ] **Step 3: Implement route request contract**

First request:

```json
{
  "source_object_ids": ["11111111-1111-1111-1111-111111111111"],
  "page_size": 500,
  "cursor": null
}
```

Later request:

```json
{
  "inventory_session_id": "inv_7b4c",
  "page_size": 500,
  "cursor": "500"
}
```

Response:

```json
{
  "schema_version": 1,
  "inventory_session_id": "inv_7b4c",
  "source_document_key": "native-context-key",
  "inventory_context_fingerprint": {
    "document_runtime_serial": 99,
    "traversal_ordering": "native_table_order_v1"
  },
  "records": [],
  "next_cursor": null,
  "complete": true,
  "warnings": []
}
```

Native must not return `source_document_fingerprint`.

- [ ] **Step 4: Implement traversal facts**

Requirements:

- Parse source ids using existing GUID parsing patterns in `DirectorHandler.cpp`.
- Enforce native max page size.
- Strict session consistency: page size, source ids, document context, traversal ordering, and cursor must match the created session.
- Return `inventory_session_invalid` for invalid session or changed page size.
- Return `inventory_stale` for document/context drift.
- Traverse each selected top-level object as `record_kind: "actor_root"`.
- Recursively traverse reachable instance definition contents.
- Emit nested instance references as `record_kind: "nested_instance"`.
- Emit leaf definition objects as `record_kind: "definition_object"`.
- Include `source_top_level_object_id` on every emitted record. If a legacy path omits it, the first `source_occurrence_path` segment must include the selected top-level `object_id`; Python treats records without either fact as invalid evidence.
- Include source occurrence path segments, accumulated `world_transform`, `local_transform`, `local_bbox`, `world_bbox`, `material_ref`, object id where present, object name, object type, layer path, definition name/id, definition object index, sibling ordinal, segment fingerprint, and `native_role_hint`.
- For supported object facts, native must provide enough flat or leaf path-segment data for Python to build non-null `source_snapshot.object_type`, `object_name`, `layer_path`, `material_ref`, `local_bbox`, `world_bbox`, and `world_transform`.
- Return warnings for unsupported object facts instead of omitting records.
- Do not mutate Rhino objects, layers, user strings, groups, or block definitions.
- Do not write sidecar files.
- Do not create generated actor objects, proxy objects, duplicates, layers, or replay tracks.

Rhino SDK rule:

- Verify instance and definition APIs from `src/RookNative/Handlers/BlocksHandler.cpp` before coding.
- Do not add new native source files, because that would require `.vcxproj` changes that are out of scope.

- [ ] **Step 5: Run native source tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_native_source.py -k "occurrence_inventory or document_snapshot" -v
```

Expected:

```text
passed
```

Native build command, only if the local Rhino/MFC toolchain is available:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected:

```text
Build succeeded.
```

If this build is not run, report that explicitly.

## Task 8: Live Rhino Tests

**Files:**

- Modify: `mcp_server/tests/test_director_routes_live.py`

- [ ] **Step 1: Add paged occurrence inventory live smoke test**

Use existing helpers in `test_director_routes_live.py`:

- `_post_director`
- `_create_brep`
- `_block_create`
- `_block_insert`
- `fresh_document`

Assertions:

- Create nested block content.
- Insert a top-level block instance.
- Call `/director/occurrence-inventory` with `page_size: 1`.
- Assert more than one page is returned.
- Assert all pages share `inventory_session_id`.
- Assert records include `record_kind`.
- Assert at least one nested record has `world_transform`.
- Assert changing page size on a later page returns `inventory_session_invalid`.
- Assert native responses do not include `source_document_fingerprint`.

- [ ] **Step 2: Add end-to-end prepare live test**

Assertions:

- Use `rhino_director_prepare_take` or direct `director_prepare.prepare_take`.
- Use a temporary `output_root`.
- Prepare a selected top-level block instance.
- Assert Rhino object count does not increase.
- Assert JSONL exists and contains every record returned by native inventory for that selected root.
- Assert manifest `source_document_fingerprint.hash` is non-empty.
- Assert manifest `inventory_summary.provenance_jsonl_sha256` matches the actual JSONL file.
- Assert `materialized_count` is `0`.
- Assert no source object user strings are written.
- Assert preparing an unsaved document in global/custom-output mode succeeds when `/document.documentSessionId` is present.
- Assert two prepares against the same unsaved live document produce the same `source_document_key`.
- Assert two distinct unsaved live documents, if the live test harness can create/switch them, produce different `source_document_key` values.

- [ ] **Step 3: Run live tests when Rhino and Rook are available**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_routes_live.py -k "occurrence_inventory or prepare_take" -v
```

Expected:

```text
passed
```

If Rhino or Rook is not running, report that live verification was not run.

## Task 9: Final Verification and Self-Review

**Files:**

- `docs/superpowers/specs/2026-06-26-rookvisiondirector-prepare-take-design.md`
- `docs/superpowers/plans/2026-06-26-rookvisiondirector-prepare-take.md`
- Implementation and test files from Tasks 1-8

- [ ] **Step 1: Run Python tests that do not require Rhino**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_prepare.py mcp_server/tests/test_director_mcp_tools.py mcp_server/tests/test_director_native_source.py -v
```

Expected:

```text
passed
```

- [ ] **Step 2: Run memory-shape scan**

Run:

```powershell
rg -n "raw[_]records|enriched[_]records|records[.]extend|return record[s]" mcp_server/src/rook/director_prepare.py
```

Expected:

```text
No output.
```

- [ ] **Step 3: Run invariant scan**

Run:

```powershell
rg -n "source_document_fingerprint[^\\r\\n]*page|get\\(\"source_document_fingerprint\"\\)|runtime_serial[^\\r\\n]*source_document_key|files\\[\"take_manifest\"\\]|\"take_manifest\": \\{\"path\"" mcp_server/src/rook/director_prepare.py
```

Expected:

```text
No output.
```

- [ ] **Step 4: Run diff hygiene**

Run:

```powershell
git diff --check
```

Expected:

```text
No output.
```

## Commit Strategy

Commit after verified milestones:

- Python evidence writer tests and primitives.
- Streaming prepare orchestration.
- MCP registration.
- Native occurrence inventory route.
- Live tests and final cleanup.

Suggested commit messages:

```text
Add Director prepare take evidence writer
Add Director occurrence inventory route
```

## Acceptance Criteria

- `prepare_take` does not dirty Rhino documents.
- Source geometry, user strings, layers, groups, and block definitions are untouched.
- No generated actor object exists.
- Every reachable object under selected roots appears in `provenance_records.jsonl`.
- Every JSONL record has `schema_version`, `path_hash`, `source_object_id_or_definition_object_id`, `source_snapshot`, and selected-root identity.
- Nested records are associated with the selected root that produced them, even when two roots share the same nested definition object.
- JSONL is appended page by page as inventory pages arrive.
- Python builds a non-empty `source_document_fingerprint`.
- `source_document_key` excludes volatile and structural facts, and unsaved keys are session-scoped rather than take-scoped.
- Conflicting strong classification evidence produces `classification_status: "ambiguous"` with conflicts.
- Manifest actors are compact indexes derived from `actor_root` evidence records.
- Manifest `files` does not contain `take_manifest`.
- Manifest `inventory_summary.provenance_jsonl_sha256` matches the JSONL file.
- Failed prepare deletes temp artifacts by default.
- Playback cannot target this take directly, by design.
