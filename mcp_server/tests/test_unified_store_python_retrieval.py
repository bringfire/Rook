"""UnifiedStore retrieval tests for Python script-component routing.

Python follow-up to PR-86 — pins the L1 knowledge-note narrowing on
the real retrieval surface (`UnifiedStore.resolve_components` reading
`knowledge/gh/notes/`). Complements the resolver-level tests in
`test_dspy_resolver_python_ranking.py`.

Pre-PR baseline: IronPython 2 Script (legacy) ranked ABOVE Python 3
Script (modern) on every generic Python intent, because the legacy
note's `trigger_intents` claimed bare `"python"`. Post-PR: IronPython 2
reachable only via explicit legacy cues (`ironpython`, `ipy`, `python2`,
etc.); generic `"python script"` surfaces Python 3 rank 1.

GhPython is intentionally out of scope — no component note today.

See rook_docs/work-queue.md + the Python-follow-up plan.
"""

from __future__ import annotations

import pytest

from rook.learning.unified_store import get_unified_store


_MODERN_PY_GUID = "719467e6-7cf5-4848-99b0-c5dd57e5442c"
_LEGACY_IRONPY_GUID = "97aa26ef-88ae-4ba6-98a6-ed6ddeca11d1"
_MODERN_CS_GUID = "b6ba1144-02d6-4a2d-b53c-ec62e290eeb7"
_LEGACY_CS_GUID = "88c3f2b5-27f7-48a2-9528-1397fad62b93"


def _guids(candidates):
    return [c.get("guid") for c in candidates]


def test_python_3_ranks_first_on_generic_python_script_intent():
    """Primary retrieval-layer assertion. Before this PR, IronPython 2
    (legacy) ranked 1st; Python 3 (modern) ranked 2nd. Post-PR, the
    narrowing removes IronPython 2 from the generic `"python"` intent
    index, flipping the ranking.
    """
    store = get_unified_store()
    candidates = store.resolve_components("python script", limit=10)
    guids = _guids(candidates)
    assert guids, "expected non-empty candidate list"
    assert guids[0] == _MODERN_PY_GUID, (
        f"Python 3 Script must rank first on 'python script'; got {guids!r}"
    )


def test_python_3_ranks_first_on_create_a_python_script_intent():
    """Same assertion on the full natural-language variant."""
    store = get_unified_store()
    candidates = store.resolve_components("create a python script", limit=10)
    guids = _guids(candidates)
    assert guids[0] == _MODERN_PY_GUID, (
        f"Python 3 Script must rank first on 'create a python script'; got {guids!r}"
    )


def test_python_3_ranks_first_on_python_3_script_intent():
    """Even the explicit `'python 3 script'` phrasing should yield
    modern first. Baseline ranked IronPython 2 above Python 3 here too.
    """
    store = get_unified_store()
    candidates = store.resolve_components("python 3 script", limit=10)
    guids = _guids(candidates)
    assert guids[0] == _MODERN_PY_GUID, (
        f"Python 3 Script must rank first on 'python 3 script'; got {guids!r}"
    )


def test_ironpython_cue_returns_only_legacy():
    """IronPython 2 note's `"ironpython"` trigger makes it retrievable.
    Modern Python 3 does not claim `"ironpython"` so it should not appear.
    """
    store = get_unified_store()
    candidates = store.resolve_components("ironpython", limit=10)
    guids = _guids(candidates)
    assert _LEGACY_IRONPY_GUID in guids
    assert _MODERN_PY_GUID not in guids, (
        f"Python 3 must not match 'ironpython'; got {guids!r}"
    )


def test_ironpython_script_cue_ranks_legacy_first():
    """Explicit `'ironpython script'` intent puts legacy first."""
    store = get_unified_store()
    candidates = store.resolve_components("ironpython script", limit=10)
    guids = _guids(candidates)
    assert guids[0] == _LEGACY_IRONPY_GUID, (
        f"IronPython 2 must rank first on 'ironpython script'; got {guids!r}"
    )


def test_ipy_cue_returns_only_legacy():
    """The `"ipy"` shorthand was added as a legacy-specific trigger."""
    store = get_unified_store()
    candidates = store.resolve_components("ipy", limit=10)
    guids = _guids(candidates)
    assert _LEGACY_IRONPY_GUID in guids
    assert _MODERN_PY_GUID not in guids


def test_python2_no_space_cue_ranks_legacy_ahead_of_modern():
    """The no-space `"python2"` spelling is a legacy-only trigger;
    Python 3 note does not claim it. `python2 script` should rank
    IronPython 2 above Python 3.
    """
    store = get_unified_store()
    candidates = store.resolve_components("python2 script", limit=10)
    guids = _guids(candidates)
    assert _LEGACY_IRONPY_GUID in guids
    if _MODERN_PY_GUID in guids:
        assert guids.index(_LEGACY_IRONPY_GUID) < guids.index(_MODERN_PY_GUID), (
            f"IronPython 2 must outrank Python 3 on 'python2 script'; got {guids!r}"
        )


def test_csharp_retrieval_unchanged_after_python_note_narrowing():
    """Regression floor: narrowing the IronPython 2 note must not
    degrade C# retrieval (PR-86 behavior). `'create a C# script'`
    must still surface both modern and legacy C# candidates.
    """
    store = get_unified_store()
    candidates = store.resolve_components("create a C# script", limit=10)
    guids = _guids(candidates)
    assert _MODERN_CS_GUID in guids, (
        f"C# retrieval regressed: modern C# missing; got {guids!r}"
    )
    assert _LEGACY_CS_GUID in guids, (
        f"C# retrieval regressed: legacy C# missing; got {guids!r}"
    )


def test_knowledge_store_query_surfaces_python_3_first_for_generic_intent():
    """End-to-end: `get_gh_knowledge_store().query(intent)` (the actual
    `gh_execute_intent` entry point) must surface Python 3 first on a
    generic Python intent — this is what drives downstream DSPy selection
    and PR-3 handoff.
    """
    from rook.learning.gh_knowledge import get_gh_knowledge_store

    ghk = get_gh_knowledge_store()
    result = ghk.query("create a python script", depth="context")
    guids = result.get("guids") or []
    assert guids and guids[0] == _MODERN_PY_GUID, (
        f"GHKnowledgeStore.query did not surface Python 3 first; guids={guids!r}"
    )
