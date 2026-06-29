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
    tokens = _string_and_comment_tokens_from_bytes(b'MESSAGE = "supports this slab"\n')

    assert set(_domain_term_hits(tokens)) == {
        ("slab", '"supports this slab"', (1, 10)),
        ("supports", '"supports this slab"', (1, 10)),
    }


def test_guard_catches_mixed_case_forbidden_string_literal():
    tokens = _string_and_comment_tokens_from_bytes(b'MESSAGE = "Supports selected Wall"\n')

    assert set(_domain_term_hits(tokens)) == {
        ("supports", '"Supports selected Wall"', (1, 10)),
        ("wall", '"Supports selected Wall"', (1, 10)),
    }


def test_guard_catches_forbidden_comment():
    tokens = _string_and_comment_tokens_from_bytes(b"# hosted_by belongs in the profile, not the card\n")

    assert _domain_term_hits(tokens) == [
        ("hosted_by", "# hosted_by belongs in the profile, not the card", (1, 0))
    ]


def test_guard_ignores_forbidden_terms_in_identifiers():
    tokens = _string_and_comment_tokens_from_bytes(
        b"supports = relationship.get('relationshipLabel')\n"
    )

    assert _domain_term_hits(tokens) == []
