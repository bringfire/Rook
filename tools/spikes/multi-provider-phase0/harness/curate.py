from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from .env import CAPTURE_ROOT, REPO_ROOT
from .redact import redact_capture


BINARY_VALUE_KEYS = {"data", "image_base64", "b64_json", "bytes"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Curate redacted spike captures for commit.")
    parser.add_argument("--spike-date", required=True, help="Completion date, e.g. 2026-04-29")
    args = parser.parse_args()

    dest = REPO_ROOT / "docs" / "rook_docs" / "artifacts" / f"{args.spike_date}-multi-provider-spike"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    if not CAPTURE_ROOT.exists():
        raise SystemExit(f"Missing capture root: {CAPTURE_ROOT}")

    for probe_dir in sorted(path for path in CAPTURE_ROOT.iterdir() if path.is_dir()):
        out_dir = dest / probe_dir.name
        out_dir.mkdir(parents=True, exist_ok=True)
        for source in sorted(probe_dir.glob("*.json")):
            payload = json.loads(source.read_text(encoding="utf-8"))
            curated = _drop_binary_values(redact_capture(payload))
            (out_dir / source.name).write_text(
                json.dumps(curated, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        notes = probe_dir / "notes.md"
        if notes.exists():
            shutil.copyfile(notes, out_dir / "notes.md")

    print(dest)


def _drop_binary_values(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if lowered in BINARY_VALUE_KEYS:
                result[key] = "<DROPPED_BINARY_OR_BASE64>"
            else:
                result[key] = _drop_binary_values(item)
        return result
    if isinstance(value, list):
        return [_drop_binary_values(item) for item in value]
    if isinstance(value, str) and _looks_like_data_uri_or_long_base64(value):
        return "<DROPPED_BINARY_OR_BASE64>"
    return value


def _looks_like_data_uri_or_long_base64(value: str) -> bool:
    if value.startswith("data:"):
        return True
    if len(value) < 300:
        return False
    alphabet = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
    return all(char in alphabet for char in value)


if __name__ == "__main__":
    main()
