"""Source-level guards for the layer and object tool fixes.

The native plug-in only runs inside Rhino, so these tests pin the
behaviour-carrying lines of the C++ handlers and check that the Python tool
schemas agree with them. They run without Rhino.

The behavioural counterparts, which need a Rhino running a plug-in built from
this source, are in ``test_layer_object_tools_live.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
NATIVE = REPO_ROOT / "src" / "RookNative"
LAYER_OPS = NATIVE / "Handlers" / "LayerOpsHandler.cpp"
SELECTION = NATIVE / "Handlers" / "SelectionHandler.cpp"
OBJECTS = NATIVE / "Handlers" / "ObjectsHandler.cpp"
LAYER_HELPERS = NATIVE / "Infrastructure" / "LayerHelpers.cpp"
DOCUMENT_HELPERS = NATIVE / "Models" / "DocumentHelpers.h"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_function(source: str, signature: str) -> str:
    start = source.index(signature)
    body_start = source.index("{", start)
    depth = 0
    for index in range(body_start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"Could not extract function for {signature!r}")


async def _public_tools(monkeypatch) -> dict:
    from rook import server

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    return {tool.name: tool for tool in await server.list_tools()}


# --- Case-only layer rename ---------------------------------------------------
#
# Rhino resolves layer paths case-insensitively, so looking up the target of a
# case-only rename ("mullions" -> "MULLIONS") finds the layer being renamed.
# The collision check must compare layer identity, not path text.


def test_layer_lookup_helper_returns_index_of_live_layer():
    source = _read(LAYER_HELPERS)
    lookup = _extract_function(source, "int FindLayerIndexByFullPath")

    assert "FindLayerFromFullPathName" in lookup
    assert "IsDeleted()" in lookup
    assert "return -1;" in lookup

    exists = _extract_function(source, "bool LayerExistsByFullPath")
    assert "FindLayerIndexByFullPath(pDoc, fullPath) >= 0" in exists


@pytest.mark.parametrize(
    "signature",
    [
        # rhino_layer_set_properties and rhino_layer_set_properties_batch
        "LayerMutationResult ApplyLayerPropertiesMutation",
        # rhino_layer_rename
        "void HandleLayerRename",
    ],
)
def test_rename_collision_compares_layer_identity_not_path_text(signature):
    body = _extract_function(_read(LAYER_OPS), signature)

    assert "const int existingIdx = FindLayerIndexByFullPath(pDoc, targetFullPath);" in body
    assert "existingIdx >= 0 && existingIdx != idx" in body
    # The defect: a case-sensitive comparison of the two path strings.
    assert "targetFullPath != " not in body
