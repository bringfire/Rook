from __future__ import annotations

import ast
import asyncio
import importlib.util
import inspect
import json
from pathlib import Path

import pytest


def _load_smoke_module():
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "mcp_server" / "tools" / "gh_solve_readiness_live_smoke.py"
    spec = importlib.util.spec_from_file_location("gh_solve_readiness_live_smoke", script)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


SMOKE = _load_smoke_module()


class FakeToolExecutor:
    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = dict(responses)
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def __call__(self, tool_name: str, args: dict[str, object]) -> object:
        self.calls.append((tool_name, dict(args)))
        response = self.responses[tool_name]
        if isinstance(response, list):
            response = response.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def calls_after(self, tool_name: str) -> list[tuple[str, dict[str, object]]]:
        index = next(index for index, call in enumerate(self.calls) if call[0] == tool_name)
        return self.calls[index + 1 :]


def _run(coro):
    return asyncio.run(coro)


def _receipt(status: str = "ready") -> dict[str, object]:
    return {
        "schema": "rook.gh_solve_readiness_receipt:v1",
        "receipt_id": "opaque-1",
        "document_session_id": "session-1",
        "mutation_epoch": 4,
        "solution_run_epoch": 9,
        "completed_solution_run_epoch": 9,
        "status": status,
    }


def _flat_provenance(receipt: dict[str, object] | None = None) -> dict[str, object]:
    receipt = receipt or _receipt()
    return {
        "readiness_fenced": True,
        "readiness_receipt_id": receipt["receipt_id"],
        "document_session_id": receipt["document_session_id"],
        "mutation_epoch": receipt["mutation_epoch"],
        "completed_solution_epoch": receipt["completed_solution_run_epoch"],
    }


_UNSET = object()


def _responses(
    *, set_receipt: object = _UNSET, wait: object = _UNSET, inspect: object = _UNSET, preview: object = 7.5
):
    if set_receipt is _UNSET:
        set_receipt = _receipt("pending")
    if wait is _UNSET:
        wait = {"success": True, "data": {"wait_status": "ready", "receipt": _receipt()}}
    if inspect is _UNSET:
        inspect = {
            "success": True,
            "data": {
                "param_nickname": "R",
                "data_count": 1,
                "preview": [preview],
                **_flat_provenance(),
            },
        }
    return {
        "rhino_ping": "pong",
        "gh_document_new": {"success": True, "data": {"Created": True}},
        "gh_library": {
            "success": True,
            "components": [{"name": "Addition", "guid": "ADDITION-PROXY-GUID"}],
        },
        "gh_create_slider": [
            {"success": True, "data": {"Created": True, "Guid": "EDITABLE-GUID"}},
            {"success": True, "data": {"Created": True, "Guid": "OFFSET-GUID"}},
        ],
        "gh_create_component": {"success": True, "data": {"Created": True, "Guid": "ADDITION-GUID"}},
        "gh_connect": [
            {"success": True, "data": {"connected": True}},
            {"success": True, "data": {"connected": True}},
        ],
        "gh_set_value": {
            "success": True,
            "data": {"Guid": "EDITABLE-GUID", "NewValue": 7.5, "solve_readiness_receipt": set_receipt},
        },
        "gh_wait_for_solve_readiness": wait,
        "gh_inspect_output": inspect,
    }


def test_smoke_claim_begins_at_receipted_set_value(tmp_path: Path) -> None:
    fake_executor = FakeToolExecutor(_responses())

    result = _run(SMOKE.run_smoke(fake_executor, run_dir=tmp_path))

    assert result["decision"]["accepted"] is True
    assert result["decision"]["baseline_setup_only"] is True
    assert result["decision"]["readiness_fenced"] is True
    assert result["decision"]["observed_output_value"] == 7.5
    assert ("gh_wait_for_solve_readiness", {"readiness_receipt_id": "opaque-1", "timeout_ms": 10_000}) in fake_executor.calls
    assert all(tool != "gh_solve" for tool, _ in fake_executor.calls_after("gh_set_value"))
    assert [tool for tool, _ in fake_executor.calls_after("gh_set_value")] == [
        "gh_wait_for_solve_readiness",
        "gh_inspect_output",
    ]
    assert fake_executor.calls[-1] == (
        "gh_inspect_output",
        {"guid": "ADDITION-GUID", "param": "R", "readiness_receipt_id": "opaque-1"},
    )
    assert {path.name for path in tmp_path.iterdir()} == {
        "manifest.json",
        "baseline_setup_summary.json",
        "mutation_receipt.json",
        "wait_result.json",
        "fenced_output_summary.json",
        "decision.json",
    }
    assert json.loads((tmp_path / "decision.json").read_text(encoding="utf-8")) == result["decision"]


def test_smoke_rejects_missing_set_value_receipt(tmp_path: Path) -> None:
    fake_executor = FakeToolExecutor(_responses(set_receipt=None))

    with pytest.raises(SMOKE.SmokeFailure, match="solve_readiness_receipt_missing"):
        _run(SMOKE.run_smoke(fake_executor, run_dir=tmp_path))

    assert [tool for tool, _ in fake_executor.calls_after("gh_set_value")] == []


@pytest.mark.parametrize(
    "receipt",
    [
        {**_receipt("pending"), "schema": "rook.gh_solve_readiness_receipt:v0"},
        _receipt("ready"),
    ],
    ids=["unexpected_schema", "non_pending_status"],
)
def test_smoke_rejects_invalid_set_value_receipt_before_wait(
    tmp_path: Path, receipt: dict[str, object]
) -> None:
    fake_executor = FakeToolExecutor(_responses(set_receipt=receipt))

    with pytest.raises(SMOKE.SmokeFailure, match="solve_readiness_receipt_invalid"):
        _run(SMOKE.run_smoke(fake_executor, run_dir=tmp_path))

    assert [tool for tool, _ in fake_executor.calls_after("gh_set_value")] == []


def test_smoke_rejects_wait_timeout(tmp_path: Path) -> None:
    fake_executor = FakeToolExecutor(
        _responses(wait={"success": True, "data": {"wait_status": "timeout", "receipt": _receipt("pending")}})
    )

    with pytest.raises(SMOKE.SmokeFailure, match="solve_readiness_wait_not_ready"):
        _run(SMOKE.run_smoke(fake_executor, run_dir=tmp_path))

    assert [tool for tool, _ in fake_executor.calls_after("gh_set_value")] == ["gh_wait_for_solve_readiness"]


def test_smoke_rejects_terminal_wait_outcome(tmp_path: Path) -> None:
    fake_executor = FakeToolExecutor(
        _responses(wait={"success": True, "data": {"wait_status": "terminal", "receipt": _receipt("superseded")}})
    )

    with pytest.raises(SMOKE.SmokeFailure, match="solve_readiness_wait_not_ready"):
        _run(SMOKE.run_smoke(fake_executor, run_dir=tmp_path))

    assert [tool for tool, _ in fake_executor.calls_after("gh_set_value")] == ["gh_wait_for_solve_readiness"]


def test_smoke_rejects_wait_receipt_with_unexpected_schema(tmp_path: Path) -> None:
    wait_receipt = _receipt()
    wait_receipt["schema"] = "rook.gh_solve_readiness_receipt:v0"
    fake_executor = FakeToolExecutor(
        _responses(wait={"success": True, "data": {"wait_status": "ready", "receipt": wait_receipt}})
    )

    with pytest.raises(SMOKE.SmokeFailure, match="solve_readiness_wait_not_ready"):
        _run(SMOKE.run_smoke(fake_executor, run_dir=tmp_path))

    assert [tool for tool, _ in fake_executor.calls_after("gh_set_value")] == ["gh_wait_for_solve_readiness"]


def test_smoke_rejects_fenced_read_failure(tmp_path: Path) -> None:
    fake_executor = FakeToolExecutor(
        _responses(inspect={"success": False, "data": {"error": "readiness_receipt_stale_solution_run"}})
    )

    with pytest.raises(SMOKE.SmokeFailure, match="fenced_output_read_failed"):
        _run(SMOKE.run_smoke(fake_executor, run_dir=tmp_path))

    assert [tool for tool, _ in fake_executor.calls_after("gh_set_value")] == [
        "gh_wait_for_solve_readiness",
        "gh_inspect_output",
    ]


def test_smoke_rejects_mismatched_output_provenance(tmp_path: Path) -> None:
    mismatched_provenance = _flat_provenance()
    mismatched_provenance["mutation_epoch"] = 5
    fake_executor = FakeToolExecutor(
        _responses(
            inspect={
                "success": True,
                "data": {
                    "param_nickname": "R",
                    "data_count": 1,
                    "preview": [7.5],
                    **mismatched_provenance,
                },
            }
        )
    )

    with pytest.raises(SMOKE.SmokeFailure, match="fenced_output_provenance_mismatch"):
        _run(SMOKE.run_smoke(fake_executor, run_dir=tmp_path))


def test_smoke_rejects_unfenced_output_provenance(tmp_path: Path) -> None:
    unfenced_provenance = _flat_provenance()
    unfenced_provenance["readiness_fenced"] = False
    fake_executor = FakeToolExecutor(
        _responses(
            inspect={
                "success": True,
                "data": {
                    "param_nickname": "R",
                    "data_count": 1,
                    "preview": [7.5],
                    **unfenced_provenance,
                },
            }
        )
    )

    with pytest.raises(SMOKE.SmokeFailure, match="fenced_output_provenance_mismatch"):
        _run(SMOKE.run_smoke(fake_executor, run_dir=tmp_path))

    assert [tool for tool, _ in fake_executor.calls_after("gh_set_value")] == [
        "gh_wait_for_solve_readiness",
        "gh_inspect_output",
    ]


def test_smoke_accepts_finite_numeric_string_output_preview(tmp_path: Path) -> None:
    fake_executor = FakeToolExecutor(_responses(preview="7.5"))

    result = _run(SMOKE.run_smoke(fake_executor, run_dir=tmp_path))

    assert result["decision"]["observed_output_value"] == 7.5


@pytest.mark.parametrize("value", ["not-a-number", "nan", "inf", float("nan"), float("inf")])
def test_smoke_rejects_nonfinite_or_nonnumeric_output_preview(value: object) -> None:
    with pytest.raises(SMOKE.SmokeFailure, match="fenced_output_value_invalid"):
        SMOKE._observed_output_value({"data": {"preview": [value]}})


def test_harness_source_has_no_sleep_or_post_mutation_output_polling() -> None:
    source = inspect.getsource(SMOKE)
    tree = ast.parse(source)

    assert "asyncio.sleep" not in source
    assert sum(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "sleep"
        for node in ast.walk(tree)
    ) == 0
    assert sum(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_call_tool"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == "gh_inspect_output"
        for node in ast.walk(tree)
    ) == 1
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    inspect_call = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_call_tool"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == "gh_inspect_output"
    )
    parent = parents.get(inspect_call)
    while parent is not None:
        assert not isinstance(parent, (ast.For, ast.While))
        parent = parents.get(parent)
