"""Resolver ranking tests for the C# modern-vs-legacy preference fix.

Covers the two resolver-side changes:
1. `_component_concept_key` unifies modern RhinoCode C# Script and
   GH1-legacy DotNET C# Script under `csharp_script`.
2. `_select_preferred_candidate_for_concept` prefers modern by default,
   legacy only on explicit legacy cues.

Python family preference was intentionally deferred at PR-86 time. The
Python follow-up (separate PR) covers `python_script` unification and
modern-over-legacy preference. This file's `test_preference_non_csharp_concept_is_not_rewritten`
still exercises a Python candidate against a non-csharp concept as a
regression floor — Python-specific unification tests live in
test_dspy_resolver_python_ranking.py.

See rook_docs/work-queue.md "Prefer modern RhinoCode C# Script over legacy
ComponentLegacyCsScript for C# GH intents" (PR-86) and the Python
follow-up that extended the same three-layer pattern for Python variants.
"""

from __future__ import annotations

import pytest

from rook.learning.dspy_modules import GHIntentResolver


# Canonical candidate dicts (shape matches what UnifiedStore.resolve_components returns).
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
_MODERN_PY = {
    "guid": "719467e6-7cf5-4848-99b0-c5dd57e5442c",
    "name": "Python 3 Script",
    "family": "scripting",
}
# Note: Python family unification + preference is covered in
# test_dspy_resolver_python_ranking.py (Python follow-up PR). This file
# only references _MODERN_PY as a regression floor for the
# non-csharp-concept branch of _select_preferred_candidate_for_concept.
_VB = {
    "guid": "079bd9bd-54a0-41d4-98af-db999015f63d",
    "name": "VB Script",
    "family": "scripting",
}
_SPHERE = {"guid": "dabc854d-f50e-408a-b001-d043c7de151d", "name": "Sphere"}
_SLIDER = {"guid": "57da07bd-ecab-415d-9d86-af36d7073abc", "name": "Number Slider"}


# ---------- _component_concept_key — C# unification + regression floors ----------


def test_concept_key_modern_csharp_is_csharp_script():
    assert GHIntentResolver._component_concept_key(_MODERN_CS) == "csharp_script"


def test_concept_key_legacy_csharp_is_csharp_script():
    assert GHIntentResolver._component_concept_key(_LEGACY_CS) == "csharp_script"


def test_concept_key_vb_script_is_not_csharp_script():
    """Regression guardrail — VB Script has 'script' in tokens but is
    not C#. The csharp detector must exclude it.
    """
    assert GHIntentResolver._component_concept_key(_VB) != "csharp_script"


def test_concept_key_non_script_components_unchanged():
    """Sliders, toggles, and non-script components must keep their
    original concept keys. The new branch is gated on `"script" in tokens`
    so non-script candidates never enter the csharp-detection code path.
    """
    assert GHIntentResolver._component_concept_key(_SPHERE) == "sphere"
    assert GHIntentResolver._component_concept_key(_SLIDER) == "slider"


# ---------- _select_preferred_candidate_for_concept — modern-over-legacy ----------


def test_preference_generic_intent_prefers_modern():
    """On a generic C# intent with no legacy cue, modern must win."""
    picked = GHIntentResolver._select_preferred_candidate_for_concept(
        "csharp_script", [_MODERN_CS, _LEGACY_CS], "create a C# script"
    )
    assert picked is not None
    assert picked["guid"] == _MODERN_CS["guid"]


def test_preference_legacy_cue_prefers_legacy():
    """Explicit 'legacy' cue in the intent routes to legacy."""
    picked = GHIntentResolver._select_preferred_candidate_for_concept(
        "csharp_script", [_MODERN_CS, _LEGACY_CS], "create a C# legacy script"
    )
    assert picked is not None
    assert picked["guid"] == _LEGACY_CS["guid"]


def test_preference_dotnet_cue_prefers_legacy():
    """'.NET' / 'dotnet' cue in the intent routes to legacy."""
    picked = GHIntentResolver._select_preferred_candidate_for_concept(
        "csharp_script", [_MODERN_CS, _LEGACY_CS], "create a .NET script component"
    )
    assert picked is not None
    assert picked["guid"] == _LEGACY_CS["guid"]


def test_preference_falls_back_gracefully_when_only_legacy_in_pool():
    """If modern isn't in the candidate pool at all (e.g. retrieval
    didn't surface it), the generic sort path must return legacy
    without error. The csharp_script branch filters to `modern` when
    no legacy cue is present — if modern is empty, fallthrough should
    still yield the remaining pool.
    """
    picked = GHIntentResolver._select_preferred_candidate_for_concept(
        "csharp_script", [_LEGACY_CS], "create a C# script"
    )
    assert picked is not None
    assert picked["guid"] == _LEGACY_CS["guid"]


def test_preference_non_csharp_concept_is_not_rewritten():
    """The csharp_script branch must only run for that exact concept
    key. For other concepts (e.g. the raw "python" first-token key),
    the existing sort_key logic runs unchanged.
    """
    picked = GHIntentResolver._select_preferred_candidate_for_concept(
        "python", [_MODERN_PY], "create a python script"
    )
    assert picked is not None
    assert picked["guid"] == _MODERN_PY["guid"]
