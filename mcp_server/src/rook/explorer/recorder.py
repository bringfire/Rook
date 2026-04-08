"""
Knowledge Recorder - Records exploration outcomes to the knowledge graph.
"""

import logging
from typing import Any

from .executor import ExecutionResult
from .analyzer import AnalysisResult

logger = logging.getLogger("explorer.recorder")


class KnowledgeRecorder:
    """
    Records exploration outcomes to the knowledge graph.
    Uses the existing knowledge.py API.
    """

    def __init__(self):
        self.recordings: list[dict] = []

    async def record(self, result: ExecutionResult, analysis: AnalysisResult) -> bool:
        """Record an execution result to the knowledge graph."""
        try:
            from ..knowledge import record_knowledge

            # Build the intent description
            intent = self._build_intent(result, analysis)

            # Build the action description
            action = {
                "tool": result.tool_name,
                "params": result.params,
            }

            # Record to knowledge graph
            outcome = "success" if result.success else "failure"

            # Include correction info if this was a failure
            correction_of = None
            if not result.success and result.error:
                correction_of = {
                    "params": result.params,
                    "error": result.error,
                }

            # record_knowledge is synchronous
            kg_result = record_knowledge(
                intent=intent,
                action=action,
                outcome=outcome,
                correction_of=correction_of,
            )

            # Track locally
            self.recordings.append({
                "tool": result.tool_name,
                "success": result.success,
                "intent": intent,
                "kg_result": kg_result,
            })

            logger.info(f"Recorded: {result.tool_name} ({outcome})")
            return True

        except Exception as e:
            logger.error(f"Failed to record {result.tool_name}: {e}")
            return False

    def record_sync(self, result: ExecutionResult, analysis: AnalysisResult) -> bool:
        """Synchronous version of record."""
        import asyncio
        return asyncio.run(self.record(result, analysis))

    def _build_intent(self, result: ExecutionResult, analysis: AnalysisResult) -> str:
        """Build a human-readable intent description."""
        tool = result.tool_name.replace("rhino_", "")
        params = result.params

        # Tool-specific intent generation
        if tool == "create":
            geom_type = params.get("type", "geometry")
            return f"create {geom_type.lower()}"

        if tool == "transform":
            operation = params.get("operation", "transform")
            return f"{operation} objects"

        if tool == "boolean":
            operation = params.get("operation", "boolean")
            return f"boolean {operation}"

        if tool == "layer_create":
            name = params.get("name", "layer")
            parent = params.get("parent")
            if parent:
                return f"create nested layer {name} under {parent}"
            return f"create layer {name}"

        if tool.startswith("measure_"):
            measure_type = tool.replace("measure_", "")
            return f"measure {measure_type}"

        if tool.startswith("select"):
            return f"select objects"

        if tool.startswith("block_"):
            action = tool.replace("block_", "")
            return f"block {action}"

        if tool.startswith("subd_"):
            action = tool.replace("subd_", "")
            return f"SubD {action}"

        if tool.startswith("mesh_"):
            action = tool.replace("mesh_", "")
            return f"mesh {action}"

        if tool.startswith("intersect_"):
            return "find intersections"

        if tool.startswith("offset_"):
            return "offset geometry"

        if tool.startswith("curve_"):
            return "curve operation"

        # Default
        return f"explorer test {tool}"

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of all recordings."""
        total = len(self.recordings)
        successes = sum(1 for r in self.recordings if r["success"])
        failures = total - successes

        tools = set(r["tool"] for r in self.recordings)

        return {
            "total_recordings": total,
            "successes": successes,
            "failures": failures,
            "unique_tools": len(tools),
            "tools": list(tools),
        }

    def clear(self) -> None:
        """Clear local recordings."""
        self.recordings.clear()
