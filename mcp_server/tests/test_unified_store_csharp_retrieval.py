"""UnifiedStore retrieval tests for the modern RhinoCode C# Script note.

Pins the Layer 1 knowledge-note changes on the real retrieval surface —
`UnifiedStore.resolve_components()` reading note files from
`knowledge/gh/notes/`. Tests assert the retrieval contract, not the
downstream ranking (which is covered by `test_dspy_resolver_csharp_ranking`).

See rook_docs/work-queue.md "Prefer modern RhinoCode C# Script over legacy
ComponentLegacyCsScript for C# GH intents" and the 2026-04-21 follow-up
plan that produced this fix.
"""

from __future__ import annotations

import pytest

from rook.learning.unified_store import get_unified_store


_MODERN_GUID = "b6ba1144-02d6-4a2d-b53c-ec62e290eeb7"
_LEGACY_GUID = "88c3f2b5-27f7-48a2-9528-1397fad62b93"
_MODERN_PYTHON_GUID = "719467e6-7cf5-4848-99b0-c5dd57e5442c"


def _guids(candidates):
    return [c.get("guid") for c in candidates]


def test_modern_csharp_script_note_is_retrievable_by_csharp_keyword():
    """Before this PR, `"csharp"` returned zero candidates — modern C#
    had no note in the knowledge store. L1 adds the note with `"csharp"`
    as both a keyword and a trigger_intent.
    """
    store = get_unified_store()
    candidates = store.resolve_components("csharp", limit=10)
    guids = _guids(candidates)
    assert _MODERN_GUID in guids, (
        f"Modern C# Script must be retrievable by 'csharp'; got {guids!r}"
    )


def test_modern_csharp_script_is_retrievable_by_rhinocode_csharp():
    """The intent phrasing that disambiguates modern from legacy must
    resolve uniquely to modern (legacy does not carry a `rhinocode`
    keyword post-narrow).
    """
    store = get_unified_store()
    candidates = store.resolve_components("rhinocode c#", limit=10)
    guids = _guids(candidates)
    assert _MODERN_GUID in guids
    assert _LEGACY_GUID not in guids, (
        f"Legacy must not match 'rhinocode c#' after L1 narrowing; got {guids!r}"
    )


def test_generic_csharp_script_intent_surfaces_both_candidates():
    """The ranking layer (L3) relies on both modern and legacy arriving
    in the resolver's candidate pool for a generic `"C# script"` intent.
    Pin that retrieval returns BOTH (ranking is verified at the resolver
    level in `test_dspy_resolver_csharp_ranking`).
    """
    store = get_unified_store()
    candidates = store.resolve_components("create a C# script", limit=10)
    guids = _guids(candidates)
    assert _MODERN_GUID in guids, (
        f"Modern C# missing from 'create a C# script' candidates; got {guids!r}"
    )
    assert _LEGACY_GUID in guids, (
        f"Legacy C# missing from 'create a C# script' candidates; got {guids!r}"
    )


def test_legacy_cue_routes_legacy_first():
    """Legacy-specific intent cues (`legacy`, `dotnet`, `gh1`) must
    put the legacy candidate ahead of modern — the L1 narrowing added
    these as first-class triggers on the legacy note.
    """
    store = get_unified_store()
    for cue_intent in ("create a legacy C# script", "dotnet script"):
        candidates = store.resolve_components(cue_intent, limit=10)
        guids = _guids(candidates)
        assert _LEGACY_GUID in guids, (
            f"Legacy missing for cue intent {cue_intent!r}; got {guids!r}"
        )
        # Legacy must appear ABOVE modern when the legacy cue fires.
        if _MODERN_GUID in guids:
            assert guids.index(_LEGACY_GUID) < guids.index(_MODERN_GUID), (
                f"Legacy must outrank modern under cue {cue_intent!r}; got {guids!r}"
            )


def test_python_retrieval_unchanged_after_csharp_note_addition():
    """Regression floor: adding the modern C# note + narrowing the legacy
    C# note must not degrade Python retrieval. Python 3 must still
    surface as a top candidate for `"python script"`.
    """
    store = get_unified_store()
    candidates = store.resolve_components("python script", limit=10)
    guids = _guids(candidates)
    assert _MODERN_PYTHON_GUID in guids, (
        f"Python 3 Script regressed from 'python script' candidates; got {guids!r}"
    )


def test_knowledge_store_query_surfaces_modern_csharp_guid():
    """End-to-end integration: `get_gh_knowledge_store().query(intent)`
    (the actual gh_execute_intent entry point) must expose the modern
    C# GUID in its `guids` list for a C# intent.
    """
    from rook.learning.gh_knowledge import get_gh_knowledge_store

    ghk = get_gh_knowledge_store()
    result = ghk.query("create a C# script", depth="context")
    guids = result.get("guids") or []
    assert _MODERN_GUID in guids, (
        f"GHKnowledgeStore.query('create a C# script') did not surface modern C#; "
        f"guids={guids!r}"
    )
