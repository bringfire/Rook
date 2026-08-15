import copy

import pytest

from rook.gh_edit_contract import admit_gh_edit_request, apply_gh_edit_contract


@pytest.mark.parametrize("temp_id", ["T1", "TActorSetControl", "T_CLEAN"])
def test_descriptive_temp_ids_are_admitted_without_mutating_request(temp_id):
    request = {
        "epoch": 3,
        "create": [{"temp_id": temp_id, "type": "slider"}],
        "disconnect": ["C1.o00>C2.i01"],
        "set_values": [{"id": temp_id, "value": 2}],
        "connect": [f"{temp_id}.O0>C1.I0"],
        "groups": [{"action": "create", "members": [temp_id, "C1"]}],
    }
    original = copy.deepcopy(request)

    assert admit_gh_edit_request(request) is None
    assert request == original


@pytest.mark.parametrize(
    "temp_id",
    [None, 1, "T", "t1", "N1", "T-hyphen", "T1\n", "T" + ("A" * 64)],
)
def test_invalid_declared_temp_ids_refuse_with_exact_value(temp_id):
    request = {
        "epoch": 3,
        "create": [{"temp_id": temp_id, "type": "slider"}],
    }

    result = admit_gh_edit_request(request)

    assert result == {
        "success": False,
        "data": {
            "error": "gh_edit_admission_failed",
            "issues": [
                {
                    "path": "/create/0/temp_id",
                    "code": "invalid_temp_id",
                    "value": temp_id,
                }
            ],
        },
    }


def test_duplicate_and_invalid_references_refuse_in_fixed_semantic_order():
    request = {
        "epoch": 3,
        "create": [
            {"temp_id": "T_CLEAN", "type": "slider"},
            {"temp_id": "T_CLEAN", "type": "panel"},
        ],
        "disconnect": ["TUNKNOWN.O0>C1.I0"],
        "set_values": [{"id": "N1", "value": 2}],
        "connect": ["T_CLEAN.O0>TABSENT.I0"],
        "groups": [{"action": "create", "members": ["N2"]}],
    }

    result = admit_gh_edit_request(request)

    assert result["success"] is False
    assert result["data"]["error"] == "gh_edit_admission_failed"
    assert result["data"]["issues"] == [
        {
            "path": "/create/1/temp_id",
            "code": "duplicate_temp_id",
            "value": "T_CLEAN",
        },
        {
            "path": "/disconnect/0",
            "code": "unresolved_temp_reference",
            "value": "TUNKNOWN",
        },
        {
            "path": "/set_values/0/id",
            "code": "invalid_component_reference",
            "value": "N1",
        },
        {
            "path": "/connect/0",
            "code": "unresolved_temp_reference",
            "value": "TABSENT",
        },
        {
            "path": "/groups/0/members/0",
            "code": "invalid_component_reference",
            "value": "N2",
        },
    ]


@pytest.mark.parametrize(
    "flow",
    [
        None,
        1,
        "C1.O0-C2.I0",
        "C1.O0>C2.I0>C3.I0",
        "C1.X0>C2.I0",
        "C1.O0>C2.X0",
        "C1.O-1>C2.I0",
        "C1.Ox>C2.I0",
        "C1.O2147483648>C2.I0",
        f"C1.O{'9' * 5000}>C2.I0",
    ],
)
def test_malformed_flows_refuse_before_reference_resolution(flow):
    result = admit_gh_edit_request({"epoch": 3, "connect": [flow]})

    assert result["data"]["issues"] == [
        {"path": "/connect/0", "code": "invalid_flow", "value": flow}
    ]


def test_no_mutation_edit_errors_become_failure_without_partial_success():
    result = {
        "success": True,
        "data": {
            "edit_summary": {
                "created": 0,
                "deleted": 0,
                "values_set": 0,
                "connected": 0,
                "disconnected": 0,
                "errors": ["Create failed: Centre Box not found"],
            }
        },
    }

    contracted = apply_gh_edit_contract(result)

    assert contracted["success"] is False
    assert contracted["verified"] is False
    assert contracted["errors"] == ["Create failed: Centre Box not found"]
    assert "partial_success" not in contracted
    assert contracted["data"]["errors"] == ["Create failed: Centre Box not found"]
    assert contracted["data"]["warnings"] == ["Create failed: Centre Box not found"]
    assert contracted["data"]["verified"] is False
    assert "failed before applying any mutations" in contracted["data"]["verification_note"]
    assert "failed before applying any mutations" in contracted["verification_note"]


def test_no_mutation_edit_errors_clear_stale_partial_success_flags():
    result = {
        "success": True,
        "partial_success": True,
        "data": {
            "partial_success": True,
            "edit_summary": {
                "created": 0,
                "deleted": 0,
                "values_set": 0,
                "connected": 0,
                "disconnected": 0,
                "errors": ["Create failed before mutation"],
            },
        },
    }

    contracted = apply_gh_edit_contract(result)

    assert contracted["success"] is False
    assert "partial_success" not in contracted
    assert "partial_success" not in contracted["data"]
    assert contracted["verified"] is False
    assert "failed before applying any mutations" in contracted["verification_note"]


def test_partial_mutation_edit_errors_are_strict_failure_with_partial_metadata():
    result = {
        "success": True,
        "data": {
            "edit_summary": {
                "created": 2,
                "deleted": 0,
                "values_set": 0,
                "connected": 0,
                "disconnected": 0,
                "errors": ["connect: param not found for 'T1.O0>T2.I3'"],
                "temp_id_map": {"T1": "G1"},
                "instance_guids": {"T1": "guid-1"},
            }
        },
    }

    contracted = apply_gh_edit_contract(result)

    assert contracted["success"] is False
    assert contracted["partial_success"] is True
    assert contracted["verified"] is False
    assert contracted["errors"] == ["connect: param not found for 'T1.O0>T2.I3'"]
    assert contracted["data"]["partial_success"] is True
    assert contracted["data"]["errors"] == ["connect: param not found for 'T1.O0>T2.I3'"]
    assert contracted["data"]["warnings"] == ["connect: param not found for 'T1.O0>T2.I3'"]
    assert contracted["data"]["verified"] is False
    assert "partially applied" in contracted["data"]["verification_note"]
    assert "partially applied" in contracted["verification_note"]


def test_phase1_compatibility_can_preserve_partial_success_transport_success():
    result = {
        "success": True,
        "data": {
            "edit_summary": {
                "created": 1,
                "errors": ["group: failed"],
            }
        },
    }

    contracted = apply_gh_edit_contract(result, strict_partial_success=False)

    assert contracted["success"] is True
    assert contracted["partial_success"] is True
    assert contracted["verified"] is False


def test_clean_edit_result_is_returned_unchanged():
    result = {"success": True, "data": {"edit_summary": {"created": 1}}}

    assert apply_gh_edit_contract(result) is result


def test_malformed_instance_guid_string_is_not_mutation_evidence():
    result = {
        "success": True,
        "data": {
            "edit_summary": {
                "created": 0,
                "errors": ["connect failed"],
                "instance_guids": "unavailable",
            }
        },
    }

    contracted = apply_gh_edit_contract(result)

    assert contracted["success"] is False
    assert "partial_success" not in contracted


def test_boolean_mutation_count_is_not_mutation_evidence():
    result = {
        "success": True,
        "data": {
            "edit_summary": {
                "created": True,
                "errors": ["create failed"],
            }
        },
    }

    contracted = apply_gh_edit_contract(result)

    assert contracted["success"] is False
    assert "partial_success" not in contracted


def test_existing_warning_string_is_preserved_as_single_warning():
    result = {
        "success": True,
        "data": {
            "warnings": "legacy warning",
            "edit_summary": {
                "created": 0,
                "errors": ["create failed"],
            },
        },
    }

    contracted = apply_gh_edit_contract(result)

    assert contracted["data"]["warnings"] == ["legacy warning", "create failed"]


def test_existing_warning_dict_is_ignored_not_split_into_keys():
    result = {
        "success": True,
        "data": {
            "warnings": {"bad": "shape"},
            "edit_summary": {
                "created": 0,
                "errors": ["create failed"],
            },
        },
    }

    contracted = apply_gh_edit_contract(result)

    assert contracted["data"]["warnings"] == ["create failed"]
