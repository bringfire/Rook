from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import director_prepare as dp


IDENTITY = [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
]


def _saved_document(tmp_path: Path, **overrides):
    document = {
        "is_saved": True,
        "path": str(tmp_path / "Project.3dm"),
        "document_id": "doc-guid-1",
        "documentSessionId": "doc-session-1",
        "unit_system": "Millimeters",
        "runtime_serial_number": 100,
        "file_size": 10,
        "modified_time": "2026-01-01T00:00:00Z",
    }
    document.update(overrides)
    return document


def _occurrence(
    record_kind: str = "actor_root",
    *,
    root: str = "root-a",
    path=None,
    name: str = "Bridge pier",
    layer_path=None,
    source_object_id: str | None = None,
    definition_object_id: str | None = None,
    include_top_level: bool = True,
):
    record = {
        "record_kind": record_kind,
        "source_occurrence_path": path if path is not None else [root],
        "object_type": "Brep",
        "object_name": name,
        "layer_path": layer_path if layer_path is not None else ["Site", "Bridge"],
        "material_ref": {"kind": "by_layer", "name": "Concrete"},
        "local_bbox": {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0]},
        "world_bbox": {"min": [10.0, 0.0, 0.0], "max": [11.0, 1.0, 1.0]},
        "world_transform": IDENTITY,
    }
    if include_top_level:
        record["source_top_level_object_id"] = root
    if source_object_id is not None:
        record["source_object_id"] = source_object_id
    elif record_kind != "definition_object":
        record["source_object_id"] = root if record_kind == "actor_root" else f"{root}-nested"
    if definition_object_id is not None:
        record["definition_object_id"] = definition_object_id
    elif record_kind == "definition_object":
        record["definition_object_id"] = "def-shared"
    return record


def _page(records, *, next_cursor=None, complete=True, inventory_session_id="inventory-1"):
    return {
        "inventory_session_id": inventory_session_id,
        "records": records,
        "next_cursor": next_cursor,
        "complete": complete,
        "inventory_context": {"native_schema": "test", "source": "fake"},
    }


class FakeNative:
    def __init__(
        self,
        *,
        document,
        pages,
        selection=None,
        before_second_inventory=None,
    ):
        self.document = document
        self.pages = list(pages)
        self.selection = selection or []
        self.before_second_inventory = before_second_inventory
        self.calls = []
        self.inventory_calls = 0

    async def __call__(self, endpoint, method="POST", data=None, port=None):
        self.calls.append(
            {"endpoint": endpoint, "method": method, "data": data, "port": port}
        )
        if endpoint == "/document":
            return {"success": True, "data": self.document}
        if endpoint == "/selection":
            return {
                "success": True,
                "data": {"objects": [{"id": oid} for oid in self.selection]},
            }
        if endpoint == "/director/occurrence-inventory":
            self.inventory_calls += 1
            if self.inventory_calls == 2 and self.before_second_inventory is not None:
                self.before_second_inventory()
            return {"success": True, "data": self.pages[self.inventory_calls - 1]}
        raise AssertionError(f"unexpected endpoint: {endpoint}")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_jsonl(path: str | Path):
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _assert_code(excinfo, code: str):
    assert excinfo.value.code == code


APPROVED_PUBLIC_ERROR_CODES = {
    "missing_source_selection",
    "unsupported_scope",
    "invalid_source_object_ids",
    "invalid_storage_options",
    "source_document_unsaved",
    "invalid_page_size",
    "inventory_stale",
    "inventory_session_invalid",
    "inventory_cursor_missing",
    "native_response_invalid",
    "invalid_output_root",
    "missing_unsaved_document_session",
    "missing_source_top_level_object_id",
    "missing_source_object_id",
    "missing_source_snapshot_fact",
    "provenance_hash_mismatch",
    "take_already_exists",
}


def test_director_prepare_error_codes_are_approved_public_contract():
    tree = ast.parse(Path(dp.__file__).read_text(encoding="utf-8"))
    codes = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Name) or func.id != "DirectorPrepareError":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        if isinstance(node.args[0].value, str):
            codes.add(node.args[0].value)
    assert codes <= APPROVED_PUBLIC_ERROR_CODES


def test_saved_source_document_key_ignores_volatile_facts(tmp_path):
    first = _saved_document(
        tmp_path,
        file_size=10,
        modified_time="2026-01-01T00:00:00Z",
        runtime_serial_number=100,
        unit_system="Millimeters",
    )
    second = _saved_document(
        tmp_path,
        file_size=999999,
        modified_time="2026-06-26T12:00:00Z",
        runtime_serial_number=999,
        unit_system="Feet",
    )

    key1 = dp.source_document_key_from_facts(first)
    key2 = dp.source_document_key_from_facts(second)

    assert key1 == key2
    assert key1.scope == "saved_document"
    assert key1.value


def test_unsaved_keys_use_stable_generated_session_tokens():
    doc_a = {"is_saved": False, "documentSessionId": "unsaved-session-a"}
    doc_a_again = {"is_saved": False, "documentSessionId": "unsaved-session-a"}
    doc_b = {"is_saved": False, "documentSessionId": "unsaved-session-b"}

    token_a = dp.get_unsaved_session_token(doc_a)
    assert token_a == dp.get_unsaved_session_token(doc_a_again)
    assert token_a != dp.get_unsaved_session_token(doc_b)

    key_a = dp.source_document_key_from_facts(doc_a, token_a)
    assert key_a == dp.source_document_key_from_facts(doc_a_again, token_a)
    assert key_a != dp.source_document_key_from_facts(
        doc_b, dp.get_unsaved_session_token(doc_b)
    )
    assert key_a.scope == "unsaved_session"

    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        dp.get_unsaved_session_token({"is_saved": False})
    _assert_code(excinfo, "missing_unsaved_document_session")


def test_request_validation_rejects_scope_page_size_and_storage_conflict(tmp_path):
    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        dp.PrepareTakeRequest.from_payload(
            {"scope": "whole_document", "source_object_ids": ["a"]}
        )
    _assert_code(excinfo, "unsupported_scope")

    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        dp.PrepareTakeRequest.from_payload(
            {"source_object_ids": ["a"], "page_size": 0}
        )
    _assert_code(excinfo, "invalid_page_size")

    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        dp.PrepareTakeRequest.from_payload(
            {"source_object_ids": ["a"], "page_size": 1001}
        )
    _assert_code(excinfo, "invalid_page_size")

    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        dp.PrepareTakeRequest.from_payload(
            {
                "source_object_ids": ["a"],
                "output_root": str(tmp_path),
                "portable": True,
            }
        )
    _assert_code(excinfo, "invalid_storage_options")

    request = dp.PrepareTakeRequest.from_payload(
        {"source_object_ids": ["a"], "use_current_selection": True}
    )
    assert request.source_object_ids == ["a"]
    assert request.use_current_selection is False
    assert any(w["code"] == "explicit_source_ids_override_selection" for w in request.warnings)


@pytest.mark.parametrize(
    "bad_take_id",
    [".", "..", "CON", "con", "CON.txt", "PRN", "AUX", "NUL", "COM1", "com9", "LPT1", "lpt9", "take."],
)
def test_request_validation_rejects_unsafe_take_id_segments(bad_take_id):
    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        dp.PrepareTakeRequest.from_payload(
            {"take_id": bad_take_id, "source_object_ids": ["root-a"]}
        )
    _assert_code(excinfo, "invalid_source_object_ids")


def test_resolve_storage_modes_and_rejections(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    document_path = tmp_path / "models" / "Project.3dm"
    document = _saved_document(tmp_path, path=str(document_path))
    key = dp.source_document_key_from_facts(document)

    default_storage = dp.resolve_storage(
        document=document,
        source_document_key=key,
        take_id="take-default",
    )
    assert default_storage.storage_mode == "global"
    assert default_storage.final_dir == (
        tmp_path / "local" / "Rook" / "director_takes" / key.value / "take-default"
    ).resolve()

    custom_storage = dp.resolve_storage(
        document=document,
        source_document_key=key,
        take_id="take-custom",
        output_root=str(tmp_path / "custom"),
    )
    assert custom_storage.storage_mode == "custom_output_root"
    assert custom_storage.final_dir == (
        tmp_path / "custom" / key.value / "take-custom"
    ).resolve()

    portable_storage = dp.resolve_storage(
        document=document,
        source_document_key=key,
        take_id="take-portable",
        portable=True,
    )
    assert portable_storage.storage_mode == "document_local"
    assert portable_storage.final_dir == (
        document_path.parent / ".rook" / "director_takes" / "take-portable"
    ).resolve()

    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        dp.resolve_storage(
            document={"is_saved": False, "documentSessionId": "unsaved"},
            source_document_key=dp.source_document_key_from_facts(
                {"is_saved": False, "documentSessionId": "unsaved"}
            ),
            take_id="take-portable-unsaved",
            portable=True,
        )
    _assert_code(excinfo, "source_document_unsaved")

    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        dp.resolve_storage(
            document=document,
            source_document_key=key,
            take_id="take-invalid",
            output_root="",
        )
    _assert_code(excinfo, "invalid_output_root")


def test_evidence_normalization_helpers_fail_closed():
    record = _occurrence(
        "definition_object",
        root="root-a",
        path=["root-a", "instance-a", "def-a"],
        definition_object_id="def-a",
    )

    assert dp.source_occurrence_key(record)
    assert dp.path_hash(record)
    assert dp.source_top_level_object_id_from_record(record) == "root-a"
    assert dp.source_object_id_or_definition_object_id(record) == "def-a"
    snapshot = dp.source_snapshot_from_record(record)
    assert snapshot["object_type"] == "Brep"
    assert snapshot["world_transform"] == IDENTITY

    missing_object_id = dict(record)
    missing_object_id.pop("definition_object_id")
    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        dp.source_object_id_or_definition_object_id(missing_object_id)
    _assert_code(excinfo, "missing_source_object_id")


def test_evidence_writer_hash_mismatch_uses_public_provenance_code(tmp_path, monkeypatch):
    with dp.PrepareEvidenceWriter(
        take_id="take-hash-mismatch",
        run_dir=tmp_path,
        classify_nested=False,
    ) as writer:
        writer.append_page([_occurrence(root="root-a", source_object_id="root-a")])

    monkeypatch.setattr(dp, "_sha256_file", lambda path: "not-the-streaming-hash")
    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        writer.finalize()
    _assert_code(excinfo, "provenance_hash_mismatch")


@pytest.mark.asyncio
async def test_missing_selection_raises_before_native_calls():
    native = FakeNative(document={}, pages=[])

    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        await dp.prepare_take({"take_id": "take-missing-selection"}, call_native=native)

    _assert_code(excinfo, "missing_source_selection")
    assert native.calls == []


@pytest.mark.asyncio
async def test_use_current_selection_calls_selection_and_inventory_with_selected_ids(tmp_path):
    native = FakeNative(
        document=_saved_document(tmp_path),
        selection=["sel-a", "sel-b"],
        pages=[
            _page(
                [
                    _occurrence(root="sel-a", source_object_id="sel-a"),
                    _occurrence(root="sel-b", source_object_id="sel-b"),
                ]
            )
        ],
    )

    result = await dp.prepare_take(
        {
            "take_id": "take-selection",
            "use_current_selection": True,
            "output_root": str(tmp_path / "out"),
        },
        call_native=native,
    )

    endpoints = [call["endpoint"] for call in native.calls]
    assert endpoints[:3] == ["/document", "/selection", "/director/occurrence-inventory"]
    document_call = native.calls[0]
    assert document_call["endpoint"] == "/document"
    assert document_call["method"] == "GET"
    assert document_call["data"] is None
    inventory_payload = next(
        call["data"]
        for call in native.calls
        if call["endpoint"] == "/director/occurrence-inventory"
    )
    assert inventory_payload["source_object_ids"] == ["sel-a", "sel-b"]
    assert result["actor_count"] == 2


@pytest.mark.asyncio
async def test_jsonl_is_written_incrementally_before_second_page_returns(tmp_path):
    output_root = tmp_path / "out"

    def assert_first_page_flushed():
        matches = list(output_root.rglob("provenance_records.jsonl"))
        assert len(matches) == 1
        assert len(matches[0].read_text(encoding="utf-8").splitlines()) == 1

    native = FakeNative(
        document=_saved_document(tmp_path),
        before_second_inventory=assert_first_page_flushed,
        pages=[
            _page(
                [_occurrence(root="root-a", source_object_id="root-a")],
                next_cursor="cursor-2",
                complete=False,
            ),
            _page(
                [
                    _occurrence(
                        "nested_instance",
                        root="root-a",
                        path=["root-a", "nested-a"],
                    )
                ]
            ),
        ],
    )

    result = await dp.prepare_take(
        {
            "take_id": "take-incremental",
            "source_object_ids": ["root-a"],
            "output_root": str(output_root),
            "page_size": 1,
        },
        call_native=native,
    )

    assert result["provenance_record_count"] == 2
    inventory_payloads = [
        call["data"]
        for call in native.calls
        if call["endpoint"] == "/director/occurrence-inventory"
    ]
    assert inventory_payloads[0] == {
        "source_object_ids": ["root-a"],
        "page_size": 1,
        "cursor": None,
    }
    assert inventory_payloads[1] == {
        "inventory_session_id": "inventory-1",
        "page_size": 1,
        "cursor": "cursor-2",
    }


@pytest.mark.asyncio
async def test_manifest_indexes_finalized_evidence_and_provenance_contract(tmp_path):
    native = FakeNative(
        document=_saved_document(tmp_path),
        pages=[
            _page(
                [
                    _occurrence(
                        "actor_root",
                        root="root-a",
                        path=["root-a"],
                        source_object_id="root-a",
                        name="Bridge pier",
                    ),
                    _occurrence(
                        "nested_instance",
                        root="root-a",
                        path=["root-a", "nested-a"],
                        source_object_id="nested-a",
                        name="Nested bolt",
                    ),
                    _occurrence(
                        "definition_object",
                        root="root-a",
                        path=["root-a", "nested-a", "def-a"],
                        definition_object_id="def-a",
                        name="Definition beam",
                    ),
                ]
            )
        ],
    )

    result = await dp.prepare_take(
        {
            "take_id": "take-manifest",
            "source_object_ids": ["root-a"],
            "output_root": str(tmp_path / "out"),
        },
        call_native=native,
    )

    assert set(result) == {
        "take_id",
        "prepare_status",
        "storage_mode",
        "source_document_key",
        "source_document_key_scope",
        "source_document_fingerprint",
        "actor_count",
        "provenance_record_count",
        "validation_status",
        "paths",
        "warnings",
    }
    assert "ok" not in result
    assert "summary" not in result
    assert result["prepare_status"] == "complete"
    assert result["validation_status"] == "valid"
    assert result["storage_mode"] == "custom_output_root"

    manifest = _read_json(result["paths"]["take_manifest"])
    lines = _read_jsonl(result["paths"]["provenance_records"])
    audit = _read_json(result["paths"]["audit_report_json"])

    for field in (
        "schema_version",
        "take_id",
        "prepare_status",
        "created_at",
        "generator_version",
        "storage_mode",
        "source_document_key",
        "source_document_key_scope",
        "source_document_fingerprint",
        "input",
        "files",
        "actors",
        "inventory_summary",
        "validation_status",
    ):
        assert field in manifest
    assert manifest["prepare_status"] == "complete"
    assert manifest["validation_status"] == "valid"
    assert audit["prepare_status"] == "complete"
    assert audit["validation_status"] == "valid"

    inventory_summary = manifest["inventory_summary"]
    assert inventory_summary["total_records"] == 3
    assert inventory_summary["provenance_record_count"] == 3
    assert inventory_summary["actor_count"] == 1
    assert inventory_summary["page_count"] == 1
    assert inventory_summary["selected_root_ids"] == ["root-a"]
    assert inventory_summary["selected_roots"] == ["root-a"]
    assert inventory_summary["role_counts"] == {
        "actor_root": 1,
        "nested_instance": 1,
        "definition_object": 1,
    }
    assert inventory_summary["animation_relevance_counts"] == {
        "direct": 1,
        "inherited": 1,
        "definition_reference": 1,
    }
    assert inventory_summary["warning_counts"] == {}
    assert inventory_summary["materialization_status_counts"] == {"referenced_only": 3}
    assert inventory_summary["referenced_record_count"] == 3
    assert inventory_summary["referenced_only_count"] == 3
    assert inventory_summary["materialized_record_count"] == 0
    assert inventory_summary["materialized_count"] == 0
    assert (
        manifest["files"]["provenance_records"]["sha256"]
        == _sha256_file(Path(result["paths"]["provenance_records"]))
    )
    assert (
        inventory_summary["provenance_jsonl_sha256"]
        == manifest["files"]["provenance_records"]["sha256"]
    )
    assert manifest["source_document_fingerprint"]["hash"]
    assert manifest["source_document_fingerprint"] == result["source_document_fingerprint"]
    assert "take_manifest" not in manifest["files"]

    actor = manifest["actors"][0]
    assert actor == {
        "take_id": "take-manifest",
        "actor_id": lines[0]["actor_id"],
        "actor_kind": "source_occurrence",
        "representation": "metadata_only",
        "source_top_level_object_id": "root-a",
        "source_occurrence_key": lines[0]["source_occurrence_key"],
        "source_occurrence_path": ["root-a"],
        "semantic_group": "bridge",
        "classification_status": "classified",
    }

    by_kind = {line["record_kind"]: line for line in lines}
    assert set(by_kind) == {"actor_root", "nested_instance", "definition_object"}
    for record in lines:
        for field in (
            "schema_version",
            "record_kind",
            "take_id",
            "actor_id",
            "provenance_id",
            "source_occurrence_key",
            "path_hash",
            "source_occurrence_path",
            "source_top_level_object_id",
            "source_object_id_or_definition_object_id",
            "source_snapshot",
            "materialization_status",
            "object_role",
            "animation_relevance",
            "semantic_group",
            "classification_status",
            "candidate_groups",
            "classification_evidence",
            "classification_conflicts",
        ):
            assert field in record
        assert record["take_id"] == "take-manifest"
        assert record["materialization_status"] == "referenced_only"
        snapshot = record["source_snapshot"]
        for fact in (
            "object_type",
            "object_name",
            "layer_path",
            "material_ref",
            "local_bbox",
            "world_bbox",
            "world_transform",
        ):
            assert snapshot[fact] is not None

    assert by_kind["actor_root"]["object_role"] == "actor_root"
    assert by_kind["nested_instance"]["object_role"] == "nested_instance"
    assert by_kind["definition_object"]["object_role"] == "definition_object"


@pytest.mark.asyncio
async def test_native_inventory_context_fingerprint_is_preserved_in_manifest_and_source_fingerprint(tmp_path):
    page = _page([_occurrence(root="root-a", source_object_id="root-a")])
    page.pop("inventory_context")
    page["inventory_context_fingerprint"] = {
        "document_runtime_serial": 42,
        "traversal_ordering": "native_instance_definition_depth_first_v1",
        "traversal_ordering_version": 1,
    }
    native = FakeNative(document=_saved_document(tmp_path), pages=[page])

    result = await dp.prepare_take(
        {
            "take_id": "take-native-context",
            "source_object_ids": ["root-a"],
            "output_root": str(tmp_path / "out"),
        },
        call_native=native,
    )

    manifest = _read_json(result["paths"]["take_manifest"])
    context_fingerprint = manifest["inventory_context"]["inventory_context_fingerprint"]
    assert context_fingerprint["document_runtime_serial"] == 42
    assert (
        context_fingerprint["traversal_ordering"]
        == "native_instance_definition_depth_first_v1"
    )
    assert (
        manifest["source_document_fingerprint"]["inventory_context"][
            "inventory_context_fingerprint"
        ]
        == context_fingerprint
    )


@pytest.mark.asyncio
async def test_prepare_take_fails_if_selected_root_has_no_actor_root_record(tmp_path):
    output_root = tmp_path / "out"
    native = FakeNative(
        document=_saved_document(tmp_path),
        pages=[_page([], complete=True)],
    )

    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        await dp.prepare_take(
            {
                "take_id": "take-missing-root",
                "source_object_ids": ["root-a"],
                "output_root": str(output_root),
            },
            call_native=native,
        )

    _assert_code(excinfo, "native_response_invalid")
    assert not (output_root / "take-missing-root").exists()


@pytest.mark.asyncio
async def test_explicit_uuid_source_ids_are_canonicalized_for_native_root_matching(tmp_path):
    canonical_root = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    explicit_root = "{AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA}"
    native = FakeNative(
        document=_saved_document(tmp_path),
        pages=[
            _page(
                [
                    _occurrence(
                        root=canonical_root,
                        path=[canonical_root],
                        source_object_id=canonical_root,
                    )
                ]
            )
        ],
    )

    result = await dp.prepare_take(
        {
            "take_id": "take-canonical-uuid",
            "source_object_ids": [explicit_root],
            "output_root": str(tmp_path / "out"),
        },
        call_native=native,
    )

    manifest = _read_json(result["paths"]["take_manifest"])
    assert manifest["input"]["source_object_ids"] == [canonical_root]
    assert manifest["inventory_summary"]["selected_root_ids"] == [canonical_root]
    assert native.calls[1]["data"]["source_object_ids"] == [canonical_root]


@pytest.mark.asyncio
async def test_repeated_page_warnings_are_deduplicated_in_manifest_and_response(tmp_path):
    warning = "missing_bbox: bbox_unavailable_zero_fallback for object root-a"
    first_page = _page(
        [_occurrence(root="root-a", source_object_id="root-a")],
        next_cursor="1",
        complete=False,
    )
    second_page = _page(
        [
            _occurrence(
                "definition_object",
                root="root-a",
                path=["root-a", "leaf-a"],
                definition_object_id="leaf-a",
            )
        ],
        complete=True,
    )
    first_page["warnings"] = [warning]
    second_page["warnings"] = [warning]
    native = FakeNative(
        document=_saved_document(tmp_path),
        pages=[first_page, second_page],
    )

    result = await dp.prepare_take(
        {
            "take_id": "take-warning-dedupe",
            "source_object_ids": ["root-a"],
            "output_root": str(tmp_path / "out"),
        },
        call_native=native,
    )

    manifest = _read_json(result["paths"]["take_manifest"])
    assert result["warnings"] == [{"code": "missing_bbox", "message": warning}]
    assert manifest["warnings"] == result["warnings"]
    assert manifest["inventory_summary"]["warning_counts"] == {"missing_bbox": 1}


@pytest.mark.asyncio
async def test_missing_required_snapshot_fact_fails_closed_and_cleans_artifacts(tmp_path):
    bad = _occurrence(root="root-a", source_object_id="root-a")
    bad.pop("world_bbox")
    output_root = tmp_path / "out"
    native = FakeNative(
        document=_saved_document(tmp_path),
        pages=[_page([bad])],
    )

    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        await dp.prepare_take(
            {
                "take_id": "take-bad-snapshot",
                "source_object_ids": ["root-a"],
                "output_root": str(output_root),
            },
            call_native=native,
        )

    _assert_code(excinfo, "missing_source_snapshot_fact")
    assert not list(output_root.rglob("provenance_records.jsonl"))
    assert not list(output_root.rglob("take_manifest.json"))


@pytest.mark.asyncio
async def test_bad_inventory_page_shape_uses_native_response_invalid(tmp_path):
    native = FakeNative(
        document=_saved_document(tmp_path),
        pages=[
            {
                "inventory_session_id": "inventory-1",
                "records": {"not": "an array"},
                "complete": True,
            }
        ],
    )

    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        await dp.prepare_take(
            {
                "take_id": "take-bad-page",
                "source_object_ids": ["root-a"],
                "output_root": str(tmp_path / "out"),
            },
            call_native=native,
        )

    _assert_code(excinfo, "native_response_invalid")


@pytest.mark.asyncio
async def test_non_dict_inventory_record_uses_native_response_invalid_and_cleans_artifacts(tmp_path):
    output_root = tmp_path / "out"
    native = FakeNative(
        document=_saved_document(tmp_path),
        pages=[_page([None])],
    )

    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        await dp.prepare_take(
            {
                "take_id": "take-non-dict-record",
                "source_object_ids": ["root-a"],
                "output_root": str(output_root),
            },
            call_native=native,
        )

    _assert_code(excinfo, "native_response_invalid")
    assert not list(output_root.rglob("provenance_records.jsonl"))
    assert not list(output_root.rglob("take_manifest.json"))


@pytest.mark.asyncio
async def test_inventory_page_items_alias_is_rejected(tmp_path):
    native = FakeNative(
        document=_saved_document(tmp_path),
        pages=[
            {
                "inventory_session_id": "inventory-1",
                "items": [_occurrence(root="root-a", source_object_id="root-a")],
                "complete": True,
            }
        ],
    )

    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        await dp.prepare_take(
            {
                "take_id": "take-items-alias",
                "source_object_ids": ["root-a"],
                "output_root": str(tmp_path / "out"),
            },
            call_native=native,
        )

    _assert_code(excinfo, "native_response_invalid")


@pytest.mark.asyncio
async def test_non_finite_inventory_value_is_rejected_and_cleans_artifacts(tmp_path):
    output_root = tmp_path / "out"
    bad = _occurrence(root="root-a", source_object_id="root-a")
    bad["world_bbox"]["max"][0] = math.inf
    native = FakeNative(
        document=_saved_document(tmp_path),
        pages=[_page([bad])],
    )

    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        await dp.prepare_take(
            {
                "take_id": "take-non-finite",
                "source_object_ids": ["root-a"],
                "output_root": str(output_root),
            },
            call_native=native,
        )

    _assert_code(excinfo, "native_response_invalid")
    assert not list(output_root.rglob("provenance_records.jsonl"))
    assert not list(output_root.rglob("take_manifest.json"))


@pytest.mark.asyncio
async def test_off_selection_source_root_is_rejected_and_cleans_artifacts(tmp_path):
    output_root = tmp_path / "out"
    native = FakeNative(
        document=_saved_document(tmp_path),
        pages=[_page([_occurrence(root="root-b", source_object_id="root-b")])],
    )

    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        await dp.prepare_take(
            {
                "take_id": "take-off-selection-root",
                "source_object_ids": ["root-a"],
                "output_root": str(output_root),
            },
            call_native=native,
        )

    _assert_code(excinfo, "native_response_invalid")
    assert not list(output_root.rglob("provenance_records.jsonl"))
    assert not list(output_root.rglob("take_manifest.json"))


@pytest.mark.asyncio
async def test_multi_root_shared_nested_definition_keeps_correct_selected_root(tmp_path):
    native = FakeNative(
        document=_saved_document(tmp_path),
        pages=[
            _page(
                [
                    _occurrence("actor_root", root="root-a", source_object_id="root-a"),
                    _occurrence("actor_root", root="root-b", source_object_id="root-b"),
                    _occurrence(
                        "definition_object",
                        root="root-a",
                        path=["root-a", "inst-a", "def-shared"],
                        definition_object_id="def-shared",
                    ),
                    _occurrence(
                        "definition_object",
                        root="root-b",
                        path=["root-b", "inst-b", "def-shared"],
                        definition_object_id="def-shared",
                    ),
                ]
            )
        ],
    )

    result = await dp.prepare_take(
        {
            "take_id": "take-multi-root",
            "source_object_ids": ["root-a", "root-b"],
            "output_root": str(tmp_path / "out"),
        },
        call_native=native,
    )

    lines = _read_jsonl(result["paths"]["provenance_records"])
    actor_by_root = {
        record["source_top_level_object_id"]: record["actor_id"]
        for record in lines
        if record["record_kind"] == "actor_root"
    }
    definition_records = [
        record for record in lines if record["record_kind"] == "definition_object"
    ]
    assert {
        record["source_top_level_object_id"] for record in definition_records
    } == {"root-a", "root-b"}
    for record in definition_records:
        assert record["actor_id"] == actor_by_root[record["source_top_level_object_id"]]


@pytest.mark.asyncio
async def test_missing_source_top_level_object_id_or_top_path_root_fails(tmp_path):
    bad = _occurrence(
        root="root-a",
        path=[],
        include_top_level=False,
        source_object_id="root-a",
    )
    native = FakeNative(document=_saved_document(tmp_path), pages=[_page([bad])])

    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        await dp.prepare_take(
            {
                "take_id": "take-missing-root",
                "source_object_ids": ["root-a"],
                "output_root": str(tmp_path / "out"),
            },
            call_native=native,
        )

    _assert_code(excinfo, "missing_source_top_level_object_id")


@pytest.mark.asyncio
async def test_ambiguous_bridge_roof_classification_reports_candidates_and_conflicts(tmp_path):
    native = FakeNative(
        document=_saved_document(tmp_path),
        pages=[
            _page(
                [
                    _occurrence(
                        root="root-a",
                        source_object_id="root-a",
                        name="Bridge roof assembly",
                        layer_path=["Bridge", "Roof"],
                    )
                ]
            )
        ],
    )

    result = await dp.prepare_take(
        {
            "take_id": "take-ambiguous",
            "source_object_ids": ["root-a"],
            "output_root": str(tmp_path / "out"),
        },
        call_native=native,
    )

    record = _read_jsonl(result["paths"]["provenance_records"])[0]
    assert record["classification_status"] == "ambiguous"
    assert record["semantic_group"] is None
    assert {candidate["semantic_group"] for candidate in record["candidate_groups"]} >= {
        "bridge",
        "roof",
    }
    assert record["classification_conflicts"]


@pytest.mark.asyncio
async def test_incomplete_inventory_page_without_cursor_fails_and_cleans_artifacts(tmp_path):
    output_root = tmp_path / "out"
    native = FakeNative(
        document=_saved_document(tmp_path),
        pages=[
            _page(
                [_occurrence(root="root-a", source_object_id="root-a")],
                next_cursor=None,
                complete=False,
            )
        ],
    )

    with pytest.raises(dp.DirectorPrepareError) as excinfo:
        await dp.prepare_take(
            {
                "take_id": "take-missing-cursor",
                "source_object_ids": ["root-a"],
                "output_root": str(output_root),
            },
            call_native=native,
        )

    _assert_code(excinfo, "inventory_cursor_missing")
    assert not list(output_root.rglob("take_manifest.json"))
    assert not list(output_root.rglob("provenance_records.jsonl"))


@pytest.mark.asyncio
async def test_markdown_audit_default_on_and_disabled_shape(tmp_path):
    default_native = FakeNative(
        document=_saved_document(tmp_path),
        pages=[_page([_occurrence(root="root-a", source_object_id="root-a")])],
    )
    default_result = await dp.prepare_take(
        {
            "take_id": "take-md-on",
            "source_object_ids": ["root-a"],
            "output_root": str(tmp_path / "out-on"),
        },
        call_native=default_native,
    )
    assert default_result["paths"]["audit_report_markdown"] is not None
    assert Path(default_result["paths"]["audit_report_markdown"]).exists()
    default_manifest = _read_json(default_result["paths"]["take_manifest"])
    assert default_manifest["files"]["audit_report_markdown"]["enabled"] is True

    disabled_native = FakeNative(
        document=_saved_document(tmp_path),
        pages=[_page([_occurrence(root="root-a", source_object_id="root-a")])],
    )
    disabled_result = await dp.prepare_take(
        {
            "take_id": "take-md-off",
            "source_object_ids": ["root-a"],
            "output_root": str(tmp_path / "out-off"),
            "write_markdown_audit": False,
        },
        call_native=disabled_native,
    )
    assert disabled_result["paths"]["audit_report_markdown"] is None
    disabled_manifest = _read_json(disabled_result["paths"]["take_manifest"])
    assert disabled_manifest["files"]["audit_report_markdown"]["enabled"] is False
    assert disabled_manifest["files"]["audit_report_markdown"]["path"] is None
    assert disabled_manifest["files"]["audit_report_markdown"]["sha256"] is None
