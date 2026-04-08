"""Execution Policy — verification layer for the chat panel.

Implements the "guarded execution runtime" architecture:

    LLM proposes action
        → dispatch
        → post-execution verification  (here)
        → annotated result → LLM

The model remains the planner. This module adds two new architectural
components on top of the existing dispatch layer:

  Verification Layer:
    Checks observable postconditions (objectsCreated, prompt idle state)
    and marks results as verified=True/False with a machine-readable note.
    "Success" is no longer inferred from tool return — it requires evidence.

  Prompt/Modal Observer:
    Treats a non-idle Rhino prompt as a formal execution signal.
    If the prompt is active after a tool call, the command did not complete.
    If the prompt check itself fails, that is treated as unknown/unverified
    rather than silently passing.

Design notes:
  - /execute (CommandHandler.cpp) returns objectCount = total objects in the
    document after execution, NOT a created-object delta. Do not use objectCount
    as a creation verification signal — it gives false positives in non-empty
    documents. Only objectsCreated (returned by /create, /command, etc.) is
    a reliable delta.
  - rhino_execute_intent is multipurpose (create, modify, query, delete). It is
    NOT in CREATION_TOOLS because objectsCreated=0 is not a failure signal for
    non-creation intents (e.g., "move all objects to layer X"). Its verification
    needs are determined by the substrate it actually used at runtime.

References:
  - CommandInteractiveHandler.cpp: GET /command/prompt → {prompt, is_active}
  - CommandHandler.cpp: /create, /command return objectsCreated (delta)
  - CommandHandler.cpp: /execute returns objectCount (total, not delta)
  - SessionHandler.cpp: GET /session/history → per-command success/error
"""

from typing import Optional


# ─── Risk Classification ───────────────────────────────────────────────────

# Tools that return objectsCreated as a created-object DELTA.
# objectsCreated=0 on apparent success is a reliable silent-failure signal.
# Only include tools whose C++ handlers genuinely return this delta field.
CREATION_TOOLS: frozenset = frozenset({
    "rhino_create",
    "rhino_boolean",
    "rhino_loft",
    "rhino_sweep",
    "rhino_extrude",
    # rhino_execute_intent excluded: multipurpose (create/modify/query/delete),
    #   objectsCreated=0 is a false failure for non-creation intents.
    # rhino_execute excluded: /execute returns objectCount (total), not a delta;
    #   objectCount > 0 in a non-empty document is not evidence of creation.
})

# Tools that invoke RunScript or _-RunPythonScript — prompt/input blocking is
# still possible even though native /execute now returns script failures as
# structured errors instead of Rhino's default error popups.
MODAL_RISK_TOOLS: frozenset = frozenset({
    "rhino_execute",  # Python script via _-RunPythonScript
    "rhino_command",  # scripted command string via RunScript
})

# Union: tools where post-execution prompt check is warranted
NEEDS_VERIFICATION: frozenset = CREATION_TOOLS | MODAL_RISK_TOOLS

# rhino_execute_intent is verified by substrate rather than tool name.
COMMAND_SUBSTRATES: frozenset = frozenset({
    "known_command",
    "interactive",
})


def _extract_route_taken(result: dict) -> str:
    """Return the actual execution substrate recorded in a tool result."""
    if not isinstance(result, dict):
        return ""
    data = result.get("data", {})
    if isinstance(data, dict):
        route = data.get("execution_route") or data.get("route_taken")
        if isinstance(route, str):
            return route
    route = result.get("execution_route") or result.get("route_taken")
    return route if isinstance(route, str) else ""


def needs_verification(tool_name: str, result: Optional[dict] = None) -> bool:
    """Determine whether a tool result needs guarded-runtime verification."""
    if tool_name in NEEDS_VERIFICATION:
        return True

    if tool_name == "rhino_execute_intent":
        return _extract_route_taken(result or {}) in COMMAND_SUBSTRATES

    return False


# ─── Result Annotation ────────────────────────────────────────────────────

def annotate_result(
    tool_name: str,
    result: dict,
    prompt_state: Optional[dict] = None,
    prompt_poll_failed: bool = False,
) -> dict:
    """Annotate a tool result with verification metadata.

    Adds ``verified`` (bool) and optionally ``verification_note`` (str) to
    the result dict. This replaces implicit "success because no exception"
    with evidence-based confirmation.

    The annotation is additive — it never removes or changes existing fields.
    A shallow copy is made before writing to avoid mutating the caller's dict.

    Args:
        tool_name:         The dispatched tool name.
        result:            Raw dict returned by the tool executor.
        prompt_state:      Optional result of a ``rhino_command_prompt`` call.
                           If ``is_active=True``, Rhino is blocked on input.
        prompt_poll_failed: True when the rhino_command_prompt call raised an
                            exception. For modal-risk tools this is treated as
                            unverified rather than silently passing.
    """
    if not isinstance(result, dict):
        return result

    annotations: list[str] = []
    verified = bool(result.get("success", False))
    route_taken = _extract_route_taken(result)
    is_modal_risk = (
        tool_name in MODAL_RISK_TOOLS
        or (tool_name == "rhino_execute_intent" and route_taken in COMMAND_SUBSTRATES)
    )
    needs_postcheck = needs_verification(tool_name, result)

    # ── Prompt poll failure: cannot confirm Rhino is idle ──
    # Treat as unverified for modal-risk tools — a failed prompt poll on a
    # tool that uses RunScript may mean Rhino is blocked or unresponsive.
    if prompt_poll_failed and is_modal_risk:
        verified = False
        annotations.append(
            "Could not verify Rhino prompt state after execution — Rhino may be "
            "blocked. Call rhino_command_prompt manually to check the current state."
        )

    # ── Strongest signal: non-idle prompt means the command did not finish ──
    elif prompt_state and isinstance(prompt_state, dict):
        pdata = prompt_state.get("data", {})
        if isinstance(pdata, dict) and pdata.get("is_active"):
            verified = False
            prompt_text = pdata.get("prompt", "")
            annotations.append(
                f"Rhino is waiting for input (prompt: {prompt_text!r}). "
                "The command did not complete. Cancel with "
                "rhino_command_interactive_cancel, or supply the required "
                "input via rhino_command_interactive_send."
            )

    # ── Creation check: objectsCreated=0 on a geometry tool is a silent failure ──
    # Only uses the objectsCreated field (a delta). objectCount (total) is not
    # checked here because it is not a reliable creation signal.
    if tool_name in CREATION_TOOLS:
        data = result.get("data", {})
        if isinstance(data, dict):
            obj_created = data.get("objectsCreated")
            if obj_created == 0:
                verified = False
                annotations.append(
                    "objectsCreated=0 — the operation may have failed silently. "
                    "Call session_history to inspect the error, or retry with a "
                    "higher-reliability substrate (rhino_create, rhino_boolean, etc.)."
                )

    # ── Modal-risk reminder when no other issue was detected ──
    if is_modal_risk and not annotations:
        route_note = ""
        if tool_name == "rhino_execute_intent" and route_taken:
            route_note = f" The intent runtime used the {route_taken} substrate."
        annotations.append(
            "Script or command executed. Confirm the expected change occurred: "
            "check objectsCreated in this result, or call rhino_objects. "
            "Script failures should come back as tool errors, but the script "
            "can still block Rhino if it prompts for input or opens UI."
            + route_note
        )

    if annotations or needs_postcheck:
        result = dict(result)  # shallow copy — don't mutate the caller's dict
        result["verified"] = verified
        if annotations:
            result["verification_note"] = " | ".join(annotations)

    return result
