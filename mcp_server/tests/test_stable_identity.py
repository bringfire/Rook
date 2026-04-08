# mcp_server/tests/test_stable_identity.py
"""Tests for stable identity dedup in gh_build_knowledge."""
import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from rook.learning.gh_knowledge import GHKnowledgeBuilder, compute_stable_key, gh_build_knowledge
from rook.learning.knowledge_note import KnowledgeNote
from rook.learning.unified_store import UnifiedStore


# --- compute_stable_key tests ---


class TestComputeStableKey:
    def test_normal(self):
        assert compute_stable_key("Wasp", "Connection", "Wasp_Connection From Direction") == (
            "wasp|connection|wasp_connection from direction"
        )

    def test_normalized_case(self):
        assert compute_stable_key("WASP", "CONNECTION", "Wasp_Connection From Direction") == (
            "wasp|connection|wasp_connection from direction"
        )

    def test_trimmed(self):
        assert compute_stable_key("  Wasp  ", " Connection ", "  Name  ") == "wasp|connection|name"

    def test_missing_category(self):
        assert compute_stable_key("", "Connection", "Name") is None

    def test_missing_subcategory(self):
        assert compute_stable_key("Wasp", "", "Name") is None

    def test_missing_name(self):
        assert compute_stable_key("Wasp", "Connection", "") is None

    def test_all_missing(self):
        assert compute_stable_key("", "", "") is None

    def test_none_values(self):
        assert compute_stable_key(None, "Connection", "Name") is None


# --- Fixtures for gh_build_knowledge tests ---


def _make_temp_stores(tmpdir: Path):
    """Create temporary tiered, sparse, and unified stores for testing."""
    tiered_path = tmpdir / "tiered_knowledge.json"
    sparse_path = tmpdir / "sparse_index.json"
    notes_dir = tmpdir / "notes"

    tiered_path.write_text(json.dumps({"components": {}, "wiring_patterns": {}, "global_gotchas": []}))
    sparse_path.write_text(json.dumps({"guid_to_info": {}, "intent_to_guids": {}, "family_to_guids": {}}))

    store = UnifiedStore(
        notes_dir=notes_dir,
        index_path=tmpdir / "index.json",
        auto_save=True,
        enable_evolution=False,
    )
    return store, tiered_path, sparse_path


def _make_component_info(name="TestComp", category="TestCat", sub_category="TestSub", nick="TC"):
    return {
        "name": name,
        "type": "Component",
        "nickName": nick,
        "category": category,
        "subCategory": sub_category,
        "params": {"inputs": [], "outputs": []},
    }


def _add_note_with_stable_key(store, name, guid, stable_key, family="test"):
    """Add a component note with a stable_key for testing."""
    note = KnowledgeNote(
        note_id=KnowledgeNote.generate_id("component"),
        note_type="component",
        name=name,
        brief=f"{name} | test",
        created="2026-03-24T12:00:00Z",
        category=family,
        type_data={
            "guid": guid,
            "category": family,
            "stable_key": stable_key,
            "inputs": {},
            "outputs": {},
        },
        created_from="test",
    )
    store.add(note, skip_evolution=True)
    return note


def _add_note_without_stable_key(store, name, guid, family="test"):
    """Add a component note WITHOUT stable_key (simulates pre-migration note)."""
    note = KnowledgeNote(
        note_id=KnowledgeNote.generate_id("component"),
        note_type="component",
        name=name,
        brief=f"{name} | test",
        created="2026-03-24T12:00:00Z",
        category=family,
        type_data={
            "guid": guid,
            "category": family,
            "inputs": {},
            "outputs": {},
        },
        created_from="test",
    )
    store.add(note, skip_evolution=True)
    return note


def _seed_tiered_and_sparse(tiered_path, sparse_path, guid, name, family):
    """Write a tiered entry and sparse entry keyed by guid."""
    tiered = json.loads(tiered_path.read_text())
    tiered["components"][guid] = {"name": name, "family": family, "params": {}}
    tiered_path.write_text(json.dumps(tiered, indent=2))

    sparse = json.loads(sparse_path.read_text())
    sparse["guid_to_info"][guid] = {"name": name, "family": family, "nickName": ""}
    sparse.setdefault("intent_to_guids", {})[name.lower()] = [guid]
    sparse.setdefault("family_to_guids", {}).setdefault(family, []).append(guid)
    sparse_path.write_text(json.dumps(sparse, indent=2))


# --- Test: Step 1 GUID match with stable_key backfill ---


class TestGuidMatchBackfill:
    """When GUID matches an existing note that lacks stable_key,
    the system should backfill stable_key on the existing note."""

    def test_guid_match_backfills_stable_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            store, tiered_path, sparse_path = _make_temp_stores(tmpdir)

            existing_guid = "guid-existing-123"
            # Note exists WITHOUT stable_key (simulates old note)
            note = _add_note_without_stable_key(store, "TestComp", existing_guid, family="testcat")

            # Verify no stable_key
            assert "stable_key" not in (note.type_data or {})

            component_info = _make_component_info()

            with patch("rook.learning.gh_knowledge.get_knowledge_builder") as mock_builder_fn:
                mock_builder = mock_builder_fn.return_value
                mock_builder.build_from_component_info.return_value = {
                    "name": "TestComp", "family": "testcat", "params": {"inputs": {}, "outputs": {}},
                }
                mock_builder.save_entry.return_value = True
                mock_builder.ensure_sparse_entry.return_value = True

                with patch("rook.learning.unified_store.get_unified_store", return_value=store):
                    result = gh_build_knowledge(
                        component_info,
                        component_guid=existing_guid,
                        save=True,
                    )

            # Assert: GUID match succeeded
            assert result.get("saved_unified") is True

            # Assert: stable_key was backfilled
            updated_note = store.get(note.note_id)
            assert updated_note is not None
            assert updated_note.type_data.get("stable_key") == "testcat|testsub|testcomp"


# --- Test: Step 3 unique merge with store verification ---


class TestStableKeyUniqueMerge:
    """When GUID misses but stable_key uniquely matches one note,
    the system should merge: update unified note, re-key tiered + sparse."""

    def test_unique_merge_updates_all_three_stores(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            store, tiered_path, sparse_path = _make_temp_stores(tmpdir)

            old_guid = "guid-old-session"
            new_guid = "guid-new-session"
            stable_key = "testcat|testsub|testcomp"

            # Pre-populate: existing note with old_guid and stable_key
            note = _add_note_with_stable_key(store, "TestComp", old_guid, stable_key, family="testcat")
            # Also seed tiered + sparse with old_guid
            _seed_tiered_and_sparse(tiered_path, sparse_path, old_guid, "TestComp", "testcat")

            component_info = _make_component_info()

            with patch("rook.learning.gh_knowledge.get_knowledge_builder") as mock_builder_fn:
                mock_builder = mock_builder_fn.return_value
                mock_builder.build_from_component_info.return_value = {
                    "name": "TestComp", "family": "testcat", "params": {"inputs": {}, "outputs": {}},
                }
                mock_builder.save_entry.return_value = True
                mock_builder.ensure_sparse_entry.return_value = True
                mock_builder.tiered_path = tiered_path
                mock_builder.sparse_path = sparse_path
                # Use real re-key methods so file mutations actually happen
                mock_builder.rekey_tiered_entry.side_effect = (
                    lambda old, new: GHKnowledgeBuilder.rekey_tiered_entry(mock_builder, old, new)
                )
                mock_builder.rekey_sparse_entry.side_effect = (
                    lambda old, new: GHKnowledgeBuilder.rekey_sparse_entry(mock_builder, old, new)
                )

                with patch("rook.learning.unified_store.get_unified_store", return_value=store):
                    result = gh_build_knowledge(
                        component_info,
                        component_guid=new_guid,
                        save=True,
                    )

            # Assert: merge happened
            assert result.get("merged") is True
            assert result.get("saved_unified") is True

            # Assert: unified note updated with new GUID
            updated_note = store.get(note.note_id)
            assert updated_note.type_data["guid"] == new_guid
            assert updated_note.type_data["stable_key"] == stable_key

            # Assert: no duplicate notes
            matches = store.get_component_by_stable_key(stable_key)
            assert len(matches) == 1

            # Assert: tiered knowledge — old GUID removed
            tiered = json.loads(tiered_path.read_text())
            assert old_guid not in tiered["components"]

            # Assert: sparse index — old GUID removed from guid_to_info
            sparse = json.loads(sparse_path.read_text())
            assert old_guid not in sparse["guid_to_info"]

            # Assert: sparse index — old GUID removed from intent lists
            for intent_key, guid_list in sparse.get("intent_to_guids", {}).items():
                assert old_guid not in guid_list, f"old GUID still in intent_to_guids[{intent_key}]"

            # Assert: sparse index — old GUID removed from family lists
            for family, guid_list in sparse.get("family_to_guids", {}).items():
                assert old_guid not in guid_list, f"old GUID still in family_to_guids[{family}]"


# --- Test 4: Stable_key ambiguity ---


class TestStableKeyAmbiguity:
    """When two notes share the same stable_key and a new GUID arrives,
    the system should log a warning, skip auto-merge, and create a new entry."""

    def test_ambiguous_stable_key_creates_new_entry(self, caplog):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            store, tiered_path, sparse_path = _make_temp_stores(tmpdir)

            stable_key = "testcat|testsub|testcomp"

            # Pre-populate two notes with the same stable_key (simulates prior ambiguity)
            note1 = _add_note_with_stable_key(store, "TestComp", "guid-aaa", stable_key)
            note2 = _add_note_with_stable_key(store, "TestComp", "guid-bbb", stable_key)

            # Verify both exist
            matches = store.get_component_by_stable_key(stable_key)
            assert len(matches) == 2

            # Now learn with a brand-new GUID (misses Step 1)
            component_info = _make_component_info()
            new_guid = "guid-ccc-new-session"

            with patch("rook.learning.gh_knowledge.get_knowledge_builder") as mock_builder_fn:
                mock_builder = mock_builder_fn.return_value
                mock_builder.build_from_component_info.return_value = {
                    "name": "TestComp", "family": "testcat", "params": {"inputs": {}, "outputs": {}},
                }
                mock_builder.save_entry.return_value = True
                mock_builder.ensure_sparse_entry.return_value = True
                mock_builder.tiered_path = tiered_path
                mock_builder.sparse_path = sparse_path

                with patch("rook.learning.unified_store.get_unified_store", return_value=store):
                    with caplog.at_level(logging.WARNING, logger="rook.gh_knowledge"):
                        result = gh_build_knowledge(
                            component_info,
                            component_guid=new_guid,
                            save=True,
                        )

            # Assert: warning logged about ambiguity
            assert any("stable_key ambiguous" in msg for msg in caplog.messages), (
                f"Expected 'stable_key ambiguous' warning, got: {caplog.messages}"
            )

            # Assert: no auto-merge — original two notes unchanged
            matches_after = store.get_component_by_stable_key(stable_key)
            assert len(matches_after) == 3  # two original + one new

            # Assert: new entry was created
            assert result.get("saved_unified") is True
            assert result.get("merged") is not True


# --- Test: Name-based migration fallback ---


class TestNameBasedMigration:
    """When a pre-migration note exists (no stable_key) and GUID misses,
    the system should match by name, backfill stable_key, and merge."""

    def test_legacy_note_matched_by_name_and_merged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            store, tiered_path, sparse_path = _make_temp_stores(tmpdir)

            old_guid = "guid-old-session"
            new_guid = "guid-new-session"

            # Pre-populate: existing note WITHOUT stable_key (pre-migration)
            note = _add_note_without_stable_key(store, "TestComp", old_guid, family="testcat")
            _seed_tiered_and_sparse(tiered_path, sparse_path, old_guid, "TestComp", "testcat")

            component_info = _make_component_info()

            with patch("rook.learning.gh_knowledge.get_knowledge_builder") as mock_builder_fn:
                mock_builder = mock_builder_fn.return_value
                mock_builder.build_from_component_info.return_value = {
                    "name": "TestComp", "family": "testcat", "params": {"inputs": {}, "outputs": {}},
                }
                mock_builder.save_entry.return_value = True
                mock_builder.ensure_sparse_entry.return_value = True
                mock_builder.tiered_path = tiered_path
                mock_builder.sparse_path = sparse_path
                mock_builder.rekey_tiered_entry.side_effect = (
                    lambda old, new: GHKnowledgeBuilder.rekey_tiered_entry(mock_builder, old, new)
                )
                mock_builder.rekey_sparse_entry.side_effect = (
                    lambda old, new: GHKnowledgeBuilder.rekey_sparse_entry(mock_builder, old, new)
                )

                with patch("rook.learning.unified_store.get_unified_store", return_value=store):
                    result = gh_build_knowledge(
                        component_info,
                        component_guid=new_guid,
                        save=True,
                    )

            # Assert: merge happened via name-based migration
            assert result.get("merged") is True
            assert result.get("saved_unified") is True

            # Assert: unified note updated with new GUID and stable_key backfilled
            updated_note = store.get(note.note_id)
            assert updated_note.type_data["guid"] == new_guid
            assert updated_note.type_data["stable_key"] == "testcat|testsub|testcomp"

            # Assert: no duplicate notes
            assert len(store.get_component_by_stable_key("testcat|testsub|testcomp")) == 1

    def test_legacy_ambiguous_names_not_merged(self):
        """Two legacy notes with same name but no stable_key — should not auto-merge."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            store, tiered_path, sparse_path = _make_temp_stores(tmpdir)

            # Two notes with same name, no stable_key
            _add_note_without_stable_key(store, "TestComp", "guid-aaa", family="testcat")
            _add_note_without_stable_key(store, "TestComp", "guid-bbb", family="testcat")

            component_info = _make_component_info()
            new_guid = "guid-new"

            with patch("rook.learning.gh_knowledge.get_knowledge_builder") as mock_builder_fn:
                mock_builder = mock_builder_fn.return_value
                mock_builder.build_from_component_info.return_value = {
                    "name": "TestComp", "family": "testcat", "params": {"inputs": {}, "outputs": {}},
                }
                mock_builder.save_entry.return_value = True
                mock_builder.ensure_sparse_entry.return_value = True
                mock_builder.tiered_path = tiered_path
                mock_builder.sparse_path = sparse_path

                with patch("rook.learning.unified_store.get_unified_store", return_value=store):
                    result = gh_build_knowledge(
                        component_info,
                        component_guid=new_guid,
                        save=True,
                    )

            # Assert: no auto-merge — creates new entry
            assert result.get("merged") is not True
            assert result.get("saved_unified") is True


# --- Test 5: Missing subCategory ---


class TestMissingSubCategory:
    """When subCategory is empty, no stable_key dedup should be attempted."""

    def test_missing_subcategory_creates_entry_without_stable_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            store, tiered_path, sparse_path = _make_temp_stores(tmpdir)

            # component_info with empty subCategory
            component_info = _make_component_info(sub_category="")
            new_guid = "guid-no-subcat"

            with patch("rook.learning.gh_knowledge.get_knowledge_builder") as mock_builder_fn:
                mock_builder = mock_builder_fn.return_value
                mock_builder.build_from_component_info.return_value = {
                    "name": "TestComp", "family": "testcat", "params": {"inputs": {}, "outputs": {}},
                }
                mock_builder.save_entry.return_value = True
                mock_builder.ensure_sparse_entry.return_value = True
                mock_builder.tiered_path = tiered_path
                mock_builder.sparse_path = sparse_path

                with patch("rook.learning.unified_store.get_unified_store", return_value=store):
                    result = gh_build_knowledge(
                        component_info,
                        component_guid=new_guid,
                        save=True,
                    )

            # Assert: entry was created
            assert result.get("saved_unified") is True

            # Assert: no stable_key on the new note
            note_id = result.get("unified_note_id")
            assert note_id is not None
            note = store.get(note_id)
            assert note is not None
            td = note.type_data or {}
            assert "stable_key" not in td or td.get("stable_key") is None

    def test_missing_subcategory_does_not_crash(self):
        """Ensure no exception when subCategory is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            store, tiered_path, sparse_path = _make_temp_stores(tmpdir)

            component_info = _make_component_info(sub_category="", category="")
            new_guid = "guid-no-cat-no-subcat"

            with patch("rook.learning.gh_knowledge.get_knowledge_builder") as mock_builder_fn:
                mock_builder = mock_builder_fn.return_value
                mock_builder.build_from_component_info.return_value = {
                    "name": "TestComp", "family": "", "params": {"inputs": {}, "outputs": {}},
                }
                mock_builder.save_entry.return_value = True
                mock_builder.ensure_sparse_entry.return_value = True
                mock_builder.tiered_path = tiered_path
                mock_builder.sparse_path = sparse_path

                with patch("rook.learning.unified_store.get_unified_store", return_value=store):
                    # Should not raise
                    result = gh_build_knowledge(
                        component_info,
                        component_guid=new_guid,
                        save=True,
                    )

            assert result.get("saved_unified") is True
