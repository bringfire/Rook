"""
Phase 3: Just-in-Time Verification - Integration Tests

Tests the complete JIT verification flow:
1. Search returns patterns with verification status
2. Stale patterns are detected and flagged
3. Missing sessions make patterns unverifiable
4. Successful use refreshes verification timestamp
5. Verified patterns rank higher in search results
"""

import json
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from rook.learning.pattern_memory import PatternNote
from rook.learning.pattern_store import PatternStore


class TestJITVerificationIntegration:
    """Integration tests for JIT verification in PatternStore."""

    @pytest.fixture
    def temp_storage(self):
        """Create isolated temporary storage for patterns and sessions."""
        tmpdir = Path(tempfile.mkdtemp())

        # Pattern storage
        patterns_dir = tmpdir / "patterns"
        index_path = tmpdir / "pattern_index.json"
        patterns_dir.mkdir(parents=True, exist_ok=True)

        # Session storage
        sessions_dir = tmpdir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "_active").mkdir(parents=True, exist_ok=True)

        # Patch pattern_store paths
        import rook.learning.pattern_store as ps

        original_knowledge_dir = ps.KNOWLEDGE_DIR
        original_patterns_dir = ps.PATTERNS_DIR
        original_index_path = ps.INDEX_PATH

        ps.KNOWLEDGE_DIR = tmpdir
        ps.PATTERNS_DIR = patterns_dir
        ps.INDEX_PATH = index_path

        # Patch gh_session_history paths
        import rook.learning.gh_session_history as gh

        original_sessions_dir = gh.SESSIONS_DIR

        gh.SESSIONS_DIR = sessions_dir

        # Reset verifier singleton
        import rook.learning.pattern_verifier as pv

        pv._verifier = None

        yield {
            "tmpdir": tmpdir,
            "patterns_dir": patterns_dir,
            "sessions_dir": sessions_dir,
        }

        # Restore and cleanup
        ps.KNOWLEDGE_DIR = original_knowledge_dir
        ps.PATTERNS_DIR = original_patterns_dir
        ps.INDEX_PATH = original_index_path
        gh.SESSIONS_DIR = original_sessions_dir
        pv._verifier = None

        shutil.rmtree(tmpdir)

    def _create_session(
        self,
        sessions_dir: Path,
        session_id: str,
        successes: int = 1,
        failures: int = 0,
    ) -> Path:
        """Helper to create a session file."""
        session_data = {
            "session_id": session_id,
            "document": "test.gh",
            "document_path": "/test/test.gh",
            "started": datetime.utcnow().isoformat() + "Z",
            "status": "ended",
            "entries": [
                {"entry_id": i + 1, "outcome": "success"}
                for i in range(successes)
            ] + [
                {"entry_id": successes + i + 1, "outcome": "failure"}
                for i in range(failures)
            ],
            "summary": {
                "total_entries": successes + failures,
                "successes": successes,
                "failures": failures,
            },
        }

        path = sessions_dir / f"{session_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session_data, f)

        return path

    def test_search_returns_verification_status(self, temp_storage):
        """Search results include verification status."""
        sessions_dir = temp_storage["sessions_dir"]

        # Create a session for citation
        session_id = "gh_session_20260131_100000"
        self._create_session(sessions_dir, session_id)

        # Create pattern with valid citation
        store = PatternStore(
            auto_save=True,
            enable_evolution=False,
            verify_on_search=True,
        )

        pattern = PatternNote(
            name="Verified Pattern",
            solution_brief="This pattern has valid citations",
            trigger_intents=["test verification"],
            citations=[
                {
                    "session_id": session_id,
                    "outcome": "success",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            ],
            last_verified=datetime.utcnow().isoformat() + "Z",
        )
        store.add(pattern, skip_evolution=True)

        # Search should return pattern with verification status
        results = store.search(intent="test verification")

        assert len(results) == 1
        assert results[0].verification_status == "verified"
        assert results[0]._days_since_verified is not None
        assert len(results[0].verification_warnings) == 0

    def test_stale_pattern_flagged(self, temp_storage):
        """Patterns not verified recently are marked stale."""
        sessions_dir = temp_storage["sessions_dir"]

        # Create session
        session_id = "gh_session_stale"
        self._create_session(sessions_dir, session_id)

        store = PatternStore(
            auto_save=True,
            enable_evolution=False,
            verify_on_search=True,
        )

        # Create pattern verified 45 days ago
        old_date = datetime.utcnow() - timedelta(days=45)
        pattern = PatternNote(
            name="Stale Pattern",
            solution_brief="This pattern is stale",
            trigger_intents=["stale test"],
            citations=[
                {
                    "session_id": session_id,
                    "outcome": "success",
                    "timestamp": old_date.isoformat() + "Z",
                }
            ],
            last_verified=old_date.isoformat() + "Z",
        )
        store.add(pattern, skip_evolution=True)

        # Search should mark pattern as stale
        results = store.search(intent="stale test")

        assert len(results) == 1
        assert results[0].verification_status == "stale"
        assert results[0]._days_since_verified >= 45
        assert any("days" in w for w in results[0].verification_warnings)

    def test_missing_session_unverifiable(self, temp_storage):
        """Patterns citing deleted sessions are marked unverifiable."""
        store = PatternStore(
            auto_save=True,
            enable_evolution=False,
            verify_on_search=True,
        )

        # Create pattern citing non-existent session
        pattern = PatternNote(
            name="Unverifiable Pattern",
            solution_brief="This pattern cites a missing session",
            trigger_intents=["missing session"],
            citations=[
                {
                    "session_id": "gh_session_deleted",
                    "outcome": "success",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            ],
        )
        store.add(pattern, skip_evolution=True)

        # Search should mark pattern as unverifiable
        results = store.search(intent="missing session")

        assert len(results) == 1
        assert results[0].verification_status == "unverifiable"
        assert any("no longer exists" in w for w in results[0].verification_warnings)

    def test_verified_patterns_rank_higher(self, temp_storage):
        """Verified patterns rank higher than stale patterns."""
        sessions_dir = temp_storage["sessions_dir"]

        # Create two sessions
        session1 = "gh_session_verified"
        session2 = "gh_session_stale"
        self._create_session(sessions_dir, session1)
        self._create_session(sessions_dir, session2)

        store = PatternStore(
            auto_save=True,
            enable_evolution=False,
            verify_on_search=True,
        )

        # Add stale pattern first
        # Note: 100% success rate = 60 day threshold, so use 65 days to ensure stale
        old_date = datetime.utcnow() - timedelta(days=65)
        stale = PatternNote(
            name="Stale Pattern",
            solution_brief="This is stale",
            trigger_intents=["rank test"],
            trigger_symptoms=["rank test"],
            citations=[{"session_id": session2, "outcome": "success"}],
            last_verified=old_date.isoformat() + "Z",
            times_used=1,
            times_succeeded=1,  # 100% = 60 day threshold
        )
        store.add(stale, skip_evolution=True)

        # Add verified pattern (with same success rate)
        verified = PatternNote(
            name="Verified Pattern",
            solution_brief="This is verified",
            trigger_intents=["rank test"],
            trigger_symptoms=["rank test"],
            citations=[{"session_id": session1, "outcome": "success"}],
            last_verified=datetime.utcnow().isoformat() + "Z",
            times_used=1,
            times_succeeded=1,
        )
        store.add(verified, skip_evolution=True)

        # Search should return verified pattern first
        results = store.search(intent="rank test")

        assert len(results) == 2
        assert results[0].name == "Verified Pattern"
        assert results[0].verification_status == "verified"
        assert results[1].name == "Stale Pattern"
        assert results[1].verification_status == "stale"

    def test_successful_use_refreshes_verification(self, temp_storage):
        """Recording successful use updates last_verified timestamp."""
        sessions_dir = temp_storage["sessions_dir"]

        session_id = "gh_session_use"
        self._create_session(sessions_dir, session_id)

        store = PatternStore(
            auto_save=True,
            enable_evolution=False,
            verify_on_search=True,
        )

        # Create stale pattern
        old_date = datetime.utcnow() - timedelta(days=45)
        pattern = PatternNote(
            name="Stale Until Used",
            solution_brief="Will be refreshed on use",
            trigger_intents=["refresh test"],
            citations=[{"session_id": session_id, "outcome": "success"}],
            last_verified=old_date.isoformat() + "Z",
        )
        store.add(pattern, skip_evolution=True)

        # Verify it's stale
        results = store.search(intent="refresh test")
        assert results[0].verification_status == "stale"

        # Record successful use
        new_session = "gh_session_new_use"
        self._create_session(sessions_dir, new_session)

        updated = store.record_use(
            pattern.pattern_id,
            success=True,
            session_id=new_session,
        )

        # Should now be verified (last_verified updated)
        assert updated.last_verified is not None
        recent = datetime.fromisoformat(updated.last_verified.rstrip("Z"))
        assert (datetime.utcnow() - recent).total_seconds() < 10

        # Search again should show verified
        results = store.search(intent="refresh test")
        assert results[0].verification_status == "verified"

    def test_no_citations_pattern(self, temp_storage):
        """Patterns without citations get no_citations status."""
        store = PatternStore(
            auto_save=True,
            enable_evolution=False,
            verify_on_search=True,
        )

        # Create pattern with no citations
        pattern = PatternNote(
            name="No Citations Pattern",
            solution_brief="This has no citations",
            trigger_intents=["no citations"],
            citations=[],  # Empty
        )
        store.add(pattern, skip_evolution=True)

        results = store.search(intent="no citations")

        assert len(results) == 1
        assert results[0].verification_status == "no_citations"
        assert any("no citations" in w.lower() for w in results[0].verification_warnings)

    def test_verification_disabled(self, temp_storage):
        """Verification can be disabled per-search or store-wide."""
        sessions_dir = temp_storage["sessions_dir"]

        session_id = "gh_session_disabled"
        self._create_session(sessions_dir, session_id)

        # Store with verification disabled
        store = PatternStore(
            auto_save=True,
            enable_evolution=False,
            verify_on_search=False,
        )

        pattern = PatternNote(
            name="No Verification",
            solution_brief="Verification disabled",
            trigger_intents=["disabled test"],
            citations=[{"session_id": session_id, "outcome": "success"}],
            last_verified=datetime.utcnow().isoformat() + "Z",
        )
        store.add(pattern, skip_evolution=True)

        # Search without verification
        results = store.search(intent="disabled test")

        assert len(results) == 1
        assert results[0].verification_status == "unchecked"

    def test_verify_parameter_overrides(self, temp_storage):
        """verify parameter in search() can override store setting."""
        sessions_dir = temp_storage["sessions_dir"]

        session_id = "gh_session_override"
        self._create_session(sessions_dir, session_id)

        # Store with verification enabled by default
        store = PatternStore(
            auto_save=True,
            enable_evolution=False,
            verify_on_search=True,
        )

        pattern = PatternNote(
            name="Override Test",
            solution_brief="Test verify parameter",
            trigger_intents=["override test"],
            citations=[{"session_id": session_id, "outcome": "success"}],
            last_verified=datetime.utcnow().isoformat() + "Z",
        )
        store.add(pattern, skip_evolution=True)

        # Search with verify=False should skip verification
        results = store.search(intent="override test", verify=False)

        assert len(results) == 1
        assert results[0].verification_status == "unchecked"

    def test_stats_includes_stale_count(self, temp_storage):
        """Stats include stale pattern count."""
        sessions_dir = temp_storage["sessions_dir"]

        session_id = "gh_session_stats"
        self._create_session(sessions_dir, session_id)

        store = PatternStore(
            auto_save=True,
            enable_evolution=False,
            verify_on_search=True,
        )

        # Add fresh pattern
        fresh = PatternNote(
            name="Fresh",
            solution_brief="Fresh",
            trigger_intents=["fresh"],
            last_verified=datetime.utcnow().isoformat() + "Z",
        )
        store.add(fresh, skip_evolution=True)

        # Add stale pattern
        old_date = datetime.utcnow() - timedelta(days=45)
        stale = PatternNote(
            name="Stale",
            solution_brief="Stale",
            trigger_intents=["stale"],
            last_verified=old_date.isoformat() + "Z",
        )
        store.add(stale, skip_evolution=True)

        stats = store.stats()

        assert stats["total_patterns"] == 2
        assert stats["stale_patterns"] == 1
        assert stats["verification_enabled"] is True


class TestVerificationToDict:
    """Test verification info in MCP response format."""

    def test_verification_to_dict(self):
        """Pattern's verification_to_dict() returns correct format."""
        pattern = PatternNote(
            name="Test",
            solution_brief="Test",
            last_verified=datetime.utcnow().isoformat() + "Z",
        )

        # Set verification status
        pattern.set_verification(
            status="verified",
            warnings=["minor warning"],
            days_since=5,
        )

        d = pattern.verification_to_dict()

        assert d["status"] == "verified"
        assert d["last_verified"] is not None
        assert d["days_since_verified"] == 5
        assert d["is_stale"] is False
        assert d["warnings"] == ["minor warning"]

    def test_verification_to_dict_stale(self):
        """Stale pattern shows in verification_to_dict."""
        old_date = datetime.utcnow() - timedelta(days=45)
        pattern = PatternNote(
            name="Stale",
            solution_brief="Stale",
            last_verified=old_date.isoformat() + "Z",
        )

        pattern.set_verification(
            status="stale",
            warnings=["Not verified in 45 days"],
            days_since=45,
        )

        d = pattern.verification_to_dict()

        assert d["status"] == "stale"
        assert d["is_stale"] is True
        assert d["days_since_verified"] == 45
