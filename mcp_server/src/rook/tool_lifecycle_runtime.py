"""Runtime adapter for lifecycle denial and best-effort local telemetry."""

from __future__ import annotations

from .tool_lifecycle import (
    DispatchOrigin,
    LifecycleEntry,
    containment_envelope,
    resolve_contained_identity,
)


def _record_containment_denial(
    entry: LifecycleEntry,
    origin: DispatchOrigin,
) -> None:
    from .learning.metrics_store import get_metrics_store

    get_metrics_store().record_containment_denial(entry, origin)


def deny_if_contained(
    raw_name: object,
    origin: DispatchOrigin,
) -> dict[str, object] | None:
    entry = resolve_contained_identity(raw_name)
    if entry is None:
        return None

    try:
        _record_containment_denial(entry, origin)
    except Exception:
        pass
    return containment_envelope(entry)
