from __future__ import annotations

import argparse
import ast
import base64
import copy
import dataclasses
import hashlib
import importlib
import inspect
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


EXPECTED_RED = "EXPECTED_RED:containment-release-probe:missing"
SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

try:
    probe: ModuleType | None = importlib.import_module(
        "containment_release.installed_probe"
    )
except ModuleNotFoundError as exc:
    if exc.name not in {
        "containment_release",
        "containment_release.installed_probe",
    }:
        raise
    probe = None

requires_probe = pytest.mark.skipif(probe is None, reason=EXPECTED_RED)


CONTAINED_TOOLS = (
    "gh_execute_intent",
    "rhino_execute_intent",
    "plan_and_execute",
    "spawn_agent",
    "gh_explore_workflow",
    "gh_replay_recipe",
)
EXPECTED_DENIALS = {
    "gh_execute_intent": {
        "code": "legacy_semantic_tool_contained",
        "tool": "gh_execute_intent",
        "disposition": "retired",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current Grasshopper surface; inspect state and "
            "components, then use explicit gh_edit or supported script tools "
            "and verify solve state, outputs, and errors."
        ),
    },
    "rhino_execute_intent": {
        "code": "legacy_semantic_tool_contained",
        "tool": "rhino_execute_intent",
        "disposition": "retired",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current Rhino surface; use explicit typed Rhino "
            "tools, rhino_execute, or a sanctioned preflighted rhino_command, "
            "then verify the host result."
        ),
    },
    "plan_and_execute": {
        "code": "legacy_semantic_tool_contained",
        "tool": "plan_and_execute",
        "disposition": "suspended",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current surface and perform bounded steps through "
            "explicit admitted tools; autonomous plan execution is suspended."
        ),
    },
    "spawn_agent": {
        "code": "legacy_semantic_tool_contained",
        "tool": "spawn_agent",
        "disposition": "suspended",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current surface and use the connected model to call "
            "explicit admitted tools directly; autonomous agent spawning is "
            "suspended."
        ),
    },
    "gh_explore_workflow": {
        "code": "legacy_semantic_tool_contained",
        "tool": "gh_explore_workflow",
        "disposition": "suspended",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current Grasshopper inspection surface and use "
            "explicit snapshot, component, or knowledge tools; semantic "
            "workflow exploration is suspended."
        ),
    },
    "gh_replay_recipe": {
        "code": "legacy_semantic_tool_contained",
        "tool": "gh_replay_recipe",
        "disposition": "suspended",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current Grasshopper surface and apply reviewed "
            "explicit gh_edit operations; recipe replay is suspended."
        ),
    },
}

DISCOVERY_COUNTS = {
    "unprofiled": 422,
    "interactive-full": 425,
    "lean": 20,
    "readonly": 148,
}
TRANSPORT_INGRESSES = ("public_mcp", "progressive_meta")
PROFILES = ("full", "lean", "readonly")
INTERNAL_ROWS = (
    ("server._call_tool_dispatch", "gh_execute_intent", "server_dispatch", "dictionary_envelope"),
    ("server._mcp_tool_executor", "rhino_execute_intent", "server_dispatch", "dictionary_envelope"),
    ("ToolDispatcher.dispatch", "plan_and_execute", "tool_dispatcher", "dictionary_envelope"),
    ("ToolDispatcher._dispatch_inner", "spawn_agent", "tool_dispatcher", "dictionary_envelope"),
    ("ToolDispatcher._call_local", "gh_explore_workflow", "tool_dispatcher", "dictionary_envelope"),
    ("ToolDispatcher._dispatch_with_knowledge", "gh_replay_recipe", "tool_dispatcher", "dictionary_envelope"),
    ("RookAgent._run_loop", "gh_execute_intent", "rook_agent", "rook_agent_protocol"),
    ("RookAgent._execute_tool", "rhino_execute_intent", "rook_agent", "dictionary_envelope"),
    ("RookAgent._execute_local_tool", "plan_and_execute", "rook_agent", "dictionary_envelope"),
    ("ChatRunner.run_turn", "spawn_agent", "rook_chat", "rook_chat_protocol"),
    ("rook.agent.plan_graph_live.apply_live_producer_node", "gh_explore_workflow", "plan_graph", "plan_graph_refusal"),
    ("BootstrapRunner.run_test", "gh_replay_recipe", "internal_handler", "bootstrap_test_result"),
    ("BootstrapRunner._mock_executor", "gh_execute_intent", "internal_handler", "dictionary_envelope"),
    ("bootstrap.HttpExecutor.execute", "rhino_execute_intent", "internal_handler", "dictionary_envelope"),
    ("bootstrap.create_mock_executor.callable", "plan_and_execute", "internal_handler", "dictionary_envelope"),
    ("learning.create_tool_executor.callable", "spawn_agent", "internal_handler", "dictionary_envelope"),
    ("Investigator.investigate_tool", "gh_explore_workflow", "internal_handler", "investigation_result"),
    ("Investigator.investigate_gap", "gh_replay_recipe", "internal_handler", "investigation_result"),
    ("Investigator.investigate_workflow", "gh_execute_intent", "internal_handler", "investigation_result"),
    ("Investigator._run_experiment", "rhino_execute_intent", "internal_handler", "experiment_result"),
    ("HybridInvestigator.investigate_tool", "plan_and_execute", "internal_handler", "hybrid_investigation_result"),
    ("HybridInvestigator.investigate_gap", "spawn_agent", "internal_handler", "hybrid_investigation_result"),
    ("LearningSession.run_investigation_cycle.tool_target", "gh_explore_workflow", "internal_handler", "investigation_result"),
    ("explorer.HttpExecutor.execute", "gh_replay_recipe", "internal_handler", "explorer_execution_result"),
    ("explorer.HttpExecutor.execute_sync", "gh_execute_intent", "internal_handler", "explorer_execution_result"),
    ("explorer.MockExecutor.execute", "rhino_execute_intent", "internal_handler", "explorer_execution_result"),
    ("explorer.MockExecutor.execute_sync", "plan_and_execute", "internal_handler", "explorer_execution_result"),
    ("server._handle_spawn_agent", "spawn_agent", "internal_handler", "dictionary_envelope"),
    ("server._handle_plan_and_execute", "plan_and_execute", "internal_handler", "dictionary_envelope"),
)

TIMESTAMP = "2026-07-19T12:34:56.123456Z"
TOKEN = "0123456789abcdef0123456789abcdef"
PID = 4321


def test_installed_probe_module_is_present() -> None:
    assert probe is not None, EXPECTED_RED


def _require_probe() -> ModuleType:
    assert probe is not None, EXPECTED_RED
    return probe


def _denial(tool: str) -> dict[str, object]:
    return {"success": False, "data": copy.deepcopy(EXPECTED_DENIALS[tool])}


def _event(tool: str, origin: str) -> dict[str, object]:
    return {
        "tool": tool,
        "disposition": EXPECTED_DENIALS[tool]["disposition"],
        "origin": origin,
        "timestamp": TIMESTAMP,
    }


def _telemetry(tool: str, origin: str) -> dict[str, object]:
    return {
        "process_id": PID,
        "process_start_token": TOKEN,
        "event": _event(tool, origin),
    }


def _history(tool: str, call_id: str) -> list[dict[str, object]]:
    return [
        {"role": "user", "content": "exercise installed containment"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": tool, "arguments": '{"probe":true}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(_denial(tool), separators=(",", ":")),
        },
        {"role": "assistant", "content": "continued after containment"},
    ]


def _adapter_evidence(adapter: str, tool: str, index: int) -> dict[str, object]:
    if adapter == "dictionary_envelope":
        return {"outer_type": "builtins.dict", "value": _denial(tool)}
    if adapter == "rook_agent_protocol":
        return {
            "outer_type": "builtins.NoneType",
            "return_is_none": True,
            "history": _history(tool, f"probe-agent-{index}"),
            "loop": {
                "tool_calls": 1,
                "successful_tools": 0,
                "tool_start_events": 0,
                "tool_end_events": 0,
                "adaptations": 0,
                "observations": 0,
                "failure_count_entries": 0,
            },
        }
    if adapter == "rook_chat_protocol":
        history = _history(tool, f"probe-chat-{index}")
        history[1].pop("content")
        return {
            "outer_type": "builtins.async_generator",
            "history": history,
            "events": ["text_delta", "done"],
            "loop": {
                "tool_calls": 1,
                "successful_tools": 0,
                "tool_start_events": 0,
                "tool_result_events": 0,
                "error_events": 0,
                "tools_used": [],
                "surface_adaptations": 0,
                "meta_only_diagnoses": 0,
                "stuck_diagnoses": 0,
            },
        }
    if adapter == "plan_graph_refusal":
        return {
            "outer_type": "rook.agent.plan_graph_live.LiveProducerResult",
            "graph_unchanged": True,
            "applied": False,
            "node_id": "containment-producer",
            "tool_name": tool,
            "outcome_status": None,
            "reason": "tool_lifecycle_denied",
        }
    if adapter == "bootstrap_test_result":
        return {
            "outer_type": "rook.bootstrap.runner.TestResult",
            "test_id": f"containment:{tool}",
            "tool": tool,
            "params": {},
            "expected": "either",
            "actual": "error",
            "response": _denial(tool),
            "error_message": "legacy_semantic_tool_contained",
            "duration_ms": 0.0,
            "timestamp_valid": True,
            "created_object_ids": [],
            "completed_tests": [],
        }
    if adapter == "investigation_result":
        return {
            "outer_type": "rook.learning.investigator.InvestigationResult",
            "gap_id": None,
            "tool": tool,
            "patterns_discovered": [],
            "antipatterns_discovered": [],
            "experiments": [],
            "gap_resolved": False,
            "resolution": None,
            "new_gaps": [],
            "insights": [],
            "containment_denial": _denial(tool),
        }
    if adapter == "experiment_result":
        return {
            "outer_type": "rook.learning.investigator.ExperimentResult",
            "tool": tool,
            "params": {},
            "success": False,
            "response": _denial(tool),
            "error": "legacy_semantic_tool_contained",
            "error_category": "unknown",
            "execution_time_ms": 0,
        }
    if adapter == "hybrid_investigation_result":
        return {
            "outer_type": "rook.learning.hybrid_investigator.HybridInvestigationResult",
            "tool": tool,
            "success": False,
            "hypotheses_generated": [],
            "diagnosis": None,
            "reasoning_trace": [],
            "hypothesis_selected": None,
            "fix_selected": None,
            "patterns_discovered": [],
            "antipatterns_discovered": [],
            "insights": [],
            "consolidation_action": None,
            "workflow_detected": None,
            "nuanced_reward": None,
            "visually_verified": False,
            "visual_description": None,
            "viewport_hash_before": None,
            "viewport_hash_after": None,
            "gap_id": None,
            "gap_resolved": False,
            "resolution": None,
            "new_gaps": [],
            "attempts": 0,
            "time_ms": 0,
            "containment_denial": _denial(tool),
            "serialized_containment_denial": _denial(tool),
        }
    if adapter == "explorer_execution_result":
        return {
            "outer_type": "rook.explorer.executor.ExecutionResult",
            "tool_name": tool,
            "params": {},
            "success": False,
            "response": _denial(tool),
            "error": "legacy_semantic_tool_contained",
            "duration_ms": 0,
        }
    raise AssertionError(adapter)


@requires_probe
def test_literal_tables_are_exact_code_owned_and_closed() -> None:
    module = _require_probe()
    assert module.EXPECTED_DENIALS == EXPECTED_DENIALS
    assert type(module.EXPECTED_DENIALS) is dict
    assert module.CONTAINED_TOOLS == CONTAINED_TOOLS
    assert module.DISCOVERY_COUNTS == DISCOVERY_COUNTS
    assert module.TRANSPORT_INGRESSES == TRANSPORT_INGRESSES
    assert module.PROFILES == PROFILES
    assert tuple(
        (row.seam, row.tool, row.origin, row.result_adapter)
        for row in module.INTERNAL_PROBES
    ) == INTERNAL_ROWS
    assert len({row[0] for row in INTERNAL_ROWS}) == 29
    assert set(row[1] for row in INTERNAL_ROWS) == set(CONTAINED_TOOLS)


@requires_probe
def test_script_does_not_use_candidate_expected_value_or_matrix_inputs() -> None:
    module = _require_probe()
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "rook.containment_acceptance" not in imported
    assert ".containment_acceptance" not in imported
    for forbidden in (
        "containment_envelope",
        "lifecycle_manifest",
        "resolve_contained_identity",
        "candidate_matrix",
        "probe_registry",
    ):
        assert forbidden not in source
    assert "164" not in source


@requires_probe
def test_runtime_inputs_is_frozen_small_and_does_not_own_output() -> None:
    module = _require_probe()
    fields = tuple(field.name for field in dataclasses.fields(module.RuntimeInputs))
    assert fields == (
        "expected_release_sha",
        "expected_version",
        "expected_python",
        "expected_venv",
        "expected_package_root",
        "packaged_runtime_manifest",
        "installed_runtime_manifest",
        "install_state",
        "packaged_wheelhouse",
        "forbidden_source_roots",
        "staged_script_path",
    )
    assert module.RuntimeInputs.__dataclass_params__.frozen is True
    assert "output" not in fields


@requires_probe
@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(extra=True),
        lambda value: value.pop("success"),
        lambda value: value.update(success=0),
        lambda value: value.update(data={**value["data"], "extra": 1}),
        lambda value: value["data"].pop("recovery"),
        lambda value: value["data"].update(tool="spawn_agent"),
        lambda value: value["data"].update(disposition="retired"),
        lambda value: value["data"].update(retryable=True),
        lambda value: value["data"].update(verified=True),
        lambda value: value["data"].update(recovery="rediscover"),
    ],
)
def test_denial_validation_rejects_every_payload_mutation(mutation) -> None:
    module = _require_probe()
    value = _denial("plan_and_execute")
    module._validate_denial("plan_and_execute", value)
    mutation(value)
    with pytest.raises(module.ProbeError):
        module._validate_denial("plan_and_execute", value)


@requires_probe
@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-07-19T12:34:56Z",
        "2026-07-19T12:34:56.12345Z",
        "2026-07-19T12:34:56.123456+00:00",
        "2026-13-19T12:34:56.123456Z",
        123,
    ],
)
def test_telemetry_requires_exact_fields_and_real_utc_timestamp(timestamp) -> None:
    module = _require_probe()
    event = _event("spawn_agent", "tool_dispatcher")
    module._validate_event(event, "spawn_agent", "tool_dispatcher")
    event["timestamp"] = timestamp
    with pytest.raises(module.ProbeError):
        module._validate_event(event, "spawn_agent", "tool_dispatcher")


@requires_probe
def test_installed_child_environment_scrubs_case_insensitively() -> None:
    module = _require_probe()
    base = {
        "Path": "C:/Windows",
        "PYTHONPATH": "hostile",
        "pythonhome": "hostile",
        "PyThOnUsErBaSe": "hostile",
        "pythonNOUSERSITE": "0",
        "dspy_model": "hostile",
        "dSpY_CaChEdIr": "hostile",
        "chirp_home": "hostile",
        "rook_mode": "hostile",
        "ROOK_INSTALL_ROOT": "C:/Program Files/Rook",
        "ROOK_DATA_DIR": "C:/Users/test/AppData/Roaming/Rook",
        "DSPY_CACHEDIR": "C:/Users/test/AppData/Roaming/Rook/dspy-cache",
        "CHIRP_HOME": "C:/Program Files/Rook/chirp",
    }
    cleaned = module.build_installed_child_environment(
        base, profile="full", interactive=True
    )
    controlled = {
        key.casefold(): value
        for key, value in cleaned.items()
        if key.casefold().startswith("rook_")
        or key.casefold()
        in {
            "pythonpath",
            "pythonhome",
            "pythonuserbase",
            "pythonnousersite",
            "dspy_model",
            "dspy_cachedir",
            "chirp_home",
        }
    }
    assert controlled == {
        "pythonnousersite": "1",
        "rook_install_root": str(Path(base["ROOK_INSTALL_ROOT"]).resolve()),
        "rook_data_dir": str(Path(base["ROOK_DATA_DIR"]).resolve()),
        "rook_mode": "release",
        "rook_dspy_restrict_pickle": "1",
        "dspy_cachedir": str(Path(base["DSPY_CACHEDIR"]).resolve()),
        "chirp_home": str(Path(base["CHIRP_HOME"]).resolve()),
        "rook_mcp_tool_profile": "full",
        "rook_enable_interactive_command_learning": "1",
    }
    assert cleaned["Path"] == "C:/Windows"


@requires_probe
def test_environment_modes_are_exact_and_unprofiled_is_genuinely_absent() -> None:
    module = _require_probe()
    base = {
        "ROOK_INSTALL_ROOT": "C:/Rook/app",
        "ROOK_DATA_DIR": "C:/Rook/data",
        "DSPY_CACHEDIR": "C:/Rook/data/dspy-cache",
    }
    unprofiled = module.build_installed_child_environment(base)
    assert "ROOK_MCP_TOOL_PROFILE" not in unprofiled
    assert "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING" not in unprofiled
    for profile in PROFILES:
        env = module.build_installed_child_environment(base, profile=profile)
        assert env["ROOK_MCP_TOOL_PROFILE"] == profile
        assert "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING" not in env
    with pytest.raises(module.ProbeError):
        module.build_installed_child_environment(base, interactive=True)
    with pytest.raises(module.ProbeError):
        module.build_installed_child_environment(base, profile="invalid")


def _process(package_root: Path, cwd: Path) -> dict[str, object]:
    return {
        "executable": str(package_root.parents[2] / "Scripts" / "python.exe"),
        "cwd": str(cwd),
        "sys_path": [str(package_root.parent)],
        "rook_origins": {
            "rook": str(package_root / "__init__.py"),
            "rook.server": str(package_root / "server.py"),
        },
        "process_id": PID,
        "process_start_token": TOKEN,
    }


def _startup_refresh() -> dict[str, object]:
    return {
        "status": "degraded_cache",
        "persisted": False,
        "refresh_requested": True,
        "retained_names": ["safe_cached"],
        "cache_bytes_unchanged": True,
        "cache_path_unchanged": True,
        "unlink_calls": 0,
        "rmtree_calls": 0,
        "telemetry_unchanged": True,
        "normal_status": "fresh",
        "normal_catalog_count": 422,
    }


def _discovery_snapshot(surface: str, package_root: Path, cwd: Path) -> dict[str, object]:
    count = DISCOVERY_COUNTS[surface]
    names = [f"safe_{surface}_{index}" for index in range(count)]
    return {
        "surface": surface,
        "process": _process(package_root, cwd),
        "profile_env_present": surface != "unprofiled",
        "interactive_env_present": surface == "interactive-full",
        "catalog_names": names,
        "rook_agent_names": list(names),
        "rook_chat_names": list(names),
        "telemetry_before": {
            "process_id": PID,
            "process_start_token": TOKEN,
            "events": [],
        },
        "telemetry_after": {
            "process_id": PID,
            "process_start_token": TOKEN,
            "events": [],
        },
        "startup_refresh": _startup_refresh() if surface == "unprofiled" else None,
    }


@requires_probe
def test_four_discovery_snapshots_pin_full_name_sets_and_cache_retention(tmp_path: Path) -> None:
    module = _require_probe()
    package_root = tmp_path / "venv" / "Lib" / "site-packages" / "rook"
    snapshots = [
        _discovery_snapshot(surface, package_root, tmp_path / f"cwd-{surface}")
        for surface in DISCOVERY_COUNTS
    ]
    module._validate_discovery_snapshots(snapshots)
    assert snapshots[0]["profile_env_present"] is False
    assert snapshots[0]["startup_refresh"] == _startup_refresh()

    for field in ("catalog_names", "rook_agent_names", "rook_chat_names"):
        mutated = copy.deepcopy(snapshots)
        values = mutated[1][field]
        values[-1] = values[0] + "-wrong-member"
        with pytest.raises(module.ProbeError):
            module._validate_discovery_snapshots(mutated)


@requires_probe
@pytest.mark.parametrize("shape", ["missing", "duplicate", "extra", "reordered"])
def test_discovery_snapshot_collection_rejects_record_shape_drift(tmp_path: Path, shape: str) -> None:
    module = _require_probe()
    root = tmp_path / "venv" / "Lib" / "site-packages" / "rook"
    snapshots = [_discovery_snapshot(name, root, tmp_path / name) for name in DISCOVERY_COUNTS]
    if shape == "missing":
        snapshots.pop()
    elif shape == "duplicate":
        snapshots[-1] = copy.deepcopy(snapshots[0])
    elif shape == "extra":
        snapshots.append(copy.deepcopy(snapshots[-1]))
    else:
        snapshots[0], snapshots[1] = snapshots[1], snapshots[0]
    with pytest.raises(module.ProbeError):
        module._validate_discovery_snapshots(snapshots)


def _transport_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    index = 1
    for profile in PROFILES:
        for ingress in TRANSPORT_INGRESSES:
            origin = "public_mcp" if ingress == "public_mcp" else "progressive_meta"
            for tool in CONTAINED_TOOLS:
                records.append(
                    {
                        "index": index,
                        "profile": profile,
                        "ingress": ingress,
                        "tool": tool,
                        "origin": origin,
                        "denial": _denial(tool),
                        "wire": {
                            "content_count": 1,
                            "content_types": ["text"],
                            "is_error": False,
                            "text": "Error: " + json.dumps(EXPECTED_DENIALS[tool], indent=2),
                        },
                        "process_id": PID,
                        "process_start_token": TOKEN,
                        "telemetry": _telemetry(tool, origin),
                        "downstream": [],
                    }
                )
                index += 1
    return records


@requires_probe
def test_transport_matrix_is_exactly_36_unique_code_owned_tuples() -> None:
    module = _require_probe()
    records = _transport_records()
    module._validate_transport_records(records)
    assert len(records) == 36
    assert len({(r["profile"], r["ingress"], r["tool"]) for r in records}) == 36


@requires_probe
@pytest.mark.parametrize("shape", ["missing", "duplicate", "extra", "reordered", "malformed"])
def test_transport_rejects_missing_duplicate_extra_reordered_or_malformed(shape: str) -> None:
    module = _require_probe()
    records = _transport_records()
    if shape == "missing":
        records.pop()
    elif shape == "duplicate":
        records[-1] = copy.deepcopy(records[0])
    elif shape == "extra":
        records.append(copy.deepcopy(records[-1]))
    elif shape == "reordered":
        records[0], records[1] = records[1], records[0]
    else:
        records[0]["downstream"] = ["http"]
    with pytest.raises(module.ProbeError):
        module._validate_transport_records(records)


def _internal_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for index, (seam, tool, origin, adapter) in enumerate(INTERNAL_ROWS, 1):
        records.append(
            {
                "index": index,
                "seam": seam,
                "tool": tool,
                "origin": origin,
                "result_adapter": adapter,
                "adapter": _adapter_evidence(adapter, tool, index),
                "process_id": PID,
                "process_start_token": TOKEN,
                "telemetry": _telemetry(tool, origin),
                "downstream": [],
                "primary_model_calls": 2 if index in {7, 10} else 0,
                "dormant_model_calls": 0,
            }
        )
    return records


@requires_probe
def test_internal_snapshot_is_exact_ordered_29_and_validates_every_adapter() -> None:
    module = _require_probe()
    records = _internal_records()
    module._validate_internal_records(records)
    assert len(records) == 29
    assert [record["seam"] for record in records] == [row[0] for row in INTERNAL_ROWS]
    assert [record["primary_model_calls"] for record in records].count(2) == 2
    assert all(record["dormant_model_calls"] == 0 for record in records)


@requires_probe
@pytest.mark.parametrize("row_index", range(29))
def test_each_internal_adapter_rejects_correct_inner_denial_in_wrong_outer_type(row_index: int) -> None:
    module = _require_probe()
    records = _internal_records()
    records[row_index]["adapter"]["outer_type"] = "wrong.OuterType"
    with pytest.raises(module.ProbeError):
        module._validate_internal_records(records)


@requires_probe
@pytest.mark.parametrize("shape", ["missing", "duplicate", "extra", "reordered", "malformed"])
def test_internal_rejects_missing_duplicate_extra_reordered_or_malformed(shape: str) -> None:
    module = _require_probe()
    records = _internal_records()
    if shape == "missing":
        records.pop()
    elif shape == "duplicate":
        records[-1] = copy.deepcopy(records[0])
    elif shape == "extra":
        records.append(copy.deepcopy(records[-1]))
    elif shape == "reordered":
        records[0], records[1] = records[1], records[0]
    else:
        records[6]["adapter"]["history"].pop()
    with pytest.raises(module.ProbeError):
        module._validate_internal_records(records)


@requires_probe
def test_adjacent_telemetry_same_identity_and_zero_downstream_are_required() -> None:
    module = _require_probe()
    for factory, validator in (
        (_transport_records, module._validate_transport_records),
        (_internal_records, module._validate_internal_records),
    ):
        for field, wrong in (
            ("process_id", PID + 1),
            ("process_start_token", "f" * 32),
            ("telemetry", _telemetry("spawn_agent", "wrong")),
            ("downstream", ["host"]),
            ("dormant_model_calls", 1),
        ):
            records = factory()
            if field not in records[0]:
                continue
            records[0][field] = wrong
            with pytest.raises(module.ProbeError):
                validator(records)


@requires_probe
def test_cli_is_closed_to_pinned_public_and_private_protocols(tmp_path: Path) -> None:
    module = _require_probe()
    parser = module._build_parser()
    actions = parser._subparsers._group_actions[0].choices
    assert set(actions) == {
        "run",
        "_child-discovery",
        "_child-transport",
        "_child-internal",
    }
    public_options = {
        option
        for action in actions["run"]._actions
        for option in action.option_strings
    }
    assert public_options == {
        "-h",
        "--help",
        "--expected-release-sha",
        "--expected-version",
        "--expected-python",
        "--expected-venv",
        "--expected-package-root",
        "--packaged-runtime-manifest",
        "--installed-runtime-manifest",
        "--install-state",
        "--packaged-wheelhouse",
        "--forbidden-source-root",
        "--output",
    }
    for forbidden in ("--matrix", "--seam", "--tool", "--origin", "--result-adapter"):
        with pytest.raises(SystemExit):
            parser.parse_args(["_child-internal", "--probe-index", "1", "--output", str(tmp_path / "x.json"), forbidden, "x"])


@requires_probe
def test_source_uses_real_mcp_process_boundary_and_inert_http_construction() -> None:
    module = _require_probe()
    source = Path(module.__file__).read_text(encoding="utf-8")
    for required in (
        "mcp.client.stdio",
        "stdio_client",
        "ClientSession",
        "mcp.server.stdio",
        "stdio_server",
        "request_handlers",
        "call_tool",
        "httpx.AsyncClient",
        "urllib.request.urlopen",
        "http://127.0.0.1:9",
        "refresh_catalog_at_startup",
        "_all_live_tools",
    ):
        assert required in source
    assert "_child-transport" in source
    assert "_child-internal" in source
    assert "subprocess.Popen" in source


def _record_digest(data: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def _runtime_fixture(tmp_path: Path):
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    wheel = wheelhouse / "rook_mcp-1.2.3-py3-none-any.whl"
    package_root = tmp_path / "venv" / "Lib" / "site-packages" / "rook"
    package_root.mkdir(parents=True)
    init_bytes = b'__version__ = "1.2.3"\n'
    server_bytes = b"VALUE = 1\n"
    (package_root / "__init__.py").write_bytes(init_bytes)
    (package_root / "server.py").write_bytes(server_bytes)
    record_path = "rook_mcp-1.2.3.dist-info/RECORD"
    record_text = (
        f"rook/__init__.py,sha256={_record_digest(init_bytes)},{len(init_bytes)}\n"
        f"rook/server.py,sha256={_record_digest(server_bytes)},{len(server_bytes)}\n"
        f"{record_path},,\n"
    ).encode()
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("rook/__init__.py", init_bytes)
        archive.writestr("rook/server.py", server_bytes)
        archive.writestr(record_path, record_text)
    wheel_sha = hashlib.sha256(wheel.read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1,
        "release_version": "1.2.3",
        "rook_git_sha": "a" * 40,
        "wheelhouse": {
            "path": "installer/runtime/python-wheelhouse",
            "accepted_tag_sample": ["py3-none-any"],
            "wheels": [
                {
                    "file": wheel.name,
                    "project": "rook-mcp",
                    "version": "1.2.3",
                    "sha256": wheel_sha.upper(),
                    "tags": ["py3-none-any"],
                }
            ],
        },
    }
    packaged_manifest = tmp_path / "packaged-manifest.json"
    installed_manifest = tmp_path / "installed-manifest.json"
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode()
    packaged_manifest.write_bytes(manifest_bytes)
    installed_manifest.write_bytes(manifest_bytes)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    expected_venv = tmp_path / "venv"
    expected_python = expected_venv / "Scripts" / "python.exe"
    expected_python.parent.mkdir()
    expected_python.write_bytes(b"synthetic-python")
    state = {
        "schema_version": 1,
        "python": {
            "path": str(tmp_path / "private-python.exe"),
            "version": "3.11.9",
            "identity_hash": manifest_sha,
            "runtime_manifest_path": str(installed_manifest),
            "runtime_manifest_sha256": manifest_sha,
        },
        "rook": {
            "venv_path": str(expected_venv),
            "python_path": str(expected_python),
            "python_identity_hash": manifest_sha,
            "lockfile_path": str(tmp_path / "rook.lock"),
            "lockfile_sha256": "b" * 64,
            "installed_utc": "2026-07-19T12:34:56Z",
            "pip_check": "No broken requirements found.",
        },
    }
    install_state = tmp_path / "install-state.json"
    install_state.write_text(json.dumps(state), encoding="utf-8")
    script = tmp_path / "installed_probe.py"
    script.write_text("# staged\n", encoding="utf-8")
    module = _require_probe()
    inputs = module.RuntimeInputs(
        expected_release_sha="a" * 40,
        expected_version="1.2.3",
        expected_python=expected_python,
        expected_venv=expected_venv,
        expected_package_root=package_root,
        packaged_runtime_manifest=packaged_manifest,
        installed_runtime_manifest=installed_manifest,
        install_state=install_state,
        packaged_wheelhouse=wheelhouse,
        forbidden_source_roots=(tmp_path / "checkout",),
        staged_script_path=script,
    )
    return inputs, wheel, package_root


@requires_probe
def test_runtime_validation_pins_manifests_state_wheels_record_and_installed_files(tmp_path: Path) -> None:
    module = _require_probe()
    inputs, _wheel, _root = _runtime_fixture(tmp_path)
    evidence = module.validate_installed_runtime(inputs)
    assert set(evidence) == {
        "release_sha",
        "version",
        "python",
        "venv",
        "package_root",
        "runtime_manifest_sha256",
        "wheel_hashes",
        "rook_record_files",
    }
    assert evidence["release_sha"] == "a" * 40
    assert evidence["wheel_hashes"] == {"rook_mcp-1.2.3-py3-none-any.whl": hashlib.sha256((inputs.packaged_wheelhouse / "rook_mcp-1.2.3-py3-none-any.whl").read_bytes()).hexdigest()}
    assert evidence["rook_record_files"] == ["rook/__init__.py", "rook/server.py"]


@requires_probe
@pytest.mark.parametrize("mutation", ["manifest", "state", "wheel", "record", "installed"])
def test_runtime_validation_rejects_each_identity_mutation(tmp_path: Path, mutation: str) -> None:
    module = _require_probe()
    inputs, wheel, package_root = _runtime_fixture(tmp_path)
    if mutation == "manifest":
        inputs.installed_runtime_manifest.write_bytes(b"{}\n")
    elif mutation == "state":
        state = json.loads(inputs.install_state.read_text(encoding="utf-8"))
        state["python"]["identity_hash"] = "0" * 64
        inputs.install_state.write_text(json.dumps(state), encoding="utf-8")
    elif mutation == "wheel":
        wheel.write_bytes(wheel.read_bytes() + b"drift")
    elif mutation == "record":
        with pytest.warns(UserWarning, match="Duplicate name"):
            with zipfile.ZipFile(wheel, "a") as archive:
                archive.writestr("rook_mcp-1.2.3.dist-info/RECORD", "rook/server.py,sha256=bad,1\n")
        manifest = json.loads(inputs.packaged_runtime_manifest.read_text(encoding="utf-8"))
        manifest["wheelhouse"]["wheels"][0]["sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest().upper()
        data = (json.dumps(manifest, indent=2) + "\n").encode()
        inputs.packaged_runtime_manifest.write_bytes(data)
        inputs.installed_runtime_manifest.write_bytes(data)
        state = json.loads(inputs.install_state.read_text(encoding="utf-8"))
        digest = hashlib.sha256(data).hexdigest()
        state["python"]["identity_hash"] = digest
        state["python"]["runtime_manifest_sha256"] = digest
        state["rook"]["python_identity_hash"] = digest
        inputs.install_state.write_text(json.dumps(state), encoding="utf-8")
    else:
        (package_root / "server.py").write_bytes(b"VALUE = 2\n")
    with pytest.raises(module.ProbeError):
        module.validate_installed_runtime(inputs)


@requires_probe
def test_process_validation_rejects_source_paths_and_foreign_origins(tmp_path: Path) -> None:
    module = _require_probe()
    inputs, _wheel, package_root = _runtime_fixture(tmp_path)
    process = _process(package_root, tmp_path / "fresh-cwd")
    process["executable"] = str(inputs.expected_python)
    module._validate_process_evidence(process, inputs, allowed_roots=(tmp_path,))
    checkout = inputs.forbidden_source_roots[0]
    checkout.mkdir()
    process["sys_path"].append(str(checkout))
    with pytest.raises(module.ProbeError):
        module._validate_process_evidence(process, inputs, allowed_roots=(tmp_path,))
    process = _process(package_root, tmp_path / "fresh-cwd")
    process["executable"] = str(inputs.expected_python)
    process["rook_origins"]["rook.server"] = str(tmp_path / "foreign" / "server.py")
    with pytest.raises(module.ProbeError):
        module._validate_process_evidence(process, inputs, allowed_roots=(tmp_path,))


@requires_probe
def test_run_all_writes_one_atomic_canonical_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _require_probe()
    inputs, _wheel, package_root = _runtime_fixture(tmp_path)
    discoveries = [_discovery_snapshot(name, package_root, tmp_path / name) for name in DISCOVERY_COUNTS]
    monkeypatch.setattr(module, "run_discovery_snapshots", lambda _inputs: discoveries)
    monkeypatch.setattr(module, "run_transport_probes", lambda _inputs: _transport_records())
    monkeypatch.setattr(module, "run_internal_probes", lambda _inputs: _internal_records())
    output = tmp_path / "result.json"
    result = module.run_all(inputs, output)
    assert set(result) == {"schema_version", "success", "runtime", "discovery", "transport", "internal"}
    assert result["success"] is True
    assert json.loads(output.read_text(encoding="utf-8")) == result
    assert output.read_bytes().endswith(b"\n")
    assert not list(tmp_path.glob(f".{output.name}.*.tmp"))


@requires_probe
def test_failed_or_preexisting_output_can_never_leave_a_passing_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _require_probe()
    inputs, _wheel, _root = _runtime_fixture(tmp_path)
    output = tmp_path / "result.json"
    monkeypatch.setattr(module, "run_discovery_snapshots", lambda _inputs: (_ for _ in ()).throw(module.ProbeError("failed")))
    with pytest.raises(module.ProbeError):
        module.run_all(inputs, output)
    assert not output.exists()
    output.write_text('{"success":true}\n', encoding="utf-8")
    before = output.read_bytes()
    with pytest.raises(module.ProbeError):
        module.run_all(inputs, output)
    assert output.read_bytes() == before


@requires_probe
def test_public_interfaces_exist_with_output_owned_only_by_run_all() -> None:
    module = _require_probe()
    for name in (
        "build_installed_child_environment",
        "validate_installed_runtime",
        "run_discovery_snapshots",
        "run_transport_probes",
        "run_internal_probes",
        "run_all",
        "main",
    ):
        assert callable(getattr(module, name))
    assert tuple(module.run_all.__annotations__) == ("inputs", "output_path", "return")


@requires_probe
def test_internal_model_counts_are_observed_not_synthetic_literals() -> None:
    module = _require_probe()
    preparation_source = inspect.getsource(module._prepare_internal_probe)
    child_source = inspect.getsource(module._internal_child)
    assert "lambda: 0" not in preparation_source
    assert '"dormant_model_calls": 0' not in child_source
    assert "spies.entries" in child_source


@requires_probe
def test_direct_child_artifact_pid_must_match_launched_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _require_probe()
    inputs = module.RuntimeInputs(
        expected_release_sha="a" * 40,
        expected_version="1.2.3",
        expected_python=tmp_path / "venv" / "Scripts" / "python.exe",
        expected_venv=tmp_path / "venv",
        expected_package_root=tmp_path / "venv" / "Lib" / "site-packages" / "rook",
        packaged_runtime_manifest=tmp_path / "packaged.json",
        installed_runtime_manifest=tmp_path / "installed.json",
        install_state=tmp_path / "state.json",
        packaged_wheelhouse=tmp_path / "wheelhouse",
        forbidden_source_roots=(tmp_path / "checkout",),
        staged_script_path=tmp_path / "installed_probe.py",
    )

    def write_foreign_artifact(command: list[str]) -> None:
        output = Path(command[command.index("--output") + 1])
        output.write_text(
            json.dumps({"process": {"process_id": PID + 1}}),
            encoding="utf-8",
        )

    def fake_run(command: list[str], **_kwargs):
        write_foreign_artifact(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    class FakePopen:
        pid = PID

        def __init__(self, command: list[str], **_kwargs) -> None:
            self.command = command
            self.returncode = 0

        def communicate(self, timeout: int | None = None):
            assert timeout == 900
            write_foreign_artifact(self.command)
            return "", ""

        def kill(self) -> None:
            self.returncode = -9

    monkeypatch.setattr(module, "build_installed_child_environment", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(module, "_validate_process_evidence", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module.subprocess, "Popen", FakePopen)

    with pytest.raises(module.ProbeError, match="launched child PID"):
        module._run_subprocess_child(
            inputs,
            label="pid-binding",
            arguments=["_child-internal", "--probe-index", "1"],
            profile=None,
        )


@requires_probe
def test_internal_record_pid_must_match_validated_child_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _require_probe()
    records = _internal_records()
    package_root = tmp_path / "venv" / "Lib" / "site-packages" / "rook"
    process = _process(package_root, tmp_path / "child-cwd")

    def fake_child(_inputs, *, arguments, **_kwargs):
        index = int(arguments[-1])
        record = copy.deepcopy(records[index - 1])
        record["process_id"] = PID + 1
        record["telemetry"]["process_id"] = PID + 1
        return {
            "mode": "internal",
            "process": copy.deepcopy(process),
            "record": record,
        }, tmp_path

    monkeypatch.setattr(module, "_run_subprocess_child", fake_child)
    inputs = SimpleNamespace()
    with pytest.raises(module.ProbeError, match="process PID"):
        module.run_internal_probes(inputs)
