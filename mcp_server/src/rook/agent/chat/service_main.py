"""Standalone entrypoint for the Rhino-owned chat service."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from .server import start_chat_server, stop_chat_server, wait_for_chat_server


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
    return parser.parse_args()


async def _run_service(
    args: argparse.Namespace,
    loaded_env: str | None,
    prime_base_environment: Mapping[str, str],
) -> None:
    del loaded_env
    await start_chat_server(
        port=args.port,
        include_gh_health=args.include_gh_health,
        owner=args.owner,
        rhino_process_id=args.rhino_process_id,
        prime_base_environment=prime_base_environment,
    )
    try:
        await wait_for_chat_server()
    finally:
        await stop_chat_server()


def main() -> None:
    prime_base_environment = MappingProxyType(dict(os.environ))
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
    loaded_env = _load_env()
    asyncio.run(_run_service(args, loaded_env, prime_base_environment))


if __name__ == "__main__":
    main()
