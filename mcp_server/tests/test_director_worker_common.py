from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from rook import director_worker_common as dwc

pytestmark = pytest.mark.asyncio

LIVE_DOC_PATH = "C:/work/live_project.3dm"


class CustomWorkerError(dwc.DirectorWorkerError):
    pass


def make_package_files(tmp_path: Path) -> Path:
    root = tmp_path / "take1"
    root.mkdir()
    (root / "scene.3dm").write_bytes(b"scene")
    (root / "prepared.3dm").write_bytes(b"prepared")
    return root


def make_fake_native(
    *,
    initial_path: str = LIVE_DOC_PATH,
    modified: bool = False,
    same_path_already_open: bool = False,
    reported_path_after_open: str | None = None,
):
    state = {
        "current_path": initial_path,
        "modified": modified,
        "calls": [],
        "opens": [],
    }

    async def fake(endpoint: str, method: str, data: dict | None = None, *,
                   port: int | None = None) -> dict:
        state["calls"].append((endpoint, method, data))
        if endpoint == "/document" and method == "GET":
            return {"success": True, "data": {
                "path": reported_path_after_open or state["current_path"],
                "modified": state["modified"],
                "objectCount": 10,
            }}
        if endpoint == "/document/open" and method == "POST":
            path = data["path"]
            state["opens"].append(path)
            if (same_path_already_open
                    and dwc.norm_path(path) == dwc.norm_path(state["current_path"])):
                return {"success": True, "data": {
                    "path": path,
                    "alreadyOpen": True,
                }}
            state["current_path"] = path
            state["modified"] = False
            return {"success": True, "data": {"path": path}}
        raise AssertionError(f"unexpected native call: {endpoint} {method}")

    fake.state = state
    return fake


async def expect_error(coro, code: str, error_cls=dwc.DirectorWorkerError):
    with pytest.raises(error_cls) as exc_info:
        await coro
    assert exc_info.value.code == code, exc_info.value
    return exc_info.value


async def test_norm_path_case_and_slashes():
    assert dwc.norm_path("C:\\A\\b.3dm") == dwc.norm_path("c:/a/B.3DM")
    assert dwc.norm_path("C:/A/B.3DM").endswith("c:/a/b.3dm")


async def test_dirty_nonpackage_doc_blocks(tmp_path):
    root = make_package_files(tmp_path)
    fake = make_fake_native(modified=True)
    await expect_error(
        dwc.open_package_document(
            fake, root, root / "prepared.3dm", port=None,
            error_cls=dwc.DirectorWorkerError, mode="require_fresh"),
        "document_not_saved")
    assert fake.state["opens"] == []


async def test_dirty_scene_doc_is_discardable(tmp_path):
    root = make_package_files(tmp_path)
    fake = make_fake_native(initial_path=str(root / "scene.3dm"), modified=True)
    await dwc.open_package_document(
        fake, root, root / "prepared.3dm", port=None,
        error_cls=dwc.DirectorWorkerError, mode="require_fresh")
    assert fake.state["opens"] == [str(root / "prepared.3dm")]


async def test_dirty_prepared_doc_is_discardable_on_reset(tmp_path):
    root = make_package_files(tmp_path)
    prepared = root / "prepared.3dm"
    fake = make_fake_native(
        initial_path=str(prepared), modified=True, same_path_already_open=True)
    await dwc.open_package_document(
        fake, root, prepared, port=None,
        error_cls=dwc.DirectorWorkerError, mode="require_fresh")
    assert fake.state["opens"] == [
        str(prepared), str(root / "scene.3dm"), str(prepared)]


async def test_fail_closed_mode_rejects_already_open(tmp_path):
    root = make_package_files(tmp_path)
    scene = root / "scene.3dm"
    fake = make_fake_native(
        initial_path=str(scene), same_path_already_open=True)
    await expect_error(
        dwc.open_package_document(
            fake, root, scene, port=None,
            error_cls=dwc.DirectorWorkerError, mode="fail_closed"),
        "take_copy_not_pristine")
    assert fake.state["opens"] == [str(scene)]


async def test_require_fresh_double_hops_on_already_open(tmp_path):
    root = make_package_files(tmp_path)
    prepared = root / "prepared.3dm"
    fake = make_fake_native(
        initial_path=str(prepared), same_path_already_open=True)
    await dwc.open_package_document(
        fake, root, prepared, port=None,
        error_cls=dwc.DirectorWorkerError, mode="require_fresh")
    assert fake.state["opens"] == [
        str(prepared), str(root / "scene.3dm"), str(prepared)]


async def test_double_hop_via_file_missing_fails(tmp_path):
    root = make_package_files(tmp_path)
    (root / "scene.3dm").unlink()
    prepared = root / "prepared.3dm"
    fake = make_fake_native(
        initial_path=str(prepared), same_path_already_open=True)
    await expect_error(
        dwc.open_package_document(
            fake, root, prepared, port=None,
            error_cls=dwc.DirectorWorkerError, mode="require_fresh"),
        "take_copy_not_pristine")


async def test_double_hop_still_wrong_path_fails(tmp_path):
    root = make_package_files(tmp_path)
    prepared = root / "prepared.3dm"
    fake = make_fake_native(
        initial_path=str(prepared), same_path_already_open=True,
        reported_path_after_open="C:/wrong/active.3dm")
    await expect_error(
        dwc.open_package_document(
            fake, root, prepared, port=None,
            error_cls=dwc.DirectorWorkerError, mode="require_fresh"),
        "wrong_document")


async def test_wrong_path_after_plain_open_fails(tmp_path):
    root = make_package_files(tmp_path)
    fake = make_fake_native(reported_path_after_open="C:/wrong/active.3dm")
    await expect_error(
        dwc.open_package_document(
            fake, root, root / "prepared.3dm", port=None,
            error_cls=dwc.DirectorWorkerError, mode="require_fresh"),
        "wrong_document")


async def test_enforce_save_copy_evidence_passes_and_fails():
    evidence: dict[str, Any] = {
        "path_before": "C:/model/source.3dm",
        "path_after": "C:/model/source.3dm",
        "title_before": "source.3dm",
        "title_after": "source.3dm",
        "modified_before": False,
        "modified_after": False,
        "save_small_used": False,
    }
    dwc.enforce_save_copy_evidence(evidence, dwc.DirectorWorkerError)

    missing = dict(evidence)
    del missing["title_after"]
    with pytest.raises(dwc.DirectorWorkerError) as missing_exc:
        dwc.enforce_save_copy_evidence(missing, dwc.DirectorWorkerError)
    assert missing_exc.value.code == "save_copy_invariant_violation"

    changed_path = dict(evidence, path_after="C:/model/changed.3dm")
    with pytest.raises(dwc.DirectorWorkerError) as changed_exc:
        dwc.enforce_save_copy_evidence(changed_path, dwc.DirectorWorkerError)
    assert changed_exc.value.code == "save_copy_invariant_violation"

    save_small = dict(evidence, save_small_used=True)
    with pytest.raises(dwc.DirectorWorkerError) as small_exc:
        dwc.enforce_save_copy_evidence(save_small, dwc.DirectorWorkerError)
    assert small_exc.value.code == "save_copy_invariant_violation"


async def test_error_cls_is_respected(tmp_path):
    root = make_package_files(tmp_path)
    fake = make_fake_native(modified=True)
    await expect_error(
        dwc.open_package_document(
            fake, root, root / "prepared.3dm", port=None,
            error_cls=CustomWorkerError, mode="require_fresh"),
        "document_not_saved", CustomWorkerError)
