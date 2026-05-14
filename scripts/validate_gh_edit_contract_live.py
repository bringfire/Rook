from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "mcp_server" / "src"))

from rook.agent.tool_dispatcher import ToolDispatcher  # noqa: E402
from rook.bridge import discover_instances  # noqa: E402


class Suite:
    def __init__(self) -> None:
        self.checks: list[tuple[str, bool, Any]] = []

    def record(self, label: str, ok: bool, detail: Any) -> None:
        self.checks.append((label, ok, detail))

    def expect(self, label: str, detail: Any, predicate: Callable[[Any], bool]) -> Any:
        ok = False
        try:
            ok = predicate(detail)
        except Exception as exc:
            detail = {"detail": detail, "exception": repr(exc)}
        self.record(label, ok, detail)
        return detail

    def summarize(self) -> int:
        failed = False
        print("\nLive GH edit contract checks:")
        for label, ok, detail in self.checks:
            print(f"{'PASS' if ok else 'FAIL'}: {label}")
            if not ok:
                failed = True
                print(json.dumps(detail, indent=2, default=str))
        return 1 if failed else 0


def _owned_port() -> int | None:
    for env_name in ("ROOK_RHINO_PORT", "NATIVE_PORT"):
        raw = os.environ.get(env_name)
        if raw:
            return int(raw)

    native = next((i for i in discover_instances() if i.get("pluginType") == "native"), None)
    if native is not None:
        return int(native["port"])
    return None


def _data(result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data")
    return data if isinstance(data, dict) else {}


def _errors(result: dict[str, Any]) -> list[str]:
    errors = result.get("errors")
    if isinstance(errors, list):
        return [str(e) for e in errors]
    data_errors = _data(result).get("errors")
    if isinstance(data_errors, list):
        return [str(e) for e in data_errors]
    return []


def _note(result: dict[str, Any]) -> str:
    data = _data(result)
    return str(
        result.get("verification_note")
        or data.get("verification_note")
        or data.get("message")
        or ""
    )


def _is_not_ready_failure(result: dict[str, Any]) -> bool:
    data = _data(result)
    return (
        result.get("success") is False
        and result.get("verified") is False
        and data.get("verified") is False
        and data.get("error") == "grasshopper_not_ready"
        and bool(_note(result))
    )


async def _wait_for_ready(dispatcher: ToolDispatcher, suite: Suite, timeout_seconds: float = 20.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = await dispatcher.dispatch("gh_status", {})
        if _data(last).get("ready_for_edit") is True:
            return last
        await asyncio.sleep(0.5)

    suite.record("gh_status becomes ready after lifecycle document creation", False, last)
    return last


async def _wait_for_available(dispatcher: ToolDispatcher, suite: Suite, timeout_seconds: float = 20.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = await dispatcher.dispatch("gh_status", {})
        if _data(last).get("available") is True:
            return last
        await asyncio.sleep(0.5)

    suite.record("gh_status reports Grasshopper available after explicit open command", False, last)
    return last


async def main() -> int:
    suite = Suite()
    port = _owned_port()
    suite.expect("owned native Rook port discovered", {"port": port}, lambda d: isinstance(d["port"], int) and d["port"] > 0)
    if port is None:
        return suite.summarize()

    dispatcher = ToolDispatcher(port=port)
    unique = uuid.uuid4().hex[:8]

    status_1 = await dispatcher.dispatch("gh_status", {})
    suite.expect(
        "gh_status endpoint execution is distinct from readiness",
        status_1,
        lambda r: r.get("success") is True
        and "ready_for_edit" in _data(r)
        and _data(r).get("ready_for_edit") is False,
    )

    status_2 = await dispatcher.dispatch("gh_status", {})
    suite.expect(
        "gh_status does not create a document or ready canvas",
        {"before": status_1, "after": status_2},
        lambda r: _data(r["after"]).get("ready_for_edit") is False
        and _data(r["after"]).get("has_active_document") is not True,
    )

    snapshot_not_ready = await dispatcher.dispatch("gh_snapshot", {})
    suite.expect(
        "gh_snapshot fails closed when Grasshopper is not ready",
        snapshot_not_ready,
        _is_not_ready_failure,
    )

    edit_not_ready = await dispatcher.dispatch("gh_edit", {"epoch": 0, "create": []})
    suite.expect(
        "gh_edit fails closed when Grasshopper is not ready",
        edit_not_ready,
        lambda r: _is_not_ready_failure(r) and "partial_success" not in r and "partial_success" not in _data(r),
    )

    status_3 = await dispatcher.dispatch("gh_status", {})
    suite.expect(
        "fail-closed GH calls do not create a phantom document",
        status_3,
        lambda r: r.get("success") is True
        and _data(r).get("ready_for_edit") is False
        and _data(r).get("has_active_document") is not True,
    )

    open_gh = await dispatcher.dispatch("rhino_command", {"command": "_Grasshopper"})
    suite.expect(
        "explicit _Grasshopper command loads the Grasshopper runtime",
        open_gh,
        lambda r: r.get("success") is True,
    )

    available_status = await _wait_for_available(dispatcher, suite)
    suite.expect(
        "gh_status reports Grasshopper available after explicit open command",
        available_status,
        lambda r: r.get("success") is True and _data(r).get("available") is True,
    )

    document_new = await dispatcher.dispatch("gh_document_new", {})
    suite.expect(
        "gh_document_new creates a blank editable document for ready-state checks",
        document_new,
        lambda r: r.get("success") is True or _data(r).get("created") is True or r.get("created") is True,
    )

    ready_status = await _wait_for_ready(dispatcher, suite)
    suite.expect(
        "gh_status reports ready_for_edit once a real document is active",
        ready_status,
        lambda r: r.get("success") is True and _data(r).get("ready_for_edit") is True,
    )

    snapshot_ready = await dispatcher.dispatch("gh_snapshot", {})
    suite.expect(
        "gh_snapshot succeeds when Grasshopper is ready",
        snapshot_ready,
        lambda r: r.get("success") is True and isinstance(_data(r).get("epoch"), int),
    )
    epoch = _data(snapshot_ready).get("epoch")
    if not isinstance(epoch, int):
        return suite.summarize()

    clean_edit = await dispatcher.dispatch(
        "gh_edit",
        {
            "epoch": epoch,
            "create": [
                {
                    "temp_id": "T_CLEAN",
                    "type": "panel",
                    "content": f"clean-{unique}",
                    "pos": [80, 80],
                }
            ],
        },
    )
    suite.expect(
        "clean gh_edit creates one component without contract warnings",
        clean_edit,
        lambda r: r.get("success") is True
        and _data(r).get("edit_summary", {}).get("created") == 1
        and not _data(r).get("edit_summary", {}).get("errors")
        and "partial_success" not in r,
    )

    next_snapshot = await dispatcher.dispatch("gh_snapshot", {})
    next_epoch = _data(next_snapshot).get("epoch")
    suite.expect(
        "gh_snapshot returns epoch after clean edit",
        next_snapshot,
        lambda r: r.get("success") is True and isinstance(_data(r).get("epoch"), int),
    )
    if not isinstance(next_epoch, int):
        return suite.summarize()

    no_mutation_error = await dispatcher.dispatch(
        "gh_edit",
        {
            "epoch": next_epoch,
            "create": [
                {
                    "temp_id": "T_BAD",
                    "name": f"DefinitelyMissingComponent_{unique}",
                    "pos": [220, 80],
                }
            ],
        },
    )
    suite.expect(
        "no-mutation gh_edit error is strict failure without partial_success",
        no_mutation_error,
        lambda r: r.get("success") is False
        and r.get("verified") is False
        and "partial_success" not in r
        and "partial_success" not in _data(r)
        and bool(_errors(r))
        and "failed before applying any mutations" in _note(r),
    )

    partial_snapshot = await dispatcher.dispatch("gh_snapshot", {})
    partial_epoch = _data(partial_snapshot).get("epoch")
    suite.expect(
        "gh_snapshot returns epoch after no-mutation failure",
        partial_snapshot,
        lambda r: r.get("success") is True and isinstance(_data(r).get("epoch"), int),
    )
    if not isinstance(partial_epoch, int):
        return suite.summarize()

    partial_error = await dispatcher.dispatch(
        "gh_edit",
        {
            "epoch": partial_epoch,
            "create": [
                {
                    "temp_id": "T_PART",
                    "type": "panel",
                    "content": f"partial-{unique}",
                    "pos": [80, 180],
                }
            ],
            "connect": ["T_PART.O0>T_MISSING.I0"],
        },
    )
    suite.expect(
        "partial-mutation gh_edit error is strict unverified partial failure",
        partial_error,
        lambda r: r.get("success") is False
        and r.get("partial_success") is True
        and r.get("verified") is False
        and _data(r).get("partial_success") is True
        and _data(r).get("verified") is False
        and _data(r).get("edit_summary", {}).get("created") == 1
        and bool(_errors(r))
        and "partially applied" in _note(r),
    )

    undo_partial = await dispatcher.dispatch("gh_undo", {})
    suite.expect("gh_undo cleans up partial create", undo_partial, lambda r: r.get("success") is not False)

    undo_clean = await dispatcher.dispatch("gh_undo", {})
    suite.expect("gh_undo cleans up clean create", undo_clean, lambda r: r.get("success") is not False)

    return suite.summarize()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
