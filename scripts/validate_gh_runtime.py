import asyncio
import json
import os
import sys
import uuid

import httpx


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "mcp_server", "src"))

from rook.bridge import call_rhino, discover_instances, native_client, select_rhino_instance  # noqa: E402
from rook.server import _mcp_tool_executor  # noqa: E402


async def _get_json(url: str) -> tuple[int | None, dict | str]:
    async with native_client(timeout=10.0) as client:
        try:
            response = await client.get(url)
            try:
                return response.status_code, response.json()
            except ValueError:
                return response.status_code, response.text
        except Exception as exc:
            return None, str(exc)


async def main() -> int:
    instances = discover_instances()
    print("Instances:")
    print(json.dumps(instances, indent=2))

    native = next((i for i in instances if i.get("pluginType") == "native"), None)
    managed = next((i for i in instances if i.get("pluginType") == "csharp"), None)
    if not native or not managed:
        print("FAIL: expected both native and managed instances")
        return 1

    if native.get("processId") != managed.get("processId"):
        print("FAIL: native and managed instances do not share a Rhino PID")
        return 1

    checks: list[tuple[str, bool, object]] = []

    for route in (
        "/gh/status",
        "/gh/query",
        "/gh/document",
        "/gh/selection",
        "/gh/categories",
        "/gh/library",
        "/gh/errors",
    ):
        status, body = await _get_json(f"http://localhost:{native['port']}{route}")
        checks.append((f"native {route}", status == 200, {"status": status, "body": body}))

    status, body = await _get_json(f"http://localhost:{native['port']}/gh/value")
    checks.append(("native /gh/value proxied", status == 400, {"status": status, "body": body}))

    status, body = await _get_json(f"http://localhost:{native['port']}/gh/component")
    checks.append(("native /gh/component proxied", status == 400, {"status": status, "body": body}))

    status, body = await _get_json(f"http://localhost:{native['port']}/gh/inspect-output")
    checks.append(("native /gh/inspect-output proxied", status == 400, {"status": status, "body": body}))

    status, body = await _get_json(f"http://localhost:{native['port']}/gh/not-a-route")
    checks.append(("native /gh/not-a-route absent", status == 404, {"status": status, "body": body}))

    for endpoint, expected in (
        ("/gh/query", "native"),
        ("/gh/document", "native"),
        ("/gh/selection", "native"),
        ("/gh/library", "native"),
        ("/gh/value", "native"),
        ("/gh/component", "native"),
        ("/gh/inspect-output", "native"),
    ):
        selected = select_rhino_instance(endpoint=endpoint)
        checks.append((
            f"bridge selects {expected} for {endpoint}",
            bool(selected and selected.get("pluginType") == expected),
            selected,
        ))

    unsupported_result = await call_rhino("/gh/not-a-route", "GET", port=native["port"])
    checks.append((
        "unsupported GH route is rejected explicitly",
        isinstance(unsupported_result, dict)
        and not unsupported_result.get("success")
        and "supports /gh/not-a-route" in str(unsupported_result.get("data")),
        unsupported_result,
    ))

    slider_name = f"CodexValidation_{uuid.uuid4().hex[:8]}"
    create_result = await _mcp_tool_executor("gh_create_slider", {
        "x": 120,
        "y": 120,
        "min": 0,
        "max": 10,
        "value": 5,
        "nickname": slider_name,
        "port": native["port"],
    })
    checks.append((
        "gh_create_slider succeeds",
        isinstance(create_result, dict) and create_result.get("created") is True,
        create_result,
    ))

    history = await _mcp_tool_executor("gh_session_history", {"limit": 5})
    entries = history.get("entries", []) if isinstance(history, dict) else []
    matching_entry = next((entry for entry in entries if entry.get("action") == "gh_create_slider"), None)
    checks.append((
        "gh_session_history records slider creation",
        matching_entry is not None,
        history,
    ))
    checks.append((
        "session document is not unknown.gh",
        isinstance(history, dict) and history.get("document") != "unknown.gh",
        history.get("document") if isinstance(history, dict) else history,
    ))

    failed = False
    print("\nChecks:")
    for label, ok, detail in checks:
        prefix = "PASS" if ok else "FAIL"
        print(f"{prefix}: {label}")
        if not ok:
            failed = True
            print(json.dumps(detail, indent=2, default=str))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
