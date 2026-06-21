# LM2C — Explicit Readonly Group Evidence & Faithful Local Readonly Seed

**Date:** 2026-06-21
**Status:** Approved (design)
**Campaign:** Local/Internal Models roadmap (LM2 continuation)
**Branch:** `codex/lm2c-readonly-group-evidence`

---

## Summary

LM2B left the `readonly` diagnostic seed *tier-only* (`groups=()`) because a
name-suffix heuristic (`*_readonly`) is not a faithful proxy for the repo's
actual `READONLY_ALLOWED_GROUPS` policy. LM2C closes that gap the evidence-first
way:

1. Carry the real `READONLY_ALLOWED_GROUPS` set into the injected snapshot
   (`SurfaceSources`).
2. Populate it in `collect_live_sources()` from `tool_groups.READONLY_ALLOWED_GROUPS`.
3. Add a pure builder that constructs a **locally-executable** readonly profile
   from that evidence, subtracting MCP-only groups.
4. Add a sibling pure function that exposes the **deliberately excluded**
   MCP-only groups, so the exclusion is provable, never silent.

LM2C is read-only and diagnostic. It changes no runtime behavior, no
`ToolRegistry`, no resolver logic, and no `CapabilityInventory` output.

## Motivation

`READONLY_ALLOWED_GROUPS` (13 groups) and `MCP_ONLY_GROUPS` overlap in exactly
three entries:

```
READONLY_ALLOWED_GROUPS ∩ MCP_ONLY_GROUPS
  = {"gh_exploration", "gh_knowledge", "gh_validation"}
```

The `tool_groups.py` comment confirms these three are "MCP-only and unreachable
by agents via the HTTP bridge … included for forward compatibility." A faithful
readonly seed must therefore say two true things at once:

- these groups **are** readonly-policy-allowed, and
- they are **not** locally dispatchable today.

A *local* readonly worker can only run the locally-reachable subset. So the
evidence-backed seed carries `allowed − mcp_only` (further narrowed to groups
that actually have a definition in the same snapshot), and the excluded MCP-only
groups are surfaced as separate, testable data rather than being silently
dropped.

## Design

### Unit 1 — Evidence carrier (`capability_record.py`)

Add one field to the `SurfaceSources` frozen dataclass:

```python
readonly_allowed_groups: frozenset[str] = frozenset()
```

- Defaulted to empty, so every existing LM2A/LM2B `SurfaceSources` fixture
  remains valid with no change.
- Adds no import. The module stays stdlib-only (`frozenset` is a builtin).

**Responsibility:** hold the readonly-allowed group-name policy set as injected
evidence. It does not interpret it.

### Unit 2 — Live collector (`capability_inventory.py`)

`collect_live_sources()` populates the new field. The function already imports
`rook.agent.tool_groups as tg`, so this adds no import:

```python
readonly_allowed_groups=frozenset(tg.READONLY_ALLOWED_GROUPS),
```

**Invariant:** nothing in `build_inventory` reads `readonly_allowed_groups`.
`CapabilityRecord` and `CapabilityInventory` output is byte-for-byte unchanged by
LM2C. The new field is consumed only by the Unit 3 helpers.

### Unit 3 — Two pure functions (`execution_profile.py`)

Both consume only `SurfaceSources` (defined in `capability_record`, already on
the module's import allow-list `{__future__, dataclasses, typing,
rook.agent.capability_record}`), so the import boundary is preserved verbatim —
no new import is introduced.

```python
def readonly_profile_from_sources(sources: SurfaceSources) -> ProfileDefinition:
    """Evidence-backed, locally-executable readonly seed.

    Groups = readonly-allowed groups that (a) have a definition in this same
    snapshot and (b) are not MCP-only. The result is resolvable against the
    inventory built from the same SurfaceSources, and never knowingly emits an
    unknown_group finding from the default seed.
    """
    local_groups = (
        sources.readonly_allowed_groups
        & frozenset(sources.groups.keys())
    ) - sources.mcp_only_groups
    return ProfileDefinition(
        name="readonly",
        initial_tier="readonly_tier0",
        groups=tuple(sorted(local_groups)),
        description="Locally-executable observation-only worker (evidence-backed seed).",
    )


def readonly_excluded_mcp_only_groups(sources: SurfaceSources) -> tuple[str, ...]:
    """Readonly-allowed groups deliberately excluded because they are MCP-only.

    Full policy intersection — NOT filtered by groups.keys() — so the excluded
    pin reflects policy regardless of whether a group definition exists.
    """
    return tuple(sorted(sources.readonly_allowed_groups & sources.mcp_only_groups))
```

Notes:

- `(A & B) - C` is set-identical to Python's precedence-driven `A & (B - C)`
  (both equal `{x : x∈A ∧ x∈B ∧ x∉C}`); explicit parentheses are used for the
  reader.
- Both functions are pure, deterministic, sorted-output, and evidence-driven
  (no tool names, no suffixes).
- The builder emits **no findings** — group-policy evidence is not
  profile-resolution evidence. Findings remain the job of `resolve_profile`.
- `excluded_mcp` is not narrowed by `groups.keys()`; the builder's `local_groups`
  is.

### What LM2C explicitly does NOT do

- No change to `default_profile_definitions()` — it stays no-arg, constant,
  tier-only. The evidence-backed `readonly` is its counterpart, not its
  replacement.
- No `profile_definitions_from_sources` bundle helper this slice (avoids
  "profile catalog" gravity).
- No `ProfileFinding` for the exclusion; no resolver changes; no
  `default_profile_definitions` overload.
- No external/MCP readonly profile.
- No "readonly-allowed but missing group definition" drift helper — deferred to
  a possible later sibling.
- No runtime wiring. Diagnostic only.

## Data Flow

```
READONLY_ALLOWED_GROUPS (tool_groups.py)
        │  collect_live_sources()
        ▼
SurfaceSources.readonly_allowed_groups        ← injected evidence
        │
        ├── readonly_profile_from_sources(sources) ─► ProfileDefinition(name="readonly", groups=local_groups)
        │            │
        │            └── resolve_profile(def, inventory)  ← existing LM2B path, unchanged
        │
        └── readonly_excluded_mcp_only_groups(sources) ─► ("gh_exploration","gh_knowledge","gh_validation")
```

`build_inventory(sources, catalog)` is unaffected by the new field and produces
identical records.

## Error / Edge Handling

- **Empty `readonly_allowed_groups`:** builder yields `groups == ()` — degrades
  to a tier-only readonly profile, matching the constant seed. No error.
- **Readonly-allowed group with no definition in `sources.groups`:** excluded
  from the builder's `local_groups` (filtered by `groups.keys()`), so the
  default evidence-backed seed never knowingly emits `unknown_group`. The
  drift itself is intentionally not reported in LM2C (deferred).
- **Readonly-allowed group that is MCP-only:** excluded from `local_groups`;
  surfaced by `readonly_excluded_mcp_only_groups`.

## Testing

All tests are deterministic and use small injected fixtures or live module
constants — never a broad live catalog.

1. **Record field exists / default:** a `SurfaceSources()` with no
   `readonly_allowed_groups` arg has `readonly_allowed_groups == frozenset()`.
2. **Collector (live constants):**
   `collect_live_sources().readonly_allowed_groups == frozenset(READONLY_ALLOWED_GROUPS)`.
3. **Builder filters both ways (synthetic fixture):** given
   `groups = {"a": (...), "b": (...), "gh_knowledge": (...)}`,
   `readonly_allowed_groups = {"a","b","gh_knowledge","ghost_group"}`,
   `mcp_only_groups = {"gh_knowledge"}` →
   `readonly_profile_from_sources(sources).groups == ("a","b")`
   (`ghost_group` dropped: no definition; `gh_knowledge` dropped: MCP-only).
   Assert `name == "readonly"`, `initial_tier == "readonly_tier0"`.
4. **Excluded (synthetic fixture):** same fixture →
   `readonly_excluded_mcp_only_groups(sources) == ("gh_knowledge",)`.
5. **Excluded (real constants pin):** with `readonly_allowed_groups` and
   `mcp_only_groups` from the live module constants,
   `readonly_excluded_mcp_only_groups(...) == ("gh_exploration","gh_knowledge","gh_validation")`.
6. **Empty edge:** `SurfaceSources(readonly_allowed_groups=frozenset())` →
   builder `groups == ()`.
7. **Determinism:** builder `groups` and excluded output are sorted tuples
   (assert equality to `tuple(sorted(...))` of the inputs).
8. **Integration (small deterministic inventory, no live catalog):** build a
   fixture with
   - one readonly-allowed **non-MCP** group (`"ro_local"`) holding a
     local-visible, dispatchable, schema-backed tool (`"ro_tool_local"` in
     `local_tool_names` and in `catalog`);
   - one readonly-allowed **MCP-only** group (`"ro_mcp"` in `mcp_only_groups`)
     holding an MCP-only tool (`"ro_tool_mcp"`);

   with `readonly_allowed_groups = {"ro_local","ro_mcp"}` and
   `groups = {"ro_local": ("ro_tool_local",), "ro_mcp": ("ro_tool_mcp",)}`.
   Then:
   - `readonly_profile_from_sources(sources).groups == ("ro_local",)`
     (`ro_mcp` excluded);
   - `inv = build_inventory(sources, catalog)`;
   - `res = resolve_profile(readonly_profile_from_sources(sources), inv)`;
   - assert no `ProfileFinding` with `code == "mcp_only_tool"` in
     `res.findings`, and `"ro_tool_mcp" not in res.tool_names` — proving the
     seed is locally executable.
9. **Import-boundary guards re-run:**
   - `execution_profile.py` imports remain
     `<= {__future__, dataclasses, typing, rook.agent.capability_record}`
     (the existing LM2B boundary test, unchanged set).
   - `capability_record.py` stays stdlib-only (the existing LM2A boundary
     test, unchanged).

## Invariants (do not violate)

- `build_inventory` / `CapabilityInventory` / `CapabilityRecord` output unchanged.
- `default_profile_definitions()` unchanged (no-arg, constant, tier-only).
- No findings emitted from a builder.
- No resolver (`resolve_profile`) behavior change.
- `execution_profile.py` import allow-list unchanged; `capability_record.py`
  stdlib-only.
- All tuple outputs sorted; all functions pure and deterministic.

## File Touch List

- `mcp_server/src/rook/agent/capability_record.py` — add one field.
- `mcp_server/src/rook/agent/capability_inventory.py` — populate field in
  `collect_live_sources()`.
- `mcp_server/src/rook/agent/execution_profile.py` — add two pure functions.
- Tests: extend the existing LM2A/LM2B test modules (record, inventory,
  execution_profile) with the cases above.
