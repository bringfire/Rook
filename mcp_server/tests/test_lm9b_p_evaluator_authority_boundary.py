"""LM9B-P evaluator authority boundary — semantic verdicts vs deterministic advancement.

Governing invariant: models propose and judge meaning; deterministic authority
decides whether the system may advance. These tests pin the two closures:

1. Report serialization visibility: the rendered evaluator request embeds the
   EXACT report schema the parser validates with (single source of truth), plus
   the recommendation meanings.
2. Authority boundary: the evaluator emits semantic-only verdicts
   (semantically_faithful | semantically_unfaithful | evaluation_inconclusive);
   the controller deterministically derives blocked/ready from the mechanically
   accepted artifact's explicit unresolved_intent, bound to the recomputed
   MechanicalGateResult with a byte-equality integrity check. No semantic
   recommendation can override explicit recipe state, and a blocked
   classification shows no handoff, no compiler provider call, no compiler
   attempt evidence, checkpoint 2 = not_evaluated."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "scripts" / "lm9b_p_fixtures"
READY_RECIPE = ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json"
BLOCKED_RECIPE = ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_blocked_recipe.json"


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SUPPORT = _load_script("lm9b_p_planner_recipe_transfer_support")
ARTIFACTS = _load_script("lm9b_p_planner_recipe_transfer_artifacts")
PROBE = _load_script("lm9b_p_planner_recipe_transfer_probe")


def _authority():
    return ARTIFACTS.load_planner_authority_context(FIXTURES)


def _gate(recipe_bytes: bytes):
    authority = _authority()
    return SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=recipe_bytes,
        authority=authority,
        recipe_schema=authority.recipe_schema,
        normalization_profile=authority.normalization_profile,
        exclusion_policy=authority.exclusion_policy,
    )


def _accepted_session(recipe_bytes: bytes):
    """Return (session, checkpoint_gate) with the proof carrier attached.

    ``checkpoint_gate`` models the checkpoint's independent reevaluation of the
    final bytes under the frozen inputs; the gate is deterministic, so it
    equals the accepted turn's retained gate result in the honest path."""

    gate_result = _gate(recipe_bytes)
    assert gate_result.status == "mechanically_accepted", gate_result.diagnostics
    turn = SimpleNamespace(gate_result=gate_result)
    session = SimpleNamespace(
        termination="mechanically_accepted",
        final_recipe_bytes=gate_result.final_recipe_bytes,
        turns=(turn,),
    )
    return session, gate_result


def _evaluator(recommendation: str):
    return SimpleNamespace(
        termination="valid_recommendation", recommendation=recommendation
    )


# ==================== Closure 1: rendered report contract ====================

def test_rendered_evaluator_request_embeds_exact_report_schema() -> None:
    inputs = ARTIFACTS.load_planner_inputs(FIXTURES)
    gate_result = _gate(READY_RECIPE.read_bytes())
    rendered = ARTIFACTS.render_planner_evaluator_request(
        inputs, gate_result=gate_result
    )
    payload = json.loads(rendered.raw_bytes)
    contract = payload["evaluation_report_contract"]
    # Deep equality with the parser's single source of truth (via JSON round-trip
    # so frozen/builtin representations compare equal).
    assert contract["report_schema"] == json.loads(
        json.dumps(SUPPORT.PLANNER_EVALUATION_REPORT_SCHEMA)
    )
    assert contract["recommendation_meanings"] == json.loads(
        json.dumps(SUPPORT.PLANNER_EVALUATION_RECOMMENDATION_MEANINGS)
    )


def test_parser_validates_with_the_same_schema_object() -> None:
    # The validator must be constructed from the exact exported schema object.
    assert SUPPORT.PLANNER_EVALUATION_REPORT_SCHEMA["properties"]["recommendation"][
        "enum"
    ] == list(SUPPORT.PLANNER_EVALUATION_RECOMMENDATIONS)


def test_recommendation_meanings_state_the_authority_limit() -> None:
    meanings = SUPPORT.PLANNER_EVALUATION_RECOMMENDATION_MEANINGS
    assert set(meanings) == {
        "semantically_faithful",
        "semantically_unfaithful",
        "evaluation_inconclusive",
    }
    # Readiness is not the evaluator's decision; the meanings must say so.
    joined = " ".join(meanings.values()).lower()
    assert "readiness" in joined or "blocked" in joined


# ==================== Closure 2a: semantic-only enum ====================

def _report_turn(report: dict) -> object:
    arguments = json.dumps({"evaluation_json": json.dumps(report)})
    return SUPPORT.ProviderTurn(
        b"{}",
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "eval-1",
                    "function": {
                        "name": "submit_planner_evaluation",
                        "arguments": arguments,
                    },
                }
            ],
        },
        {},
        {"model_identity": "evaluator", "profile_identity": "profile"},
        b"{}",
    )


@pytest.mark.parametrize(
    "recommendation",
    ["semantically_faithful", "semantically_unfaithful", "evaluation_inconclusive"],
)
def test_parser_accepts_semantic_only_recommendations(recommendation: str) -> None:
    turn = _report_turn(
        {
            "recommendation": recommendation,
            "evidence": [{"criterion_id": "brief_fidelity", "finding": "assessed"}],
        }
    )
    result = SUPPORT._planner_evaluation_from_message(turn)
    assert result.termination == "valid_recommendation"
    assert result.recommendation == recommendation


@pytest.mark.parametrize(
    "legacy", ["faithful_ready", "faithful_blocked", "planner_failure", "ready", ""]
)
def test_parser_rejects_legacy_and_unknown_recommendations(legacy: str) -> None:
    turn = _report_turn(
        {
            "recommendation": legacy,
            "evidence": [{"criterion_id": "brief_fidelity", "finding": "assessed"}],
        }
    )
    result = SUPPORT._planner_evaluation_from_message(turn)
    assert result.termination == "malformed"
    assert result.recommendation is None


# ==================== Closure 2b: explicit blocker projection ====================

def test_blockers_present_for_nonempty_unresolved_intent() -> None:
    blockers = ARTIFACTS.derive_probe_explicit_blockers(BLOCKED_RECIPE.read_bytes())
    assert blockers == ("unresolved_intent_present",)


def test_no_blockers_for_empty_unresolved_intent() -> None:
    assert ARTIFACTS.derive_probe_explicit_blockers(READY_RECIPE.read_bytes()) == ()


def test_blocker_vocabulary_is_closed() -> None:
    # The projection can only ever emit the single explicit blocker this probe
    # is authorized to establish.
    for path in (READY_RECIPE, BLOCKED_RECIPE):
        for blocker in ARTIFACTS.derive_probe_explicit_blockers(path.read_bytes()):
            assert blocker == "unresolved_intent_present"


def test_blockers_require_explicit_unresolved_intent_collection() -> None:
    recipe = json.loads(READY_RECIPE.read_bytes())
    del recipe["unresolved_intent"]
    with pytest.raises(ValueError):
        ARTIFACTS.derive_probe_explicit_blockers(
            json.dumps(recipe).encode("utf-8")
        )


# ==================== Closure 2c: controller equations ====================
# The controller consumes checkpoint_gate - the checkpoint's INDEPENDENT
# reevaluation under the frozen inputs - as the proof carrier for advancement.

def test_faithful_with_blockers_classifies_blocked() -> None:
    session, gate = _accepted_session(BLOCKED_RECIPE.read_bytes())
    assert (
        ARTIFACTS.derive_checkpoint_classification(
            session, _evaluator("semantically_faithful"), checkpoint_gate=gate
        )
        == "probe_candidate_blocked"
    )


def test_faithful_without_blockers_classifies_ready() -> None:
    session, gate = _accepted_session(READY_RECIPE.read_bytes())
    assert (
        ARTIFACTS.derive_checkpoint_classification(
            session, _evaluator("semantically_faithful"), checkpoint_gate=gate
        )
        == "probe_candidate_ready"
    )


def test_unfaithful_classifies_planner_failure_regardless_of_blockers() -> None:
    for path in (READY_RECIPE, BLOCKED_RECIPE):
        session, gate = _accepted_session(path.read_bytes())
        assert (
            ARTIFACTS.derive_checkpoint_classification(
                session, _evaluator("semantically_unfaithful"), checkpoint_gate=gate
            )
            == "probe_planner_failure"
        )


def test_inconclusive_verdict_classifies_inconclusive() -> None:
    session, gate = _accepted_session(READY_RECIPE.read_bytes())
    assert (
        ARTIFACTS.derive_checkpoint_classification(
            session, _evaluator("evaluation_inconclusive"), checkpoint_gate=gate
        )
        == "probe_inconclusive"
    )


def test_malformed_or_absent_evaluator_stays_inconclusive() -> None:
    session, gate = _accepted_session(READY_RECIPE.read_bytes())
    assert (
        ARTIFACTS.derive_checkpoint_classification(
            session, None, checkpoint_gate=gate
        )
        == "probe_inconclusive"
    )
    malformed = SimpleNamespace(termination="malformed", recommendation=None)
    assert (
        ARTIFACTS.derive_checkpoint_classification(
            session, malformed, checkpoint_gate=gate
        )
        == "probe_inconclusive"
    )


def test_mechanical_rejection_is_unchanged() -> None:
    session = SimpleNamespace(
        termination="mechanically_rejected", final_recipe_bytes=None, turns=()
    )
    assert (
        ARTIFACTS.derive_checkpoint_classification(session, None)
        == "probe_mechanically_rejected"
    )


def test_legacy_recommendation_cannot_reach_the_controller_map() -> None:
    session, gate = _accepted_session(READY_RECIPE.read_bytes())
    with pytest.raises(ValueError):
        ARTIFACTS.derive_checkpoint_classification(
            session, _evaluator("faithful_ready"), checkpoint_gate=gate
        )


def test_missing_checkpoint_gate_is_integrity_failure() -> None:
    # Classifying an accepted session WITHOUT the independent checkpoint
    # reevaluation must refuse - sealing may never bypass the proof carrier.
    session, _gate_result = _accepted_session(READY_RECIPE.read_bytes())
    with pytest.raises(ValueError):
        ARTIFACTS.derive_checkpoint_classification(
            session, _evaluator("semantically_faithful")
        )


def test_non_accepted_checkpoint_gate_is_integrity_failure() -> None:
    session, _gate_result = _accepted_session(READY_RECIPE.read_bytes())
    rejected_gate = _gate(b'{"not": "a recipe"}')
    assert rejected_gate.status != "mechanically_accepted"
    with pytest.raises(ValueError):
        ARTIFACTS.derive_checkpoint_classification(
            session, _evaluator("semantically_faithful"), checkpoint_gate=rejected_gate
        )


def test_gate_session_byte_mismatch_is_integrity_failure_not_classification() -> None:
    session, gate = _accepted_session(BLOCKED_RECIPE.read_bytes())
    tampered = SimpleNamespace(
        termination="mechanically_accepted",
        final_recipe_bytes=READY_RECIPE.read_bytes(),  # differs from gate bytes
        turns=session.turns,
    )
    with pytest.raises(ValueError):
        ARTIFACTS.derive_checkpoint_classification(
            tampered, _evaluator("semantically_faithful"), checkpoint_gate=gate
        )


def test_checkpoint_gate_must_equal_accepted_turn_gate_result() -> None:
    # The independent reevaluation must agree exactly with the session's
    # accepted turn result; a divergent (e.g. differently fingerprinted)
    # checkpoint gate is a control failure.
    import dataclasses

    session, gate = _accepted_session(READY_RECIPE.read_bytes())
    divergent = dataclasses.replace(
        gate, ratified_recipe_fingerprint="sha256:" + "0" * 64
    )
    with pytest.raises(ValueError):
        ARTIFACTS.derive_checkpoint_classification(
            session, _evaluator("semantically_faithful"), checkpoint_gate=divergent
        )


def test_accepted_session_without_retained_gate_result_is_integrity_failure() -> None:
    _session, gate = _accepted_session(READY_RECIPE.read_bytes())
    session = SimpleNamespace(
        termination="mechanically_accepted",
        final_recipe_bytes=gate.final_recipe_bytes,
        turns=(),
    )
    with pytest.raises(ValueError):
        ARTIFACTS.derive_checkpoint_classification(
            session, _evaluator("semantically_faithful"), checkpoint_gate=gate
        )


# ==================== Override impossibility through the real session path ====================

def _planner_turn_bytes(recipe_bytes: bytes) -> object:
    arguments = json.dumps(
        {"recipe_json": recipe_bytes.decode("utf-8")}, ensure_ascii=False
    )
    return SUPPORT.ProviderTurn(
        b"{}",
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "planner-1",
                    "function": {
                        "name": "submit_planner_recipe",
                        "arguments": arguments,
                    },
                }
            ],
        },
        {},
        {"model_identity": "planner", "profile_identity": "profile"},
        b"{}",
    )


class _Provider:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests: list = []

    def __call__(self, request):
        self.requests.append(request)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _sealable_blocked_bytes() -> bytes:
    # The blocked fixture must round-trip the fingerprint the session expects.
    return BLOCKED_RECIPE.read_bytes()


# Compiler isolation for non-ready classifications (no handoff, no compiler
# provider call, no compiler attempt evidence) is proven through the joined
# path by test_every_non_ready_checkpoint_skips_handoff_and_compiler in
# test_lm9b_p_planner_recipe_transfer_probe.py, which exercises
# run_joined_probe. The checkpoint-only tests below assert classification and
# checkpoint_2 state; they deliberately make no handoff claims.


def test_faithful_verdict_cannot_override_unresolved_intent() -> None:
    planner = _Provider([_planner_turn_bytes(_sealable_blocked_bytes())])
    evaluator = _Provider(
        [
            _report_turn(
                {
                    "recommendation": "semantically_faithful",
                    "evidence": [
                        {"criterion_id": "brief_fidelity", "finding": "faithful"}
                    ],
                }
            )
        ]
    )
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=planner,
        evaluator_provider=evaluator,
    )
    assert result.classification == "probe_candidate_blocked"
    assert result.checkpoint_2 == "not_evaluated"


def test_legacy_ready_emission_never_classifies_ready() -> None:
    planner = _Provider([_planner_turn_bytes(_sealable_blocked_bytes())])
    evaluator = _Provider(
        [
            _report_turn(
                {
                    "recommendation": "faithful_ready",
                    "evidence": [
                        {"criterion_id": "brief_fidelity", "finding": "faithful"}
                    ],
                }
            )
        ]
    )
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=planner,
        evaluator_provider=evaluator,
    )
    assert result.classification == "probe_inconclusive"
    assert result.evaluator.termination == "malformed"
    assert result.checkpoint_2 == "not_evaluated"


# ==================== rubric fixture carries the semantic vocabulary ====================

def test_rubric_fixture_recommendations_are_semantic_only() -> None:
    rubric = json.loads(
        (FIXTURES / "planner_evaluation_rubric.json").read_text(encoding="utf-8")
    )
    assert rubric["recommendations"] == [
        "evaluation_inconclusive",
        "semantically_faithful",
        "semantically_unfaithful",
    ]
    assert rubric["rubric_fingerprint"] == SUPPORT.fingerprint_without(
        rubric, "rubric_fingerprint"
    )
