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


def test_lazy_learner_proxy_serves_the_knowledge_store_without_building_the_learner():
    import rook.server as server

    proxy = server.command_learner
    assert isinstance(proxy, server._LazyCommandLearner)
    assert proxy._learner is None
    store = proxy.knowledge_store
    assert store is proxy.knowledge_store
    assert proxy._learner is None, "knowledge_store access must not construct the learner"


_FIRST_USE_PROBE = r"""
import json, sys
import rook.server as server
report = {"dspy_loaded_at_import": "dspy" in sys.modules}
calls = []
def recording_configure(*args, **kwargs):
    calls.append("configure_dspy")
server.configure_dspy = recording_configure          # what _configure_dspy_if_available calls
report["configured_before_first_use"] = server._dspy_configured
server.command_learner.knowledge_store              # cheap path: must NOT configure or build
report["calls_after_knowledge_store"] = list(calls)
report["learner_built_after_knowledge_store"] = server.command_learner._learner is not None
server.command_learner.select_command               # first learning use: builds the learner
report["calls_after_first_learning_use"] = list(calls)
report["configured_after_first_use"] = server._dspy_configured
report["learner_built"] = server.command_learner._learner is not None
server.command_learner.consolidate_command          # second use: no reconfiguration
report["calls_after_second_use"] = list(calls)
print(json.dumps(report))
"""


def test_first_learning_use_configures_dspy_in_a_fresh_process():
    """DSPy used to be configured at server startup. Deferring it must not lose it:
    the first use of the command learner (the learning boundary) has to configure
    DSPy exactly once, before the learner is built, while the cheap knowledge-store
    path stays free of it."""
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
    assert report["calls_after_first_learning_use"] == ["configure_dspy"]
    assert report["configured_after_first_use"] is True
    assert report["learner_built"] is True
    assert report["calls_after_second_use"] == ["configure_dspy"]


def test_every_dspy_consuming_tool_path_configures_dspy_first():
    """Tool branches that import DSPy-backed modules without their own
    is_configured()/configure_dspy() guard must cross the learning boundary."""
    source = (_SRC / "rook" / "server.py").read_text(encoding="utf-8")
    for case_label, dspy_import in (
        ('case "gh_learn_directory":', "from .learning.recipe_classification import classify_recipe"),
        ('case "gh_add_pattern":', "from rook.learning.dspy_modules import PatternMetadataExtractor"),
        ('case "gh_consolidate":', "from rook.learning.gh_consolidator import GHConsolidator"),
    ):
        start = source.index(case_label)
        use = source.index(dspy_import, start)
        block = source[start:use]
        assert "_configure_dspy_if_available()" in block, f"{case_label} imports {dspy_import} before configuring DSPy"


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
