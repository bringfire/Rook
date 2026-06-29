from __future__ import annotations

import os
import warnings
from pathlib import Path

import pytest
from PIL import Image


def make_png(path: Path, *, size: tuple[int, int] = (1, 1)) -> None:
    image = Image.new("RGBA", size, (32, 64, 96, 255))
    image.save(path, format="PNG")


def assert_texture_error(exc: pytest.ExceptionInfo[Exception], code: str) -> None:
    assert getattr(exc.value, "code") == code


@pytest.mark.parametrize(
    "source",
    [
        "http://example.test/texture.png",
        "https://example.test/texture.png",
        "file:///C:/tmp/texture.png",
        "ftp://example.test/texture.png",
        "data:image/png;base64,AAAA",
    ],
)
def test_url_schemes_are_rejected_before_file_io(
    source: str, monkeypatch: pytest.MonkeyPatch
):
    from rook.mesh2splat.textures import TextureError, resolve_texture_source

    stat_calls: list[str | os.PathLike[str]] = []

    def fail_if_called(path):
        stat_calls.append(path)
        raise AssertionError("os.stat must not be called for rejected URL schemes")

    monkeypatch.setattr(os, "stat", fail_if_called)

    with pytest.raises(TextureError) as exc:
        resolve_texture_source(source, allow_network_textures=False)

    assert_texture_error(exc, "texture_source_rejected")
    assert stat_calls == []


def test_relative_paths_are_rejected_before_file_io(monkeypatch: pytest.MonkeyPatch):
    from rook.mesh2splat.textures import TextureError, resolve_texture_source

    monkeypatch.setattr(
        os,
        "stat",
        lambda path: pytest.fail("os.stat must not be called for relative paths"),
    )

    with pytest.raises(TextureError) as exc:
        resolve_texture_source("textures/base.png", allow_network_textures=False)

    assert_texture_error(exc, "texture_source_rejected")


def test_unc_paths_are_skipped_unless_user_trusts_network_textures():
    from rook.mesh2splat.textures import TextureError, resolve_texture_source

    with pytest.raises(TextureError) as exc:
        resolve_texture_source("//server/share/texture.png", allow_network_textures=False)

    assert_texture_error(exc, "texture_source_rejected")


def test_user_trusted_network_paths_must_still_resolve_to_regular_files(
    monkeypatch: pytest.MonkeyPatch,
):
    from rook.mesh2splat import textures
    from rook.mesh2splat.textures import resolve_texture_source

    monkeypatch.setattr(textures, "_is_absolute_path", lambda path: True)
    monkeypatch.setattr(textures, "_is_network_path", lambda path: path.startswith("//"))
    monkeypatch.setattr(Path, "resolve", lambda self, strict=True: self)
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(textures, "_resolved_target_is_network", lambda path: False)

    result = resolve_texture_source(
        "//server/share/texture.png",
        allow_network_textures=True,
    )

    assert result.path == Path("//server/share/texture.png")
    assert [warning.code for warning in result.warnings] == [
        "network_texture_user_trusted"
    ]


def test_resolved_unc_targets_are_classified_as_network():
    from rook.mesh2splat import textures

    assert textures._resolved_target_is_network(Path("//server/share/texture.png"))
    assert textures._resolved_target_is_network(Path(r"\\server\share\texture.png"))


def test_resolved_mapped_drive_targets_use_windows_drive_classification(
    monkeypatch: pytest.MonkeyPatch,
):
    from rook.mesh2splat import textures

    monkeypatch.setattr(
        textures,
        "_windows_drive_is_remote",
        lambda path: str(path).replace("\\", "/").upper().startswith("Z:/"),
        raising=False,
    )

    assert textures._resolved_target_is_network(Path("Z:/texture.png"))
    assert not textures._resolved_target_is_network(Path("C:/texture.png"))


def test_mapped_drive_targets_are_rejected_by_default_before_resolution(
    monkeypatch: pytest.MonkeyPatch,
):
    from rook.mesh2splat import textures
    from rook.mesh2splat.textures import TextureError, resolve_texture_source

    monkeypatch.setattr(textures, "_is_absolute_path", lambda path: True)
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda self, strict=True: pytest.fail(
            "mapped network drives must be rejected before Path.resolve"
        ),
    )
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda self: pytest.fail(
            "mapped network drives must be rejected before file checks"
        ),
    )
    monkeypatch.setattr(
        textures,
        "_windows_drive_is_remote",
        lambda path: str(path).replace("\\", "/").upper().startswith("Z:/"),
        raising=False,
    )

    with pytest.raises(TextureError) as exc:
        resolve_texture_source("Z:/texture.png", allow_network_textures=False)

    assert_texture_error(exc, "texture_source_rejected")


def test_user_trusted_mapped_drive_targets_warn_after_resolution(
    monkeypatch: pytest.MonkeyPatch,
):
    from rook.mesh2splat import textures
    from rook.mesh2splat.textures import resolve_texture_source

    monkeypatch.setattr(textures, "_is_absolute_path", lambda path: True)
    monkeypatch.setattr(Path, "resolve", lambda self, strict=True: Path("Z:/texture.png"))
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(
        textures,
        "_windows_drive_is_remote",
        lambda path: str(path).replace("\\", "/").upper().startswith("Z:/"),
        raising=False,
    )

    result = resolve_texture_source("Z:/texture.png", allow_network_textures=True)

    assert result.path == Path("Z:/texture.png")
    assert [warning.code for warning in result.warnings] == [
        "network_texture_user_trusted"
    ]


def test_accepts_only_resolved_regular_local_files(tmp_path: Path):
    from rook.mesh2splat.textures import resolve_texture_source

    texture = tmp_path / "texture.png"
    make_png(texture)

    result = resolve_texture_source(str(texture), allow_network_textures=False)

    assert result.path == texture.resolve()
    assert result.warnings == ()


def test_rejects_missing_files_directories_and_devices(tmp_path: Path):
    from rook.mesh2splat.textures import TextureError, resolve_texture_source

    missing = tmp_path / "missing.png"
    directory = tmp_path / "texture-dir"
    directory.mkdir()

    for source in (missing, directory, os.devnull):
        with pytest.raises(TextureError) as exc:
            resolve_texture_source(str(source), allow_network_textures=False)

        assert_texture_error(exc, "texture_source_rejected")


def test_rejects_network_reparse_targets_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from rook.mesh2splat import textures
    from rook.mesh2splat.textures import TextureError, resolve_texture_source

    texture = tmp_path / "texture.png"
    make_png(texture)
    monkeypatch.setattr(textures, "_resolved_target_is_network", lambda path: True)

    with pytest.raises(TextureError) as exc:
        resolve_texture_source(str(texture), allow_network_textures=False)

    assert_texture_error(exc, "texture_source_rejected")


def test_source_byte_cap_uses_fstat_before_pillow_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from rook.mesh2splat.textures import (
        MAX_TEXTURE_BYTES_PER_SOURCE,
        TextureError,
        image_to_embedded_png,
    )

    texture = tmp_path / "texture.png"
    make_png(texture)
    open_calls: list[int] = []

    real_fstat = os.fstat

    def oversized_fstat(fd):
        stat_result = real_fstat(fd)
        values = list(stat_result)
        values[6] = MAX_TEXTURE_BYTES_PER_SOURCE + 1
        return os.stat_result(values)

    def fail_if_opened(fp, *args, **kwargs):
        open_calls.append(fp.fileno())
        raise AssertionError("Pillow must not open oversized source images")

    monkeypatch.setattr(os, "fstat", oversized_fstat)
    monkeypatch.setattr(Image, "open", fail_if_opened)

    with pytest.raises(TextureError) as exc:
        image_to_embedded_png(texture)

    assert_texture_error(exc, "texture_too_large")
    assert open_calls == []


def test_source_byte_cap_and_decode_share_open_file_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from rook.mesh2splat.textures import image_to_embedded_png

    texture = tmp_path / "texture.png"
    make_png(texture)
    opened_fds: list[int] = []
    real_stat = os.stat
    real_image_open = Image.open

    def fail_texture_path_stat(path, *args, **kwargs):
        if Path(path) == texture:
            pytest.fail("texture cap must use the already-open file descriptor")
        return real_stat(path, *args, **kwargs)

    def assert_file_handle_opened(fp, *args, **kwargs):
        assert not isinstance(fp, (str, os.PathLike))
        opened_fds.append(fp.fileno())
        return real_image_open(fp, *args, **kwargs)

    monkeypatch.setattr(os, "stat", fail_texture_path_stat)
    monkeypatch.setattr(Image, "open", assert_file_handle_opened)

    png_bytes = image_to_embedded_png(texture)

    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(opened_fds) == 1


def test_decompression_bomb_warnings_fail_with_decode_too_large(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from rook.mesh2splat.textures import TextureError, image_to_embedded_png

    texture = tmp_path / "texture.png"
    make_png(texture)

    def warn_on_open(path):
        warnings.warn(Image.DecompressionBombWarning("too many pixels"))
        return Image.new("RGBA", (1, 1))

    monkeypatch.setattr(Image, "open", warn_on_open)

    with pytest.raises(TextureError) as exc:
        image_to_embedded_png(texture)

    assert_texture_error(exc, "texture_decode_too_large")


def test_pillow_decompression_bomb_errors_fail_with_decode_too_large(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from rook.mesh2splat.textures import TextureError, image_to_embedded_png

    texture = tmp_path / "texture.png"
    make_png(texture)
    monkeypatch.setattr(
        Image,
        "open",
        lambda path: (_ for _ in ()).throw(
            Image.DecompressionBombError("too many pixels")
        ),
    )

    with pytest.raises(TextureError) as exc:
        image_to_embedded_png(texture)

    assert_texture_error(exc, "texture_decode_too_large")


def test_pixel_cap_fails_before_png_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from rook.mesh2splat.textures import (
        MAX_TEXTURE_PIXELS,
        TextureError,
        image_to_embedded_png,
    )

    texture = tmp_path / "texture.png"
    make_png(texture)

    class HeaderOnlyImage:
        size = (MAX_TEXTURE_PIXELS + 1, 1)

        def convert(self, mode):
            pytest.fail("oversized pixels must not be converted")

    image = HeaderOnlyImage()
    monkeypatch.setattr(Image, "open", lambda path: image)
    monkeypatch.setattr(
        Image.Image,
        "save",
        lambda self, fp, format=None: pytest.fail("oversized pixels must not save"),
    )

    with pytest.raises(TextureError) as exc:
        image_to_embedded_png(texture)

    assert_texture_error(exc, "texture_decode_too_large")


def test_decoded_byte_cap_fails_before_png_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from rook.mesh2splat import textures
    from rook.mesh2splat.textures import TextureError, image_to_embedded_png

    texture = tmp_path / "texture.png"
    make_png(texture)
    width = (textures.MAX_TEXTURE_DECODED_BYTES // 4) + 1

    class HeaderOnlyImage:
        def __init__(self):
            self.size = (width, 1)

        def convert(self, mode):
            return self

        @property
        def width(self):
            return self.size[0]

        @property
        def height(self):
            return self.size[1]

        def getbands(self):
            return ("R", "G", "B", "A")

    monkeypatch.setattr(textures, "MAX_TEXTURE_PIXELS", width)
    image = HeaderOnlyImage()
    monkeypatch.setattr(Image, "open", lambda path: image)
    monkeypatch.setattr(
        Image.Image,
        "save",
        lambda self, fp, format=None: pytest.fail("oversized decode must not save"),
    )

    with pytest.raises(TextureError) as exc:
        image_to_embedded_png(texture)

    assert_texture_error(exc, "texture_decode_too_large")


def test_valid_image_returns_embedded_png_bytes_without_sidecar(tmp_path: Path):
    from rook.mesh2splat.textures import image_to_embedded_png

    texture = tmp_path / "texture.jpg"
    image = Image.new("RGB", (2, 2), (40, 80, 120))
    image.save(texture, format="JPEG")

    png_bytes = image_to_embedded_png(texture)

    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert sorted(path.name for path in tmp_path.iterdir()) == ["texture.jpg"]


def test_texture_failure_with_scalar_fallback_uses_base_color_factor(
    tmp_path: Path,
):
    from rook.mesh2splat.textures import CapturedMaterial, normalize_material_texture

    material = CapturedMaterial(
        name="paint",
        base_color_texture=str(tmp_path / "missing.png"),
        base_color_factor=(0.25, 0.5, 0.75, 1.0),
    )

    normalized = normalize_material_texture(
        material,
        allow_network_textures=False,
    )

    assert normalized.base_color_factor == (0.25, 0.5, 0.75, 1.0)
    assert normalized.base_color_texture is None
    assert normalized.requires_base_color_texture is False
    assert [warning.code for warning in normalized.warnings] == [
        "texture_source_rejected"
    ]


def test_texture_rejection_with_scalar_fallback_preserves_warning_code():
    from rook.mesh2splat.textures import CapturedMaterial, normalize_material_texture

    material = CapturedMaterial(
        name="paint",
        base_color_texture="https://example.test/texture.png",
        base_color_factor=(0.25, 0.5, 0.75, 1.0),
    )

    normalized = normalize_material_texture(
        material,
        allow_network_textures=False,
    )

    assert normalized.base_color_factor == (0.25, 0.5, 0.75, 1.0)
    assert [warning.code for warning in normalized.warnings] == [
        "texture_source_rejected"
    ]


@pytest.mark.parametrize(
    "code",
    [
        "texture_too_large",
        "texture_decode_too_large",
    ],
)
def test_texture_size_failures_with_scalar_fallback_preserve_warning_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str
):
    from rook.mesh2splat import textures
    from rook.mesh2splat.textures import (
        CapturedMaterial,
        TextureError,
        normalize_material_texture,
    )

    texture = tmp_path / "texture.png"
    make_png(texture)
    monkeypatch.setattr(
        textures,
        "image_to_embedded_png",
        lambda path: (_ for _ in ()).throw(TextureError(code, "specific failure")),
    )
    material = CapturedMaterial(
        name="paint",
        base_color_texture=str(texture),
        base_color_factor=(0.25, 0.5, 0.75, 1.0),
    )

    normalized = normalize_material_texture(
        material,
        allow_network_textures=False,
    )

    assert [warning.code for warning in normalized.warnings] == [code]


def test_network_resolution_warning_survives_scalar_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from rook.mesh2splat import textures
    from rook.mesh2splat.textures import (
        CapturedMaterial,
        TextureError,
        TextureWarning,
        normalize_material_texture,
    )

    texture = tmp_path / "texture.png"
    make_png(texture)
    monkeypatch.setattr(
        textures,
        "resolve_texture_source",
        lambda path, *, allow_network_textures: textures.TextureResolution(
            path=texture,
            warnings=(
                TextureWarning(
                    "network_texture_user_trusted",
                    "network texture path was allowed by user opt-in",
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        textures,
        "image_to_embedded_png",
        lambda path: (_ for _ in ()).throw(
            TextureError("texture_read_failed", "specific failure")
        ),
    )
    material = CapturedMaterial(
        name="paint",
        base_color_texture="//server/share/texture.png",
        base_color_factor=(0.25, 0.5, 0.75, 1.0),
    )

    normalized = normalize_material_texture(
        material,
        allow_network_textures=True,
    )

    assert normalized.base_color_factor == (0.25, 0.5, 0.75, 1.0)
    assert [warning.code for warning in normalized.warnings] == [
        "network_texture_user_trusted",
        "texture_read_failed",
    ]


def test_network_resolve_failure_warning_survives_scalar_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    from rook.mesh2splat import textures
    from rook.mesh2splat.textures import CapturedMaterial, normalize_material_texture

    monkeypatch.setattr(textures, "_is_absolute_path", lambda path: True)
    monkeypatch.setattr(textures, "_is_network_path", lambda path: path.startswith("//"))
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda self, strict=True: (_ for _ in ()).throw(
            OSError("network target unavailable")
        ),
    )
    material = CapturedMaterial(
        name="paint",
        base_color_texture="//server/share/texture.png",
        base_color_factor=(0.25, 0.5, 0.75, 1.0),
    )

    normalized = normalize_material_texture(
        material,
        allow_network_textures=True,
    )

    assert normalized.base_color_factor == (0.25, 0.5, 0.75, 1.0)
    assert [warning.code for warning in normalized.warnings] == [
        "network_texture_user_trusted",
        "texture_source_rejected",
    ]


def test_passing_texture_requires_base_color_texture(tmp_path: Path):
    from rook.mesh2splat.textures import CapturedMaterial, normalize_material_texture

    texture = tmp_path / "texture.png"
    make_png(texture)
    material = CapturedMaterial(
        name="paint",
        base_color_texture=str(texture),
        base_color_factor=(1.0, 1.0, 1.0, 1.0),
    )

    normalized = normalize_material_texture(
        material,
        allow_network_textures=False,
    )

    assert normalized.base_color_factor is None
    assert normalized.base_color_texture is not None
    assert normalized.base_color_texture.startswith(b"\x89PNG\r\n\x1a\n")
    assert normalized.requires_base_color_texture is True
    assert normalized.warnings == ()


def test_texture_read_failure_without_scalar_fallback_is_testable_error(
    tmp_path: Path,
):
    from rook.mesh2splat.textures import (
        CapturedMaterial,
        TextureError,
        normalize_material_texture,
    )

    material = CapturedMaterial(
        name="paint",
        base_color_texture=str(tmp_path / "missing.png"),
        base_color_factor=None,
    )

    with pytest.raises(TextureError) as exc:
        normalize_material_texture(material, allow_network_textures=False)

    assert_texture_error(exc, "texture_source_rejected")


@pytest.mark.parametrize(
    "code",
    [
        "texture_source_rejected",
        "texture_too_large",
        "texture_decode_too_large",
    ],
)
def test_specific_texture_failures_without_scalar_fallback_preserve_error_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str
):
    from rook.mesh2splat import textures
    from rook.mesh2splat.textures import (
        CapturedMaterial,
        TextureError,
        normalize_material_texture,
    )

    texture = tmp_path / "texture.png"
    make_png(texture)
    monkeypatch.setattr(
        textures,
        "resolve_texture_source",
        lambda path, *, allow_network_textures: textures.TextureResolution(
            path=texture
        ),
    )
    monkeypatch.setattr(
        textures,
        "image_to_embedded_png",
        lambda path: (_ for _ in ()).throw(TextureError(code, "specific failure")),
    )
    material = CapturedMaterial(
        name="paint",
        base_color_texture=str(texture),
        base_color_factor=None,
    )

    with pytest.raises(TextureError) as exc:
        normalize_material_texture(material, allow_network_textures=False)

    assert_texture_error(exc, code)


def test_decode_read_failure_without_scalar_fallback_remains_read_failed(
    tmp_path: Path,
):
    from rook.mesh2splat.textures import (
        CapturedMaterial,
        TextureError,
        normalize_material_texture,
    )

    texture = tmp_path / "texture.png"
    texture.write_bytes(b"not an image")
    material = CapturedMaterial(
        name="paint",
        base_color_texture=str(texture),
        base_color_factor=None,
    )

    with pytest.raises(TextureError) as exc:
        normalize_material_texture(material, allow_network_textures=False)

    assert_texture_error(exc, "texture_read_failed")


def test_material_without_texture_uses_scalar_base_color_only():
    from rook.mesh2splat.textures import CapturedMaterial, normalize_material_texture

    material = CapturedMaterial(
        name="paint",
        base_color_texture=None,
        base_color_factor=(0.1, 0.2, 0.3, 1.0),
    )

    normalized = normalize_material_texture(
        material,
        allow_network_textures=False,
    )

    assert normalized.base_color_factor == (0.1, 0.2, 0.3, 1.0)
    assert normalized.base_color_texture is None
    assert normalized.requires_base_color_texture is False
    assert normalized.warnings == ()


def test_required_texture_constants_are_exposed():
    from rook.mesh2splat import textures

    assert textures.MAX_TEXTURE_BYTES_PER_SOURCE == 64 * 1024 * 1024
    assert textures.MAX_TEXTURE_PIXELS == 16_777_216
    assert textures.MAX_TEXTURE_DECODED_BYTES == 64 * 1024 * 1024
