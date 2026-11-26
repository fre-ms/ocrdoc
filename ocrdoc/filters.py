"""The steps that only help OCR read a page, applied to ocrdoc's own rendering of it and
never to the document.

A page as optdoc (or another program) prepared it is a faithful picture of the paper: a
stamp keeps its colour, a table its ruled lines.  Some of that stands in the way of the
recognition, though, so ocrdoc may change its own copy before reading it:

- **upscale**: the page is rendered at a multiple of the resolution (for low-resolution
  scans and photos);
- **letter mode**: grey, strokes sharpened, on that enlargement (measured: a hard local
  threshold looked crisp and wrecked the recognition; grey with sharpened strokes matched
  or beat the plain enlargement);
- **remove colour**: coloured ink (stamps, highlighter, a blue signature) becomes white,
  so that it hides no print;
- **remove lines**: long ruled and table lines become white;
- **black and white**: an adaptive threshold, never in letter mode.

Each page has its filters (:class:`Filters`), suggested by :func:`suggest` and kept in the
configuration document; the areas are looked for on the page as it is, in its colours.
Needs OpenCV and NumPy (the extra "ocr").
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import Any

import pymupdf

from ocrdoc.errors import OcrdocError

UPSCALE = (1, 2, 3, 4)


def available() -> bool:
    """True when OpenCV and NumPy are installed; they are not loaded for that."""
    return all(importlib.util.find_spec(name) is not None for name in ("cv2", "numpy"))


@dataclass
class Filters:
    """What a page's rendering goes through before OCR reads it (see the module)."""

    upscale: int = 1
    letter_mode: bool = False
    remove_colour: bool = False
    remove_lines: bool = False
    black_white: bool = False

    @property
    def active(self) -> bool:
        """True when the filters change the rendering."""
        return self != Filters()

    def as_dict(self) -> dict[str, Any]:
        """The filters for the configuration document."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, d: Any) -> Filters:
        """The filters from a configuration document; anything not of its kind is a
        "bad-config" (reason "field")."""
        if not isinstance(d, dict):
            raise OcrdocError("bad-config", reason="field")
        out = cls()
        for name, value in d.items():
            if name not in cls.__dataclass_fields__:
                continue
            default = getattr(cls(), name)
            fits = (isinstance(value, bool) if isinstance(default, bool)
                    else isinstance(value, int) and not isinstance(value, bool))
            if not fits or (name == "upscale" and value not in UPSCALE):
                raise OcrdocError("bad-config", reason="field")
            setattr(out, name, value)
        return out


# -- what the page looks like -------------------------------------------------------------------
def grey(image: Any) -> Any:
    """The image in grey."""
    import cv2

    return image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _shrunk(image: Any, longest: int = 600) -> Any:
    import cv2

    h, w = image.shape[:2]
    f = min(1.0, longest / max(h, w))
    return cv2.resize(image, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA) \
        if f < 1.0 else image


def render(page: pymupdf.Page, dpi: int = 150, max_pixel: int = 4000) -> tuple[Any, float]:
    """The page as a BGR NumPy image and its pixels per point."""
    import numpy as np

    scale = dpi / 72.0
    longest = max(page.rect.width, page.rect.height) * scale
    if longest > max_pixel:
        scale *= max_pixel / longest
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False,
                          colorspace=pymupdf.csRGB)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return image[:, :, ::-1].copy(), scale


def colour_share(image: Any) -> float:
    """Share of clearly coloured pixels (stamps, highlighter, coloured print)."""
    import cv2
    import numpy as np

    if image.ndim != 3:
        return 0.0
    hsv = cv2.cvtColor(_shrunk(image), cv2.COLOR_BGR2HSV)
    return float(np.mean((hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 60)))


def native_dpi(page: pymupdf.Page) -> float | None:
    """Resolution of the largest image on the page, or None without images."""
    best: float | None = None
    for info in page.get_image_info():
        bbox = pymupdf.Rect(info["bbox"]) & page.rect
        if bbox.width < 20 or bbox.height < 20:
            continue
        dpi = info["width"] / (bbox.width / 72.0)
        if best is None or dpi > best:
            best = dpi
    return best


def suggest(page: pymupdf.Page) -> Filters:
    """ocrdoc's suggestion for a page OCR reads: upscaled where its picture is below 150
    dpi, coloured ink taken away where more than 0.3 % of it is coloured."""
    out = Filters()
    resolution = native_dpi(page)
    out.upscale = 2 if resolution is not None and resolution < 150 else 1
    if available():
        image, _scale = render(page, 72)
        out.remove_colour = colour_share(image) > 0.003
    return out


# -- the filters --------------------------------------------------------------------------------
def _sharpen(image: Any, amount: float = 0.6) -> Any:
    import cv2

    blurred = cv2.GaussianBlur(image, (0, 0), 1.0)
    return cv2.addWeighted(image, 1.0 + amount, blurred, -amount, 0)


def letter_finish(image: Any, factor: int = 2) -> Any:
    """Letter-aware finish for an upscaled (or large) rendering: grey, strokes sharpened."""
    return _sharpen(grey(image))


def remove_colour(image: Any) -> Any:
    """Coloured ink (stamps, highlighter, signatures in blue) becomes white; black and
    grey print stays.  Returns a grey image."""
    import cv2
    import numpy as np

    if image.ndim != 3:
        return image
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    coloured = (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 60)
    coloured = cv2.dilate(coloured.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1) > 0
    out = grey(image)
    out[coloured] = 255
    return out


def remove_lines(image: Any) -> Any:
    """Long horizontal and vertical lines (forms, tables, underlines) become white;
    letters are far shorter than the kernels and survive."""
    import cv2
    import numpy as np

    g = grey(image)
    h, w = g.shape
    _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    horizontal = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(30, w // 25), 1)))
    vertical = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(30, h // 25))))
    rules = cv2.dilate(cv2.bitwise_or(horizontal, vertical), np.ones((3, 3), np.uint8))
    out = image.copy()
    out[rules > 0] = (255, 255, 255) if out.ndim == 3 else 255
    return out


def grid_areas(image: Any) -> list[tuple[int, int, int, int]]:
    """Pixel boxes of table grids: connected long horizontal and vertical rules that
    together span at least 15 % of the width and 2 % of the height.  Tesseract's page
    segmentation treats such a grid as graphics and drops the cells; the OCR reads the
    boxes again without their lines (:class:`~ocrdoc.ocr.TesseractBackend`)."""
    import cv2

    g = grey(image)
    h, w = g.shape
    _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    horizontal = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(20, w // 25), 1)))
    vertical = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(20, h // 40))))
    rules = cv2.dilate(cv2.bitwise_or(horizontal, vertical), cv2.getStructuringElement(
        cv2.MORPH_RECT, (5, 5)))
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(rules, connectivity=8)
    boxes: list[tuple[int, int, int, int]] = []
    for i in range(1, n):
        x, y, bb, bh, _area = (int(v) for v in stats[i])
        if bb < w * 0.15 or bh < h * 0.02:
            continue
        if not cv2.countNonZero(horizontal[y:y + bh, x:x + bb]) or \
                not cv2.countNonZero(vertical[y:y + bh, x:x + bb]):
            continue  # a lone rule or a bar, not a grid
        boxes.append((x, y, x + bb, y + bh))
    return boxes


def black_white(image: Any) -> Any:
    """Adaptive threshold to pure black and white."""
    import cv2

    return cv2.adaptiveThreshold(grey(image), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY, 31, 15)


def pipeline(f: Filters) -> Callable[[Any], Any] | None:
    """What the rendering of a page goes through before OCR, as one function of a NumPy
    image (the upscaling is the rendering's resolution, not a step here); None where
    nothing is to be done."""
    steps: list[Callable[[Any], Any]] = []
    if f.remove_colour:
        steps.append(remove_colour)
    if f.letter_mode:
        steps.append(letter_finish)
    if f.remove_lines:
        steps.append(remove_lines)
    if f.black_white and not f.letter_mode:  # measured: worse OCR in letter mode
        steps.append(black_white)
    if not steps:
        return None

    def run(image: Any) -> Any:
        for step in steps:
            image = step(image)
        return image

    return run
