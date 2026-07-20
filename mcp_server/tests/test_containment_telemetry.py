from __future__ import annotations

import re
import sys
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from rook.learning.metrics_store import MetricsStore  # noqa: E402
from rook.tool_lifecycle import resolve_contained_tool  # noqa: E402
from rook.tool_lifecycle_runtime import (  # noqa: E402
    DispatchOrigin,
    deny_if_contained,
)


def test_containment_telemetry_is_bounded_closed_and_persisted(tmp_path: Path) -> None:
    path = tmp_path / "metrics.json"
    store = MetricsStore(path)
    entry = resolve_contained_tool("gh_execute_intent")
    assert entry is not None

    for _ in range(55):
        store.record_containment_denial(entry, DispatchOrigin.PUBLIC_MCP)
    store.save()

    events = MetricsStore(path).get_containment_denials_snapshot()
    assert len(events) == 50
    assert all(
        set(event) == {"tool", "disposition", "origin", "timestamp"}
        for event in events
    )
    assert events[-1] == {
        "tool": "gh_execute_intent",
        "disposition": "retired",
        "origin": "public_mcp",
        "timestamp": events[-1]["timestamp"],
    }
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T.*Z", events[-1]["timestamp"])


def test_denial_survives_telemetry_failure(monkeypatch) -> None:
    import rook.tool_lifecycle_runtime as runtime

    monkeypatch.setattr(runtime, "_record_denial", lambda *_args: (_ for _ in ()).throw(OSError("disk unavailable")))

    payload = deny_if_contained("rhino_execute_intent", DispatchOrigin.SERVER_DISPATCH)
    assert payload is not None
    assert payload["code"] == "legacy_semantic_tool_contained"
    assert payload["tool"] == "rhino_execute_intent"


def test_active_and_near_match_names_do_not_emit(monkeypatch) -> None:
    import rook.tool_lifecycle_runtime as runtime

    calls: list[object] = []
    monkeypatch.setattr(runtime, "_record_denial", lambda *args: calls.append(args))

    assert deny_if_contained("gh_edit", DispatchOrigin.SERVER_DISPATCH) is None
    assert deny_if_contained("GH_EXECUTE_INTENT", DispatchOrigin.SERVER_DISPATCH) is None
    assert calls == []
