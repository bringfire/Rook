from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace
import pytest


class FakeLM:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def load_dspy_config(monkeypatch, tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "mcp_server" / "src" / "rook" / "learning" / "dspy_config.py"
    calls: list[dict] = []

    fake_dspy = SimpleNamespace(
        LM=FakeLM,
        configure=lambda **_kwargs: None,
        configure_cache=lambda **kwargs: calls.append(kwargs),
    )
    monkeypatch.setitem(sys.modules, "dspy", fake_dspy)
    monkeypatch.setenv("ROOK_MODE", "release")
    monkeypatch.setenv("ROOK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("DSPY_CACHEDIR", raising=False)

    rook_pkg = ModuleType("rook")
    rook_pkg.__path__ = []
    learning_pkg = ModuleType("rook.learning")
    learning_pkg.__path__ = []
    agent_pkg = ModuleType("rook.agent")
    agent_pkg.__path__ = []
    model_profiles = ModuleType("rook.agent.model_profiles")
    model_profiles.api_base_for_model = lambda _model, api_base: api_base
    monkeypatch.setitem(sys.modules, "rook", rook_pkg)
    monkeypatch.setitem(sys.modules, "rook.learning", learning_pkg)
    monkeypatch.setitem(sys.modules, "rook.agent", agent_pkg)
    monkeypatch.setitem(sys.modules, "rook.agent.model_profiles", model_profiles)

    spec = importlib.util.spec_from_file_location("rook.learning.dspy_config", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, calls


def test_dspy_cache_is_reconfigured_with_restricted_pickle(monkeypatch, tmp_path: Path):
    _module, calls = load_dspy_config(monkeypatch, tmp_path)

    assert calls
    cache_config = calls[-1]
    assert cache_config["enable_disk_cache"] is True
    assert cache_config["enable_memory_cache"] is True
    assert cache_config["restrict_pickle"] is True
    assert cache_config["disk_cache_dir"].endswith("data/dspy-cache") or cache_config[
        "disk_cache_dir"
    ].endswith("data\\dspy-cache")


def test_configure_dspy_reapplies_secure_cache(monkeypatch, tmp_path: Path):
    module, calls = load_dspy_config(monkeypatch, tmp_path)

    calls.clear()
    module.configure_dspy(model="ollama_chat/qwen", api_base="http://127.0.0.1:11434")

    assert calls
    assert calls[-1]["restrict_pickle"] is True


def test_release_mode_fails_if_dspy_lacks_restricted_pickle(monkeypatch, tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "mcp_server" / "src" / "rook" / "learning" / "dspy_config.py"

    def reject_restrict_pickle(**kwargs):
        if "restrict_pickle" in kwargs:
            raise TypeError("unexpected keyword argument 'restrict_pickle'")

    fake_dspy = SimpleNamespace(
        LM=FakeLM,
        configure=lambda **_kwargs: None,
        configure_cache=reject_restrict_pickle,
    )
    monkeypatch.setitem(sys.modules, "dspy", fake_dspy)
    monkeypatch.setenv("ROOK_MODE", "release")
    monkeypatch.setenv("ROOK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("DSPY_CACHEDIR", raising=False)

    spec = importlib.util.spec_from_file_location("rook.learning.dspy_config", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    with pytest.raises(RuntimeError, match="restrict_pickle"):
        spec.loader.exec_module(module)
