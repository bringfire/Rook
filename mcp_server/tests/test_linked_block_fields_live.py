"""Live-Rhino verification + observation for the P7 linked-block substrate.

Held for Rhino: requires a running Rhino with a freshly-built + deployed
RookNative (the DecorateLinkedBlockFields fields). Skips cleanly when Rhino
is unreachable (fresh_document), so an absent toolchain is a graceful skip,
never a fake pass — spec §6 honesty discipline.

Run (from repo root, with a throwaway Rhino session):
    mcp_server\\.venv\\Scripts\\python.exe -m pytest -m requires_rhino ^
        mcp_server/tests/test_linked_block_fields_live.py -s
IMPORTANT: replaces the active Rhino document; use a throwaway session.
"""
from __future__ import annotations

import os
import tempfile

import pytest

from rook.server import _mcp_tool_executor

from .conftest import fresh_document  # noqa: F401 — fixture used by name

pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


def _tmp(tag: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"rook_p7lb_{os.getpid()}_{tag}.3dm")


async def _save_one_box_source(src_path: str) -> None:
    """Save a single-box document to src_path to serve as a linked source."""
    await _mcp_tool_executor(
        "rhino_create",
        {"type": "BOX", "corner1": [0, 0, 0], "corner2": [1, 1, 1], "name": "srcbox"},
    )
    save = await _mcp_tool_executor("rhino_document_ops", {"action": "save", "path": src_path})
    assert save.get("success") is not False, f"save source failed: {save!r}"


def _find_block(blocks: list, name: str) -> dict:
    for b in blocks:
        if isinstance(b, dict) and b.get("name") == name:
            return b
    raise AssertionError(f"{name!r} not in /blocks: {[b.get('name') for b in blocks]}")


async def test_blocks_and_info_expose_linked_fields(fresh_document):
    src = _tmp("src")
    try:
        await _save_one_box_source(src)
        await _mcp_tool_executor("rhino_document_ops", {"action": "new"})

        link = await _mcp_tool_executor("rhino_block_link", {"path": src, "name": "lb_linked"})
        assert link.get("success") is not False, f"block_link failed: {link!r}"

        box = await _mcp_tool_executor(
            "rhino_create",
            {"type": "BOX", "corner1": [0, 0, 0], "corner2": [1, 1, 1], "name": "embbox"},
        )
        await _mcp_tool_executor(
            "rhino_block_create",
            {"name": "lb_embedded", "ids": [box["id"]], "basePoint": [0, 0, 0],
             "replaceWithInstance": True},
        )

        blocks = (await _mcp_tool_executor("rhino_blocks", {}))["blocks"]
        linked = _find_block(blocks, "lb_linked")
        embedded = _find_block(blocks, "lb_embedded")

        # Linked def: four fields present and consistent.
        assert linked["blockType"] in ("Linked", "EmbeddedAndLinked"), linked
        assert linked["isLinked"] is True, linked
        assert linked["sourcePath"], "linked sourcePath must be non-empty"
        assert linked["sourcePath"] == linked["sourceArchive"], linked

        # Embedded def: isLinked false, empty path aliases.
        assert embedded["blockType"] == "Embedded", embedded
        assert embedded["isLinked"] is False, embedded
        assert embedded["sourcePath"] == "", embedded
        assert embedded["sourceArchive"] == "", embedded

        # /block/info parity for the linked def (gains isLinked + sourcePath).
        info = await _mcp_tool_executor("rhino_block_info", {"name": "lb_linked"})
        assert info["isLinked"] is True, info
        assert info["sourcePath"] == info["sourceArchive"] and info["sourcePath"], info
        assert info["blockType"] == linked["blockType"], info

        # /block/info parity for the embedded def — both surfaces x both cases.
        einfo = await _mcp_tool_executor("rhino_block_info", {"name": "lb_embedded"})
        assert einfo["blockType"] == "Embedded", einfo
        assert einfo["isLinked"] is False, einfo
        assert einfo["sourcePath"] == "" and einfo["sourceArchive"] == "", einfo
    finally:
        try:
            os.remove(src)
        except OSError:
            pass


async def test_post_save_linked_path_form_observation(fresh_document, capsys):
    """OBSERVATION (spec §6): record what sourcePath returns after the HOST
    doc is saved + reopened. Lenient — the purpose is to record the form
    (absolute / relative / drive-rooted) for the executor's resolution rule.
    """
    src = _tmp("src2")
    host = _tmp("host2")
    try:
        await _save_one_box_source(src)
        await _mcp_tool_executor("rhino_document_ops", {"action": "new"})
        await _mcp_tool_executor("rhino_block_link", {"path": src, "name": "lb_obs"})

        save = await _mcp_tool_executor("rhino_document_ops", {"action": "save", "path": host})
        assert save.get("success") is not False, f"save host failed: {save!r}"
        opened = await _mcp_tool_executor("rhino_document_ops", {"action": "open", "path": host})
        assert opened.get("success") is not False, f"open host failed: {opened!r}"

        info = await _mcp_tool_executor("rhino_block_info", {"name": "lb_obs"})
        with capsys.disabled():
            print(
                f"\n[P7-LB OBSERVATION] post-save linked sourcePath = "
                f"{info.get('sourcePath')!r}  (host={host!r}, source={src!r})"
            )
        assert info.get("isLinked") is True, info
        assert info.get("sourcePath"), info
    finally:
        for p in (src, host):
            try:
                os.remove(p)
            except OSError:
                pass
