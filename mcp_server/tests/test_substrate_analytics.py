import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from rook.agent.conductor import Conductor
from rook.agent.substrate_analytics import (
    extract_substrate_observation,
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
