"""Server-side deprecation regressions for GH component lookup and warnings."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from rook import server
from rook.learning.knowledge_note import KnowledgeNote
from rook.learning.unified_store import UnifiedStore


class _DummyPhaseTracker:
    def record_call(self, _name: str) -> None:
        pass


def _make_store_with_area_notes() -> UnifiedStore:
    tmpdir = tempfile.TemporaryDirectory()
    store = UnifiedStore(
        notes_dir=Path(tmpdir.name) / "notes",
        index_path=Path(tmpdir.name) / "index.json",
        auto_save=False,
        enable_evolution=False,
    )
    store._test_tmpdir = tmpdir  # Keep tempdir alive for the test duration.

    deprecated = KnowledgeNote(
        note_id="comp_deprecated_area",
        note_type="component",
        name="Area",
        brief="Deprecated area",
        created="2026-02-01T12:00:00Z",
        trigger_intents=["area"],
        type_data={"guid": "2e205f24-9279-47b2-b414-d06dcd0b21a7"},
        deprecated=True,
        deprecated_reason="obsolete",
        deprecated_by="86b28a7e-94d9-4791-8306-e13e10d5f8d5",
        deprecated_replacement_name="Area",
    )
    active = KnowledgeNote(
        note_id="comp_active_area",
        note_type="component",
        name="Area",
        brief="Active area",
        created="2026-02-01T12:00:00Z",
        trigger_intents=["area"],
        type_data={
            "guid": "86b28a7e-94d9-4791-8306-e13e10d5f8d5",
            "usage_count": 10,
        },
    )
    store.add(deprecated, skip_evolution=True)
    store.add(active, skip_evolution=True)
    return store


def _make_store_with_multiplication_alias() -> UnifiedStore:
    tmpdir = tempfile.TemporaryDirectory()
    store = UnifiedStore(
        notes_dir=Path(tmpdir.name) / "notes",
        index_path=Path(tmpdir.name) / "index.json",
        auto_save=False,
        enable_evolution=False,
    )
    store._test_tmpdir = tmpdir

    deprecated = KnowledgeNote(
        note_id="comp_deprecated_mul",
        note_type="component",
        name="Multiplication",
        brief="Deprecated multiplication",
        created="2026-02-01T12:00:00Z",
        type_data={
            "guid": "b8963bb1-aa57-476e-a20e-ed6cf635a49c",
        },
        deprecated=True,
        deprecated_reason="obsolete",
        deprecated_by="ce46b74e-00c9-43c4-805a-193b69ea4a11",
        deprecated_replacement_name="Multiplication",
    )
    active = KnowledgeNote(
        note_id="comp_active_mul",
        note_type="component",
        name="Multiplication",
        brief="Active multiplication",
        created="2026-02-01T12:00:00Z",
        type_data={
            "guid": "ce46b74e-00c9-43c4-805a-193b69ea4a11",
            "usage_count": 10,
        },
    )
    store.add(deprecated, skip_evolution=True)
    store.add(active, skip_evolution=True)
    store._legacy_guid_info = {
        "b8963bb1-aa57-476e-a20e-ed6cf635a49c": {
            "name": "Multiplication",
            "nickName": "A×B",
        },
        "ce46b74e-00c9-43c4-805a-193b69ea4a11": {
            "name": "Multiplication",
            "nickName": "A×B",
        },
    }
    return store


@pytest.fixture
def patched_server(monkeypatch):
    monkeypatch.setattr(server, "should_inject", lambda _name, _result: False)
    monkeypatch.setattr(server, "_record_observation", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "get_phase_tracker", lambda: _DummyPhaseTracker())


@pytest.mark.asyncio
async def test_gh_edit_attaches_per_item_deprecation_warnings(monkeypatch, patched_server):
    store = _make_store_with_area_notes()
    record_mock = AsyncMock()

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/edit"
        assert method == "POST"
        assert port is None
        assert payload["create"][0]["guid"] == "2e205f24-9279-47b2-b414-d06dcd0b21a7"
        return {"success": True, "data": {"updated": True}}

    monkeypatch.setattr(server, "get_unified_store", lambda: store)
    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server, "_record_gh_to_session", record_mock)

    response = await server.call_tool(
        "gh_edit",
        {
            "epoch": 1,
            "create": [
                {
                    "temp_id": "T1",
                    "guid": "2e205f24-9279-47b2-b414-d06dcd0b21a7",
                    "pos": [0, 0],
                },
                {
                    "temp_id": "T2",
                    "name": "Area",
                    "pos": [100, 0],
                },
            ],
        },
    )

    payload = json.loads(response[0].text)
    warnings = payload["deprecation_warnings"]
    assert warnings == [
        {
            "temp_id": "T1",
            "type": "deprecated_guid",
            "guid": "2e205f24-9279-47b2-b414-d06dcd0b21a7",
            "name": "Area",
            "replacement_guid": "86b28a7e-94d9-4791-8306-e13e10d5f8d5",
            "replacement_name": "Area",
            "reason": "obsolete",
        },
        {
            "temp_id": "T2",
            "type": "ambiguous_name",
            "name": "Area",
            "deprecated_guids": ["2e205f24-9279-47b2-b414-d06dcd0b21a7"],
            "replacement_guids": ["86b28a7e-94d9-4791-8306-e13e10d5f8d5"],
            "replacement_names": ["Area"],
        },
    ]

    recorded_result = record_mock.await_args.kwargs["result"]
    assert recorded_result["data"]["deprecation_warnings"] == warnings


@pytest.mark.asyncio
async def test_gh_batch_component_info_resolves_active_guid(monkeypatch, patched_server):
    store = _make_store_with_area_notes()

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/batch-component-info"
        assert method == "POST"
        assert payload == {"guids": ["86b28a7e-94d9-4791-8306-e13e10d5f8d5"]}
        return {
            "success": True,
            "data": {
                "components": [
                    {
                        "guid": "86b28a7e-94d9-4791-8306-e13e10d5f8d5",
                        "name": "Area",
                    }
                ]
            },
        }

    monkeypatch.setattr(server, "get_unified_store", lambda: store)
    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool("gh_batch_component_info", {"names": ["Area"]})
    payload = json.loads(response[0].text)

    assert payload["resolved"] == {"Area": "86b28a7e-94d9-4791-8306-e13e10d5f8d5"}
    assert payload["unresolved"] == []


@pytest.mark.asyncio
async def test_gh_batch_component_info_library_fallback_skips_deprecated_exact_match(monkeypatch, patched_server):
    store = _make_store_with_area_notes()
    monkeypatch.setattr(store, "resolve_active_component_guid_by_name", lambda _name: None)

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/library":
            assert method == "GET"
            assert payload == {"search": "Area", "limit": 50}
            return {
                "success": True,
                "data": {
                    "components": [
                        {"guid": "2e205f24-9279-47b2-b414-d06dcd0b21a7", "name": "Area"},
                        {"guid": "86b28a7e-94d9-4791-8306-e13e10d5f8d5", "name": "Area"},
                    ]
                },
            }
        if route == "/gh/batch-component-info":
            assert method == "POST"
            assert payload == {"guids": ["86b28a7e-94d9-4791-8306-e13e10d5f8d5"]}
            return {
                "success": True,
                "data": {"components": [{"guid": "86b28a7e-94d9-4791-8306-e13e10d5f8d5", "name": "Area"}]},
            }
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "get_unified_store", lambda: store)
    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool("gh_batch_component_info", {"names": ["Area"]})
    payload = json.loads(response[0].text)

    assert payload["resolved"] == {"Area": "86b28a7e-94d9-4791-8306-e13e10d5f8d5"}
    assert payload["unresolved"] == []


@pytest.mark.asyncio
async def test_gh_edit_warns_for_deprecated_nickname_alias(monkeypatch, patched_server):
    store = _make_store_with_multiplication_alias()

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/edit"
        assert method == "POST"
        return {"success": True, "data": {"updated": True}}

    monkeypatch.setattr(server, "get_unified_store", lambda: store)
    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server, "_record_gh_to_session", AsyncMock())

    response = await server.call_tool(
        "gh_edit",
        {
            "epoch": 1,
            "create": [
                {
                    "temp_id": "T1",
                    "name": "A×B",
                    "pos": [0, 0],
                }
            ],
        },
    )
    payload = json.loads(response[0].text)
    assert payload["deprecation_warnings"] == [
        {
            "temp_id": "T1",
            "type": "ambiguous_name",
            "name": "A×B",
            "deprecated_guids": ["b8963bb1-aa57-476e-a20e-ed6cf635a49c"],
            "replacement_guids": ["ce46b74e-00c9-43c4-805a-193b69ea4a11"],
            "replacement_names": ["Multiplication"],
        }
    ]
