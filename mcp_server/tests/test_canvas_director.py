from __future__ import annotations

import json

import pytest

from rook import canvas_director as cd


def _state(export_id="export_a"):
    return {
        "metadata_kind": "rook.canvas_director.export",
        "schema_version": 1,
        "export_id": export_id,
        "template_id": "canvas_director.basic_motion",
        "template_version": "0.1.0",
        "payload": {"timeline": {"fps": 24, "frame_count": 3}},
    }


def _envelope(state=None, diagnostics=None):
    state = state or _state()
    return {
        "canvas_export_state": state,
        "canvas_export_state_sha256": cd.canvas_export_state_sha256(state),
        "diagnostics": diagnostics or [],
        "suggested_spec_id": "spec_a",
        "read_only": True,
    }


def test_validate_id_accepts_safe_ids():
    assert cd.validate_canvas_director_id("export_01") == "export_01"


@pytest.mark.parametrize("bad", ["", "../x", "x/y", "x.y", "CON", "A", "-x"])
def test_validate_id_rejects_unsafe_ids(bad):
    with pytest.raises(cd.CanvasDirectorError) as ei:
        cd.validate_canvas_director_id(bad)
    assert ei.value.code in {"invalid_export_id", "invalid_spec_id"}


def test_hash_is_independent_of_object_key_order():
    left = {"b": "2", "a": "1"}
    right = {"a": "1", "b": "2"}
    assert cd.canvas_export_state_sha256(left) == cd.canvas_export_state_sha256(right)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"b": "2", "a": "1"}, b'{"a":"1","b":"2"}'),
        ({"text": "<>&", "list": [True, None, 3]}, b'{"list":[true,null,3],"text":"<>&"}'),
    ],
)
def test_canonical_json_bytes_match_managed_vectors(payload, expected):
    assert cd._canonical_json_bytes(payload) == expected


def test_canonical_json_rejects_non_integer_numbers():
    with pytest.raises(cd.CanvasDirectorError) as ei:
        cd.canvas_export_state_sha256({"x": 1.25})
    assert ei.value.code == "invalid_input"


def test_canonical_json_rejects_non_ascii_object_keys():
    with pytest.raises(cd.CanvasDirectorError) as ei:
        cd.canvas_export_state_sha256({"😀": 1})
    assert ei.value.code == "invalid_input"


def test_save_export_persists_full_envelope(tmp_path):
    result = cd.save_canvas_export(tmp_path, _envelope(), export_id="export_a")
    path = result["export_path"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload) == {
        "canvas_export_state",
        "canvas_export_state_sha256",
        "diagnostics",
        "suggested_spec_id",
        "read_only",
    }


def test_same_state_retry_is_idempotent_and_does_not_overwrite_diagnostics(tmp_path):
    first = _envelope(diagnostics=[{"code": "first"}])
    second = _envelope(diagnostics=[{"code": "second"}])
    cd.save_canvas_export(tmp_path, first, export_id="export_a")
    result = cd.save_canvas_export(tmp_path, second, export_id="export_a")
    persisted = json.loads(result["export_path"].read_text(encoding="utf-8"))
    assert result["idempotent"] is True
    assert persisted["diagnostics"] == [{"code": "first"}]


def test_different_state_same_export_id_fails_with_collision(tmp_path):
    cd.save_canvas_export(tmp_path, _envelope(_state("export_a")), export_id="export_a")
    changed = _state("export_a")
    changed["payload"]["timeline"]["frame_count"] = 4
    with pytest.raises(cd.CanvasDirectorError) as ei:
        cd.save_canvas_export(tmp_path, _envelope(changed), export_id="export_a")
    assert ei.value.code == "id_collision"


@pytest.mark.asyncio
async def test_extract_canvas_export_preserves_structured_solve_timeout():
    async def native(*args, **kwargs):
        return {"success": False, "data": {"code": "solve_timeout", "message": "timed out"}}

    with pytest.raises(cd.CanvasDirectorError) as ei:
        await cd.extract_canvas_export({"export_id": "export_a"}, call_native=native)
    assert ei.value.code == "solve_timeout"
