from __future__ import annotations

import base64
from pathlib import Path

from .env import OUTPUT_ROOT


SYNTHETIC_PROMPTS = {
    "red_cube": "a red cube on a white background",
    "blue_chair": "a simple blue chair on a plain gray floor",
    "white_arch": "a small white architectural arch on a neutral background",
}


_PNG_1X1_RED = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR4nGP4z8AAAAMBAQDJ"
    "/pLvAAAAAElFTkSuQmCC"
)


def synthetic_prompt(name: str) -> str:
    try:
        return SYNTHETIC_PROMPTS[name]
    except KeyError as exc:
        names = ", ".join(sorted(SYNTHETIC_PROMPTS))
        raise SystemExit(f"Unknown synthetic prompt '{name}'. Use one of: {names}") from exc


def assert_synthetic_prompt(prompt: str) -> None:
    if prompt not in SYNTHETIC_PROMPTS.values():
        raise SystemExit(
            "Probe prompt is not in SYNTHETIC_PROMPTS. Refusing to capture possible client work."
        )


def write_red_cube_png() -> Path:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_ROOT / "synthetic-red-cube-input.png"
    if not path.exists():
        path.write_bytes(base64.b64decode(_PNG_1X1_RED))
    return path
