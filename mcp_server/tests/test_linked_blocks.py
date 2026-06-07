from __future__ import annotations

import pytest

from rook.linked_blocks import block_def_name
from rook import linked_blocks as lb

# A valid canonical artifact id is 64 lowercase hex chars (SHA-256). These
# fixtures pad a recognizable 16-hex prefix out to full length.
_AID = "a1b2c3d4e5f67890" + "0" * 48
_AID2 = "ffffffffffffffff" + "0" * 48
_ALPHABET = set("abcdefghijklmnopqrstuvwxyz0123456789_-")


def test_deterministic_same_inputs_same_output():
    assert block_def_name("mc-abc", _AID) == block_def_name("mc-abc", _AID)


def test_prefix_and_shape():
    name = block_def_name("mc-abc", _AID)
    parts = name.split("_")
    assert parts[:2] == ["rook", "p7lb"]
    assert len(parts[2]) == 8 and all(c in "0123456789abcdef" for c in parts[2])
    assert parts[3] == "a1b2c3d4e5f67890"  # first 16 hex of the artifact id
    assert set(name) <= _ALPHABET


def test_case_stability_lowercase_output():
    lower = block_def_name("mc-abc", _AID)
    upper = block_def_name("mc-abc", ("A1B2C3D4E5F67890" + "0" * 48))
    assert lower == upper == lower.lower()


def test_illegal_looking_contract_id_still_restricted_alphabet():
    name = block_def_name("contract with spaces / Ünîçødé / ../x", _AID)
    assert set(name) <= _ALPHABET
    assert name.startswith("rook_p7lb_")


def test_distinct_contracts_distinct_names():
    assert block_def_name("mc-aaa", _AID) != block_def_name("mc-bbb", _AID)


def test_distinct_sources_distinct_names():
    assert block_def_name("mc-abc", _AID) != block_def_name("mc-abc", _AID2)


def test_rejects_too_short_source_artifact_id():
    with pytest.raises(ValueError):
        block_def_name("mc-abc", "a1b2c3")


def test_rejects_16_hex_prefix_requires_full_sha256():
    # A 16-hex prefix must NOT be accepted: only a full 64-char SHA-256
    # artifact id. Else a truncated prefix would alias the full id to the
    # same durable block name.
    with pytest.raises(ValueError):
        block_def_name("mc-abc", "a1b2c3d4e5f67890")  # exactly 16 hex, not 64


def test_rejects_non_hex_source_artifact_id():
    with pytest.raises(ValueError):
        block_def_name("mc-abc", "z" * 64)


# ----- P7 Slice 4: plan_source_action decision table -----
_AID_A = "a" * 64          # a valid-looking 64-hex source artifact id
_AID_B = "b" * 64          # a different one


def _facts(is_linked, source_path, block_type="Linked"):
    return {"isLinked": is_linked, "sourcePath": source_path, "blockType": block_type}


def test_plan_absent_block_present_source_creates():
    assert lb.plan_source_action(
        block_facts=None, expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=None, source_present=True,
        refresh_policy="refresh_on_demand") == lb.WOULD_CREATE_LINK


def test_plan_absent_block_missing_source_not_present():
    assert lb.plan_source_action(
        block_facts=None, expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=None, source_present=False,
        refresh_policy="refresh_on_demand") == lb.SOURCE_ARTIFACT_NOT_PRESENT


def test_plan_existing_nonlinked_is_conflict():
    assert lb.plan_source_action(
        block_facts=_facts(False, ""), expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=None, source_present=True,
        refresh_policy="refresh_on_demand") == lb.CONFLICT_NONLINKED


def test_plan_linked_unparseable_path_is_unresolvable():
    assert lb.plan_source_action(
        block_facts=_facts(True, "??"), expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=None, source_present=True,
        refresh_policy="refresh_on_demand") == lb.SOURCE_PATH_UNRESOLVABLE


def test_plan_linked_different_source_is_conflict():
    assert lb.plan_source_action(
        block_facts=_facts(True, "C:/x.3dm"), expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=_AID_B, source_present=True,
        refresh_policy="refresh_on_demand") == lb.CONFLICT_DIFFERENT_SOURCE


def test_plan_same_source_on_demand_refreshes():
    assert lb.plan_source_action(
        block_facts=_facts(True, "C:/a.3dm"), expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=_AID_A, source_present=True,
        refresh_policy="refresh_on_demand") == lb.WOULD_REFRESH_EXISTING


def test_plan_same_source_after_save_is_already_linked():
    assert lb.plan_source_action(
        block_facts=_facts(True, "C:/a.3dm"), expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=_AID_A, source_present=True,
        refresh_policy="refresh_after_save") == lb.ALREADY_LINKED


def test_plan_same_source_absent_present_bar_blocks_already_linked():
    # Finding 2: present-bar applies to already_linked too.
    assert lb.plan_source_action(
        block_facts=_facts(True, "C:/a.3dm"), expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=_AID_A, source_present=False,
        refresh_policy="refresh_after_save") == lb.SOURCE_ARTIFACT_NOT_PRESENT


def test_plan_same_source_absent_present_bar_blocks_refresh():
    assert lb.plan_source_action(
        block_facts=_facts(True, "C:/a.3dm"), expected_source_artifact_id=_AID_A,
        observed_source_artifact_id=_AID_A, source_present=False,
        refresh_policy="refresh_on_demand") == lb.SOURCE_ARTIFACT_NOT_PRESENT
