"""
Geometric Constraint Library - Precondition and postcondition checking for GH operations.

Provides:
- Precondition: A constraint that must be true before execution
- Postcondition: A constraint that should be verified after execution
- ComponentConstraints: All constraints for a GH component
- ConstraintChecker: Load and check constraints against operations
- ConstraintWarning: A warning about a potential constraint violation

Part of Phase 6 of the meta-learning system.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional
from ..runtime_paths import resolve_readable_knowledge_path

logger = logging.getLogger("rook.constraints")

# Default path for constraints file
CONSTRAINTS_PATH = resolve_readable_knowledge_path("gh", "constraints.json")


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class Precondition:
    """A constraint that must be true before execution.

    Preconditions check input requirements like:
    - Input types (curve, solid, etc.)
    - Geometric properties (closed, direction, etc.)
    - Minimum input counts
    """

    type: str
    """Constraint type: min_inputs, curve_direction, solid_closed, etc."""

    description: str
    """Human-readable description of what's required."""

    severity: Literal["error", "warning"]
    """error = likely to fail, warning = may cause issues."""

    fix_suggestion: str
    """How to fix if constraint is violated."""

    param: Optional[str] = None
    """Which parameter this applies to (e.g., 'C' for curves)."""

    params: Optional[list[str]] = None
    """Multiple parameters for relationship constraints."""

    min_count: Optional[int] = None
    """For min_inputs: minimum required count."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        d = {
            "type": self.type,
            "description": self.description,
            "severity": self.severity,
            "fix_suggestion": self.fix_suggestion,
        }
        if self.param:
            d["param"] = self.param
        if self.params:
            d["params"] = self.params
        if self.min_count is not None:
            d["min_count"] = self.min_count
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Precondition":
        """Create from dict."""
        return cls(
            type=d["type"],
            description=d["description"],
            severity=d.get("severity", "warning"),
            fix_suggestion=d.get("fix_suggestion", ""),
            param=d.get("param"),
            params=d.get("params"),
            min_count=d.get("min_count"),
        )


@dataclass
class Postcondition:
    """A constraint that should be verified after execution.

    Postconditions verify expected outputs like:
    - Output exists (not null)
    - Output is valid geometry
    - Output matches expected type
    """

    type: str
    """Constraint type: output_exists, output_valid, output_type, etc."""

    description: str
    """Human-readable description of expected result."""

    param: Optional[str] = None
    """Which output parameter to check."""

    expected_type: Optional[str] = None
    """For output_type: expected geometry type."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        d = {
            "type": self.type,
            "description": self.description,
        }
        if self.param:
            d["param"] = self.param
        if self.expected_type:
            d["expected_type"] = self.expected_type
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Postcondition":
        """Create from dict."""
        return cls(
            type=d["type"],
            description=d["description"],
            param=d.get("param"),
            expected_type=d.get("expected_type"),
        )


@dataclass
class ComponentConstraints:
    """All constraints for a GH component.

    Groups preconditions and postconditions for a specific component
    like Loft, Boolean Difference, etc.
    """

    component_name: str
    """Display name of the component."""

    category: str
    """Category: surface_ops, solid_ops, curve_ops, etc."""

    preconditions: list[Precondition]
    """Constraints to check before execution."""

    postconditions: list[Postcondition]
    """Constraints to verify after execution."""

    component_guid: Optional[str] = None
    """GH component GUID if known."""

    aliases: list[str] = field(default_factory=list)
    """Alternative names for this component (e.g., 'Boolean Difference' for 'Solid Difference')."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        d = {
            "category": self.category,
            "preconditions": [p.to_dict() for p in self.preconditions],
            "postconditions": [p.to_dict() for p in self.postconditions],
        }
        if self.component_guid:
            d["component_guid"] = self.component_guid
        if self.aliases:
            d["aliases"] = self.aliases
        return d

    @classmethod
    def from_dict(cls, name: str, d: dict) -> "ComponentConstraints":
        """Create from dict."""
        return cls(
            component_name=name,
            category=d.get("category", "unknown"),
            component_guid=d.get("component_guid"),
            aliases=d.get("aliases", []),
            preconditions=[Precondition.from_dict(p) for p in d.get("preconditions", [])],
            postconditions=[Postcondition.from_dict(p) for p in d.get("postconditions", [])],
        )

    def get_errors(self) -> list[Precondition]:
        """Get preconditions with severity=error."""
        return [p for p in self.preconditions if p.severity == "error"]

    def get_warnings(self) -> list[Precondition]:
        """Get preconditions with severity=warning."""
        return [p for p in self.preconditions if p.severity == "warning"]


@dataclass
class ConstraintWarning:
    """A warning about a potential constraint violation.

    Returned when checking constraints to inform the user
    about potential issues before execution.
    """

    component: str
    """Component name that has the constraint."""

    constraint_type: str
    """Type of constraint: curve_direction, solid_closed, etc."""

    severity: Literal["error", "warning"]
    """error = likely to fail, warning = may cause issues."""

    description: str
    """Human-readable description of the issue."""

    fix_suggestion: str
    """How to resolve the issue."""

    param: Optional[str] = None
    """Which single parameter is affected."""

    params: Optional[list[str]] = None
    """Multiple parameters for relationship constraints."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for MCP response."""
        d = {
            "component": self.component,
            "type": self.constraint_type,
            "severity": self.severity,
            "description": self.description,
            "fix_suggestion": self.fix_suggestion,
        }
        if self.param:
            d["param"] = self.param
        if self.params:
            d["params"] = self.params
        return d


# =============================================================================
# Constraint Checker
# =============================================================================

class ConstraintChecker:
    """Load and check geometric constraints for GH operations.

    Loads constraints from JSON and provides methods to:
    - Get constraints for a component
    - Check preconditions against known input info
    - Generate warnings for intents involving constrained components

    Usage:
        checker = ConstraintChecker()
        constraints = checker.get_constraints("Loft")
        warnings = checker.get_warnings_for_components(["Loft", "Sphere"])
    """

    def __init__(self, constraints_path: Optional[Path] = None):
        """Initialize with constraints from JSON file.

        Args:
            constraints_path: Path to constraints.json (uses default if None)
        """
        self.path = constraints_path or CONSTRAINTS_PATH
        self.constraints: dict[str, ComponentConstraints] = {}
        self._load_constraints()

    def _load_constraints(self) -> None:
        """Load constraints from JSON file.

        Indexes constraints by primary name AND all aliases for flexible lookup.
        """
        if not self.path.exists():
            logger.warning(f"Constraints file not found: {self.path}")
            return

        try:
            with open(self.path) as f:
                data = json.load(f)

            primary_count = 0
            alias_count = 0

            for name, constraint_data in data.get("constraints", {}).items():
                constraint = ComponentConstraints.from_dict(name, constraint_data)

                # Index by primary name
                self.constraints[name.lower()] = constraint
                primary_count += 1

                # Also index by aliases
                for alias in constraint.aliases:
                    self.constraints[alias.lower()] = constraint
                    alias_count += 1

            logger.info(
                f"Loaded constraints for {primary_count} components "
                f"({alias_count} aliases)"
            )

        except Exception as e:
            logger.error(f"Failed to load constraints: {e}")

    def reload(self) -> int:
        """Reload constraints from disk.

        Returns:
            Number of components loaded
        """
        self.constraints.clear()
        self._load_constraints()
        return len(self.constraints)

    def get_constraints(self, component_name: str) -> Optional[ComponentConstraints]:
        """Get constraints for a component by name.

        Args:
            component_name: Component name (case-insensitive)

        Returns:
            ComponentConstraints if found, None otherwise
        """
        return self.constraints.get(component_name.lower())

    def get_all_constrained_components(self) -> list[str]:
        """Get list of all components with constraints."""
        return [c.component_name for c in self.constraints.values()]

    def get_warnings_for_components(
        self,
        component_names: list[str],
        include_warnings: bool = True,
        include_errors: bool = True,
    ) -> list[ConstraintWarning]:
        """Get constraint warnings for a list of components.

        Args:
            component_names: List of component names to check
            include_warnings: Include severity=warning constraints
            include_errors: Include severity=error constraints

        Returns:
            List of ConstraintWarning objects
        """
        warnings = []

        for name in component_names:
            constraints = self.get_constraints(name)
            if not constraints:
                continue

            for pre in constraints.preconditions:
                if pre.severity == "error" and not include_errors:
                    continue
                if pre.severity == "warning" and not include_warnings:
                    continue

                warnings.append(ConstraintWarning(
                    component=constraints.component_name,
                    constraint_type=pre.type,
                    severity=pre.severity,
                    description=pre.description,
                    fix_suggestion=pre.fix_suggestion,
                    param=pre.param,
                    params=pre.params,
                ))

        return warnings

    def get_warnings_by_category(
        self,
        category: str,
    ) -> list[ConstraintWarning]:
        """Get all warnings for components in a category.

        Args:
            category: Category name (surface_ops, solid_ops, etc.)

        Returns:
            List of ConstraintWarning objects
        """
        component_names = [
            c.component_name
            for c in self.constraints.values()
            if c.category == category
        ]
        return self.get_warnings_for_components(component_names)

    def check_component_inputs(
        self,
        component_name: str,
        input_counts: dict[str, int],
    ) -> list[ConstraintWarning]:
        """Check specific input counts against constraints.

        Args:
            component_name: Component to check
            input_counts: Dict of param -> count (e.g., {"C": 3})

        Returns:
            List of violations found
        """
        constraints = self.get_constraints(component_name)
        if not constraints:
            return []

        warnings = []

        for pre in constraints.preconditions:
            if pre.type == "min_inputs" and pre.param:
                actual = input_counts.get(pre.param, 0)
                if pre.min_count and actual < pre.min_count:
                    warnings.append(ConstraintWarning(
                        component=constraints.component_name,
                        constraint_type=pre.type,
                        severity=pre.severity,
                        description=f"{pre.description} (got {actual}, need {pre.min_count})",
                        fix_suggestion=pre.fix_suggestion,
                        param=pre.param,
                    ))

        return warnings

    def get_constraint_summary(self, component_name: str) -> Optional[dict]:
        """Get a summary of constraints for a component.

        Args:
            component_name: Component name

        Returns:
            Summary dict with counts and key constraints
        """
        constraints = self.get_constraints(component_name)
        if not constraints:
            return None

        return {
            "component": constraints.component_name,
            "category": constraints.category,
            "error_count": len(constraints.get_errors()),
            "warning_count": len(constraints.get_warnings()),
            "postcondition_count": len(constraints.postconditions),
            "key_constraints": [
                p.description for p in constraints.get_errors()[:3]
            ],
        }

    def to_dict(self) -> dict:
        """Export all constraints as dict."""
        return {
            "version": "1.0",
            "component_count": len(self.constraints),
            "constraints": {
                c.component_name: c.to_dict()
                for c in self.constraints.values()
            },
        }

    def __len__(self) -> int:
        return len(self.constraints)

    def __contains__(self, component_name: str) -> bool:
        return component_name.lower() in self.constraints


# =============================================================================
# Singleton Accessor
# =============================================================================

_checker_instance: Optional[ConstraintChecker] = None


def get_constraint_checker() -> ConstraintChecker:
    """Get the singleton ConstraintChecker instance.

    The checker is initialized on first access and reused thereafter.
    """
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = ConstraintChecker()
    return _checker_instance
