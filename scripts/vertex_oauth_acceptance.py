"""Bounded, source-only installed acceptance for Rook's Vertex provider.

This file is intentionally not an installed command, HTTP route, or MCP tool.
It must be run by the installed Rook interpreter from reviewed source.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import inspect
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path
from typing import Any, Callable


RESULT_KEYS = {
    "schema_version",
    "success",
    "acceptance_level",
    "stages",
    "error_code",
    "rook_commit",
    "chirp_commit",
    "installed_versions",
}
_SENTINEL_NAME = ".rook-vertex-acceptance-owned.json"
_SENTINEL = {"schema_version": 1, "owner": "rook-vertex-acceptance"}
_MODEL_PATTERN = re.compile(r"^vertex_ai/gemini-[A-Za-z0-9._-]+$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_MAX_WATCHDOG_SECONDS = 900.0
_DSPY_TIMEOUT_SECONDS = 180.0
_CHIRP_TIMEOUT_SECONDS = 360.0
_RHINO_CLEANUP_TIMEOUT_SECONDS = 30.0
_DEFAULT_RHINO_EXE = Path(r"C:\Program Files\Rhino 8\System\Rhino.exe")
_PRODUCTION_FLAGS = (
    "production_client_ready",
    "google_verification_complete",
    "enterprise_admin_guidance_published",
    "managed_business_production_validated",
)


class AcceptanceFailure(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        stages: dict[str, str] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.stages = dict(stages or {})


class AcceptanceOperations:
    def __init__(
        self,
        *,
        provenance: Callable[[], dict[str, Any]],
        connect: Callable[[dict[str, str], str, str], Any],
        readiness: Callable[[str], Any],
        dspy: Callable[[str, str], Any],
        chirp: Callable[[str, str, Path], Any],
        disconnect: Callable[[], Any],
    ) -> None:
        self.provenance = provenance
        self.connect = connect
        self.readiness = readiness
        self.dspy = dspy
        self.chirp = chirp
        self.disconnect = disconnect


class AcceptanceBoundary:
    def __init__(
        self,
        *,
        executable: Path,
        local_app_data: Path,
        temp_root: Path,
        script_path: Path,
        expected_rook_commit: str | None,
        expected_chirp_commit: str | None,
    ) -> None:
        self.executable = Path(executable)
        self.local_app_data = Path(local_app_data)
        self.temp_root = Path(temp_root)
        self.script_path = Path(script_path)
        self.expected_rook_commit = expected_rook_commit
        self.expected_chirp_commit = expected_chirp_commit


class AcceptanceContext:
    def __init__(
        self,
        *,
        arguments: argparse.Namespace,
        evidence_root: Path,
        result_path: Path,
        client: dict[str, str] | None,
        expected_rook_commit: str,
        expected_chirp_commit: str,
    ) -> None:
        self.arguments = arguments
        self.evidence_root = evidence_root
        self.result_path = result_path
        self.client = client
        self.expected_rook_commit = expected_rook_commit
        self.expected_chirp_commit = expected_chirp_commit


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise AcceptanceFailure("vertex_acceptance_arguments_invalid")


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(description="Run bounded installed Vertex acceptance.")
    parser.add_argument("--acceptance-level", choices=("technical", "production"))
    parser.add_argument("--project")
    parser.add_argument("--region")
    parser.add_argument("--model")
    parser.add_argument("--desktop-client-json", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--watchdog-seconds", type=float, required=True)
    parser.add_argument("--run-consumers", action="store_true")
    parser.add_argument("--disconnect", action="store_true")
    parser.add_argument("--production-client-ready", action="store_true")
    parser.add_argument("--google-verification-complete", action="store_true")
    parser.add_argument("--enterprise-admin-guidance-published", action="store_true")
    parser.add_argument("--managed-business-production-validated", action="store_true")
    return parser


def _default_boundary() -> AcceptanceBoundary:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise AcceptanceFailure("vertex_acceptance_environment_invalid")
    return AcceptanceBoundary(
        executable=Path(sys.executable),
        local_app_data=Path(local_app_data),
        temp_root=Path(tempfile.gettempdir()),
        script_path=Path(__file__).resolve(),
        expected_rook_commit=os.environ.get("ROOK_VERTEX_MERGE_SHA"),
        expected_chirp_commit=os.environ.get("CHIRP_VERTEX_MERGE_SHA"),
    )


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(
        os.path.realpath(right)
    )


def _is_direct_child(path: Path, parent: Path) -> bool:
    return _same_path(path.parent, parent)


def _claim_evidence_root(path: Path, temp_root: Path) -> Path:
    root = path.resolve()
    expected_temp = temp_root.resolve()
    if (
        not root.is_dir()
        or not _is_direct_child(root, expected_temp)
        or not root.name.startswith("rook-vertex-acceptance-")
        or root.is_symlink()
    ):
        raise AcceptanceFailure("vertex_acceptance_evidence_root_invalid")

    sentinel = root / _SENTINEL_NAME
    if sentinel.exists():
        try:
            value = json.loads(sentinel.read_text(encoding="utf-8"))
        except Exception as exc:
            raise AcceptanceFailure("vertex_acceptance_ownership_invalid") from exc
        if value != _SENTINEL:
            raise AcceptanceFailure("vertex_acceptance_ownership_invalid")
    else:
        if any(root.iterdir()):
            raise AcceptanceFailure("vertex_acceptance_ownership_missing")
        sentinel.write_text(
            json.dumps(_SENTINEL, sort_keys=True),
            encoding="utf-8",
        )
    return root


def _load_desktop_client(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise AcceptanceFailure("vertex_acceptance_client_invalid")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        installed = payload["installed"]
        client_id = installed["client_id"]
        client_secret = installed["client_secret"]
    except Exception as exc:
        raise AcceptanceFailure("vertex_acceptance_client_invalid") from exc
    if not isinstance(client_id, str) or not client_id:
        raise AcceptanceFailure("vertex_acceptance_client_invalid")
    if not isinstance(client_secret, str) or not client_secret:
        raise AcceptanceFailure("vertex_acceptance_client_invalid")
    return {"client_id": client_id, "client_secret": client_secret}


def _prepare(argv: list[str], boundary: AcceptanceBoundary) -> AcceptanceContext:
    arguments = _build_parser().parse_args(argv)
    expected_rook_commit = getattr(boundary, "expected_rook_commit", None)
    expected_chirp_commit = getattr(boundary, "expected_chirp_commit", None)
    if (
        not isinstance(expected_rook_commit, str)
        or _COMMIT_PATTERN.fullmatch(expected_rook_commit) is None
        or not isinstance(expected_chirp_commit, str)
        or _COMMIT_PATTERN.fullmatch(expected_chirp_commit) is None
    ):
        raise AcceptanceFailure("vertex_acceptance_expected_provenance_invalid")
    expected_python = (
        boundary.local_app_data / "Rook" / "venv" / "Scripts" / "python.exe"
    )
    if not _same_path(boundary.executable, expected_python):
        raise AcceptanceFailure("vertex_acceptance_interpreter_invalid")
    if (
        not isinstance(arguments.watchdog_seconds, float)
        or not 0 < arguments.watchdog_seconds <= _MAX_WATCHDOG_SECONDS
    ):
        raise AcceptanceFailure("vertex_acceptance_watchdog_invalid")
    if arguments.disconnect:
        if arguments.run_consumers or arguments.acceptance_level is not None:
            raise AcceptanceFailure("vertex_acceptance_arguments_invalid")
        client = None
    else:
        if (
            arguments.acceptance_level not in {"technical", "production"}
            or not arguments.run_consumers
            or not isinstance(arguments.project, str)
            or not arguments.project
            or not isinstance(arguments.region, str)
            or not arguments.region
            or not isinstance(arguments.model, str)
            or _MODEL_PATTERN.fullmatch(arguments.model) is None
        ):
            raise AcceptanceFailure("vertex_acceptance_arguments_invalid")
        if arguments.acceptance_level == "technical" and any(
            getattr(arguments, flag) for flag in _PRODUCTION_FLAGS
        ):
            raise AcceptanceFailure("vertex_acceptance_arguments_invalid")
        if arguments.acceptance_level == "production" and not all(
            getattr(arguments, flag) for flag in _PRODUCTION_FLAGS
        ):
            raise AcceptanceFailure("vertex_production_prerequisites_incomplete")
        client = _load_desktop_client(arguments.desktop_client_json)

    evidence_root = _claim_evidence_root(arguments.evidence_root, boundary.temp_root)
    return AcceptanceContext(
        arguments=arguments,
        evidence_root=evidence_root,
        result_path=evidence_root / "result.json",
        client=client,
        expected_rook_commit=expected_rook_commit,
        expected_chirp_commit=expected_chirp_commit,
    )


def _result_payload(
    *,
    success: bool,
    acceptance_level: str,
    stages: dict[str, str],
    error_code: str | None,
    provenance: dict[str, Any] | None,
) -> dict[str, Any]:
    safe = provenance or {}
    payload = {
        "schema_version": 1,
        "success": success,
        "acceptance_level": acceptance_level,
        "stages": dict(stages),
        "error_code": error_code,
        "rook_commit": safe.get("rook_commit"),
        "chirp_commit": safe.get("chirp_commit"),
        "installed_versions": dict(safe.get("installed_versions") or {}),
    }
    if set(payload) != RESULT_KEYS:
        raise AcceptanceFailure("vertex_acceptance_evidence_invalid")
    return payload


def _write_result(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _require_operation_success(result: Any) -> None:
    if getattr(result, "success", None) is not True:
        code = getattr(result, "code", None)
        raise AcceptanceFailure(
            code if isinstance(code, str) and code else "vertex_acceptance_operation_failed"
        )


def validate_dspy_result(result: Any, marker: str) -> None:
    value = getattr(result, "echoed_marker", None)
    if not isinstance(value, str) or not value or marker not in value:
        raise AcceptanceFailure("vertex_dspy_acceptance_failed")


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _verify_installed_provenance(boundary: AcceptanceBoundary) -> dict[str, Any]:
    expected_site = (
        boundary.local_app_data / "Rook" / "venv" / "Lib" / "site-packages"
    ).resolve()
    try:
        import rook
    except Exception as exc:
        raise AcceptanceFailure("vertex_acceptance_installed_import_failed") from exc
    rook_path = Path(rook.__file__).resolve()
    try:
        rook_path.relative_to(expected_site)
    except ValueError as exc:
        raise AcceptanceFailure("vertex_acceptance_source_import_refused") from exc

    manifest_path = (
        boundary.local_app_data / "Rook" / "app" / "python-runtime-manifest.json"
    )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        rook_commit = manifest["rook_git_sha"]
        chirp_commit = manifest["chirp_git_sha"]
    except Exception as exc:
        raise AcceptanceFailure("vertex_acceptance_provenance_invalid") from exc
    if (
        not isinstance(rook_commit, str)
        or _COMMIT_PATTERN.fullmatch(rook_commit) is None
        or not isinstance(chirp_commit, str)
        or _COMMIT_PATTERN.fullmatch(chirp_commit) is None
    ):
        raise AcceptanceFailure("vertex_acceptance_provenance_invalid")

    versions = {
        "rook-mcp": metadata.version("rook-mcp"),
        "chirp": _read_installed_chirp_version(boundary),
        "google-auth": metadata.version("google-auth"),
        "mcp": metadata.version("mcp"),
    }
    if versions["google-auth"] != "2.56.3":
        raise AcceptanceFailure("vertex_acceptance_dependency_invalid")
    return {
        "rook_commit": rook_commit,
        "chirp_commit": chirp_commit,
        "installed_versions": versions,
    }


def _read_installed_chirp_version(boundary: AcceptanceBoundary) -> str:
    chirp_root = (boundary.local_app_data / "Rook" / "app" / "chirp").resolve()
    chirp_python = chirp_root / ".venv" / "Scripts" / "python.exe"
    if not chirp_python.is_file():
        raise AcceptanceFailure("vertex_acceptance_provenance_invalid")
    probe = (
        "import json; from importlib.metadata import version; import chirp; "
        "print(json.dumps({'version': version('chirp'), 'path': chirp.__file__}))"
    )
    try:
        completed = subprocess.run(
            [str(chirp_python), "-c", probe],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        payload = json.loads(completed.stdout.strip())
        version = payload["version"]
        module_path = Path(payload["path"]).resolve()
        module_path.relative_to(chirp_root)
    except Exception as exc:
        raise AcceptanceFailure("vertex_acceptance_provenance_invalid") from exc
    if completed.returncode != 0 or not isinstance(version, str) or not version:
        raise AcceptanceFailure("vertex_acceptance_provenance_invalid")
    return version


async def _run_dspy(model: str, marker: str) -> None:
    import dspy
    from rook.learning.dspy_config import configure_dspy

    lm = configure_dspy(
        model=model,
        temperature=0,
        max_tokens=64,
        cache=False,
    )
    if getattr(lm, "model", None) != model:
        raise AcceptanceFailure("vertex_dspy_acceptance_failed")
    lm_kwargs = getattr(lm, "kwargs", {})
    if isinstance(lm_kwargs, dict) and "api_key" in lm_kwargs:
        raise AcceptanceFailure("vertex_dspy_acceptance_failed")

    class MarkerEcho(dspy.Signature):
        """Return the supplied marker unchanged in echoed_marker."""

        marker: str = dspy.InputField()
        echoed_marker: str = dspy.OutputField()

    prediction = dspy.Predict(MarkerEcho)
    try:
        result = await asyncio.wait_for(
            prediction.acall(marker=marker),
            timeout=_DSPY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise AcceptanceFailure(
            "vertex_dspy_timeout",
            stages={"dspy": "failed"},
        ) from exc
    validate_dspy_result(result, marker)


def _parse_child_status(stdout: str) -> dict[str, str]:
    for line in reversed(stdout.splitlines()):
        try:
            payload = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict) and payload.get("schema_version") == 1:
            return {
                "chirp": payload.get("chirp", "failed"),
                "canvas_cleanup": payload.get("canvas_cleanup", "failed"),
            }
    return {"chirp": "failed", "canvas_cleanup": "failed"}


@contextlib.contextmanager
def _scoped_process_environment(
    values: dict[str, str | None],
):
    prior = {name: os.environ.get(name) for name in values}
    try:
        for name, value in values.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        yield
    finally:
        for name, value in prior.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


async def _run_chirp(
    model: str,
    marker: str,
    evidence_root: Path,
    boundary: AcceptanceBoundary,
) -> dict[str, str]:
    from rook.runtime_harness import CleanupStatus, run_rhino_runtime_harness

    scoped_environment = {
        "ROOK_VERTEX_ACCEPTANCE_MODEL": model,
        "ROOK_VERTEX_ACCEPTANCE_MARKER": marker,
        "ROOK_VERTEX_ACCEPTANCE_PROJECT": None,
        "ROOK_VERTEX_ACCEPTANCE_REGION": None,
        "ROOK_VERTEX_DESKTOP_CLIENT_JSON": None,
    }
    with _scoped_process_environment(scoped_environment):
        result = await asyncio.to_thread(
            run_rhino_runtime_harness,
            rhino_exe=_DEFAULT_RHINO_EXE,
            artifact_root=evidence_root / "rhino-runtime",
            smoke_command=[
                str(boundary.executable),
                str(boundary.script_path),
                "--_chirp-child",
            ],
            smoke_kind="vertex-acceptance",
            smoke_cwd=evidence_root,
            smoke_timeout_seconds=_CHIRP_TIMEOUT_SECONDS,
            readiness_timeout_seconds=90.0,
            cleanup_timeout_seconds=_RHINO_CLEANUP_TIMEOUT_SECONDS,
            launch_env_overrides=scoped_environment,
        )
    smoke_status = (
        _parse_child_status(result.smoke.stdout)
        if result.smoke is not None
        else {"chirp": "failed", "canvas_cleanup": "failed"}
    )
    process_status = (
        "passed"
        if result.cleanup_status is CleanupStatus.GRACEFUL_EXIT
        else "failed"
    )
    stages = {**smoke_status, "process_cleanup": process_status}
    if not result.success:
        body_failed = smoke_status["chirp"] != "passed"
        cleanup_failed = (
            smoke_status["canvas_cleanup"] != "passed" or process_status != "passed"
        )
        code = (
            "vertex_chirp_and_cleanup_failed"
            if body_failed and cleanup_failed
            else "vertex_chirp_acceptance_failed"
            if body_failed
            else "vertex_chirp_cleanup_failed"
        )
        raise AcceptanceFailure(code, stages=stages)
    if stages != {
        "chirp": "passed",
        "canvas_cleanup": "passed",
        "process_cleanup": "passed",
    }:
        raise AcceptanceFailure("vertex_chirp_acceptance_failed", stages=stages)
    return stages


def _default_operations(boundary: AcceptanceBoundary) -> AcceptanceOperations:
    from rook.providers.vertex_backend import (
        connect_vertex_oauth,
        disconnect_vertex,
        probe_vertex_readiness,
    )
    from rook.providers.vertex_oauth import DesktopOAuthClient

    def connect(client: dict[str, str], project: str, region: str) -> Any:
        return connect_vertex_oauth(
            DesktopOAuthClient(client["client_id"], client["client_secret"]),
            project,
            region,
        )

    async def chirp(model: str, marker: str, root: Path) -> dict[str, str]:
        return await _run_chirp(model, marker, root, boundary)

    return AcceptanceOperations(
        provenance=lambda: _verify_installed_provenance(boundary),
        connect=connect,
        readiness=probe_vertex_readiness,
        dspy=_run_dspy,
        chirp=chirp,
        disconnect=disconnect_vertex,
    )


async def _execute(
    context: AcceptanceContext,
    operations: AcceptanceOperations,
) -> tuple[dict[str, Any], dict[str, str]]:
    arguments = context.arguments
    provenance = operations.provenance()
    if (
        not isinstance(provenance, dict)
        or provenance.get("rook_commit") != context.expected_rook_commit
        or provenance.get("chirp_commit") != context.expected_chirp_commit
    ):
        raise AcceptanceFailure("vertex_acceptance_provenance_mismatch")
    stages: dict[str, str] = {"installed_provenance": "passed"}
    if arguments.disconnect:
        disconnected = operations.disconnect()
        _require_operation_success(disconnected)
        stages["disconnect"] = "passed"
        return provenance, stages

    connected = await asyncio.to_thread(
        operations.connect,
        context.client,
        arguments.project,
        arguments.region,
    )
    _require_operation_success(connected)
    stages["oauth"] = "passed"

    readiness = await asyncio.to_thread(operations.readiness, arguments.model)
    _require_operation_success(readiness)
    stages["readiness"] = "passed"

    marker = "rook-vertex-marker-" + secrets.token_hex(8)
    await _maybe_await(operations.dspy(arguments.model, marker))
    stages["dspy"] = "passed"
    chirp_stages = await _maybe_await(
        operations.chirp(arguments.model, marker, context.evidence_root)
    )
    if not isinstance(chirp_stages, dict):
        raise AcceptanceFailure("vertex_chirp_acceptance_failed")
    stages.update(chirp_stages)
    return provenance, stages


def run(
    argv: list[str] | None = None,
    *,
    boundary: AcceptanceBoundary | Any | None = None,
    operations: AcceptanceOperations | None = None,
) -> int:
    selected_boundary = boundary or _default_boundary()
    context: AcceptanceContext | None = None
    provenance: dict[str, Any] | None = None
    stages: dict[str, str] = {}
    try:
        context = _prepare(list(argv or []), selected_boundary)
        selected_operations = operations or _default_operations(selected_boundary)
        provenance, stages = asyncio.run(
            asyncio.wait_for(
                _execute(context, selected_operations),
                timeout=context.arguments.watchdog_seconds,
            )
        )
        level = (
            "failed"
            if context.arguments.disconnect
            else "production_ready"
            if context.arguments.acceptance_level == "production"
            else "technical_pass"
        )
        payload = _result_payload(
            success=True,
            acceptance_level=level,
            stages=stages,
            error_code=None,
            provenance=provenance,
        )
        if context.arguments.disconnect and context.result_path.is_file():
            try:
                prior = json.loads(context.result_path.read_text(encoding="utf-8"))
            except Exception:
                prior = None
            if isinstance(prior, dict) and set(prior) == RESULT_KEYS:
                payload["acceptance_level"] = prior.get("acceptance_level", "failed")
                payload["stages"] = {**dict(prior.get("stages") or {}), **stages}
        _write_result(context.result_path, payload)
        return 0
    except AcceptanceFailure as exc:
        stages.update(exc.stages)
        code = exc.code
    except asyncio.TimeoutError:
        code = "vertex_acceptance_watchdog_expired"
    except Exception:
        code = "vertex_acceptance_internal_error"

    if context is not None:
        payload = _result_payload(
            success=False,
            acceptance_level="failed",
            stages=stages,
            error_code=code,
            provenance=provenance,
        )
        _write_result(context.result_path, payload)
    return 1


async def _run_chirp_child() -> int:
    model = os.environ.get("ROOK_VERTEX_ACCEPTANCE_MODEL", "")
    marker = os.environ.get("ROOK_VERTEX_ACCEPTANCE_MARKER", "")
    if _MODEL_PATTERN.fullmatch(model) is None or not marker.startswith(
        "rook-vertex-marker-"
    ):
        return 2

    try:
        port = int(os.environ["ROOK_RHINO_PORT"])
        process_id = int(os.environ["ROOK_RHINO_PROCESS_ID"])
        if port <= 0 or process_id <= 0:
            raise ValueError
        from rook.runtime_harness import OwnedRhinoDiscovery

        owned_record = OwnedRhinoDiscovery().read_owned_record(process_id)
        if owned_record.pid != process_id or owned_record.port != port:
            raise ValueError
    except Exception:
        return 2

    from rook.bridge import call_rhino, rhino_request_context
    from rook.local_testing_proof import (
        ProofFailure,
        _capture_chirp_cleanup_state,
        _ensure_grasshopper_ready,
        _is_retryable_slow_inspection_timeout,
        _run_chirp_smoke_mutation,
    )
    from rook.server import _call_tool_dispatch

    args: dict[str, int] = {"port": port}
    child_status = {
        "schema_version": 1,
        "chirp": "failed",
        "canvas_cleanup": "failed",
    }
    try:
        with rhino_request_context(port=port, process_id=process_id):
            await _ensure_grasshopper_ready(args)
            baseline = await _capture_chirp_cleanup_state(
                args,
                dispatch_fn=_call_tool_dispatch,
                call_rhino_fn=call_rhino,
            )
            if baseline["object_count"] != 0 or baseline["instance_guids"]:
                raise AcceptanceFailure("vertex_chirp_canvas_not_empty")

            async def verify_created(
                component_guid: str,
                _response: dict[str, Any],
            ) -> None:
                deadline = asyncio.get_running_loop().time() + 300.0
                while asyncio.get_running_loop().time() < deadline:
                    inspected = await _call_tool_dispatch(
                        "gh_inspect_output",
                        {"guid": component_guid, "param": "Result", **args},
                    )
                    if _is_retryable_slow_inspection_timeout(inspected):
                        await asyncio.sleep(0.5)
                        continue
                    if (
                        not isinstance(inspected, dict)
                        or inspected.get("success") is not True
                    ):
                        raise AcceptanceFailure("vertex_chirp_inspection_failed")
                    data = inspected.get("data")
                    if not isinstance(data, dict) or not isinstance(
                        data.get("preview"), list
                    ):
                        raise AcceptanceFailure("vertex_chirp_inspection_failed")
                    preview = data["preview"]
                    if any(isinstance(item, str) and item.strip() for item in preview):
                        return
                    await asyncio.sleep(0.5)
                raise AcceptanceFailure("vertex_chirp_output_missing")

            await _run_chirp_smoke_mutation(
                args,
                component_name="Rook Vertex Acceptance " + marker[-8:],
                dispatch_fn=_call_tool_dispatch,
                call_rhino_fn=call_rhino,
                create_arguments={
                    "category": "classifier",
                    "name": "Rook Vertex Acceptance " + marker[-8:],
                    "pins_in": [
                        {"name": "Input", "type": "string", "optional": True}
                    ],
                    "pins_out": [{"name": "Result", "type": "string"}],
                    "signature": "input -> result",
                    "model": model,
                    "x": 40,
                    "y": 40,
                },
                verify_created_fn=verify_created,
            )
        child_status["chirp"] = "passed"
        child_status["canvas_cleanup"] = "passed"
        print(json.dumps(child_status, sort_keys=True))
        return 0
    except ProofFailure as exc:
        cleanup = exc.details.get("cleanup") if isinstance(exc.details, dict) else None
        if isinstance(cleanup, dict) and cleanup.get("component_removed") is True:
            child_status["canvas_cleanup"] = "passed"
    except Exception:
        pass
    print(json.dumps(child_status, sort_keys=True))
    return 1


def main() -> int:
    if sys.argv[1:] == ["--_chirp-child"]:
        return asyncio.run(_run_chirp_child())
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
