"""Importing ``rook.server`` must stay cheap.

Prime's MCP client (``rlm.mcp``) spawns ``python -m rook`` and gives it 20 s to
answer ``initialize``. On a cold machine the learning stack (DSPy, MABWiser and
its numpy/pandas/scikit-learn dependencies, networkx) took 35-50 s to import, so
RookChat's first tool call failed with a startup timeout. Those packages are now
imported on first use; this test pins that contract by importing the server in
a fresh interpreter and asserting none of them were loaded.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"

# Top-level package names that must not be imported by ``import rook.server``.
HEAVY_PACKAGES = (
    "dspy",
    "mabwiser",
    "networkx",
    "numpy",
    "pandas",
    "sklearn",
    "scipy",
    "litellm",
    "torch",
)

_PROBE = r"""
import json, sys
import rook.server
loaded = sorted({m.split('.')[0] for m in sys.modules} & set(sys.argv[1:]))
print(json.dumps(loaded))
"""


def test_importing_rook_server_does_not_load_the_learning_stack():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SRC)
    env.pop("ROOK_LOG_LEVEL", None)
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, *HEAVY_PACKAGES],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    loaded = json.loads(result.stdout.strip().splitlines()[-1])
    assert loaded == [], (
        "import rook.server pulled in heavy packages at import time: "
        f"{loaded}. Import them inside the functions that use them instead."
    )


def test_lazy_learner_proxy_serves_the_knowledge_store_without_building_the_learner(monkeypatch):
    import rook.server as server

    proxy = server.command_learner
    assert isinstance(proxy, server._LazyCommandLearner)
    # Earlier tests in the same session may have built the learner through a
    # learning operation; start from the fresh-import state (restored on exit).
    monkeypatch.setattr(proxy, "_learner", None)
    monkeypatch.setattr(proxy, "_knowledge_store", server._LazyCommandLearner._UNSET)
    assert proxy._learner is None
    store = proxy.knowledge_store
    assert store is proxy.knowledge_store
    assert proxy._learner is None, "knowledge_store access must not construct the learner"


_FIRST_USE_PROBE = r"""
import importlib, json, sys
import rook.server as server
report = {"dspy_loaded_at_import": "dspy" in sys.modules}   # measured BEFORE dspy_config is imported
import rook.learning.dspy_config as dspy_config             # (this import loads dspy; the recorder below still sees first use)
calls = []
def recording_configure(*args, **kwargs):
    calls.append("configure_dspy")
dspy_config.configure_dspy = recording_configure     # what ensure_configured() calls
report["configured_before_first_use"] = server._dspy_configured
server.command_learner.knowledge_store              # cheap path: must NOT configure or build
report["calls_after_knowledge_store"] = list(calls)
report["learner_built_after_knowledge_store"] = server.command_learner._learner is not None
# An INDIRECT first use: gh_extract_recipe imports recipe_extraction, which imports
# recipe_classification (runs an LM). No server call site is involved.
importlib.import_module("rook.learning.recipe_extraction")
report["calls_after_indirect_first_use"] = list(calls)
# More indirect chains reached by many tools: pattern_store -> pattern_evolution -> dspy_modules,
# the command tiering system, the GH consolidator. None may reconfigure.
importlib.import_module("rook.learning.pattern_store")
importlib.import_module("rook.learning.command_consolidator")
importlib.import_module("rook.learning.gh_consolidator")
server.command_learner.select_command               # builds the learner (imports command_learner)
report["calls_after_all_paths"] = list(calls)
report["helper_reports_configured"] = server._configure_dspy_if_available()
report["learner_built"] = server.command_learner._learner is not None
print(json.dumps(report))
"""


def test_first_learning_use_configures_dspy_in_a_fresh_process():
    """DSPy used to be configured at server startup. Deferring the learning
    stack must not lose that: the first import of ANY module that runs an LM,
    however indirect the path, configures DSPy exactly once, while the cheap
    knowledge-store path stays free of it."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SRC)
    result = subprocess.run(
        [sys.executable, "-c", _FIRST_USE_PROBE],
        capture_output=True, text=True, env=env, timeout=300, check=False,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["dspy_loaded_at_import"] is False
    assert report["configured_before_first_use"] is None
    assert report["calls_after_knowledge_store"] == []
    assert report["learner_built_after_knowledge_store"] is False
    assert report["calls_after_indirect_first_use"] == ["configure_dspy"]
    assert report["calls_after_all_paths"] == ["configure_dspy"]
    assert report["helper_reports_configured"] is True
    assert report["learner_built"] is True


_EXPLICIT_CONFIG_PROBE = r"""
import json, sys
import rook.server as server                      # lazy: no dspy yet
import dspy
import rook.learning.dspy_config as dspy_config
calls = []
real_configure = dspy_config.configure_dspy
def recording_configure(*args, **kwargs):
    calls.append("configure_dspy")
    return real_configure(*args, **kwargs)
dspy_config.configure_dspy = recording_configure
# The host (or a test) configures an explicit model directly, bypassing configure_dspy.
explicit = dspy.LM("openai/explicit-model-for-test", api_key="not-a-real-key")
dspy.configure(lm=explicit)
import rook.learning.recipe_classification         # first LM-running import: crosses the boundary
server.command_learner.select_command              # and the learner
lm = dspy.settings.lm
print(json.dumps({"same_object": lm is explicit, "model": getattr(lm, "model", None),
                  "configure_calls": calls, "helper": server._configure_dspy_if_available()}))
"""


def test_learning_boundary_preserves_an_explicitly_configured_model():
    """Review finding: the boundary must not replace a model the host configured
    directly through dspy.configure(lm=...) with the profile default. main
    preserved it (startup ran first); the lazy boundary must too."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SRC)
    result = subprocess.run(
        [sys.executable, "-c", _EXPLICIT_CONFIG_PROBE],
        capture_output=True, text=True, env=env, timeout=300, check=False,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["same_object"] is True, report
    assert report["model"] == "openai/explicit-model-for-test"
    assert report["configure_calls"] == []
    assert report["helper"] is True


# Modules that import dspy at module level but do not run an LM program themselves,
# or that guard every LM use with their own is_configured()/configure_dspy() call.
_BOUNDARY_EXEMPT = {"dspy_config.py", "dspy_signatures.py", "hybrid_investigator.py", "intent_planner.py"}


def test_every_lm_running_module_crosses_the_learning_boundary_at_import():
    """No call-site list: any module under rook.learning that imports dspy at
    module level must call ensure_configured() at import (or be exempt above),
    so indirect chains such as gh_extract_recipe -> recipe_extraction ->
    recipe_classification, or pattern_store -> pattern_evolution -> dspy_modules,
    always find DSPy configured."""
    learning = _SRC / "rook" / "learning"
    offenders = []
    for path in sorted(learning.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        imports_dspy = any(line.strip() in ("import dspy", "from dspy import *") or line.startswith("import dspy")
                           or line.startswith("from dspy ") or line.strip().startswith("import dspy")
                           for line in text.splitlines())
        if not imports_dspy or path.name in _BOUNDARY_EXEMPT:
            continue
        if "_ensure_dspy_configured()" not in text and "ensure_configured()" not in text:
            offenders.append(path.name)
    assert offenders == [], f"modules import dspy without crossing the learning boundary: {offenders}"


def test_lazy_learner_proxy_accepts_store_assignment_like_the_real_learner(monkeypatch):
    # Tests (e.g. test_server_execute_safety) replace command_learner.knowledge_store
    # via monkeypatch; the proxy must accept that, and undo cleanly, without
    # building the learner.
    import rook.server as server

    proxy = server.command_learner
    original = proxy.knowledge_store
    monkeypatch.setattr(proxy, "knowledge_store", None)
    assert proxy.knowledge_store is None
    assert proxy._learner is None
    monkeypatch.undo()
    assert proxy.knowledge_store is original
