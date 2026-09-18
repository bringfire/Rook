"""Canonical runtime path resolution for repo and installed Rook runtimes."""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    """Resolved runtime roots for the current Rook process."""

    mode: str
    install_root: Path
    data_root: Path
    logs_root: Path
    runtime_root: Path
    mcp_server_dir: Path
    repo_root: Path


_SAFE_ACP_FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class AcpDataPaths:
    """Product-owned durable roots for ACP-backed RookChat conversations."""

    root: Path
    conversations_root: Path
    sessions_root: Path
    presentation_root: Path
    claims_root: Path
    workspaces_root: Path

    @classmethod
    def from_runtime_paths(cls, runtime_paths: RuntimePaths) -> "AcpDataPaths":
        root = runtime_paths.data_root.resolve(strict=False) / "rookchat" / "acp" / "v1"
        return cls(
            root=root,
            conversations_root=root / "conversations",
            sessions_root=root / "sessions",
            presentation_root=root / "presentation",
            claims_root=root / "claims",
            workspaces_root=root / "workspaces",
        )

    def create_roots(self) -> None:
        for path in (
            self.conversations_root,
            self.sessions_root,
            self.presentation_root,
            self.claims_root,
            self.workspaces_root,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def conversation_path(self, conversation_id: str) -> Path:
        return self.conversations_root / f"{_validated_conversation_id(conversation_id)}.json"

    def session_path(self, conversation_id: str) -> Path:
        return self.sessions_root / f"{_validated_conversation_id(conversation_id)}.jsonl"

    def presentation_path(self, conversation_id: str) -> Path:
        return self.presentation_root / _validated_conversation_id(conversation_id)

    def workspace_path(self, conversation_id: str) -> Path:
        return self.workspaces_root / _validated_conversation_id(conversation_id)

    def canonical_session(self, file_name: str) -> str:
        if not _SAFE_ACP_FILE_NAME.fullmatch(file_name) or not file_name.endswith(".jsonl"):
            raise ValueError("ACP session file name is invalid")
        return str((self.sessions_root / file_name).resolve(strict=False))


def _validated_conversation_id(value: str) -> str:
    if not isinstance(value, str) or len(value) != 32:
        raise ValueError("conversation ID must be a lowercase UUID hex value")
    try:
        parsed = uuid.UUID(hex=value)
    except (ValueError, AttributeError) as exc:
        raise ValueError("conversation ID must be a lowercase UUID hex value") from exc
    if parsed.hex != value:
        raise ValueError("conversation ID must be a lowercase UUID hex value")
    return value


def get_acp_data_paths(runtime_paths: RuntimePaths | None = None) -> AcpDataPaths:
    return AcpDataPaths.from_runtime_paths(runtime_paths or resolve_runtime_paths())


_cached_runtime_paths: RuntimePaths | None = None


def _repo_fallback_roots() -> tuple[Path, Path]:
    package_dir = Path(__file__).resolve().parent
    mcp_server_dir = package_dir.parent.parent
    repo_root = mcp_server_dir.parent
    return repo_root, mcp_server_dir


def _same_path(left: Path, right: Path) -> bool:
    return left.expanduser().resolve() == right.expanduser().resolve()


def _installed_runtime_from_package_root(
    repo_root: Path,
    mcp_server_dir: Path,
    mode: str,
) -> RuntimePaths | None:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata or mode == "dev":
        return None

    runtime_root = Path(local_appdata).expanduser().resolve() / "Rook"
    install_root = runtime_root / "app"
    if not _same_path(repo_root, install_root):
        return None

    return RuntimePaths(
        mode="release",
        install_root=install_root,
        data_root=runtime_root / "data",
        logs_root=runtime_root / "logs",
        runtime_root=runtime_root,
        mcp_server_dir=mcp_server_dir.expanduser().resolve(),
        repo_root=repo_root.expanduser().resolve(),
    )


def _normalize_mode(mode: str | None) -> str:
    normalized = (mode or "").strip().lower()
    return normalized if normalized in {"dev", "release"} else ""


def resolve_runtime_paths() -> RuntimePaths:
    """Resolve runtime roots from environment, with repo bootstrap fallback."""

    global _cached_runtime_paths
    if _cached_runtime_paths is not None:
        return _cached_runtime_paths

    repo_root, fallback_mcp_server_dir = _repo_fallback_roots()
    install_root_env = os.environ.get("ROOK_INSTALL_ROOT")
    data_root_env = os.environ.get("ROOK_DATA_DIR")
    mode = _normalize_mode(os.environ.get("ROOK_MODE"))

    if install_root_env and data_root_env:
        install_root = Path(install_root_env).expanduser().resolve()
        data_root = Path(data_root_env).expanduser().resolve()
        # Installer-generated configs set ROOK_DATA_DIR to "<runtime_root>/data".
        # Derive runtime_root from that contract rather than inventing another env var.
        runtime_root = data_root.parent
        logs_root = runtime_root / "logs"
        mcp_server_dir = install_root / "mcp_server"

        if not mode:
            mode = "dev" if install_root == repo_root else "release"
    else:
        installed_paths = _installed_runtime_from_package_root(repo_root, fallback_mcp_server_dir, mode)
        if installed_paths is not None:
            _cached_runtime_paths = installed_paths
            return _cached_runtime_paths

        install_root = repo_root
        data_root = repo_root / "knowledge"
        runtime_root = repo_root
        logs_root = repo_root / "logs"
        mcp_server_dir = fallback_mcp_server_dir
        mode = "dev"

    _cached_runtime_paths = RuntimePaths(
        mode=mode,
        install_root=install_root,
        data_root=data_root,
        logs_root=logs_root,
        runtime_root=runtime_root,
        mcp_server_dir=mcp_server_dir,
        repo_root=repo_root,
    )
    return _cached_runtime_paths


def get_dotenv_search_paths(runtime_paths: RuntimePaths | None = None) -> list[Path]:
    """Return .env lookup paths in priority order for the active runtime."""

    runtime_paths = runtime_paths or resolve_runtime_paths()
    candidates = [
        runtime_paths.mcp_server_dir / ".env",
        runtime_paths.install_root / ".env",
    ]
    if runtime_paths.mode == "dev":
        candidates.append(runtime_paths.install_root / "autonomous_dev" / ".env")

    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        if candidate not in seen:
            ordered.append(candidate)
            seen.add(candidate)
    return ordered


def get_bundled_knowledge_root(runtime_paths: RuntimePaths | None = None) -> Path:
    """Return the read-only bundled knowledge root for the active runtime."""

    runtime_paths = runtime_paths or resolve_runtime_paths()
    return runtime_paths.install_root / "knowledge"


def get_mutable_knowledge_root(runtime_paths: RuntimePaths | None = None) -> Path:
    """Return the writable knowledge/data root for the active runtime."""

    runtime_paths = runtime_paths or resolve_runtime_paths()
    return runtime_paths.data_root


def resolve_writable_knowledge_path(*parts: str, runtime_paths: RuntimePaths | None = None) -> Path:
    """Return the canonical writable runtime-data path for a knowledge asset."""

    return get_mutable_knowledge_root(runtime_paths).joinpath(*parts)


def resolve_readable_knowledge_path(*parts: str, runtime_paths: RuntimePaths | None = None) -> Path:
    """Return the preferred readable path, falling back from mutable to bundled."""

    runtime_paths = runtime_paths or resolve_runtime_paths()
    mutable_path = get_mutable_knowledge_root(runtime_paths).joinpath(*parts)
    if mutable_path.exists():
        return mutable_path

    bundled_path = get_bundled_knowledge_root(runtime_paths).joinpath(*parts)
    if bundled_path.exists():
        return bundled_path

    return mutable_path


def load_runtime_dotenv(runtime_paths: RuntimePaths | None = None) -> Path | None:
    """Load the first matching .env file for the active runtime."""

    try:
        from dotenv import load_dotenv
    except ImportError:
        return None

    runtime_paths = runtime_paths or resolve_runtime_paths()
    for env_path in get_dotenv_search_paths(runtime_paths):
        if env_path.exists():
            load_dotenv(env_path)
            return env_path
    return None
