"""
Pattern Verifier - Just-in-Time verification for pattern citations.

Provides:
- PatternVerifier: Verifies pattern citations against session history
- VerificationResult: Result of verification check
- StalenessPolicy: Configurable staleness thresholds

Part of Phase 3 of the meta-learning system.
Implements the GitHub Copilot-inspired insight:
"Information retrieval is asymmetrical: It's hard to solve, but easy to verify."
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional
import json

logger = logging.getLogger("rook.pattern_verifier")

# Import shared types and constants from pattern_memory
from .pattern_memory import (
    VerificationStatus,
    STALENESS_HIGH_CONFIDENCE_DAYS,
    STALENESS_DEFAULT_DAYS,
    STALENESS_LOW_CONFIDENCE_DAYS,
)


@dataclass
class VerificationResult:
    """Result of verifying a pattern's citations.

    Returned by PatternVerifier.verify() with details about
    the verification process and outcome.
    """

    pattern_id: str
    """ID of the verified pattern."""

    status: VerificationStatus
    """Verification status:
    - verified: At least one valid citation exists and pattern is not stale
    - stale: Citations exist but pattern hasn't been verified recently
    - unverifiable: Citations point to non-existent sessions
    - no_citations: Pattern has no citations to verify
    """

    # Existence check results
    citations_checked: int = 0
    """Number of citations checked."""

    citations_valid: int = 0
    """Number of citations with existing sessions."""

    # Staleness info
    days_since_verified: Optional[int] = None
    """Days since last successful verification (None if never verified)."""

    needs_reverification: bool = False
    """True if pattern should be re-verified (stale or low confidence)."""

    # For consistency checks
    consistency_checked: bool = False
    """Whether consistency check was performed."""

    consistency_passed: Optional[bool] = None
    """Result of consistency check (None if not checked)."""

    # Messages
    warnings: list[str] = field(default_factory=list)
    """Warning messages about verification issues."""

    def to_dict(self) -> dict:
        """Convert to dict for MCP response."""
        return {
            "status": self.status,
            "citations_checked": self.citations_checked,
            "citations_valid": self.citations_valid,
            "days_since_verified": self.days_since_verified,
            "needs_reverification": self.needs_reverification,
            "warnings": self.warnings,
        }


class StalenessPolicy:
    """Policy for determining when patterns need re-verification.

    Higher confidence patterns get longer grace periods before
    being marked as stale.

    Thresholds are defined in pattern_memory.py (single source of truth):
    - STALENESS_HIGH_CONFIDENCE_DAYS (60): >80% success rate
    - STALENESS_DEFAULT_DAYS (30): 50-80% success rate
    - STALENESS_LOW_CONFIDENCE_DAYS (14): <50% success rate
    """

    # Reference module-level constants for backward compatibility
    DEFAULT_DAYS = STALENESS_DEFAULT_DAYS
    HIGH_CONFIDENCE_DAYS = STALENESS_HIGH_CONFIDENCE_DAYS
    LOW_CONFIDENCE_DAYS = STALENESS_LOW_CONFIDENCE_DAYS

    @classmethod
    def get_threshold_days(cls, success_rate: float) -> int:
        """Get staleness threshold based on pattern confidence.

        Args:
            success_rate: Pattern's success rate (0.0 to 1.0)

        Returns:
            Number of days before pattern is considered stale
        """
        if success_rate >= 0.8:
            return STALENESS_HIGH_CONFIDENCE_DAYS
        elif success_rate < 0.5:
            return STALENESS_LOW_CONFIDENCE_DAYS
        return STALENESS_DEFAULT_DAYS


class PatternVerifier:
    """Just-in-Time verification for pattern citations.

    Implements verification levels:
    - Existence: Check if cited sessions still exist (fast, always done)
    - Consistency: Check if pattern matches session outcomes (low cost)

    Usage:
        verifier = PatternVerifier(sessions_dir)
        result = verifier.verify(pattern)
        if result.status == "verified":
            # Pattern is trustworthy
        elif result.status == "stale":
            # Pattern needs re-verification
    """

    def __init__(self, sessions_dir: Path):
        """Initialize the verifier.

        Args:
            sessions_dir: Path to session storage directory
        """
        self.sessions_dir = sessions_dir
        self.active_dir = sessions_dir / "_active"

    def _session_exists(self, session_id: str) -> bool:
        """Check if a session file exists.

        Args:
            session_id: Session ID to check

        Returns:
            True if session file exists
        """
        # Check completed sessions
        completed_path = self.sessions_dir / f"{session_id}.json"
        if completed_path.exists():
            return True

        # Check active sessions (scan for matching session_id in files)
        if self.active_dir.exists():
            for active_path in self.active_dir.glob("*.json"):
                try:
                    with open(active_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("session_id") == session_id:
                        return True
                except Exception:
                    continue

        return False

    def _load_session(self, session_id: str) -> Optional[dict]:
        """Load session data for consistency checks.

        Args:
            session_id: Session ID to load

        Returns:
            Session data dict or None if not found
        """
        # Try completed sessions first
        completed_path = self.sessions_dir / f"{session_id}.json"
        if completed_path.exists():
            try:
                with open(completed_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load session {session_id}: {e}")
                return None

        # Try active sessions
        if self.active_dir.exists():
            for active_path in self.active_dir.glob("*.json"):
                try:
                    with open(active_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("session_id") == session_id:
                        return data
                except Exception:
                    continue

        return None

    def _calculate_days_since(self, iso_timestamp: Optional[str]) -> Optional[int]:
        """Calculate days since a timestamp.

        Args:
            iso_timestamp: ISO format timestamp string

        Returns:
            Days since timestamp, or None if timestamp is invalid
        """
        if not iso_timestamp:
            return None

        try:
            # Handle Z suffix
            timestamp_str = iso_timestamp.rstrip("Z")
            timestamp = datetime.fromisoformat(timestamp_str)
            delta = datetime.utcnow() - timestamp
            return delta.days
        except (ValueError, TypeError):
            return None

    def verify_existence(self, pattern) -> VerificationResult:
        """Level 1: Check if cited sessions still exist.

        Fast verification that just checks file existence.
        No session content is loaded.

        Args:
            pattern: PatternNote to verify

        Returns:
            VerificationResult with existence check results
        """
        from .pattern_memory import PatternNote

        if not isinstance(pattern, PatternNote):
            raise TypeError(f"Expected PatternNote, got {type(pattern)}")

        citations = pattern.citations
        warnings = []

        # No citations case
        if not citations:
            return VerificationResult(
                pattern_id=pattern.pattern_id,
                status="no_citations",
                citations_checked=0,
                citations_valid=0,
                warnings=["Pattern has no citations to verify"],
            )

        # Check each citation
        valid_count = 0
        for citation in citations:
            session_id = citation.get("session_id")
            if session_id and self._session_exists(session_id):
                valid_count += 1
            elif session_id:
                warnings.append(f"Session {session_id} no longer exists")

        # Calculate staleness
        days_since = self._calculate_days_since(pattern.last_verified)
        threshold = StalenessPolicy.get_threshold_days(pattern.success_rate())
        is_stale = days_since is None or days_since > threshold

        # Determine status
        if valid_count == 0:
            status: VerificationStatus = "unverifiable"
            warnings.append("All cited sessions are missing")
        elif is_stale:
            status = "stale"
            if days_since is not None:
                warnings.append(f"Pattern not verified in {days_since} days (threshold: {threshold})")
            else:
                warnings.append("Pattern has never been verified")
        else:
            status = "verified"

        return VerificationResult(
            pattern_id=pattern.pattern_id,
            status=status,
            citations_checked=len(citations),
            citations_valid=valid_count,
            days_since_verified=days_since,
            needs_reverification=is_stale,
            warnings=warnings,
        )

    def verify_consistency(self, pattern) -> VerificationResult:
        """Level 2: Check if pattern matches session outcomes.

        Loads session content and checks if the pattern's claimed
        outcome matches what actually happened in the session.

        More expensive than existence check but provides stronger
        verification.

        Args:
            pattern: PatternNote to verify

        Returns:
            VerificationResult with consistency check results
        """
        from .pattern_memory import PatternNote

        if not isinstance(pattern, PatternNote):
            raise TypeError(f"Expected PatternNote, got {type(pattern)}")

        # Start with existence check
        result = self.verify_existence(pattern)

        # If unverifiable or no citations, can't do consistency
        if result.status in ("unverifiable", "no_citations"):
            result.consistency_checked = False
            return result

        # Check consistency for valid citations
        result.consistency_checked = True
        consistency_failures = 0

        for citation in pattern.citations:
            session_id = citation.get("session_id")
            if not session_id:
                continue

            session_data = self._load_session(session_id)
            if not session_data:
                continue

            # Check if claimed outcome matches session summary
            claimed_outcome = citation.get("outcome")
            if claimed_outcome == "success":
                # For success claims, check session had successes
                summary = session_data.get("summary", {})
                actual_successes = summary.get("successes", 0)
                if actual_successes == 0:
                    consistency_failures += 1
                    result.warnings.append(
                        f"Citation claims success but session {session_id} had no successes"
                    )

            # Check entry range if provided
            entry_range = citation.get("entry_range")
            if entry_range and len(entry_range) == 2:
                entries = session_data.get("entries", [])
                start_id, end_id = entry_range

                # Verify entries exist
                entry_ids = {e.get("entry_id") for e in entries}
                if start_id not in entry_ids or end_id not in entry_ids:
                    consistency_failures += 1
                    result.warnings.append(
                        f"Entry range [{start_id}, {end_id}] not found in session {session_id}"
                    )

        # Determine consistency result
        if consistency_failures == 0:
            result.consistency_passed = True
        else:
            result.consistency_passed = False
            # Downgrade status if consistency failed
            if result.status == "verified":
                result.status = "stale"
                result.needs_reverification = True

        return result

    def check_staleness(self, pattern) -> tuple[bool, Optional[int]]:
        """Check if pattern is stale (needs re-verification).

        Args:
            pattern: PatternNote to check

        Returns:
            Tuple of (is_stale, days_since_verified)
        """
        from .pattern_memory import PatternNote

        if not isinstance(pattern, PatternNote):
            raise TypeError(f"Expected PatternNote, got {type(pattern)}")

        days_since = self._calculate_days_since(pattern.last_verified)
        threshold = StalenessPolicy.get_threshold_days(pattern.success_rate())

        if days_since is None:
            return True, None

        return days_since > threshold, days_since

    def verify(
        self,
        pattern,
        level: Literal["existence", "consistency"] = "existence",
    ) -> VerificationResult:
        """Main verification entry point.

        Args:
            pattern: PatternNote to verify
            level: Verification level:
                - "existence": Fast check if sessions exist
                - "consistency": Also checks if outcomes match

        Returns:
            VerificationResult with verification details
        """
        if level == "consistency":
            return self.verify_consistency(pattern)
        return self.verify_existence(pattern)


# Singleton instance
_verifier: Optional[PatternVerifier] = None


def get_pattern_verifier(sessions_dir: Optional[Path] = None) -> PatternVerifier:
    """Get or create the global pattern verifier.

    Args:
        sessions_dir: Override sessions directory (for testing)

    Returns:
        PatternVerifier singleton instance
    """
    global _verifier

    if sessions_dir is not None:
        # Custom directory - create new instance
        return PatternVerifier(sessions_dir)

    if _verifier is None:
        # Use default sessions directory
        # Import module to get current attribute value (supports patching)
        from . import gh_session_history
        _verifier = PatternVerifier(gh_session_history.SESSIONS_DIR)

    return _verifier
