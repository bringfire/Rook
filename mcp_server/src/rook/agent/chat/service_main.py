"""Standalone entrypoint for the Rhino-owned chat service."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .prime_backend import PrimeChatBackend
from .prime_process import PrimeRpcProcess
from .prime_registry import (
    PrimeConversationRegistry,
    PrimeModelSelection,
    TargetFingerprint,
)
from .server import start_chat_server, stop_chat_server, wait_for_chat_server


_THINKING_LEVELS = frozenset(
    {"off", "minimal", "low", "medium", "high", "xhigh", "max"}
)


@dataclass(frozen=True)
class ServiceConfiguration:
    backend_mode: str
    node_path: Path | None = None
    cli_path: Path | None = None
    registry_root: Path | None = None
    default_model: PrimeModelSelection | None = None
    prime_backend: PrimeChatBackend | None = None
    registry: PrimeConversationRegistry | None = None


def _absolute_path(value: str | None, name: str, *, must_exist: bool) -> Path:
    if not value:
        raise ValueError(f"{name} is required in Prime mode")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{name} must be absolute")
    absolute = path.absolute()
    if must_exist and not absolute.is_file():
        raise ValueError(f"{name} must name an existing file")
    return absolute


def _build_service_configuration(
    *,
    rhino_process_id: int,
    rhino_process_start_utc_ticks: str,
    environment: Mapping[str, str] | None = None,
) -> ServiceConfiguration:
    env = os.environ if environment is None else environment
    backend_mode = env.get("ROOK_CHAT_BACKEND", "legacy")
    if backend_mode not in {"legacy", "prime"}:
        raise ValueError("ROOK_CHAT_BACKEND must be exactly 'legacy' or 'prime'")
    # Validate the process-generation identity before opening a registry lock.
    TargetFingerprint(rhino_process_id, rhino_process_start_utc_ticks, 1)
    if backend_mode == "legacy":
        return ServiceConfiguration(backend_mode="legacy")

    node_path = _absolute_path(
        env.get("ROOK_PRIME_NODE_PATH"), "ROOK_PRIME_NODE_PATH", must_exist=True
    )
    cli_path = _absolute_path(
        env.get("ROOK_PRIME_CLI_PATH"), "ROOK_PRIME_CLI_PATH", must_exist=True
    )
    registry_value = env.get("ROOK_PRIME_REGISTRY_ROOT")
    if registry_value is None:
        local_app_data = env.get("LOCALAPPDATA")
        if not local_app_data:
            raise ValueError(
                "LOCALAPPDATA or ROOK_PRIME_REGISTRY_ROOT is required in Prime mode"
            )
        registry_value = str(Path(local_app_data) / "Rook" / "chat" / "prime")
    registry_root = _absolute_path(
        registry_value, "ROOK_PRIME_REGISTRY_ROOT", must_exist=False
    )

    configured_model = env.get("ROOK_PRIME_MODEL")
    thinking = env.get("ROOK_PRIME_THINKING")
    if thinking is not None and thinking not in _THINKING_LEVELS:
        raise ValueError("ROOK_PRIME_THINKING is not a valid Prime thinking level")
    if configured_model is not None:
        if configured_model.count("/") != 1:
            raise ValueError("ROOK_PRIME_MODEL must use provider/model syntax")
        provider, model_id = configured_model.split("/", 1)
        if not provider or not model_id:
            raise ValueError("ROOK_PRIME_MODEL must use provider/model syntax")
        default_model = PrimeModelSelection(provider, model_id, thinking)
    else:
        default_model = PrimeModelSelection("prime-config", "default", thinking)

    registry = PrimeConversationRegistry(
        registry_root,
        rhino_pid=rhino_process_id,
        rhino_process_start_utc_ticks=rhino_process_start_utc_ticks,
    )
    session_dir = registry_root / "sessions"

    def process_factory(
        generation: int,
        model: PrimeModelSelection,
        resume_session_path: str | None,
    ) -> PrimeRpcProcess:
        use_configured_model = (
            configured_model is not None or resume_session_path is not None
        )
        return PrimeRpcProcess(
            node_path=node_path,
            cli_path=cli_path,
            session_dir=session_dir,
            generation=generation,
            provider=model.provider if use_configured_model else None,
            model_id=model.id if use_configured_model else None,
            thinking=model.thinking,
            resume_session_path=resume_session_path,
        )

    backend = PrimeChatBackend(registry, process_factory, default_model)
    return ServiceConfiguration(
        backend_mode="prime",
        node_path=node_path,
        cli_path=cli_path,
        registry_root=registry_root,
        default_model=(default_model if configured_model is not None else None),
        prime_backend=backend,
        registry=registry,
    )


def _load_env() -> str | None:
    try:
        from dotenv import load_dotenv

        cwd = Path.cwd()
        repo_root = cwd.parent
        env_locations = [
            cwd / ".env",
            repo_root / ".env",
            repo_root / "autonomous_dev" / ".env",
        ]
        for env_path in env_locations:
            if env_path.exists():
                load_dotenv(env_path)
                return str(env_path)
        return None
    except ImportError:
        return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Rook agent chat service.")
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Chat service port. Use 0 to let the OS choose a free port.",
    )
    parser.add_argument(
        "--include-gh-health",
        action="store_true",
        help="Include GH health in service health responses.",
    )
    parser.add_argument(
        "--owner",
        default="external",
        help="Ownership marker written to discovery/health for service selection.",
    )
    parser.add_argument(
        "--rhino-process-id",
        type=int,
        default=0,
        help="Owning Rhino process ID for multi-instance discovery scoping.",
    )
    parser.add_argument(
        "--rhino-process-start-utc-ticks",
        required=True,
        help="Owning Rhino process start fingerprint as UTC ticks.",
    )
    return parser.parse_args()


def main() -> None:
    log_file = os.environ.get("ROOK_LOG_FILE")
    log_handlers: list[logging.Handler] = []
    if log_file:
        log_handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    else:
        log_handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=log_handlers,
    )
    args = _parse_args()
    sys.dont_write_bytecode = True
    _load_env()
    configuration = _build_service_configuration(
        rhino_process_id=args.rhino_process_id,
        rhino_process_start_utc_ticks=args.rhino_process_start_utc_ticks,
    )

    async def _run() -> None:
        try:
            await start_chat_server(
                port=args.port,
                include_gh_health=args.include_gh_health,
                owner=args.owner,
                rhino_process_id=args.rhino_process_id,
                rhino_process_start_utc_ticks=(
                    args.rhino_process_start_utc_ticks
                ),
                backend_mode=configuration.backend_mode,
                prime_backend=configuration.prime_backend,
            )
            try:
                await wait_for_chat_server()
            finally:
                await stop_chat_server()
        finally:
            if configuration.registry is not None:
                configuration.registry.close()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
