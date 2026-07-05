import ast
import hashlib
import importlib.util
import inspect
import json
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

from rook.agent import local_worker_acceptance_criteria as module
from rook.agent.local_worker_acceptance_criteria import (
    ACCEPTANCE_CRITERIA_PACKET_SCHEMA,
    AcceptanceCriteriaSource,
    AcceptanceCriteriaSources,
    UnresolvedIntentEntry,
    assemble_acceptance_criteria_packet,
)


PIN_SOURCE_PATH = "create_script.initial_execution_params.pins_out"
VERIFY_SOURCE_PATH = "workflow_contract.rules.verify_repair.expected_outcome"
DIAGNOSTIC_SOURCE_PATH = "create_script.receipt.script_receipt.repair_anchor.target_errors"
CONVENTION_SOURCE_PATH = "script_body_gotcha"
TARGET_DIAGNOSTIC = (
    "CS0103: The name 'DefinitelyMissingSymbol' does not exist in the current context."
)


def _valid_sources(**overrides):
    values = {
        "pin_contract": AcceptanceCriteriaSource(
            source_class="pin_contract",
            source_path=PIN_SOURCE_PATH,
            value={"pins_out": ["A:double"]},
        ),
        "verifier_outcome": AcceptanceCriteriaSource(
            source_class="verifier_outcome",
            source_path=VERIFY_SOURCE_PATH,
            value="succeeded",
        ),
        "receipt_diagnostic": AcceptanceCriteriaSource(
            source_class="receipt_diagnostic",
            source_path=DIAGNOSTIC_SOURCE_PATH,
            value=[TARGET_DIAGNOSTIC],
        ),
        "convention": AcceptanceCriteriaSource(
            source_class="convention",
            source_path=CONVENTION_SOURCE_PATH,
            value={"mode": "body"},
        ),
        "unresolved_intent": (),
    }
    values.update(overrides)
    return AcceptanceCriteriaSources(**values)


def _without_fingerprint(packet):
    packet = dict(packet)
    packet.pop("fingerprint")
    return packet


def _load_lm5k_probe_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "lm5k_worker_probe.py"
    spec = importlib.util.spec_from_file_location("lm5k_worker_probe_for_lm5w", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _jsonable(value):
    if isinstance(value, Mapping):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _import_names(source):
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
            imports.update(alias.name for alias in node.names)
            if node.module:
                imports.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imports


def _call_names(source):
    tree = ast.parse(source)
    calls = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            calls.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                calls.add(f"{node.func.value.id}.{node.func.attr}")
            calls.add(node.func.attr)
    return calls


def test_public_surface_exports_acceptance_criteria_packet_api():
    assert module.__all__ == (
        "ACCEPTANCE_CRITERIA_PACKET_SCHEMA",
        "AcceptanceCriteriaSource",
        "UnresolvedIntentEntry",
        "AcceptanceCriteriaSources",
        "assemble_acceptance_criteria_packet",
    )
    assert ACCEPTANCE_CRITERIA_PACKET_SCHEMA == "rook.acceptance_criteria_packet:v1"


def test_assembles_canonical_lm5w_acceptance_criteria_packet():
    packet = assemble_acceptance_criteria_packet(_valid_sources())

    assert _without_fingerprint(packet) == {
        "schema": "rook.acceptance_criteria_packet:v1",
        "source_set": {
            "source_classes": [
                "convention",
                "pin_contract",
                "receipt_diagnostic",
                "verifier_outcome",
            ],
            "source_paths": [
                PIN_SOURCE_PATH,
                DIAGNOSTIC_SOURCE_PATH,
                CONVENTION_SOURCE_PATH,
                VERIFY_SOURCE_PATH,
            ],
        },
        "criteria": [
            {
                "criterion_id": "output_a_assigned",
                "description": "Output A must be assigned.",
                "source": PIN_SOURCE_PATH,
                "source_class": "pin_contract",
            },
            {
                "criterion_id": "output_a_double_compatible",
                "description": "Output A must be double-compatible.",
                "source": PIN_SOURCE_PATH,
                "source_class": "pin_contract",
            },
            {
                "criterion_id": "verify_repair_succeeds",
                "description": "The repaired body must satisfy the verify_repair expected_outcome: succeeded.",
                "source": VERIFY_SOURCE_PATH,
                "source_class": "verifier_outcome",
            },
            {
                "criterion_id": "preserve_body_mode",
                "description": "The repair must preserve body-style code.",
                "source": CONVENTION_SOURCE_PATH,
                "source_class": "convention",
            },
            {
                "criterion_id": "resolve_target_diagnostics",
                "description": "The repair must resolve the current target diagnostics.",
                "source": DIAGNOSTIC_SOURCE_PATH,
                "source_class": "receipt_diagnostic",
            },
            {
                "criterion_id": "remove_unresolved_symbol",
                "description": "The repaired body must not leave DefinitelyMissingSymbol unresolved.",
                "source": DIAGNOSTIC_SOURCE_PATH,
                "source_class": "receipt_diagnostic",
            },
        ],
        "unresolved_intent": [],
    }
    assert [criterion["criterion_id"] for criterion in packet["criteria"]] == [
        "output_a_assigned",
        "output_a_double_compatible",
        "verify_repair_succeeds",
        "preserve_body_mode",
        "resolve_target_diagnostics",
        "remove_unresolved_symbol",
    ]
    assert packet["fingerprint"].startswith("sha256:")


def test_fixture_reproduction_anchor_matches_lm5u_legacy_projection():
    probe = _load_lm5k_probe_script()
    _scaffold, result = probe.derive_probe_graph_state()
    lm5u_packet = _jsonable(
        probe._acceptance_criteria_evidence_packet(result.final_graph).content
    )
    lm5u_packet_acceptance_criteria = lm5u_packet["fields"]["acceptance_criteria"][
        "criteria"
    ]
    sources = AcceptanceCriteriaSources(
        pin_contract=AcceptanceCriteriaSource(
            source_class="pin_contract",
            source_path=PIN_SOURCE_PATH,
            value={"pins_out": ["A:double"]},
        ),
        verifier_outcome=AcceptanceCriteriaSource(
            source_class="verifier_outcome",
            source_path=VERIFY_SOURCE_PATH,
            value="succeeded",
        ),
        receipt_diagnostic=AcceptanceCriteriaSource(
            source_class="receipt_diagnostic",
            source_path=DIAGNOSTIC_SOURCE_PATH,
            value=[probe.REPAIR_TARGET_ERROR],
        ),
        convention=AcceptanceCriteriaSource(
            source_class="convention",
            source_path=CONVENTION_SOURCE_PATH,
            value={"mode": "body"},
        ),
    )
    assembled = assemble_acceptance_criteria_packet(sources)
    legacy_projection = [
        {
            "criterion_id": criterion["criterion_id"],
            "description": criterion["description"],
            "source": criterion["source"],
        }
        for criterion in assembled["criteria"]
    ]

    assert legacy_projection == lm5u_packet_acceptance_criteria
    assert [criterion["source_class"] for criterion in assembled["criteria"]] == [
        "pin_contract",
        "pin_contract",
        "verifier_outcome",
        "convention",
        "receipt_diagnostic",
        "receipt_diagnostic",
    ]


def test_module_import_boundary_stays_narrow():
    source = inspect.getsource(module)
    imports = _import_names(source)
    forbidden_import_fragments = (
        "plan_graph",
        "RookWorkflowContract",
        "CompiledWorkflowScaffold",
        "lm5k_worker_probe",
        "lm5r_two_pass_publication_probe",
        "LiteLLM",
        "run_local_worker",
        "yaml",
    )
    forbidden_calls = {"open", "Path", "json.load"}

    for fragment in forbidden_import_fragments:
        assert not any(fragment in imported for imported in imports)
    assert forbidden_calls.isdisjoint(_call_names(source))


def test_probe_scripts_do_not_import_acceptance_criteria_boundary():
    root = Path(__file__).resolve().parents[2]
    for relative in (
        "scripts/lm5k_worker_probe.py",
        "scripts/lm5r_two_pass_publication_probe.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        imports = _import_names(source)
        assert not any(
            "local_worker_acceptance_criteria" in imported for imported in imports
        )


def test_fingerprint_matches_canonical_json_without_fingerprint():
    packet = assemble_acceptance_criteria_packet(_valid_sources())

    expected = hashlib.sha256(
        json.dumps(
            _without_fingerprint(packet), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()

    assert packet["fingerprint"] == f"sha256:{expected}"


def test_fingerprint_is_stable_for_equivalent_source_dict_order():
    baseline = assemble_acceptance_criteria_packet(_valid_sources())
    equivalent = assemble_acceptance_criteria_packet(
        _valid_sources(
            convention=AcceptanceCriteriaSource(
                source_class="convention",
                source_path=CONVENTION_SOURCE_PATH,
                value=dict([("mode", "body")]),
            )
        )
    )

    assert equivalent["fingerprint"] == baseline["fingerprint"]


def test_fingerprint_changes_when_source_path_changes():
    baseline = assemble_acceptance_criteria_packet(_valid_sources())
    changed = assemble_acceptance_criteria_packet(
        _valid_sources(
            convention=AcceptanceCriteriaSource(
                source_class="convention",
                source_path="script_body_gotcha.v2",
                value={"mode": "body"},
            )
        )
    )

    assert changed["fingerprint"] != baseline["fingerprint"]


def test_returned_packet_is_fresh_across_calls():
    first = assemble_acceptance_criteria_packet(_valid_sources())
    first["criteria"].clear()
    first["source_set"]["source_classes"].clear()
    first["source_set"]["source_paths"].clear()
    first["unresolved_intent"].append(
        {
            "intent_id": "mutated",
            "description": "mutated",
            "source_class": "planner_user_intent",
            "source_path": "planner.intent.design_goal",
            "reason": "mutated",
        }
    )

    second = assemble_acceptance_criteria_packet(_valid_sources())

    assert len(second["criteria"]) == 6
    assert second["source_set"]["source_classes"] == [
        "convention",
        "pin_contract",
        "receipt_diagnostic",
        "verifier_outcome",
    ]
    assert second["unresolved_intent"] == []


def test_unresolved_intent_entries_are_sorted_and_indexed():
    baseline = assemble_acceptance_criteria_packet(_valid_sources())

    packet = assemble_acceptance_criteria_packet(
        _valid_sources(
            unresolved_intent=(
                UnresolvedIntentEntry(
                    intent_id="z_missing_design_goal",
                    description="Design goal is missing.",
                    source_class="planner_user_intent",
                    source_path="planner.intent.design_goal",
                    reason="required by planner",
                ),
                UnresolvedIntentEntry(
                    intent_id="a_missing_output_value",
                    description="Output value is missing.",
                    source_class="planner_user_intent",
                    source_path="planner.intent.output_value",
                    reason="required by planner",
                ),
            )
        )
    )

    assert [entry["intent_id"] for entry in packet["unresolved_intent"]] == [
        "a_missing_output_value",
        "z_missing_design_goal",
    ]
    assert "planner_user_intent" in packet["source_set"]["source_classes"]
    assert "planner.intent.design_goal" in packet["source_set"]["source_paths"]
    assert packet["fingerprint"] != baseline["fingerprint"]


def test_source_paths_are_sorted_unique_for_duplicate_unresolved_intent_paths():
    packet = assemble_acceptance_criteria_packet(
        _valid_sources(
            unresolved_intent=(
                UnresolvedIntentEntry(
                    intent_id="missing_design_goal",
                    description="Design goal is missing.",
                    source_class="planner_user_intent",
                    source_path="planner.intent.shared",
                    reason="required by planner",
                ),
                UnresolvedIntentEntry(
                    intent_id="missing_output_value",
                    description="Output value is missing.",
                    source_class="planner_user_intent",
                    source_path="planner.intent.shared",
                    reason="required by planner",
                ),
            )
        )
    )

    assert packet["source_set"]["source_paths"].count("planner.intent.shared") == 1


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        (
            {
                "pin_contract": AcceptanceCriteriaSource(
                    source_class="wrong",
                    source_path=PIN_SOURCE_PATH,
                    value={"pins_out": ["A:double"]},
                )
            },
            "unknown source class|expected source class",
        ),
        (
            {
                "pin_contract": AcceptanceCriteriaSource(
                    source_class="pin_contract",
                    source_path="",
                    value={"pins_out": ["A:double"]},
                )
            },
            "source_path",
        ),
        (
            {
                "pin_contract": AcceptanceCriteriaSource(
                    source_class="pin_contract",
                    source_path=123,
                    value={"pins_out": ["A:double"]},
                )
            },
            "source_path",
        ),
        (
            {
                "pin_contract": AcceptanceCriteriaSource(
                    source_class="pin_contract",
                    source_path=PIN_SOURCE_PATH,
                    value={"pins_out": ["A:double"], "bind_params": {"A": 42.0}},
                )
            },
            "exactly the pins_out field",
        ),
        (
            {
                "pin_contract": AcceptanceCriteriaSource(
                    source_class="pin_contract",
                    source_path=PIN_SOURCE_PATH,
                    value={"pins_out": []},
                )
            },
            "exactly one output pin",
        ),
        (
            {
                "pin_contract": AcceptanceCriteriaSource(
                    source_class="pin_contract",
                    source_path=PIN_SOURCE_PATH,
                    value={"pins_out": ["A:double", "B:int"]},
                )
            },
            "exactly one output pin",
        ),
        (
            {
                "pin_contract": AcceptanceCriteriaSource(
                    source_class="pin_contract",
                    source_path=PIN_SOURCE_PATH,
                    value={"pins_out": ["A"]},
                )
            },
            "<name>:<type>",
        ),
        (
            {
                "pin_contract": AcceptanceCriteriaSource(
                    source_class="pin_contract",
                    source_path=PIN_SOURCE_PATH,
                    value={"pins_out": ["B:int"]},
                )
            },
            "A:double",
        ),
        (
            {
                "verifier_outcome": AcceptanceCriteriaSource(
                    source_class="verifier_outcome",
                    source_path=VERIFY_SOURCE_PATH,
                    value="needs_repair",
                )
            },
            "succeeded",
        ),
        (
            {
                "convention": AcceptanceCriteriaSource(
                    source_class="convention",
                    source_path=CONVENTION_SOURCE_PATH,
                    value={"mode": "script"},
                )
            },
            "body",
        ),
        (
            {
                "receipt_diagnostic": AcceptanceCriteriaSource(
                    source_class="receipt_diagnostic",
                    source_path=DIAGNOSTIC_SOURCE_PATH,
                    value=[],
                )
            },
            "non-empty",
        ),
        (
            {
                "receipt_diagnostic": AcceptanceCriteriaSource(
                    source_class="receipt_diagnostic",
                    source_path=DIAGNOSTIC_SOURCE_PATH,
                    value=["CS0000: Different diagnostic"],
                )
            },
            "DefinitelyMissingSymbol",
        ),
        (
            {
                "receipt_diagnostic": AcceptanceCriteriaSource(
                    source_class="receipt_diagnostic",
                    source_path=DIAGNOSTIC_SOURCE_PATH,
                    value=[123],
                )
            },
            "strings",
        ),
    ],
)
def test_validation_fails_closed(overrides, match):
    with pytest.raises(ValueError, match=match):
        assemble_acceptance_criteria_packet(_valid_sources(**overrides))


def test_receipt_diagnostic_extra_target_diagnostic_fails_closed():
    sources = _valid_sources(
        receipt_diagnostic=AcceptanceCriteriaSource(
            source_class="receipt_diagnostic",
            source_path=DIAGNOSTIC_SOURCE_PATH,
            value=[TARGET_DIAGNOSTIC, "CS0029: extra"],
        )
    )

    with pytest.raises(ValueError, match="exactly one target diagnostic"):
        assemble_acceptance_criteria_packet(sources)


def test_unresolved_intent_wrong_source_class_fails():
    sources = _valid_sources(
        unresolved_intent=(
            UnresolvedIntentEntry(
                intent_id="missing_design_goal",
                description="Design goal is missing.",
                source_class="wrong",
                source_path="planner.intent.design_goal",
                reason="required by planner",
            ),
        )
    )

    with pytest.raises(ValueError, match="planner_user_intent"):
        assemble_acceptance_criteria_packet(sources)


def test_unresolved_intent_empty_field_fails():
    sources = _valid_sources(
        unresolved_intent=(
            UnresolvedIntentEntry(
                intent_id="",
                description="Design goal is missing.",
                source_class="planner_user_intent",
                source_path="planner.intent.design_goal",
                reason="required by planner",
            ),
        )
    )

    with pytest.raises(ValueError, match="intent_id"):
        assemble_acceptance_criteria_packet(sources)


def test_unresolved_intent_non_string_field_fails():
    sources = _valid_sources(
        unresolved_intent=(
            UnresolvedIntentEntry(
                intent_id=123,
                description="Design goal is missing.",
                source_class="planner_user_intent",
                source_path="planner.intent.design_goal",
                reason="required by planner",
            ),
        )
    )

    with pytest.raises(ValueError, match="intent_id"):
        assemble_acceptance_criteria_packet(sources)


def test_unresolved_intent_duplicate_intent_id_fails():
    sources = _valid_sources(
        unresolved_intent=(
            UnresolvedIntentEntry(
                intent_id="missing_design_goal",
                description="Design goal is missing.",
                source_class="planner_user_intent",
                source_path="planner.intent.design_goal",
                reason="required by planner",
            ),
            UnresolvedIntentEntry(
                intent_id="missing_design_goal",
                description="Output value is missing.",
                source_class="planner_user_intent",
                source_path="planner.intent.output_value",
                reason="required by planner",
            ),
        )
    )

    with pytest.raises(ValueError, match="duplicate unresolved_intent intent_id"):
        assemble_acceptance_criteria_packet(sources)


def test_unresolved_intent_wrong_entry_type_fails():
    sources = _valid_sources(
        unresolved_intent=(
            {
                "intent_id": "missing_design_goal",
                "description": "Design goal is missing.",
                "source_class": "planner_user_intent",
                "source_path": "planner.intent.design_goal",
                "reason": "required by planner",
            },
        )
    )

    with pytest.raises(ValueError, match="UnresolvedIntentEntry"):
        assemble_acceptance_criteria_packet(sources)
