"""Tests for Pattern Verifier - JIT verification for pattern citations."""

import json
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from rook.learning.pattern_memory import PatternNote
from rook.learning.pattern_verifier import (
    PatternVerifier,
    StalenessPolicy,
    VerificationResult,
)


class TestStalenessPolicy:
    """Tests for staleness threshold calculation."""

    def test_high_confidence_gets_longer_threshold(self):
        """High success rate patterns get more grace period."""
        days = StalenessPolicy.get_threshold_days(0.9)
        assert days == StalenessPolicy.HIGH_CONFIDENCE_DAYS
        assert days == 60

    def test_low_confidence_gets_shorter_threshold(self):
        """Low success rate patterns need faster re-check."""
        days = StalenessPolicy.get_threshold_days(0.3)
        assert days == StalenessPolicy.LOW_CONFIDENCE_DAYS
        assert days == 14

    def test_medium_confidence_gets_default(self):
        """Medium success rate patterns get default threshold."""
        days = StalenessPolicy.get_threshold_days(0.6)
        assert days == StalenessPolicy.DEFAULT_DAYS
        assert days == 30

    def test_boundary_at_80_percent(self):
        """80% success rate gets high confidence threshold."""
        assert StalenessPolicy.get_threshold_days(0.8) == 60
        assert StalenessPolicy.get_threshold_days(0.79) == 30

    def test_boundary_at_50_percent(self):
        """50% success rate gets default, below gets low."""
        assert StalenessPolicy.get_threshold_days(0.5) == 30
        assert StalenessPolicy.get_threshold_days(0.49) == 14


class TestVerificationResult:
    """Tests for VerificationResult data class."""

    def test_to_dict(self):
        """Verify to_dict includes all relevant fields."""
        result = VerificationResult(
            pattern_id="test123",
            status="verified",
            citations_checked=3,
            citations_valid=2,
            days_since_verified=5,
            needs_reverification=False,
            warnings=["one warning"],
        )

        d = result.to_dict()
        assert d["status"] == "verified"
        assert d["citations_checked"] == 3
        assert d["citations_valid"] == 2
        assert d["days_since_verified"] == 5
        assert d["needs_reverification"] is False
        assert d["warnings"] == ["one warning"]


class TestPatternVerifier:
    """Tests for PatternVerifier class."""

    @pytest.fixture
    def temp_sessions_dir(self):
        """Create temporary sessions directory."""
        tmpdir = Path(tempfile.mkdtemp())
        sessions_dir = tmpdir / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "_active").mkdir(parents=True)

        yield sessions_dir

        shutil.rmtree(tmpdir)

    @pytest.fixture
    def verifier(self, temp_sessions_dir):
        """Create verifier with temp directory."""
        return PatternVerifier(temp_sessions_dir)

    def _create_session_file(self, sessions_dir: Path, session_id: str, summary: dict = None):
        """Helper to create a session file."""
        session_data = {
            "session_id": session_id,
            "document": "test.gh",
            "started": datetime.utcnow().isoformat() + "Z",
            "status": "ended",
            "entries": [],
            "summary": summary or {"successes": 1, "failures": 0},
        }

        path = sessions_dir / f"{session_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session_data, f)

        return path

    def test_no_citations_returns_no_citations_status(self, verifier):
        """Pattern without citations should return no_citations status."""
        pattern = PatternNote(
            name="No Citations Pattern",
            solution_brief="Test",
            citations=[],
        )

        result = verifier.verify(pattern)

        assert result.status == "no_citations"
        assert result.citations_checked == 0
        assert result.citations_valid == 0
        assert "no citations" in result.warnings[0].lower()

    def test_valid_citation_returns_verified(self, verifier, temp_sessions_dir):
        """Pattern with valid citation should be verified."""
        # Create session file
        session_id = "gh_session_20260131_120000"
        self._create_session_file(temp_sessions_dir, session_id)

        # Create pattern citing this session
        pattern = PatternNote(
            name="Valid Citation Pattern",
            solution_brief="Test",
            citations=[
                {
                    "session_id": session_id,
                    "outcome": "success",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            ],
            last_verified=datetime.utcnow().isoformat() + "Z",
        )

        result = verifier.verify(pattern)

        assert result.status == "verified"
        assert result.citations_checked == 1
        assert result.citations_valid == 1
        assert result.needs_reverification is False

    def test_missing_session_returns_unverifiable(self, verifier):
        """Pattern citing non-existent session should be unverifiable."""
        pattern = PatternNote(
            name="Missing Session Pattern",
            solution_brief="Test",
            citations=[
                {
                    "session_id": "gh_session_nonexistent",
                    "outcome": "success",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            ],
        )

        result = verifier.verify(pattern)

        assert result.status == "unverifiable"
        assert result.citations_valid == 0
        assert any("no longer exists" in w for w in result.warnings)

    def test_stale_pattern_detected(self, verifier, temp_sessions_dir):
        """Pattern not verified recently should be marked stale."""
        session_id = "gh_session_20260131_120000"
        self._create_session_file(temp_sessions_dir, session_id)

        # Create pattern verified 45 days ago
        old_date = datetime.utcnow() - timedelta(days=45)
        pattern = PatternNote(
            name="Stale Pattern",
            solution_brief="Test",
            citations=[
                {
                    "session_id": session_id,
                    "outcome": "success",
                    "timestamp": old_date.isoformat() + "Z",
                }
            ],
            last_verified=old_date.isoformat() + "Z",
        )

        result = verifier.verify(pattern)

        assert result.status == "stale"
        assert result.needs_reverification is True
        assert result.days_since_verified is not None
        assert result.days_since_verified >= 45

    def test_never_verified_is_stale(self, verifier, temp_sessions_dir):
        """Pattern never verified should be marked stale."""
        session_id = "gh_session_20260131_120000"
        self._create_session_file(temp_sessions_dir, session_id)

        pattern = PatternNote(
            name="Never Verified",
            solution_brief="Test",
            citations=[
                {
                    "session_id": session_id,
                    "outcome": "success",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            ],
            last_verified=None,  # Never verified
        )

        result = verifier.verify(pattern)

        assert result.status == "stale"
        assert result.days_since_verified is None
        assert result.needs_reverification is True

    def test_partial_citations_valid(self, verifier, temp_sessions_dir):
        """Pattern with some valid citations should still be verified."""
        # Create one valid session
        valid_session = "gh_session_valid"
        self._create_session_file(temp_sessions_dir, valid_session)

        pattern = PatternNote(
            name="Partial Citations",
            solution_brief="Test",
            citations=[
                {
                    "session_id": valid_session,
                    "outcome": "success",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
                {
                    "session_id": "gh_session_missing",
                    "outcome": "success",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
            ],
            last_verified=datetime.utcnow().isoformat() + "Z",
        )

        result = verifier.verify(pattern)

        # Should still be verified because one citation is valid
        assert result.status == "verified"
        assert result.citations_checked == 2
        assert result.citations_valid == 1

    def test_check_staleness_method(self, verifier):
        """Test check_staleness helper method."""
        # Fresh pattern
        fresh = PatternNote(
            name="Fresh",
            last_verified=datetime.utcnow().isoformat() + "Z",
        )
        is_stale, days = verifier.check_staleness(fresh)
        assert is_stale is False
        assert days is not None
        assert days < 1

        # Stale pattern
        old_date = datetime.utcnow() - timedelta(days=45)
        stale = PatternNote(
            name="Stale",
            last_verified=old_date.isoformat() + "Z",
        )
        is_stale, days = verifier.check_staleness(stale)
        assert is_stale is True
        assert days >= 45

    def test_high_confidence_pattern_longer_threshold(self, verifier, temp_sessions_dir):
        """High confidence patterns stay verified longer."""
        session_id = "gh_session_20260131_120000"
        self._create_session_file(temp_sessions_dir, session_id)

        # Pattern verified 50 days ago with high success rate
        old_date = datetime.utcnow() - timedelta(days=50)
        pattern = PatternNote(
            name="High Confidence",
            solution_brief="Test",
            citations=[
                {
                    "session_id": session_id,
                    "outcome": "success",
                    "timestamp": old_date.isoformat() + "Z",
                }
            ],
            last_verified=old_date.isoformat() + "Z",
            times_used=10,
            times_succeeded=9,  # 90% success rate
        )

        result = verifier.verify(pattern)

        # Should still be verified (threshold is 60 days for high confidence)
        assert result.status == "verified"
        assert result.needs_reverification is False


class TestConsistencyVerification:
    """Tests for consistency-level verification."""

    @pytest.fixture
    def temp_sessions_dir(self):
        """Create temporary sessions directory."""
        tmpdir = Path(tempfile.mkdtemp())
        sessions_dir = tmpdir / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "_active").mkdir(parents=True)

        yield sessions_dir

        shutil.rmtree(tmpdir)

    @pytest.fixture
    def verifier(self, temp_sessions_dir):
        """Create verifier with temp directory."""
        return PatternVerifier(temp_sessions_dir)

    def _create_session_with_entries(
        self,
        sessions_dir: Path,
        session_id: str,
        entries: list[dict],
        summary: dict = None,
    ):
        """Helper to create a session with entries."""
        session_data = {
            "session_id": session_id,
            "document": "test.gh",
            "started": datetime.utcnow().isoformat() + "Z",
            "status": "ended",
            "entries": entries,
            "summary": summary or {
                "successes": sum(1 for e in entries if e.get("outcome") == "success"),
                "failures": sum(1 for e in entries if e.get("outcome") == "failure"),
            },
        }

        path = sessions_dir / f"{session_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session_data, f)

        return path

    def test_consistency_check_success(self, verifier, temp_sessions_dir):
        """Consistency check passes when session has successes."""
        session_id = "gh_session_consistent"
        entries = [
            {"entry_id": 1, "outcome": "success"},
            {"entry_id": 2, "outcome": "success"},
        ]
        self._create_session_with_entries(temp_sessions_dir, session_id, entries)

        pattern = PatternNote(
            name="Consistent Pattern",
            solution_brief="Test",
            citations=[
                {
                    "session_id": session_id,
                    "outcome": "success",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            ],
            last_verified=datetime.utcnow().isoformat() + "Z",
        )

        result = verifier.verify(pattern, level="consistency")

        assert result.consistency_checked is True
        assert result.consistency_passed is True
        assert result.status == "verified"

    def test_consistency_check_fails_no_successes(self, verifier, temp_sessions_dir):
        """Consistency check fails when citation claims success but session has none."""
        session_id = "gh_session_no_success"
        entries = [
            {"entry_id": 1, "outcome": "failure"},
        ]
        self._create_session_with_entries(temp_sessions_dir, session_id, entries)

        pattern = PatternNote(
            name="Inconsistent Pattern",
            solution_brief="Test",
            citations=[
                {
                    "session_id": session_id,
                    "outcome": "success",  # Claims success
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            ],
            last_verified=datetime.utcnow().isoformat() + "Z",
        )

        result = verifier.verify(pattern, level="consistency")

        assert result.consistency_checked is True
        assert result.consistency_passed is False
        assert result.status == "stale"  # Downgraded due to consistency failure
        assert any("claims success" in w for w in result.warnings)

    def test_entry_range_verification(self, verifier, temp_sessions_dir):
        """Consistency check verifies entry range exists."""
        session_id = "gh_session_entries"
        entries = [
            {"entry_id": 1, "outcome": "success"},
            {"entry_id": 2, "outcome": "success"},
            {"entry_id": 3, "outcome": "success"},
        ]
        self._create_session_with_entries(temp_sessions_dir, session_id, entries)

        # Citation with valid entry range
        pattern = PatternNote(
            name="Valid Entry Range",
            solution_brief="Test",
            citations=[
                {
                    "session_id": session_id,
                    "outcome": "success",
                    "entry_range": [1, 3],
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            ],
            last_verified=datetime.utcnow().isoformat() + "Z",
        )

        result = verifier.verify(pattern, level="consistency")
        assert result.consistency_passed is True

    def test_invalid_entry_range_fails(self, verifier, temp_sessions_dir):
        """Consistency check fails when entry range doesn't exist."""
        session_id = "gh_session_entries"
        entries = [
            {"entry_id": 1, "outcome": "success"},
            {"entry_id": 2, "outcome": "success"},
        ]
        self._create_session_with_entries(temp_sessions_dir, session_id, entries)

        # Citation with invalid entry range
        pattern = PatternNote(
            name="Invalid Entry Range",
            solution_brief="Test",
            citations=[
                {
                    "session_id": session_id,
                    "outcome": "success",
                    "entry_range": [1, 10],  # Entry 10 doesn't exist
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            ],
            last_verified=datetime.utcnow().isoformat() + "Z",
        )

        result = verifier.verify(pattern, level="consistency")
        assert result.consistency_passed is False
        assert any("Entry range" in w for w in result.warnings)
