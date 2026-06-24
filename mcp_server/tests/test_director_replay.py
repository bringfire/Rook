import json, pytest
from pathlib import Path
from rook import director


class FakeNative:
    def __init__(self, response): self.response = response; self.calls = []
    async def __call__(self, endpoint, method="POST", data=None, port=None):
        self.calls.append((endpoint, method, data, port)); return self.response


VALID_TRACK = {"schema_version": 1, "transform_semantics": "absolute_from_source",
               "frame_count": 1, "fps": 24, "resolution": {"width": 16, "height": 16},
               "animated_object_ids": ["a"], "camera_frames": [], "object_frames": []}


@pytest.mark.asyncio
async def test_run_replay_inline_track_generates_session_id_and_posts():
    native = FakeNative({"success": True, "data": {"status": "completed", "frames_played": 1}})
    out = await director.run_replay({"track": VALID_TRACK}, call_native=native)
    assert out["status"] == "completed"
    ep, _m, body, _p = native.calls[0]
    assert ep == "/director/replay"
    assert body["track"] == VALID_TRACK
    assert isinstance(body["replay_session_id"], str) and body["replay_session_id"]


@pytest.mark.asyncio
async def test_run_replay_passthrough_session_id():
    native = FakeNative({"success": True, "data": {"status": "completed"}})
    await director.run_replay({"track": VALID_TRACK, "replay_session_id": "my-id_1"}, call_native=native)
    assert native.calls[0][2]["replay_session_id"] == "my-id_1"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", 123, {"x": 1}])
async def test_run_replay_rejects_explicit_invalid_session_id(bad):
    native = FakeNative({"success": True, "data": {}})
    with pytest.raises(director.DirectorError, match="invalid_session_id"):
        await director.run_replay({"track": VALID_TRACK, "replay_session_id": bad}, call_native=native)
    assert native.calls == []  # rejected before any native call


@pytest.mark.asyncio
async def test_run_replay_track_path_read(tmp_path):
    p = tmp_path / "t.json"; p.write_text(json.dumps(VALID_TRACK), encoding="utf-8")
    native = FakeNative({"success": True, "data": {"status": "completed"}})
    await director.run_replay({"track_path": str(p)}, call_native=native)
    assert native.calls[0][2]["track"] == VALID_TRACK


@pytest.mark.asyncio
async def test_run_replay_both_or_neither_track_is_error():
    native = FakeNative({"success": True, "data": {}})
    with pytest.raises(director.DirectorError, match="invalid_track_input"):
        await director.run_replay({"track": VALID_TRACK, "track_path": "x"}, call_native=native)
    with pytest.raises(director.DirectorError, match="invalid_track_input"):
        await director.run_replay({}, call_native=native)


@pytest.mark.asyncio
async def test_run_replay_missing_path_and_bad_json(tmp_path):
    native = FakeNative({"success": True, "data": {}})
    with pytest.raises(director.DirectorError, match="track_not_found"):
        await director.run_replay({"track_path": str(tmp_path / "nope.json")}, call_native=native)
    bad = tmp_path / "bad.json"; bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(director.DirectorError, match="track_read_failed"):
        await director.run_replay({"track_path": str(bad)}, call_native=native)


@pytest.mark.asyncio
async def test_run_replay_native_error_raises_directorerror():
    native = FakeNative({"success": False, "data": {"code": "replay_already_active", "message": "busy"}})
    with pytest.raises(director.DirectorError, match="replay_already_active"):
        await director.run_replay({"track": VALID_TRACK}, call_native=native)


@pytest.mark.asyncio
async def test_cancel_replay_requires_id_and_posts():
    native = FakeNative({"success": True, "data": {"cancel_requested": True}})
    out = await director.cancel_replay({"replay_session_id": "abc"}, call_native=native)
    assert out["cancel_requested"] is True
    assert native.calls[0][0] == "/director/replay/cancel"
    with pytest.raises(director.DirectorError, match="invalid_session_id"):
        await director.cancel_replay({}, call_native=native)
