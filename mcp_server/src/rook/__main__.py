"""Entry point for running rook as a module: python -m rook"""

from __future__ import annotations

import sys

from .runtime_paths import load_runtime_dotenv, resolve_runtime_paths

_runtime_paths = resolve_runtime_paths()
_loaded_env = load_runtime_dotenv(_runtime_paths)


def _clear_pycache():
    """Clear __pycache__ dirs on startup to ensure fresh bytecode after code edits.

    Editable pip installs cache .pyc files that survive MCP server restarts,
    causing stale code to be loaded even after source files are modified.
    """
    import shutil
    src_dir = _runtime_paths.mcp_server_dir / "src"
    count = 0
    for cache_dir in src_dir.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)
        count += 1
    if count:
        print(f"[rook] Cleared {count} __pycache__ dirs", file=sys.stderr)


def main(argv: list[str] | None = None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "doctor":
        from .doctor import main as doctor_main

        return doctor_main(argv[1:])
    _clear_pycache()
    from .server import main as server_main

    return server_main()

if __name__ == "__main__":
    sys.exit(main())
