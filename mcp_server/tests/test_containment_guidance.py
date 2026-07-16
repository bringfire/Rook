"""Current-guidance containment checks for legacy semantic tool identities."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from rook import server
from rook.agent.chat import chat_runner
from rook.agent.chat.prompt_builder import PromptBuilder
from rook.agent.tool_dispatcher import build_local_tools


EXPECTED_RED = "EXPECTED_RED:T6:GUIDANCE"
REPO_ROOT = Path(__file__).resolve().parents[2]

CONTAINED_IDENTITIES = (
    "gh_execute_intent",
    "rhino_execute_intent",
    "plan_and_execute",
    "spawn_agent",
    "gh_explore_workflow",
    "gh_replay_recipe",
)

TOP_CURRENT_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "AGENT_SETUP.md",
    "README.md",
    ".claude/hookify.rhino-command-safety.local.md",
    ".claude/hookify.rhino-execute-safety.local.md",
    "installer/CLAUDE.md",
    "installer/AGENTS.md",
    "docs/ONBOARDING_NEW_CLAUDE.md",
    "docs/TROUBLESHOOTING.md",
    "docs/AGENT_ARCHITECTURE.md",
    "docs/CURRENT_ARCHITECTURE.md",
    "docs/rook_docs/POSITIONING.md",
    "docs/rook_docs/work-queue.md",
    "scripts/session-start.sh",
    "mcp_server/src/rook/server.py",
    "mcp_server/src/rook/learning/dspy_signatures.py",
    "mcp_server/src/rook/agent/chat/prompt_builder.py",
    "mcp_server/src/rook/agent/chat/chat_runner.py",
    "mcp_server/src/rook/agent/prompts/WORKER.md",
    "mcp_server/src/rook/agent/personas/architect/role.md",
    "mcp_server/src/rook/agent/personas/explorer/role.md",
    "mcp_server/src/rook/agent/personas/worker/role.md",
    "mcp_server/tests/test_e2e_agents.py",
)

SKILL_SUFFIXES = (
    "_template/SKILL.md",
    "_template/references/gotchas.md",
    "_template/references/knowledge-integration.md",
    "chirp-cascade/references/wasp-grammar-authoring.md",
    "consolidate/SKILL.md",
    "consolidate/references/consolidation-paths.md",
    "design-grasshopper/references/wasp-domain-context.md",
    "design-grasshopper/references/wasp-rhino-scaffold.md",
    "design-road/references/road-rhino-scaffold.md",
    "execute-grasshopper/SKILL.md",
    "execute-grasshopper/references/checkpoint-protocol.md",
    "plan-grasshopper/SKILL.md",
    "plan-grasshopper/references/tool-call-patterns.md",
    "plan-grasshopper/references/wasp/wasp-aggregate.md",
    "plan-grasshopper/references/wasp/wasp-catalog.md",
    "plan-grasshopper/references/wasp/wasp-constraints.md",
    "plan-grasshopper/references/wasp/wasp-disco-export.md",
    "plan-grasshopper/references/wasp/wasp-field.md",
    "plan-grasshopper/references/wasp/wasp-grammar-aggregate.md",
    "plan-grasshopper/references/wasp/wasp-hierarchy.md",
    "plan-grasshopper/references/wasp/wasp-learn.md",
    "plan-grasshopper/references/wasp/wasp-parts.md",
    "plan-grasshopper/references/wasp/wasp-rules.md",
    "plan-grasshopper/references/wasp/wasp-save-load.md",
    "twisted-column/SKILL.md",
    "twisted-column/references/hollowing-gotchas.md",
    "validate-security/SKILL.md",
)

INSTALLED_FILES = (
    "installer/agent-assets/codex-skills/chirp-cascade/references/wasp-grammar-authoring.md",
    "installer/agent-assets/codex-skills/design-grasshopper/references/wasp-domain-context.md",
    "installer/agent-assets/codex-skills/design-grasshopper/references/wasp-rhino-scaffold.md",
    "installer/agent-assets/codex-skills/design-road/references/road-rhino-scaffold.md",
    "installer/agent-assets/codex-skills/execute-grasshopper/references/checkpoint-protocol.md",
    "installer/agent-assets/codex-skills/execute-grasshopper/SKILL.md",
    "installer/agent-assets/codex-skills/plan-grasshopper/references/tool-call-patterns.md",
    "installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-aggregate.md",
    "installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-catalog.md",
    "installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-constraints.md",
    "installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-disco-export.md",
    "installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-field.md",
    "installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-grammar-aggregate.md",
    "installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-hierarchy.md",
    "installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-learn.md",
    "installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-parts.md",
    "installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-rules.md",
    "installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-save-load.md",
    "installer/agent-assets/codex-skills/plan-grasshopper/SKILL.md",
    "installer/agent-assets/codex-skills/twisted-column/references/hollowing-gotchas.md",
    "installer/agent-assets/codex-skills/twisted-column/SKILL.md",
)

SKILL_FILES = tuple(
    f"{root}/{suffix}"
    for root in (".agents/skills", ".claude/skills")
    for suffix in SKILL_SUFFIXES
)

_SOURCE_ONLY_FILES = {
    "mcp_server/src/rook/server.py",
    "mcp_server/src/rook/agent/chat/chat_runner.py",
}
_LIFECYCLE_WORDING = re.compile(r"\b(?:contained|retired|suspended)\b", re.I)


def _fail(findings: list[str]) -> None:
    if findings:
        joined = "\n".join(f"- {finding}" for finding in findings)
        raise AssertionError(f"{EXPECTED_RED}\n{joined}")


def _identity_hits(text: str) -> tuple[str, ...]:
    return tuple(name for name in CONTAINED_IDENTITIES if name in text)


def _line_findings(relative_path: str, text: str) -> list[str]:
    findings: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        hits = _identity_hits(line)
        if hits and not _LIFECYCLE_WORDING.search(line):
            findings.append(
                f"{relative_path}:{line_number}: active reference to "
                f"{', '.join(hits)}: {line.strip()[:180]}"
            )
    return findings


def _schema_findings(label: str, schemas: list[object]) -> list[str]:
    findings: list[str] = []
    for schema in schemas:
        if isinstance(schema, dict):
            function = schema.get("function", {})
            name = function.get("name", "") if isinstance(function, dict) else ""
            description = (
                function.get("description", "")
                if isinstance(function, dict)
                else ""
            )
        else:
            name = getattr(schema, "name", "")
            description = getattr(schema, "description", "")
        hits = _identity_hits(f"{name}\n{description}")
        if hits:
            findings.append(
                f"{label}: model-visible schema {name!r} references "
                f"{', '.join(hits)}"
            )
    return findings


def _catalog_schemas(catalog: dict[str, dict]) -> list[dict]:
    return list(catalog.values())


def test_exact_scope_installer_contract_and_mirror_equality() -> None:
    findings: list[str] = []
    exact_scope = (
        ("mcp_server/tests/test_containment_guidance.py",)
        + TOP_CURRENT_FILES
        + SKILL_FILES
        + INSTALLED_FILES
    )
    if len(exact_scope) != 100 or len(set(exact_scope)) != 100:
        findings.append(
            f"Task 6 scope must contain exactly 100 unique paths, got "
            f"{len(exact_scope)} paths / {len(set(exact_scope))} unique"
        )
    for relative_path in exact_scope:
        if not (REPO_ROOT / relative_path).is_file():
            findings.append(f"missing pinned Task 6 path: {relative_path}")

    installer_text = (REPO_ROOT / "installer/RookSetup.iss").read_text(
        encoding="utf-8"
    )
    shipment_lines = [
        line
        for line in installer_text.splitlines()
        if "{#CodexCuratedSkillsDir}\\*" in line
    ]
    if len(shipment_lines) != 1:
        findings.append(
            "RookSetup.iss must contain exactly one curated Codex skill "
            "shipment entry"
        )
    elif not all(
        token in shipment_lines[0]
        for token in ("recursesubdirs", "createallsubdirs")
    ):
        findings.append(
            "RookSetup.iss no longer recursively ships the curated Codex "
            "skill tree"
        )

    for suffix in SKILL_SUFFIXES:
        agents = REPO_ROOT / ".agents/skills" / suffix
        claude = REPO_ROOT / ".claude/skills" / suffix
        if agents.is_file() and claude.is_file() and agents.read_bytes() != claude.read_bytes():
            findings.append(f"paired skill copies differ: {suffix}")

    installed_root = REPO_ROOT / "installer/agent-assets/codex-skills"
    for relative_path in INSTALLED_FILES:
        installed = REPO_ROOT / relative_path
        suffix = installed.relative_to(installed_root).as_posix()
        source = REPO_ROOT / ".agents/skills" / suffix
        if installed.is_file() and source.is_file() and installed.read_bytes() != source.read_bytes():
            findings.append(f"installed mirror differs from source: {suffix}")

    _fail(findings)


def test_current_guidance_and_recursively_shipped_text_are_clean() -> None:
    findings: list[str] = []

    for relative_path in TOP_CURRENT_FILES:
        if relative_path in _SOURCE_ONLY_FILES:
            continue
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        if relative_path == "docs/AGENT_ARCHITECTURE.md":
            banner = "\n".join(text.splitlines()[:30])
            missing = [
                name for name in CONTAINED_IDENTITIES if name not in banner
            ]
            if missing or not _LIFECYCLE_WORDING.search(banner):
                findings.append(
                    "docs/AGENT_ARCHITECTURE.md lacks a visible lifecycle "
                    f"supersession banner for: {', '.join(missing)}"
                )
            continue
        if relative_path == "docs/rook_docs/work-queue.md":
            current_prefix = text.split("**Last triaged:**", 1)[0]
            missing = [
                name
                for name in CONTAINED_IDENTITIES
                if name not in current_prefix
            ]
            if missing or not _LIFECYCLE_WORDING.search(current_prefix):
                findings.append(
                    "docs/rook_docs/work-queue.md lacks a current lifecycle "
                    f"supersession note for: {', '.join(missing)}"
                )
            findings.extend(_line_findings(relative_path, current_prefix))
            continue
        findings.extend(_line_findings(relative_path, text))

    for relative_path in SKILL_FILES:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        findings.extend(_line_findings(relative_path, text))

    installed_root = REPO_ROOT / "installer/agent-assets/codex-skills"
    allowed_installed = set(INSTALLED_FILES)
    for path in sorted(installed_root.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits = _identity_hits(text)
        if not hits:
            continue
        if relative_path not in allowed_installed:
            findings.append(
                "recursively shipped positive match lies outside the pinned "
                f"21-file inventory: {relative_path}: {', '.join(hits)}"
            )
        findings.extend(_line_findings(relative_path, text))

    _fail(findings)


def test_twisted_column_examples_follow_copy_and_centroid_contracts() -> None:
    relative_path = ".agents/skills/twisted-column/SKILL.md"
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    findings: list[str] = []

    copy_calls = text.count("rhino_copy(")
    copied_id_reads = text.count('["copies"][0]["newId"]')
    if copied_id_reads != copy_calls:
        findings.append(
            f"{relative_path}: {copy_calls} rhino_copy examples require "
            f"copies[0].newId extraction, found {copied_id_reads}"
        )

    centroid_calls = text.count("rhino_measure_centroid(")
    centroid_reads = text.count('["centroid"]')
    if centroid_reads != centroid_calls:
        findings.append(
            f"{relative_path}: {centroid_calls} centroid examples require "
            f"the top-level centroid field, found {centroid_reads}"
        )

    for forbidden, contract in (
        (
            "inner_id = rhino_copy(",
            "do not pass the whole rhino_copy result as an object ID",
        ),
        (
            'result["ids"]',
            "rhino_copy returns copies[].newId, not ids",
        ),
        (
            'centroid["point"]',
            "rhino_measure_centroid returns centroid, not point",
        ),
    ):
        if forbidden in text:
            findings.append(f"{relative_path}: {contract}: {forbidden}")

    _fail(findings)


def test_final_model_visible_schemas_and_prompts_are_clean(monkeypatch) -> None:
    findings: list[str] = []

    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    monkeypatch.delenv("ROOK_MCP_TOOL_PROFILE", raising=False)
    full = asyncio.run(server.list_tools())
    if len(full) != 422:
        findings.append(f"default full MCP surface has {len(full)} tools, expected 422")
    findings.extend(_schema_findings("default full MCP surface", full))

    monkeypatch.setenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", "1")
    interactive = asyncio.run(server.list_tools())
    if len(interactive) != 425:
        findings.append(
            f"interactive MCP surface has {len(interactive)} tools, expected 425"
        )
    findings.extend(_schema_findings("interactive MCP surface", interactive))

    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    for profile, expected_count in (("lean", 20), ("readonly", 148)):
        monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)
        tools = asyncio.run(server.list_tools())
        if len(tools) != expected_count:
            findings.append(
                f"{profile} MCP surface has {len(tools)} tools, "
                f"expected {expected_count}"
            )
        findings.extend(_schema_findings(f"{profile} MCP surface", tools))

    fallback = chat_runner._build_fallback_catalog()
    findings.extend(
        _schema_findings("RookChat fallback catalog", _catalog_schemas(fallback))
    )
    local = chat_runner._build_local_tool_catalog(build_local_tools())
    findings.extend(
        _schema_findings("RookChat local catalog", _catalog_schemas(local))
    )

    runner = chat_runner.ChatRunner(
        tool_executor=lambda _name, _arguments: None,
        catalog=fallback,
    )
    findings.extend(
        _schema_findings(
            "RookChat active registry",
            runner._registry.get_active_schemas(),
        )
    )

    builder = PromptBuilder()
    for persona in ("architect", "explorer", "worker"):
        prompt = builder.build_system(persona)
        hits = _identity_hits(prompt)
        if hits:
            findings.append(
                f"RookChat {persona} prompt references {', '.join(hits)}"
            )

    chat_runner_source = (
        REPO_ROOT / "mcp_server/src/rook/agent/chat/chat_runner.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        '"rhino_execute_intent":',
        "_RHINO_EXECUTE_INTENT_SCHEMA",
    ):
        if forbidden in chat_runner_source:
            findings.append(
                f"RookChat source still contains fallback artifact {forbidden}"
            )

    _fail(findings)
