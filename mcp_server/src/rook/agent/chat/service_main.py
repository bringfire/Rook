"""Standalone entrypoint for the Rhino-owned chat service."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from rook.runtime_paths import get_acp_data_paths, resolve_runtime_paths

from .acp_conversation import AcpConversationManager, DirectAcpProcessFactory
from .acp_presentation import PresentationCache
from .acp_storage import AssociationStore
from .prime_runtime import RuntimeUnavailable, load_and_verify_runtime
from .server import start_chat_server, stop_chat_server, wait_for_chat_server


_RUNTIME_ID = re.compile(r"^[A-F0-9]{64}$")
_MAX_CURRENT_POINTER_BYTES = 4096


class InstalledRuntimeCatalog:
    """Resolve only the product-qualified immutable Prime runtime."""

    def __init__(self, prime_root: Path) -> None:
        self._prime_root = prime_root.expanduser().resolve(strict=False)
        self._current_path = self._prime_root / "current.json"

    def latest(self):
        try:
            with self._current_path.open("rb") as stream:
                raw = stream.read(_MAX_CURRENT_POINTER_BYTES + 1)
            if len(raw) > _MAX_CURRENT_POINTER_BYTES:
                raise RuntimeUnavailable("qualified runtime pointer is invalid")
            payload = json.loads(raw.decode("utf-8", errors="strict"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeUnavailable("qualified runtime pointer is unavailable") from exc
        canonical = (
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        ).encode("utf-8")
        if (
            not raw
            or raw != canonical
            or not isinstance(payload, dict)
            or set(payload) != {"runtimeId"}
            or type(payload.get("runtimeId")) is not str
            or not _RUNTIME_ID.fullmatch(payload["runtimeId"])
        ):
            raise RuntimeUnavailable("qualified runtime pointer is invalid")
        return self.get(payload["runtimeId"])

    def get(self, runtime_id: str):
        return load_and_verify_runtime(self._prime_root, runtime_id)


def build_acp_manager(
    prime_base_environment: Mapping[str, str],
) -> tuple[AcpConversationManager, bool]:
    runtime_paths = resolve_runtime_paths()
    data_paths = get_acp_data_paths(runtime_paths)
    data_paths.create_roots()
    catalog = InstalledRuntimeCatalog(runtime_paths.install_root / "prime")
    runtime_available = True
    try:
        catalog.latest()
    except RuntimeUnavailable:
        runtime_available = False
    manager = AcpConversationManager(
        AssociationStore(data_paths),
        catalog,
        DirectAcpProcessFactory(prime_base_environment),
        PresentationCache(data_paths.presentation_root),
    )
    return manager, runtime_available


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
