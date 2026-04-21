"""Resolver ranking tests for the Python modern-vs-legacy preference fix.

Python follow-up to the C# campaign (PR-86). Covers:
1. `_component_concept_key` unifies modern RhinoCode "Python 3 Script"
   and GH1-legacy "IronPython 2 Script" under `python_script`.
2. `_select_preferred_candidate_for_concept` prefers modern by default,
   legacy only on explicit legacy cues (`ironpython`, `ipy`, `python2`,
   `legacy`, `gh1`, word-bounded ` python 2 ` / ` py2 ` / ` iron python `).

GhPython is intentionally OUT OF SCOPE. It has no component note today
(only a recipe reference at `recipe_41f76822.json`), so it never enters
the candidate pool. If a GhPython component note is added later, revisit
both L2 detection and L3 preference.

This file intentionally REPLACES `test_concept_key_python_variants_unchanged`
from `test_dspy_resolver_csharp_ranking.py` — that test was a PR-86
guardrail pinning Python behavior as untouched; it was deleted here
because Python behavior is now the explicit target.

See rook_docs/work-queue.md + the Python-follow-up plan.
"""

from __future__ import annotations

import pytest

from rook.learning.dspy_modules import GHIntentResolver


_MODERN_PY = {
    "guid": "719467e6-7cf5-4848-99b0-c5dd57e5442c",
    "name": "Python 3 Script",
    "family": "scripting",
}
_LEGACY_IRONPY = {
    "guid": "97aa26ef-88ae-4ba6-98a6-ed6ddeca11d1",
    "name": "IronPython 2 Script",
    "family": "scripting",
}
_MODERN_CS = {
    "guid": "b6ba1144-02d6-4a2d-b53c-ec62e290eeb7",
    "name": "C# Script",
    "family": "scripting",
}
_LEGACY_CS = {
    "guid": "88c3f2b5-27f7-48a2-9528-1397fad62b93",
    "name": "DotNET C# Script (LEGACY)",
    "family": "scripting",
}
_VB = {
    "guid": "079bd9bd-54a0-41d4-98af-db999015f63d",
    "name": "VB Script",
    "family": "scripting",
}
_SPHERE = {"guid": "dabc854d-f50e-408a-b001-d043c7de151d", "name": "Sphere"}


# ---------- _component_concept_key — Python unification + scope guards ----------


def test_concept_key_modern_python_is_python_script():
    assert GHIntentResolver._component_concept_key(_MODERN_PY) == "python_script"


def test_concept_key_ironpython_is_python_script():
    assert GHIntentResolver._component_concept_key(_LEGACY_IRONPY) == "python_script"


def test_concept_key_vb_script_is_not_python_script():
    """Regression guardrail — VB Script has 'script' in tokens but is
    not Python. The python detector must exclude it.
    """
    assert GHIntentResolver._component_concept_key(_VB) != "python_script"


def test_concept_key_csharp_variants_not_misclassified_as_python():
    """Cross-family regression — both C# variants must stay in
    `csharp_script`, not get pulled into `python_script`.
    """
    assert GHIntentResolver._component_concept_key(_MODERN_CS) == "csharp_script"
    assert GHIntentResolver._component_concept_key(_LEGACY_CS) == "csharp_script"


def test_concept_key_non_script_components_unchanged():
    """Sphere and other non-script candidates keep their original
    first-token keys. The python branch is gated on `"script" in tokens`
    so non-script candidates never enter the python detection path.
    """
    assert GHIntentResolver._component_concept_key(_SPHERE) == "sphere"


# ---------- _select_preferred_candidate_for_concept — modern-over-legacy ----------


def test_python_preference_generic_intent_prefers_modern():
    """On a generic Python intent with no legacy cue, modern wins."""
    picked = GHIntentResolver._select_preferred_candidate_for_concept(
        "python_script",
        [_MODERN_PY, _LEGACY_IRONPY],
        "create a python script",
    )
    assert picked is not None
    assert picked["guid"] == _MODERN_PY["guid"]


def test_python_preference_ironpython_cue_prefers_legacy():
    """Explicit `ironpython` cue routes to IronPython 2."""
    picked = GHIntentResolver._select_preferred_candidate_for_concept(
        "python_script",
        [_MODERN_PY, _LEGACY_IRONPY],
        "create an ironpython script",
    )
    assert picked is not None
    assert picked["guid"] == _LEGACY_IRONPY["guid"]


def test_python_preference_ipy_cue_prefers_legacy():
    """`ipy` shorthand also cues legacy."""
    picked = GHIntentResolver._select_preferred_candidate_for_concept(
        "python_script",
        [_MODERN_PY, _LEGACY_IRONPY],
        "make an ipy script",
    )
    assert picked is not None
    assert picked["guid"] == _LEGACY_IRONPY["guid"]


def test_python_preference_python2_no_space_cue_prefers_legacy():
    """No-space `python2` spelling routes to legacy."""
    picked = GHIntentResolver._select_preferred_candidate_for_concept(
        "python_script",
        [_MODERN_PY, _LEGACY_IRONPY],
        "create a python2 script",
    )
    assert picked is not None
    assert picked["guid"] == _LEGACY_IRONPY["guid"]


def test_python_preference_python_2_with_space_cue_prefers_legacy():
    """Word-bounded ` python 2 ` cue routes to legacy (spaced spelling)."""
    picked = GHIntentResolver._select_preferred_candidate_for_concept(
        "python_script",
        [_MODERN_PY, _LEGACY_IRONPY],
        "create a python 2 script",
    )
    assert picked is not None
    assert picked["guid"] == _LEGACY_IRONPY["guid"]


def test_python_preference_iron_python_spaced_cue_prefers_legacy():
    """Word-bounded ` iron python ` cue (two-word spelling) routes to legacy."""
    picked = GHIntentResolver._select_preferred_candidate_for_concept(
        "python_script",
        [_MODERN_PY, _LEGACY_IRONPY],
        "create an iron python script",
    )
    assert picked is not None
    assert picked["guid"] == _LEGACY_IRONPY["guid"]


def test_python_preference_legacy_cue_prefers_legacy():
    """Generic `legacy` cue routes to IronPython 2."""
    picked = GHIntentResolver._select_preferred_candidate_for_concept(
        "python_script",
        [_MODERN_PY, _LEGACY_IRONPY],
        "create a legacy python script",
    )
    assert picked is not None
    assert picked["guid"] == _LEGACY_IRONPY["guid"]


def test_python_preference_falls_back_when_only_legacy_in_pool():
    """If modern isn't present (hypothetical knowledge-store gap), the
    generic sort returns legacy without raising.
    """
    picked = GHIntentResolver._select_preferred_candidate_for_concept(
        "python_script",
        [_LEGACY_IRONPY],
        "create a python script",
    )
    assert picked is not None
    assert picked["guid"] == _LEGACY_IRONPY["guid"]


def test_python_preference_non_python_concept_unchanged():
    """Regression floor: passing a non-`python_script` concept must not
    route through the Python preference branch. The existing sort_key
    path handles the candidate pool as-is.
    """
    picked = GHIntentResolver._select_preferred_candidate_for_concept(
        "sphere", [_SPHERE], "create a sphere"
    )
    assert picked is not None
    assert picked["guid"] == _SPHERE["guid"]


def test_python_py2_wordbounded_cue_prefers_legacy():
    """Word-bounded ` py2 ` cue routes to legacy. Completes coverage of
    the three word-bounded cues (` python 2 ` / ` py2 ` / ` iron python `).
    """
    picked = GHIntentResolver._select_preferred_candidate_for_concept(
        "python_script",
        [_MODERN_PY, _LEGACY_IRONPY],
        "create a py2 script",
    )
    assert picked is not None
    assert picked["guid"] == _LEGACY_IRONPY["guid"]
