from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "installer" / "agent-assets" / "prime-skills" / "rook-full"


def _read(relative: str) -> str:
    return (SKILL_ROOT / relative).read_text(encoding="utf-8", errors="strict")


def test_rook_full_is_one_markdown_only_skill_package() -> None:
    root = _read("SKILL.md")
    assert root.startswith("---\nname: rook-full\n")
    assert (SKILL_ROOT / "references" / "grasshopper.md").is_file()
    assert (SKILL_ROOT / "references" / "receipts-and-evidence.md").is_file()
    assert not (SKILL_ROOT / "pyproject.toml").exists()
    assert not (SKILL_ROOT / "src").exists()


def test_root_skill_contains_the_persistent_rookchat_operating_contract() -> None:
    root = _read("SKILL.md")
    for required in (
        "await goal.get()",
        "await goal.create(",
        "await goal.complete()",
        "substantive",
        "Stop",
        "reopen",
        'await mcp.call_tool("rook", "rook_tools_search"',
        'await mcp.call_tool("rook", "rook_tools_read"',
        'await mcp.call_tool("rook", "rook_tools_call"',
        '"success"',
        "receipt",
        "readiness",
        "fenced",
        "no-op",
        "ambiguous",
        "20 seconds",
        "60 seconds",
        "IPython",
    ):
        assert required in root

    lowered = root.lower()
    assert "campaign" not in lowered
    assert "permanent readonly" not in lowered
    assert "c:/users/" not in lowered
    assert "d:/" not in lowered


def test_references_keep_domain_and_evidence_detail_out_of_the_root_contract() -> None:
    grasshopper = _read("references/grasshopper.md")
    evidence = _read("references/receipts-and-evidence.md")

    assert "expectedGhDocumentId" in grasshopper
    assert "gh_document_open" in grasshopper
    assert "gh_update_script" in grasshopper
    assert "same captured document" in grasshopper

    assert "authentic unique receipt" in evidence
    assert "same-receipt" in evidence
    assert "Never replay" in evidence
    assert "success: false" in evidence
