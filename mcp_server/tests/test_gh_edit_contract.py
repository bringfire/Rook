from rook.gh_edit_contract import apply_gh_edit_contract


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

    contracted = apply_gh_edit_contract(result, strict_partial_success=False)

    assert contracted["success"] is False
    assert contracted["verified"] is False
    assert contracted["errors"] == ["Create failed: Centre Box not found"]
    assert "partial_success" not in contracted
    assert contracted["data"]["errors"] == ["Create failed: Centre Box not found"]
    assert contracted["data"]["warnings"] == ["Create failed: Centre Box not found"]
    assert contracted["data"]["verified"] is False
    assert "failed before applying any mutations" in contracted["data"]["verification_note"]
    assert "failed before applying any mutations" in contracted["verification_note"]


def test_partial_mutation_edit_errors_are_compat_success_but_unverified():
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

    contracted = apply_gh_edit_contract(result, strict_partial_success=False)

    assert contracted["success"] is True
    assert contracted["partial_success"] is True
    assert contracted["verified"] is False
    assert contracted["errors"] == ["connect: param not found for 'T1.O0>T2.I3'"]
    assert contracted["data"]["partial_success"] is True
    assert contracted["data"]["errors"] == ["connect: param not found for 'T1.O0>T2.I3'"]
    assert contracted["data"]["verified"] is False
    assert "partially applied" in contracted["data"]["verification_note"]
    assert "partially applied" in contracted["verification_note"]


def test_partial_mutation_edit_errors_flip_to_strict_failure_when_enabled():
    result = {
        "success": True,
        "data": {
            "edit_summary": {
                "created": 1,
                "errors": ["group: failed"],
            }
        },
    }

    contracted = apply_gh_edit_contract(result, strict_partial_success=True)

    assert contracted["success"] is False
    assert contracted["partial_success"] is True
    assert contracted["verified"] is False


def test_clean_edit_result_is_returned_unchanged():
    result = {"success": True, "data": {"edit_summary": {"created": 1}}}

    assert apply_gh_edit_contract(result) is result
