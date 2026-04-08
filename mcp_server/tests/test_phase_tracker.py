"""Tests for PhaseTracker workflow phase detection."""

import pytest
from rook.learning.phase_tracker import PhaseTracker, WorkflowPhase


class TestCurrentPhase:
    """Test phase detection from recent tool calls."""

    def test_empty_tracker_returns_exploration(self):
        tracker = PhaseTracker()
        assert tracker.current_phase() == WorkflowPhase.EXPLORATION

    def test_fewer_than_threshold_returns_exploration(self):
        tracker = PhaseTracker()
        tracker.record_call("gh_connect")
        tracker.record_call("gh_component")
        assert tracker.current_phase() == WorkflowPhase.EXPLORATION

    def test_gh_build_phase_detected(self):
        tracker = PhaseTracker()
        for _ in range(5):
            tracker.record_call("gh_execute_intent")
        assert tracker.current_phase() == WorkflowPhase.GH_BUILD

    def test_rhino_model_phase_detected(self):
        tracker = PhaseTracker()
        for _ in range(5):
            tracker.record_call("rhino_create")
        assert tracker.current_phase() == WorkflowPhase.RHINO_MODEL

    def test_debugging_phase_detected(self):
        tracker = PhaseTracker()
        for _ in range(5):
            tracker.record_call("gh_errors")
        assert tracker.current_phase() == WorkflowPhase.DEBUGGING

    def test_exploration_phase_detected(self):
        tracker = PhaseTracker()
        for _ in range(5):
            tracker.record_call("gh_knowledge_query")
        assert tracker.current_phase() == WorkflowPhase.EXPLORATION

    def test_mixed_calls_below_threshold_stays_exploration(self):
        tracker = PhaseTracker()
        tracker.record_call("gh_connect")
        tracker.record_call("rhino_create")
        tracker.record_call("gh_errors")
        tracker.record_call("some_random_tool")
        tracker.record_call("another_tool")
        assert tracker.current_phase() == WorkflowPhase.EXPLORATION

    def test_phase_uses_last_10_calls(self):
        tracker = PhaseTracker()
        # Fill with 10 rhino calls, then 5 GH calls
        for _ in range(10):
            tracker.record_call("rhino_create")
        # Now add enough GH calls to dominate the last-10 window
        for _ in range(8):
            tracker.record_call("gh_execute_intent")
        assert tracker.current_phase() == WorkflowPhase.GH_BUILD

    def test_window_size_limits_memory(self):
        tracker = PhaseTracker(window_size=5)
        for _ in range(3):
            tracker.record_call("rhino_create")
        # Fill window with GH calls, pushing rhino out
        for _ in range(5):
            tracker.record_call("gh_connect")
        assert tracker.current_phase() == WorkflowPhase.GH_BUILD

    def test_substring_matching(self):
        """Phase patterns use 'in' matching, not exact match."""
        tracker = PhaseTracker()
        # "rhino_execute_intent" contains "rhino_execute_intent" pattern
        for _ in range(5):
            tracker.record_call("rhino_execute_intent")
        assert tracker.current_phase() == WorkflowPhase.RHINO_MODEL


class TestShouldInjectWorkflowHint:
    """Test sustained phase detection for P1 workflow hints."""

    def test_returns_false_when_too_few_calls(self):
        tracker = PhaseTracker()
        tracker.record_call("gh_connect")
        tracker.record_call("gh_component")
        assert tracker.should_inject_workflow_hint() is False

    def test_returns_false_for_exploration(self):
        tracker = PhaseTracker()
        for _ in range(10):
            tracker.record_call("gh_knowledge_query")
        assert tracker.should_inject_workflow_hint() is False

    def test_returns_true_on_sustained_gh_build(self):
        tracker = PhaseTracker()
        for _ in range(5):
            tracker.record_call("gh_execute_intent")
        assert tracker.should_inject_workflow_hint() is True

    def test_returns_false_on_second_call_same_phase(self):
        tracker = PhaseTracker()
        for _ in range(5):
            tracker.record_call("gh_connect")
        assert tracker.should_inject_workflow_hint() is True
        # Second call in same phase should be rate-limited
        tracker.record_call("gh_component")
        assert tracker.should_inject_workflow_hint() is False

    def test_resets_on_phase_change(self):
        tracker = PhaseTracker()
        # Enter GH_BUILD phase
        for _ in range(5):
            tracker.record_call("gh_connect")
        assert tracker.should_inject_workflow_hint() is True

        # Push all GH calls out of the last-10 window so phase becomes EXPLORATION
        for _ in range(12):
            tracker.record_call("some_random_tool")
        # Must call during exploration so internal state resets
        assert tracker.should_inject_workflow_hint() is False

        # Re-enter GH_BUILD — should fire again since phase was reset
        for _ in range(5):
            tracker.record_call("gh_execute_intent")
        assert tracker.should_inject_workflow_hint() is True

    def test_requires_4_of_5_matches(self):
        tracker = PhaseTracker()
        # 3 of 5 = not enough
        tracker.record_call("gh_connect")
        tracker.record_call("gh_component")
        tracker.record_call("gh_set_value")
        tracker.record_call("some_tool")
        tracker.record_call("another_tool")
        assert tracker.should_inject_workflow_hint() is False

    def test_4_of_5_matches_triggers(self):
        tracker = PhaseTracker()
        tracker.record_call("gh_connect")
        tracker.record_call("gh_component")
        tracker.record_call("gh_set_value")
        tracker.record_call("gh_execute_intent")
        tracker.record_call("some_tool")
        assert tracker.should_inject_workflow_hint() is True


class TestRecentTools:
    """Test the recent_tools debugging helper."""

    def test_returns_last_n(self):
        tracker = PhaseTracker()
        tracker.record_call("a")
        tracker.record_call("b")
        tracker.record_call("c")
        assert tracker.recent_tools(2) == ["b", "c"]

    def test_returns_all_if_fewer_than_n(self):
        tracker = PhaseTracker()
        tracker.record_call("a")
        assert tracker.recent_tools(5) == ["a"]

    def test_empty_tracker(self):
        tracker = PhaseTracker()
        assert tracker.recent_tools() == []
