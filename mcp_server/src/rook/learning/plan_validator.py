"""
Plan Validator - Validate execution plans for gh_execute_intent.

Provides:
- ExecutionPlan: Dataclass representing a validated plan
- validate_plan: Validate plan dict and return errors
- PlanValidationError: Exception for invalid plans

Part of Phase 4 of the meta-learning system.
"""

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

logger = logging.getLogger("rook.plan_validator")


@dataclass
class ExecutionPlan:
    """A validated execution plan for gh_execute_intent.

    Plans help Claude organize complex intents before execution.
    Required fields ensure Claude thinks through key aspects.
    Flexible content lets Claude express plans naturally.

    Attributes:
        reasoning: Free text explaining approach and considerations
        sub_problems: Breakdown of the intent into sub-tasks
        sequence: Ordered steps to execute
        success_criteria: What success looks like
        patterns_to_apply: Pattern IDs to apply (optional)
        constraints_checked: Geometric constraints verified (optional)
        unknowns: Acknowledged uncertainties (optional, encouraged)
    """

    # Required fields
    reasoning: str
    """Free text explaining approach and considerations."""

    sub_problems: list[str]
    """Breakdown of the intent into sub-tasks."""

    sequence: list[str]
    """Ordered steps to execute."""

    success_criteria: str
    """What success looks like."""

    # Optional fields
    patterns_to_apply: list[str] = field(default_factory=list)
    """Pattern IDs to apply from pattern memory."""

    constraints_checked: list[str] = field(default_factory=list)
    """Geometric constraints that have been verified."""

    unknowns: list[str] = field(default_factory=list)
    """Acknowledged uncertainties (encouraged - admitting uncertainty is valuable)."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        d = {
            "reasoning": self.reasoning,
            "sub_problems": self.sub_problems,
            "sequence": self.sequence,
            "success_criteria": self.success_criteria,
        }
        # Only include optional fields if non-empty
        if self.patterns_to_apply:
            d["patterns_to_apply"] = self.patterns_to_apply
        if self.constraints_checked:
            d["constraints_checked"] = self.constraints_checked
        if self.unknowns:
            d["unknowns"] = self.unknowns
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ExecutionPlan":
        """Create from dict.

        Args:
            d: Dictionary with plan fields

        Returns:
            ExecutionPlan instance

        Raises:
            KeyError: If required fields are missing
        """
        return cls(
            reasoning=d["reasoning"],
            sub_problems=d["sub_problems"],
            sequence=d["sequence"],
            success_criteria=d["success_criteria"],
            patterns_to_apply=d.get("patterns_to_apply", []),
            constraints_checked=d.get("constraints_checked", []),
            unknowns=d.get("unknowns", []),
        )

    def summary(self) -> str:
        """Return a brief summary of the plan for logging."""
        return (
            f"Plan: {len(self.sub_problems)} sub-problems, "
            f"{len(self.sequence)} steps, "
            f"{len(self.patterns_to_apply)} patterns"
        )


class PlanValidationError(Exception):
    """Exception raised when plan validation fails."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Plan validation failed: {', '.join(errors)}")


# Required fields and their expected types
REQUIRED_FIELDS = {
    "reasoning": str,
    "sub_problems": list,
    "sequence": list,
    "success_criteria": str,
}

# Optional fields and their expected types
OPTIONAL_FIELDS = {
    "patterns_to_apply": list,
    "constraints_checked": list,
    "unknowns": list,
}


def validate_plan(plan_dict: Optional[dict]) -> tuple[bool, list[str], Optional[ExecutionPlan]]:
    """Validate a plan dictionary.

    Checks:
    - All required fields present
    - Required fields not empty
    - Correct types for all fields
    - List fields contain strings

    Args:
        plan_dict: Dictionary to validate (or None)

    Returns:
        Tuple of (is_valid, error_messages, validated_plan)
        If valid, error_messages is empty and validated_plan is set.
        If invalid, error_messages contains issues and validated_plan is None.
    """
    if plan_dict is None:
        return True, [], None  # No plan is valid (planning is optional)

    if not isinstance(plan_dict, dict):
        return False, ["Plan must be an object/dictionary"], None

    errors = []

    # Check required fields
    for field_name, expected_type in REQUIRED_FIELDS.items():
        if field_name not in plan_dict:
            errors.append(f"Missing required field: {field_name}")
        elif not isinstance(plan_dict[field_name], expected_type):
            errors.append(
                f"Field '{field_name}' must be {expected_type.__name__}, "
                f"got {type(plan_dict[field_name]).__name__}"
            )
        elif expected_type == str and not plan_dict[field_name].strip():
            errors.append(f"Field '{field_name}' cannot be empty")
        elif expected_type == list and len(plan_dict[field_name]) == 0:
            errors.append(f"Field '{field_name}' cannot be empty")

    # Check optional fields (if present)
    for field_name, expected_type in OPTIONAL_FIELDS.items():
        if field_name in plan_dict:
            if not isinstance(plan_dict[field_name], expected_type):
                errors.append(
                    f"Field '{field_name}' must be {expected_type.__name__}, "
                    f"got {type(plan_dict[field_name]).__name__}"
                )

    # Check list fields contain strings
    list_fields = ["sub_problems", "sequence", "patterns_to_apply", "constraints_checked", "unknowns"]
    for field_name in list_fields:
        if field_name in plan_dict and isinstance(plan_dict[field_name], list):
            for i, item in enumerate(plan_dict[field_name]):
                if not isinstance(item, str):
                    errors.append(
                        f"Field '{field_name}[{i}]' must be string, "
                        f"got {type(item).__name__}"
                    )

    if errors:
        return False, errors, None

    # Create validated plan
    try:
        plan = ExecutionPlan.from_dict(plan_dict)
        logger.debug(f"Validated plan: {plan.summary()}")
        return True, [], plan
    except Exception as e:
        return False, [f"Failed to create plan: {str(e)}"], None


def validate_plan_or_raise(plan_dict: Optional[dict]) -> Optional[ExecutionPlan]:
    """Validate a plan dictionary or raise PlanValidationError.

    Convenience function that raises instead of returning errors.

    Args:
        plan_dict: Dictionary to validate (or None)

    Returns:
        ExecutionPlan if valid, None if no plan provided

    Raises:
        PlanValidationError: If plan is invalid
    """
    is_valid, errors, plan = validate_plan(plan_dict)
    if not is_valid:
        raise PlanValidationError(errors)
    return plan
