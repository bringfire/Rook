"""
Bootstrap Test Runner

Executes test cases and records outcomes using the production knowledge API.
This ensures bootstrap testing validates the actual MAB system.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .test_matrix import TestCase, TestPhase, ExpectedOutcome, TOOL_TESTS

# Import the production knowledge API
from ..knowledge import record_knowledge, get_learning_summary
from ..runtime_paths import resolve_writable_knowledge_path
from ..tool_lifecycle_runtime import DispatchOrigin, deny_if_contained

logger = logging.getLogger("rook.bootstrap")

# Paths for run logs (separate from the bundled knowledge payload)
RUN_LOG_PATH = resolve_writable_knowledge_path("local", "run_log.json")


class TestOutcome(Enum):
    """Actual outcome of a test."""
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"  # Test itself failed to run
    SKIPPED = "skipped"  # Dependency not met


@dataclass
class TestResult:
    """Result of running a single test case."""
    test_id: str
    tool: str
    params: dict[str, Any]
    expected: ExpectedOutcome
    actual: TestOutcome
    response: dict[str, Any] | None
    error_message: str | None
    duration_ms: float
    timestamp: str
    created_object_ids: list[str] = field(default_factory=list)

    def matches_expectation(self) -> bool:
        """Check if actual outcome matches expected."""
        if self.expected == ExpectedOutcome.EITHER:
            return self.actual in (TestOutcome.SUCCESS, TestOutcome.FAILURE)
        return self.actual.value == self.expected.value

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "test_id": self.test_id,
            "tool": self.tool,
            "params": self.params,
            "expected": self.expected.value,
            "actual": self.actual.value,
            "response": self.response,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "created_object_ids": self.created_object_ids,
            "matches_expectation": self.matches_expectation(),
        }


@dataclass
class BootstrapSession:
    """Tracks a bootstrap testing session."""
    session_id: str
    phase: TestPhase
    started_at: str
    results: list[TestResult] = field(default_factory=list)
    completed_at: str | None = None

    def add_result(self, result: TestResult):
        """Add a test result."""
        self.results.append(result)

    def get_summary(self) -> dict[str, Any]:
        """Get session summary statistics."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.matches_expectation())
        successes = sum(1 for r in self.results if r.actual == TestOutcome.SUCCESS)
        failures = sum(1 for r in self.results if r.actual == TestOutcome.FAILURE)
        errors = sum(1 for r in self.results if r.actual == TestOutcome.ERROR)
        skipped = sum(1 for r in self.results if r.actual == TestOutcome.SKIPPED)

        return {
            "session_id": self.session_id,
            "phase": self.phase.name,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_tests": total,
            "passed": passed,
            "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
            "successes": successes,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "phase": self.phase.name,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "results": [r.to_dict() for r in self.results],
            "summary": self.get_summary(),
        }


class BootstrapRunner:
    """
    Executes bootstrap tests and records to local knowledge graph.

    Usage:
        runner = BootstrapRunner(tool_executor)
        session = runner.run_phase(TestPhase.PHASE_1_QUERY)
        runner.save_session(session)
    """

    def __init__(self, tool_executor=None):
        """
        Initialize runner.

        Args:
            tool_executor: Callable that executes MCP tools.
                           Signature: (tool_name: str, params: dict) -> dict
                           If None, uses mock executor for testing.
        """
        self.tool_executor = tool_executor or self._mock_executor
        self.completed_tests: set[str] = set()
        self._load_completed_tests()

    def _mock_executor(self, tool_name: str, params: dict) -> dict:
        """Mock executor for testing the runner itself."""
        denial = deny_if_contained(tool_name, DispatchOrigin.INTERNAL_HANDLER)
        if denial is not None:
            return denial
        logger.warning(f"Using mock executor for {tool_name}")
        return {"success": True, "data": {"mock": True}}

    def _load_completed_tests(self):
        """Load IDs of previously completed tests."""
        if RUN_LOG_PATH.exists():
            try:
                data = json.loads(RUN_LOG_PATH.read_text(encoding="utf-8"))
                for session in data.get("sessions", []):
                    for result in session.get("results", []):
                        self.completed_tests.add(result.get("test_id"))
            except Exception as e:
                logger.warning(f"Failed to load run log: {e}")

    def check_dependencies(self, test: TestCase) -> bool:
        """Check if all test dependencies are satisfied."""
        for dep_id in test.depends_on:
            if dep_id not in self.completed_tests:
                return False
        return True

    def run_test(self, test: TestCase) -> TestResult:
        """Run a single test case."""
        denial = deny_if_contained(test.tool, DispatchOrigin.INTERNAL_HANDLER)
        if denial is not None:
            return TestResult(
                test_id=test.id,
                tool=test.tool,
                params={},
                expected=test.expected,
                actual=TestOutcome.FAILURE,
                response=denial,
                error_message="legacy_semantic_tool_contained",
                duration_ms=0,
                timestamp=datetime.now().isoformat(),
            )
        # Check dependencies
        if not self.check_dependencies(test):
            return TestResult(
                test_id=test.id,
                tool=test.tool,
                params=test.params,
                expected=test.expected,
                actual=TestOutcome.SKIPPED,
                response=None,
                error_message=f"Dependencies not met: {test.depends_on}",
                duration_ms=0,
                timestamp=datetime.now().isoformat(),
            )

        # Execute the test
        start_time = time.perf_counter()
        try:
            response = self.tool_executor(test.tool, test.params)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Determine outcome
            success = response.get("success", False)
            actual = TestOutcome.SUCCESS if success else TestOutcome.FAILURE

            # Extract created object IDs if any
            created_ids = []
            data = response.get("data", {})
            if isinstance(data, dict):
                if "id" in data:
                    created_ids.append(data["id"])
                elif "ids" in data:
                    created_ids.extend(data["ids"])

            result = TestResult(
                test_id=test.id,
                tool=test.tool,
                params=test.params,
                expected=test.expected,
                actual=actual,
                response=response,
                error_message=None if success else str(data),
                duration_ms=round(duration_ms, 2),
                timestamp=datetime.now().isoformat(),
                created_object_ids=created_ids,
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            result = TestResult(
                test_id=test.id,
                tool=test.tool,
                params=test.params,
                expected=test.expected,
                actual=TestOutcome.ERROR,
                response=None,
                error_message=str(e),
                duration_ms=round(duration_ms, 2),
                timestamp=datetime.now().isoformat(),
            )

        # Mark as completed
        self.completed_tests.add(test.id)
        return result

    def run_phase(self, phase: TestPhase) -> BootstrapSession:
        """Run all tests for a phase."""
        session = BootstrapSession(
            session_id=f"{phase.name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            phase=phase,
            started_at=datetime.now().isoformat(),
        )

        tests = TOOL_TESTS.get_phase(phase)
        logger.info(f"Running {len(tests)} tests for {phase.name}")

        for test in tests:
            logger.info(f"Running test {test.id}: {test.description}")
            result = self.run_test(test)
            session.add_result(result)

            status = "✓" if result.matches_expectation() else "✗"
            logger.info(f"  {status} {result.actual.value} (expected {result.expected.value})")

        session.completed_at = datetime.now().isoformat()
        return session

    def record_to_knowledge(self, session: BootstrapSession):
        """
        Record session results using the production knowledge API.

        This ensures:
        1. Patterns are added to the actual knowledge graph
        2. Context-free MAB is updated via partial_fit()
        3. Context observations are stored for contextual MAB
        4. The production system is validated during bootstrap
        """
        recordings = []

        for result in session.results:
            test = TOOL_TESTS.get_by_id(result.test_id)
            if not test:
                continue

            # Skip errors and skipped tests
            if result.actual in (TestOutcome.ERROR, TestOutcome.SKIPPED):
                continue

            # Build intent string with rich context
            intent = test.intent
            if test.learn_on_success and result.actual == TestOutcome.SUCCESS:
                # Append the learning note to make intent more descriptive
                intent = f"{test.intent} - {test.learn_on_success}"
            elif test.learn_on_failure and result.actual == TestOutcome.FAILURE:
                intent = f"{test.intent} - {test.learn_on_failure}"

            # Build action dict with actual params used
            action = {
                "tool": result.tool,
                "params": result.params
            }

            # Add response data if available (for richer learning)
            if result.response and result.response.get("data"):
                # Include successful response structure for future reference
                action["response_sample"] = result.response.get("data")

            # Record to production knowledge API
            outcome = "success" if result.actual == TestOutcome.SUCCESS else "failure"

            try:
                record_result = record_knowledge(
                    intent=intent,
                    action=action,
                    outcome=outcome
                )
                recordings.append({
                    "test_id": result.test_id,
                    "recorded": record_result.get("success", False),
                    "mab_updated": record_result.get("mab_updated", False),
                    "context_recorded": record_result.get("context_recorded", False),
                })

                if record_result.get("success"):
                    logger.info(f"  Recorded {outcome} for {result.test_id} via knowledge API")
                else:
                    logger.warning(f"  Failed to record {result.test_id}: {record_result}")

            except Exception as e:
                logger.error(f"  Error recording {result.test_id}: {e}")
                recordings.append({
                    "test_id": result.test_id,
                    "recorded": False,
                    "error": str(e)
                })

        # Log summary
        successful = sum(1 for r in recordings if r.get("recorded"))
        mab_updates = sum(1 for r in recordings if r.get("mab_updated"))
        context_records = sum(1 for r in recordings if r.get("context_recorded"))

        logger.info(f"Recorded {successful}/{len(recordings)} observations to knowledge graph")
        logger.info(f"  MAB updated: {mab_updates}, Context recorded: {context_records}")

        # Return summary for session tracking
        return {
            "total": len(recordings),
            "successful": successful,
            "mab_updates": mab_updates,
            "context_records": context_records,
            "recordings": recordings
        }

    def save_session(self, session: BootstrapSession):
        """Save session to run log."""
        RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        if RUN_LOG_PATH.exists():
            run_log = json.loads(RUN_LOG_PATH.read_text(encoding="utf-8"))
        else:
            run_log = {"sessions": []}

        run_log["sessions"].append(session.to_dict())
        run_log["last_updated"] = datetime.now().isoformat()

        RUN_LOG_PATH.write_text(json.dumps(run_log, indent=2), encoding="utf-8")
        logger.info(f"Saved session {session.session_id} to run log")

    def get_phase_status(self) -> dict[str, Any]:
        """Get status of all phases."""
        status = {}
        for phase in TestPhase:
            tests = TOOL_TESTS.get_phase(phase)
            completed = sum(1 for t in tests if t.id in self.completed_tests)
            status[phase.name] = {
                "total": len(tests),
                "completed": completed,
                "remaining": len(tests) - completed,
                "complete": completed == len(tests),
            }
        return status

    def cleanup_created_objects(self, session: BootstrapSession, delete_executor=None):
        """Delete objects created during testing."""
        if delete_executor is None:
            delete_executor = self.tool_executor

        all_ids = []
        for result in session.results:
            all_ids.extend(result.created_object_ids)

        if all_ids:
            logger.info(f"Cleaning up {len(all_ids)} created objects")
            try:
                delete_executor("rhino_delete", {"ids": all_ids})
            except Exception as e:
                logger.error(f"Cleanup failed: {e}")


def get_knowledge_summary() -> dict[str, Any]:
    """Get summary of the production knowledge system."""
    try:
        summary = get_learning_summary()
        return {
            "exists": True,
            "knowledge_graph": summary.get("knowledge_graph", {}),
            "mab": summary.get("mab", {}),
            "contextual_mab": summary.get("contextual_mab", {}),
            "context_history": summary.get("context_history", {}),
        }
    except Exception as e:
        logger.error(f"Failed to get knowledge summary: {e}")
        return {"exists": False, "error": str(e)}
