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

from rook import server  # noqa: E402
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
        print("\nLive direct MCP GH edit contract checks:")
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


def _decode_text_response(response: Any) -> dict[str, Any]:
    text = response[0].text
    if text.startswith("Error: "):
        raw = text[len("Error: ") :]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = raw
        return {"success": False, "data": data, "text": text}

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = text
    return {"success": True, "data": data, "text": text}


async def tool(name: str, args: dict[str, Any] | None = None, *, port: int) -> dict[str, Any]:
    payload = dict(args or {})
    payload["port"] = port
    return _decode_text_response(await server.call_tool(name, payload))


def _data(result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data")
    return data if isinstance(data, dict) else {}


def _errors(result: dict[str, Any]) -> list[str]:
    data_errors = _data(result).get("errors")
    if isinstance(data_errors, list):
        return [str(e) for e in data_errors]
    return []


def _note(result: dict[str, Any]) -> str:
    data = _data(result)
    return str(data.get("verification_note") or data.get("message") or "")


def _is_not_ready_failure(result: dict[str, Any]) -> bool:
    data = _data(result)
    return (
        result.get("success") is False
        and data.get("error") == "grasshopper_not_ready"
        and data.get("ready_for_edit") is False
        and data.get("verified") is False
        and bool(_note(result))
    )


async def _wait_for_status(
    suite: Suite,
    port: int,
    predicate: Callable[[dict[str, Any]], bool],
    label: str,
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = await tool("gh_status", port=port)
        if predicate(_data(last)):
            return last
        await asyncio.sleep(0.5)

    suite.record(label, False, last)
    return last


async def main() -> int:
    suite = Suite()
    port = _owned_port()
    suite.expect(
        "owned native Rook port discovered",
        {"port": port},
        lambda d: isinstance(d["port"], int) and d["port"] > 0,
    )
    if port is None:
        return suite.summarize()

    unique = uuid.uuid4().hex[:8]

    status_1 = await tool("gh_status", port=port)
    suite.expect(
        "direct MCP gh_status reports endpoint success separately from readiness",
        status_1,
        lambda r: r.get("success") is True
        and "ready_for_edit" in _data(r)
        and _data(r).get("ready_for_edit") is False,
    )

    status_2 = await tool("gh_status", port=port)
    suite.expect(
        "direct MCP gh_status does not create a document or ready canvas",
        status_2,
        lambda r: _data(r).get("ready_for_edit") is False
        and _data(r).get("has_active_document") is not True,
    )

    snapshot_not_ready = await tool("gh_snapshot", {}, port=port)
    suite.expect(
        "direct MCP gh_snapshot fails closed with parseable unverified payload",
        snapshot_not_ready,
        _is_not_ready_failure,
    )

    edit_not_ready = await tool("gh_edit", {"epoch": 0, "create": []}, port=port)
    suite.expect(
        "direct MCP gh_edit fails closed with parseable unverified payload",
        edit_not_ready,
        lambda r: _is_not_ready_failure(r) and "partial_success" not in _data(r),
    )

    status_3 = await tool("gh_status", port=port)
    suite.expect(
        "direct MCP fail-closed GH calls do not create a phantom document",
        status_3,
        lambda r: _data(r).get("ready_for_edit") is False
        and _data(r).get("has_active_document") is not True,
    )

    open_gh = await tool("rhino_command", {"command": "_Grasshopper"}, port=port)
    suite.expect(
        "direct MCP explicit _Grasshopper command loads the runtime",
        open_gh,
        lambda r: r.get("success") is True,
    )

    available_status = await _wait_for_status(
        suite,
        port,
        lambda d: d.get("available") is True,
        "direct MCP gh_status reports Grasshopper available after explicit open command",
    )
    suite.expect(
        "direct MCP gh_status reports Grasshopper available after explicit open command",
        available_status,
        lambda r: _data(r).get("available") is True,
    )

    document_new = await tool("gh_document_new", {}, port=port)
    suite.expect(
        "direct MCP gh_document_new creates a blank editable document",
        document_new,
        lambda r: r.get("success") is True
        and (_data(r).get("created") is True or _data(r).get("created") is None),
    )

    ready_status = await _wait_for_status(
        suite,
        port,
        lambda d: d.get("ready_for_edit") is True,
        "direct MCP gh_status becomes ready after document creation",
    )
    suite.expect(
        "direct MCP gh_status reports ready_for_edit once active",
        ready_status,
        lambda r: _data(r).get("ready_for_edit") is True,
    )

    snapshot_ready = await tool("gh_snapshot", {}, port=port)
    suite.expect(
        "direct MCP gh_snapshot succeeds when ready",
        snapshot_ready,
        lambda r: r.get("success") is True and isinstance(_data(r).get("epoch"), int),
    )
    epoch = _data(snapshot_ready).get("epoch")
    if not isinstance(epoch, int):
        return suite.summarize()

    clean_edit = await tool(
        "gh_edit",
        {
            "epoch": epoch,
            "create": [
                {
                    "temp_id": "T_CLEAN",
                    "type": "panel",
                    "content": f"mcp-clean-{unique}",
                    "pos": [80, 80],
                }
            ],
        },
        port=port,
    )
    suite.expect(
        "direct MCP clean gh_edit returns snapshot data without partial metadata",
        clean_edit,
        lambda r: r.get("success") is True
        and _data(r).get("edit_summary", {}).get("created") == 1
        and not _data(r).get("edit_summary", {}).get("errors")
        and "partial_success" not in _data(r),
    )

    next_snapshot = await tool("gh_snapshot", {}, port=port)
    next_epoch = _data(next_snapshot).get("epoch")
    suite.expect(
        "direct MCP gh_snapshot returns epoch after clean edit",
        next_snapshot,
        lambda r: r.get("success") is True and isinstance(_data(r).get("epoch"), int),
    )
    if not isinstance(next_epoch, int):
        return suite.summarize()

    no_mutation_error = await tool(
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
        port=port,
    )
    suite.expect(
        "direct MCP no-mutation edit error has visible failure contract",
        no_mutation_error,
        lambda r: r.get("success") is False
        and _data(r).get("verified") is False
        and "partial_success" not in _data(r)
        and bool(_errors(r))
        and "failed before applying any mutations" in _note(r),
    )

    partial_snapshot = await tool("gh_snapshot", {}, port=port)
    partial_epoch = _data(partial_snapshot).get("epoch")
    suite.expect(
        "direct MCP gh_snapshot returns epoch after no-mutation failure",
        partial_snapshot,
        lambda r: r.get("success") is True and isinstance(_data(r).get("epoch"), int),
    )
    if not isinstance(partial_epoch, int):
        return suite.summarize()

    partial_error = await tool(
        "gh_edit",
        {
            "epoch": partial_epoch,
            "create": [
                {
                    "temp_id": "T_PART",
                    "type": "panel",
                    "content": f"mcp-partial-{unique}",
                    "pos": [80, 180],
                }
            ],
            "connect": ["T_PART.O0>T_MISSING.I0"],
        },
        port=port,
    )
    suite.expect(
        "direct MCP partial edit error has visible partial failure contract",
        partial_error,
        lambda r: r.get("success") is False
        and _data(r).get("partial_success") is True
        and _data(r).get("verified") is False
        and _data(r).get("edit_summary", {}).get("created") == 1
        and bool(_errors(r))
        and "partially applied" in _note(r),
    )

    undo_partial = await tool("gh_undo", {}, port=port)
    suite.expect("direct MCP gh_undo cleans up partial create", undo_partial, lambda r: r.get("success") is True)

    undo_clean = await tool("gh_undo", {}, port=port)
    suite.expect("direct MCP gh_undo cleans up clean create", undo_clean, lambda r: r.get("success") is True)

    return suite.summarize()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
