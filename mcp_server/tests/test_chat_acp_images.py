from __future__ import annotations

import base64
import hashlib
from io import BytesIO

import pytest
from PIL import Image

from rook.agent.chat.acp_images import ImageAdmissionError, validate_images


def _png(width: int = 2, height: int = 3) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_valid_image_becomes_acp_block_but_cache_metadata_contains_no_bytes() -> None:
    binary = _png()

    (validated,) = validate_images(
        [
            {
                "file_name": "fixture.png",
                "mime_type": "image/png",
                "base64_data": base64.b64encode(binary).decode("ascii"),
            }
        ],
        encoded_http_body_bytes=len(binary) * 2,
    )

    assert validated.binary_bytes == len(binary)
    assert (validated.width, validated.height) == (2, 3)
    assert validated.sha256 == hashlib.sha256(binary).hexdigest()
    assert validated.acp_block.data == base64.b64encode(binary).decode("ascii")
    metadata = validated.cache_metadata()
    assert metadata == {
        "fileName": "fixture.png",
        "mimeType": "image/png",
        "binaryBytes": len(binary),
        "width": 2,
        "height": 3,
        "sha256": hashlib.sha256(binary).hexdigest(),
        "previewAvailable": False,
    }
    assert "data" not in metadata and "base64Data" not in metadata


@pytest.mark.parametrize(
    ("mime_type", "encoded"),
    [
        ("image/png", "%%%"),
        ("image/jpeg", base64.b64encode(_png()).decode("ascii")),
        ("image/gif", base64.b64encode(b"GIF89a").decode("ascii")),
    ],
)
def test_image_admission_rejects_invalid_base64_or_mime_magic(mime_type: str, encoded: str) -> None:
    with pytest.raises(ImageAdmissionError, match="invalid_image"):
        validate_images(
            [{"file_name": "bad", "mime_type": mime_type, "base64_data": encoded}],
            encoded_http_body_bytes=len(encoded),
        )


def test_image_admission_enforces_count_http_and_dimension_bounds() -> None:
    encoded = base64.b64encode(_png()).decode("ascii")
    with pytest.raises(ImageAdmissionError):
        validate_images(
            [
                {"file_name": f"{index}.png", "mime_type": "image/png", "base64_data": encoded}
                for index in range(9)
            ],
            encoded_http_body_bytes=9 * len(encoded),
        )

    with pytest.raises(ImageAdmissionError):
        validate_images(
            [{"file_name": "huge-request.png", "mime_type": "image/png", "base64_data": encoded}],
            encoded_http_body_bytes=48 * 1024 * 1024 + 1,
        )

    too_wide = base64.b64encode(_png(width=16_385, height=1)).decode("ascii")
    with pytest.raises(ImageAdmissionError):
        validate_images(
            [{"file_name": "wide.png", "mime_type": "image/png", "base64_data": too_wide}],
            encoded_http_body_bytes=len(too_wide),
        )
