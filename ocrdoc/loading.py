"""Open what is to be read: a PDF, or a picture, which stays a picture.

docrepro forces no file type.  ocrdoc reads a PDF and lays its text over the pages; it
reads a picture as well, and lays the reading beside it, since a picture has no place for
text (:mod:`ocrdoc.output`).

A picture is looked at as pages to read it: one for each picture in the file, upright as
its EXIF orientation says, the long side that of A4.  That is the page the standard medRDS
binds a picture into (9.5, what typdoc does) and the page optdoc looks at, so that a box
means the same in every tool; the reading gives a picture's boxes in the picture's own
pixels (:func:`pixel_sizes`).
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pymupdf

from ocrdoc.errors import OcrdocError

PICTURES = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".heif", ".webp", ".bmp", ".gif",
            ".pnm")
HEIC = (".heic", ".heif")
LONG_SIDE = 842.0  # points: the long side of A4, as medRDS 9.5 binds a picture
_ORIENTATION = 0x0112
_ON_ITS_SIDE = (5, 6, 7, 8)  # EXIF orientations that swap width and height


def is_picture(path: str | Path) -> bool:
    """True for a file whose type is a picture's (by its name)."""
    return Path(path).suffix.lower() in PICTURES


def heic_available() -> bool:
    """True when HEIC and HEIF photos can be opened (pillow-heif, with the extra "ocr")."""
    from importlib.util import find_spec

    return find_spec("pillow_heif") is not None


def _pillow(path: Path) -> Any:
    """Pillow's Image module, able to open the file: with HEIC and HEIF where
    pillow-heif is installed ("unsupported" for such a file where it is not)."""
    from PIL import Image

    if path.suffix.lower() in HEIC:
        try:
            import pillow_heif
        except ImportError as e:
            raise OcrdocError("unsupported", suffix=path.suffix.lower()) from e
        pillow_heif.register_heif_opener()
    return Image


def open_document(path: str | Path) -> pymupdf.Document:
    """A PDF to read, every page upright (``/Rotate`` taken into its content, which looks
    the same), or a picture as pages to read.  Raises "missing", "unsupported" (neither
    a PDF nor a picture ocrdoc knows), "encrypted", "unreadable"."""
    path = Path(path)
    suffix = path.suffix.lower()
    if not path.is_file():
        raise OcrdocError("missing")
    if suffix != ".pdf" and suffix not in PICTURES:
        raise OcrdocError("unsupported", suffix=suffix or "(none)")
    try:
        doc = pymupdf.open(path) if suffix == ".pdf" else _pages(path)
    except OcrdocError:
        raise
    except Exception as e:  # MuPDF and Pillow word their failures with the file's name
        raise OcrdocError("unreadable") from e
    if doc.needs_pass:
        doc.close()
        raise OcrdocError("encrypted")
    if doc.page_count == 0:
        doc.close()
        raise OcrdocError("unreadable")
    for page in doc.pages():
        if page.rotation:
            page.remove_rotation()
    return doc


def _upright(path: Path) -> list[Any]:
    """Every picture of the file, upright as its orientation says, what is transparent
    on white."""
    from PIL import ImageOps

    image_module = _pillow(path)
    pictures = []
    with image_module.open(path) as image:
        for n in range(getattr(image, "n_frames", 1)):
            image.seek(n)
            upright = ImageOps.exif_transpose(image)
            if upright.mode in ("RGBA", "LA", "PA") or "transparency" in upright.info:
                rgba = upright.convert("RGBA")
                white = image_module.new("RGBA", rgba.size, (255, 255, 255, 255))
                upright = image_module.alpha_composite(white, rgba)
            pictures.append(upright.convert("RGB"))
    return pictures


def pixel_sizes(path: str | Path) -> list[tuple[int, int]]:
    """Width and height in pixels of every picture in the file, upright (as
    :func:`_upright` turns it; read from what the file says, without decoding it)."""
    path = Path(path)
    try:
        sizes = []
        with _pillow(path).open(path) as image:
            for n in range(getattr(image, "n_frames", 1)):
                image.seek(n)
                width, height = image.size
                if image.getexif().get(_ORIENTATION) in _ON_ITS_SIDE:
                    width, height = height, width
                sizes.append((width, height))
        return sizes
    except OcrdocError:
        raise
    except Exception as e:
        raise OcrdocError("unreadable") from e


def _pages(path: Path) -> pymupdf.Document:
    """The pictures of a file as pages: each fills its page, whose long side is that of
    A4."""
    doc = pymupdf.open()
    for picture in _upright(path):
        buffer = io.BytesIO()
        picture.save(buffer, format="PNG", compress_level=1)
        between = pymupdf.open("png", buffer.getvalue())
        source = pymupdf.open("pdf", between.convert_to_pdf())
        try:
            sheet = source[0]
            scale = LONG_SIDE / max(sheet.rect.width, sheet.rect.height)
            page = doc.new_page(width=round(sheet.rect.width * scale, 2),
                                height=round(sheet.rect.height * scale, 2))
            page.show_pdf_page(page.rect, source, 0)
        finally:
            source.close()
            between.close()
    result = pymupdf.open("pdf", doc.tobytes())  # independent of what it was made from
    doc.close()
    return result
