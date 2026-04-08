"""
Result Analyzer - Analyzes execution results and extracts learnings.
"""

import logging
from typing import Any
from dataclasses import dataclass

from .executor import ExecutionResult

logger = logging.getLogger("explorer.analyzer")


@dataclass
class AnalysisResult:
    """Result of analyzing an execution."""
    tool_name: str
    params: dict[str, Any]
    success: bool
    pattern_learned: str | None = None
    antipattern_learned: str | None = None
    notes: list[str] = None

    def __post_init__(self):
        if self.notes is None:
            self.notes = []


class ResultAnalyzer:
    """
    Analyzes execution results to extract learnings.
    Identifies patterns, antipatterns, and interesting observations.
    """

    # Common error patterns and their meanings
    ERROR_PATTERNS = {
        "Object not found": "Object ID does not exist in document",
        "Layer not found": "Layer name does not exist",
        "Invalid geometry": "Geometry parameters are invalid",
        "Connection refused": "Rhino is not running",
        "Timeout": "Operation took too long",
        "null reference": "Required object was not provided",
        "Index out of range": "Array index is invalid",
    }

    def analyze(self, result: ExecutionResult) -> AnalysisResult:
        """Analyze an execution result and extract learnings."""
        analysis = AnalysisResult(
            tool_name=result.tool_name,
            params=result.params,
            success=result.success,
        )

        if result.success:
            analysis.pattern_learned = self._extract_pattern(result)
            analysis.notes.append(f"Succeeded with params: {list(result.params.keys())}")
        else:
            analysis.antipattern_learned = self._extract_antipattern(result)
            analysis.notes.append(f"Failed: {result.error}")

        # Add any special observations
        self._add_observations(result, analysis)

        return analysis

    def _extract_pattern(self, result: ExecutionResult) -> str | None:
        """Extract a pattern description from a successful execution."""
        tool_name = result.tool_name
        params = result.params

        if not params:
            return f"{tool_name} works with no parameters"

        required = list(params.keys())
        return f"{tool_name} works with params: {required}"

    def _extract_antipattern(self, result: ExecutionResult) -> str | None:
        """Extract an antipattern description from a failed execution."""
        tool_name = result.tool_name
        error = result.error or "Unknown error"

        # Handle dict errors (convert to string)
        if isinstance(error, dict):
            error = str(error)

        # Check for known error patterns
        for pattern, meaning in self.ERROR_PATTERNS.items():
            if pattern.lower() in error.lower():
                return f"{tool_name}: {meaning}"

        return f"{tool_name} fails with: {error}"

    def _add_observations(self, result: ExecutionResult, analysis: AnalysisResult) -> None:
        """Add interesting observations to the analysis."""
        response = result.response

        if not isinstance(response, dict):
            return

        data = response.get("data")
        if not data:
            return

        # Check for interesting response patterns
        if isinstance(data, dict):
            # Created object - note the returned ID
            if "id" in data:
                analysis.notes.append(f"Returns object ID: {data['id'][:8]}...")

            # Multiple objects created
            if "ids" in data and isinstance(data["ids"], list):
                analysis.notes.append(f"Returns {len(data['ids'])} object IDs")

            # Measurements
            if "distance" in data:
                analysis.notes.append(f"Distance: {data['distance']}")
            if "area" in data:
                analysis.notes.append(f"Area: {data['area']}")
            if "volume" in data:
                analysis.notes.append(f"Volume: {data['volume']}")

        elif isinstance(data, list):
            analysis.notes.append(f"Returns list with {len(data)} items")

    def summarize_batch(self, results: list[ExecutionResult]) -> dict[str, Any]:
        """Summarize a batch of execution results."""
        total = len(results)
        successes = sum(1 for r in results if r.success)
        failures = total - successes

        tools_tested = set(r.tool_name for r in results)
        failed_tools = set(r.tool_name for r in results if not r.success)

        avg_duration = sum(r.duration_ms for r in results) / total if total > 0 else 0

        return {
            "total": total,
            "successes": successes,
            "failures": failures,
            "success_rate": (successes / total * 100) if total > 0 else 0,
            "tools_tested": len(tools_tested),
            "failed_tools": list(failed_tools),
            "avg_duration_ms": round(avg_duration, 2),
        }
