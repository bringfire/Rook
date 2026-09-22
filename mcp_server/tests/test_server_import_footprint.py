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
