from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image


MAX_TEXTURE_BYTES_PER_SOURCE = 64 * 1024 * 1024
MAX_TEXTURE_PIXELS = 16_777_216
MAX_TEXTURE_DECODED_BYTES = 64 * 1024 * 1024

REJECTED_URL_SCHEMES = {"http", "https", "file", "ftp", "data"}
SOURCE_REJECTED = "texture_source_rejected"
TEXTURE_TOO_LARGE = "texture_too_large"
DECODE_TOO_LARGE = "texture_decode_too_large"
READ_FAILED = "texture_read_failed"


@dataclass(frozen=True)
class TextureWarning:
    code: str
    message: str


@dataclass(frozen=True)
class TextureResolution:
    path: Path
    warnings: tuple[TextureWarning, ...] = ()


@dataclass(frozen=True)
class CapturedMaterial:
    name: str
    base_color_texture: str | None = None
    base_color_factor: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class NormalizedMaterial:
    base_color_factor: tuple[float, float, float, float] | None = None
    base_color_texture: bytes | None = None
    requires_base_color_texture: bool = False
    warnings: tuple[TextureWarning, ...] = ()


class TextureError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        warnings: tuple[TextureWarning, ...] = (),
    ):
        super().__init__(message)
        self.code = code
        self.warnings = warnings


def resolve_texture_source(
    path: str, *, allow_network_textures: bool
) -> TextureResolution:
    if not isinstance(path, str) or not path:
        raise TextureError(SOURCE_REJECTED, "texture path must be a non-empty string")
    if _has_rejected_url_scheme(path):
        raise TextureError(SOURCE_REJECTED, "texture URL schemes are not supported")
    if not _is_absolute_path(path):
        raise TextureError(SOURCE_REJECTED, "texture path must be absolute")

    warnings_: list[TextureWarning] = []
    if _is_network_path(path):
        if not allow_network_textures:
            raise TextureError(
                SOURCE_REJECTED,
                "network texture paths require allowNetworkTextures=true",
            )
        warnings_.append(
            TextureWarning(
                "network_texture_user_trusted",
                "network texture path was allowed by user opt-in",
            )
        )
    elif _windows_drive_is_remote(path):
        if not allow_network_textures:
            raise TextureError(
                SOURCE_REJECTED,
                "network texture paths require allowNetworkTextures=true",
            )
        warnings_.append(
            TextureWarning(
                "network_texture_user_trusted",
                "network texture target was allowed by user opt-in",
            )
        )

    try:
        resolved = Path(path).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise TextureError(
            SOURCE_REJECTED,
            "texture path must resolve",
            warnings=tuple(warnings_),
        ) from exc

    target_is_network = _resolved_target_is_network(resolved)
    if target_is_network and not allow_network_textures:
        raise TextureError(
            SOURCE_REJECTED,
            "texture target resolves to a network location",
        )
    if target_is_network and not warnings_:
        warnings_.append(
            TextureWarning(
                "network_texture_user_trusted",
                "network texture target was allowed by user opt-in",
            )
        )

    if not resolved.is_file():
        raise TextureError(SOURCE_REJECTED, "texture path must be a regular file")

    return TextureResolution(path=resolved, warnings=tuple(warnings_))


def image_to_embedded_png(path: Path) -> bytes:
    try:
        source_file = path.open("rb")
    except OSError as exc:
        raise TextureError(READ_FAILED, "texture source could not be read") from exc

    with source_file:
        try:
            source_bytes = os.fstat(source_file.fileno()).st_size
        except OSError as exc:
            raise TextureError(READ_FAILED, "texture source could not be read") from exc
        if source_bytes > MAX_TEXTURE_BYTES_PER_SOURCE:
            raise TextureError(TEXTURE_TOO_LARGE, "texture source exceeds byte cap")

        previous_max_pixels = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = MAX_TEXTURE_PIXELS
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                try:
                    image = Image.open(source_file)
                    width, height = image.size
                    _enforce_decode_caps(width, height, 4)
                    rgba = image.convert("RGBA")
                    _enforce_decode_caps(
                        rgba.width, rgba.height, len(rgba.getbands())
                    )
                except Image.DecompressionBombWarning as exc:
                    raise TextureError(
                        DECODE_TOO_LARGE,
                        "texture decode exceeds Pillow pixel safety limit",
                    ) from exc
                except Image.DecompressionBombError as exc:
                    raise TextureError(
                        DECODE_TOO_LARGE,
                        "texture decode exceeds Pillow pixel safety limit",
                    ) from exc
                except TextureError:
                    raise
                except OSError as exc:
                    raise TextureError(
                        READ_FAILED, "texture could not be decoded"
                    ) from exc

            output = BytesIO()
            rgba.save(output, format="PNG")
            return output.getvalue()
        finally:
            Image.MAX_IMAGE_PIXELS = previous_max_pixels


def normalize_material_texture(
    material: CapturedMaterial, *, allow_network_textures: bool
) -> NormalizedMaterial:
    if not material.base_color_texture:
        return NormalizedMaterial(base_color_factor=material.base_color_factor)

    resolution_warnings: tuple[TextureWarning, ...] = ()
    try:
        resolution = resolve_texture_source(
            material.base_color_texture,
            allow_network_textures=allow_network_textures,
        )
        resolution_warnings = resolution.warnings
        png_bytes = image_to_embedded_png(resolution.path)
    except TextureError as exc:
        if material.base_color_factor is None:
            raise
        return NormalizedMaterial(
            base_color_factor=material.base_color_factor,
            warnings=(
                *resolution_warnings,
                *exc.warnings,
                TextureWarning(exc.code, str(exc)),
            ),
        )

    return NormalizedMaterial(
        base_color_texture=png_bytes,
        requires_base_color_texture=True,
        warnings=resolution.warnings,
    )


def _has_rejected_url_scheme(path: str) -> bool:
    return urlparse(path).scheme.lower() in REJECTED_URL_SCHEMES


def _is_absolute_path(path: str) -> bool:
    return Path(path).is_absolute()


def _is_network_path(path: str | Path) -> bool:
    normalized = str(path).replace("\\", "/")
    return normalized.startswith("//")


def _resolved_target_is_network(path: Path) -> bool:
    return _is_network_path(path) or _windows_drive_is_remote(path)


def _windows_drive_is_remote(path: str | Path) -> bool:
    if os.name != "nt":
        return False

    drive = Path(path).drive
    if not drive:
        return False

    try:
        import ctypes

        drive_type = ctypes.windll.kernel32.GetDriveTypeW(f"{drive}\\")
    except (AttributeError, OSError, ValueError):
        return False

    return drive_type == 4


def _enforce_decode_caps(width: int, height: int, channels: int) -> None:
    pixels = width * height
    if pixels > MAX_TEXTURE_PIXELS:
        raise TextureError(DECODE_TOO_LARGE, "texture exceeds pixel cap")
    if pixels * channels > MAX_TEXTURE_DECODED_BYTES:
        raise TextureError(DECODE_TOO_LARGE, "texture exceeds decoded byte cap")
