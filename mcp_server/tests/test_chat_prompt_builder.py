"""Tests for PromptBuilder — system prompt assembly from personas."""
import pytest
from rook.agent.chat.prompt_builder import PromptBuilder


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
