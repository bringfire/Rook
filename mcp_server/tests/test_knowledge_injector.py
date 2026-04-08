"""Tests for universal knowledge injection system."""

import asyncio
import math
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest
from rook.learning.knowledge_injector import (
    should_inject,
    inject_knowledge,
    record_injection_success,
    _route_to_store,
    _score_gotcha,
    _score_note,
    _severity_weight,
    _recency_decay,
    _ensure_staleness_fields,
    _gh_intent,
    _gh_operation,
    _rhino_command_name,
    _GH_TOOL_OPERATION,
    _WRAPPED_TOOLS,
    _SKIP_TOOLS,
    _INTENT_TOOLS,
)
from rook.learning.phase_tracker import WorkflowPhase


# -------------------------------------------------------------------------
# should_inject
# -------------------------------------------------------------------------

class TestShouldInject:
    """Test the gating function that decides whether to inject."""

    def test_normal_success_returns_true(self):
        result = {"success": True, "data": {"some": "value"}}
        assert should_inject("gh_move", result) is True

    def test_wrapped_tool_returns_false(self):
        result = {"success": True, "data": {"some": "value"}}
        for tool in _WRAPPED_TOOLS:
            assert should_inject(tool, result) is False

    def test_skip_tool_returns_false(self):
        result = {"success": True, "data": {"some": "value"}}
        for tool in _SKIP_TOOLS:
            assert should_inject(tool, result) is False

    def test_failed_result_returns_false(self):
        result = {"success": False, "data": {"error": "something"}}
        assert should_inject("gh_move", result) is False

    def test_missing_success_returns_false(self):
        result = {"data": {"some": "value"}}
        assert should_inject("gh_move", result) is False

    def test_non_dict_data_returns_false(self):
        result = {"success": True, "data": "just a string"}
        assert should_inject("gh_move", result) is False

    def test_already_has_gotchas_returns_false(self):
        result = {"success": True, "data": {"gotchas": ["something"]}}
        assert should_inject("gh_move", result) is False

    def test_already_has_knowledge_hint_returns_false(self):
        result = {"success": True, "data": {"knowledge_hint": "tip"}}
        assert should_inject("gh_move", result) is False

    def test_none_data_returns_false(self):
        result = {"success": True, "data": None}
        assert should_inject("gh_move", result) is False

    def test_rhino_tool_returns_true(self):
        result = {"success": True, "data": {"objects": []}}
        assert should_inject("rhino_create", result) is True

    def test_general_tool_returns_true(self):
        result = {"success": True, "data": {"result": "ok"}}
        assert should_inject("some_other_tool", result) is True


# -------------------------------------------------------------------------
# Routing
# -------------------------------------------------------------------------

class TestRouting:
    """Test tool name → store type routing."""

    def test_gh_prefix(self):
        assert _route_to_store("gh_connect") == "gh"
        assert _route_to_store("gh_execute_intent") == "gh"

    def test_rhino_prefix(self):
        assert _route_to_store("rhino_create") == "rhino"
        assert _route_to_store("rhino_command") == "rhino"

    def test_other_prefix(self):
        assert _route_to_store("some_tool") == "general"
        assert _route_to_store("knowledge_query") == "general"


# -------------------------------------------------------------------------
# Scoring
# -------------------------------------------------------------------------

class TestScoreGotcha:
    """Test gotcha scoring formula."""

    def test_string_gotcha_gets_neutral_score(self):
        assert _score_gotcha("plain string gotcha") == 0.5

    def test_dict_gotcha_with_defaults(self):
        gotcha = {"message": "test", "severity": "medium"}
        score = _score_gotcha(gotcha)
        # severity=2.0, occurrence=1→log10(2)=0.301, recency=0.5, confidence=0.7
        expected = 2.0 * math.log10(2) * 0.5 * 0.7
        assert abs(score - expected) < 0.01

    def test_high_severity_scores_higher(self):
        low = _score_gotcha({"message": "t", "severity": "low"})
        high = _score_gotcha({"message": "t", "severity": "high"})
        assert high > low

    def test_critical_severity_scores_highest(self):
        medium = _score_gotcha({"message": "t", "severity": "medium"})
        critical = _score_gotcha({"message": "t", "severity": "critical"})
        assert critical > medium

    def test_link_boost_adds_to_score(self):
        no_links = _score_gotcha({"message": "t", "link_count": 0})
        with_links = _score_gotcha({"message": "t", "link_count": 4})
        assert with_links > no_links
        assert with_links - no_links == pytest.approx(0.2, abs=0.01)

    def test_link_boost_capped_at_03(self):
        many_links = _score_gotcha({"message": "t", "link_count": 100})
        six_links = _score_gotcha({"message": "t", "link_count": 6})
        assert many_links == six_links  # Both capped at 0.3

    def test_high_occurrence_boosts_score(self):
        low_occ = _score_gotcha({"message": "t", "occurrence_count": 1})
        high_occ = _score_gotcha({"message": "t", "occurrence_count": 100})
        assert high_occ > low_occ

    def test_invalid_types_return_neutral(self):
        assert _score_gotcha({"message": "t", "occurrence_count": "not_a_number"}) == 0.5

    def test_confidence_zero_gives_zero_base(self):
        score = _score_gotcha({"message": "t", "confidence": 0.0})
        # base is 0, only link_boost remains
        assert score == pytest.approx(0.0, abs=0.01)

    def test_confidence_clamped_to_1(self):
        s1 = _score_gotcha({"message": "t", "confidence": 1.0})
        s2 = _score_gotcha({"message": "t", "confidence": 5.0})  # Should clamp
        assert s1 == s2


class TestSeverityWeight:
    """Test severity string → numeric weight."""

    def test_known_severities(self):
        assert _severity_weight("low") == 1.0
        assert _severity_weight("medium") == 2.0
        assert _severity_weight("high") == 3.0
        assert _severity_weight("critical") == 5.0

    def test_unknown_severity_defaults_to_medium(self):
        assert _severity_weight("unknown") == 2.0
        assert _severity_weight("") == 2.0


class TestRecencyDecay:
    """Test exponential recency decay with clamping."""

    def test_none_returns_neutral(self):
        assert _recency_decay(None) == 0.5

    def test_just_verified_returns_near_1(self):
        now = datetime.now(timezone.utc).isoformat()
        decay = _recency_decay(now)
        assert 0.95 <= decay <= 1.0

    def test_21_days_ago_returns_half(self):
        past = (datetime.now(timezone.utc) - timedelta(days=21)).isoformat()
        decay = _recency_decay(past)
        assert 0.45 <= decay <= 0.55

    def test_very_old_clamped_to_03(self):
        ancient = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
        decay = _recency_decay(ancient)
        assert decay == pytest.approx(0.3, abs=0.01)

    def test_z_suffix_handled(self):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        decay = _recency_decay(now)
        assert 0.95 <= decay <= 1.0

    def test_invalid_string_returns_neutral(self):
        assert _recency_decay("not-a-date") == 0.5

    def test_future_date_clamped_to_1(self):
        future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        decay = _recency_decay(future)
        assert decay == pytest.approx(1.0, abs=0.01)


class TestScoreNote:
    """Test UnifiedStore note scoring."""

    def test_empty_note_gets_base_score(self):
        score = _score_note({}, WorkflowPhase.EXPLORATION)
        assert score == pytest.approx(0.5, abs=0.01)

    def test_phase_matching_boosts_score(self):
        note = {"tags": ["grasshopper", "component"]}
        score_match = _score_note(note, WorkflowPhase.GH_BUILD)
        score_no_match = _score_note(note, WorkflowPhase.RHINO_MODEL)
        assert score_match > score_no_match

    def test_links_boost_score(self):
        no_links = _score_note({"links": []}, WorkflowPhase.EXPLORATION)
        with_links = _score_note({"links": ["a", "b", "c"]}, WorkflowPhase.EXPLORATION)
        assert with_links > no_links

    def test_link_boost_capped(self):
        many = _score_note({"links": list(range(20))}, WorkflowPhase.EXPLORATION)
        six = _score_note({"links": list(range(6))}, WorkflowPhase.EXPLORATION)
        assert many == six  # Both capped at 0.3


# -------------------------------------------------------------------------
# Staleness lazy migration
# -------------------------------------------------------------------------

class TestEnsureStalenessFields:
    """Test lazy migration of gotcha entries."""

    def test_string_gotcha_wrapped_to_dict(self):
        result = _ensure_staleness_fields("plain warning")
        assert result["message"] == "plain warning"
        assert result["severity"] == "medium"
        assert result["confidence"] == 0.7
        assert result["occurrence_count"] == 1
        assert result["link_count"] == 0

    def test_string_uses_cmd_metadata(self):
        cmd = MagicMock()
        cmd.observations_count = 42
        cmd.last_updated = "2026-01-15T00:00:00Z"
        result = _ensure_staleness_fields("warn", cmd)
        assert result["occurrence_count"] == 42
        assert result["last_verified"] == "2026-01-15T00:00:00Z"

    def test_dict_gotcha_backfills_missing(self):
        gotcha = {"message": "test", "severity": "high"}
        result = _ensure_staleness_fields(gotcha)
        assert result["severity"] == "high"  # Preserved
        assert result["confidence"] == 0.7  # Backfilled
        assert result["occurrence_count"] == 1  # Backfilled

    def test_dict_gotcha_preserves_existing(self):
        gotcha = {"message": "test", "confidence": 0.9, "link_count": 5}
        result = _ensure_staleness_fields(gotcha)
        assert result["confidence"] == 0.9
        assert result["link_count"] == 5

    def test_dict_without_message_gets_str(self):
        gotcha = {"severity": "low"}
        result = _ensure_staleness_fields(gotcha)
        assert "message" in result


# -------------------------------------------------------------------------
# GH tool → operation mapping
# -------------------------------------------------------------------------

class TestGHOperationMapping:
    """Test the tool name → operation key mapping."""

    def test_mapped_tools_return_operation(self):
        assert _gh_operation("gh_move") == "move"
        assert _gh_operation("gh_component") == "create"
        assert _gh_operation("gh_set_reference") == "reference"
        assert _gh_operation("gh_investigate") == "investigate"

    def test_unmapped_tool_returns_none(self):
        assert _gh_operation("gh_solve") is None
        assert _gh_operation("gh_preview") is None
        assert _gh_operation("not_a_gh_tool") is None

    def test_all_wrapped_tools_are_mapped(self):
        """Wrapped tools should also be in the operation mapping."""
        for tool in _WRAPPED_TOOLS:
            assert tool in _GH_TOOL_OPERATION, f"{tool} missing from mapping"

    def test_intent_tools_are_mapped(self):
        for tool in _INTENT_TOOLS:
            assert tool in _GH_TOOL_OPERATION

    def test_mapping_covers_all_categories(self):
        ops = set(_GH_TOOL_OPERATION.values())
        expected = {
            "wire", "disconnect", "set_value", "delete", "create",
            "move", "canvas_cleanup", "group", "query", "reference",
            "document", "explore", "inspect_output", "investigate",
        }
        assert ops == expected


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

class TestGHIntent:
    """Test intent extraction from GH tool arguments."""

    def test_intent_arg_takes_priority(self):
        assert _gh_intent("gh_execute_intent", {"intent": "create sphere"}) == "create sphere"

    def test_name_arg_used_if_no_intent(self):
        assert _gh_intent("gh_component", {"name": "Circle"}) == "Circle"

    def test_fallback_to_tool_name(self):
        result = _gh_intent("gh_move", {})
        assert result == "move"

    def test_underscores_replaced_in_fallback(self):
        result = _gh_intent("gh_canvas_cleanup", {})
        assert result == "canvas cleanup"


class TestRhinoCommandName:
    """Test Rhino command name extraction."""

    def test_command_arg_normalized(self):
        assert _rhino_command_name("rhino_command", {"command": "Box"}) == "-Box"
        assert _rhino_command_name("rhino_command", {"command": "-Box"}) == "-Box"
        assert _rhino_command_name("rhino_command", {"command": "_Box"}) == "-Box"

    def test_intent_extracts_capitalized_word(self):
        result = _rhino_command_name("rhino_execute_intent", {"intent": "create a Box"})
        assert result == "-Box"

    def test_no_command_or_intent_returns_empty(self):
        assert _rhino_command_name("rhino_create", {}) == ""

    def test_empty_command_returns_empty(self):
        assert _rhino_command_name("rhino_command", {"command": ""}) == ""

    def test_dash_only_command_returns_empty(self):
        assert _rhino_command_name("rhino_command", {"command": "-"}) == ""


# -------------------------------------------------------------------------
# inject_knowledge (async, needs mocking)
# -------------------------------------------------------------------------

class TestInjectKnowledge:
    """Test the main injection entry point."""

    def test_adds_knowledge_hint_to_data(self):
        result = {"success": True, "data": {"some": "value"}}
        with patch(
            "rook.learning.knowledge_injector._fetch_and_score",
            return_value=("Use GUID not name", {"store": "gh", "source": "gh_operation"}),
        ):
            enriched = asyncio.run(inject_knowledge("gh_move", {}, result))
        assert enriched["data"]["knowledge_hint"] == "Use GUID not name"
        assert enriched["_injection_meta"]["store"] == "gh"

    def test_no_hint_no_injection(self):
        result = {"success": True, "data": {"some": "value"}}
        with patch(
            "rook.learning.knowledge_injector._fetch_and_score",
            return_value=(None, None),
        ):
            enriched = asyncio.run(inject_knowledge("gh_move", {}, result))
        assert "knowledge_hint" not in enriched["data"]
        assert "_injection_meta" not in enriched

    def test_exception_returns_original_result(self):
        result = {"success": True, "data": {"some": "value"}}
        with patch(
            "rook.learning.knowledge_injector._fetch_and_score",
            side_effect=RuntimeError("boom"),
        ):
            enriched = asyncio.run(inject_knowledge("gh_move", {}, result))
        assert enriched is result
        assert "knowledge_hint" not in enriched["data"]

    def test_none_arguments_handled(self):
        result = {"success": True, "data": {"some": "value"}}
        with patch(
            "rook.learning.knowledge_injector._fetch_and_score",
            return_value=(None, None),
        ):
            enriched = asyncio.run(inject_knowledge("gh_move", None, result))
        assert enriched is result

    def test_p0_p1_mutually_exclusive(self):
        """When P0 hint exists, P1 workflow hint should NOT be added."""
        result = {"success": True, "data": {"some": "value"}}
        with patch(
            "rook.learning.knowledge_injector._fetch_and_score",
            return_value=("per-tool hint", {"store": "gh"}),
        ), patch(
            "rook.learning.knowledge_injector._fetch_workflow_hint",
            return_value="workflow hint",
        ):
            enriched = asyncio.run(inject_knowledge("gh_move", {}, result))
        assert enriched["data"]["knowledge_hint"] == "per-tool hint"
        assert "workflow_hint" not in enriched["data"]


# -------------------------------------------------------------------------
# record_injection_success (P2 staleness)
# -------------------------------------------------------------------------

class TestRecordInjectionSuccess:
    """Test staleness feedback routing."""

    def test_unified_store_called(self):
        with patch(
            "rook.learning.unified_store.get_unified_store"
        ) as mock_get:
            mock_store = MagicMock()
            mock_get.return_value = mock_store
            record_injection_success({"store": "unified", "note_id": "abc123"})
            mock_store.mark_used_successfully.assert_called_once_with("abc123")

    def test_command_store_called(self):
        with patch(
            "rook.learning.command_knowledge_store.get_command_knowledge_store"
        ) as mock_get:
            mock_store = MagicMock()
            mock_get.return_value = mock_store
            record_injection_success({"store": "command", "command": "-Box"})
            mock_store.record_gotcha_success.assert_called_once_with("-Box")

    def test_empty_command_skipped(self):
        with patch(
            "rook.learning.command_knowledge_store.get_command_knowledge_store"
        ) as mock_get:
            record_injection_success({"store": "command", "command": ""})
            mock_get.assert_not_called()

    def test_dash_only_command_skipped(self):
        with patch(
            "rook.learning.command_knowledge_store.get_command_knowledge_store"
        ) as mock_get:
            record_injection_success({"store": "command", "command": "-"})
            mock_get.assert_not_called()

    def test_gh_store_no_staleness_yet(self):
        """GH store has no per-entry staleness — should be a no-op."""
        record_injection_success({"store": "gh", "source": "gh_operation"})

    def test_exception_does_not_propagate(self):
        with patch(
            "rook.learning.unified_store.get_unified_store",
            side_effect=RuntimeError("broken"),
        ):
            # Should not raise
            record_injection_success({"store": "unified", "note_id": "abc"})
