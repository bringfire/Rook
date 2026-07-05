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
