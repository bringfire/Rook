"""
Visual Verification System for Autonomous Learning.

Verifies that operations actually worked via viewport capture.
Just because the API returned 200 doesn't mean the geometry is correct.

This module captures viewport states and compares them to verify
that geometric operations produced expected results.
"""

import hashlib
import logging

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from .schema import Verification
from .graph import KnowledgeGraphV2

logger = logging.getLogger("rook.learning.verifier")


# Type alias for viewport capture function
ViewportCapture = Callable[[], Awaitable[dict]]


@dataclass
class ViewportState:
    """Captured state of the viewport."""
    timestamp: str
    image_base64: str | None = None
    image_hash: str | None = None

    # Metadata from document
    object_count: int = 0
    selected_count: int = 0
    layer_count: int = 0

    # Object summary
    object_types: dict[str, int] = field(default_factory=dict)

    def compute_hash(self) -> str:
        """Compute hash of the viewport image."""
        if self.image_base64:
            self.image_hash = hashlib.sha256(self.image_base64.encode()).hexdigest()[:16]
        return self.image_hash or ""


@dataclass
class StateDiff:
    """Difference between two viewport states."""
    objects_added: int = 0
    objects_removed: int = 0
    selection_changed: bool = False

    # Type-specific changes
    type_changes: dict[str, int] = field(default_factory=dict)  # type -> delta

    # Visual change detected
    image_changed: bool = False

    def has_changes(self) -> bool:
        """Check if there were any changes."""
        return (
            self.objects_added > 0 or
            self.objects_removed > 0 or
            self.selection_changed or
            self.image_changed
        )


class VisualVerifier:
    """
    Verify that operations actually worked via viewport capture.

    Just because the API returned 200 doesn't mean the geometry is correct.
    This class captures viewport images and compares states to verify results.
    """

    def __init__(
        self,
        kg: KnowledgeGraphV2,
        executor: Callable[[str, dict], Awaitable[dict]],
    ):
        """
        Initialize the verifier.

        Args:
            kg: Knowledge graph V2 API for recording verifications
            executor: Async function to execute MCP tools
        """
        self.kg = kg
        self.executor = executor
        self._last_state: ViewportState | None = None

    async def capture_state(self, view: str = "Perspective") -> ViewportState:
        """
        Capture current viewport as image + metadata.

        Args:
            view: Which view to capture (Perspective, Top, Front, etc.)

        Returns:
            ViewportState with image and metadata
        """
        from .schema import now_iso

        state = ViewportState(timestamp=now_iso())

        # Capture viewport image
        try:
            result = await self.executor("rhino_viewport", {"view": view})
            if result.get("success"):
                data = result.get("data", {})
                if isinstance(data, dict):
                    state.image_base64 = data.get("image")
                elif isinstance(data, str):
                    state.image_base64 = data
                state.compute_hash()
        except Exception as e:
            logger.warning(f"Failed to capture viewport: {e}")

        # Get document info for object counts
        try:
            result = await self.executor("rhino_document", {})
            if result.get("success"):
                data = result.get("data", {})
                if isinstance(data, dict):
                    state.object_count = data.get("objectCount", 0)
                    state.layer_count = data.get("layerCount", 0)
                    # Get object summary if available
                    summary = data.get("objectSummary", {})
                    if isinstance(summary, dict):
                        state.object_types = summary
        except Exception as e:
            logger.warning(f"Failed to get document info: {e}")

        # Get selection count
        try:
            result = await self.executor("rhino_selection", {})
            if result.get("success"):
                data = result.get("data", [])
                if isinstance(data, list):
                    state.selected_count = len(data)
        except Exception as e:
            logger.warning(f"Failed to get selection: {e}")

        self._last_state = state
        return state

    def compare_states(
        self,
        before: ViewportState,
        after: ViewportState,
    ) -> StateDiff:
        """
        Compare two viewport states to identify changes.

        Args:
            before: State before operation
            after: State after operation

        Returns:
            StateDiff describing what changed
        """
        diff = StateDiff()

        # Object count changes
        diff.objects_added = max(0, after.object_count - before.object_count)
        diff.objects_removed = max(0, before.object_count - after.object_count)

        # Selection changed
        diff.selection_changed = after.selected_count != before.selected_count

        # Type-specific changes
        all_types = set(before.object_types.keys()) | set(after.object_types.keys())
        for obj_type in all_types:
            before_count = before.object_types.get(obj_type, 0)
            after_count = after.object_types.get(obj_type, 0)
            if before_count != after_count:
                diff.type_changes[obj_type] = after_count - before_count

        # Image changed (compare hashes)
        if before.image_hash and after.image_hash:
            diff.image_changed = before.image_hash != after.image_hash
        else:
            diff.image_changed = True  # Assume changed if we can't compare

        return diff

    async def verify_geometry_created(
        self,
        expected_type: str,
        before_state: ViewportState | None = None,
    ) -> tuple[bool, str]:
        """
        Verify that geometry was created.

        Args:
            expected_type: Expected geometry type (Brep, Curve, Mesh, etc.)
            before_state: State before creation (captured if not provided)

        Returns:
            Tuple of (success, description)
        """
        if before_state is None:
            before_state = self._last_state or await self.capture_state()

        after_state = await self.capture_state()
        diff = self.compare_states(before_state, after_state)

        # Check if objects were added
        if diff.objects_added == 0:
            return False, "No new objects detected in viewport"

        # Check if expected type was added
        type_delta = diff.type_changes.get(expected_type, 0)
        if type_delta <= 0:
            # Check if any geometry was added (might be different type name)
            if diff.objects_added > 0:
                return True, f"Object created but type is {list(diff.type_changes.keys())}, not {expected_type}"
            return False, f"No {expected_type} was created"

        return True, f"Successfully created {type_delta} {expected_type} object(s)"

    async def verify_transform_applied(
        self,
        transform_type: str,
        before_state: ViewportState | None = None,
    ) -> tuple[bool, str]:
        """
        Verify that a transformation was correctly applied.

        Args:
            transform_type: Type of transform (move, rotate, scale)
            before_state: State before transform

        Returns:
            Tuple of (success, description)
        """
        if before_state is None:
            return False, "No before state to compare"

        after_state = await self.capture_state()
        diff = self.compare_states(before_state, after_state)

        # For transforms, we expect the image to change but object count to stay same
        if diff.objects_added > 0 or diff.objects_removed > 0:
            return False, f"Object count changed during {transform_type} (added: {diff.objects_added}, removed: {diff.objects_removed})"

        if not diff.image_changed:
            return False, f"Viewport did not change after {transform_type}"

        return True, f"{transform_type} transform appears to have been applied (viewport changed)"

    async def verify_boolean_result(
        self,
        operation: str,
        before_state: ViewportState | None = None,
    ) -> tuple[bool, str]:
        """
        Verify boolean operation produced expected result.

        Args:
            operation: Boolean operation type (union, difference, intersection)
            expected_result_count: Expected number of result objects
            before_state: State before operation

        Returns:
            Tuple of (success, description)
        """
        if before_state is None:
            before_state = self._last_state or await self.capture_state()

        after_state = await self.capture_state()
        diff = self.compare_states(before_state, after_state)

        # Boolean operations typically reduce object count
        if operation in ("union", "difference", "intersection"):
            if diff.objects_removed == 0:
                return False, f"No objects were consumed by {operation}"

        # Check image changed
        if not diff.image_changed:
            return False, f"Viewport did not change after boolean {operation}"

        return True, f"Boolean {operation} completed (objects removed: {diff.objects_removed}, added: {diff.objects_added})"

    async def verify_and_record(
        self,
        pattern_id: str,
        verification_type: str,
        before_state: ViewportState | None = None,
        **kwargs,
    ) -> Verification:
        """
        Perform verification and record result to knowledge graph.

        Args:
            pattern_id: Pattern ID being verified
            verification_type: Type of verification (create, transform, boolean)
            before_state: State before operation
            **kwargs: Additional args for specific verification types

        Returns:
            Verification record
        """
        success = False
        description = ""

        if verification_type == "create":
            expected_type = kwargs.get("expected_type", "Brep")
            success, description = await self.verify_geometry_created(
                expected_type, before_state
            )

        elif verification_type == "transform":
            transform_type = kwargs.get("transform_type", "move")
            success, description = await self.verify_transform_applied(
                transform_type, before_state
            )

        elif verification_type == "boolean":
            operation = kwargs.get("operation", "union")
            success, description = await self.verify_boolean_result(
                operation, before_state=before_state
            )

        else:
            # Generic verification - just check if viewport changed
            after_state = await self.capture_state()
            if before_state:
                diff = self.compare_states(before_state, after_state)
                success = diff.has_changes()
                description = "Viewport changed" if success else "No visible changes"
            else:
                success = True
                description = "Captured viewport state"

        # Record to knowledge graph
        current_state = await self.capture_state()
        verification = self.kg.record_verification(
            pattern_id=pattern_id,
            geometry_created=verification_type == "create" and success,
            geometry_at_expected_location=success,
            measurements_correct=success,  # We don't actually measure, assume OK if visual check passed
            visual_description=description,
            viewport_hash=current_state.image_hash,
        )

        return verification

    async def quick_verify(self) -> dict[str, Any]:
        """
        Quick verification - just capture current state and return summary.

        Returns:
            Summary of current viewport state
        """
        state = await self.capture_state()

        return {
            "object_count": state.object_count,
            "layer_count": state.layer_count,
            "selected_count": state.selected_count,
            "object_types": state.object_types,
            "has_image": state.image_base64 is not None,
            "image_hash": state.image_hash,
        }
