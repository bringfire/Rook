"""Tests for PromptBuilder — system prompt assembly from personas."""
import pytest

from rook.agent.chat.prompt_builder import PromptBuilder
from rook.agent.tool_groups import TOOL_GROUPS


def test_build_system_prompt_has_personality():
    builder = PromptBuilder()
    prompt = builder.build_system("worker")
    # Worker persona should have some content (personality.md + role.md)
    assert len(prompt) > 0
    assert isinstance(prompt, str)


def test_build_system_prompt_unknown_persona():
    builder = PromptBuilder()
    # Unknown persona should still return a usable prompt (empty personality is OK)
    prompt = builder.build_system("nonexistent_persona_xyz")
    assert isinstance(prompt, str)
    assert len(prompt) > 0  # Should have at least the base instructions


def test_resolve_model_from_profile():
    builder = PromptBuilder()
    model = builder.resolve_model("worker")
    # Should resolve to something (depends on active profile)
    assert isinstance(model, str)
    assert len(model) > 0


def test_resolve_model_for_planner():
    builder = PromptBuilder()
    worker_model = builder.resolve_model("worker")
    planner_model = builder.resolve_model("planner")
    # Planner typically gets a stronger model than worker
    # (both should resolve, that's the important thing)
    assert isinstance(planner_model, str)
    assert len(planner_model) > 0


def test_system_prompt_treats_in_chat_ui_as_ui_block_signal():
    prompt = PromptBuilder().build_system("worker")

    assert "here in chat" in prompt
    assert "ui_block" in prompt
    assert "Do not substitute Grasshopper sliders" in prompt


def test_system_prompt_requires_remediation_for_unverified_tool_results():
    prompt = PromptBuilder().build_system("worker")

    assert "verified=false" in prompt
    assert "partial_success" in prompt
    assert "edit_summary.errors" in prompt
    assert "not safe to build on" in prompt


def test_gh_canvas_group_includes_status_health_check():
    assert "gh_status" in TOOL_GROUPS["gh_canvas"]


# ---------- GH script-component routing — persona-prompt regressions ----------
# Anchor against drift that misrouted an agent to rhino_execute on 2026-04-21.
# The runtime worker/architect/scripter prompts are built from personas/<name>/
# role.md (NOT from prompts/WORKER.md, which is a display snapshot). These
# personas all touch GH scripting workflows — their prompts must not advertise
# gh_set_script as Py3-only and must name the dedicated script-creation tools
# that are preloaded via the gh_canvas group (tool_groups.py:289).
# See rook_docs/2026-04-21-gh-script-component-routing-design-pass.md §PR-1.


@pytest.mark.parametrize("persona", ["worker", "architect", "scripter"])
def test_persona_prompt_script_tool_language_is_capability_accurate(persona):
    builder = PromptBuilder()
    prompt = builder.build_system(persona)

    # Old Py3-only drift strings must not reappear on any of the three personas.
    assert "set Python 3 script source" not in prompt, (
        f"{persona}: Py3-only preloaded-tools drift — see design-pass memo"
    )
    assert "to set Python 3 code" not in prompt, (
        f"{persona}: Py3-only tool-usage guidance drift (architect:89 site today)"
    )

    # Dedicated script-creation tools must appear in the persona prompt.
    # They're preloaded in the gh_canvas group — absent mention is the same
    # class of drift that caused the 2026-04-21 incident.
    assert "gh_create_python_script" in prompt, (
        f"{persona}: missing gh_create_python_script; preloaded in gh_canvas "
        "but not mentioned in persona prompt"
    )
    assert "gh_create_csharp_script" in prompt, (
        f"{persona}: missing gh_create_csharp_script"
    )
    # PR-2: unified gh_create_script tool is now primary; aliases remain for
    # back-compat. Persona prompts must advertise the unified tool so agents
    # can reach for the canonical discriminator-param entry point first.
    assert "gh_create_script" in prompt, (
        f"{persona}: missing gh_create_script (unified tool, PR-2) — "
        "see rook_docs/2026-04-21-gh-script-component-routing-design-pass.md §PR-2"
    )
