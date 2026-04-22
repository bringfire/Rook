import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


import json

from rook.agent.conductor import Conductor
from rook.agent.substrate_analytics import (
    SubstrateObservation,
    _compact_error,
    extract_substrate_observation,
    load_substrate_observations_jsonl,
    persist_substrate_observation,
    summarize_substrate_observations,
)
from rook.agent.spawn import SpawnResult


def test_extract_substrate_observation_from_nested_data():
    result = {
        "success": True,
        "verified": True,
        "data": {
            "execution_route": "known_command",
            "command": "_-Sphere",
        },
    }

    obs = extract_substrate_observation("rhino_execute_intent", result, task_id="t1")

    assert obs is not None
    assert obs.tool == "rhino_execute_intent"
    assert obs.route_taken == "known_command"
    assert obs.operation == "_-Sphere"
    assert obs.success is True
    assert obs.verified is True
    assert obs.task_id == "t1"


def test_extract_substrate_observation_returns_none_without_route():
    result = {"success": True, "data": {"message": "ok"}}
    assert extract_substrate_observation("rhino_create", result) is None


def test_summarize_substrate_observations_reports_candidates_and_hotspots():
    observations = [
        {
            "tool": "rhino_execute_intent",
            "route_taken": "known_command",
            "operation": "_-Sphere",
            "success": True,
            "verified": True,
        },
        {
            "tool": "rhino_execute_intent",
            "route_taken": "known_command",
            "operation": "_-Sphere",
            "success": True,
            "verified": True,
        },
        {
            "tool": "rhino_execute_intent",
            "route_taken": "known_command",
            "operation": "_-Sphere",
            "success": True,
            "verified": True,
        },
        {
            "tool": "rhino_execute_intent",
            "route_taken": "interactive",
            "operation": "_-FilletEdge",
            "success": False,
            "verified": False,
        },
        {
            "tool": "rhino_execute_intent",
            "route_taken": "interactive",
            "operation": "_-FilletEdge",
            "success": True,
            "verified": False,
        },
    ]

    summary = summarize_substrate_observations(observations)

    assert summary["total_observations"] == 5
    assert summary["route_counts"]["known_command"] == 3
    assert summary["route_counts"]["interactive"] == 2
    assert summary["promotion_candidates"][0]["operation"] == "_-Sphere"
    assert summary["interactive_hotspots"][0]["operation"] == "_-FilletEdge"


def test_conductor_report_includes_fleet_substrate_summary():
    conductor = Conductor()
    per_agent_summary = summarize_substrate_observations([
        {
            "tool": "rhino_execute_intent",
            "success": True,
            "error": "",
            "route_taken": "direct_api",
            "operation": "create_sphere",
            "verified": True,
        },
        {
            "tool": "rhino_execute_intent",
            "success": True,
            "error": "",
            "route_taken": "known_command",
            "operation": "_-Sphere",
            "verified": True,
        },
    ])
    result = SpawnResult(
        task_id="t1",
        status="success",
        task="test",
        substrate_summary=per_agent_summary,
        tools_called=[
            {
                "tool": "rhino_execute_intent",
                "success": True,
                "error": "",
                "route_taken": "direct_api",
                "operation": "create_sphere",
                "verified": True,
            },
            {
                "tool": "rhino_execute_intent",
                "success": True,
                "error": "",
                "route_taken": "known_command",
                "operation": "_-Sphere",
                "verified": True,
            },
        ],
    )

    conductor.add_result("t1", result)
    report = conductor.report()

    assert report.substrate_summary["total_observations"] == 2
    assert report.substrate_summary["route_counts"]["direct_api"] == 1
    assert report.substrate_summary["route_counts"]["known_command"] == 1
    assert report.per_agent_summaries[0]["substrate_summary"] == per_agent_summary


# ---------------------------------------------------------------------------
# Persistence (substrate_observations.jsonl)
# ---------------------------------------------------------------------------


def _sample_observation(**overrides) -> SubstrateObservation:
    base = dict(
        tool="rhino_execute_intent",
        route_taken="known_command",
        success=True,
        operation="_-Sphere",
        verified=True,
        task_id="",
    )
    base.update(overrides)
    return SubstrateObservation(**base)


def test_persist_substrate_observation_writes_expected_schema(tmp_path):
    path = tmp_path / "substrate_observations.jsonl"
    obs = _sample_observation()

    persist_substrate_observation(obs, error="", session_id="chat-xyz", path=path)

    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert set(record.keys()) == {
        "timestamp", "session_id", "tool", "operation",
        "route_taken", "success", "verified", "error",
    }
    assert record["tool"] == "rhino_execute_intent"
    assert record["operation"] == "_-Sphere"
    assert record["route_taken"] == "known_command"
    assert record["success"] is True
    assert record["verified"] is True
    assert record["session_id"] == "chat-xyz"
    assert record["error"] == ""


def test_persist_substrate_observation_appends_not_truncates(tmp_path):
    path = tmp_path / "substrate_observations.jsonl"

    persist_substrate_observation(
        _sample_observation(operation="first"), path=path
    )
    persist_substrate_observation(
        _sample_observation(operation="second"), path=path
    )
    persist_substrate_observation(
        _sample_observation(operation="third"), path=path
    )

    records = load_substrate_observations_jsonl(path=path)
    assert [r["operation"] for r in records] == ["first", "second", "third"]


def test_persist_substrate_observation_roundtrips_via_loader(tmp_path):
    path = tmp_path / "substrate_observations.jsonl"
    originals = [
        _sample_observation(operation="op1"),
        _sample_observation(
            operation="op2", route_taken="interactive", verified=False
        ),
        _sample_observation(operation="op3", success=False, verified=None),
    ]

    for obs in originals:
        persist_substrate_observation(obs, path=path)

    loaded = load_substrate_observations_jsonl(path=path)
    assert len(loaded) == 3
    assert [r["operation"] for r in loaded] == ["op1", "op2", "op3"]
    assert loaded[1]["route_taken"] == "interactive"
    assert loaded[1]["verified"] is False
    assert loaded[2]["success"] is False
    assert loaded[2]["verified"] is None


def test_persist_substrate_observation_session_id_fallback_to_task_id(tmp_path):
    path = tmp_path / "substrate_observations.jsonl"
    obs = _sample_observation(task_id="worker-42")

    persist_substrate_observation(obs, path=path)  # no session_id provided

    record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert record["session_id"] == "worker-42"


def test_persist_substrate_observation_never_raises_on_bad_path(tmp_path):
    # Point at a path whose parent cannot be created (file-in-the-middle).
    blocker = tmp_path / "blocker.txt"
    blocker.write_text("not a directory")
    bad_path = blocker / "substrate_observations.jsonl"

    # Must not raise — best-effort posture is the contract.
    persist_substrate_observation(_sample_observation(), path=bad_path)


def test_load_substrate_observations_jsonl_missing_file(tmp_path):
    path = tmp_path / "does_not_exist.jsonl"
    assert load_substrate_observations_jsonl(path=path) == []


def test_load_substrate_observations_jsonl_skips_malformed_lines(tmp_path):
    path = tmp_path / "substrate_observations.jsonl"
    path.write_text(
        '{"tool":"rhino_execute_intent","route_taken":"direct"}\n'
        'not json at all\n'
        '\n'  # blank line should be skipped
        '{"tool":"gh_execute_intent","route_taken":"known_command"}\n',
        encoding="utf-8",
    )

    records = load_substrate_observations_jsonl(path=path)
    assert len(records) == 2
    assert records[0]["tool"] == "rhino_execute_intent"
    assert records[1]["tool"] == "gh_execute_intent"


# ---------------------------------------------------------------------------
# _compact_error fallback posture
# ---------------------------------------------------------------------------


def test_compact_error_empty_on_success():
    assert _compact_error({"success": True, "error": "ignore me"}) == ""


def test_compact_error_prefers_top_level_error():
    result = {
        "success": False,
        "error": "top-level failure",
        "data": {"error": "nested failure"},
    }
    assert _compact_error(result) == "top-level failure"


def test_compact_error_falls_back_to_nested_data_error():
    result = {
        "success": False,
        "data": {"error": "nested failure"},
    }
    assert _compact_error(result) == "nested failure"


def test_compact_error_falls_back_to_stringified_data():
    result = {
        "success": False,
        "data": {"code": 42, "detail": "stringy"},
    }
    out = _compact_error(result)
    assert "code" in out and "42" in out


def test_compact_error_truncates_to_max_len():
    result = {"success": False, "error": "x" * 500}
    assert len(_compact_error(result, max_len=120)) == 120


def test_compact_error_handles_missing_data():
    assert _compact_error({"success": False}) == ""
    assert _compact_error({}) == ""
    assert _compact_error(None) == ""


# ---------------------------------------------------------------------------
# Decoupling: substrate persistence must NOT be gated on metrics availability
# ---------------------------------------------------------------------------


def test_base_agent_substrate_persists_when_observation_recording_off(monkeypatch):
    """Substrate persistence must run even when the metrics path is disabled.

    Pins Codex Finding #1: base_agent.py::_record_observation gated substrate
    writes behind ``config.observation_recording`` and the metrics-infra check,
    silently dropping route_taken telemetry for direct-bridge executions.
    """
    from rook.agent.base_agent import RookAgent
    from rook.agent.config import AgentConfig

    captured = []

    def _spy_persist(observation, *, error="", session_id="", path=None):
        captured.append({
            "tool": observation.tool,
            "route_taken": observation.route_taken,
        })

    monkeypatch.setattr(
        "rook.agent.base_agent.persist_substrate_observation", _spy_persist
    )

    agent = RookAgent(config=AgentConfig(observation_recording=False))
    result = {
        "success": True,
        "verified": True,
        "data": {
            "route_taken": "known_command",
            "command": "_-Sphere",
        },
    }

    agent._record_observation("rhino_execute_intent", {}, result, duration_ms=1.0)

    assert len(captured) == 1
    assert captured[0]["tool"] == "rhino_execute_intent"
    assert captured[0]["route_taken"] == "known_command"


def test_server_substrate_persists_when_metrics_store_raises(monkeypatch):
    """Substrate persistence must survive a metrics.record() exception.

    Pins Codex Finding #2: server.py::_record_observation originally nested
    the substrate write inside the same try block as ``get_metrics_store().record()``,
    so any metrics exception would silently drop substrate telemetry too.
    """
    from rook import server as server_mod

    class _RaisingStore:
        def record(self, obs):
            raise RuntimeError("metrics store deliberately broken for this test")

    captured = []

    def _spy_persist(observation, *, error="", session_id="", path=None):
        captured.append({
            "tool": observation.tool,
            "route_taken": observation.route_taken,
        })

    # get_metrics_store is imported lazily inside _record_observation, so the
    # binding lives on the source module, not on server.
    monkeypatch.setattr(
        "rook.learning.metrics_store.get_metrics_store",
        lambda: _RaisingStore(),
    )
    monkeypatch.setattr(
        "rook.agent.substrate_analytics.persist_substrate_observation",
        _spy_persist,
    )

    result = {
        "success": True,
        "verified": True,
        "data": {
            "route_taken": "known_command",
            "command": "_-Sphere",
        },
    }

    # Must not raise even though the metrics store explodes.
    server_mod._record_observation(
        "rhino_execute_intent", {}, result, duration_ms=1.0, injection_meta=None
    )

    assert len(captured) == 1
    assert captured[0]["tool"] == "rhino_execute_intent"
    assert captured[0]["route_taken"] == "known_command"


def test_server_handoff_gate_skips_both_paths(monkeypatch):
    """A single top-of-function gate skips both metrics and substrate for handoffs.

    Pins the PR-3 handoff contract after the decoupling fix: handoff results
    are not executions for either telemetry store. Asserts (a) substrate
    persist is never called, and (b) the metrics store is never touched —
    proving the single gate, not two separate checks, covers both paths.
    """
    from rook import server as server_mod

    metrics_touched = []
    substrate_captured = []

    class _RecordingStore:
        def record(self, obs):
            metrics_touched.append(obs)

    def _spy_persist(observation, **_kwargs):
        substrate_captured.append(observation)

    monkeypatch.setattr(
        "rook.learning.metrics_store.get_metrics_store",
        lambda: _RecordingStore(),
    )
    monkeypatch.setattr(
        "rook.agent.substrate_analytics.persist_substrate_observation",
        _spy_persist,
    )

    handoff_result = {
        "_is_handoff": True,
        "success": True,
        "data": {
            "route_taken": "direct",
            "command": "_-Sphere",
        },
    }

    server_mod._record_observation(
        "gh_execute_intent", {}, handoff_result, duration_ms=1.0, injection_meta=None
    )

    assert substrate_captured == []
    assert metrics_touched == []
