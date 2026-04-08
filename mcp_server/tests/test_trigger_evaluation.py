"""Tests for GH operation trigger evaluation and query_operation."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from rook.learning.gh_knowledge import (
    _TRIGGER_RULES,
    _evaluate_trigger,
    GHKnowledgeStore,
    gh_query_operation,
)


# -------------------------------------------------------------------------
# _evaluate_trigger
# -------------------------------------------------------------------------

class TestEvaluateTrigger:
    """Test the trigger evaluation function."""

    def test_always_returns_true(self):
        assert _evaluate_trigger("always", {}) is True

    def test_always_ignores_context(self):
        assert _evaluate_trigger("always", {"target_type": "slider"}) is True

    def test_unknown_trigger_returns_false(self):
        assert _evaluate_trigger("nonexistent_trigger", {}) is False

    def test_unknown_trigger_ignores_context(self):
        assert _evaluate_trigger("nonexistent_trigger", {"target_type": "slider"}) is False

    def test_target_is_slider_matches(self):
        assert _evaluate_trigger("target_is_slider", {"target_type": "slider"}) is True

    def test_target_is_slider_no_match(self):
        assert _evaluate_trigger("target_is_slider", {"target_type": "panel"}) is False

    def test_target_is_slider_missing_key(self):
        assert _evaluate_trigger("target_is_slider", {}) is False

    def test_target_is_integer_slider_matches(self):
        assert _evaluate_trigger("target_is_integer_slider", {"target_type": "integer_slider"}) is True

    def test_target_is_integer_slider_no_match_on_regular_slider(self):
        assert _evaluate_trigger("target_is_integer_slider", {"target_type": "slider"}) is False

    def test_contains_list_component_truthy(self):
        assert _evaluate_trigger("contains_list_component", {"involves_list": True}) is True

    def test_contains_list_component_falsy(self):
        assert _evaluate_trigger("contains_list_component", {"involves_list": False}) is False

    def test_contains_list_component_missing(self):
        assert _evaluate_trigger("contains_list_component", {}) is False

    def test_target_in_group_truthy(self):
        assert _evaluate_trigger("target_in_group", {"in_group": True}) is True

    def test_target_in_group_falsy(self):
        assert _evaluate_trigger("target_in_group", {"in_group": False}) is False

    def test_target_has_expression(self):
        assert _evaluate_trigger("target_has_expression", {"has_expression": True}) is True
        assert _evaluate_trigger("target_has_expression", {"has_expression": False}) is False

    def test_component_from_plugin(self):
        assert _evaluate_trigger("component_from_plugin", {"from_plugin": True}) is True
        assert _evaluate_trigger("component_from_plugin", {"from_plugin": False}) is False

    def test_param_has_multiple_sources(self):
        assert _evaluate_trigger("param_has_multiple_sources", {"multiple_sources": True}) is True
        assert _evaluate_trigger("param_has_multiple_sources", {"multiple_sources": False}) is False

    def test_data_structure_mismatch(self):
        assert _evaluate_trigger("data_structure_mismatch", {"data_mismatch": True}) is True
        assert _evaluate_trigger("data_structure_mismatch", {"data_mismatch": False}) is False

    def test_empty_context_for_all_rules(self):
        """All conditional triggers should return False on empty context."""
        for trigger_name in _TRIGGER_RULES:
            assert _evaluate_trigger(trigger_name, {}) is False, f"{trigger_name} should be False on empty context"


# -------------------------------------------------------------------------
# _TRIGGER_RULES coverage
# -------------------------------------------------------------------------

class TestTriggerRules:
    """Test the trigger rules dict itself."""

    def test_expected_triggers_present(self):
        expected = {
            "target_is_slider",
            "target_is_integer_slider",
            "contains_list_component",
            "target_in_group",
            "target_has_expression",
            "component_from_plugin",
            "param_has_multiple_sources",
            "data_structure_mismatch",
        }
        assert set(_TRIGGER_RULES.keys()) == expected

    def test_all_rules_are_callable(self):
        for name, rule in _TRIGGER_RULES.items():
            assert callable(rule), f"{name} is not callable"

    def test_all_rules_return_bool_compatible(self):
        """Rules should return truthy/falsy values that work with bool()."""
        for name, rule in _TRIGGER_RULES.items():
            result = rule({})
            assert result is None or isinstance(result, (bool, int, str, type(None))), (
                f"{name} returned unexpected type {type(result)}"
            )


# -------------------------------------------------------------------------
# query_operation integration
# -------------------------------------------------------------------------

class TestQueryOperation:
    """Test the GHKnowledgeStore.query_operation method."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a store with test operations knowledge."""
        ops_file = tmp_path / "operations_knowledge.json"
        ops_file.write_text(json.dumps({
            "version": "1.1",
            "operations": {
                "wire": {
                    "aliases": ["connect"],
                    "description": "Connect components",
                    "gotchas": [
                        {"id": "g1", "trigger": "always", "message": "Always shown", "severity": "warning"},
                        {"id": "g2", "trigger": "contains_list_component", "message": "List gotcha", "severity": "info"},
                        {"id": "g3", "trigger": "target_in_group", "message": "Group gotcha", "severity": "info"},
                    ],
                    "common_mistakes": [
                        {"pattern": "wrong param", "correction": "query first"}
                    ],
                },
                "set_value": {
                    "aliases": ["set"],
                    "description": "Set value",
                    "gotchas": [
                        {"id": "s1", "trigger": "target_is_slider", "message": "Check bounds", "severity": "warning"},
                        {"id": "s2", "trigger": "target_is_integer_slider", "message": "Integer only", "severity": "info"},
                    ],
                    "common_mistakes": [],
                },
            },
        }))

        s = GHKnowledgeStore()
        s._operations_path = ops_file
        s._operations_knowledge = None  # Force reload
        return s

    def test_always_trigger_included(self, store):
        result = store.query_operation("wire")
        gotcha_ids = [g["id"] for g in result["gotchas"]]
        assert "g1" in gotcha_ids

    def test_conditional_trigger_excluded_when_no_context(self, store):
        result = store.query_operation("wire")
        gotcha_ids = [g["id"] for g in result["gotchas"]]
        assert "g2" not in gotcha_ids
        assert "g3" not in gotcha_ids

    def test_conditional_trigger_included_when_matched(self, store):
        result = store.query_operation("wire", {"involves_list": True})
        gotcha_ids = [g["id"] for g in result["gotchas"]]
        assert "g1" in gotcha_ids  # always
        assert "g2" in gotcha_ids  # matched
        assert "g3" not in gotcha_ids  # not matched

    def test_multiple_triggers_matched(self, store):
        result = store.query_operation("wire", {"involves_list": True, "in_group": True})
        gotcha_ids = [g["id"] for g in result["gotchas"]]
        assert "g1" in gotcha_ids
        assert "g2" in gotcha_ids
        assert "g3" in gotcha_ids

    def test_alias_resolves(self, store):
        result = store.query_operation("connect")
        assert result["operation"] == "wire"
        assert len(result["gotchas"]) >= 1  # at least the "always" one

    def test_unknown_operation_returns_empty_gotchas(self, store):
        result = store.query_operation("teleport")
        assert result["gotchas"] == []
        assert "No operation knowledge" in result["hint"]

    def test_common_mistakes_returned(self, store):
        result = store.query_operation("wire")
        assert len(result["common_mistakes"]) == 1
        assert result["common_mistakes"][0]["pattern"] == "wrong param"

    def test_slider_trigger_with_correct_type(self, store):
        result = store.query_operation("set_value", {"target_type": "slider"})
        gotcha_ids = [g["id"] for g in result["gotchas"]]
        assert "s1" in gotcha_ids
        assert "s2" not in gotcha_ids

    def test_integer_slider_trigger(self, store):
        result = store.query_operation("set_value", {"target_type": "integer_slider"})
        gotcha_ids = [g["id"] for g in result["gotchas"]]
        assert "s1" not in gotcha_ids  # "slider" != "integer_slider"
        assert "s2" in gotcha_ids

    def test_case_insensitive_operation(self, store):
        result = store.query_operation("WIRE")
        assert result["operation"] == "wire"
        assert len(result["gotchas"]) >= 1

    def test_hint_contains_description(self, store):
        result = store.query_operation("wire")
        assert "Connect components" in result["hint"]

    def test_none_context_treated_as_empty(self, store):
        result = store.query_operation("wire", None)
        gotcha_ids = [g["id"] for g in result["gotchas"]]
        assert "g1" in gotcha_ids
        assert "g2" not in gotcha_ids


# -------------------------------------------------------------------------
# gh_query_operation facade
# -------------------------------------------------------------------------

class TestGHQueryOperationFacade:
    """Test the module-level facade function."""

    def test_delegates_to_store(self):
        mock_store = MagicMock()
        mock_store.query_operation.return_value = {"operation": "wire", "gotchas": []}
        with patch("rook.learning.gh_knowledge.get_gh_knowledge_store", return_value=mock_store):
            result = gh_query_operation("wire", {"in_group": True})
        mock_store.query_operation.assert_called_once_with("wire", {"in_group": True})
        assert result["operation"] == "wire"
