from __future__ import annotations

import struct
import zlib
from pathlib import Path

from .env import OUTPUT_ROOT


SYNTHETIC_PROMPTS = {
    "red_cube": "a red cube on a white background",
    "blue_chair": "a simple blue chair on a plain gray floor",
    "white_arch": "a small white architectural arch on a neutral background",
}


# Default 256×256 — large enough for fal's Hunyuan3D minimum (128px) and
# small enough to not bloat captures. Constructed via stdlib zlib+struct
# to avoid a Pillow dependency.
_SYNTHETIC_PNG_SIZE = 256


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


def write_red_cube_png(size: int = _SYNTHETIC_PNG_SIZE) -> Path:
    """Write a `size`×`size` solid-red PNG to OUTPUT_ROOT and return its path.

    Uses stdlib only. Default 256×256 satisfies fal Hunyuan3D's >=128px input
    constraint while staying small enough not to bloat captures.
    """
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_ROOT / f"synthetic-red-cube-input-{size}x{size}.png"
    if not path.exists():
        path.write_bytes(_build_solid_red_png(size, size))
    return path


def _build_solid_red_png(width: int, height: int) -> bytes:
    """Construct an RGB solid-red PNG using only the stdlib (zlib + struct)."""
    signature = b"\x89PNG\r\n\x1a\n"

    def chunk(name: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

    # IHDR: width, height, bit_depth=8, color_type=2 (RGB), compression=0, filter=0, interlace=0
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    # IDAT: each scanline prefixed with filter byte 0 (None) then width × RGB(255,0,0)
    row = b"\x00" + (b"\xff\x00\x00" * width)
    raw = row * height
    idat = zlib.compress(raw, 9)

    return signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
