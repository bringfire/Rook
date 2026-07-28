"""Unit tests for gh_update_script schedule-acceptance handling (no Rhino needed)."""


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
