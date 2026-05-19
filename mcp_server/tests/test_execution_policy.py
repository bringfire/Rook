"""Tests for execution_policy.py — the chat panel verification layer."""

import pytest
from rook.agent.chat.execution_policy import (
    CREATION_TOOLS,
    MODAL_RISK_TOOLS,
    NEEDS_VERIFICATION,
    annotate_result,
)


# ─── Classification ───────────────────────────────────────────────────────────

def test_needs_verification_is_union():
    assert NEEDS_VERIFICATION == CREATION_TOOLS | MODAL_RISK_TOOLS


def test_rhino_execute_is_modal_risk_only():
    # rhino_execute is MODAL_RISK only — /execute returns objectCount (total),
    # not a created-object delta, so it must not be in CREATION_TOOLS.
    assert "rhino_execute" in MODAL_RISK_TOOLS
    assert "rhino_execute" not in CREATION_TOOLS
    assert "rhino_execute" in NEEDS_VERIFICATION


def test_rhino_command_is_modal_risk():
    assert "rhino_command" in MODAL_RISK_TOOLS


def test_rhino_create_is_creation():
    assert "rhino_create" in CREATION_TOOLS
    assert "rhino_create" in NEEDS_VERIFICATION


def test_rhino_execute_intent_not_in_creation_tools():
    # rhino_execute_intent is multipurpose (create/modify/query/delete).
    # objectsCreated=0 is not a failure signal for non-creation intents.
    assert "rhino_execute_intent" not in CREATION_TOOLS
    assert "rhino_execute_intent" not in NEEDS_VERIFICATION


def test_rhino_ping_not_in_verification():
    assert "rhino_ping" not in NEEDS_VERIFICATION


# ─── annotate_result — non-mutation ──────────────────────────────────────────

def test_annotate_does_not_mutate_original():
    original = {"success": True, "data": {"objectsCreated": 1}}
    annotated = annotate_result("rhino_create", original)
    assert "verified" not in original
    assert "verified" in annotated


def test_annotate_non_dict_passthrough():
    result = annotate_result("rhino_create", "not a dict")
    assert result == "not a dict"


def test_non_verification_tool_unchanged():
    original = {"success": True, "data": {}}
    result = annotate_result("rhino_ping", original)
    assert result is original  # same object, not a copy


# ─── annotate_result — creation verification ─────────────────────────────────

def test_creation_objectsCreated_nonzero_verified():
    result = annotate_result("rhino_create", {"success": True, "data": {"objectsCreated": 2}})
    assert result["verified"] is True
    assert "verification_note" not in result


def test_creation_objectsCreated_zero_not_verified():
    result = annotate_result("rhino_create", {"success": True, "data": {"objectsCreated": 0}})
    assert result["verified"] is False
    assert "objectsCreated=0" in result["verification_note"]


def test_creation_does_not_use_objectCount_fallback():
    # objectCount is the total scene count from /execute — not a created-object delta.
    # It must NOT trigger the creation failure signal.
    result = annotate_result("rhino_create", {"success": True, "data": {"objectCount": 5}})
    # objectsCreated is absent → no creation check fires → verified = tool's own success
    assert result["verified"] is True


def test_rhino_execute_objectCount_does_not_trigger_creation_check():
    # rhino_execute is MODAL_RISK only, not CREATION. objectCount=0 must not
    # produce a false creation-failure annotation.
    result = annotate_result("rhino_execute", {"success": True, "data": {"objectCount": 0}})
    assert result["verified"] is True
    assert "objectsCreated=0" not in result.get("verification_note", "")


# ─── annotate_result — modal risk ────────────────────────────────────────────

def test_modal_risk_success_adds_reminder():
    result = annotate_result("rhino_execute", {"success": True, "data": {"objectCount": 3}})
    assert result["verified"] is True
    assert "verification_note" in result
    assert "rhino_objects" in result["verification_note"]


def test_modal_risk_reminder_mentions_input_blocking_caveat():
    result = annotate_result("rhino_execute", {"success": True, "data": {}})
    note = result["verification_note"].lower()
    assert "prompts for input" in note or "opens ui" in note


def test_modal_risk_failure_unverified():
    result = annotate_result("rhino_command", {"success": False, "data": "error"})
    assert result["verified"] is False


# ─── annotate_result — prompt state ──────────────────────────────────────────

def test_active_prompt_overrides_to_unverified():
    prompt_state = {"success": True, "data": {"is_active": True, "prompt": "Select objects"}}
    result = annotate_result(
        "rhino_command",
        {"success": True, "data": {}},
        prompt_state=prompt_state,
    )
    assert result["verified"] is False
    assert "Select objects" in result["verification_note"]
    assert "rhino_command_prompt" in result["verification_note"]
    assert "rhino_command_interactive_cancel" in result["verification_note"]
    assert "rhino_command_interactive_send" not in result["verification_note"]


def test_idle_prompt_does_not_override():
    prompt_state = {"success": True, "data": {"is_active": False, "prompt": "Command:"}}
    result = annotate_result(
        "rhino_execute",
        {"success": True, "data": {"objectCount": 1}},
        prompt_state=prompt_state,
    )
    assert result["verified"] is True


def test_none_prompt_state_ignored():
    result = annotate_result("rhino_execute", {"success": True, "data": {}}, prompt_state=None)
    assert "verified" in result


def test_malformed_prompt_state_ignored():
    result = annotate_result(
        "rhino_command",
        {"success": True, "data": {}},
        prompt_state="not a dict",
    )
    assert result["verified"] is True


# ─── annotate_result — prompt poll failure ───────────────────────────────────

def test_prompt_poll_failed_modal_risk_unverified():
    # If rhino_command_prompt raised an exception, modal-risk tool is unverified.
    result = annotate_result(
        "rhino_execute",
        {"success": True, "data": {}},
        prompt_state=None,
        prompt_poll_failed=True,
    )
    assert result["verified"] is False
    assert "Could not verify" in result["verification_note"]


def test_prompt_poll_failed_creation_tool_not_affected():
    # For CREATION_TOOLS (not modal-risk), prompt poll failure should not
    # force unverified — those tools don't block the prompt in the same way.
    result = annotate_result(
        "rhino_create",
        {"success": True, "data": {"objectsCreated": 2}},
        prompt_state=None,
        prompt_poll_failed=True,
    )
    assert result["verified"] is True


def test_prompt_poll_failed_takes_precedence_over_prompt_state():
    # If both prompt_poll_failed=True and a prompt_state is somehow provided,
    # poll_failed should win (else branch means prompt_state is skipped).
    prompt_state = {"success": True, "data": {"is_active": False}}
    result = annotate_result(
        "rhino_command",
        {"success": True, "data": {}},
        prompt_state=prompt_state,
        prompt_poll_failed=True,
    )
    assert result["verified"] is False
    assert "Could not verify" in result["verification_note"]
