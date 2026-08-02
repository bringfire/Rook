# Findings-to-Parameters Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that researched findings can drive a parametric Grasshopper definition through a Chirp reasoning node, end to end, on a live canvas.

**Architecture:** A source-neutral `Finding`/`FindingSet` contract carries researched facts with their source and confidence. An Architecture Studio reader converts AS report markdown into that contract. `FindingSet.to_brief()` renders a **deterministic** string that feeds a Chirp `planner` node's Brief pin; the planner emits typed parameters that drive ordinary deterministic Grasshopper geometry. Determinism of the brief matters because Chirp caches on input — an unstable brief would defeat the cache.

**Tech Stack:** Python 3.12 (stdlib only for the new module), pytest, Rook MCP tools (`chirp_create`, `gh_snapshot`, `gh_edit`, `gh_errors`, `gh_knowledge_query`), Chirp adapter (FastAPI + DSPy).

**Slice scope:** This is slice 1 of 5 from `docs/superpowers/specs/2026-08-01-reasoning-as-dataflow-design.md`. Slices 2–5 (Correction loop, return brief, analysis/imagery, narrative/deck) are planned separately after this one returns evidence.

## Global Constraints

- Python 3.12; venv at `mcp_server/.venv` (created with `uv venv .venv --python 3.12`).
- **No new third-party dependencies.** The `findings` module uses stdlib only (`dataclasses`, `json`, `re`).
- Tests live flat in `mcp_server/tests/`, named `test_*.py`. Tests requiring live Rhino use the `_live.py` suffix.
- `sys.dont_write_bytecode = True` is set in the package `__init__.py`; do not remove it.
- **Never hardcode Grasshopper component GUIDs.** GUIDs differ across installs. Always resolve via `gh_knowledge_query` and pass the resolved GUID to `gh_edit`.
- Chirp categories are exactly: `planner`, `interpreter`, `critic`, `narrator`, `classifier`, `gate`, `editor`.
- `chirp_create` auto-adds a `Correction` input pin and a `Reasoning` output pin. Never declare them in `pins_in`/`pins_out`.
- Chirp pin type format is `"Name:Type"`. Valid types: `string`, `int`, `float`, `double`, `bool`, `Point3d`, `Vector3d`, `Plane`, `Line`, `Curve`, `Surface`, `Brep`, `Mesh`, `Box`, `Circle`, `Arc`, `Polyline`.
- Confidence values are exactly `"sourced"`, `"derived"`, `"assumed"`.

---

### Task 1: Finding and FindingSet contract

**Files:**
- Create: `mcp_server/src/rook/findings/__init__.py`
- Create: `mcp_server/src/rook/findings/model.py`
- Test: `mcp_server/tests/test_findings_model.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `Finding(key: str, value: str, source: str, confidence: str, unit: str | None = None)` — frozen dataclass; `.render() -> str`
  - `FindingSet(findings: Iterable[Finding] = ())` — `.add(Finding) -> None`, `.get(key: str) -> Finding | None`, `.to_brief() -> str`, `__len__`, `__iter__` (yields sorted by key)
  - `CONFIDENCE_LEVELS: tuple[str, str, str]`

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_findings_model.py`:

```python
import pytest

from rook.findings.model import CONFIDENCE_LEVELS, Finding, FindingSet


def test_finding_renders_with_unit_and_source():
    f = Finding(
        key="max_floor_area",
        value="218620",
        source="MapPLUTO via /as:zoning-analysis-nyc",
        confidence="sourced",
        unit="SF",
    )
    assert f.render() == (
        "max_floor_area: 218620 SF "
        "[sourced; source: MapPLUTO via /as:zoning-analysis-nyc]"
    )


def test_finding_renders_without_unit():
    f = Finding(key="zone", value="C6-4", source="PLUTO", confidence="sourced")
    assert f.render() == "zone: C6-4 [sourced; source: PLUTO]"


def test_finding_rejects_empty_key():
    with pytest.raises(ValueError, match="non-empty"):
        Finding(key="", value="1", source="s", confidence="sourced")


def test_finding_rejects_unknown_confidence():
    with pytest.raises(ValueError, match="confidence"):
        Finding(key="k", value="1", source="s", confidence="guessed")


def test_confidence_levels_are_exactly_three():
    assert CONFIDENCE_LEVELS == ("sourced", "derived", "assumed")


def test_findingset_rejects_duplicate_keys():
    fs = FindingSet([Finding(key="k", value="1", source="s", confidence="sourced")])
    with pytest.raises(ValueError, match="duplicate"):
        fs.add(Finding(key="k", value="2", source="s", confidence="sourced"))


def test_findingset_get_returns_none_for_missing():
    fs = FindingSet()
    assert fs.get("nope") is None


def test_to_brief_is_sorted_by_key_regardless_of_insertion_order():
    a = Finding(key="alpha", value="1", source="s", confidence="sourced")
    z = Finding(key="zulu", value="2", source="s", confidence="sourced")

    forward = FindingSet([a, z]).to_brief()
    reverse = FindingSet([z, a]).to_brief()

    assert forward == reverse
    assert forward.splitlines()[0].startswith("alpha")
    assert forward.splitlines()[1].startswith("zulu")


def test_to_brief_empty_set_is_empty_string():
    assert FindingSet().to_brief() == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python -m pytest mcp_server/tests/test_findings_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rook.findings'`

- [ ] **Step 3: Write the implementation**

Create `mcp_server/src/rook/findings/__init__.py`:

```python
"""Source-neutral contract for researched findings that drive parameters."""

from .model import CONFIDENCE_LEVELS, Finding, FindingSet

__all__ = ["CONFIDENCE_LEVELS", "Finding", "FindingSet"]
```

Create `mcp_server/src/rook/findings/model.py`:

```python
"""Source-neutral contract for researched findings that drive parameters.

A Finding is one researched fact with its provenance attached. A FindingSet
renders to a deterministic brief string consumed by a Chirp planner node.

Determinism matters: ChirpAdapter.call() caches on (signature, inputs, schema,
model). An unstable brief string would produce a cache miss on every solve and
make the definition both slow and non-reproducible.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

CONFIDENCE_LEVELS = ("sourced", "derived", "assumed")


@dataclass(frozen=True)
class Finding:
    """One researched fact with provenance.

    Args:
        key: Stable snake_case identifier, e.g. "max_floor_area".
        value: The fact, always as a string. Typing happens downstream at the
            Chirp pin boundary, not here.
        source: Where it came from, specific enough to re-check.
        confidence: One of CONFIDENCE_LEVELS.
        unit: Optional unit, e.g. "SF", "ft", "ratio".
    """

    key: str
    value: str
    source: str
    confidence: str
    unit: str | None = None

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("Finding.key must be non-empty")
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(
                f"Finding.confidence must be one of {CONFIDENCE_LEVELS}, "
                f"got {self.confidence!r}"
            )

    def render(self) -> str:
        """One line, provenance inline, for the planner brief."""
        unit = f" {self.unit}" if self.unit else ""
        return (
            f"{self.key}: {self.value}{unit} "
            f"[{self.confidence}; source: {self.source}]"
        )


class FindingSet:
    """An ordered-by-key collection of Findings with unique keys."""

    def __init__(self, findings: Iterable[Finding] = ()) -> None:
        self._by_key: dict[str, Finding] = {}
        for finding in findings:
            self.add(finding)

    def add(self, finding: Finding) -> None:
        if finding.key in self._by_key:
            raise ValueError(f"duplicate finding key: {finding.key!r}")
        self._by_key[finding.key] = finding

    def get(self, key: str) -> Finding | None:
        return self._by_key.get(key)

    def __len__(self) -> int:
        return len(self._by_key)

    def __iter__(self) -> Iterator[Finding]:
        return iter(sorted(self._by_key.values(), key=lambda f: f.key))

    def to_brief(self) -> str:
        """Deterministic brief string for a Chirp planner's Brief pin."""
        return "\n".join(finding.render() for finding in self)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python -m pytest mcp_server/tests/test_findings_model.py -v`
Expected: PASS, 9 passed

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/findings/ mcp_server/tests/test_findings_model.py
git commit -m "feat(findings): source-neutral Finding/FindingSet contract"
```

---

### Task 2: Architecture Studio data-block reader

**Files:**
- Create: `mcp_server/src/rook/findings/architecture_studio.py`
- Create: `mcp_server/tests/fixtures/as_report_sample.md`
- Test: `mcp_server/tests/test_findings_architecture_studio.py`

**Interfaces:**
- Consumes: `Finding`, `FindingSet` from Task 1.
- Produces:
  - `extract_data_block(markdown: str, heading: str) -> dict`
  - `findings_from_stats(stats: dict, source: str, confidence: str = "sourced") -> FindingSet`
  - `normalize_key(key: str) -> str`

**Design note:** The reader is heading-parameterised rather than zoning-specific, so it works for any AS report that publishes a fenced `json` data block — not only NYC zoning. AS's zoning skills are NYC-only; this module must not assume them.

- [ ] **Step 1: Write the fixture**

Create `mcp_server/tests/fixtures/as_report_sample.md`:

````markdown
# Zoning Analysis — 250 Hudson St

## Bulk Controls

| Use | Max FAR | Max Floor Area (SF) |
|-----|---------|---------------------|
| Commercial | 10.0 | 218,620 |

## Envelope Data

Machine-readable data for `/as:zoning-envelope`.

```json
{
  "lot_poly": [[0, 0], [100, 0], [100, 200], [0, 200]],
  "unit": "ft",
  "height_cap": 290,
  "info": { "title": "250 Hudson St", "zone": "C6-4" },
  "stats": { "Commercial FAR": "10.0", "Max Floor Area": "218,620 SF" }
}
```

## Caveats

Verify with NYC Department of City Planning.
````

- [ ] **Step 2: Write the failing tests**

Create `mcp_server/tests/test_findings_architecture_studio.py`:

```python
from pathlib import Path

import pytest

from rook.findings.architecture_studio import (
    extract_data_block,
    findings_from_stats,
    normalize_key,
)

FIXTURE = Path(__file__).parent / "fixtures" / "as_report_sample.md"


def _markdown() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_extract_data_block_returns_parsed_json():
    block = extract_data_block(_markdown(), "Envelope Data")
    assert block["height_cap"] == 290
    assert block["info"]["zone"] == "C6-4"


def test_extract_data_block_does_not_read_past_next_heading():
    markdown = "## Empty Section\n\ntext\n\n## Other\n\n```json\n{\"a\": 1}\n```\n"
    with pytest.raises(ValueError, match="no fenced json block"):
        extract_data_block(markdown, "Empty Section")


def test_extract_data_block_raises_on_missing_heading():
    with pytest.raises(ValueError, match="not found"):
        extract_data_block(_markdown(), "No Such Heading")


def test_normalize_key_snake_cases_and_strips_punctuation():
    assert normalize_key("Max Floor Area") == "max_floor_area"
    assert normalize_key("  Commercial FAR  ") == "commercial_far"
    assert normalize_key("Lot Coverage (%)") == "lot_coverage"


def test_findings_from_stats_attaches_source_and_confidence():
    block = extract_data_block(_markdown(), "Envelope Data")
    findings = findings_from_stats(block["stats"], source="/as:zoning-analysis-nyc")

    assert len(findings) == 2
    far = findings.get("commercial_far")
    assert far is not None
    assert far.value == "10.0"
    assert far.source == "/as:zoning-analysis-nyc"
    assert far.confidence == "sourced"


def test_findings_from_stats_brief_is_deterministic():
    block = extract_data_block(_markdown(), "Envelope Data")
    first = findings_from_stats(block["stats"], source="s").to_brief()
    second = findings_from_stats(block["stats"], source="s").to_brief()
    assert first == second
    assert first.splitlines()[0].startswith("commercial_far")


def test_findings_from_stats_accepts_confidence_override():
    findings = findings_from_stats({"A B": "1"}, source="s", confidence="assumed")
    assert findings.get("a_b").confidence == "assumed"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python -m pytest mcp_server/tests/test_findings_architecture_studio.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rook.findings.architecture_studio'`

- [ ] **Step 4: Write the implementation**

Create `mcp_server/src/rook/findings/architecture_studio.py`:

```python
"""Read Architecture Studio report markdown into source-neutral findings.

AS skills publish machine-readable data as a fenced ```json block under a
named '## ' heading. This module is heading-parameterised on purpose: AS's
zoning skills are NYC-only, and nothing here should assume them.
"""

from __future__ import annotations

import json
import re

from .model import Finding, FindingSet

_JSON_FENCE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_key(key: str) -> str:
    """'Max Floor Area' -> 'max_floor_area'."""
    return _NON_ALNUM.sub("_", key.strip().lower()).strip("_")


def _section(markdown: str, heading: str) -> str:
    """Return the lines under '## <heading>', stopping at the next '## '."""
    lines = markdown.splitlines()
    target = f"## {heading}"
    start = None
    for index, line in enumerate(lines):
        if line.strip() == target:
            start = index + 1
            break
    if start is None:
        raise ValueError(f"heading {heading!r} not found")

    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


def extract_data_block(markdown: str, heading: str) -> dict:
    """Parse the first fenced json block under the given '## ' heading."""
    match = _JSON_FENCE.search(_section(markdown, heading))
    if match is None:
        raise ValueError(f"no fenced json block under heading {heading!r}")
    return json.loads(match.group(1))


def findings_from_stats(
    stats: dict,
    source: str,
    confidence: str = "sourced",
) -> FindingSet:
    """Convert a flat stats dict into a FindingSet with provenance attached."""
    findings = FindingSet()
    for key, value in stats.items():
        findings.add(
            Finding(
                key=normalize_key(key),
                value=str(value),
                source=source,
                confidence=confidence,
            )
        )
    return findings
```

- [ ] **Step 5: Export the new names**

Modify `mcp_server/src/rook/findings/__init__.py` to read:

```python
"""Source-neutral contract for researched findings that drive parameters."""

from .architecture_studio import (
    extract_data_block,
    findings_from_stats,
    normalize_key,
)
from .model import CONFIDENCE_LEVELS, Finding, FindingSet

__all__ = [
    "CONFIDENCE_LEVELS",
    "Finding",
    "FindingSet",
    "extract_data_block",
    "findings_from_stats",
    "normalize_key",
]
```

- [ ] **Step 6: Run the full findings test suite**

Run: `mcp_server/.venv/Scripts/python -m pytest mcp_server/tests/test_findings_model.py mcp_server/tests/test_findings_architecture_studio.py -v`
Expected: PASS, 16 passed

- [ ] **Step 7: Commit**

```bash
git add mcp_server/src/rook/findings/ mcp_server/tests/test_findings_architecture_studio.py mcp_server/tests/fixtures/as_report_sample.md
git commit -m "feat(findings): Architecture Studio data-block reader"
```

---

### Task 3: Live spine run — findings drive geometry through a planner

**Files:**
- Create: `mcp_server/tests/test_findings_spine_live.py`
- Reference: `docs/superpowers/specs/2026-08-01-reasoning-as-dataflow-design.md`

**Interfaces:**
- Consumes: `extract_data_block`, `findings_from_stats`, `FindingSet.to_brief` from Tasks 1–2.
- Produces: a documented, repeatable live procedure and a recorded result. No new library code.

**Preconditions — verify before starting, and stop if any fail:**

1. Rhino is running with Rook loaded. Verify: `rhino_ping` returns `"pong"`.
2. Grasshopper is open with an empty document. Verify: `gh_snapshot` returns an epoch and zero components.
3. The Chirp adapter is running (`python -m chirp` from `C:\UDEV\Chirp`). Verify: a `chirp-service-{port}.json` file exists in `%TEMP%/rook/`.
4. `ANTHROPIC_API_KEY` is set in Chirp's `.env`.

- [ ] **Step 1: Build the brief from the fixture**

Run in the venv:

```bash
mcp_server/.venv/Scripts/python -c "from pathlib import Path; from rook.findings import extract_data_block, findings_from_stats; md = Path('mcp_server/tests/fixtures/as_report_sample.md').read_text(encoding='utf-8'); block = extract_data_block(md, 'Envelope Data'); print(findings_from_stats(block['stats'], source='/as:zoning-analysis-nyc').to_brief())"
```

Expected output, exactly two lines:

```
commercial_far: 10.0 [sourced; source: /as:zoning-analysis-nyc]
max_floor_area: 218,620 SF [sourced; source: /as:zoning-analysis-nyc]
```

Record this string — it is the planner's Brief input.

- [ ] **Step 2: Resolve component GUIDs from the knowledge store**

Do **not** hardcode GUIDs. Call:

```
gh_knowledge_query(intent="rectangle from plane with x and y sizes")
gh_knowledge_query(intent="extrude a curve along a vector to make a solid")
gh_knowledge_query(intent="unit z vector scaled by a number")
```

Record the returned GUIDs. If any query returns no confident match, call `gh_query_patterns` with the same intent before proceeding.

- [ ] **Step 3: Create the planner node**

Call `chirp_create`:

```
chirp_create(
  category="planner",
  signature="brief -> floor_to_floor, bay_count",
  pins_in=["Brief:string"],
  pins_out=["FloorToFloor:float", "BayCount:int"],
  name="Massing Planner",
  x=100,
  y=200
)
```

Do not declare `Correction` or `Reasoning` — `chirp_create` adds both automatically.

- [ ] **Step 4: Wire the definition**

Take a snapshot, then apply one atomic edit using the GUIDs from Step 2 and the short IDs from the snapshot:

```
snap = gh_snapshot()
gh_edit(
  epoch=snap["epoch"],
  create=[ ... Panel (Brief text), Rectangle, Unit Z, Extrude ... ],
  set_values=[ ... Panel := the exact brief string from Step 1 ... ],
  connect=[ ... Panel.O0 > Planner.I0,
             Planner.O0 (FloorToFloor) > UnitZ factor,
             Rectangle.O0 > Extrude curve,
             UnitZ.O0 > Extrude direction ... ]
)
```

Wire the planner's `FloorToFloor` output into the Z-vector magnitude so the extrusion height is set by reasoning over the findings, not by a hardcoded number. Leave `BayCount` unconnected in this slice — it exists to prove multi-output typing.

- [ ] **Step 5: Verify the canvas solved cleanly**

Call `gh_errors`.
Expected: zero components with errors. If the Chirp node errors, the most likely causes are the adapter not running or a pin-type mismatch — check the discovery file in `%TEMP%/rook/` first.

- [ ] **Step 6: Verify geometry exists and reasoning is populated**

Call `gh_snapshot` after the solve settles, and confirm:

1. The Extrude component has a Brep output with non-empty data.
2. The planner's `Reasoning` output pin contains non-empty text.
3. The planner's `FloorToFloor` output is a number, and it is plausible given the brief.

**This is the thesis check.** Record the actual `Reasoning` text verbatim in the results file — it is the evidence that the parameter was derived from the findings rather than invented.

- [ ] **Step 7: Verify caching — the determinism check**

Force a re-solve without changing the Brief (nudge an unrelated slider, or toggle the Extrude preview). Then confirm from Chirp's JSONL trace in the Chirp repo that the second call was a **cache hit** (`cached: true`) and that `FloorToFloor` is unchanged.

Expected: cache hit, identical value. If it re-called the LLM, check that `CHIRP_CACHE` is not set to `false`.

- [ ] **Step 8: Record the result**

Create `mcp_server/tests/test_findings_spine_live.py` as a documented skip-by-default record:

```python
"""Live spine run: findings -> planner -> typed parameters -> geometry.

Requires Rhino + Grasshopper + the Chirp adapter. Skipped by default; run the
procedure in docs/superpowers/plans/2026-08-01-findings-to-parameters-spine.md
Task 3 by hand and paste the observed values into RECORDED_RESULT below.
"""

import pytest

RECORDED_RESULT = {
    "brief_lines": 2,
    "reasoning_text": "",       # paste verbatim from Step 6
    "floor_to_floor": None,     # observed value
    "bay_count": None,          # observed value
    "second_solve_cached": None,  # True expected, from Step 7
}


@pytest.mark.skip(reason="live run; requires Rhino, Grasshopper and Chirp adapter")
def test_spine_produced_geometry_from_findings():
    assert RECORDED_RESULT["reasoning_text"], "no reasoning captured"
    assert RECORDED_RESULT["floor_to_floor"] is not None
    assert RECORDED_RESULT["second_solve_cached"] is True
```

- [ ] **Step 9: Commit**

```bash
git add mcp_server/tests/test_findings_spine_live.py
git commit -m "test(findings): record live spine run evidence"
```

---

## Self-review

**Spec coverage.** This plan covers slice 1 only: the findings contract, the AS reader, and the live spine link. Slices 2–5 are explicitly out of scope and separately planned. The AS "research" leg is exercised (Task 2 reads a real AS report format); the "project record" and "delivery" legs are not touched in this slice and do not need to be.

**Deferred by decision.** Stale-state semantics are out of scope per the spec's open problem 1. Task 3 Step 7 verifies only that the existing input-keyed cache behaves as freeze-by-default; it does not attempt change detection.

**Known soft spot.** Task 3 Step 4 describes the wiring in prose rather than exact `gh_edit` arguments, because the short IDs come from a runtime snapshot and the GUIDs from a runtime knowledge query — neither can honestly be written in advance. The implementer must resolve both at execution time. This is the one place in the plan where a step cannot be fully pre-specified, and it is called out rather than papered over.

**Type consistency.** `Finding`, `FindingSet`, `extract_data_block`, `findings_from_stats`, `normalize_key` are used with identical signatures in Tasks 2 and 3 as defined in Tasks 1 and 2. Pin names `FloorToFloor` and `BayCount` are consistent between Task 3 Steps 3, 4, 6 and 8.

---

## Next

After this slice returns evidence, plan slice 2 (Correction pin → `editor` round trip), which is the first half of the human-in-the-loop story.
