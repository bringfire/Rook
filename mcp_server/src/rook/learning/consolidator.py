"""DSPy-based Knowledge Consolidation Module.

This module transforms raw learned patterns into tiered, contextual knowledge
that Claude instances can query efficiently.

The Core Problem:
    The overnight learning agent collected 500+ patterns for rhino_layer_create alone.
    Returning all of these to a querying Claude burns tokens and accelerates context collapse.

The Solution:
    Use DSPy to build structured, tiered knowledge:
    - QUICK (20 tokens): Essential facts for this tool
    - CONTEXT (50 tokens): Specific rules for each usage context
    - ERRORS (30 tokens): What fails and why
    - RAW (5000 tokens): Full patterns, only when debugging

Architecture:
    Raw Knowledge Graph --> DSPy Consolidator --> Tiered JSON
    (500+ patterns)        (Identifies contexts,   (Structured,
                            clusters, summarizes)   queryable)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import dspy

# Learning boundary: configure DSPy once, on first import of any module that runs an LM.
from .dspy_config import ensure_configured as _ensure_dspy_configured
_ensure_dspy_configured()
from ..runtime_paths import resolve_readable_knowledge_path, resolve_writable_knowledge_path

from rook.learning.dspy_config import _get_default_model

logger = logging.getLogger(__name__)


# =============================================================================
# DSPy Signatures for Consolidation
# =============================================================================


class IdentifyContexts(dspy.Signature):
    """Identify distinct usage contexts from patterns for a tool.

    Analyze a sample of patterns to identify the different ways this tool
    is commonly used. Each context represents a distinct use case with
    its own requirements and gotchas.
    """

    tool_name: str = dspy.InputField(desc="The MCP tool name")
    tool_description: str = dspy.InputField(desc="What the tool does")
    sample_patterns: str = dspy.InputField(desc="JSON sample of 20-30 patterns")
    sample_antipatterns: str = dspy.InputField(desc="JSON sample of antipatterns")

    contexts: str = dspy.OutputField(
        desc="Comma-separated context names (e.g., 'basic,nested,colored')"
    )
    context_descriptions: str = dspy.OutputField(
        desc="One sentence per context explaining what it covers, separated by semicolons"
    )


class ClassifyPattern(dspy.Signature):
    """Classify a single pattern into one of the identified contexts.

    Given a pattern and the available contexts, determine which context
    this pattern belongs to based on its parameters and behavior.
    """

    tool_name: str = dspy.InputField(desc="The MCP tool name")
    pattern_params: str = dspy.InputField(desc="JSON of pattern parameters")
    pattern_note: str = dspy.InputField(desc="Note/description of the pattern")
    available_contexts: str = dspy.InputField(
        desc="Comma-separated available contexts"
    )

    context: str = dspy.OutputField(desc="The single best-matching context name")


class ConsolidateContext(dspy.Signature):
    """Consolidate all patterns within a context into actionable knowledge.

    Take all successful and failed patterns for a specific context and
    distill them into a summary, required/optional params, gotchas, and example.
    """

    tool_name: str = dspy.InputField(desc="The MCP tool name")
    context_name: str = dspy.InputField(desc="Name of this usage context")
    context_description: str = dspy.InputField(desc="What this context covers")
    success_patterns: str = dspy.InputField(
        desc="JSON array of successful patterns in this context"
    )
    failure_patterns: str = dspy.InputField(
        desc="JSON array of failed patterns in this context"
    )

    summary: str = dspy.OutputField(
        desc="One sentence: how to use the tool in this context"
    )
    required_params: str = dspy.OutputField(
        desc="Comma-separated parameters that must be provided"
    )
    optional_params: str = dspy.OutputField(
        desc="Comma-separated parameters that can be provided"
    )
    gotchas: str = dspy.OutputField(
        desc="Semicolon-separated things that can go wrong"
    )
    example_params: str = dspy.OutputField(
        desc="JSON of one good example parameter set"
    )


class ExtractErrorCategories(dspy.Signature):
    """Categorize and summarize error patterns.

    Analyze all antipatterns for a tool and group them into categories
    with counts, descriptions, and avoidance strategies.
    """

    tool_name: str = dspy.InputField(desc="The MCP tool name")
    antipatterns: str = dspy.InputField(desc="JSON array of all antipatterns")

    error_categories: str = dspy.OutputField(
        desc="JSON object: {category_name: {count, description, avoidance}}"
    )


class GenerateQuickSummary(dspy.Signature):
    """Generate minimal quick-reference from consolidated contexts.

    Create a 30-word-or-less summary that covers the essentials for this tool.
    This is the "QUICK" tier - maximum insight in minimum tokens.
    """

    tool_name: str = dspy.InputField(desc="The MCP tool name")
    tool_description: str = dspy.InputField(desc="What the tool does")
    consolidated_contexts: str = dspy.InputField(
        desc="JSON of all consolidated contexts"
    )

    quick: str = dspy.OutputField(
        desc="Under 30 words covering the essentials for this tool"
    )


# =============================================================================
# Data Classes for Consolidated Knowledge
# =============================================================================


@dataclass
class ConsolidatedContext:
    """A single usage context for a tool."""

    description: str
    summary: str
    required_params: str
    optional_params: str
    gotchas: str
    example: dict[str, Any]
    patterns_analyzed: int = 0
    success_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "summary": self.summary,
            "required_params": self.required_params,
            "optional_params": self.optional_params,
            "gotchas": self.gotchas,
            "example": self.example,
            "patterns_analyzed": self.patterns_analyzed,
            "success_rate": self.success_rate,
        }


@dataclass
class ErrorCategory:
    """A category of errors for a tool."""

    count: int
    description: str
    avoidance: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "description": self.description,
            "avoidance": self.avoidance,
        }


@dataclass
class ConsolidatedTool:
    """Consolidated knowledge for a single tool."""

    quick: str
    contexts: dict[str, ConsolidatedContext] = field(default_factory=dict)
    errors: dict[str, ErrorCategory] = field(default_factory=dict)
    total_patterns: int = 0
    total_antipatterns: int = 0
    contexts_identified: int = 0
    consolidation_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "quick": self.quick,
            "contexts": {k: v.to_dict() for k, v in self.contexts.items()},
            "errors": {k: v.to_dict() for k, v in self.errors.items()},
            "meta": {
                "total_patterns": self.total_patterns,
                "total_antipatterns": self.total_antipatterns,
                "contexts_identified": self.contexts_identified,
                "consolidation_confidence": self.consolidation_confidence,
            },
        }


@dataclass
class ConsolidatedKnowledge:
    """Top-level consolidated knowledge structure."""

    version: str = "1.0"
    consolidated_at: str = ""
    consolidation_model: str = ""
    tools: dict[str, ConsolidatedTool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "consolidated_at": self.consolidated_at or datetime.utcnow().isoformat() + "Z",
            "consolidation_model": self.consolidation_model,
            "tools": {k: v.to_dict() for k, v in self.tools.items()},
        }

    def save(self, path: Path | str) -> None:
        """Save to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Saved consolidated knowledge to {path}")

    @classmethod
    def load(cls, path: Path | str) -> "ConsolidatedKnowledge":
        """Load from JSON file."""
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConsolidatedKnowledge":
        """Create from dictionary."""
        knowledge = cls(
            version=data.get("version", "1.0"),
            consolidated_at=data.get("consolidated_at", ""),
            consolidation_model=data.get("consolidation_model", ""),
        )
        for tool_name, tool_data in data.get("tools", {}).items():
            contexts = {}
            for ctx_name, ctx_data in tool_data.get("contexts", {}).items():
                contexts[ctx_name] = ConsolidatedContext(
                    description=ctx_data.get("description", ""),
                    summary=ctx_data.get("summary", ""),
                    required_params=ctx_data.get("required_params", ""),
                    optional_params=ctx_data.get("optional_params", ""),
                    gotchas=ctx_data.get("gotchas", ""),
                    example=ctx_data.get("example", {}),
                    patterns_analyzed=ctx_data.get("patterns_analyzed", 0),
                    success_rate=ctx_data.get("success_rate", 0.0),
                )
            errors = {}
            for err_name, err_data in tool_data.get("errors", {}).items():
                errors[err_name] = ErrorCategory(
                    count=err_data.get("count", 0),
                    description=err_data.get("description", ""),
                    avoidance=err_data.get("avoidance", ""),
                )
            meta = tool_data.get("meta", {})
            knowledge.tools[tool_name] = ConsolidatedTool(
                quick=tool_data.get("quick", ""),
                contexts=contexts,
                errors=errors,
                total_patterns=meta.get("total_patterns", 0),
                total_antipatterns=meta.get("total_antipatterns", 0),
                contexts_identified=meta.get("contexts_identified", 0),
                consolidation_confidence=meta.get("consolidation_confidence", 0.0),
            )
        return knowledge


# =============================================================================
# Intelligent Consolidator Module
# =============================================================================


class IntelligentConsolidator(dspy.Module):
    """Orchestrates tiered knowledge generation from raw patterns.

    This module takes raw patterns from the knowledge graph and transforms
    them into tiered, contextual knowledge with token-aware representations
    (quick ~20 tokens, context ~50 tokens, errors ~30 tokens, raw ~300+ tokens).

    Relationship to other Consolidators:
        - PatternConsolidator: DSPy module for merging individual patterns.
          Used for real-time pattern deduplication during learning.
        - IntelligentConsolidator: (THIS) DSPy module for tiered knowledge generation.
          Used for creating token-aware knowledge tiers.
        - CommandConsolidator: Orchestrator class for structural analysis.
          Used for batch processing command families and relationships.

    Usage:
        from rook.learning import configure_dspy
        from rook.learning.consolidator import IntelligentConsolidator

        # Configure DSPy with Claude backend
        configure_dspy(model="claude-sonnet-4-20250514")

        # Create consolidator
        consolidator = IntelligentConsolidator()

        # Consolidate a tool's patterns
        result = consolidator.forward(
            tool_name="rhino_layer_create",
            tool_description="Create a new layer in the document",
            patterns=[{"params": {"name": "MyLayer"}, "note": "Basic layer"}],
            antipatterns=[{"params": {"name": ""}, "error": "Name required"}]
        )
    """

    def __init__(self) -> None:
        super().__init__()
        self.identify_contexts = dspy.ChainOfThought(IdentifyContexts)
        self.classify_pattern = dspy.Predict(ClassifyPattern)
        self.consolidate_context = dspy.ChainOfThought(ConsolidateContext)
        self.extract_errors = dspy.ChainOfThought(ExtractErrorCategories)
        self.generate_quick = dspy.Predict(GenerateQuickSummary)

    def forward(
        self,
        tool_name: str,
        tool_description: str,
        patterns: list[dict[str, Any]],
        antipatterns: list[dict[str, Any]],
    ) -> ConsolidatedTool:
        """Consolidate patterns for a single tool.

        Args:
            tool_name: The MCP tool name (e.g., "rhino_layer_create")
            tool_description: Brief description of what the tool does
            patterns: List of successful patterns [{params, note, confidence}]
            antipatterns: List of failure patterns [{params, error, note}]

        Returns:
            ConsolidatedTool with tiered knowledge
        """
        logger.info(f"Consolidating {len(patterns)} patterns for {tool_name}")

        # Step 1: Identify contexts from sample patterns
        sample_patterns = patterns[:30]  # Use up to 30 patterns as sample
        sample_antipatterns = antipatterns[:15]  # Use up to 15 antipatterns

        context_result = self.identify_contexts(
            tool_name=tool_name,
            tool_description=tool_description,
            sample_patterns=json.dumps(sample_patterns),
            sample_antipatterns=json.dumps(sample_antipatterns),
        )

        context_names = [c.strip() for c in context_result.contexts.split(",")]
        context_descs = [d.strip() for d in context_result.context_descriptions.split(";")]

        logger.info(f"Identified {len(context_names)} contexts: {context_names}")

        # Step 2: Classify all patterns into contexts
        classified: dict[str, list[dict]] = {ctx: [] for ctx in context_names}
        classified["_unclassified"] = []

        for pattern in patterns:
            try:
                result = self.classify_pattern(
                    tool_name=tool_name,
                    pattern_params=json.dumps(pattern.get("params", {})),
                    pattern_note=pattern.get("note", ""),
                    available_contexts=",".join(context_names),
                )
                ctx = result.context.strip()
                if ctx in classified:
                    classified[ctx].append(pattern)
                else:
                    classified["_unclassified"].append(pattern)
            except Exception as e:
                logger.warning(f"Failed to classify pattern: {e}")
                classified["_unclassified"].append(pattern)

        # Step 3: Consolidate each context
        consolidated_contexts: dict[str, ConsolidatedContext] = {}

        for i, ctx_name in enumerate(context_names):
            ctx_patterns = classified.get(ctx_name, [])
            ctx_desc = context_descs[i] if i < len(context_descs) else ""

            if not ctx_patterns:
                logger.info(f"Skipping empty context: {ctx_name}")
                continue

            # Find failures for this context (patterns that match but failed)
            ctx_failures = [
                ap for ap in antipatterns
                if self._pattern_matches_context(ap, ctx_name)
            ]

            try:
                result = self.consolidate_context(
                    tool_name=tool_name,
                    context_name=ctx_name,
                    context_description=ctx_desc,
                    success_patterns=json.dumps(ctx_patterns),
                    failure_patterns=json.dumps(ctx_failures),
                )

                # Parse example params
                try:
                    example = json.loads(result.example_params)
                except (json.JSONDecodeError, TypeError):
                    example = {}

                # Calculate success rate
                total = len(ctx_patterns) + len(ctx_failures)
                success_rate = len(ctx_patterns) / total if total > 0 else 0.0

                consolidated_contexts[ctx_name] = ConsolidatedContext(
                    description=ctx_desc,
                    summary=result.summary,
                    required_params=result.required_params,
                    optional_params=result.optional_params,
                    gotchas=result.gotchas,
                    example=example,
                    patterns_analyzed=len(ctx_patterns),
                    success_rate=success_rate,
                )
            except Exception as e:
                logger.error(f"Failed to consolidate context {ctx_name}: {e}")

        # Step 4: Extract error categories
        error_categories: dict[str, ErrorCategory] = {}
        if antipatterns:
            try:
                result = self.extract_errors(
                    tool_name=tool_name,
                    antipatterns=json.dumps(antipatterns),
                )
                errors_dict = json.loads(result.error_categories)
                for err_name, err_data in errors_dict.items():
                    error_categories[err_name] = ErrorCategory(
                        count=err_data.get("count", 0),
                        description=err_data.get("description", ""),
                        avoidance=err_data.get("avoidance", ""),
                    )
            except Exception as e:
                logger.error(f"Failed to extract error categories: {e}")

        # Step 5: Generate quick summary
        quick = ""
        try:
            result = self.generate_quick(
                tool_name=tool_name,
                tool_description=tool_description,
                consolidated_contexts=json.dumps(
                    {k: v.to_dict() for k, v in consolidated_contexts.items()}
                ),
            )
            quick = result.quick
        except Exception as e:
            logger.error(f"Failed to generate quick summary: {e}")
            # Fallback quick summary
            quick = f"{tool_name}: {tool_description}"

        # Build final consolidated tool
        return ConsolidatedTool(
            quick=quick,
            contexts=consolidated_contexts,
            errors=error_categories,
            total_patterns=len(patterns),
            total_antipatterns=len(antipatterns),
            contexts_identified=len(consolidated_contexts),
            consolidation_confidence=self._calculate_confidence(
                patterns, antipatterns, consolidated_contexts
            ),
        )

    def _pattern_matches_context(
        self,
        pattern: dict[str, Any],
        target_context: str,
    ) -> bool:
        """Heuristically check if an antipattern matches a context.

        For efficiency, we use simple heuristics instead of calling the LLM
        for every antipattern. This is a placeholder for Phase 2 optimization.
        """
        # Simple keyword matching for now
        note = pattern.get("note", "").lower()
        error = pattern.get("error", "").lower()
        combined = f"{note} {error}"

        # Context-specific keywords
        context_keywords = {
            "basic": ["simple", "basic", "default", "minimal"],
            "nested": ["nested", "child", "parent", "hierarchy"],
            "colored": ["color", "rgb", "red", "green", "blue"],
        }

        keywords = context_keywords.get(target_context.lower(), [target_context.lower()])
        return any(kw in combined for kw in keywords)

    def _calculate_confidence(
        self,
        patterns: list[dict],
        antipatterns: list[dict],
        contexts: dict[str, ConsolidatedContext],
    ) -> float:
        """Calculate confidence score for the consolidation."""
        if not patterns:
            return 0.0

        # Factors:
        # 1. Coverage: what % of patterns were classified
        total_classified = sum(c.patterns_analyzed for c in contexts.values())
        coverage = total_classified / len(patterns) if patterns else 0

        # 2. Context quality: average success rate
        if contexts:
            avg_success = sum(c.success_rate for c in contexts.values()) / len(contexts)
        else:
            avg_success = 0

        # 3. Sample size: more patterns = higher confidence
        size_factor = min(1.0, len(patterns) / 50)  # Cap at 50 patterns

        return (coverage * 0.4 + avg_success * 0.4 + size_factor * 0.2)


# =============================================================================
# Convenience Functions
# =============================================================================


def consolidate_tool(
    tool_name: str,
    tool_description: str,
    patterns: list[dict[str, Any]],
    antipatterns: list[dict[str, Any]],
) -> ConsolidatedTool:
    """Convenience function to consolidate a tool's patterns.

    Requires DSPy to be configured first via configure_dspy().
    """
    consolidator = IntelligentConsolidator()
    return consolidator.forward(tool_name, tool_description, patterns, antipatterns)


def extract_patterns_by_tool(knowledge_path: Path | str) -> dict[str, dict[str, list[dict]]]:
    """Extract patterns and antipatterns from knowledge graph, grouped by tool.

    Args:
        knowledge_path: Path to knowledge graph JSON

    Returns:
        {tool_name: {"patterns": [...], "antipatterns": [...]}}
    """
    knowledge_path = Path(knowledge_path)
    if not knowledge_path.exists():
        logger.warning(f"Knowledge graph not found: {knowledge_path}")
        return {}

    with open(knowledge_path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    nodes = graph.get("nodes", [])
    links = graph.get("links", [])

    # Index nodes by ID
    nodes_by_id = {n["id"]: n for n in nodes}

    # Build tool -> patterns/antipatterns mapping
    tool_data: dict[str, dict[str, list[dict]]] = {}

    for link in links:
        source = link.get("source", "")
        target = link.get("target", "")
        relation = link.get("relation", "")

        # Pattern: action -[requires]-> pattern
        if relation == "requires" and source.startswith("action:"):
            tool_name = source.replace("action:", "")
            target_node = nodes_by_id.get(target, {})
            if target_node.get("type") == "pattern":
                if tool_name not in tool_data:
                    tool_data[tool_name] = {"patterns": [], "antipatterns": []}
                tool_data[tool_name]["patterns"].append({
                    "params": target_node.get("params", {}),
                    "note": target_node.get("note", ""),
                    "weight": target_node.get("weight", 0.5),
                })

        # Antipattern: action -[avoid]-> antipattern
        elif relation == "avoid" and source.startswith("action:"):
            tool_name = source.replace("action:", "")
            target_node = nodes_by_id.get(target, {})
            if target_node.get("type") == "antipattern":
                if tool_name not in tool_data:
                    tool_data[tool_name] = {"patterns": [], "antipatterns": []}
                tool_data[tool_name]["antipatterns"].append({
                    "params": target_node.get("params", {}),
                    "error": target_node.get("reason", ""),
                    "note": target_node.get("note", ""),
                    "weight": target_node.get("weight", 0.5),
                })

    return tool_data


# Default tool descriptions (can be overridden)
DEFAULT_TOOL_DESCRIPTIONS = {
    "rhino_layer_create": "Create a new layer in the document with optional color, visibility, and parent layer",
    "rhino_layers": "Get all layers in the current document with their properties",
    "rhino_create": "Create geometry in Rhino (point, line, circle, box, sphere, etc.)",
    "rhino_execute": "Execute a Python script in Rhino using rhinoscriptsyntax",
    "rhino_command": "Run a Rhino command string",
    "rhino_transform": "Transform objects (move, rotate, scale, mirror)",
    "rhino_boolean": "Perform boolean operations on solids (union, difference, intersection)",
    "rhino_loft": "Create a lofted surface through multiple curves",
    "rhino_sweep": "Create a swept surface along a rail curve",
    "rhino_extrude": "Extrude a curve or surface along a direction",
    "rhino_curve_ops": "Perform curve operations (join, explode, divide, extend, trim, split, fillet)",
    "rhino_ping": "Check if Rhino bridge is running and responsive",
}


def consolidate_all_tools(
    knowledge_path: Path | str,
    output_path: Path | str,
    tool_descriptions: dict[str, str] | None = None,
    min_patterns: int = 5,
    tools_to_consolidate: list[str] | None = None,
) -> ConsolidatedKnowledge:
    """Consolidate all tools from a knowledge graph.

    Args:
        knowledge_path: Path to knowledge graph JSON (e.g., knowledge/local.json)
        output_path: Path to save consolidated knowledge
        tool_descriptions: Optional dict of tool_name -> description
        min_patterns: Minimum patterns required to consolidate a tool (default 5)
        tools_to_consolidate: Optional list of specific tools to consolidate
                              If None, consolidates all tools with enough patterns

    Returns:
        ConsolidatedKnowledge with all tools consolidated
    """
    knowledge_path = Path(knowledge_path)
    output_path = Path(output_path)

    # Merge default descriptions with provided ones
    descriptions = DEFAULT_TOOL_DESCRIPTIONS.copy()
    if tool_descriptions:
        descriptions.update(tool_descriptions)

    # Extract patterns by tool
    logger.info(f"Loading patterns from {knowledge_path}")
    tool_data = extract_patterns_by_tool(knowledge_path)
    logger.info(f"Found {len(tool_data)} tools with patterns")

    # Filter to tools with enough patterns
    if tools_to_consolidate:
        tools_to_process = [
            t for t in tools_to_consolidate
            if t in tool_data and len(tool_data[t]["patterns"]) >= min_patterns
        ]
    else:
        tools_to_process = [
            t for t, data in tool_data.items()
            if len(data["patterns"]) >= min_patterns
        ]

    logger.info(f"Will consolidate {len(tools_to_process)} tools with >= {min_patterns} patterns")

    # Create consolidator
    consolidator = IntelligentConsolidator()

    # Build consolidated knowledge
    knowledge = ConsolidatedKnowledge()
    knowledge.consolidation_model = _get_default_model()

    for tool_name in tools_to_process:
        data = tool_data[tool_name]
        patterns = data["patterns"]
        antipatterns = data["antipatterns"]

        logger.info(f"Consolidating {tool_name}: {len(patterns)} patterns, {len(antipatterns)} antipatterns")

        description = descriptions.get(tool_name, f"MCP tool: {tool_name}")

        try:
            consolidated_tool = consolidator.forward(
                tool_name=tool_name,
                tool_description=description,
                patterns=patterns,
                antipatterns=antipatterns,
            )
            knowledge.tools[tool_name] = consolidated_tool
            logger.info(f"  -> {len(consolidated_tool.contexts)} contexts, {len(consolidated_tool.errors)} error categories")
        except Exception as e:
            logger.error(f"Failed to consolidate {tool_name}: {e}")
            continue

    # Save
    knowledge.save(output_path)
    logger.info(f"Saved consolidated knowledge to {output_path}")

    return knowledge


def consolidate_single_tool(
    tool_name: str,
    knowledge_path: Path | str | None = None,
    output_path: Path | str | None = None,
    tool_description: str | None = None,
) -> ConsolidatedTool | None:
    """Consolidate a single tool and optionally save to condensed knowledge.

    This is useful for testing consolidation on one tool before running full consolidation.

    Args:
        tool_name: The tool to consolidate
        knowledge_path: Path to knowledge graph (default: knowledge/local.json)
        output_path: Path to save updated condensed knowledge (default: knowledge/condensed_knowledge.json)
        tool_description: Description of the tool (uses default if not provided)

    Returns:
        ConsolidatedTool or None if consolidation failed
    """
    knowledge_path = Path(knowledge_path) if knowledge_path else resolve_writable_knowledge_path("local.json")
    output_path = Path(output_path) if output_path else DEFAULT_CONDENSED_PATH

    # Extract patterns for this tool
    tool_data = extract_patterns_by_tool(knowledge_path)
    if tool_name not in tool_data:
        logger.error(f"No patterns found for {tool_name}")
        return None

    data = tool_data[tool_name]
    patterns = data["patterns"]
    antipatterns = data["antipatterns"]

    if not patterns:
        logger.error(f"No patterns for {tool_name}")
        return None

    # Get description
    description = tool_description or DEFAULT_TOOL_DESCRIPTIONS.get(tool_name, f"MCP tool: {tool_name}")

    logger.info(f"Consolidating {tool_name}: {len(patterns)} patterns, {len(antipatterns)} antipatterns")

    # Run consolidation
    consolidator = IntelligentConsolidator()
    try:
        consolidated_tool = consolidator.forward(
            tool_name=tool_name,
            tool_description=description,
            patterns=patterns,
            antipatterns=antipatterns,
        )
    except Exception as e:
        logger.error(f"Consolidation failed: {e}")
        return None

    # Load existing condensed knowledge and update
    read_output_path = output_path if output_path.exists() else resolve_readable_knowledge_path("condensed_knowledge.json")
    knowledge = ConsolidatedKnowledge.load(read_output_path)
    knowledge.consolidation_model = _get_default_model()
    knowledge.tools[tool_name] = consolidated_tool
    knowledge.save(output_path)

    logger.info(f"Updated {output_path} with {tool_name}")
    return consolidated_tool


# Default path for consolidated knowledge
DEFAULT_CONDENSED_PATH = resolve_writable_knowledge_path("condensed_knowledge.json")
