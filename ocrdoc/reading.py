"""What a reading is, and :func:`read`, the short way to one.

ocrdoc reads a PDF and leaves its pages as they are.  A page with a text layer of its own
is read as it is; a page without one (a scan, a photo, a page optdoc prepared) is read
by OCR, on ocrdoc's own rendering of it through the page's filters
(:mod:`ocrdoc.filters`).  The work itself is :class:`ocrdoc.project.Project`'s;
:func:`read` opens one and builds its result.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

from ocrdoc import ocr as ocrlib
from ocrdoc.layout import Region
from ocrdoc.pagetext import PageText
from ocrdoc.structure import Structure
from ocrdoc.tables import Table

MAX_PIXELS_UPSCALED = 9000  # cap for the OCR image of an upscaled page


Progress = Callable[[int, int], None]  # page (from 1) about to be done, and how many


@dataclass
class PageReading:
    """One page as read: its text (with a box for every character), whether that text
    came from OCR, the structure of an OCR text, on an OCR page for every word whether
    a person wrote it (corrected the OCR) rather than the engine, its regions
    (:mod:`ocrdoc.layout`) and the tables its table regions make."""

    number: int
    text: PageText
    ocr: bool
    structure: Structure | None = None
    person: list[bool] | None = None
    regions: list[Region] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)

    @property
    def markdown(self) -> str:
        """The page text as Markdown where it has a structure, else as it is."""
        return self.structure.render(self.text.text) if self.structure else self.text.text


@dataclass
class Reading:
    """A read document: the input's pages as they came, the pages as read, the OCR
    engine used (None without one), the tables of its pages by page number (None when
    they were not looked for), the configuration that makes it again
    (:mod:`ocrdoc.project`), and the configuration documents of the steps before, which
    the input carried (by their names in it, ``optdoc.json``).  For a picture, which
    stays a picture, ``pixels`` holds the size of every picture in the file (upright, in
    its own pixels): the reading gives its boxes in those.  Call :meth:`close` when
    done."""

    source: Path
    doc: pymupdf.Document
    pages: list[PageReading] = field(default_factory=list)
    reader: str | None = None
    tables: dict[int, list[Table]] | None = None
    config: dict[str, Any] | None = None
    carried: dict[str, bytes] = field(default_factory=dict)
    pixels: list[tuple[int, int]] | None = None

    @property
    def without_text(self) -> list[int]:
        """Pages that hold no text at all after reading (no text layer and no OCR)."""
        return [s.number for s in self.pages if not s.text.text.strip()]

    def close(self) -> None:
        """Close the document."""
        self.doc.close()


def read(
    path: str | Path,
    reader: str = "auto",
    languages: str | None = None,
    tables: bool = True,
    dpi: int = ocrlib.OCR_DPI,
    with_structure: bool = True,
    progress: Progress | None = None,
    cells: bool = True,
    areas: bool = True,
    scratch: Path | None = None,
    config: dict[str, Any] | None = None,
) -> Reading:
    """Read a PDF.

    ``reader`` is the OCR engine ("auto", "rapidocr", "tesseract", "none"), ``languages``
    its language packs, ``tables`` Tesseract's second pass for table grids, ``dpi`` the
    resolution pages are read at; every page gets the filters ocrdoc suggests for it.
    ``with_structure`` gives OCR pages their structure.  ``progress`` is called with the
    number of the page about to be done (from 1) and the number of pages.  ``cells``
    finds the tables with their cells (the extra "tables"), ``areas`` the barcodes,
    stamps, pictures and handwriting; ``scratch`` is a folder where a page may be written
    for a moment for the tables (a hidden folder in it is removed at once), else a
    private temporary folder.  With ``config`` (a configuration document) the work is
    done as it says, and the other settings do not count.

    Raises :class:`~ocrdoc.errors.OcrdocError` (an :class:`~ocrdoc.errors.OCRError` for
    the engines)."""
    from ocrdoc.project import Options, Project

    options = Options(reader=reader, languages=languages, tables=tables,
                      structure=with_structure, dpi=dpi, cells=cells, areas=areas)
    project = Project.open(path, options, config)
    project.scratch = scratch
    try:
        reading = project.build(progress)
    finally:
        project.close()
    return reading
