"""
Phase 5: Testing & Validation Module

Provides tools for validating the contextual MAB system:
- Synthetic test data generation
- A/B comparison framework
- Performance benchmarks
"""

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .context import TOOL_CATEGORIES, GEOMETRY_KEYWORDS, CATEGORY_ORDER

logger = logging.getLogger("rook.validation")


# =============================================================================
# F5.1: Synthetic Test Data Generator
# =============================================================================

# Sample intents for each category
SAMPLE_INTENTS = {
    "create": [
        "create a box at origin",
        "make a sphere with radius 5",
        "draw a cylinder between two points",
        "add a cone to the scene",
        "create a point at 0,0,0",
        "draw a line from start to end",
        "make a circle with center at origin",
        "create a rectangle 10x20",
    ],
    "layer": [
        "create a new layer called walls",
        "make a nested layer structure",
        "delete the empty layer",
        "set layer visibility to off",
        "lock the layer",
        "change current layer",
        "create sublayer under parent",
    ],
    "boolean": [
        "union these two solids",
        "subtract the cylinder from box",
        "intersect the shapes",
        "boolean difference operation",
        "combine solids together",
    ],
    "curve": [
        "join the curves together",
        "explode the polycurve",
        "divide curve into points",
        "extend the line",
        "trim the curve at point",
        "fillet two curves",
        "rebuild the curve",
    ],
    "transform": [
        "move object by vector",
        "rotate 45 degrees around z",
        "scale by factor 2",
        "mirror across plane",
        "copy with offset",
        "translate the selection",
    ],
    "viewport": [
        "capture the viewport",
        "take a screenshot",
        "render the view",
        "get viewport image",
    ],
    "measure": [
        "measure distance between points",
        "calculate the area",
        "get the volume",
        "measure curve length",
        "find bounding box",
        "get centroid",
    ],
    "material": [
        "create a red material",
        "assign material to object",
        "delete unused materials",
        "list all materials",
    ],
    "select": [
        "select all objects",
        "select by layer",
        "select curves only",
        "deselect everything",
        "invert selection",
        "select by name pattern",
    ],
    "document": [
        "save the document",
        "undo last action",
        "redo operation",
        "set units to meters",
        "create new document",
        "get document info",
    ],
}

# Sample tool names by category
TOOLS_BY_CATEGORY = {
    "create": ["rhino_create"],
    "layer": ["rhino_layer_create", "rhino_layer_create_batch", "rhino_layer_delete", "rhino_layer_visibility",
              "rhino_layer_lock", "rhino_layer_current", "rhino_layer_set_properties", "rhino_layer_rename",
              "rhino_layer_move_objects", "rhino_layer_merge", "rhino_layer_dependencies"],
    "boolean": ["rhino_boolean"],
    "curve": ["rhino_curve_ops", "rhino_loft", "rhino_sweep", "rhino_extrude"],
    "transform": ["rhino_transform", "rhino_copy"],
    "viewport": ["rhino_viewport"],
    "measure": ["rhino_measure_distance", "rhino_measure_area", "rhino_measure_volume",
                "rhino_measure_length", "rhino_measure_bbox", "rhino_measure_centroid"],
    "material": ["rhino_material_ops"],
    "select": ["rhino_select", "rhino_selection", "rhino_select_by_type",
               "rhino_select_by_name", "rhino_select_all", "rhino_select_none"],
    "document": ["rhino_document", "rhino_document_ops"],
}

# Sample parameters by geometry type
SAMPLE_PARAMS = {
    "BOX": {"type": "BOX", "origin": [0, 0, 0], "width": 10, "depth": 10, "height": 5},
    "SPHERE": {"type": "SPHERE", "center": [0, 0, 0], "radius": 5},
    "CYLINDER": {"type": "CYLINDER", "center": [0, 0, 0], "radius": 3, "height": 10},
    "CONE": {"type": "CONE", "center": [0, 0, 0], "radius": 4, "height": 8},
    "POINT": {"type": "POINT", "point": [0, 0, 0]},
    "LINE": {"type": "LINE", "start": [0, 0, 0], "end": [10, 0, 0]},
    "CIRCLE": {"type": "CIRCLE", "center": [0, 0, 0], "radius": 5},
    "POLYLINE": {"type": "POLYLINE", "points": [[0, 0, 0], [5, 0, 0], [5, 5, 0]]},
}


def generate_test_scenarios(
    n_scenarios: int = 100,
    seed: int = 42,
    categories: list[str] | None = None
) -> list[dict[str, Any]]:
    """
    Generate diverse test scenarios for validation.

    Args:
        n_scenarios: Number of scenarios to generate
        seed: Random seed for reproducibility
        categories: Optional list of categories to include (all if None)

    Returns:
        List of scenario dictionaries with intent, tool, params, expected_category
    """
    random.seed(seed)

    # Use all categories if not specified
    target_categories = categories or list(CATEGORY_ORDER)

    scenarios = []

    # Ensure coverage of all categories
    scenarios_per_category = max(1, n_scenarios // len(target_categories))

    for category in target_categories:
        intents = SAMPLE_INTENTS.get(category, [f"perform {category} operation"])
        tools = TOOLS_BY_CATEGORY.get(category, [f"rhino_{category}"])

        for i in range(scenarios_per_category):
            intent = random.choice(intents)
            tool = random.choice(tools)

            # Generate params based on tool type
            if tool == "rhino_create":
                geom_type = random.choice(list(SAMPLE_PARAMS.keys()))
                params = SAMPLE_PARAMS[geom_type].copy()
            elif "layer" in tool:
                params = {"name": f"test_layer_{i}"}
            elif tool == "rhino_boolean":
                params = {"operation": random.choice(["union", "difference", "intersection"])}
            elif tool == "rhino_transform":
                params = {"operation": random.choice(["move", "rotate", "scale"])}
            else:
                params = {}

            scenarios.append({
                "id": f"scenario_{len(scenarios)}",
                "intent": intent,
                "tool": tool,
                "params": params,
                "expected_category": category,
                "expected_outcome": random.choice(["success", "success", "success", "failure"])
            })

    # Shuffle and trim to exact count
    random.shuffle(scenarios)
    return scenarios[:n_scenarios]


def get_category_coverage(scenarios: list[dict]) -> dict[str, int]:
    """Get coverage statistics for scenarios."""
    coverage = {cat: 0 for cat in CATEGORY_ORDER}
    for s in scenarios:
        cat = s.get("expected_category")
        if cat in coverage:
            coverage[cat] += 1
    return coverage


# =============================================================================
# F5.2: A/B Comparison Framework
# =============================================================================

@dataclass
class ComparisonResult:
    """Result of comparing two systems on a scenario."""
    scenario_id: str
    baseline_patterns: list[dict]
    challenger_patterns: list[dict]
    baseline_latency_ms: float
    challenger_latency_ms: float
    baseline_confidence: float
    challenger_confidence: float


@dataclass
class ABComparisonMetrics:
    """Aggregated metrics from A/B comparison."""
    n_scenarios: int
    baseline_avg_latency_ms: float
    challenger_avg_latency_ms: float
    baseline_avg_confidence: float
    challenger_avg_confidence: float
    baseline_avg_patterns: float
    challenger_avg_patterns: float
    latency_improvement_pct: float
    confidence_improvement_pct: float


class ABComparison:
    """
    Compare two knowledge query strategies.

    Usage:
        comparison = ABComparison(baseline_fn, challenger_fn)
        comparison.run_scenarios(scenarios)
        metrics = comparison.compute_metrics()
    """

    def __init__(
        self,
        baseline_fn: Callable[[str, str, dict], dict],
        challenger_fn: Callable[[str, str, dict], dict]
    ):
        """
        Initialize A/B comparison.

        Args:
            baseline_fn: Baseline query function (intent, tool, params) -> result
            challenger_fn: Challenger query function with same signature
        """
        self.baseline_fn = baseline_fn
        self.challenger_fn = challenger_fn
        self.results: list[ComparisonResult] = []

    def run_scenario(self, scenario: dict) -> ComparisonResult:
        """Run single scenario through both systems."""
        intent = scenario.get("intent", "")
        tool = scenario.get("tool", "")
        params = scenario.get("params", {})

        # Run baseline
        start = time.perf_counter()
        baseline_result = self.baseline_fn(intent, tool, params)
        baseline_latency = (time.perf_counter() - start) * 1000

        # Run challenger
        start = time.perf_counter()
        challenger_result = self.challenger_fn(intent, tool, params)
        challenger_latency = (time.perf_counter() - start) * 1000

        result = ComparisonResult(
            scenario_id=scenario.get("id", "unknown"),
            baseline_patterns=baseline_result.get("patterns", []),
            challenger_patterns=challenger_result.get("patterns", []),
            baseline_latency_ms=baseline_latency,
            challenger_latency_ms=challenger_latency,
            baseline_confidence=baseline_result.get("confidence", 0.0),
            challenger_confidence=challenger_result.get("confidence", 0.0)
        )

        self.results.append(result)
        return result

    def run_scenarios(self, scenarios: list[dict]) -> list[ComparisonResult]:
        """Run all scenarios through both systems."""
        for scenario in scenarios:
            self.run_scenario(scenario)
        return self.results

    def compute_metrics(self) -> ABComparisonMetrics:
        """Compute aggregated comparison metrics."""
        if not self.results:
            return ABComparisonMetrics(
                n_scenarios=0,
                baseline_avg_latency_ms=0.0,
                challenger_avg_latency_ms=0.0,
                baseline_avg_confidence=0.0,
                challenger_avg_confidence=0.0,
                baseline_avg_patterns=0.0,
                challenger_avg_patterns=0.0,
                latency_improvement_pct=0.0,
                confidence_improvement_pct=0.0
            )

        n = len(self.results)

        baseline_latency = sum(r.baseline_latency_ms for r in self.results) / n
        challenger_latency = sum(r.challenger_latency_ms for r in self.results) / n
        baseline_confidence = sum(r.baseline_confidence for r in self.results) / n
        challenger_confidence = sum(r.challenger_confidence for r in self.results) / n
        baseline_patterns = sum(len(r.baseline_patterns) for r in self.results) / n
        challenger_patterns = sum(len(r.challenger_patterns) for r in self.results) / n

        # Calculate improvements (negative latency improvement is good)
        latency_improvement = ((baseline_latency - challenger_latency) / baseline_latency * 100
                               if baseline_latency > 0 else 0.0)
        confidence_improvement = ((challenger_confidence - baseline_confidence) / baseline_confidence * 100
                                  if baseline_confidence > 0 else 0.0)

        return ABComparisonMetrics(
            n_scenarios=n,
            baseline_avg_latency_ms=round(baseline_latency, 3),
            challenger_avg_latency_ms=round(challenger_latency, 3),
            baseline_avg_confidence=round(baseline_confidence, 3),
            challenger_avg_confidence=round(challenger_confidence, 3),
            baseline_avg_patterns=round(baseline_patterns, 2),
            challenger_avg_patterns=round(challenger_patterns, 2),
            latency_improvement_pct=round(latency_improvement, 2),
            confidence_improvement_pct=round(confidence_improvement, 2)
        )

    def clear_results(self):
        """Clear accumulated results."""
        self.results = []


# =============================================================================
# F5.4: Performance Benchmarks
# =============================================================================

@dataclass
class LatencyStats:
    """Latency statistics from benchmark."""
    n_samples: int
    p50_ms: float
    p90_ms: float
    p99_ms: float
    mean_ms: float
    min_ms: float
    max_ms: float


def benchmark_query_latency(
    query_fn: Callable[[str, str, dict], dict],
    scenarios: list[dict],
    n_iterations: int = 1
) -> LatencyStats:
    """
    Benchmark query performance.

    Args:
        query_fn: Query function to benchmark
        scenarios: Test scenarios to run
        n_iterations: Number of iterations per scenario

    Returns:
        LatencyStats with percentile measurements
    """
    latencies = []

    for scenario in scenarios:
        intent = scenario.get("intent", "")
        tool = scenario.get("tool", "")
        params = scenario.get("params", {})

        for _ in range(n_iterations):
            start = time.perf_counter()
            query_fn(intent, tool, params)
            latency_ms = (time.perf_counter() - start) * 1000
            latencies.append(latency_ms)

    if not latencies:
        return LatencyStats(0, 0, 0, 0, 0, 0, 0)

    latencies.sort()
    n = len(latencies)

    return LatencyStats(
        n_samples=n,
        p50_ms=round(latencies[int(n * 0.50)], 3),
        p90_ms=round(latencies[int(n * 0.90)], 3),
        p99_ms=round(latencies[min(int(n * 0.99), n - 1)], 3),
        mean_ms=round(sum(latencies) / n, 3),
        min_ms=round(min(latencies), 3),
        max_ms=round(max(latencies), 3)
    )


def benchmark_record_latency(
    record_fn: Callable[[str, dict, str], dict],
    scenarios: list[dict],
    n_iterations: int = 1
) -> LatencyStats:
    """
    Benchmark record performance.

    Args:
        record_fn: Record function to benchmark
        scenarios: Test scenarios to run
        n_iterations: Number of iterations per scenario

    Returns:
        LatencyStats with percentile measurements
    """
    latencies = []

    for scenario in scenarios:
        intent = scenario.get("intent", "")
        tool = scenario.get("tool", "")
        params = scenario.get("params", {})
        outcome = scenario.get("expected_outcome", "success")

        action = {"tool": tool, "params": params}

        for _ in range(n_iterations):
            start = time.perf_counter()
            record_fn(intent, action, outcome)
            latency_ms = (time.perf_counter() - start) * 1000
            latencies.append(latency_ms)

    if not latencies:
        return LatencyStats(0, 0, 0, 0, 0, 0, 0)

    latencies.sort()
    n = len(latencies)

    return LatencyStats(
        n_samples=n,
        p50_ms=round(latencies[int(n * 0.50)], 3),
        p90_ms=round(latencies[int(n * 0.90)], 3),
        p99_ms=round(latencies[min(int(n * 0.99), n - 1)], 3),
        mean_ms=round(sum(latencies) / n, 3),
        min_ms=round(min(latencies), 3),
        max_ms=round(max(latencies), 3)
    )


def check_latency_targets(
    stats: LatencyStats,
    p50_target_ms: float = 10.0,
    p99_target_ms: float = 50.0
) -> tuple[bool, str]:
    """
    Check if latency meets targets.

    Args:
        stats: Latency statistics
        p50_target_ms: Target for 50th percentile
        p99_target_ms: Target for 99th percentile

    Returns:
        (passes, message) tuple
    """
    p50_ok = stats.p50_ms <= p50_target_ms
    p99_ok = stats.p99_ms <= p99_target_ms

    if p50_ok and p99_ok:
        return True, f"Latency OK: p50={stats.p50_ms}ms <= {p50_target_ms}ms, p99={stats.p99_ms}ms <= {p99_target_ms}ms"

    issues = []
    if not p50_ok:
        issues.append(f"p50={stats.p50_ms}ms > {p50_target_ms}ms")
    if not p99_ok:
        issues.append(f"p99={stats.p99_ms}ms > {p99_target_ms}ms")

    return False, f"Latency FAILED: {', '.join(issues)}"
