"""Regression tests for gh_edit / gh_move schema field names in agent prompts.

Anchored against the 2026-04-29 Architect-agent failure: the prompts taught
`id`/`component`/`nickname`/`actions`/`moves` and flat `x`/`y` for create
entries. The runtime schema accepts `temp_id`/`name`/`nick`, no `actions`
wrapper, `pos: [x, y]` in gh_edit.create, and `gh_move.positions`.

See docs/superpowers/plans/2026-04-29-agent-prompt-tool-schema-audit.md.

The runtime worker/architect/specialist/scripter guidance comes from the shared
persona source in personas/<name>/{personality,role}.md.
The `prompts/WORKER.md` file is a display snapshot loaded directly by humans
debugging an agent — it must also stay in sync with the schema, but is checked
as a raw file read here.
"""
import re
from pathlib import Path

import pytest

from rook.agent.personas import load_persona


# Patterns that MUST NOT appear in any agent-facing prompt.
STALE_PATTERNS = [
    (r'"id"\s*:\s*"T\d', 'uses {"id": "T..."} for gh_edit.create — should be "temp_id"'),
    (r'"component"\s*:', 'uses {"component": "..."} — should be "name"'),
    (r'"nickname"\s*:', 'uses {"nickname": "..."} — should be "nick"'),
    (r'"actions"\s*:\s*\{', 'wraps gh_edit args in an {"actions": {...}} object — params are flat'),
    (r'"moves"\s*:', 'uses {"moves": [...]} for gh_move — should be "positions"'),
    (r'x/y offsets when creating', 'prose says "x/y offsets when creating" — gh_edit.create uses pos: [x, y]'),
]

# Tokens that SHOULD appear in any prompt that documents gh_edit.
EXPECTED_TOKENS = [
    'temp_id',          # the create-entry id field
    '"epoch"',          # required top-level field
    '"pos"',            # create-entry position
]


def _assert_clean(prompt: str, label: str) -> None:
    for pattern, why in STALE_PATTERNS:
        match = re.search(pattern, prompt)
        assert match is None, (
            f"{label}: stale schema reference matched /{pattern}/ ({why}). "
            f"Excerpt: {prompt[max(0, match.start()-40):match.end()+40]!r}"
        )


def _assert_has_schema_cues(prompt: str, label: str) -> None:
    for token in EXPECTED_TOKENS:
        assert token in prompt, (
            f"{label}: missing expected schema cue {token!r} — the prompt no "
            f"longer documents the current gh_edit shape."
        )


def _persona_text(persona: str) -> str:
    content = load_persona(persona)
    return "\n".join((content["personality"], content["role"]))


@pytest.mark.parametrize("persona", ["worker", "architect", "specialist", "scripter"])
def test_persona_prompt_uses_current_gh_edit_schema(persona):
    """Shared persona guidance must use current schema field names."""
    prompt = _persona_text(persona)
    _assert_clean(prompt, f"persona {persona}")


@pytest.mark.parametrize("persona", ["worker", "architect", "specialist"])
def test_persona_prompt_documents_current_gh_edit_cues(persona):
    """Personas that include a gh_edit JSON example must show current schema tokens.

    Scripter is excluded — its role.md only has a negative example
    ("do NOT use gh_edit with name='Python 3 Script'") and is not expected
    to carry a positive gh_edit example with epoch/pos/temp_id.
    """
    prompt = _persona_text(persona)
    _assert_has_schema_cues(prompt, f"persona {persona}")


@pytest.mark.parametrize("persona", ["worker", "architect"])
def test_persona_prompt_documents_gh_move_signature(persona):
    """Each persona that lists `gh_move` must spell out the full signature.

    Without the explicit positions=[{guid, x, y}] signature, agents have
    historically invented gh_move(moves=[{id, x, y}]). Parameterized so a
    drift in one persona doesn't get masked by the other still having it
    (concatenation would have hidden a single-prompt regression).
    """
    prompt = _persona_text(persona)
    assert "gh_move(positions=" in prompt, (
        f"persona {persona}: prompt lists gh_move but no longer documents the "
        f"gh_move(positions=...) signature — agents will guess the wrong field names."
    )


def test_worker_md_display_snapshot_uses_current_schema():
    """prompts/WORKER.md is a human-readable display snapshot — must stay in sync."""
    mcp_server_root = Path(__file__).resolve().parents[1]
    worker_md = mcp_server_root / "src" / "rook" / "agent" / "prompts" / "WORKER.md"
    assert worker_md.exists(), f"missing display snapshot: {worker_md}"
    content = worker_md.read_text(encoding="utf-8")
    _assert_clean(content, "prompts/WORKER.md")
    _assert_has_schema_cues(content, "prompts/WORKER.md")
    assert "gh_move(positions=" in content, (
        "prompts/WORKER.md no longer documents the gh_move(positions=...) signature."
    )
