"""Unit tests for the rhino_launch leaf module (the launch + readiness primitives).

Grows task-by-task with the Rhino-launch-hardening plan. Task 1 covers the move +
re-export contract; later tasks add the LaunchOutcome/evidence/argv/classifier/primitives.
"""

from __future__ import annotations


def test_primitives_resolve_from_both_modules():
    from rook import rhino_launch, runtime_harness
    # canonical home is rhino_launch; runtime_harness re-exports the SAME objects
    for name in ("DiscoveryError", "DiscoveryFailureReason", "OwnedRhinoDiscovery",
                 "OwnedRhinoRecord", "ping_native", "describe_windows_for_pid",
                 "_windows_user32", "default_discovery_dir"):
        assert getattr(rhino_launch, name) is getattr(runtime_harness, name), name


def test_close_windows_stays_in_harness_with_wm_close():
    # WM_CLOSE + close_windows_for_pid are cleanup — they stay in runtime_harness.
    from rook import runtime_harness, rhino_launch
    assert hasattr(runtime_harness, "close_windows_for_pid")
    assert runtime_harness.WM_CLOSE == 0x0010
    assert not hasattr(rhino_launch, "WM_CLOSE")  # not moved
