# Profile Boundary Audit v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a narrow automated guard proving `scene_object_semantic_context` does not hard-code known domain relationship/object vocabulary in string literals or comments.

**Architecture:** This is an audit/test-only slice. The card module should remain a generic presentation layer; relationship meaning remains in profiles, fixtures, tests, docs, and authored graphs. The guard uses Python `tokenize` and inspects only `STRING` and `COMMENT` tokens in `mcp_server/src/rook/scene/object_semantic_context.py`.

**Tech Stack:** Python 3, `pytest`, standard-library `tokenize`, existing Rook MCP test layout.

---

## File Structure

- Create `mcp_server/tests/test_object_semantic_context_profile_boundary.py`
  - Contains a local token scanner helper.
  - Defines the forbidden vocabulary list from the approved spec, excluding `space`.
  - Tests the real production card module.
  - Tests synthetic string/comment/identifier cases so the guard behavior is explicit.

- Do not modify `mcp_server/src/rook/scene/object_semantic_context.py` unless the guard fails against the real file.
- Do not modify `mcp_server/src/rook/scene/relationship_profile.py`.
- Do not modify projection, inspector, tool registration, or fixture code.

---

### Task 1: Add Tokenized Profile-Boundary Guard

**Files:**
- Create: `mcp_server/tests/test_object_semantic_context_profile_boundary.py`

- [ ] **Step 1: Create the guard test module**

Create `mcp_server/tests/test_object_semantic_context_profile_boundary.py` with this exact content:

```python
from __future__ import annotations

import io
import tokenize
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CARD_MODULE_PATH = REPO_ROOT / "mcp_server" / "src" / "rook" / "scene" / "object_semantic_context.py"

FORBIDDEN_CARD_DOMAIN_TERMS = {
    "connects",
    "supports",
    "hosted_by",
    "voids",
    "penetrates",
    "bounded_by",
    "column",
    "slab",
    "wall",
    "door",
    "opening",
    "duct",
    "member",
    "joint",
    "architectural_relationship_fixture",
    "pearson_robot_skeleton_graph",
}


def _string_and_comment_tokens_from_bytes(source: bytes) -> list[tokenize.TokenInfo]:
    return [
        token
        for token in tokenize.tokenize(io.BytesIO(source).readline)
        if token.type in {tokenize.STRING, tokenize.COMMENT}
    ]


def _string_and_comment_tokens(path: Path) -> list[tokenize.TokenInfo]:
    with path.open("rb") as fh:
        return [
            token
            for token in tokenize.tokenize(fh.readline)
            if token.type in {tokenize.STRING, tokenize.COMMENT}
        ]


def _domain_term_hits(tokens: list[tokenize.TokenInfo]) -> list[tuple[str, str, tuple[int, int]]]:
    hits: list[tuple[str, str, tuple[int, int]]] = []
    for token in tokens:
        token_text = token.string
        normalized = token_text.lower()
        for term in sorted(FORBIDDEN_CARD_DOMAIN_TERMS):
            if term in normalized:
                hits.append((term, token_text, token.start))
    return hits


def assert_no_card_domain_terms_in_strings_or_comments(path: Path) -> None:
    hits = _domain_term_hits(_string_and_comment_tokens(path))
    assert hits == [], (
        f"{path} must not hard-code profile/domain vocabulary in string literals or comments; "
        f"hits={hits!r}"
    )


def test_object_semantic_context_has_no_domain_terms_in_strings_or_comments():
    assert_no_card_domain_terms_in_strings_or_comments(CARD_MODULE_PATH)


def test_guard_catches_forbidden_string_literal():
    tokens = _string_and_comment_tokens_from_bytes(b'MESSAGE = "supports this slab"\\n')

    assert set(_domain_term_hits(tokens)) == {
        ("slab", '"supports this slab"', (1, 10)),
        ("supports", '"supports this slab"', (1, 10)),
    }


def test_guard_catches_mixed_case_forbidden_string_literal():
    tokens = _string_and_comment_tokens_from_bytes(b'MESSAGE = "Supports selected Wall"\\n')

    assert set(_domain_term_hits(tokens)) == {
        ("supports", '"Supports selected Wall"', (1, 10)),
        ("wall", '"Supports selected Wall"', (1, 10)),
    }


def test_guard_catches_forbidden_comment():
    tokens = _string_and_comment_tokens_from_bytes(b"# hosted_by belongs in the profile, not the card\\n")

    assert _domain_term_hits(tokens) == [
        ("hosted_by", "# hosted_by belongs in the profile, not the card", (1, 0))
    ]


def test_guard_ignores_forbidden_terms_in_identifiers():
    tokens = _string_and_comment_tokens_from_bytes(
        b"supports = relationship.get('relationshipLabel')\\n"
    )

    assert _domain_term_hits(tokens) == []
```

- [ ] **Step 2: Run the new tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_object_semantic_context_profile_boundary.py -q
```

Expected outcome:

- If all tests pass, continue to Step 3.
- If `test_object_semantic_context_has_no_domain_terms_in_strings_or_comments` fails, inspect the reported token hits in `object_semantic_context.py`. Remove only real domain vocabulary leaks from production card strings/comments. Do not remove generic fallback wording such as `connected by` or `relates to`.

- [ ] **Step 3: Run focused card/profile tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_object_semantic_context_profile_boundary.py mcp_server/tests/test_object_semantic_context.py mcp_server/tests/test_relationship_profile.py -q
```

Expected:

- profile boundary tests pass;
- object semantic context tests pass;
- relationship profile tests pass.

- [ ] **Step 4: Commit the guard**

Run:

```powershell
git add mcp_server/tests/test_object_semantic_context_profile_boundary.py
git commit -m "test: guard semantic card profile boundary"
```

Expected: one commit containing only the new test module, unless Step 2 found and removed a real production leak.

---

### Task 2: Final Verification and Handoff

**Files:**
- Read: `docs/superpowers/specs/2026-06-28-profile-boundary-audit-v1-design.md`
- Verify: `mcp_server/tests/test_object_semantic_context_profile_boundary.py`

- [ ] **Step 1: Run focused regression tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_object_semantic_context_profile_boundary.py mcp_server/tests/test_object_semantic_context.py mcp_server/tests/test_object_semantic_context_tool.py mcp_server/tests/test_relationship_profile.py mcp_server/tests/test_relationship_profile_tool.py -q
```

Expected: all collected tests pass.

- [ ] **Step 2: Run compatibility smoke tests for adjacent semantic layers**

Run:

```powershell
python -m pytest mcp_server/tests/test_semantic_relationship_inspector.py mcp_server/tests/test_relationship_fact_projection.py -q
```

Expected: all collected tests pass.

- [ ] **Step 3: Run whitespace and commit checks**

Run:

```powershell
git diff --check
git show --check --stat HEAD
git status --short --branch
```

Expected:

- `git diff --check` emits no output and exits 0;
- `git show --check --stat HEAD` exits 0;
- status shows a clean `codex/profile-boundary-audit-v1` branch.

- [ ] **Step 4: Push the branch**

Run:

```powershell
git push -u origin codex/profile-boundary-audit-v1
```

Expected: branch pushes successfully.

---

## Self-Review Notes

- Spec coverage: The plan implements the narrow tokenized guard for `object_semantic_context.py`, excludes `space`, leaves fixtures/docs/default profile unconstrained, and does not add ontology, evidence, projection, or inspector scope.
- Placeholder scan: No placeholder markers or unspecified implementation steps remain.
- Type consistency: Helpers use `Path`, `bytes`, and `tokenize.TokenInfo` consistently; no production APIs are introduced.
