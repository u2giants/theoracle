"""Transparent images are flattened onto white before the vision call (#418)."""

from __future__ import annotations

import io

from PIL import Image

from brain.read.vision import flatten_alpha


def _png(mode: str, color: tuple[int, ...]) -> bytes:
    out = io.BytesIO()
    Image.new(mode, (4, 4), color).save(out, format="PNG")
    return out.getvalue()


def test_transparent_png_becomes_white() -> None:
    data, media_type = flatten_alpha(_png("RGBA", (0, 0, 0, 0)), "image/png")
    assert media_type == "image/png"
    with Image.open(io.BytesIO(data)) as image:
        assert image.mode == "RGB"
        assert image.getpixel((0, 0)) == (255, 255, 255)


def test_opaque_lines_stay_black() -> None:
    data, _ = flatten_alpha(_png("RGBA", (0, 0, 0, 255)), "image/png")
    with Image.open(io.BytesIO(data)) as image:
        assert image.getpixel((0, 0)) == (0, 0, 0)


def test_image_without_alpha_is_unchanged() -> None:
    original = _png("RGB", (10, 20, 30))
    assert flatten_alpha(original, "image/png") == (original, "image/png")


def test_jpeg_media_type_kept_when_no_alpha() -> None:
    out = io.BytesIO()
    Image.new("RGB", (4, 4), (1, 2, 3)).save(out, format="JPEG")
    assert flatten_alpha(out.getvalue(), "image/jpeg")[1] == "image/jpeg"


def test_unreadable_bytes_pass_through() -> None:
    assert flatten_alpha(b"not an image", "image/png") == (b"not an image", "image/png")
