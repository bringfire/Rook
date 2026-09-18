"""Strict live-only image admission for ACP prompts."""

from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Mapping, Sequence

from acp.schema import ImageContentBlock
from PIL import Image, UnidentifiedImageError


MAX_IMAGES_PER_TURN = 8
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_IMAGE_BYTES_PER_TURN = 32 * 1024 * 1024
MAX_HTTP_BODY_BYTES = 48 * 1024 * 1024
MAX_IMAGE_DIMENSION = 16_384
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_FILE_NAME_UTF8_BYTES = 512


class ImageAdmissionError(ValueError):
    code = "invalid_image"

    def __init__(self, detail: str) -> None:
        super().__init__(f"{self.code}: {detail}")


@dataclass(frozen=True)
class ValidatedImage:
    file_name: str
    mime_type: str
    binary_bytes: int
    width: int
    height: int
    sha256: str
    acp_block: ImageContentBlock

    def cache_metadata(self) -> dict[str, Any]:
        return {
            "fileName": self.file_name,
            "mimeType": self.mime_type,
            "binaryBytes": self.binary_bytes,
            "width": self.width,
            "height": self.height,
            "sha256": self.sha256,
            "previewAvailable": False,
        }


def _matches_magic(binary: bytes, mime_type: str) -> bool:
    if mime_type == "image/png":
        return binary.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type == "image/jpeg":
        return binary.startswith(b"\xff\xd8\xff")
    if mime_type == "image/webp":
        return len(binary) >= 12 and binary[:4] == b"RIFF" and binary[8:12] == b"WEBP"
    return False


def validate_images(
    images: Sequence[Mapping[str, Any]],
    *,
    encoded_http_body_bytes: int,
) -> tuple[ValidatedImage, ...]:
    if encoded_http_body_bytes < 0 or encoded_http_body_bytes > MAX_HTTP_BODY_BYTES:
        raise ImageAdmissionError("encoded HTTP request is oversized")
    if len(images) > MAX_IMAGES_PER_TURN:
        raise ImageAdmissionError("too many images")

    validated: list[ValidatedImage] = []
    total_binary_bytes = 0
    for entry in images:
        file_name = entry.get("file_name")
        mime_type = entry.get("mime_type")
        encoded = entry.get("base64_data")
        if not isinstance(file_name, str) or not file_name or len(file_name.encode("utf-8")) > MAX_IMAGE_FILE_NAME_UTF8_BYTES:
            raise ImageAdmissionError("file name is invalid")
        if not isinstance(mime_type, str) or not isinstance(encoded, str):
            raise ImageAdmissionError("image fields are invalid")
        try:
            binary = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ImageAdmissionError("base64 is invalid") from exc
        if not binary or len(binary) > MAX_IMAGE_BYTES:
            raise ImageAdmissionError("image binary size is invalid")
        total_binary_bytes += len(binary)
        if total_binary_bytes > MAX_IMAGE_BYTES_PER_TURN:
            raise ImageAdmissionError("turn image bytes are oversized")
        if not _matches_magic(binary, mime_type):
            raise ImageAdmissionError("MIME type does not match image magic")
        try:
            with Image.open(BytesIO(binary)) as image:
                width, height = image.size
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ImageAdmissionError("image content is invalid") from exc
        if (
            width <= 0
            or height <= 0
            or width > MAX_IMAGE_DIMENSION
            or height > MAX_IMAGE_DIMENSION
            or width * height > MAX_IMAGE_PIXELS
        ):
            raise ImageAdmissionError("image dimensions are invalid")
        validated.append(
            ValidatedImage(
                file_name=file_name,
                mime_type=mime_type,
                binary_bytes=len(binary),
                width=width,
                height=height,
                sha256=hashlib.sha256(binary).hexdigest(),
                acp_block=ImageContentBlock(type="image", data=encoded, mime_type=mime_type),
            )
        )
    return tuple(validated)
