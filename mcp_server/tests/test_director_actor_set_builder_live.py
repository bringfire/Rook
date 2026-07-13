from __future__ import annotations

import os
import uuid

import pytest

from rook import director_actor_metadata as actor_metadata


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

SOURCE_ID = "a28cbdb5-51fa-46b2-b18b-ab880b54ded7"
EXISTING_ROOF_ACTOR_SET_REF = (
    ".rook/director_planning/actor_sets/roof_uplift_vertical_test_chunk_001.json"
)


def _live_enabled() -> bool:
    return os.environ.get("ROOK_DIRECTOR_ACTOR_SET_BUILDER_LIVE") == "1"


async def _read_metadata(arguments: dict) -> dict:
    project_root, source_document = await actor_metadata.resolve_active_project_root()
    ref = arguments["ref"]
    expected_kind = arguments["expected_kind"]
    return {
        "ref": ref,
        "expected_kind": expected_kind,
        "resolved_metadata_path": str(
            actor_metadata.resolve_metadata_ref(project_root, ref)
        ),
        "source_document": source_document,
        "payload": actor_metadata.load_metadata_ref(
            project_root, ref, expected_kind=expected_kind
        ),
    }


def _member_identity(member: dict) -> tuple[int, str]:
    return (
        member["ordinal"],
        member["resolved_reference"]["definition_object_id"],
    )


async def test_live_build_actor_set_from_fresh_source_occurrence():
    if not _live_enabled():
        pytest.skip(
            "Set ROOK_DIRECTOR_ACTOR_SET_BUILDER_LIVE=1 with Pearson open to run."
        )

    suffix = uuid.uuid4().hex[:8]
    snapshot_id = f"source_occurrence_roof_builder_live_{suffix}"
    actor_set_id = f"roof_builder_live_{suffix}"

    capture = await actor_metadata.capture_source_occurrence_v2(
        {
            "snapshot_id": snapshot_id,
            "ids": [SOURCE_ID],
            "intent": "live_actor_set_builder_gate",
            "label": "Live actor-set builder gate",
        }
    )
    built = await actor_metadata.build_actor_set_from_source_occurrence_v2(
        {
            "source_occurrence_snapshot_ref": capture["snapshot_ref"],
            "actor_set_id": actor_set_id,
        }
    )
    loaded = await _read_metadata(
        {"ref": built["actor_set_ref"], "expected_kind": "director_actor_set"},
    )
    payload = loaded["payload"]
    assert payload["schema_version"] == 2
    assert payload["metadata_kind"] == "director_actor_set"
    assert payload["actor_set_id"] == actor_set_id
    assert payload["source_occurrence_snapshot_ref"] == capture["snapshot_ref"]
    assert (
        payload["summary"]["member_count"]
        == payload["summary"]["resolved_count"]
        == built["member_count"]
    )
    assert built["member_count"] > 0

    ordinals = [m["ordinal"] for m in payload["members"]]
    assert ordinals == sorted(ordinals)
    assert len(ordinals) == len(set(ordinals))
    for member in payload["members"]:
        assert "actor_member_id" not in member
        assert "definition_object_index" not in member
        assert "current_reference" not in member
        assert "observed_selection" not in member
        assert member["resolved_reference"]["definition_object_id"]
        assert member["bbox_evidence"]["bbox_method"] == "tight_object"

    try:
        existing = await _read_metadata(
            {"ref": EXISTING_ROOF_ACTOR_SET_REF, "expected_kind": "director_actor_set"},
        )
    except actor_metadata.DirectorActorMetadataError:
        print("Existing hand-authored roof actor set not found; skipped oracle diff.")
        return

    existing_members = existing["payload"].get("members") or []
    existing_pairs = {
        _member_identity(m)
        for m in existing_members
        if isinstance(m, dict)
        and isinstance(m.get("ordinal"), int)
        and isinstance(m.get("resolved_reference"), dict)
        and m["resolved_reference"].get("definition_object_id")
    }
    built_pairs = {_member_identity(m) for m in payload["members"]}
    if existing_pairs:
        assert built_pairs == existing_pairs
