"""Unit tests for script solve-readiness propagation (no Rhino needed)."""

from __future__ import annotations

import pytest

from rook import server


def _receipt(
    status: str = "pending",
    *,
    receipt_id: str = "receipt-1",
    solution_run_epoch: int | None = None,
    completed_solution_run_epoch: int = 7,
) -> dict[str, object]:
    return {
        "schema": "rook.gh_solve_readiness_receipt:v1",
        "receipt_id": receipt_id,
        "document_session_id": "session-1",
        "mutation_epoch": 8,
        "solution_run_epoch": solution_run_epoch,
        "completed_solution_run_epoch": completed_solution_run_epoch,
        "status": status,
        "reason": None,
        "completion_signal": "solution_end" if status == "ready" else None,
        "issued_at": "2026-08-12T12:00:00+00:00",
        "completed_at": "2026-08-12T12:00:01+00:00" if status == "ready" else None,
    }


def _ready_wait(receipt_id: str = "receipt-1") -> dict[str, object]:
    return {
        "success": True,
        "data": {
            "schema": "rook.gh_solve_readiness_wait_result:v1",
            "wait_status": "ready",
            "receipt": _receipt(
                "ready",
                receipt_id=receipt_id,
                solution_run_epoch=9,
                completed_solution_run_epoch=9,
            ),
        },
    }


def test_accepted_schedule_is_verified_even_when_completion_was_unverified_at_write_time():
    from rook.server import _gh_update_script_should_defer

    deferred, flags = _gh_update_script_should_defer(
        {
            "schedule_classification": "rir_mediated_schedule_requested",
            "schedule_acceptance": "accepted",
            "schedule_failure_code": None,
            "solve_scheduled": True,
            "verification_deferred": True,
            "solver_locked": True,
            "solver_state_known": True,
        }
    )

    assert deferred is False
    assert flags == {
        "schedule_classification": "rir_mediated_schedule_requested",
        "schedule_acceptance": "accepted",
        "schedule_failure_code": None,
        "verification_deferred": True,
        "solver_locked": True,
        "solver_state_known": True,
        "solve_scheduled": True,
    }


def test_unknown_schedule_acceptance_remains_deferred_without_retry():
    from rook.server import _gh_update_script_should_defer

    deferred, flags = _gh_update_script_should_defer(
        {
            "schedule_classification": "async_schedule_requested",
            "schedule_acceptance": "unknown",
            "schedule_failure_code": "schedule_acceptance_unknown",
            "solve_scheduled": False,
            "verification_deferred": True,
        }
    )

    assert deferred is True
    assert flags["schedule_failure_code"] == "schedule_acceptance_unknown"


def test_conclusively_unaccepted_schedule_remains_deferred():
    from rook.server import _gh_update_script_should_defer

    for acceptance in ("not_attempted", "unavailable"):
        deferred, _ = _gh_update_script_should_defer(
            {
                "schedule_acceptance": acceptance,
                "verification_deferred": True,
            }
        )
        assert deferred is True


def test_defer_true_when_solver_locked():
    from rook.server import _gh_update_script_should_defer

    deferred, flags = _gh_update_script_should_defer(
        {"verification_deferred": True, "solver_locked": True, "solver_state_known": True}
    )
    assert deferred is True
    assert flags["solver_locked"] is True


def test_defer_false_when_enabled_and_scheduled():
    from rook.server import _gh_update_script_should_defer

    deferred, flags = _gh_update_script_should_defer(
        {"verification_deferred": False, "solver_locked": False, "solver_state_known": True, "solve_scheduled": True}
    )
    assert deferred is False


def test_defer_handles_missing_flags():
    from rook.server import _gh_update_script_should_defer

    deferred, flags = _gh_update_script_should_defer({})
    assert deferred is False
    assert flags == {}


def test_script_pipeline_incomplete_has_one_closed_monotonic_shape():
    receipt = _receipt()
    script_receipt = {"schema": "rook.gh_script_receipt:v1"}

    result = server._script_pipeline_incomplete(
        "post_write_verification",
        component_created=True,
        pins_configured=True,
        component_guid="component-guid",
        component_short_id=None,
        final_write_dispatched=True,
        final_write_success=True,
        solve_relevant_mutation_committed=True,
        solve_readiness_receipt=receipt,
        script_receipt=script_receipt,
    )

    assert result == {
        "success": False,
        "data": {
            "error": "script_pipeline_incomplete",
            "phase": "post_write_verification",
            "committed_preparatory": {
                "component_created": True,
                "pins_configured": True,
            },
            "component": {"guid": "component-guid", "short_id": None},
            "final_write": {
                "dispatched": True,
                "success": True,
                "solve_relevant_mutation_committed": True,
            },
            "solve_readiness_receipt": receipt,
            "script_receipt": script_receipt,
        },
    }
    assert result["data"]["solve_readiness_receipt"] is receipt
    assert result["data"]["script_receipt"] is script_receipt


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.pop("receipt_id"),
        lambda value: value.__setitem__("mutation_epoch", True),
        lambda value: value.__setitem__("solution_run_epoch", "9"),
        lambda value: value.__setitem__("status", "invented"),
        lambda value: value.update({
            "status": "ready",
            "solution_run_epoch": None,
            "completion_signal": "solution_end",
            "completed_at": "2026-08-12T12:00:01+00:00",
        }),
        lambda value: value.__setitem__("extra", 1),
    ],
)
def test_solve_readiness_receipt_validation_is_closed_and_preserves_identity(mutation):
    receipt = _receipt()
    assert server._validated_solve_readiness_receipt(receipt) is receipt

    malformed = _receipt()
    mutation(malformed)
    assert server._validated_solve_readiness_receipt(malformed) is None


@pytest.mark.asyncio
async def test_create_script_waits_on_exact_final_receipt_without_sleep(monkeypatch):
    pending = _receipt()
    calls: list[tuple[str, str, object]] = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None, timeout=None):
        calls.append((route, method, payload))
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": "component-guid"}}
        if route == "/gh/script-params":
            return {"success": True, "data": {"guid": "component-guid"}}
        if route == "/gh/script":
            return {
                "success": True,
                "data": {
                    "guid": "component-guid",
                    "solve_relevant_mutation_committed": True,
                    "solve_readiness_receipt": pending,
                },
            }
        if route == "/gh/wait-for-solve-readiness":
            return _ready_wait()
        if route == "/gh/errors":
            return {"success": True, "data": {"errors": [], "warnings": []}}
        raise AssertionError(f"unexpected route: {route}")

    async def forbidden_sleep(*args, **kwargs):
        raise AssertionError("fixed sleep used as readiness evidence")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server.asyncio, "sleep", forbidden_sleep)

    result = await server._execute_gh_create_script(
        "python",
        {"code": "A = 1", "pins_in": [], "pins_out": ["A:int"]},
        6011,
    )

    assert result["success"] is True
    data = result["data"]
    assert data["solve_relevant_mutation_committed"] is True
    assert data["solve_readiness_receipt"] is pending
    assert data["script_receipt"] is not pending
    assert "solve_readiness_receipt" not in data["script_receipt"]
    assert [route for route, _, _ in calls] == [
        "/gh/create-component",
        "/gh/script-params",
        "/gh/script",
        "/gh/wait-for-solve-readiness",
        "/gh/errors",
    ]
    assert calls[3][2] == {"readiness_receipt_id": "receipt-1", "timeout_ms": 10_000}
    assert sum(route == "/gh/script" for route, _, _ in calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("write_success", "commit_value", "receipt_value", "expected_phase"),
    [
        (True, None, None, "source_write"),
        (True, False, _receipt(), "source_write"),
        (False, True, _receipt(), "source_write"),
        (True, True, None, "solve_readiness"),
        (True, True, {**_receipt(), "schema": "wrong"}, "solve_readiness"),
    ],
)
async def test_create_script_final_write_failures_are_monotonic_and_never_wait(
    monkeypatch,
    write_success,
    commit_value,
    receipt_value,
    expected_phase,
):
    calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None, **kwargs):
        calls.append(route)
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": "component-guid"}}
        if route == "/gh/script-params":
            return {"success": True, "data": {}}
        if route == "/gh/script":
            data = {}
            if commit_value is not None:
                data["solve_relevant_mutation_committed"] = commit_value
            if receipt_value is not None:
                data["solve_readiness_receipt"] = receipt_value
            return {"success": write_success, "data": data}
        raise AssertionError("post-write contact is forbidden")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    result = await server._execute_gh_create_script(
        "python",
        {"code": "A = 1", "pins_in": [], "pins_out": ["A:int"]},
        6011,
    )

    assert result["success"] is False
    data = result["data"]
    assert data["error"] == "script_pipeline_incomplete"
    assert data["phase"] == expected_phase
    assert data["committed_preparatory"] == {
        "component_created": True,
        "pins_configured": True,
    }
    assert data["final_write"]["dispatched"] is True
    assert data["final_write"]["success"] is write_success
    assert data["final_write"]["solve_relevant_mutation_committed"] is commit_value
    assert data["solve_readiness_receipt"] is receipt_value
    assert calls == ["/gh/create-component", "/gh/script-params", "/gh/script"]


@pytest.mark.asyncio
async def test_create_script_final_write_exception_retains_preparatory_facts(monkeypatch):
    calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None, **kwargs):
        calls.append(route)
        if route == "/gh/create-component":
            return {"success": True, "data": {
                "guid": "component-guid",
                "short_id": "C7",
            }}
        if route == "/gh/script-params":
            return {"success": True, "data": {}}
        if route == "/gh/script":
            raise RuntimeError("transport closed")
        raise AssertionError("unexpected contact")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    result = await server._execute_gh_create_script(
        "python",
        {"code": "A = 1", "pins_in": [], "pins_out": ["A:int"]},
        6011,
    )

    assert result == server._script_pipeline_incomplete(
        "source_write",
        component_created=True,
        pins_configured=True,
        component_guid="component-guid",
        component_short_id="C7",
        final_write_dispatched=True,
        final_write_success=None,
        solve_relevant_mutation_committed=None,
        solve_readiness_receipt=None,
        script_receipt=None,
    )
    assert calls == ["/gh/create-component", "/gh/script-params", "/gh/script"]


@pytest.mark.asyncio
async def test_create_script_malformed_success_retains_known_creation_commit(monkeypatch):
    async def fake_call_rhino(route, method="GET", payload=None, port=None, **kwargs):
        assert route == "/gh/create-component"
        return {"success": True, "data": "missing component identity"}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    result = await server._execute_gh_create_script(
        "python",
        {"code": "A = 1", "pins_in": [], "pins_out": ["A:int"]},
        6011,
    )

    assert result["data"]["phase"] == "component_creation"
    assert result["data"]["committed_preparatory"] == {
        "component_created": True,
        "pins_configured": False,
    }
    assert result["data"]["component"] == {"guid": None, "short_id": None}


@pytest.mark.asyncio
@pytest.mark.parametrize("wait_result", [
    {"success": True, "data": {"schema": "rook.gh_solve_readiness_wait_result:v1", "wait_status": "timeout", "receipt": _receipt()}},
    {"success": True, "data": {"schema": "rook.gh_solve_readiness_wait_result:v1", "wait_status": "terminal", "receipt": _receipt("solver_locked")}},
    {"success": False, "data": {"error": "readiness_receipt_unknown"}},
])
async def test_create_script_wait_refusal_retains_final_receipt_without_error_poll(
    monkeypatch,
    wait_result,
):
    pending = _receipt()
    calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None, **kwargs):
        calls.append(route)
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": "component-guid"}}
        if route == "/gh/script-params":
            return {"success": True, "data": {}}
        if route == "/gh/script":
            return {"success": True, "data": {
                "solve_relevant_mutation_committed": True,
                "solve_readiness_receipt": pending,
            }}
        if route == "/gh/wait-for-solve-readiness":
            return wait_result
        raise AssertionError("error polling after failed readiness")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    result = await server._execute_gh_create_script(
        "python",
        {"code": "A = 1", "pins_in": [], "pins_out": ["A:int"]},
        6011,
    )

    assert result["success"] is False
    assert result["data"]["phase"] == "solve_readiness"
    assert result["data"]["solve_readiness_receipt"] is pending
    assert calls[-1] == "/gh/wait-for-solve-readiness"


@pytest.mark.asyncio
async def test_create_script_wait_exception_is_solve_readiness_and_stops(monkeypatch):
    pending = _receipt()
    calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None, **kwargs):
        calls.append(route)
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": "component-guid"}}
        if route == "/gh/script-params":
            return {"success": True, "data": {}}
        if route == "/gh/script":
            return {"success": True, "data": {
                "solve_relevant_mutation_committed": True,
                "solve_readiness_receipt": pending,
            }}
        if route == "/gh/wait-for-solve-readiness":
            raise TimeoutError("wait transport timed out")
        raise AssertionError("post-wait read is forbidden")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    result = await server._execute_gh_create_script(
        "python",
        {"code": "A = 1", "pins_in": [], "pins_out": ["A:int"]},
        6011,
    )

    assert result["data"]["phase"] == "solve_readiness"
    assert result["data"]["solve_readiness_receipt"] is pending
    assert calls[-1] == "/gh/wait-for-solve-readiness"


@pytest.mark.asyncio
async def test_create_script_post_write_failure_retains_both_receipts(monkeypatch):
    pending = _receipt()

    async def fake_call_rhino(route, method="GET", payload=None, port=None, **kwargs):
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": "component-guid"}}
        if route == "/gh/script-params":
            return {"success": True, "data": {}}
        if route == "/gh/script":
            return {"success": True, "data": {
                "solve_relevant_mutation_committed": True,
                "solve_readiness_receipt": pending,
            }}
        if route == "/gh/wait-for-solve-readiness":
            return _ready_wait()
        if route == "/gh/errors":
            return {"success": False, "data": "diagnostics unavailable"}
        raise AssertionError("unexpected contact")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    result = await server._execute_gh_create_script(
        "python",
        {"code": "A = 1", "pins_in": [], "pins_out": ["A:int"]},
        6011,
    )

    assert result["success"] is False
    assert result["data"]["phase"] == "post_write_verification"
    assert result["data"]["solve_readiness_receipt"] is pending
    assert result["data"]["script_receipt"]["version"] == 1
    assert "solve_readiness_receipt" not in result["data"]["script_receipt"]


@pytest.mark.asyncio
async def test_update_script_uses_one_final_write_waits_and_preserves_receipt(monkeypatch):
    pending = _receipt(receipt_id="update-receipt")
    calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None, timeout=None):
        calls.append((route, method, payload))
        if route == "/gh/script" and method == "POST" and payload == {"guid": "C1"}:
            return {"success": True, "data": {"Type": "GhPythonComponent", "guid": "component-guid"}}
        if route == "/gh/component":
            return {"success": True, "data": {"guid": "component-guid", "Params": {"Inputs": [], "Outputs": []}}}
        if route == "/gh/script" and "script" in payload:
            return {"success": True, "data": {
                "guid": "component-guid",
                "solve_relevant_mutation_committed": True,
                "solve_readiness_receipt": pending,
            }}
        if route == "/gh/wait-for-solve-readiness":
            return _ready_wait("update-receipt")
        if route == "/gh/errors":
            return {"success": True, "data": {"errors": [], "warnings": []}}
        raise AssertionError(f"unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    result = await server._execute_gh_update_script(
        {"guid": "C1", "code": "A = 2", "language": "python"},
        6011,
    )

    assert result["success"] is True
    assert result["data"]["solve_readiness_receipt"] is pending
    assert result["data"]["solve_relevant_mutation_committed"] is True
    assert sum(route == "/gh/script" and method == "POST" and "script" in payload for route, method, payload in calls) == 1
    assert [route for route, _, _ in calls][-2:] == [
        "/gh/wait-for-solve-readiness",
        "/gh/errors",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("receipt_value", [None, "malformed-receipt"])
async def test_update_script_receipt_admission_failure_retains_raw_value(
    monkeypatch,
    receipt_value,
):
    calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None, **kwargs):
        calls.append(route)
        if route == "/gh/script" and payload == {"guid": "C1"}:
            return {"success": True, "data": {
                "Type": "GhPythonComponent",
                "guid": "component-guid",
            }}
        if route == "/gh/component":
            return {"success": True, "data": {
                "guid": "component-guid",
                "Params": {"Inputs": [], "Outputs": []},
            }}
        if route == "/gh/script" and "script" in payload:
            return {"success": True, "data": {
                "solve_relevant_mutation_committed": True,
                "solve_readiness_receipt": receipt_value,
            }}
        raise AssertionError("receipt refusal must stop contact")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    result = await server._execute_gh_update_script(
        {"guid": "C1", "code": "A = 2", "language": "python"},
        6011,
    )

    assert result["data"]["phase"] == "solve_readiness"
    assert result["data"]["solve_readiness_receipt"] is receipt_value
    assert calls[-1] == "/gh/script"


@pytest.mark.asyncio
async def test_update_script_wait_exception_is_solve_readiness_and_stops(monkeypatch):
    pending = _receipt(receipt_id="update-wait-exception")
    calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None, **kwargs):
        calls.append(route)
        if route == "/gh/script" and payload == {"guid": "C1"}:
            return {"success": True, "data": {
                "Type": "GhPythonComponent",
                "guid": "component-guid",
            }}
        if route == "/gh/component":
            return {"success": True, "data": {
                "guid": "component-guid",
                "Params": {"Inputs": [], "Outputs": []},
            }}
        if route == "/gh/script" and "script" in payload:
            return {"success": True, "data": {
                "solve_relevant_mutation_committed": True,
                "solve_readiness_receipt": pending,
            }}
        if route == "/gh/wait-for-solve-readiness":
            raise TimeoutError("wait transport timed out")
        raise AssertionError("post-wait read is forbidden")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    result = await server._execute_gh_update_script(
        {"guid": "C1", "code": "A = 2", "language": "python"},
        6011,
    )

    assert result["data"]["phase"] == "solve_readiness"
    assert result["data"]["solve_readiness_receipt"] is pending
    assert calls[-1] == "/gh/wait-for-solve-readiness"
