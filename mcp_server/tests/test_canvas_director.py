from __future__ import annotations

import json
import subprocess
import threading
import time

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


@pytest.mark.parametrize("value", [-(2**63), 2**63 - 1])
def test_canonical_json_accepts_signed_int64_boundaries(value):
    assert cd._canonical_json_bytes({"x": value}) == f'{{"x":{value}}}'.encode("utf-8")


@pytest.mark.parametrize("value", [2**63, -(2**63) - 1])
def test_canonical_json_rejects_int64_overflow(value):
    with pytest.raises(cd.CanvasDirectorError) as ei:
        cd.canvas_export_state_sha256({"x": value})
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


@pytest.mark.parametrize("bad", ["", False])
def test_save_export_rejects_explicit_falsey_export_ids(tmp_path, bad):
    with pytest.raises(cd.CanvasDirectorError) as ei:
        cd.save_canvas_export(tmp_path, _envelope(), export_id=bad)
    assert ei.value.code == "invalid_export_id"
    assert not (tmp_path / ".rook" / "director" / "exports" / "export_a.json").exists()


def test_save_export_wraps_director_directory_write_failures(tmp_path):
    (tmp_path / ".rook").write_text("not a directory", encoding="utf-8")
    with pytest.raises(cd.CanvasDirectorError) as ei:
        cd.save_canvas_export(tmp_path, _envelope(), export_id="export_a")
    assert ei.value.code == "export_write_failed"


def test_save_export_rejects_export_id_mismatch(tmp_path):
    with pytest.raises(cd.CanvasDirectorError) as ei:
        cd.save_canvas_export(tmp_path, _envelope(_state("export_a")), export_id="export_b")
    assert ei.value.code == "invalid_export_id"
    assert not (tmp_path / ".rook" / "director" / "exports" / "export_b.json").exists()


def test_save_export_rejects_missing_state_export_id(tmp_path):
    state = _state()
    del state["export_id"]
    with pytest.raises(cd.CanvasDirectorError) as ei:
        cd.save_canvas_export(tmp_path, _envelope(state), export_id="export_a")
    assert ei.value.code == "invalid_export_id"
    assert not (tmp_path / ".rook" / "director" / "exports" / "export_a.json").exists()


def test_save_export_rejects_symlinked_rook_escape(tmp_path):
    project_root = tmp_path / "project"
    outside_root = tmp_path / "outside"
    project_root.mkdir()
    outside_root.mkdir()
    try:
        (project_root / ".rook").symlink_to(outside_root, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(cd.CanvasDirectorError) as ei:
        cd.save_canvas_export(project_root, _envelope(), export_id="export_a")
    assert ei.value.code == "export_write_failed"
    assert not (outside_root / "director" / "exports" / "export_a.json").exists()


def test_save_export_rejects_junction_escape_before_creating_descendants(tmp_path):
    project_root = tmp_path / "project"
    outside_root = tmp_path / "outside"
    project_root.mkdir()
    outside_root.mkdir()
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(project_root / ".rook"), str(outside_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"junction creation unavailable: {result.stderr or result.stdout}")

    with pytest.raises(cd.CanvasDirectorError) as ei:
        cd.save_canvas_export(project_root, _envelope(), export_id="export_a")
    assert ei.value.code == "export_write_failed"
    assert not (outside_root / "director").exists()
    assert not (outside_root / "director" / "exports").exists()


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


def test_same_state_retry_ignores_stale_lock_when_export_exists(tmp_path, monkeypatch):
    envelope = _envelope()
    result = cd.save_canvas_export(tmp_path, envelope, export_id="export_a")
    result["export_path"].with_name("export_a.json.lock").write_text("stale\n", encoding="utf-8")
    monkeypatch.setattr(cd, "_LOCK_WAIT_SECONDS", 0.01)

    retry = cd.save_canvas_export(tmp_path, envelope, export_id="export_a")

    assert retry["idempotent"] is True
    assert retry["export_path"] == result["export_path"]


def test_different_state_with_stale_lock_still_collides(tmp_path, monkeypatch):
    result = cd.save_canvas_export(tmp_path, _envelope(_state("export_a")), export_id="export_a")
    result["export_path"].with_name("export_a.json.lock").write_text("stale\n", encoding="utf-8")
    monkeypatch.setattr(cd, "_LOCK_WAIT_SECONDS", 0.01)
    changed = _state("export_a")
    changed["payload"]["timeline"]["frame_count"] = 4

    with pytest.raises(cd.CanvasDirectorError) as ei:
        cd.save_canvas_export(tmp_path, _envelope(changed), export_id="export_a")

    assert ei.value.code == "id_collision"


def test_concurrent_first_writes_detect_id_collision(tmp_path, monkeypatch):
    first_state = _state("export_a")
    second_state = _state("export_a")
    second_state["payload"]["timeline"]["frame_count"] = 4
    original_write = cd._atomic_write_json
    partial_started = threading.Event()
    release_writer = threading.Event()

    def paused_write(path, payload):
        partial_started.set()
        assert release_writer.wait(timeout=5)
        original_write(path, payload)

    monkeypatch.setattr(cd, "_atomic_write_json", paused_write)
    results = []
    errors = []

    def worker(envelope):
        try:
            results.append(cd.save_canvas_export(tmp_path, envelope, export_id="export_a"))
        except Exception as exc:  # noqa: BLE001 - test records thread exceptions for assertions.
            errors.append(exc)

    first = threading.Thread(target=worker, args=(_envelope(first_state),))
    first.start()
    assert partial_started.wait(timeout=5)
    second = threading.Thread(target=worker, args=(_envelope(second_state),))
    second.start()
    time.sleep(0.1)
    release_writer.set()
    first.join(timeout=10)
    second.join(timeout=10)
    assert not first.is_alive()
    assert not second.is_alive()

    assert len(results) == 1
    assert [getattr(error, "code", None) for error in errors] == ["id_collision"]
    persisted = json.loads(results[0]["export_path"].read_text(encoding="utf-8"))
    assert persisted["canvas_export_state_sha256"] == results[0]["canvas_export_state_sha256"]


def test_same_state_retry_waits_for_in_progress_first_write(tmp_path, monkeypatch):
    original_write = cd._atomic_write_json
    partial_started = threading.Event()
    release_writer = threading.Event()

    def paused_write(path, payload):
        partial_started.set()
        assert release_writer.wait(timeout=5)
        original_write(path, payload)

    monkeypatch.setattr(cd, "_atomic_write_json", paused_write)
    envelope = _envelope()
    results = []
    errors = []

    def worker():
        try:
            results.append(cd.save_canvas_export(tmp_path, envelope, export_id="export_a"))
        except Exception as exc:  # noqa: BLE001 - test records thread exceptions for assertions.
            errors.append(exc)

    first = threading.Thread(target=worker)
    first.start()
    assert partial_started.wait(timeout=5)
    second = threading.Thread(target=worker)
    second.start()
    time.sleep(0.1)
    release_writer.set()
    first.join(timeout=10)
    second.join(timeout=10)
    assert not first.is_alive()
    assert not second.is_alive()

    monkeypatch.setattr(cd, "_atomic_write_json", original_write)
    assert errors == []
    assert sorted(result["idempotent"] for result in results) == [False, True]
    assert json.loads(results[0]["export_path"].read_text(encoding="utf-8")) == envelope


@pytest.mark.asyncio
async def test_extract_canvas_export_preserves_structured_solve_timeout():
    async def native(*args, **kwargs):
        return {"success": False, "data": {"code": "solve_timeout", "message": "timed out"}}

    with pytest.raises(cd.CanvasDirectorError) as ei:
        await cd.extract_canvas_export({"export_id": "export_a"}, call_native=native)
    assert ei.value.code == "solve_timeout"
