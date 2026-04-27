from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRATCH_ROOT = REPO_ROOT / ".scratch" / "multi-provider-spike"
ENV_PATH = SCRATCH_ROOT / ".env"
CAPTURE_ROOT = SCRATCH_ROOT / "captures"
OUTPUT_ROOT = SCRATCH_ROOT / "outputs"


@dataclass(frozen=True)
class Keys:
    fal: str | None
    replicate: str | None
    google: str | None
    tencent: str | None


def load_keys() -> Keys:
    if not ENV_PATH.exists():
        raise SystemExit(
            f"Missing {ENV_PATH}. Create it from the README before running probes."
        )

    values = dotenv_values(ENV_PATH)
    return Keys(
        fal=_clean(values.get("FAL_KEY")),
        replicate=_clean(values.get("REPLICATE_API_TOKEN")),
        google=_clean(values.get("GOOGLE_API_KEY")),
        tencent=_clean(values.get("TENCENT_KEY")),
    )


def require_key(name: str, value: str | None) -> str:
    if not value:
        raise SystemExit(
            f"Missing {name} in {ENV_PATH}. This probe cannot run without it."
        )
    return value


def ensure_runtime_dirs() -> None:
    CAPTURE_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
