# Active Roadmaps

Updated: 2026-08-02

This directory is the authoritative index of Rook's active program roadmaps.
Only documents listed below govern current sequencing.

Specifications, implementation plans, probes, reports, and milestone notes under
`docs/superpowers/` are historical evidence unless an active roadmap explicitly
promotes them. Preserve those records; do not silently turn an old experiment into
current product direction.

## Active

| Roadmap | Scope |
|---|---|
| [Compositional Agent Harness Roadmap](2026-08-02-compositional-agent-harness-roadmap.md) | Frontier planning, deterministic lowering, bounded Worker leaves, receipt-driven replanning, and product graduation |
| [Release Surface Hardening Roadmap](2026-07-31-release-surface-hardening-roadmap.md) | Installer, release metadata, packaging, public documentation, upgrade behavior, and release validation |

## Authority Order

When documents disagree, use this order:

1. Live code and [Current Architecture](../CURRENT_ARCHITECTURE.md) establish what
   exists now.
2. This index and its active roadmaps establish current sequencing.
3. An approved focused specification governs its bounded slice.
4. Historical specifications, plans, probes, and milestones explain prior decisions
   and evidence but do not authorize new work.

## Maintenance Rule

Add a roadmap here only when it coordinates more than one focused implementation
slice. Remove it from the active table when the program finishes or is superseded,
while retaining the roadmap itself as historical evidence.
