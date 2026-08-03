from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIRROR_ROOTS = (
    ROOT / ".agents" / "skills",
    ROOT / ".claude" / "skills",
    ROOT / "installer" / "agent-assets" / "codex-skills",
)
RETAINED = ("design-grasshopper", "plan-grasshopper", "execute-grasshopper")


def _inventory(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


@pytest.mark.parametrize("skill", RETAINED)
def test_retained_skill_mirrors_are_byte_identical(skill: str) -> None:
    inventories = [_inventory(root / skill) for root in MIRROR_ROOTS]
    assert inventories[0]
    assert inventories[1:] == inventories[:-1]


def test_design_is_read_only_and_uses_trigger_only_frontmatter() -> None:
    root = MIRROR_ROOTS[0] / "design-grasshopper"
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = skill.split("---", 2)[1]
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in root.rglob("*.md")
    )
    assert "Use when a Grasshopper request is ambiguous or open-ended" in frontmatter
    assert "This stage is read-only" in skill
    assert "plan-grasshopper" not in frontmatter
    assert "execute-grasshopper" not in frontmatter
    for forbidden in (
        "Skill(",
        "Read(",
        "gh_query(",
        "gh_edit(",
        "rhino_create(",
        "rhino_execute(",
        "rhino_boolean(",
        "rhino_layer_create(",
    ):
        assert forbidden not in combined


def test_design_has_one_compact_wasp_admission_reference() -> None:
    root = MIRROR_ROOTS[0] / "design-grasshopper"
    assert set(_inventory(root)) == {
        "SKILL.md",
        "references/explore-checklist.md",
        "references/wasp-admission.md",
    }
    admission = (root / "references" / "wasp-admission.md").read_text(encoding="utf-8")
    for required in ("gh_library", "gh_batch_component_info", "zero mutation", "non-executable"):
        assert required in admission


def test_plan_is_optional_read_only_and_has_durable_baseline() -> None:
    root = MIRROR_ROOTS[0] / "plan-grasshopper"
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = skill.split("---", 2)[1]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.md"))
    assert "Use when Grasshopper work is large, destructive, cross-session" in frontmatter
    assert "This stage is read-only" in skill
    assert "structural baseline" in skill
    assert "document identity" in skill
    assert "ownership" in skill
    assert "preservation" in skill
    assert "does not store an epoch" in skill
    assert "design-grasshopper" not in frontmatter
    assert "execute-grasshopper" not in frontmatter
    for forbidden in ("Skill(", "Read(", "gh_query(", "gh_delete(", "gh_set_value(", "gh_canvas_cleanup("):
        assert forbidden not in combined
    assert not (root / "references" / "wasp").exists()
    assert "../design-grasshopper/references/wasp-admission.md" in skill
