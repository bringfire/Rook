"""Unit tests for the edge-detected GH solve-settle logic (no Rhino needed)."""


def test_settle_requires_busy_then_idle():
    from rook.server import _gh_solve_settle_step

    # idle observed before any busy -> NOT settled (avoids the pre-solve-idle bug)
    settled, saw_busy = _gh_solve_settle_step(prev_saw_busy=False, solution_state="Off")
    assert settled is False and saw_busy is False

    # busy observed -> arm
    settled, saw_busy = _gh_solve_settle_step(prev_saw_busy=False, solution_state="Computing")
    assert settled is False and saw_busy is True

    # idle after busy -> settled
    settled, saw_busy = _gh_solve_settle_step(prev_saw_busy=True, solution_state="Complete")
    assert settled is True and saw_busy is True
