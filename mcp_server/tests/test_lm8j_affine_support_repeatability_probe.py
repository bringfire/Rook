from __future__ import annotations

import ast
import importlib.util
import sys
import subprocess
import json
from pathlib import Path

import pytest


_LM8I_PROBE_MODULE = "lm8i_affine_publication_shape_support_probe"
_WRAPPER_ALLOWED_IMPORT_ROOTS = frozenset(
    {
        "__future__",
        "argparse",
        "collections",
        "datetime",
        "json",
        "math",
        "pathlib",
        "re",
        "subprocess",
        "sys",
        "typing",
    }
)
_LIVE_DISPATCH_SEAMS = frozenset(
    {
        "_mcp_tool_executor",
        "apply_gh_scalar_value_action_to_node",
        "call_rhino",
        "call_tool",
        "gh_connect",
        "gh_create_component",
        "gh_create_slider",
        "gh_document_new",
        "gh_get_value",
        "gh_inspect_output",
        "gh_library",
        "gh_set_value",
        "gh_solve",
        "gh_wait_for_solve_readiness",
        "rhino_ping",
        "run_two_pass_worker_publication",
    }
)
_LIVE_DISPATCH_ENTRYPOINTS = frozenset(
    {
        "dispatch",
        "execute",
        "invoke",
        "tool_executor",
        *_LIVE_DISPATCH_SEAMS,
    }
)
_DYNAMIC_IMPORT_CALLS = frozenset({"__import__", "import_module"})
_PROCESS_SPAWN_APIS = frozenset(
    {
        "asyncio.create_subprocess_exec",
        "asyncio.create_subprocess_shell",
        "concurrent.futures.ProcessPoolExecutor",
        "multiprocessing.Pool",
        "multiprocessing.Process",
        "os.execl",
        "os.execle",
        "os.execlp",
        "os.execlpe",
        "os.execv",
        "os.execve",
        "os.execvp",
        "os.execvpe",
        "os.popen",
        "os.posix_spawn",
        "os.posix_spawnp",
        "os.spawnl",
        "os.spawnle",
        "os.spawnlp",
        "os.spawnlpe",
        "os.spawnv",
        "os.spawnve",
        "os.spawnvp",
        "os.spawnvpe",
        "os.startfile",
        "os.system",
        "subprocess.Popen",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.getoutput",
        "subprocess.getstatusoutput",
        "subprocess.run",
    }
)


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm8j_affine_support_repeatability_probe.py"
    )


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _target_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.Tuple, ast.List)):
        return set().union(*(_target_names(element) for element in node.elts))
    return set()


def _is_lm8i_module(module_name: str) -> bool:
    return module_name == _LM8I_PROBE_MODULE or module_name.endswith(
        f".{_LM8I_PROBE_MODULE}"
    )


def _is_live_reference(node: ast.AST, aliases: set[str]) -> bool:
    name = _dotted_name(node)
    if name is None:
        return False
    return name in aliases or name.rsplit(".", 1)[-1] in _LIVE_DISPATCH_SEAMS


def _call_has_live_tool_name(node: ast.Call) -> bool:
    return any(
        isinstance(value, ast.Constant)
        and isinstance(value.value, str)
        and value.value in _LIVE_DISPATCH_SEAMS
        for argument in (*node.args, *(keyword.value for keyword in node.keywords))
        for value in ast.walk(argument)
    )


def _process_reference(
    node: ast.AST,
    module_aliases: dict[str, str],
    process_aliases: dict[str, str],
) -> str | None:
    name = _dotted_name(node)
    if name in process_aliases:
        return process_aliases[name]
    if name is not None:
        parts = name.split(".")
        canonical = ".".join((module_aliases.get(parts[0], parts[0]), *parts[1:]))
        if canonical in _PROCESS_SPAWN_APIS:
            return canonical

    if (
        isinstance(node, ast.Call)
        and _dotted_name(node.func) == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    ):
        module_name = _dotted_name(node.args[0])
        if module_name is not None:
            canonical_module = module_aliases.get(module_name, module_name)
            canonical = f"{canonical_module}.{node.args[1].value}"
            if canonical in _PROCESS_SPAWN_APIS:
                return canonical
    return None


def _process_reference_from_value(
    node: ast.AST,
    module_aliases: dict[str, str],
    process_aliases: dict[str, str],
) -> str | None:
    reference = _process_reference(node, module_aliases, process_aliases)
    if reference is not None:
        return reference
    if isinstance(node, ast.BoolOp):
        references = {
            reference
            for value in node.values
            if (
                reference := _process_reference_from_value(
                    value, module_aliases, process_aliases
                )
            )
            is not None
        }
        return next(iter(references)) if len(references) == 1 else None
    if isinstance(node, ast.IfExp):
        references = {
            reference
            for value in (node.body, node.orelse)
            if (
                reference := _process_reference_from_value(
                    value, module_aliases, process_aliases
                )
            )
            is not None
        }
        return next(iter(references)) if len(references) == 1 else None
    return None


def _assignment_value_and_targets(
    node: ast.AST,
) -> tuple[ast.AST | None, list[ast.AST]]:
    if isinstance(node, ast.Assign):
        return node.value, node.targets
    if isinstance(node, ast.AnnAssign) and node.value is not None:
        return node.value, [node.target]
    return None, []


def _module_call_sites(
    tree: ast.Module,
) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef | None, ast.Call]]:
    call_sites = []
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            owner_name = statement.name
            owner = statement
        else:
            owner_name = "<module>"
            owner = None
        call_sites.extend(
            (owner_name, owner, node)
            for node in ast.walk(statement)
            if isinstance(node, ast.Call)
        )
    return call_sites


def _node_owners(tree: ast.Module) -> dict[int, str]:
    owners: dict[int, str] = {}
    for statement in tree.body:
        owner_name = (
            statement.name
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
            else "<module>"
        )
        for node in ast.walk(statement):
            owners[id(node)] = owner_name
    return owners


def _node_parents(tree: ast.Module) -> dict[int, ast.AST]:
    return {
        id(child): parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }


def _command_is_from_lm8i_builder(
    owner: ast.FunctionDef | ast.AsyncFunctionDef | None,
    process_call: ast.Call,
) -> bool:
    command = process_call.args[0] if process_call.args else next(
        (
            keyword.value
            for keyword in process_call.keywords
            if keyword.arg in {"args", "command"}
        ),
        None,
    )
    if isinstance(command, ast.Call):
        return _dotted_name(command.func) == "_lm8i_command"
    if owner is None or not isinstance(command, ast.Name):
        return False

    assignments = []
    for node in ast.walk(owner):
        value, targets = _assignment_value_and_targets(node)
        if value is None or getattr(node, "lineno", 0) >= process_call.lineno:
            continue
        if command.id in set().union(*(_target_names(target) for target in targets)):
            assignments.append(node)
    if not assignments:
        return False
    nearest = max(assignments, key=lambda node: node.lineno)
    value, _targets = _assignment_value_and_targets(nearest)
    return isinstance(value, ast.Call) and _dotted_name(value.func) == "_lm8i_command"


def _is_exact_git_short_sha_call(
    owner_name: str,
    process_call: ast.Call,
) -> bool:
    if owner_name != "_git_short_sha" or not process_call.args:
        return False
    command = process_call.args[0]
    if not isinstance(command, ast.List):
        return False
    command_values = [
        element.value if isinstance(element, ast.Constant) else None
        for element in command.elts
    ]
    if command_values != ["git", "rev-parse", "--short", "HEAD"]:
        return False
    keywords = {keyword.arg: keyword.value for keyword in process_call.keywords}
    return (
        set(keywords) == {"cwd", "check", "capture_output", "text"}
        and isinstance(keywords["cwd"], ast.Name)
        and keywords["cwd"].id == "_REPO_ROOT"
        and all(
            isinstance(keywords[name], ast.Constant)
            and keywords[name].value is True
            for name in ("check", "capture_output", "text")
        )
    )


def _lm8m_wrapper_guard_violations(source: str) -> list[str]:
    """Return import and call paths that would let the wrapper dispatch live work."""

    tree = ast.parse(source)
    violations: list[str] = []
    aliases = set(_LIVE_DISPATCH_SEAMS)
    module_aliases: dict[str, str] = {}
    process_aliases: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name
                terminal_name = module_name.rsplit(".", 1)[-1]
                module_aliases[alias.asname or module_name.split(".", 1)[0]] = (
                    module_name
                )
                if module_name == "rook.server" or _is_lm8i_module(module_name):
                    violations.append(f"forbidden module import:{module_name}")
                if module_name.split(".", 1)[0] not in _WRAPPER_ALLOWED_IMPORT_ROOTS:
                    violations.append(f"non-wrapper import:{module_name}")
                if terminal_name in _LIVE_DISPATCH_SEAMS:
                    violations.append(f"live seam import:{module_name}")
                    aliases.add(alias.asname or module_name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            if module_name == "rook.server" or _is_lm8i_module(module_name):
                violations.append(f"forbidden module import:{module_name}")
            if module_name and module_name.split(".", 1)[0] not in _WRAPPER_ALLOWED_IMPORT_ROOTS:
                violations.append(f"non-wrapper import:{module_name}")
            for alias in node.names:
                imported_name = alias.name
                qualified_name = f"{module_name}.{imported_name}" if module_name else imported_name
                local_name = alias.asname or imported_name
                if qualified_name in _PROCESS_SPAWN_APIS:
                    process_aliases[local_name] = qualified_name
                if qualified_name == "rook.server" or _is_lm8i_module(qualified_name):
                    violations.append(f"forbidden module import:{qualified_name}")
                if imported_name in _LIVE_DISPATCH_SEAMS:
                    violations.append(f"live seam import:{qualified_name}")
                    aliases.add(alias.asname or imported_name)

    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            value = None
            targets: list[ast.AST] = []
            if isinstance(node, ast.Assign):
                value = node.value
                targets = node.targets
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                value = node.value
                targets = [node.target]
            if value is not None and _is_live_reference(value, aliases):
                for target in targets:
                    for target_name in _target_names(target):
                        if target_name not in aliases:
                            aliases.add(target_name)
                            changed = True

    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            value, targets = _assignment_value_and_targets(node)
            if value is None:
                continue
            process_reference = _process_reference_from_value(
                value, module_aliases, process_aliases
            )
            if process_reference is None:
                continue
            for target in targets:
                for target_name in _target_names(target):
                    if process_aliases.get(target_name) != process_reference:
                        process_aliases[target_name] = process_reference
                        changed = True

    parents = _node_parents(tree)
    owners = _node_owners(tree)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Name, ast.Attribute, ast.Call)):
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            continue
        process_reference = _process_reference(
            node, module_aliases, process_aliases
        )
        if process_reference is None:
            continue
        parent = parents.get(id(node))
        owner_name = owners.get(id(node), "<module>")
        allowed = False
        if process_reference == "subprocess.run" and owner_name == "_git_short_sha":
            allowed = (
                isinstance(parent, ast.Call)
                and parent.func is node
                and _is_exact_git_short_sha_call(owner_name, parent)
            )
        elif process_reference == "subprocess.run" and owner_name == "_run_probe":
            allowed = (
                isinstance(parent, ast.BoolOp)
                and node in parent.values
                and isinstance(parents.get(id(parent)), ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "runner"
                    for target in parents[id(parent)].targets
                )
            ) or (
                isinstance(parent, ast.Call)
                and parent.func is node
                and _command_is_from_lm8i_builder(
                    next(
                        statement
                        for statement in tree.body
                        if isinstance(statement, ast.FunctionDef)
                        and statement.name == "_run_probe"
                    ),
                    parent,
                )
            )
        if not allowed:
            violations.append(
                "forbidden direct process reference:"
                f"{owner_name}:{process_reference}"
            )

    for statement in tree.body:
        if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(statement):
            if not isinstance(node, ast.Return) or node.value is None:
                continue
            returned_process_reference = _process_reference_from_value(
                node.value, module_aliases, process_aliases
            )
            if returned_process_reference is not None:
                violations.append(
                    "forbidden process reference return:"
                    f"{statement.name}:{returned_process_reference}"
                )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = _dotted_name(node.func)
        terminal_name = call_name.rsplit(".", 1)[-1] if call_name else ""
        if terminal_name in _DYNAMIC_IMPORT_CALLS:
            violations.append(f"dynamic import call:{call_name}")
        if _is_live_reference(node.func, aliases):
            violations.append(f"live seam call:{call_name}")
        if (
            terminal_name in _LIVE_DISPATCH_ENTRYPOINTS
            or (call_name is not None and call_name in aliases)
        ) and _call_has_live_tool_name(node):
            violations.append(f"live tool dispatch:{call_name}")

    allowed_process_call_count = 0
    for owner_name, owner, call in _module_call_sites(tree):
        for argument in (*call.args, *(keyword.value for keyword in call.keywords)):
            passed_process_reference = _process_reference_from_value(
                argument, module_aliases, process_aliases
            )
            if passed_process_reference is not None:
                violations.append(
                    "forbidden process spawn:"
                    f"{owner_name}:process-api-argument:{passed_process_reference}"
                )
        process_reference = _process_reference(
            call.func, module_aliases, process_aliases
        )
        if process_reference is None:
            continue
        if (
            process_reference == "subprocess.run"
            and owner_name == "_run_probe"
            and _command_is_from_lm8i_builder(owner, call)
        ):
            allowed_process_call_count += 1
            continue
        if process_reference == "subprocess.run" and _is_exact_git_short_sha_call(
            owner_name, call
        ):
            continue
        call_name = _dotted_name(call.func) or "<dynamic>"
        violations.append(
            f"forbidden process spawn:{owner_name}:{call_name}:{process_reference}"
        )

    if allowed_process_call_count != 1:
        violations.append(
            "intended LM8I process spawn count:"
            f"expected=1:actual={allowed_process_call_count}"
        )

    return violations


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm8j_affine_support_repeatability_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical_lm8j_shape():
    args = PROBE._args([])

    assert args.attempts == 20
    assert args.model == "gemma4:12b-it-qat"
    assert args.run_dir == "probe_runs"
    assert args.attempt_timeout_s == 600
    assert args.verifier_profile == PROBE.SETTLE_VERIFIER_PROFILE
    assert (
        PROBE._canonical_evidence(
            attempts=args.attempts,
            model=args.model,
            attempt_timeout_s=args.attempt_timeout_s,
        )
        is True
    )


def test_default_run_identity_is_unchanged():
    assert PROBE._run_identity(PROBE.SETTLE_VERIFIER_PROFILE) == (
        "lm8j",
        PROBE.SCRIPT_SCHEMA,
    )


def test_managed_run_identity_is_lm8m():
    assert PROBE._run_identity(PROBE.MANAGED_VERIFIER_PROFILE) == (
        "lm8m",
        PROBE.LM8M_SCRIPT_SCHEMA,
    )


def test_cli_rejects_non_positive_attempts_and_timeout():
    for argv in (
        ["--attempts", "0"],
        ["--attempts", "-1"],
        ["--attempt-timeout-s", "0"],
        ["--attempt-timeout-s", "-2"],
    ):
        with pytest.raises(SystemExit):
            PROBE._args(argv)


def test_canonical_evidence_only_for_twenty_default_gemma_default_timeout_attempts():
    assert (
        PROBE._canonical_evidence(
            attempts=20,
            model="gemma4:12b-it-qat",
            attempt_timeout_s=600,
        )
        is True
    )
    assert (
        PROBE._canonical_evidence(
            attempts=5,
            model="gemma4:12b-it-qat",
            attempt_timeout_s=600,
        )
        is False
    )
    assert (
        PROBE._canonical_evidence(
            attempts=20,
            model="qwen3:14b",
            attempt_timeout_s=600,
        )
        is False
    )
    assert (
        PROBE._canonical_evidence(
            attempts=20,
            model="gemma4:12b-it-qat",
            attempt_timeout_s=1,
        )
        is False
    )


def test_managed_canonical_evidence_requires_historical_run_values():
    assert PROBE.READINESS_WAIT_TIMEOUT_MS == 10_000
    assert (
        PROBE._canonical_evidence(
            attempts=20,
            model="gemma4:12b-it-qat",
            attempt_timeout_s=600,
            verifier_profile="managed_receipt_v2",
        )
        is True
    )
    assert (
        PROBE._canonical_evidence(
            attempts=20,
            model="gemma4:12b-it-qat",
            attempt_timeout_s=599,
            verifier_profile="managed_receipt_v2",
        )
        is False
    )


def test_cli_rejects_non_lm8j_surfaces():
    forbidden = (
        ["--retry-clean-observation"],
        ["--planner-provider-command", "x"],
        ["--prompt-profile", "shape_guidance_v2"],
        ["--request-json", "request.json"],
        ["--gh-edit"],
        ["--phase", "receipt_recon"],
        ["--support-disabled"],
        ["--support-forced"],
    )
    for argv in forbidden:
        with pytest.raises(SystemExit):
            PROBE._args(argv)


def test_manifest_records_lm8j_identity():
    manifest = PROBE._manifest(
        attempts=20,
        model="gemma4:12b-it-qat",
        attempt_timeout_s=600,
    )

    assert manifest["schema"] == "rook.lm8j_affine_support_repeatability_probe:v1"
    assert manifest["attempts"] == 20
    assert manifest["model"] == "gemma4:12b-it-qat"
    assert manifest["attempt_timeout_s"] == 600
    assert manifest["canonical_evidence"] is True
    assert manifest["child_probe"] == "lm8i_affine_publication_shape_support_probe.py"
    assert manifest["child_probe_invocation"] == "subprocess"
    assert manifest["support_mode"] == "lm8i_default_support_enabled"
    assert "verifier_profile" not in manifest
    assert "verifier_mechanism" not in manifest
    assert "fixture_readiness_profile" not in manifest
    assert "readiness_wait_timeout_ms" not in manifest


def test_managed_manifest_records_lm8m_identity_and_metadata():
    manifest = PROBE._manifest(
        attempts=20,
        model="gemma4:12b-it-qat",
        attempt_timeout_s=600,
        verifier_profile=PROBE.MANAGED_VERIFIER_PROFILE,
    )

    assert manifest["schema"] == PROBE.LM8M_SCRIPT_SCHEMA
    assert manifest["canonical_evidence"] is True
    assert manifest["verifier_profile"] == PROBE.MANAGED_VERIFIER_PROFILE
    assert manifest["verifier_mechanism"] == PROBE.VERIFIER_MECHANISM
    assert manifest["fixture_readiness_profile"] == PROBE.FIXTURE_READINESS_PROFILE
    assert manifest["readiness_wait_timeout_ms"] == PROBE.READINESS_WAIT_TIMEOUT_MS


def test_scheduled_attempt_id_is_stable():
    assert PROBE._scheduled_attempt_id(1) == "attempt-001"
    assert PROBE._scheduled_attempt_id(20) == "attempt-020"


def test_base_attempt_row_has_lm8j_fields():
    row = PROBE._base_attempt_row(attempt_index=1)

    assert row["attempt_index"] == 1
    assert row["scheduled_attempt_id"] == "attempt-001"
    assert row["lm8i_invoked"] is False
    assert row["lm8i_returncode"] is None
    assert row["lm8i_run_dir"] is None
    assert row["terminal_category"] is None
    assert row["publication_support_attempted"] is False
    assert row["publication_support_count"] == 0
    assert row["support_eligible"] is None
    assert row["support_recovered"] is False
    assert row["leak_check_performed"] is False
    assert row["leak_marker_match_count"] == 0


def test_lm8i_command_uses_sys_executable_and_child_run_dir(tmp_path: Path):
    runs_dir = tmp_path / "lm8i_runs"

    command = PROBE._lm8i_command(
        model="gemma4:12b-it-qat",
        lm8i_runs_dir=runs_dir,
    )

    assert command == [
        sys.executable,
        str(PROBE._REPO_ROOT / "scripts" / "lm8i_affine_publication_shape_support_probe.py"),
        "--model",
        "gemma4:12b-it-qat",
        "--run-dir",
        str(runs_dir),
    ]
    assert "--retry-clean-observation" not in command
    assert "--gh-edit" not in command
    assert "--support-forced" not in command
    assert "--support-disabled" not in command


def test_default_child_command_is_exact_historical_shape(tmp_path: Path):
    command = PROBE._lm8i_command(
        model=PROBE.DEFAULT_MODEL,
        lm8i_runs_dir=tmp_path,
        verifier_profile=PROBE.SETTLE_VERIFIER_PROFILE,
    )

    assert "--verifier-profile" not in command


def test_managed_child_command_forwards_only_profile(tmp_path: Path):
    command = PROBE._lm8i_command(
        model=PROBE.DEFAULT_MODEL,
        lm8i_runs_dir=tmp_path,
        verifier_profile=PROBE.MANAGED_VERIFIER_PROFILE,
    )

    assert command[-2:] == ["--verifier-profile", "managed_receipt_v2"]
    assert "--readiness-wait-timeout-ms" not in command


@pytest.mark.parametrize(
    "verifier_profile",
    [PROBE.SETTLE_VERIFIER_PROFILE, PROBE.MANAGED_VERIFIER_PROFILE],
)
def test_lm8i_child_command_uses_only_the_exact_script_and_allowed_flags(
    tmp_path: Path, verifier_profile: str
):
    command = PROBE._lm8i_command(
        model=PROBE.DEFAULT_MODEL,
        lm8i_runs_dir=tmp_path,
        verifier_profile=verifier_profile,
    )
    expected_script = str(
        PROBE._REPO_ROOT / "scripts" / "lm8i_affine_publication_shape_support_probe.py"
    )

    assert command[0] == sys.executable
    assert command[1] == expected_script
    assert "-c" not in command
    assert [argument for argument in command if argument.endswith(".py")] == [
        expected_script
    ]
    assert {argument for argument in command if argument.startswith("--")} <= {
        "--model",
        "--run-dir",
        "--verifier-profile",
    }


def test_lm8i_command_builder_has_exact_control_and_payload_shape():
    tree = ast.parse(_script_path().read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_lm8i_command"
    )
    assert len(function.body) == 4
    validate, assign, profile_if, returned = function.body
    assert isinstance(validate, ast.Expr)
    assert ast.unparse(validate.value) == "_run_identity(verifier_profile)"
    assert isinstance(assign, ast.Assign)
    assert [ast.unparse(target) for target in assign.targets] == ["command"]
    assert ast.unparse(assign.value) == (
        "[sys.executable, str(_REPO_ROOT / 'scripts' / "
        "'lm8i_affine_publication_shape_support_probe.py'), '--model', model, "
        "'--run-dir', str(lm8i_runs_dir)]"
    )
    assert isinstance(profile_if, ast.If)
    assert ast.unparse(profile_if.test) == (
        "verifier_profile == MANAGED_VERIFIER_PROFILE"
    )
    assert len(profile_if.body) == 1 and profile_if.orelse == []
    assert ast.unparse(profile_if.body[0]) == (
        "command.extend(['--verifier-profile', MANAGED_VERIFIER_PROFILE])"
    )
    assert isinstance(returned, ast.Return)
    assert ast.unparse(returned.value) == "command"


def test_lm8i_child_command_is_not_mutated_before_subprocess_call():
    tree = ast.parse(_script_path().read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_run_probe"
    )
    command_names = [
        node for node in ast.walk(function) if isinstance(node, ast.Name) and node.id == "command"
    ]
    assert sum(isinstance(node.ctx, ast.Store) for node in command_names) == 1
    assert sum(isinstance(node.ctx, ast.Load) for node in command_names) == 1
    command_load = next(node for node in command_names if isinstance(node.ctx, ast.Load))
    runner_call = next(
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "runner"
    )
    assert runner_call.args == [command_load]


def test_discover_child_run_dirs_uses_filesystem_delta(tmp_path: Path):
    runs_dir = tmp_path / "lm8i_runs"
    runs_dir.mkdir()
    existing = runs_dir / "lm8i-existing"
    existing.mkdir()
    ignored_file = runs_dir / "lm8i-file"
    ignored_file.write_text("not a run dir", encoding="utf-8")
    before = {path for path in runs_dir.glob("lm8i-*") if path.is_dir()}

    child = runs_dir / "lm8i-new"
    child.mkdir()

    assert PROBE._discover_child_run_dirs(runs_dir, before) == [child]


def test_completed_text_and_excerpt_handle_bytes_none_and_length():
    assert PROBE._completed_text(None) == ""
    assert PROBE._completed_text(b"abc") == "abc"
    assert PROBE._completed_text("xyz") == "xyz"

    assert PROBE._excerpt(None) == ""
    assert PROBE._excerpt("") == ""
    assert PROBE._excerpt("abcdef", limit=4) == "abcd"
    assert PROBE._excerpt("abc", limit=4) == "abc"


def test_single_child_dir_error_classifies_missing_and_ambiguous(tmp_path: Path):
    assert PROBE._single_child_dir_error([]) == (None, "child_run_dir_missing")

    first = tmp_path / "lm8i-a"
    second = tmp_path / "lm8i-b"
    first.mkdir()
    second.mkdir()

    assert PROBE._single_child_dir_error([first, second]) == (
        None,
        "child_run_dir_ambiguous",
    )
    assert PROBE._single_child_dir_error([first]) == (first, None)


def test_timeout_and_subprocess_error_rows_preserve_child_dir_when_present(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    child.mkdir()
    timeout = subprocess.TimeoutExpired(
        cmd=["python"],
        timeout=600,
        output="stdout before timeout",
        stderr="stderr before timeout",
    )

    timeout_row = PROBE._timeout_row(
        attempt_index=1,
        exc=timeout,
        child_run_dirs=[child],
    )
    assert timeout_row["terminal_category"] == "wrapper_error"
    assert timeout_row["failure_reason"] == "lm8i_timeout"
    assert timeout_row["child_run_dir_error"] is None
    assert timeout_row["lm8i_run_dir"] == str(child)
    assert timeout_row["stdout_excerpt"] == "stdout before timeout"
    assert timeout_row["stderr_excerpt"] == "stderr before timeout"

    error_row = PROBE._subprocess_error_row(
        attempt_index=2,
        exc=OSError("launch failed"),
        child_run_dirs=[child],
    )
    assert error_row["terminal_category"] == "wrapper_error"
    assert error_row["failure_reason"] == "lm8i_subprocess_error:OSError"
    assert error_row["child_run_dir_error"] is None
    assert error_row["lm8i_run_dir"] == str(child)


def _write_child_decision(child: Path, payload: dict) -> None:
    child.mkdir(parents=True, exist_ok=True)
    (child / "decision.json").write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )


def _write_managed_child_artifacts(
    run_dir: Path,
    *,
    decision="accepted",
    observed=7.5,
    receipt_hash="sha256:" + "a" * 64,
    session="session-1",
    mutation_epoch=13,
    prior_completed=41,
    solution_run=42,
):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "live_set_value_summary.json").write_text(
        json.dumps(
            {
                "managed_mutation": {
                    "schema": "rook.lm8l_managed_mutation_summary:v1",
                    "receipt_schema": "rook.gh_solve_readiness_receipt:v1",
                    "receipt_status": "pending",
                    "receipt_id_sha256": receipt_hash,
                    "document_session_id": session,
                    "mutation_epoch": mutation_epoch,
                    "solution_run_epoch": None,
                    "completed_solution_run_epoch": prior_completed,
                }
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "readiness_wait_summary.json").write_text(
        json.dumps(
            {
                "schema": "rook.lm8l_readiness_wait_summary:v1",
                "receipt_schema": "rook.gh_solve_readiness_receipt:v1",
                "requested_timeout_ms": 10_000,
                "readiness_wait_count": 1,
                "wait_status": "ready",
                "receipt_status": "ready",
                "receipt_id_sha256": receipt_hash,
                "document_session_id": session,
                "mutation_epoch": mutation_epoch,
                "solution_run_epoch": solution_run,
                "completed_solution_run_epoch": solution_run,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "verify_scalar_output_summary.json").write_text(
        json.dumps(
            {
                "schema": "rook.lm8l_fenced_output_verification_summary:v1",
                "verifier_profile": "managed_receipt_v2",
                "readiness_wait_timeout_ms": 10_000,
                "readiness_wait_count": 1,
                "fenced_output_read_count": 1,
                "settle_read_count": 0,
                "readiness_fenced": True,
                "receipt_id_sha256": receipt_hash,
                "document_session_id": session,
                "mutation_epoch": mutation_epoch,
                "solution_run_epoch": solution_run,
                "completed_solution_run_epoch": solution_run,
                "expected_output_value": 7.5,
                "observed_output_value": observed,
                "tolerance": 1e-9,
                "matched": True,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "decision.json").write_text(
        json.dumps(
            {
                "schema": "rook.lm8i_affine_publication_shape_support_decision:v1",
                "decision": decision,
                "reason": "verify_scalar_output_succeeded",
                "phase": "verify_scalar_output",
                "canonical_evidence": True,
                "live_set_value_dispatched": True,
                "worker_publication_ran": True,
                "managed_verifier": {
                    "schema": "rook.lm8l_managed_verifier_decision:v1",
                    "verifier_profile": "managed_receipt_v2",
                    "verifier_mechanism": "managed_solve_readiness_receipt",
                    "fixture_readiness_profile": "lm8i_legacy_setup_v1",
                    "readiness_wait_timeout_ms": 10_000,
                    "readiness_wait_count": 1,
                    "fenced_output_read_count": 1,
                    "settle_read_count": 0,
                    "failed_invariants": [],
                },
            }
        ),
        encoding="utf-8",
    )


_DELETE = object()


def _mutate_managed_artifact(
    run_dir: Path,
    filename: str,
    field_path: tuple[str, ...],
    value,
) -> None:
    path = run_dir / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    target = payload
    for field in field_path[:-1]:
        target = target[field]
    if value is _DELETE:
        del target[field_path[-1]]
    else:
        target[field_path[-1]] = value
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_audit_managed_child_accepts_complete_consistent_artifacts(tmp_path: Path):
    _write_managed_child_artifacts(tmp_path)

    audit = PROBE._audit_managed_child(tmp_path)

    assert audit["performed"] is True
    assert audit["valid"] is True
    assert audit["failures"] == []
    assert audit["readiness_wait_count"] == 1
    assert audit["readiness_wait_status"] == "ready"
    assert audit["readiness_failure_reason"] is None
    assert audit["fenced_output_read_count"] == 1
    assert audit["settle_read_count"] == 0
    assert audit["readiness_fenced"] is True
    assert audit["observed_output_value"] == 7.5
    assert audit["receipt_id_hashes_match"] is True
    assert audit["document_session_ids_match"] is True
    assert audit["mutation_epochs_match"] is True
    assert audit["solution_run_epochs_match"] is True
    assert audit["post_mutation_solution_run_advanced"] is True


def test_audit_managed_child_accepts_noncanonical_complete_artifacts(tmp_path: Path):
    _write_managed_child_artifacts(tmp_path)
    _mutate_managed_artifact(
        tmp_path,
        "decision.json",
        ("canonical_evidence",),
        False,
    )

    audit = PROBE._audit_managed_child(tmp_path)

    assert audit["valid"] is True
    assert audit["failures"] == []


@pytest.mark.parametrize(
    ("receipt_status", "decision_reason"),
    [
        ("solver_locked", "readiness_receipt_solver_locked"),
        ("unknown", "readiness_receipt_unknown"),
        ("unknown", "readiness_receipt_expired"),
    ],
)
def test_audit_managed_child_preserves_no_wait_terminal_mutation_reason(
    tmp_path: Path,
    receipt_status: str,
    decision_reason: str,
):
    _write_managed_child_artifacts(tmp_path)
    (tmp_path / "readiness_wait_summary.json").unlink()
    (tmp_path / "verify_scalar_output_summary.json").unlink()
    _mutate_managed_artifact(
        tmp_path,
        "live_set_value_summary.json",
        ("managed_mutation", "receipt_status"),
        receipt_status,
    )
    _mutate_managed_artifact(
        tmp_path,
        "decision.json",
        ("decision",),
        "rejected",
    )
    _mutate_managed_artifact(
        tmp_path,
        "decision.json",
        ("reason",),
        decision_reason,
    )
    _mutate_managed_artifact(
        tmp_path,
        "decision.json",
        ("phase",),
        "verifier_readiness",
    )

    audit = PROBE._audit_managed_child(tmp_path)

    assert audit["performed"] is True
    assert audit["readiness_wait_count"] == 0
    assert audit["readiness_failure_reason"] == decision_reason

    row = {
        "lm8i_run_dir": str(tmp_path),
        "lm8i_decision": "rejected",
        "terminal_category": "rejected",
        "failure_reason": None,
        "verifier_profile": PROBE.MANAGED_VERIFIER_PROFILE,
    }
    PROBE._apply_managed_child_audit(row)
    summary = PROBE._build_summary(
        [row],
        attempts=1,
        model=PROBE.DEFAULT_MODEL,
        attempt_timeout_s=PROBE.DEFAULT_ATTEMPT_TIMEOUT_S,
        verifier_profile=PROBE.MANAGED_VERIFIER_PROFILE,
    )

    assert summary["readiness_failure_reason_counts"] == {decision_reason: 1}


def test_audit_managed_child_does_not_classify_no_wait_pre_mutation_failure(
    tmp_path: Path,
):
    _write_managed_child_artifacts(tmp_path)
    (tmp_path / "readiness_wait_summary.json").unlink()
    (tmp_path / "verify_scalar_output_summary.json").unlink()
    _mutate_managed_artifact(
        tmp_path,
        "live_set_value_summary.json",
        ("managed_mutation",),
        _DELETE,
    )
    _mutate_managed_artifact(
        tmp_path,
        "decision.json",
        ("decision",),
        "rejected",
    )
    _mutate_managed_artifact(
        tmp_path,
        "decision.json",
        ("reason",),
        "gh_set_value_exception:RuntimeError",
    )
    _mutate_managed_artifact(
        tmp_path,
        "decision.json",
        ("phase",),
        "live_set_value",
    )

    audit = PROBE._audit_managed_child(tmp_path)

    assert audit["readiness_failure_reason"] is None


@pytest.mark.parametrize(
    "decision_reason",
    ["readiness_receipt_missing", "readiness_receipt_malformed"],
)
def test_audit_managed_child_counts_no_wait_missing_or_malformed_receipt(
    tmp_path: Path,
    decision_reason: str,
):
    _write_managed_child_artifacts(tmp_path)
    (tmp_path / "readiness_wait_summary.json").unlink()
    (tmp_path / "verify_scalar_output_summary.json").unlink()
    _mutate_managed_artifact(
        tmp_path,
        "live_set_value_summary.json",
        ("managed_mutation",),
        _DELETE,
    )
    for field_path, value in (
        (("decision",), "rejected"),
        (("reason",), decision_reason),
        (("phase",), "verifier_readiness"),
    ):
        _mutate_managed_artifact(
            tmp_path,
            "decision.json",
            field_path,
            value,
        )

    audit = PROBE._audit_managed_child(tmp_path)

    assert audit["readiness_wait_count"] == 0
    assert audit["readiness_failure_reason"] == decision_reason


@pytest.mark.parametrize(
    ("filename", "expected_failure"),
    [
        ("live_set_value_summary.json", "mutation_artifact_missing"),
        ("readiness_wait_summary.json", "wait_artifact_missing"),
        ("verify_scalar_output_summary.json", "read_artifact_missing"),
        ("decision.json", "decision_artifact_missing"),
    ],
)
def test_audit_managed_child_rejects_missing_artifacts(
    tmp_path: Path,
    filename: str,
    expected_failure: str,
):
    _write_managed_child_artifacts(tmp_path)
    (tmp_path / filename).unlink()

    audit = PROBE._audit_managed_child(tmp_path)

    assert audit["valid"] is False
    assert expected_failure in audit["failures"]


@pytest.mark.parametrize(
    ("filename", "content", "expected_failure"),
    [
        ("live_set_value_summary.json", "{bad", "mutation_artifact_malformed"),
        ("readiness_wait_summary.json", "[]", "wait_artifact_malformed"),
        ("verify_scalar_output_summary.json", "{bad", "read_artifact_malformed"),
        ("decision.json", "[]", "decision_artifact_malformed"),
    ],
)
def test_audit_managed_child_rejects_malformed_artifacts(
    tmp_path: Path,
    filename: str,
    content: str,
    expected_failure: str,
):
    _write_managed_child_artifacts(tmp_path)
    (tmp_path / filename).write_text(content, encoding="utf-8")

    audit = PROBE._audit_managed_child(tmp_path)

    assert audit["valid"] is False
    assert expected_failure in audit["failures"]


@pytest.mark.parametrize(
    ("filename", "field_path", "value", "expected_failure"),
    [
        (
            "live_set_value_summary.json",
            ("managed_mutation", "schema"),
            "wrong",
            "mutation_schema_invalid",
        ),
        (
            "live_set_value_summary.json",
            ("managed_mutation", "receipt_schema"),
            "wrong",
            "mutation_receipt_schema_invalid",
        ),
        (
            "readiness_wait_summary.json",
            ("schema",),
            "wrong",
            "wait_schema_invalid",
        ),
        (
            "readiness_wait_summary.json",
            ("receipt_schema",),
            "wrong",
            "wait_receipt_schema_invalid",
        ),
        (
            "verify_scalar_output_summary.json",
            ("schema",),
            "wrong",
            "read_schema_invalid",
        ),
        ("decision.json", ("schema",), "wrong", "decision_schema_invalid"),
        (
            "decision.json",
            ("managed_verifier", "schema"),
            "wrong",
            "managed_decision_schema_invalid",
        ),
        (
            "live_set_value_summary.json",
            ("managed_mutation", "receipt_id_sha256"),
            "sha256:ABC",
            "receipt_id_sha256_invalid",
        ),
        (
            "readiness_wait_summary.json",
            ("receipt_id_sha256",),
            "sha256:" + "b" * 64,
            "receipt_id_sha256_mismatch",
        ),
        (
            "readiness_wait_summary.json",
            ("document_session_id",),
            "session-2",
            "document_session_id_mismatch",
        ),
        (
            "live_set_value_summary.json",
            ("managed_mutation", "mutation_epoch"),
            0,
            "mutation_epoch_not_positive",
        ),
        (
            "readiness_wait_summary.json",
            ("mutation_epoch",),
            14,
            "mutation_epoch_mismatch",
        ),
        (
            "live_set_value_summary.json",
            ("managed_mutation", "solution_run_epoch"),
            42,
            "pending_solution_run_epoch_not_null",
        ),
        (
            "live_set_value_summary.json",
            ("managed_mutation", "completed_solution_run_epoch"),
            True,
            "pending_completed_solution_run_epoch_invalid",
        ),
        (
            "readiness_wait_summary.json",
            ("solution_run_epoch",),
            41,
            "post_mutation_solution_run_not_advanced",
        ),
        (
            "readiness_wait_summary.json",
            ("completed_solution_run_epoch",),
            43,
            "wait_completed_solution_run_mismatch",
        ),
        (
            "verify_scalar_output_summary.json",
            ("solution_run_epoch",),
            43,
            "read_solution_run_mismatch",
        ),
        (
            "verify_scalar_output_summary.json",
            ("completed_solution_run_epoch",),
            43,
            "read_completed_solution_run_mismatch",
        ),
        (
            "readiness_wait_summary.json",
            ("requested_timeout_ms",),
            9999,
            "readiness_wait_timeout_ms_invalid",
        ),
        (
            "verify_scalar_output_summary.json",
            ("readiness_wait_timeout_ms",),
            9999,
            "readiness_wait_timeout_ms_invalid",
        ),
        (
            "readiness_wait_summary.json",
            ("wait_status",),
            "timeout",
            "wait_status_not_ready",
        ),
        (
            "live_set_value_summary.json",
            ("managed_mutation", "receipt_status"),
            "ready",
            "mutation_receipt_status_not_pending",
        ),
        (
            "readiness_wait_summary.json",
            ("receipt_status",),
            "pending",
            "wait_receipt_status_not_ready",
        ),
        (
            "readiness_wait_summary.json",
            ("readiness_wait_count",),
            2,
            "readiness_wait_count_not_one",
        ),
        (
            "verify_scalar_output_summary.json",
            ("readiness_wait_count",),
            2,
            "readiness_wait_count_mismatch",
        ),
        (
            "verify_scalar_output_summary.json",
            ("fenced_output_read_count",),
            2,
            "fenced_output_read_count_not_one",
        ),
        (
            "verify_scalar_output_summary.json",
            ("settle_read_count",),
            1,
            "settle_read_count_not_zero",
        ),
        (
            "verify_scalar_output_summary.json",
            ("readiness_fenced",),
            False,
            "readiness_fenced_not_true",
        ),
        (
            "verify_scalar_output_summary.json",
            ("observed_output_value",),
            8.0,
            "observed_output_value_mismatch",
        ),
        (
            "verify_scalar_output_summary.json",
            ("tolerance",),
            1e-6,
            "scalar_tolerance_invalid",
        ),
        (
            "verify_scalar_output_summary.json",
            ("verifier_profile",),
            "settle_v1",
            "read_verifier_profile_invalid",
        ),
        (
            "decision.json",
            ("managed_verifier", "verifier_profile"),
            "settle_v1",
            "managed_decision_profile_invalid",
        ),
        (
            "decision.json",
            ("managed_verifier", "verifier_mechanism"),
            "settle_polling",
            "managed_decision_mechanism_invalid",
        ),
        (
            "decision.json",
            ("managed_verifier", "fixture_readiness_profile"),
            "other",
            "managed_decision_fixture_profile_invalid",
        ),
        (
            "decision.json",
            ("managed_verifier", "readiness_wait_timeout_ms"),
            9999,
            "managed_decision_timeout_mismatch",
        ),
        (
            "decision.json",
            ("managed_verifier", "readiness_wait_count"),
            2,
            "managed_decision_readiness_wait_count_mismatch",
        ),
        (
            "decision.json",
            ("managed_verifier", "fenced_output_read_count"),
            2,
            "managed_decision_fenced_output_read_count_mismatch",
        ),
        (
            "decision.json",
            ("managed_verifier", "settle_read_count"),
            1,
            "managed_decision_settle_read_count_mismatch",
        ),
        (
            "decision.json",
            ("managed_verifier", "failed_invariants"),
            ["stale"],
            "managed_decision_failed_invariants_not_empty",
        ),
    ],
)
def test_audit_managed_child_recomputes_each_invariant(
    tmp_path: Path,
    filename: str,
    field_path: tuple[str, ...],
    value,
    expected_failure: str,
):
    _write_managed_child_artifacts(tmp_path)
    _mutate_managed_artifact(tmp_path, filename, field_path, value)

    audit = PROBE._audit_managed_child(tmp_path)

    assert audit["valid"] is False
    assert expected_failure in audit["failures"]


@pytest.mark.parametrize(
    ("field_path", "contradictory", "expected_failure"),
    [
        (("schema",), "wrong", "decision_schema_invalid"),
        (("decision",), "rejected", "child_decision_not_accepted"),
        (("reason",), "verify_scalar_output_failed", "decision_reason_invalid"),
        (("phase",), "verifier_readiness", "decision_phase_invalid"),
        (
            ("live_set_value_dispatched",),
            False,
            "live_set_value_dispatched_not_true",
        ),
        (
            ("worker_publication_ran",),
            False,
            "worker_publication_ran_not_true",
        ),
        (("managed_verifier",), "wrong", "managed_decision_missing"),
        (
            ("managed_verifier", "schema"),
            "wrong",
            "managed_decision_schema_invalid",
        ),
        (
            ("managed_verifier", "verifier_profile"),
            "settle_v1",
            "managed_decision_profile_invalid",
        ),
        (
            ("managed_verifier", "verifier_mechanism"),
            "settle_polling",
            "managed_decision_mechanism_invalid",
        ),
        (
            ("managed_verifier", "fixture_readiness_profile"),
            "other",
            "managed_decision_fixture_profile_invalid",
        ),
        (
            ("managed_verifier", "readiness_wait_timeout_ms"),
            9999,
            "managed_decision_timeout_mismatch",
        ),
        (
            ("managed_verifier", "readiness_wait_count"),
            2,
            "managed_decision_readiness_wait_count_mismatch",
        ),
        (
            ("managed_verifier", "fenced_output_read_count"),
            2,
            "managed_decision_fenced_output_read_count_mismatch",
        ),
        (
            ("managed_verifier", "settle_read_count"),
            1,
            "managed_decision_settle_read_count_mismatch",
        ),
        (
            ("managed_verifier", "failed_invariants"),
            ["stale"],
            "managed_decision_failed_invariants_not_empty",
        ),
    ],
)
@pytest.mark.parametrize("missing", [False, True], ids=["contradictory", "missing"])
def test_audit_managed_accepted_child_requires_complete_decision_envelope(
    tmp_path: Path,
    field_path: tuple[str, ...],
    contradictory,
    expected_failure: str,
    missing: bool,
):
    _write_managed_child_artifacts(tmp_path)
    _mutate_managed_artifact(
        tmp_path,
        "decision.json",
        field_path,
        _DELETE if missing else contradictory,
    )

    audit = PROBE._audit_managed_child(tmp_path)

    assert audit["valid"] is False
    assert expected_failure in audit["failures"]


def test_apply_managed_child_audit_reclassifies_only_contradictory_acceptance(
    tmp_path: Path,
):
    accepted = tmp_path / "accepted"
    _write_managed_child_artifacts(accepted)
    _mutate_managed_artifact(
        accepted,
        "verify_scalar_output_summary.json",
        ("solution_run_epoch",),
        41,
    )
    accepted_row = {
        "lm8i_run_dir": str(accepted),
        "lm8i_decision": "accepted",
        "terminal_category": "accepted",
        "failure_reason": None,
    }

    PROBE._apply_managed_child_audit(accepted_row)

    assert accepted_row["terminal_category"] == "wrapper_error"
    assert (
        accepted_row["failure_reason"]
        == "accepted_child_managed_verifier_audit_failed"
    )
    assert accepted_row["managed_verifier_audit_performed"] is True
    assert accepted_row["managed_verifier_audit_valid"] is False
    assert "read_solution_run_mismatch" in accepted_row[
        "managed_verifier_audit_failures"
    ]

    rejected = tmp_path / "rejected"
    _write_managed_child_artifacts(rejected, decision="rejected", observed=8.0)
    _mutate_managed_artifact(
        rejected,
        "decision.json",
        ("managed_verifier", "failed_invariants"),
        ["fenced_output_scalar"],
    )
    rejected_row = {
        "lm8i_run_dir": str(rejected),
        "lm8i_decision": "rejected",
        "terminal_category": "rejected",
        "failure_reason": None,
    }

    PROBE._apply_managed_child_audit(rejected_row)

    assert rejected_row["terminal_category"] == "rejected"
    assert rejected_row["managed_verifier_audit_performed"] is True
    assert rejected_row["managed_verifier_audit_valid"] is False


def test_apply_managed_child_audit_is_not_applicable_before_mutation(tmp_path: Path):
    _write_child_decision(
        tmp_path,
        {
            "schema": "rook.lm8i_affine_publication_shape_support_decision:v1",
            "decision": "worker_declined",
            "reason": "worker_declined",
            "phase": "worker_publication",
            "canonical_evidence": True,
            "live_set_value_dispatched": False,
            "worker_publication_ran": True,
        },
    )
    row = {
        "lm8i_run_dir": str(tmp_path),
        "lm8i_decision": "worker_declined",
        "terminal_category": "worker_declined",
        "failure_reason": None,
    }

    PROBE._apply_managed_child_audit(row)

    assert row["terminal_category"] == "worker_declined"
    assert row["managed_verifier_audit_performed"] is False
    assert row["managed_verifier_audit_valid"] is None
    assert row["managed_verifier_audit_failures"] == []
    assert row["readiness_wait_count"] == 0
    assert row["fenced_output_read_count"] == 0
    assert row["settle_read_count"] == 0


@pytest.mark.parametrize(
    "remaining_stage_artifact",
    [
        "live_set_value_summary.json",
        "readiness_wait_summary.json",
        "verify_scalar_output_summary.json",
    ],
)
def test_apply_managed_child_audit_rejects_false_dispatch_with_stage_artifact(
    tmp_path: Path,
    remaining_stage_artifact: str,
):
    child = tmp_path / remaining_stage_artifact
    _write_managed_child_artifacts(child)
    for stage_artifact in (
        "live_set_value_summary.json",
        "readiness_wait_summary.json",
        "verify_scalar_output_summary.json",
    ):
        if stage_artifact != remaining_stage_artifact:
            (child / stage_artifact).unlink()
    _mutate_managed_artifact(
        child,
        "decision.json",
        ("decision",),
        "worker_declined",
    )
    _mutate_managed_artifact(
        child,
        "decision.json",
        ("live_set_value_dispatched",),
        False,
    )
    row = {
        "lm8i_run_dir": str(child),
        "lm8i_decision": "worker_declined",
        "terminal_category": "worker_declined",
        "failure_reason": None,
    }

    PROBE._apply_managed_child_audit(row)

    assert row["managed_verifier_audit_performed"] is True
    assert row["managed_verifier_audit_valid"] is False
    assert row["managed_verifier_audit_failures"]
    assert row["terminal_category"] == "worker_declined"


def test_apply_managed_child_audit_reclassifies_accepted_false_dispatch(
    tmp_path: Path,
):
    child = tmp_path / "accepted-false-dispatch"
    _write_managed_child_artifacts(child)
    _mutate_managed_artifact(
        child,
        "decision.json",
        ("live_set_value_dispatched",),
        False,
    )
    row = {
        "lm8i_run_dir": str(child),
        "lm8i_decision": "accepted",
        "terminal_category": "accepted",
        "failure_reason": None,
    }

    PROBE._apply_managed_child_audit(row)

    assert row["managed_verifier_audit_performed"] is True
    assert row["managed_verifier_audit_valid"] is False
    assert "live_set_value_dispatched_not_true" in row[
        "managed_verifier_audit_failures"
    ]
    assert row["terminal_category"] == "wrapper_error"
    assert (
        row["failure_reason"]
        == "accepted_child_managed_verifier_audit_failed"
    )


@pytest.mark.parametrize(
    "field_path, expected_failure",
    [
        (("expected_output_value",), "expected_output_value_mismatch"),
        (("observed_output_value",), "observed_output_value_mismatch"),
        (("tolerance",), "scalar_tolerance_invalid"),
    ],
)
def test_apply_managed_child_audit_rejects_oversized_json_numbers(
    tmp_path: Path,
    field_path: tuple[str, ...],
    expected_failure: str,
):
    child = tmp_path / "oversized-number"
    _write_managed_child_artifacts(child)
    _mutate_managed_artifact(
        child,
        "verify_scalar_output_summary.json",
        field_path,
        10**400,
    )
    row = {
        "lm8i_run_dir": str(child),
        "lm8i_decision": "accepted",
        "terminal_category": "accepted",
        "failure_reason": None,
    }

    PROBE._apply_managed_child_audit(row)

    assert row["managed_verifier_audit_performed"] is True
    assert row["managed_verifier_audit_valid"] is False
    assert expected_failure in row["managed_verifier_audit_failures"]
    assert row["terminal_category"] == "wrapper_error"
    assert (
        row["failure_reason"]
        == "accepted_child_managed_verifier_audit_failed"
    )


def test_read_decision_handles_missing_invalid_and_non_mapping(tmp_path: Path):
    missing, missing_error = PROBE._read_decision(tmp_path / "missing.json")
    assert missing is None
    assert missing_error == "lm8i_missing_decision_json"

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{bad", encoding="utf-8")
    invalid, invalid_error = PROBE._read_decision(invalid_path)
    assert invalid is None
    assert invalid_error == "lm8i_invalid_decision_json"

    invalid_utf8_path = tmp_path / "invalid_utf8.json"
    invalid_utf8_path.write_bytes(b"{\"decision\":\"accepted\"\xff")
    invalid_utf8, invalid_utf8_error = PROBE._read_decision(invalid_utf8_path)
    assert invalid_utf8 is None
    assert invalid_utf8_error == "lm8i_unreadable_decision_json:UnicodeDecodeError"

    list_path = tmp_path / "list.json"
    list_path.write_text("[]", encoding="utf-8")
    non_mapping, non_mapping_error = PROBE._read_decision(list_path)
    assert non_mapping is None
    assert non_mapping_error == "lm8i_decision_not_mapping"


def test_read_json_mapping_returns_none_for_invalid_utf8_json(tmp_path: Path):
    invalid = tmp_path / "invalid.json"
    invalid.write_bytes(b"{\"marker\": \"value\"\xff\xff\xff}")

    assert PROBE._read_json_mapping(invalid) is None


def test_classify_decision_preserves_known_lm8i_categories():
    for decision in (
        "accepted",
        "rejected",
        "worker_declined",
        "publication_failed",
        "gate_failed",
        "preflight_failed",
    ):
        assert PROBE._classify_decision({"decision": decision}) == (decision, None)


def test_classify_decision_rejects_unknown_or_missing_value():
    assert PROBE._classify_decision({}) == (
        "wrapper_error",
        "lm8i_missing_decision",
    )
    assert PROBE._classify_decision({"decision": "strange"}) == (
        "wrapper_error",
        "lm8i_unknown_decision:strange",
    )


def test_row_from_completed_accepted_lm8i_child_copies_support_metadata(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    _write_child_decision(
        child,
        {
            "decision": "accepted",
            "reason": "verify_scalar_output_succeeded",
            "worker_publication_ran": True,
            "live_fixture_created": True,
            "live_set_value_dispatched": True,
            "verify_scalar_output_ran": True,
            "scalar_runtime_ready": True,
            "observed_output_after": 7.5,
            "publication_support_attempted": True,
            "publication_support_count": 1,
            "support_eligible": True,
            "support_not_attempted_reason": None,
            "first_publication_status": "pass1_decision_invalid",
            "first_publication_failure_reason": "pass1_missing_action_id",
            "final_publication_status": "published",
            "final_publication_failure_reason": None,
            "final_worker_response_kind": "action_request",
        },
    )
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=0,
        stdout="run_dir=child decision=accepted",
        stderr="",
    )

    row = PROBE._row_from_completed_lm8i(
        attempt_index=1,
        completed=completed,
        child_run_dirs=[child],
    )

    assert row["lm8i_invoked"] is True
    assert row["lm8i_returncode"] == 0
    assert row["lm8i_run_dir"] == str(child)
    assert row["lm8i_decision"] == "accepted"
    assert row["lm8i_reason"] == "verify_scalar_output_succeeded"
    assert row["terminal_category"] == "accepted"
    assert row["failure_reason"] is None
    assert row["worker_publication_ran"] is True
    assert row["live_set_value_dispatched"] is True
    assert row["verify_scalar_output_ran"] is True
    assert row["scalar_runtime_ready"] is True
    assert row["observed_output_after"] == 7.5
    assert row["publication_support_attempted"] is True
    assert row["publication_support_count"] == 1
    assert row["support_eligible"] is True
    assert row["first_publication_failure_reason"] == "pass1_missing_action_id"
    assert row["final_publication_status"] == "published"
    assert row["final_worker_response_kind"] == "action_request"
    assert row["support_recovered"] is False


def test_row_from_completed_nonzero_returncode_is_wrapper_error(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    _write_child_decision(
        child,
        {
            "decision": "accepted",
            "reason": "verify_scalar_output_succeeded",
            "worker_publication_ran": True,
        },
    )
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=2,
        stdout="partial stdout",
        stderr="partial stderr",
    )

    row = PROBE._row_from_completed_lm8i(
        attempt_index=1,
        completed=completed,
        child_run_dirs=[child],
    )

    assert row["terminal_category"] == "wrapper_error"
    assert row["failure_reason"] == "lm8i_nonzero_returncode:2"
    assert row["child_run_dir_error"] is None
    assert row["lm8i_run_dir"] == str(child)
    assert row["lm8i_decision"] == "accepted"
    assert row["worker_publication_ran"] is True
    assert row["stdout_excerpt"] == "partial stdout"
    assert row["stderr_excerpt"] == "partial stderr"


def test_row_from_completed_with_unreadable_decision_json_is_wrapper_error(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    child.mkdir()
    (child / "decision.json").write_bytes(b"{\"decision\":\"accepted\"\xff")

    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=0,
        stdout="run_dir=child decision=accepted",
        stderr="",
    )

    row = PROBE._row_from_completed_lm8i(
        attempt_index=1,
        completed=completed,
        child_run_dirs=[child],
    )

    assert row["terminal_category"] == "wrapper_error"
    assert row["failure_reason"] == "lm8i_unreadable_decision_json:UnicodeDecodeError"
    assert row["lm8i_run_dir"] == str(child)


def test_copy_child_artifact_summaries_reads_worker_verifier_and_support_recovery(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    child.mkdir()
    (child / "worker_action.json").write_text(
        json.dumps({"input": {"value": 3.0}}),
        encoding="utf-8",
    )
    (child / "verify_scalar_output_summary.json").write_text(
        json.dumps({"attempt_count": 2, "observed_output_value": 7.5}),
        encoding="utf-8",
    )
    row = {
        "lm8i_run_dir": str(child),
        "publication_support_attempted": True,
        "support_recovered": False,
        "worker_action_value": None,
        "verifier_attempt_count": None,
        "observed_output_after": None,
    }

    PROBE._copy_child_artifact_summaries(row)

    assert row["worker_action_value"] == 3.0
    assert row["verifier_attempt_count"] == 2
    assert row["observed_output_after"] == 7.5
    assert row["support_recovered"] is True


def test_copy_child_artifact_summaries_uses_worker_action_excerpt_when_no_worker_action_file(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    child.mkdir()
    _write_child_decision(
        child,
        {
            "decision": "accepted",
            "reason": "verify_scalar_output_succeeded",
            "worker_action_input_excerpt": (
                '{"schema":"rook.worker_action:v1","kind":"action_request",'
                '"action_id":"draft_gh_set_value_params","input":{"value":3.0}}'
            ),
        },
    )
    row = {
        "lm8i_run_dir": str(child),
        "publication_support_attempted": False,
        "support_recovered": False,
        "worker_action_value": None,
    }

    PROBE._copy_child_artifact_summaries(row)

    assert row["worker_action_value"] == 3.0
    assert row["support_recovered"] is False


def test_copy_child_artifact_summaries_uses_excerpt_when_worker_action_has_no_numeric_value(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    child.mkdir()
    (child / "worker_action.json").write_text(
        json.dumps({"input": {"value": "not-a-number"}}),
        encoding="utf-8",
    )
    _write_child_decision(
        child,
        {
            "decision": "rejected",
            "reason": "worker_action_apply_failed:invalid_input",
            "worker_action_input_excerpt": '{"input":{"value":3.0}}',
        },
    )
    row = {
        "lm8i_run_dir": str(child),
        "publication_support_attempted": False,
        "support_recovered": False,
        "worker_action_value": None,
    }

    PROBE._copy_child_artifact_summaries(row)

    assert row["worker_action_value"] == 3.0
    assert row["support_recovered"] is False


def test_support_recovered_stays_false_when_worker_action_missing_but_excerpt_present(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    child.mkdir()
    _write_child_decision(
        child,
        {
            "decision": "publication_failed",
            "reason": "worker_action_apply_failed:invalid_input",
            "final_publication_status": "published",
            "final_worker_response_kind": "action_request",
            "worker_action_input_excerpt": '{"value":3.0}',
        },
    )
    row = {
        "lm8i_run_dir": str(child),
        "publication_support_attempted": True,
        "final_publication_status": "published",
        "final_worker_response_kind": "action_request",
        "support_recovered": False,
        "worker_action_value": None,
    }

    PROBE._copy_child_artifact_summaries(row)

    assert row["worker_action_value"] == 3.0
    assert row["support_recovered"] is False


def test_support_recovered_requires_worker_action_receipt(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    child.mkdir()
    row = {
        "lm8i_run_dir": str(child),
        "publication_support_attempted": True,
        "final_publication_status": "published",
        "final_worker_response_kind": "action_request",
        "support_recovered": False,
    }

    PROBE._copy_child_artifact_summaries(row)

    assert row["support_recovered"] is False


def test_support_recovered_with_malformed_worker_action_file(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    child.mkdir()
    (child / "worker_action.json").write_text(
        "{not valid json}",
        encoding="utf-8",
    )
    row = {
        "lm8i_run_dir": str(child),
        "publication_support_attempted": True,
        "support_recovered": False,
        "worker_action_value": None,
    }

    PROBE._copy_child_artifact_summaries(row)

    assert row["support_recovered"] is True
    assert row["worker_action_value"] is None


def test_scan_and_apply_leak_markers_are_report_only(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    child.mkdir()
    (child / "notes.json").write_text(
        json.dumps(
            {
                "marker": "PROBE_REPAIR_CODE",
                "nested": {"value": "A = 42.0"},
            }
        ),
        encoding="utf-8",
    )
    (child / "notes.txt").write_text(
        "repair_same_component.bind.base_params",
        encoding="utf-8",
    )
    row = {
        "lm8i_run_dir": str(child),
        "terminal_category": "accepted",
        "leak_check_performed": False,
        "leak_marker_matches": [],
        "leak_marker_match_count": 0,
    }

    matches = PROBE._scan_leak_markers(child)
    assert matches == [
        {"path": str(child / "notes.json"), "marker": "PROBE_REPAIR_CODE"},
        {"path": str(child / "notes.json"), "marker": "A = 42.0"},
        {"path": str(child / "notes.txt"), "marker": "repair_same_component.bind.base_params"},
    ]

    PROBE._apply_leak_scan(row)

    assert row["terminal_category"] == "accepted"
    assert row["leak_check_performed"] is True
    assert row["leak_marker_match_count"] == 3
    assert row["leak_marker_matches"] == matches


def test_scan_leak_markers_ignores_invalid_utf8_textlike_file(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    child.mkdir()
    (child / "bad.json").write_bytes(b"{\"marker\": \"PROBE_REPAIR_CODE\"}\xff")
    (child / "notes.txt").write_text(
        "repair_same_component.bind.base_params",
        encoding="utf-8",
    )

    matches = PROBE._scan_leak_markers(child)

    assert matches == [
        {"path": str(child / "notes.txt"), "marker": "repair_same_component.bind.base_params"},
    ]


def test_compact_counts_removes_zero_entries_and_sorts_keys():
    from collections import Counter

    counts = Counter({"rejected": 2, "accepted": 1, "gate_failed": 0})

    assert PROBE._compact_counts(counts) == {"accepted": 1, "rejected": 2}


def test_build_summary_counts_support_and_worker_denominators():
    rows = [
        {
            "terminal_category": "accepted",
            "worker_publication_ran": True,
            "publication_support_attempted": False,
            "support_eligible": False,
            "support_recovered": False,
            "lm8i_run_dir": "run-a",
            "leak_marker_match_count": 1,
            "worker_action_value": 3.0,
            "verifier_attempt_count": 1,
            "observed_output_after": 7.5,
        },
        {
            "terminal_category": "accepted",
            "worker_publication_ran": True,
            "publication_support_attempted": True,
            "support_eligible": True,
            "support_recovered": True,
            "lm8i_run_dir": "run-b",
            "leak_marker_match_count": 0,
            "worker_action_value": 3.0,
            "verifier_attempt_count": 2,
            "observed_output_after": 7.5,
        },
        {
            "terminal_category": "publication_failed",
            "worker_publication_ran": True,
            "publication_support_attempted": True,
            "support_eligible": True,
            "support_recovered": False,
            "lm8i_run_dir": "run-c",
            "leak_marker_match_count": 0,
        },
        {
            "terminal_category": "gate_failed",
            "worker_publication_ran": False,
            "publication_support_attempted": False,
            "support_eligible": None,
            "support_recovered": False,
            "gate_failure_reason": "affine_fixture_failed:gh_connect_failed",
            "lm8i_run_dir": "run-d",
            "leak_marker_match_count": 0,
        },
        {
            "terminal_category": "preflight_failed",
            "worker_publication_ran": False,
            "publication_support_attempted": False,
            "support_eligible": None,
            "support_recovered": False,
            "preflight_failure_reason": "rhino_ping_failed",
            "lm8i_run_dir": "run-e",
            "leak_marker_match_count": 0,
        },
    ]

    summary = PROBE._build_summary(
        rows,
        attempts=20,
        model="gemma4:12b-it-qat",
        attempt_timeout_s=600,
    )

    assert summary["schema"] == "rook.lm8j_affine_support_repeatability_probe:v1"
    assert summary["scheduled_attempts"] == 20
    assert summary["attempt_timeout_s"] == 600
    assert summary["canonical_evidence"] is True
    assert summary["terminal_category_counts"] == {
        "accepted": 2,
        "gate_failed": 1,
        "preflight_failed": 1,
        "publication_failed": 1,
    }
    assert summary["accepted_count"] == 2
    assert summary["publication_failed_count"] == 1
    assert summary["gate_failed_count"] == 1
    assert summary["preflight_failed_count"] == 1
    assert summary["worker_reached_count"] == 3
    assert summary["worker_terminal_counts"] == {"accepted": 2, "publication_failed": 1}
    assert summary["publication_support_attempted_count"] == 2
    assert summary["publication_support_recovered_count"] == 1
    assert summary["accepted_without_support_count"] == 1
    assert summary["support_eligible_count"] == 2
    assert summary["support_accepted_count"] == 1
    assert summary["gate_failure_reasons"] == {"affine_fixture_failed:gh_connect_failed": 1}
    assert summary["preflight_failure_reasons"] == {"rhino_ping_failed": 1}
    assert summary["leak_marker_match_count"] == 1
    assert summary["attempt_run_dirs"] == ["run-a", "run-b", "run-c", "run-d", "run-e"]
    assert summary["worker_action_values"] == [3.0, 3.0]
    assert summary["verifier_attempt_counts"] == [1, 2]
    assert summary["observed_output_values_after"] == [7.5, 7.5]


def _valid_managed_summary_rows() -> list[dict]:
    return [
        {
            "terminal_category": "accepted",
            "worker_publication_ran": True,
            "publication_support_attempted": False,
            "support_eligible": False,
            "support_recovered": False,
            "lm8i_run_dir": f"run-{index:02d}",
            "leak_marker_match_count": 0,
            "worker_action_value": 3.0,
            "observed_output_after": 7.5,
            "verifier_profile": PROBE.MANAGED_VERIFIER_PROFILE,
            "readiness_wait_count": 1,
            "readiness_wait_status": "ready",
            "readiness_failure_reason": None,
            "fenced_output_read_count": 1,
            "settle_read_count": 0,
            "managed_verifier_audit_performed": True,
            "managed_verifier_audit_valid": True,
            "managed_verifier_audit_failures": [],
        }
        for index in range(1, 21)
    ]


def test_build_managed_summary_accounts_exact_twenty_run_success():
    rows = _valid_managed_summary_rows()

    summary = PROBE._build_summary(
        rows,
        attempts=20,
        model=PROBE.DEFAULT_MODEL,
        attempt_timeout_s=PROBE.DEFAULT_ATTEMPT_TIMEOUT_S,
        verifier_profile=PROBE.MANAGED_VERIFIER_PROFILE,
    )

    assert summary["schema"] == PROBE.LM8M_SCRIPT_SCHEMA
    assert summary["verifier_profile"] == PROBE.MANAGED_VERIFIER_PROFILE
    assert summary["verifier_mechanism"] == PROBE.VERIFIER_MECHANISM
    assert summary["fixture_readiness_profile"] == PROBE.FIXTURE_READINESS_PROFILE
    assert summary["readiness_wait_timeout_ms"] == 10_000
    assert summary["child_attempt_timeout_s"] == 600
    assert summary["readiness_ready_count"] == 20
    assert summary["readiness_failure_reason_counts"] == {}
    assert summary["total_readiness_wait_count"] == 20
    assert summary["total_fenced_output_read_count"] == 20
    assert summary["total_settle_read_count"] == 0
    assert summary["managed_verifier_audit_pass_count"] == 20
    assert summary["managed_verifier_audit_failure_count"] == 0
    assert summary["managed_verifier_invariant_violation_count"] == 0
    assert summary["post_mutation_run_advance_failure_count"] == 0
    assert summary["accepted_child_audit_contradiction_count"] == 0
    assert summary["worker_action_values"] == [3.0] * 20
    assert summary["observed_output_values_after"] == [7.5] * 20
    assert summary["comparison_success"] is True


def test_managed_comparison_success_requires_canonical_identity():
    summary = PROBE._build_summary(
        _valid_managed_summary_rows(),
        attempts=20,
        model="qwen3:14b",
        attempt_timeout_s=PROBE.DEFAULT_ATTEMPT_TIMEOUT_S,
        verifier_profile=PROBE.MANAGED_VERIFIER_PROFILE,
    )

    assert summary["canonical_evidence"] is False
    assert summary["comparison_success"] is False


def test_settle_summary_does_not_gain_managed_shape_or_comparison_success():
    rows = _valid_managed_summary_rows()
    for row in rows:
        row.pop("verifier_profile")

    summary = PROBE._build_summary(
        rows,
        attempts=20,
        model=PROBE.DEFAULT_MODEL,
        attempt_timeout_s=PROBE.DEFAULT_ATTEMPT_TIMEOUT_S,
        verifier_profile=PROBE.SETTLE_VERIFIER_PROFILE,
    )

    assert summary.get("comparison_success", False) is False
    assert "comparison_success" not in summary
    assert "verifier_profile" not in summary
    assert "managed_verifier_audit_pass_count" not in summary


def test_build_managed_summary_counts_contradiction_rejection_and_decline():
    rows = [
        {
            "terminal_category": "wrapper_error",
            "failure_reason": "accepted_child_managed_verifier_audit_failed",
            "worker_publication_ran": True,
            "publication_support_attempted": False,
            "support_recovered": False,
            "worker_action_value": 3.0,
            "observed_output_after": 7.5,
            "leak_marker_match_count": 0,
            "verifier_profile": PROBE.MANAGED_VERIFIER_PROFILE,
            "readiness_wait_count": 1,
            "readiness_wait_status": "ready",
            "readiness_failure_reason": None,
            "fenced_output_read_count": 1,
            "settle_read_count": 0,
            "managed_verifier_audit_performed": True,
            "managed_verifier_audit_valid": False,
            "managed_verifier_audit_failures": [
                "post_mutation_solution_run_not_advanced"
            ],
        },
        {
            "terminal_category": "rejected",
            "failure_reason": None,
            "worker_publication_ran": True,
            "publication_support_attempted": False,
            "support_recovered": False,
            "worker_action_value": 3.0,
            "leak_marker_match_count": 0,
            "verifier_profile": PROBE.MANAGED_VERIFIER_PROFILE,
            "readiness_wait_count": 1,
            "readiness_wait_status": "timeout",
            "readiness_failure_reason": "readiness_receipt_timeout",
            "fenced_output_read_count": 0,
            "settle_read_count": 0,
            "managed_verifier_audit_performed": True,
            "managed_verifier_audit_valid": False,
            "managed_verifier_audit_failures": ["wait_artifact_missing"],
        },
        {
            "terminal_category": "worker_declined",
            "failure_reason": None,
            "worker_publication_ran": True,
            "publication_support_attempted": False,
            "support_recovered": False,
            "leak_marker_match_count": 0,
            "verifier_profile": PROBE.MANAGED_VERIFIER_PROFILE,
            "readiness_wait_count": 0,
            "readiness_wait_status": None,
            "readiness_failure_reason": None,
            "fenced_output_read_count": 0,
            "settle_read_count": 0,
            "managed_verifier_audit_performed": False,
            "managed_verifier_audit_valid": None,
            "managed_verifier_audit_failures": [],
        },
    ]

    summary = PROBE._build_summary(
        rows,
        attempts=3,
        model=PROBE.DEFAULT_MODEL,
        attempt_timeout_s=PROBE.DEFAULT_ATTEMPT_TIMEOUT_S,
        verifier_profile=PROBE.MANAGED_VERIFIER_PROFILE,
    )

    assert summary["terminal_category_counts"] == {
        "rejected": 1,
        "worker_declined": 1,
        "wrapper_error": 1,
    }
    assert summary["rejected_count"] == 1
    assert summary["wrapper_error_count"] == 1
    assert summary["readiness_failure_reason_counts"] == {
        "readiness_receipt_timeout": 1
    }
    assert summary["total_readiness_wait_count"] == 2
    assert summary["total_fenced_output_read_count"] == 1
    assert summary["total_settle_read_count"] == 0
    assert summary["managed_verifier_audit_pass_count"] == 0
    assert summary["managed_verifier_audit_failure_count"] == 2
    assert summary["managed_verifier_invariant_violation_count"] == 2
    assert summary["post_mutation_run_advance_failure_count"] == 1
    assert summary["accepted_child_audit_contradiction_count"] == 1
    assert summary["comparison_success"] is False


def test_write_json_and_append_jsonl_are_stable_and_structured(tmp_path: Path):
    json_path = tmp_path / "artifact.json"
    jsonl_path = tmp_path / "artifact.jsonl"

    PROBE._write_json(json_path, {"b": 2, "a": 1})
    PROBE._append_jsonl(jsonl_path, {"b": 2, "a": 1})
    PROBE._append_jsonl(jsonl_path, {"c": 3})

    assert json_path.read_text(encoding="utf-8") == '{\n  "a": 1,\n  "b": 2\n}\n'
    assert jsonl_path.read_text(encoding="utf-8").splitlines() == [
        '{"a": 1, "b": 2}',
        '{"c": 3}',
    ]


class FakeLm8iRunner:
    def __init__(self, child_decisions: list[dict]):
        self.child_decisions = list(child_decisions)
        self.calls: list[dict] = []

    def __call__(self, command, *, cwd, capture_output, text, timeout):
        self.calls.append(
            {
                "command": command,
                "cwd": cwd,
                "capture_output": capture_output,
                "text": text,
                "timeout": timeout,
            }
        )
        run_dir = Path(command[command.index("--run-dir") + 1])
        decision = self.child_decisions.pop(0)
        child = run_dir / f"lm8i-child-{len(self.calls):03d}"
        child.mkdir(parents=True)
        if decision.get("_write_managed_artifacts"):
            _write_managed_child_artifacts(child)
        else:
            (child / "decision.json").write_text(
                json.dumps(decision, sort_keys=True),
                encoding="utf-8",
            )
        if decision.get("worker_action_value") is not None:
            (child / "worker_action.json").write_text(
                json.dumps({"input": {"value": decision["worker_action_value"]}}),
                encoding="utf-8",
            )
        if decision.get("verifier_attempt_count") is not None:
            (child / "verify_scalar_output_summary.json").write_text(
                json.dumps(
                    {
                        "attempt_count": decision["verifier_attempt_count"],
                        "observed_output_value": decision.get("observed_output_after"),
                    }
                ),
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=f"run_dir={child}",
            stderr="",
        )


def test_run_probe_writes_manifest_attempts_and_summary(tmp_path: Path):
    runner = FakeLm8iRunner(
        [
            {
                "decision": "accepted",
                "reason": "verify_scalar_output_succeeded",
                "worker_publication_ran": True,
                "live_fixture_created": True,
                "live_set_value_dispatched": True,
                "verify_scalar_output_ran": True,
                "scalar_runtime_ready": True,
                "observed_output_after": 7.5,
                "publication_support_attempted": False,
                "publication_support_count": 0,
                "support_eligible": False,
                "worker_action_value": 3.0,
                "verifier_attempt_count": 1,
            },
            {
                "decision": "publication_failed",
                "reason": "pass1_decision_invalid:pass1_missing_action_id",
                "worker_publication_ran": True,
                "publication_support_attempted": True,
                "publication_support_count": 1,
                "support_eligible": True,
            },
        ]
    )

    run_dir = PROBE._run_probe(
        attempts=2,
        model="gemma4:12b-it-qat",
        run_root=tmp_path,
        attempt_timeout_s=600,
        run_subprocess=runner,
    )

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    assert manifest["attempts"] == 2
    assert manifest["attempt_timeout_s"] == 600
    assert manifest["canonical_evidence"] is False
    assert [row["terminal_category"] for row in rows] == [
        "accepted",
        "publication_failed",
    ]
    assert rows[0]["worker_action_value"] == 3.0
    assert rows[0]["support_recovered"] is False
    assert rows[1]["publication_support_attempted"] is True
    assert rows[1]["support_recovered"] is False
    assert summary["accepted_count"] == 1
    assert summary["publication_failed_count"] == 1
    assert summary["attempt_timeout_s"] == 600
    assert summary["worker_reached_count"] == 2
    assert summary["publication_support_attempted_count"] == 1
    assert summary["publication_support_recovered_count"] == 0
    assert summary["accepted_without_support_count"] == 1
    assert summary["worker_action_values"] == [3.0]
    assert summary["verifier_attempt_counts"] == [1]
    assert summary["observed_output_values_after"] == [7.5]
    assert "verifier_profile" not in rows[0]
    assert "managed_verifier_audit_performed" not in rows[0]
    assert "comparison_success" not in summary
    assert len(runner.calls) == 2
    assert all(call["timeout"] == 600 for call in runner.calls)
    assert all(call["capture_output"] is True for call in runner.calls)
    assert all(call["text"] is True for call in runner.calls)


def test_managed_run_probe_uses_lm8m_identity_and_forwards_profile(tmp_path: Path):
    runner = FakeLm8iRunner(
        [
            {
                "_write_managed_artifacts": True,
                "worker_action_value": 3.0,
            }
        ]
    )

    run_dir = PROBE._run_probe(
        attempts=1,
        model=PROBE.DEFAULT_MODEL,
        run_root=tmp_path,
        attempt_timeout_s=PROBE.DEFAULT_ATTEMPT_TIMEOUT_S,
        verifier_profile=PROBE.MANAGED_VERIFIER_PROFILE,
        run_subprocess=runner,
    )
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    assert run_dir.name.startswith("lm8m-")
    assert manifest["schema"] == PROBE.LM8M_SCRIPT_SCHEMA
    assert summary["schema"] == PROBE.LM8M_SCRIPT_SCHEMA
    assert runner.calls[0]["command"][-2:] == [
        "--verifier-profile",
        PROBE.MANAGED_VERIFIER_PROFILE,
    ]
    assert "--readiness-wait-timeout-ms" not in runner.calls[0]["command"]
    assert rows[0]["terminal_category"] == "accepted"
    assert rows[0]["verifier_profile"] == PROBE.MANAGED_VERIFIER_PROFILE
    assert rows[0]["verifier_mechanism"] == PROBE.VERIFIER_MECHANISM
    assert rows[0]["fixture_readiness_profile"] == PROBE.FIXTURE_READINESS_PROFILE
    assert rows[0]["readiness_wait_timeout_ms"] == 10_000
    assert rows[0]["child_attempt_timeout_s"] == 600
    assert rows[0]["managed_verifier_audit_performed"] is True
    assert rows[0]["managed_verifier_audit_valid"] is True
    assert rows[0]["managed_verifier_audit_failures"] == []
    assert summary["managed_verifier_audit_pass_count"] == 1
    assert summary["comparison_success"] is False


def test_run_probe_continues_after_wrapper_error(tmp_path: Path):
    calls = []

    def fake_runner(command, *, cwd, capture_output, text, timeout):
        calls.append(command)
        run_dir = Path(command[command.index("--run-dir") + 1])
        if len(calls) == 1:
            return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")
        child = run_dir / "lm8i-child-002"
        child.mkdir(parents=True)
        (child / "decision.json").write_text(
            json.dumps({"decision": "accepted", "worker_publication_ran": True}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")

    run_dir = PROBE._run_probe(
        attempts=2,
        model="gemma4:12b-it-qat",
        run_root=tmp_path,
        attempt_timeout_s=600,
        run_subprocess=fake_runner,
    )
    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert [row["terminal_category"] for row in rows] == ["wrapper_error", "accepted"]
    assert rows[0]["failure_reason"] == "child_run_dir_missing"
    assert len(calls) == 2


def test_run_probe_counts_support_recovery_only_when_worker_action_exists(tmp_path: Path):
    runner = FakeLm8iRunner(
        [
            {
                "decision": "accepted",
                "reason": "verify_scalar_output_succeeded",
                "worker_publication_ran": True,
                "publication_support_attempted": True,
                "publication_support_count": 1,
                "support_eligible": True,
                "final_publication_status": "published",
                "final_worker_response_kind": "action_request",
                "worker_action_value": 3.0,
            },
            {
                "decision": "publication_failed",
                "reason": "worker_action_apply_failed:invalid_input",
                "worker_publication_ran": True,
                "publication_support_attempted": True,
                "publication_support_count": 1,
                "support_eligible": True,
                "final_publication_status": "published",
                "final_worker_response_kind": "action_request",
            },
        ]
    )

    run_dir = PROBE._run_probe(
        attempts=2,
        model="gemma4:12b-it-qat",
        run_root=tmp_path,
        attempt_timeout_s=600,
        run_subprocess=runner,
    )
    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    assert rows[0]["support_recovered"] is True
    assert rows[1]["support_recovered"] is False
    assert summary["publication_support_attempted_count"] == 2
    assert summary["publication_support_recovered_count"] == 1
    assert summary["support_accepted_count"] == 1


def test_main_prints_run_dir_and_returns_zero(monkeypatch, tmp_path: Path, capsys):
    received_kwargs = {}

    def fake_run_probe(**kwargs):
        received_kwargs.update(kwargs)
        run_dir = tmp_path / "lm8j-demo"
        run_dir.mkdir()
        (run_dir / "summary.json").write_text(
            json.dumps({"accepted_count": 1, "scheduled_attempts": 1}),
            encoding="utf-8",
        )
        return run_dir

    monkeypatch.setattr(PROBE, "_run_probe", fake_run_probe)

    assert PROBE.main(["--attempts", "1", "--run-dir", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "LM8J affine support repeatability probe complete" in output
    assert "run_dir=" in output
    assert received_kwargs["verifier_profile"] == PROBE.SETTLE_VERIFIER_PROFILE


def test_lm8m_wrapper_ast_guard_allows_manifest_and_policy_strings():
    source = '''
import subprocess

MANIFEST = {"child_probe": "lm8i_affine_publication_shape_support_probe.py"}
POLICY = ("gh_set_value", "rook.server")

def _lm8i_command():
    return ["python", "lm8i_affine_publication_shape_support_probe.py"]

def _run_probe():
    command = _lm8i_command()
    return subprocess.run(command)
'''

    assert _lm8m_wrapper_guard_violations(source) == []


def test_lm8m_wrapper_ast_guard_allows_only_exact_git_metadata_subprocess():
    source = '''
import subprocess

def _git_short_sha():
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

def _lm8i_command():
    return ["python", "lm8i_affine_publication_shape_support_probe.py"]

def _run_probe():
    command = _lm8i_command()
    return subprocess.run(command)
'''

    assert _lm8m_wrapper_guard_violations(source) == []


@pytest.mark.parametrize(
    "command",
    [
        '["git", "status"]',
        '["python", "-c", "print(1)"]',
        '["git", "rev-parse", "--short", "HEAD", "--exec-path"]',
    ],
)
def test_lm8m_wrapper_ast_guard_rejects_repurposed_git_metadata_subprocess(
    command: str,
):
    source = f'''
import subprocess

def _git_short_sha():
    return subprocess.run(
        {command},
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

def _lm8i_command():
    return ["python", "lm8i_affine_publication_shape_support_probe.py"]

def _run_probe():
    command = _lm8i_command()
    return subprocess.run(command)
'''

    assert any(
        violation.startswith("forbidden process spawn:_git_short_sha:")
        for violation in _lm8m_wrapper_guard_violations(source)
    )


@pytest.mark.parametrize(
    "source",
    [
        '''
import lm8i_affine_publication_shape_support_probe as child_probe
''',
        '''
from lm8i_affine_publication_shape_support_probe import _run_probe as child_probe
''',
        '''
from rook import server as live_server
''',
        '''
from rook.server import _mcp_tool_executor as invoke_live

def _account_attempt():
    return invoke_live("gh_set_value", {"value": 3.0})
''',
        '''
from somewhere import call_tool as invoke

def _hidden_live_dispatch():
    return invoke("gh_set_value", {"value": 3.0})

def _run_probe():
    return _hidden_live_dispatch()
''',
        '''
def _hidden_live_dispatch():
    apply_value = gh_set_value
    return apply_value("component-guid", 3.0)

def _run_probe():
    return _hidden_live_dispatch()
''',
    ],
)
def test_lm8m_wrapper_ast_guard_rejects_aliased_live_dispatch(source: str):
    assert _lm8m_wrapper_guard_violations(source)


@pytest.mark.parametrize(
    "hidden_spawn",
    [
        '''
def _hidden_spawn():
    return subprocess.run(["git", "status"])
''',
        '''
launch = subprocess.run

def _hidden_spawn():
    return launch(["git", "status"])
''',
        '''
from subprocess import run as launch

def _hidden_spawn():
    return launch(["git", "status"])
''',
        '''
def _hidden_spawn():
    return subprocess.Popen(["git", "status"])
''',
        '''
def _spawn_with(spawn):
    return spawn(["git", "status"])

def _hidden_spawn():
    return _spawn_with(subprocess.run)
''',
    ],
)
def test_lm8m_wrapper_ast_guard_rejects_helper_indirected_process_spawn(
    hidden_spawn: str,
):
    source = f'''
import subprocess

def _lm8i_command():
    return ["python", "lm8i_affine_publication_shape_support_probe.py"]

def _run_probe():
    command = _lm8i_command()
    return subprocess.run(command)

{hidden_spawn}
'''

    violations = _lm8m_wrapper_guard_violations(source)

    assert any(
        violation.startswith("forbidden process spawn:")
        for violation in violations
    )


def test_lm8m_wrapper_ast_guard_rejects_helper_returned_process_alias():
    source = '''
import subprocess

def _lm8i_command():
    return ["python", "lm8i_affine_publication_shape_support_probe.py"]

def _run_probe():
    command = _lm8i_command()
    return subprocess.run(command)

def pick():
    return subprocess.run

def hidden():
    return pick()(["git", "status"])
'''

    assert any(
        violation.startswith("forbidden process reference return:pick:")
        for violation in _lm8m_wrapper_guard_violations(source)
    )


@pytest.mark.parametrize(
    "hidden_reference",
    [
        "def pick(spawn=subprocess.run):\n    return spawn",
        "pick = lambda: subprocess.run",
        "PICKS = (subprocess.run,)",
        "PICKS = {'run': subprocess.run}",
    ],
)
def test_lm8m_wrapper_ast_guard_rejects_process_references_in_defaults_lambdas_and_containers(
    hidden_reference: str,
):
    source = f'''
import subprocess

def _lm8i_command():
    return ["python", "lm8i_affine_publication_shape_support_probe.py"]

def _run_probe():
    command = _lm8i_command()
    return subprocess.run(command)

{hidden_reference}
'''

    assert any(
        violation.startswith("forbidden direct process reference:")
        for violation in _lm8m_wrapper_guard_violations(source)
    )


@pytest.mark.parametrize(
    "command_expression",
    [
        '[sys.executable, "-c", "print(1)"]',
        '[sys.executable, "other_probe.py"]',
        '_live_command()',
    ],
)
def test_lm8m_wrapper_ast_guard_requires_exact_lm8i_command_builder(
    command_expression: str,
):
    source = f'''
import subprocess
import sys

def _lm8i_command():
    return [sys.executable, "lm8i_affine_publication_shape_support_probe.py"]

def _run_probe():
    return subprocess.run({command_expression})
'''

    violations = _lm8m_wrapper_guard_violations(source)

    assert any(
        violation.startswith("forbidden process spawn:")
        for violation in violations
    )


def test_lm8m_wrapper_remains_subprocess_only():
    source = _script_path().read_text(encoding="utf-8")

    assert _lm8m_wrapper_guard_violations(source) == []


def test_no_lm8l_or_lm8m_sibling_scripts_exist():
    scripts_dir = _script_path().parent

    assert list(scripts_dir.glob("lm8l*.py")) == []
    assert list(scripts_dir.glob("lm8m*.py")) == []
