"""Test Phase 1 → Phase 2 Integration: Pattern tracking in sessions."""

import pytest

from rook.learning.gh_session_history import SessionSummary


class TestSessionSummaryPatternFields:
    """Test SessionSummary pattern tracking fields."""

    def test_summary_has_patterns_applied(self):
        """Test that SessionSummary has patterns_applied field."""
        summary = SessionSummary()
        assert hasattr(summary, "patterns_applied")
        assert summary.patterns_applied == []

    def test_summary_has_patterns_discovered(self):
        """Test that SessionSummary has patterns_discovered field."""
        summary = SessionSummary()
        assert hasattr(summary, "patterns_discovered")
        assert summary.patterns_discovered == []

    def test_summary_to_dict_includes_patterns(self):
        """Test that to_dict includes pattern fields."""
        summary = SessionSummary()
        summary.patterns_applied = ["p1", "p2"]
        summary.patterns_discovered = ["p3"]

        d = summary.to_dict()
        assert d["patterns_applied"] == ["p1", "p2"]
        assert d["patterns_discovered"] == ["p3"]

    def test_summary_from_dict_with_patterns(self):
        """Test that from_dict restores pattern fields."""
        d = {
            "total_entries": 5,
            "successes": 4,
            "failures": 1,
            "partials": 0,
            "components_created": 10,
            "components_deleted": 2,
            "connections_made": 5,
            "connections_removed": 1,
            "patterns_applied": ["p1", "p2"],
            "patterns_discovered": ["p3"],
        }

        summary = SessionSummary.from_dict(d)
        assert summary.patterns_applied == ["p1", "p2"]
        assert summary.patterns_discovered == ["p3"]

    def test_patterns_mutable_as_list(self):
        """Test that patterns can be appended without duplicates."""
        summary = SessionSummary()

        # Simulate what record() does
        patterns_applied = ["p1", "p2"]
        for pattern_id in patterns_applied:
            if pattern_id not in summary.patterns_applied:
                summary.patterns_applied.append(pattern_id)

        assert summary.patterns_applied == ["p1", "p2"]

        # Add overlapping patterns
        patterns_applied_2 = ["p2", "p3"]
        for pattern_id in patterns_applied_2:
            if pattern_id not in summary.patterns_applied:
                summary.patterns_applied.append(pattern_id)

        # No duplicates
        assert summary.patterns_applied == ["p1", "p2", "p3"]


class TestRecordSignature:
    """Test that GHSessionRecorder.record accepts patterns_applied parameter."""

    def test_record_accepts_patterns_applied_parameter(self):
        """Verify the record method signature includes patterns_applied."""
        from rook.learning.gh_session_history import GHSessionRecorder
        import inspect

        sig = inspect.signature(GHSessionRecorder.record)
        params = list(sig.parameters.keys())

        assert "patterns_applied" in params, (
            f"record() should accept patterns_applied parameter. "
            f"Current params: {params}"
        )

    def test_record_patterns_applied_optional(self):
        """Verify patterns_applied has a default value (optional)."""
        from rook.learning.gh_session_history import GHSessionRecorder
        import inspect

        sig = inspect.signature(GHSessionRecorder.record)
        param = sig.parameters.get("patterns_applied")

        assert param is not None
        assert param.default is None, "patterns_applied should default to None"


class TestRecordGHToSessionSignature:
    """Test that _record_gh_to_session accepts patterns_applied parameter."""

    def test_helper_accepts_patterns_applied_parameter(self):
        """Verify the helper function signature includes patterns_applied."""
        from pathlib import Path

        # Read server.py with utf-8 encoding
        server_code = Path("src/rook/server.py").read_text(encoding="utf-8")

        assert "patterns_applied: list[str] | None = None" in server_code, (
            "_record_gh_to_session should accept patterns_applied parameter"
        )
        assert "patterns_applied=patterns_applied" in server_code, (
            "_record_gh_to_session should pass patterns_applied to recorder"
        )
