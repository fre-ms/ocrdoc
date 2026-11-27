"""Open what is to be read: a PDF, or a picture, which stays a picture.

docrepro forces no file type.  ocrdoc reads a PDF and lays its text over the pages; it
reads a picture as well, and lays the reading beside it, since a picture has no place for
text (:mod:`ocrdoc.output`).

A picture is looked at as pages to read it: one for each picture in the file, upright as
its EXIF orientation says, the long side that of A4.  That is the page the standard medRDS
binds a picture into (9.5, what typdoc does) and the page optdoc looks at, so that a box
means the same in every tool: the page of a picture is doccor's (:mod:`doccor.pictures`).
The reading gives a picture's boxes in the picture's own pixels (:func:`pixel_sizes`).
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
from doccor import pictures as view
from doccor.pictures import LONG_SIDE, heic_available, is_picture

from ocrdoc.errors import OcrdocError


def open_document(path: str | Path) -> pymupdf.Document:
    """A PDF to read, every page upright (``/Rotate`` taken into its content, which looks
    the same), or a picture as pages to read.  Raises "missing", "unsupported" (neither
    a PDF nor a picture ocrdoc can open), "encrypted", "unreadable"."""
    path = Path(path)
    suffix = path.suffix.lower()
    if not path.is_file():
        raise OcrdocError("missing")
    if suffix != ".pdf" and not is_picture(path):
        raise OcrdocError("unsupported", suffix=suffix or "(none)")
    try:
        doc = pymupdf.open(path) if suffix == ".pdf" else view.pages(path)
    except view.NoHeic as e:  # a HEIC photo, and pillow-heif (the extra "ocr") is not there
        raise OcrdocError("unsupported", suffix=suffix) from e
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


def pixel_sizes(path: str | Path) -> list[tuple[int, int]]:
    """Width and height in pixels of every picture in the file, upright."""
    try:
        return view.sizes(path)
    except view.NoHeic as e:
        raise OcrdocError("unsupported", suffix=Path(path).suffix.lower()) from e
    except Exception as e:
        raise OcrdocError("unreadable") from e


__all__ = ["LONG_SIDE", "heic_available", "is_picture", "open_document", "pixel_sizes"]
