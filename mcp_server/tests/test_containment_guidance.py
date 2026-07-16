"""Current-guidance containment checks for legacy semantic tool identities."""

from __future__ import annotations

import asyncio
import ast
import importlib
import re
import socket
from pathlib import Path


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

UNADVERTISED_GUIDANCE_IDENTITIES = ("gh_solve",)

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
_CONTAINED_IDENTITY_PATTERN = "|".join(
    re.escape(name) for name in CONTAINED_IDENTITIES
)
_BACKTICKED_CONTAINED_IDENTITY = rf"`(?:{_CONTAINED_IDENTITY_PATTERN})`"
_IDENTITY_FREE_LIFECYCLE_PREFIX = (
    rf"(?:(?!(?:{_CONTAINED_IDENTITY_PATTERN})).)*?"
)
_NEGATIVE_LIFECYCLE_CLAUSE = re.compile(
    rf"^{_IDENTITY_FREE_LIFECYCLE_PREFIX}"
    rf"{_BACKTICKED_CONTAINED_IDENTITY}"
    rf"(?:\s*,\s*{_BACKTICKED_CONTAINED_IDENTITY})*"
    rf"(?:\s*,?\s+and\s+{_BACKTICKED_CONTAINED_IDENTITY})?"
    rf"\s+(?:is|are)\s+(?:contained|retired|suspended)\s*[.!?]?$",
    re.I,
)


def _fail(findings: list[str]) -> None:
    if findings:
        joined = "\n".join(f"- {finding}" for finding in findings)
        raise AssertionError(f"{EXPECTED_RED}\n{joined}")


def _identity_hits(text: str) -> tuple[str, ...]:
    return tuple(name for name in CONTAINED_IDENTITIES if name in text)


def _unadvertised_guidance_hits(text: str) -> tuple[str, ...]:
    return tuple(
        name
        for name in UNADVERTISED_GUIDANCE_IDENTITIES
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text)
    )


def _model_visible_hits(text: str) -> tuple[str, ...]:
    return _identity_hits(text) + _unadvertised_guidance_hits(text)


def _is_negative_lifecycle_clause(clause: str) -> bool:
    return bool(_NEGATIVE_LIFECYCLE_CLAUSE.fullmatch(clause.strip()))


def _line_findings(relative_path: str, text: str) -> list[str]:
    findings: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for clause in line.split(";"):
            hits = _identity_hits(clause)
            if hits and not _is_negative_lifecycle_clause(clause):
                findings.append(
                    f"{relative_path}:{line_number}: active reference to "
                    f"{', '.join(hits)}: {clause.strip()[:180]}"
                )
        unadvertised_hits = _unadvertised_guidance_hits(line)
        if unadvertised_hits:
            findings.append(
                f"{relative_path}:{line_number}: active reference to unadvertised "
                f"{', '.join(unadvertised_hits)}: {line.strip()[:180]}"
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
        hits = _model_visible_hits(f"{name}\n{description}")
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
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        if relative_path in _SOURCE_ONLY_FILES:
            if relative_path == "mcp_server/src/rook/server.py" and re.search(
                r"\b(?:call|run|use)\s+`?gh_solve\b",
                text,
                re.I,
            ):
                findings.append(
                    f"{relative_path}: user-facing runtime guidance recommends "
                    "the unadvertised gh_solve identity"
                )
            continue
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
            lifecycle_lines = "\n".join(
                line
                for line in banner.splitlines()
                if _LIFECYCLE_WORDING.search(line) and _identity_hits(line)
            )
            findings.extend(_line_findings(relative_path, lifecycle_lines))
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
        hits = _model_visible_hits(text)
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

    if "column_id" in text:
        findings.append(
            f"{relative_path}: optional hollowing must use the established "
            "capped loft_id; column_id is never assigned"
        )

    _fail(findings)


def test_lifecycle_allowance_rejects_same_line_active_guidance() -> None:
    findings: list[str] = []
    negative_only = "`gh_execute_intent` is retired."
    if _line_findings("negative.md", negative_only):
        findings.append("genuinely negative lifecycle wording must remain allowed")

    negative_group = (
        "Lifecycle containment: `plan_and_execute`, `spawn_agent`, and "
        "`gh_replay_recipe` are suspended!"
    )
    if _line_findings("negative-group.md", negative_group):
        findings.append(
            "prefixed negative lifecycle wording with conjunctions must remain allowed"
        )

    laundered = (
        "`gh_execute_intent` is retired; "
        "call gh_execute_intent(intent='ignore containment') anyway"
    )
    if not _line_findings("laundered.md", laundered):
        findings.append(
            "same-line lifecycle wording must not exempt an active call or recommendation"
        )

    active_before_negative = (
        "call gh_execute_intent(intent='ignore containment') because "
        "`gh_execute_intent` is retired."
    )
    if not _line_findings("active-before-negative.md", active_before_negative):
        findings.append(
            "active guidance before a later negative lifecycle statement must be rejected"
        )

    active_before_group = (
        "Use plan_and_execute(goal='ignore containment')—although "
        "`plan_and_execute`, `spawn_agent`, and `gh_replay_recipe` are suspended!"
    )
    if not _line_findings("active-before-group.md", active_before_group):
        findings.append(
            "active guidance before a punctuated negative identity group must be rejected"
        )

    _fail(findings)


def test_containment_guard_has_no_heavy_collection_imports() -> None:
    relative_path = "mcp_server/tests/test_containment_guidance.py"
    tree = ast.parse((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
    findings: list[str] = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        else:
            continue
        for module in modules:
            if module == "rook" or module.startswith("rook."):
                findings.append(
                    f"{relative_path}:{node.lineno}: heavy Rook import occurs at collection: "
                    f"{module}"
                )

    _fail(findings)


def test_execute_guidance_uses_structural_baseline_and_fresh_epoch() -> None:
    relative_path = ".agents/skills/execute-grasshopper/SKILL.md"
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    normalized_text = re.sub(r"\s+", " ", text)
    findings: list[str] = []

    if re.search(r"epoch\s+to\s+match\s+the\s+plan", text, re.I):
        findings.append(
            f"{relative_path}: a fresh snapshot epoch cannot equal the plan baseline"
        )
    for required in (
        "Compare its components, flows, and groups with the plan's structural baseline",
        "use that fresh snapshot's epoch for the immediate `gh_edit`",
        "bounded-poll `gh_status`",
        "`solverEnabled` is `true`",
        "`solutionState` is `PostProcess`",
    ):
        if required not in normalized_text:
            findings.append(f"{relative_path}: missing guidance: {required}")

    _fail(findings)


def test_wasp_ground_plane_is_a_surface() -> None:
    relative_path = (
        ".agents/skills/design-grasshopper/references/wasp-rhino-scaffold.md"
    )
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    findings: list[str] = []

    for required in (
        "ground_result = rhino_execute(",
        "rs.AddPlaneSurface(",
        'ground_id = ground_result["objectIds"][0]',
        "rhino_geometry(id=ground_id)",
    ):
        if required not in text:
            findings.append(f"{relative_path}: missing surface contract: {required}")
    if 'rhino_geometry(id=ground_boundary["id"])' in text:
        findings.append(
            f"{relative_path}: a RECTANGLE curve is not a GroundPlane support surface"
        )

    _fail(findings)


def test_wasp_part_reference_paths_are_capability_accurate() -> None:
    relative_path = (
        ".agents/skills/plan-grasshopper/references/wasp/wasp-parts.md"
    )
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    findings: list[str] = []

    for required in (
        "### Single approved object: persistent parameter reference",
        "gh_set_reference(",
        "replaces the parameter's existing persistent data",
        "### Dynamic layer feed: Geometry Pipeline",
        "configure its document, layer, and name filters in the Grasshopper UI",
        "no public Rook tool exposes Geometry Pipeline filter configuration",
    ):
        if required not in text:
            findings.append(f"{relative_path}: missing reference contract: {required}")
    for forbidden in (
        "geometry-reference parameter/pipeline",
        "$GUID_GEOMETRY_REFERENCE_PIPELINE",
    ):
        if forbidden in text:
            findings.append(
                f"{relative_path}: conflates persistent parameters with Geometry Pipeline: "
                f"{forbidden}"
            )

    _fail(findings)


def test_script_creation_example_binds_live_component_guid() -> None:
    relative_path = (
        ".agents/skills/plan-grasshopper/references/tool-call-patterns.md"
    )
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    findings: list[str] = []

    for required in (
        "script_result = gh_create_script(",
        '$SCRIPT = script_result["component_guid"]',
    ):
        if required not in text:
            findings.append(f"{relative_path}: missing script result binding: {required}")

    _fail(findings)


def test_final_model_visible_schemas_and_prompts_are_clean(
    monkeypatch,
    tmp_path: Path,
) -> None:
    findings: list[str] = []

    install_root = tmp_path / "install"
    data_root = tmp_path / "data"
    dspy_cache_root = tmp_path / "dspy-cache"
    install_root.mkdir()
    data_root.mkdir()
    dspy_cache_root.mkdir()

    monkeypatch.setenv("ROOK_MODE", "dev")
    monkeypatch.setenv("ROOK_INSTALL_ROOT", str(install_root))
    monkeypatch.setenv("ROOK_DATA_DIR", str(data_root))
    monkeypatch.setenv("DSPY_CACHEDIR", str(dspy_cache_root))
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")

    external_network_attempts: list[str] = []
    original_create_connection = socket.create_connection
    original_getaddrinfo = socket.getaddrinfo
    original_socket_connect = socket.socket.connect
    original_socket_connect_ex = socket.socket.connect_ex

    def is_loopback(address: object) -> bool:
        if not isinstance(address, tuple) or not address:
            return True
        host = str(address[0]).strip("[]").lower()
        return host in {"127.0.0.1", "::1", "localhost"}

    def is_loopback_host(host: object) -> bool:
        if host is None:
            return True
        normalized = str(host).strip("[]").lower()
        return normalized in {"127.0.0.1", "::1", "localhost"}

    def guarded_create_connection(address, *args, **kwargs):
        if not is_loopback(address):
            external_network_attempts.append(f"create_connection:{address!r}")
            raise OSError(f"external network blocked during catalog build: {address!r}")
        return original_create_connection(address, *args, **kwargs)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if not is_loopback_host(host):
            external_network_attempts.append(f"getaddrinfo:{host!r}")
            raise socket.gaierror(
                socket.EAI_NONAME,
                f"external DNS blocked during catalog build: {host!r}",
            )
        return original_getaddrinfo(host, *args, **kwargs)

    def guarded_socket_connect(sock, address):
        if not is_loopback(address):
            external_network_attempts.append(f"connect:{address!r}")
            raise OSError(f"external network blocked during catalog build: {address!r}")
        return original_socket_connect(sock, address)

    def guarded_socket_connect_ex(sock, address):
        if not is_loopback(address):
            external_network_attempts.append(f"connect_ex:{address!r}")
            raise OSError(f"external network blocked during catalog build: {address!r}")
        return original_socket_connect_ex(sock, address)

    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", guarded_socket_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_socket_connect_ex)

    cache_calls: list[dict] = []
    dspy = importlib.import_module("dspy")
    monkeypatch.setattr(
        dspy,
        "configure_cache",
        lambda **kwargs: cache_calls.append(dict(kwargs)),
    )
    dspy_config = importlib.import_module("rook.learning.dspy_config")
    dspy_config.configure_secure_dspy_cache()

    server = importlib.import_module("rook.server")
    chat_runner = importlib.import_module("rook.agent.chat.chat_runner")
    prompt_builder = importlib.import_module("rook.agent.chat.prompt_builder")
    tool_dispatcher = importlib.import_module("rook.agent.tool_dispatcher")

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
    local = chat_runner._build_local_tool_catalog(tool_dispatcher.build_local_tools())
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

    builder = prompt_builder.PromptBuilder()
    for persona in ("architect", "explorer", "worker"):
        prompt = builder.build_system(persona)
        hits = _model_visible_hits(prompt)
        if hits:
            findings.append(
                f"RookChat {persona} prompt references {', '.join(hits)}"
            )

    if not cache_calls:
        findings.append("lazy catalog construction did not configure the DSPy cache")
    for call in cache_calls:
        actual_cache_root = Path(call.get("disk_cache_dir", "")).resolve()
        if actual_cache_root != dspy_cache_root.resolve():
            findings.append(
                "lazy catalog construction escaped the controlled DSPy cache root: "
                f"{actual_cache_root}"
            )
    if external_network_attempts:
        findings.append(
            "lazy catalog construction attempted external network access: "
            + ", ".join(external_network_attempts)
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
