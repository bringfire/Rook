"""Unit tests for gh_update_script solver-locked deferral logic (no Rhino needed)."""


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
