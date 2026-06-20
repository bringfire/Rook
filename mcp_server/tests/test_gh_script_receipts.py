from __future__ import annotations

from rook.gh_script_receipts import (
    build_script_receipt,
    derive_artifact_status,
    derive_verification,
)


def _base_receipt_kwargs(**overrides):
    kwargs = {
        "operation": "update",
        "language": "csharp",
        "mutation_status": "written",
        "mutation_method": "gh_script_write",
        "component_guid": "script-guid",
        "mode_used": "body",
        "wrapped": True,
        "pins_in": [{"name": "R", "type": "double"}],
        "pins_out": [{"name": "A", "type": "double"}],
        "input_code_length": 6,
        "prepared_source_length": 900,
        "full_source_detected": False,
        "component_errors": [],
        "component_warnings": [],
        "unrelated_error_count": 0,
        "unrelated_warning_count": 0,
        "verification_method": "gh_errors",
    }
    kwargs.update(overrides)
    return kwargs


def test_derive_verification_passed_uses_measured_zero_counts():
    verification = derive_verification(
        component_errors=[],
        component_warnings=[],
        unrelated_error_count=0,
        unrelated_warning_count=0,
        method="gh_errors",
    )

    assert verification == {
        "status": "passed",
        "method": "gh_errors",
        "target_error_count": 0,
        "target_warning_count": 0,
        "unrelated_error_count": 0,
        "unrelated_warning_count": 0,
        "note": None,
    }


def test_derive_verification_failed_counts_target_errors_and_warnings():
    verification = derive_verification(
        component_errors=["The name X does not exist"],
        component_warnings=["Unused variable"],
        unrelated_error_count=2,
        unrelated_warning_count=1,
        method="gh_errors",
    )

    assert verification["status"] == "failed"
    assert verification["method"] == "gh_errors"
    assert verification["target_error_count"] == 1
    assert verification["target_warning_count"] == 1
    assert verification["unrelated_error_count"] == 2
    assert verification["unrelated_warning_count"] == 1


def test_derive_verification_preserves_unknown_unrelated_counts_for_measured_result():
    verification = derive_verification(
        component_errors=[],
        component_warnings=["Unused variable"],
        unrelated_error_count=None,
        unrelated_warning_count=None,
        method="gh_errors",
    )

    assert verification["status"] == "passed"
    assert verification["target_error_count"] == 0
    assert verification["target_warning_count"] == 1
    assert verification["unrelated_error_count"] is None
    assert verification["unrelated_warning_count"] is None


def test_derive_verification_deferred_wins_and_uses_unknown_counts():
    verification = derive_verification(
        component_errors=["stale should not matter"],
        component_warnings=["stale should not matter"],
        unrelated_error_count=3,
        unrelated_warning_count=4,
        method="gh_errors",
        deferred=True,
        note="Solver is locked.",
    )

    assert verification == {
        "status": "deferred",
        "method": "none",
        "target_error_count": None,
        "target_warning_count": None,
        "unrelated_error_count": None,
        "unrelated_warning_count": None,
        "note": "Solver is locked.",
    }


def test_derive_verification_not_requested_wins_after_deferred():
    verification = derive_verification(
        component_errors=["stale should not matter"],
        component_warnings=[],
        unrelated_error_count=1,
        unrelated_warning_count=0,
        method="gh_errors",
        not_requested=True,
        note="check_errors was false.",
    )

    assert verification["status"] == "not_requested"
    assert verification["method"] == "none"
    assert verification["target_error_count"] is None
    assert verification["target_warning_count"] is None
    assert verification["unrelated_error_count"] is None
    assert verification["unrelated_warning_count"] is None
    assert verification["note"] == "check_errors was false."


def test_derive_verification_unavailable_uses_attempted_method_and_unknown_counts():
    verification = derive_verification(
        component_errors=[],
        component_warnings=[],
        unrelated_error_count=0,
        unrelated_warning_count=0,
        method="gh_snapshot_fallback",
        unavailable_note="Component C1 not found in /gh/snapshot",
    )

    assert verification == {
        "status": "unavailable",
        "method": "gh_snapshot_fallback",
        "target_error_count": None,
        "target_warning_count": None,
        "unrelated_error_count": None,
        "unrelated_warning_count": None,
        "note": "Component C1 not found in /gh/snapshot",
    }


def test_derive_verification_empty_unavailable_note_still_marks_unavailable():
    verification = derive_verification(
        component_errors=[],
        component_warnings=[],
        unrelated_error_count=0,
        unrelated_warning_count=0,
        method="gh_snapshot_fallback",
        unavailable_note="",
    )

    assert verification["status"] == "unavailable"
    assert verification["target_error_count"] is None
    assert verification["target_warning_count"] is None
    assert verification["unrelated_error_count"] is None
    assert verification["unrelated_warning_count"] is None
    assert verification["note"] == ""


def test_derive_verification_missing_errors_marks_unavailable():
    verification = derive_verification(
        component_errors=None,
        component_warnings=[],
        unrelated_error_count=0,
        unrelated_warning_count=0,
        method="gh_errors",
    )

    assert verification == {
        "status": "unavailable",
        "method": "gh_errors",
        "target_error_count": None,
        "target_warning_count": None,
        "unrelated_error_count": None,
        "unrelated_warning_count": None,
        "note": "Target diagnostics were not provided; target compile state is unknown.",
    }


def test_derive_verification_missing_warnings_marks_unavailable():
    verification = derive_verification(
        component_errors=[],
        component_warnings=None,
        unrelated_error_count=0,
        unrelated_warning_count=0,
        method="gh_errors",
    )

    assert verification["status"] == "unavailable"
    assert verification["method"] == "gh_errors"
    assert verification["target_error_count"] is None
    assert verification["target_warning_count"] is None
    assert (
        verification["note"]
        == "Target diagnostics were not provided; target compile state is unknown."
    )


def test_derive_artifact_status_mapping_and_warning_policy():
    assert derive_artifact_status("create", "passed") == "usable"
    assert derive_artifact_status("update", "passed") == "usable"
    assert derive_artifact_status("create", "failed") == "created_with_errors"
    assert derive_artifact_status("update", "failed") == "written_with_errors"
    assert derive_artifact_status("create", "deferred") == "verification_pending"
    assert derive_artifact_status("update", "not_requested") == "verification_pending"
    assert derive_artifact_status("create", "unavailable") == "unknown"


def test_build_script_receipt_contains_version_mutation_verification_and_repair_anchor():
    receipt = build_script_receipt(
        **_base_receipt_kwargs(
            component_errors=["Cannot convert Box to Brep"],
            component_warnings=["Possible null"],
            recovery_hint="Call gh_set_script_pins first.",
            requested_guid="C1",
        )
    )

    assert receipt["version"] == 1
    assert receipt["operation"] == "update"
    assert receipt["language"] == "csharp"
    assert receipt["mutation"] == {
        "status": "written",
        "method": "gh_script_write",
        "component_guid": "script-guid",
        "note": None,
    }
    assert receipt["verification"]["status"] == "failed"
    assert receipt["artifact_status"] == "written_with_errors"
    assert receipt["repair_anchor"] == {
        "component_guid": "script-guid",
        "requested_guid": "C1",
        "language": "csharp",
        "mode_used": "body",
        "wrapped": True,
        "pins_in": [{"name": "R", "type": "double"}],
        "pins_out": [{"name": "A", "type": "double"}],
        "source_shape": {
            "input_code_length": 6,
            "prepared_source_length": 900,
            "full_source_detected": False,
        },
        "target_errors": ["Cannot convert Box to Brep"],
        "target_warnings": ["Possible null"],
        "recovery_hint": "Call gh_set_script_pins first.",
    }


def test_build_script_receipt_warning_only_verification_is_usable():
    receipt = build_script_receipt(
        **_base_receipt_kwargs(
            operation="create",
            mutation_status="created",
            mutation_method="gh_create_component_then_script",
            component_warnings=["Unused variable"],
        )
    )

    assert receipt["verification"]["status"] == "passed"
    assert receipt["verification"]["target_error_count"] == 0
    assert receipt["verification"]["target_warning_count"] == 1
    assert receipt["artifact_status"] == "usable"


def test_build_script_receipt_omits_requested_guid_when_not_useful():
    receipt = build_script_receipt(
        **_base_receipt_kwargs(
            requested_guid="script-guid",
        )
    )

    assert "requested_guid" not in receipt["repair_anchor"]


def test_build_script_receipt_includes_requested_guid_when_caller_used_short_id():
    receipt = build_script_receipt(
        **_base_receipt_kwargs(
            requested_guid="C1",
            component_guid="C1",
            include_requested_guid=True,
        )
    )

    assert receipt["repair_anchor"]["requested_guid"] == "C1"


def test_build_script_receipt_uses_none_diagnostics_when_verification_unknown():
    receipt = build_script_receipt(
        **_base_receipt_kwargs(
            deferred=True,
            verification_note="Solver locked.",
        )
    )

    assert receipt["verification"]["status"] == "deferred"
    assert receipt["verification"]["target_error_count"] is None
    assert receipt["repair_anchor"]["target_errors"] is None
    assert receipt["repair_anchor"]["target_warnings"] is None
    assert receipt["artifact_status"] == "verification_pending"


def test_build_script_receipt_uses_none_diagnostics_when_verification_unavailable():
    receipt = build_script_receipt(
        **_base_receipt_kwargs(
            component_errors=["stale should not matter"],
            component_warnings=["stale should not matter"],
            unavailable_note="",
        )
    )

    assert receipt["verification"]["status"] == "unavailable"
    assert receipt["repair_anchor"]["target_errors"] is None
    assert receipt["repair_anchor"]["target_warnings"] is None
    assert receipt["artifact_status"] == "unknown"


def test_build_script_receipt_uses_none_diagnostics_when_target_diagnostics_missing():
    receipt = build_script_receipt(
        **_base_receipt_kwargs(
            component_errors=None,
            component_warnings=[],
        )
    )

    assert receipt["verification"]["status"] == "unavailable"
    assert receipt["verification"]["target_error_count"] is None
    assert receipt["verification"]["target_warning_count"] is None
    assert (
        receipt["verification"]["note"]
        == "Target diagnostics were not provided; target compile state is unknown."
    )
    assert receipt["repair_anchor"]["target_errors"] is None
    assert receipt["repair_anchor"]["target_warnings"] is None
    assert receipt["artifact_status"] == "unknown"


def test_build_script_receipt_uses_none_diagnostics_when_verification_not_requested():
    receipt = build_script_receipt(
        **_base_receipt_kwargs(
            component_errors=["stale should not matter"],
            component_warnings=["stale should not matter"],
            not_requested=True,
            verification_note="check_errors was false.",
        )
    )

    assert receipt["verification"]["status"] == "not_requested"
    assert receipt["repair_anchor"]["target_errors"] is None
    assert receipt["repair_anchor"]["target_warnings"] is None
    assert receipt["artifact_status"] == "verification_pending"


def test_build_script_receipt_preserves_non_dict_pin_entries():
    pins_in = [{"name": "R", "metadata": {"nicknames": ["radius"]}}, "legacy-pin"]

    receipt = build_script_receipt(
        **_base_receipt_kwargs(
            pins_in=pins_in,
            pins_out=None,
        )
    )

    assert receipt["repair_anchor"]["pins_in"] == [
        {"name": "R", "metadata": {"nicknames": ["radius"]}},
        "legacy-pin",
    ]
    assert receipt["repair_anchor"]["pins_out"] == []


def test_build_script_receipt_deep_copies_pins_and_diagnostics():
    pins_in = [{"name": "R", "metadata": {"nicknames": ["radius"]}}]
    pins_out = [{"name": "A", "metadata": {"nicknames": ["area"]}}]
    errors = [{"message": "Cannot convert", "details": ["Box", "Brep"]}]
    warnings = [{"message": "Unused", "details": ["x"]}]

    receipt = build_script_receipt(
        **_base_receipt_kwargs(
            pins_in=pins_in,
            pins_out=pins_out,
            component_errors=errors,
            component_warnings=warnings,
        )
    )

    pins_in[0]["metadata"]["nicknames"].append("mutated")
    pins_out[0]["metadata"]["nicknames"].append("mutated")
    errors[0]["details"].append("mutated")
    warnings[0]["details"].append("mutated")

    assert receipt["repair_anchor"]["pins_in"] == [
        {"name": "R", "metadata": {"nicknames": ["radius"]}}
    ]
    assert receipt["repair_anchor"]["pins_out"] == [
        {"name": "A", "metadata": {"nicknames": ["area"]}}
    ]
    assert receipt["repair_anchor"]["target_errors"] == [
        {"message": "Cannot convert", "details": ["Box", "Brep"]}
    ]
    assert receipt["repair_anchor"]["target_warnings"] == [
        {"message": "Unused", "details": ["x"]}
    ]
