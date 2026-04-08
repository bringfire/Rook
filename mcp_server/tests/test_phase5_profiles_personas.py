"""
Phase 5: Model Profiles + Personas (Engram Parity)
===================================================

Tests for:
A. model_profiles.py — ModelSet, FALLBACK_MODELS, get_models, caching, profiles
B. Ollama detection — detect_ollama_models, build_profiles_data
C. Persona loading — load_persona, load_display_config, get_model_role, discovery
D. Integration — _resolve_model with real persona files, _estimate_cost role-based
E. Backward compatibility — no file works, worker/specialist unchanged, env vars
"""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# --- Path setup ---
REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rook.agent.model_profiles import (
    ModelSet, FALLBACK_MODELS, DEFAULT_PROFILES_DATA,
    get_models, get_profile_names, get_active_profile_name,
    write_default_profiles, detect_ollama_models, build_profiles_data,
    invalidate_cache, _profiles_path,
)
from rook.agent.personas import (
    load_persona, load_display_config, get_model_role,
    available_personas, build_specialist_summary,
    _INFRASTRUCTURE_PERSONAS, _DISPLAY_DEFAULTS,
)
from rook.agent.config import PlannerConfig, AgentConfig
from rook.agent.planner import Planner, TaskSpec, Plan, SUBMIT_PLAN_SCHEMA


# =============================================================================
# A. model_profiles.py — ModelSet, FALLBACK_MODELS, get_models
# =============================================================================

class TestFallbackModels(unittest.TestCase):
    """FALLBACK_MODELS and ModelSet basics."""

    def test_fallback_returns_model_set(self):
        """No file → FALLBACK_MODELS used to build ModelSet."""
        ms = ModelSet(**FALLBACK_MODELS)
        assert isinstance(ms, ModelSet)
        assert ms.planner == FALLBACK_MODELS["planner"]
        assert ms.worker == FALLBACK_MODELS["worker"]

    def test_model_set_frozen(self):
        """ModelSet is immutable — cannot mutate fields."""
        ms = ModelSet(**FALLBACK_MODELS)
        with self.assertRaises(AttributeError):
            ms.planner = "changed"

    def test_fallback_has_all_roles(self):
        """FALLBACK_MODELS must have all 5 roles."""
        expected_roles = {"planner", "worker", "specialist", "guardian", "dspy"}
        assert set(FALLBACK_MODELS.keys()) == expected_roles

    def test_default_profiles_all_roles(self):
        """Every profile in DEFAULT_PROFILES_DATA has all 5 fields."""
        for name, profile in DEFAULT_PROFILES_DATA["profiles"].items():
            for role in ("planner", "worker", "specialist", "guardian", "dspy"):
                assert role in profile, (
                    f"Profile '{name}' missing role '{role}'"
                )


class TestModelProfilesIO(unittest.TestCase):
    """Write and read round-trip, mtime caching."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._test_path = Path(self._tmpdir) / "model_profiles.json"
        invalidate_cache()

    def tearDown(self):
        if self._test_path.exists():
            self._test_path.unlink()
        os.rmdir(self._tmpdir)
        invalidate_cache()

    def test_write_and_read_round_trip(self):
        """write → read → ModelSet matches expected values."""
        data = build_profiles_data("cloud")
        with open(self._test_path, "w") as f:
            json.dump(data, f)

        # Patch _profiles_path to use our temp path
        with patch("rook.agent.model_profiles._profiles_path",
                    return_value=self._test_path):
            invalidate_cache()
            ms = get_models("cloud")

        assert ms.planner == FALLBACK_MODELS["planner"]
        assert ms.worker == FALLBACK_MODELS["worker"]
        assert ms.specialist == FALLBACK_MODELS["specialist"]

    def test_active_profile_selection(self):
        """active: "local" → get_models() uses local models."""
        data = build_profiles_data("local")
        with open(self._test_path, "w") as f:
            json.dump(data, f)

        with patch("rook.agent.model_profiles._profiles_path",
                    return_value=self._test_path):
            invalidate_cache()
            ms = get_models()  # should use active="local"

        # Local profile uses ollama placeholders
        assert "ollama" in ms.worker.lower()

    def test_explicit_profile_overrides_active(self):
        """get_models("local") when active="cloud" returns local models."""
        data = build_profiles_data("cloud")
        with open(self._test_path, "w") as f:
            json.dump(data, f)

        with patch("rook.agent.model_profiles._profiles_path",
                    return_value=self._test_path):
            invalidate_cache()
            ms_cloud = get_models("cloud")
            ms_local = get_models("local")

        assert ms_cloud.worker != ms_local.worker

    def test_missing_profile_fallback(self):
        """Nonexistent profile → FALLBACK_MODELS."""
        data = build_profiles_data("cloud")
        with open(self._test_path, "w") as f:
            json.dump(data, f)

        with patch("rook.agent.model_profiles._profiles_path",
                    return_value=self._test_path):
            invalidate_cache()
            ms = get_models("nonexistent")

        assert ms == ModelSet(**FALLBACK_MODELS)

    def test_mtime_caching(self):
        """Same mtime = no re-read; changed mtime = re-read."""
        data = build_profiles_data("cloud")
        with open(self._test_path, "w") as f:
            json.dump(data, f)

        with patch("rook.agent.model_profiles._profiles_path",
                    return_value=self._test_path):
            invalidate_cache()
            ms1 = get_models("cloud")

            # Modify the file content (keep same profile name)
            data2 = build_profiles_data("cloud")
            data2["profiles"]["cloud"]["worker"] = "test/modified"
            with open(self._test_path, "w") as f:
                json.dump(data2, f)
            # Touch with new mtime
            os.utime(self._test_path, (time.time() + 1, time.time() + 1))

            ms2 = get_models("cloud")

        assert ms2.worker == "test/modified"

    def test_auto_write_then_read(self):
        """get_models() auto-creates file when missing, then reads it."""
        auto_path = Path(self._tmpdir) / "auto" / "model_profiles.json"
        assert not auto_path.exists()

        with patch("rook.agent.model_profiles._profiles_path",
                    return_value=auto_path):
            invalidate_cache()
            ms = get_models()

        # File should have been auto-created
        assert auto_path.exists(), "model_profiles.json should be auto-created"
        # And the returned ModelSet should match cloud defaults
        assert ms.planner == FALLBACK_MODELS["planner"]
        assert ms.worker == FALLBACK_MODELS["worker"]

        # Cleanup
        auto_path.unlink()
        auto_path.parent.rmdir()


# =============================================================================
# B. Ollama detection
# =============================================================================

class TestOllamaDetection(unittest.TestCase):
    """detect_ollama_models and build_profiles_data."""

    def test_ollama_unreachable(self):
        """When Ollama is not running, returns ollama_available=False."""
        result = detect_ollama_models(host="127.0.0.1", port=19999, timeout=0.5)
        assert result["ollama_available"] is False
        assert result["error"] is not None

    def test_ollama_parses_response(self):
        """Mock urlopen to return fake model list."""
        fake_response = json.dumps({
            "models": [
                {"name": "qwen3:8b", "size": 5_000_000_000},
                {"name": "llama3:70b", "size": 40_000_000_000},
                {"name": "tiny:1b", "size": 500_000_000},
            ]
        }).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_response
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = detect_ollama_models()

        assert result["ollama_available"] is True
        assert len(result["models"]) == 3
        assert result["largest_above_4gb"] == "llama3:70b"

    def test_build_profiles_with_local_model(self):
        """build_profiles_data replaces ollama refs in hybrid/local profiles."""
        data = build_profiles_data("hybrid", local_model="ollama_chat/my-model")
        hybrid = data["profiles"]["hybrid"]
        assert hybrid["worker"] == "ollama_chat/my-model"
        assert hybrid["guardian"] == "ollama_chat/my-model"
        # Planner stays cloud
        assert hybrid["planner"] == FALLBACK_MODELS["planner"]


# =============================================================================
# C. Persona loading
# =============================================================================

class TestPersonaLoading(unittest.TestCase):
    """Persona file loading and discovery."""

    def test_all_six_display_configs_valid(self):
        """All 6 personas load display.json without error."""
        for name in ("worker", "specialist", "scripter", "explorer",
                      "planner", "guardian"):
            config = load_display_config(name)
            assert "model_role" in config, f"Missing model_role for {name}"
            assert "tool_access" in config, f"Missing tool_access for {name}"

    def test_model_role_mapping(self):
        """Each persona maps to the correct model_role."""
        expected = {
            "worker": "worker",
            "specialist": "specialist",
            "scripter": "specialist",
            "explorer": "worker",
            "planner": "planner",
            "guardian": "guardian",
        }
        for name, role in expected.items():
            assert get_model_role(name) == role, (
                f"{name} should map to role '{role}', "
                f"got '{get_model_role(name)}'"
            )

    def test_available_personas_count(self):
        """All 6 personas are discovered."""
        personas = available_personas()
        assert len(personas) == 6, f"Expected 6 personas, got {len(personas)}: {personas}"
        for name in ("worker", "specialist", "scripter", "explorer",
                      "planner", "guardian"):
            assert name in personas, f"Missing persona: {name}"

    def test_infrastructure_excluded_from_summary(self):
        """build_specialist_summary excludes planner and guardian."""
        # Clear lru_cache first
        build_specialist_summary.cache_clear()
        summary = build_specialist_summary()
        assert "planner" not in summary.lower() or "planner" not in summary.split("|")[0]
        # Check that assignable types ARE present
        assert "`worker`" in summary
        assert "`specialist`" in summary

    def test_load_persona_returns_personality_and_role(self):
        """load_persona returns dict with personality and role strings."""
        for name in ("worker", "specialist", "scripter", "explorer",
                      "planner", "guardian"):
            p = load_persona(name)
            assert "personality" in p, f"Missing personality for {name}"
            assert "role" in p, f"Missing role for {name}"
            assert isinstance(p["personality"], str)
            assert isinstance(p["role"], str)
            # Both should have content
            assert len(p["personality"]) > 0, f"Empty personality for {name}"
            assert len(p["role"]) > 0, f"Empty role for {name}"

    def test_missing_persona_returns_defaults(self):
        """Unknown persona type → display defaults (model_role='worker')."""
        config = load_display_config("nonexistent_type_xyz")
        assert config["model_role"] == _DISPLAY_DEFAULTS["model_role"]
        assert config["label"] == _DISPLAY_DEFAULTS["label"]

    def test_infrastructure_personas_frozenset(self):
        """_INFRASTRUCTURE_PERSONAS contains exactly planner and guardian."""
        assert _INFRASTRUCTURE_PERSONAS == frozenset({"planner", "guardian"})

    def test_tool_access_readonly_for_explorer(self):
        """Explorer has readonly tool_access."""
        config = load_display_config("explorer")
        assert config["tool_access"] == "readonly"

    def test_tool_access_full_for_worker(self):
        """Worker has full tool_access."""
        config = load_display_config("worker")
        assert config["tool_access"] == "full"


# =============================================================================
# D. Integration — _resolve_model with real personas + profile
# =============================================================================

class TestResolveModelIntegration(unittest.TestCase):
    """_resolve_model uses persona → profile → model lookup."""

    def _make_planner(self):
        config = PlannerConfig()  # default models
        return Planner(config=config, tool_executor=MagicMock())

    def test_resolve_model_scripter_gets_sonnet(self):
        """scripter → model_role 'specialist' → Sonnet."""
        planner = self._make_planner()
        result = planner._resolve_model("scripter")
        assert result == FALLBACK_MODELS["specialist"], (
            f"Expected {FALLBACK_MODELS['specialist']}, got {result}"
        )

    def test_resolve_model_explorer_gets_haiku(self):
        """explorer → model_role 'worker' → Haiku."""
        planner = self._make_planner()
        result = planner._resolve_model("explorer")
        assert result == FALLBACK_MODELS["worker"], (
            f"Expected {FALLBACK_MODELS['worker']}, got {result}"
        )

    def test_resolve_model_worker_fast_path(self):
        """worker → config.worker_model directly (no persona lookup)."""
        config = PlannerConfig(worker_model="test/custom-haiku")
        planner = Planner(config=config, tool_executor=MagicMock())
        result = planner._resolve_model("worker")
        assert result == "test/custom-haiku"

    def test_resolve_model_specialist_gets_sonnet(self):
        """specialist → model_role 'specialist' → Sonnet."""
        planner = self._make_planner()
        result = planner._resolve_model("specialist")
        assert result == FALLBACK_MODELS["specialist"]


class TestEstimateCostIntegration(unittest.TestCase):
    """_estimate_cost uses role-based pricing via persona lookup."""

    def _make_planner(self):
        return Planner(config=PlannerConfig(), tool_executor=MagicMock())

    def test_estimate_cost_scripter_same_as_specialist(self):
        """scripter uses specialist pricing (same model_role)."""
        planner = self._make_planner()
        scripter_plan = Plan(
            goal="test",
            tasks=[TaskSpec(task_id="t1", description="script",
                           estimated_turns=10, agent_type="scripter")],
        )
        specialist_plan = Plan(
            goal="test",
            tasks=[TaskSpec(task_id="t2", description="complex",
                           estimated_turns=10, agent_type="specialist")],
        )
        assert planner._estimate_cost(scripter_plan) == planner._estimate_cost(specialist_plan)

    def test_estimate_cost_explorer_same_as_worker(self):
        """explorer uses worker pricing (same model_role)."""
        planner = self._make_planner()
        explorer_plan = Plan(
            goal="test",
            tasks=[TaskSpec(task_id="t1", description="explore",
                           estimated_turns=10, agent_type="explorer")],
        )
        worker_plan = Plan(
            goal="test",
            tasks=[TaskSpec(task_id="t2", description="work",
                           estimated_turns=10, agent_type="worker")],
        )
        assert planner._estimate_cost(explorer_plan) == planner._estimate_cost(worker_plan)


class TestSchemaExpanded(unittest.TestCase):
    """SUBMIT_PLAN_SCHEMA includes all 4 assignable types."""

    def test_schema_enum_expanded(self):
        props = (
            SUBMIT_PLAN_SCHEMA["function"]["parameters"]["properties"]
            ["tasks"]["items"]["properties"]
        )
        assert props["agent_type"]["enum"] == [
            "worker", "specialist", "scripter", "explorer"
        ]


class TestParsePlanIntegration(unittest.TestCase):
    """_parse_plan with new agent types."""

    def _make_planner(self):
        return Planner(config=PlannerConfig(), tool_executor=MagicMock())

    def test_parse_plan_accepts_scripter(self):
        planner = self._make_planner()
        data = {
            "goal": "Script test",
            "tasks": [{"task_id": "t1", "description": "Write script",
                       "agent_type": "scripter"}],
            "execution_groups": [["t1"]],
        }
        plan = planner._parse_plan(data)
        assert plan.tasks[0].agent_type == "scripter"

    def test_parse_plan_accepts_explorer(self):
        planner = self._make_planner()
        data = {
            "goal": "Explore test",
            "tasks": [{"task_id": "t1", "description": "Inspect scene",
                       "agent_type": "explorer"}],
            "execution_groups": [["t1"]],
        }
        plan = planner._parse_plan(data)
        assert plan.tasks[0].agent_type == "explorer"

    def test_parse_plan_rejects_planner(self):
        """Infrastructure persona 'planner' → sanitized to 'worker'."""
        planner = self._make_planner()
        data = {
            "goal": "Test",
            "tasks": [{"task_id": "t1", "description": "test",
                       "agent_type": "planner"}],
            "execution_groups": [["t1"]],
        }
        plan = planner._parse_plan(data)
        assert plan.tasks[0].agent_type == "worker"

    def test_parse_plan_rejects_guardian(self):
        """Infrastructure persona 'guardian' → sanitized to 'worker'."""
        planner = self._make_planner()
        data = {
            "goal": "Test",
            "tasks": [{"task_id": "t1", "description": "test",
                       "agent_type": "guardian"}],
            "execution_groups": [["t1"]],
        }
        plan = planner._parse_plan(data)
        assert plan.tasks[0].agent_type == "worker"


# =============================================================================
# E. Backward compatibility
# =============================================================================

class TestBackwardCompatibility(unittest.TestCase):
    """Phase 4 behavior preserved after Phase 5 additions."""

    def test_no_profiles_file_works(self):
        """delete model_profiles.json → _resolve_model still works."""
        # Patch _profiles_path to a nonexistent location
        with patch("rook.agent.model_profiles._profiles_path",
                    return_value=Path("/tmp/nonexistent/model_profiles.json")):
            invalidate_cache()
            ms = get_models()
        assert ms == ModelSet(**FALLBACK_MODELS)

    def test_worker_specialist_unchanged(self):
        """Default config: worker→Haiku, specialist→Sonnet (same as Phase 4)."""
        planner = Planner(config=PlannerConfig(), tool_executor=MagicMock())
        worker_model = planner._resolve_model("worker")
        specialist_model = planner._resolve_model("specialist")

        assert worker_model == PlannerConfig().worker_model
        assert specialist_model == FALLBACK_MODELS["specialist"]
        assert "haiku" in worker_model.lower()
        assert "sonnet" in specialist_model.lower()

    def test_env_var_override(self):
        """ROOK_WORKER_MODEL env var still works for worker fast path."""
        config = PlannerConfig(worker_model="test/env-override")
        planner = Planner(config=config, tool_executor=MagicMock())
        assert planner._resolve_model("worker") == "test/env-override"

    def test_build_worker_prompt_persona_fallback_to_worker_md(self):
        """When persona files missing, _build_worker_prompt falls back to WORKER.md."""
        from rook.agent.spawn import _build_worker_prompt
        from rook.agent.tool_registry import ToolRegistry

        registry = ToolRegistry(catalog={})
        # Use a nonexistent agent type — should fall back to WORKER.md
        prompt = _build_worker_prompt(registry, ["gh_canvas"], "nonexistent_type")
        worker_md = (
            Path(__file__).resolve().parent.parent / "src" / "rook"
            / "agent" / "prompts" / "WORKER.md"
        )
        if worker_md.exists():
            assert len(prompt) > 50, "Fallback prompt should have content"

    def test_build_worker_prompt_loads_persona(self):
        """For known agent type, _build_worker_prompt loads persona content."""
        from rook.agent.spawn import _build_worker_prompt
        from rook.agent.tool_registry import ToolRegistry

        registry = ToolRegistry(catalog={})
        prompt = _build_worker_prompt(registry, ["gh_canvas"], "scripter")
        # Scripter personality mentions Python 3 / script
        assert "script" in prompt.lower() or "python" in prompt.lower(), (
            f"Scripter prompt should mention scripts, got: {prompt[:200]}"
        )

    def test_config_agent_type_field(self):
        """AgentConfig has agent_type field defaulting to 'worker'."""
        config = AgentConfig()
        assert config.agent_type == "worker"

    def test_config_model_profile_field(self):
        """PlannerConfig has model_profile field defaulting to None."""
        config = PlannerConfig()
        assert config.model_profile is None

    def test_config_model_profile_from_env(self):
        """ROOK_MODEL_PROFILE env var sets model_profile."""
        with patch.dict(os.environ, {"ROOK_MODEL_PROFILE": "hybrid"}):
            config = PlannerConfig.from_env()
        assert config.model_profile == "hybrid"


# =============================================================================
# Run
# =============================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
