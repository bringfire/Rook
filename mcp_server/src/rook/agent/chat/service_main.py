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

import httpx

from rook.bridge import _fetch_verified_panel_capabilities, discover_instances
from rook.runtime_paths import get_acp_data_paths, resolve_runtime_paths
from rook.targeting import PanelTargetLock, resolve_panel_target_instance

from .acp_conversation import AcpConversationManager, DirectAcpProcessFactory
from .acp_presentation import PresentationCache
from .acp_storage import AssociationStore, RookBinding
from .configuration_http import ConfigurationHttp
from .prime_runtime import RuntimeUnavailable, load_and_verify_runtime
from .prime_runtime_artifact import read_current_runtime_id
from .server import start_chat_server, stop_chat_server, wait_for_chat_server


class InstalledRuntimeCatalog:
    """Resolve only the product-qualified immutable Prime runtime."""

    def __init__(self, prime_root: Path) -> None:
        self._prime_root = prime_root.absolute()

    def latest(self):
        return self.get(read_current_runtime_id(self._prime_root))

    def get(self, runtime_id: str):
        return load_and_verify_runtime(self._prime_root, runtime_id)


def build_configuration_service(prime_base_environment: Mapping[str, str]) -> ConfigurationHttp:
    paths = resolve_runtime_paths()
    return ConfigurationHttp(InstalledRuntimeCatalog(paths.install_root / "prime"), prime_base_environment, paths.data_root)


async def _target_available(binding: RookBinding) -> bool:
    lock = PanelTargetLock(
        mode="panel_locked",
        host_generation_id=binding.host_generation_id,
        process_id=binding.route_process_id,
        document_serial_number=binding.rhino_document_serial,
    )
    instance = resolve_panel_target_instance(discover_instances(), lock)
    if instance is None:
        return False
    # Availability is a bounded snapshot, never a fallback to another document.
    async with asyncio.timeout(2), httpx.AsyncClient(timeout=2, trust_env=False) as client:
        await _fetch_verified_panel_capabilities(client, instance, lock)
        host = instance.get("host") or "127.0.0.1"
        response = await client.get(
            f"http://{host}:{instance['port']}/document",
            params={"documentSerialNumber": binding.rhino_document_serial},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("success") is not True:
            return False
        data = payload.get("data")
        serial = data.get("documentSerialNumber") if isinstance(data, dict) else None
        return type(serial) is int and serial == binding.rhino_document_serial


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
        DirectAcpProcessFactory({**prime_base_environment, "ROOK_DATA_DIR": str(runtime_paths.data_root)}),
        PresentationCache(data_paths.presentation_root),
        target_available=_target_available,
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
