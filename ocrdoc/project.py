"""A piece of recognition work on one PDF, and its configuration document.

ocrdoc reads a PDF whose pages are to stay as they are: a page optdoc prepared, a scan,
any PDF.  It divides each page into areas, reads its text (OCR where the page has no text
of its own), finds its tables, barcodes, stamps and handwriting, and lays the text
invisibly over the pages without touching their pictures.

Its configuration document (``<stem>.ocrdoc.json``, format ``ocrdoc-config``) holds
everything that decides the result and nothing else (no paths, no times): the settings,
per page the filters its rendering goes through before OCR (:mod:`ocrdoc.filters`), the
words OCR read, its areas and who set them, and the text a person corrected.  It serves
three ends:

- **Reproducing.**  The input and the document always give the same result, byte for
  byte: OCR and the finders do not run again where their results are stored.
- **Resuming.**  The window (``ocrdoc edit``) saves the document and opens it again where
  the person stopped; the PDF ocrdoc writes carries it too (``ocrdoc.json``).
- **Going on after an earlier step changed.**  The document names its input by its
  SHA-256 and every page's frame (where optdoc prepared the input, a fingerprint of where
  things lie on the page).  When the input changed but a page's frame did not (more
  contrast in optdoc), what a person decided on that page stays (areas, a table's grid,
  corrected text) and what a machine found is found again; where the frame changed, the
  page's decisions go and :attr:`Project.dropped` says so.  An input without frames must
  be the very same file ("config-mismatch" otherwise).
"""

from __future__ import annotations

import contextlib
import gc
import json
import shutil
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf
from doccor import documents
from doccor.errors import DocError

from ocrdoc import __version__, areas, layout, loading, tables, textlayer
from ocrdoc import filters as filtering
from ocrdoc import ocr as ocrlib
from ocrdoc.alignment import align_correction
from ocrdoc.errors import OcrdocError
from ocrdoc.filters import Filters
from ocrdoc.pagetext import PageText, read_text_layer
from ocrdoc.reading import MAX_PIXELS_UPSCALED, PageReading, Progress, Reading
from ocrdoc.structure import analyse_page_structure
from ocrdoc.tables import Table

FORMAT = "ocrdoc-config"
FORMAT_VERSION = 1
SUFFIX = ".ocrdoc.json"
EMBEDDED = "ocrdoc.json"  # the name of the configuration document inside the PDF
UPSTREAM = "optdoc.json"  # optdoc's, inside a page it prepared: it holds the frames


@dataclass
class Options:
    """The settings that decide the result: OCR engine and its language packs,
    Tesseract's second pass for table grids, the structure of OCR text, the resolution
    pages are read at, and whether tables (``cells``) and barcodes, stamps, pictures and
    handwriting (``areas``) are found automatically; a person can set every area all the
    same."""

    reader: str = "auto"
    languages: str | None = None
    tables: bool = True
    structure: bool = True
    dpi: int = ocrlib.OCR_DPI
    cells: bool = True
    areas: bool = True

    def as_dict(self) -> dict[str, Any]:
        """The settings for the configuration document."""
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: Any) -> Options:
        """The settings from a configuration document; a value of the wrong kind is a
        "bad-config"."""
        if not isinstance(d, dict):
            raise OcrdocError("bad-config", reason="field")
        options = cls()
        kinds: dict[str, tuple[type, ...]] = {
            "reader": (str,), "languages": (str, type(None)), "tables": (bool,),
            "structure": (bool,), "dpi": (int,), "cells": (bool,), "areas": (bool,)}
        for name, value in d.items():
            if name not in kinds:
                continue
            bad = not isinstance(value, kinds[name])
            if name == "dpi" and isinstance(value, int):
                bad = bad or isinstance(value, bool) or not 72 <= value <= 1200
            if bad:
                raise OcrdocError("bad-config", reason="field")
            setattr(options, name, value)
        return options


@dataclass
class _Page:
    """The state of one page: its filters once decided, what OCR read (None: not read
    yet; ``ocr`` False: the page has a text layer and needs none), its regions (None: not
    found yet) and whether a person set them, and the person's correction."""

    filters: Filters | None = None  # decided; None: the suggestion
    filters_by_person: bool = False
    ocr: bool | None = None
    words: list[ocrlib.OCRWord] | None = None
    correction: str | None = None
    regions: list[layout.Region] | None = None
    regions_by_person: bool = False
    suggestion: Filters | None = field(default=None, repr=False)


def _rounded(w: ocrlib.OCRWord) -> ocrlib.OCRWord:
    """A word as the configuration keeps it: boxes to a thousandth of a point, the
    confidence to four places; the result is made from these, live or reproduced."""
    return ocrlib.OCRWord(w.text, round(w.x0, 3), round(w.y0, 3), round(w.x1, 3),
                          round(w.y1, 3), round(w.confidence, 4))


def _word_from(row: Any) -> ocrlib.OCRWord:
    """A stored word ``[text, x0, y0, x1, y1, confidence]``."""
    if not (isinstance(row, list) and len(row) == 6 and isinstance(row[0], str)
            and all(isinstance(v, int | float) and not isinstance(v, bool) for v in row[1:])):
        raise OcrdocError("bad-config", reason="field")
    return ocrlib.OCRWord(row[0], *(float(v) for v in row[1:]))


def load_config(path: str | Path) -> dict[str, Any]:
    """A configuration document from its file, or from the PDF ocrdoc wrote, which
    carries it.  Raises "missing", or "bad-config" (reason "json" or "format")."""
    try:
        return documents.load_document(path, FORMAT, FORMAT_VERSION, EMBEDDED, "ocrdoc")
    except DocError as e:  # ocrdoc's own, so that callers catch one kind of error
        reason = e.details.get("reason")
        raise (OcrdocError(e.kind, reason=reason) if reason is not None
               else OcrdocError(e.kind)) from e


def config_bytes(config: dict[str, Any]) -> bytes:
    """A configuration document as ocrdoc writes it: JSON, the same bytes for the same
    content."""
    return documents.document_bytes(config)


def _frames(doc: pymupdf.Document, source: Path) -> list[str | None]:
    """The frame of every page, from the configuration document of the step that
    prepared the input: optdoc's, which a PDF carries inside and which lies beside a
    picture (``<stem>.optdoc.json``, where optdoc wrote both); None where there is none.
    The document beside a picture is taken at its word, as the one inside a PDF is."""
    frames: list[str | None] = [None] * len(doc)
    try:
        if loading.is_picture(source):
            beside = source.with_name(f"{source.stem}.{UPSTREAM}")
            if not beside.is_file():
                return frames
            upstream = json.loads(beside.read_text(encoding="utf-8"))
            if not isinstance(upstream, dict) or upstream.get("format") != "optdoc-config":
                return frames
        elif UPSTREAM not in doc.embfile_names():
            return frames
        else:
            upstream = json.loads(doc.embfile_get(UPSTREAM).decode("utf-8"))
        for k, page in enumerate(upstream.get("pages", [])[:len(doc)]):
            frame = page.get("frame") if isinstance(page, dict) else None
            frames[k] = frame if isinstance(frame, str) else None
    except Exception:  # an unreadable upstream document: no frames
        return [None] * len(doc)
    return frames


class Project:
    """The recognition work on one PDF; see the module.  Open with :meth:`open`, close
    with :meth:`close`.  Page numbers count from 0."""

    def __init__(self, source: Path, doc: pymupdf.Document, sha256: str, size: int,
                 options: Options) -> None:
        self.source = source
        self.picture = loading.is_picture(source)  # it stays one: the reading lies beside it
        self.pixels = loading.pixel_sizes(source) if self.picture else None
        self.doc = doc  # every page upright, as it came (a picture: looked at as pages)
        self.sha256 = sha256
        self.size = size
        self.options = options
        self.pages = [_Page() for _ in range(len(doc))]
        self.frames = _frames(doc, source)
        self.dropped: list[int] = []  # pages whose decisions went: their frame changed
        self.scratch: Path | None = None  # where a page may be written for a moment
        self.models: Path | None = None  # the folder of models the finders may use
        self._layer: dict[int, bool] = {}
        self._needs: dict[int, bool] = {}
        self._engine: ocrlib.OCRBackend | None = None
        self._engine_made = False
        self._stored_reader: str | None = None

    # -- opening and saving --------------------------------------------------------------------
    @classmethod
    def open(cls, source: str | Path, options: Options | None = None,
             config: dict[str, Any] | None = None) -> Project:
        """A project on ``source`` (a PDF, or a picture): fresh with ``options``, or as
        ``config`` left it (whose settings then count).  Raises "config-mismatch" when the
        document belongs to another file and no frame says the pages are the same, and
        what :func:`ocrdoc.loading.open_document` raises."""
        source = Path(source)
        doc = loading.open_document(source)
        sha256 = documents.digest(source)
        if config is not None:
            options = Options.from_dict(config.get("options", {}))
        project = cls(source, doc, sha256, source.stat().st_size, options or Options())
        if config is not None:
            try:
                project._take(config)
            except Exception:
                project.close()
                raise
        return project

    def _take(self, config: dict[str, Any]) -> None:
        """The pages of a configuration document: as they were where the input is the
        same file; where it is another, by the frames (see the module)."""
        named = config.get("input")
        if not isinstance(named, dict):
            raise OcrdocError("bad-config", reason="field")
        reader = config.get("reader")
        self._stored_reader = reader if isinstance(reader, str) else None
        pages = config.get("pages")
        if not isinstance(pages, list) or len(pages) != len(self.pages):
            raise OcrdocError("bad-config", reason="page")
        if named.get("sha256") == self.sha256:
            for page, entry in zip(self.pages, pages, strict=True):
                self._take_page(page, entry, everything=True)
            return
        stored = named.get("pages")
        if not isinstance(stored, list) or len(stored) != len(self.pages) \
                or not any(self.frames):
            raise OcrdocError("config-mismatch")
        self._stored_reader = None  # what is read again is read by the engine of now
        for n, (page, entry, then) in enumerate(zip(self.pages, pages, stored, strict=True)):
            same = isinstance(then, dict) and self.frames[n] is not None \
                and then.get("frame") == self.frames[n]
            if same:
                self._take_page(page, entry, everything=False)
            elif _has_decisions(entry):
                self.dropped.append(n)

    def _take_page(self, page: _Page, entry: Any, everything: bool) -> None:
        """One page of a configuration document: all of it (``everything``, the same
        input), or what a person decided (another input, the same frame)."""
        if not isinstance(entry, dict):
            raise OcrdocError("bad-config", reason="field")
        chosen = entry.get("filters")
        if chosen is not None:
            if not isinstance(chosen, dict) or chosen.get("by") not in layout.BY:
                raise OcrdocError("bad-config", reason="field")
            by_person = chosen["by"] == "person"
            if everything or by_person:
                page.filters = Filters.from_dict(chosen)
                page.filters_by_person = by_person
        correction = entry.get("correction")
        if correction is not None and not isinstance(correction, str):
            raise OcrdocError("bad-config", reason="field")
        page.correction = correction
        found = entry.get("layout")
        if found is not None:
            if not isinstance(found, dict) or found.get("by") not in layout.BY:
                raise OcrdocError("bad-config", reason="field")
            by_person = found["by"] == "person"
            if everything or by_person:
                page.regions = layout.regions_from_dicts(found.get("regions"))
                page.regions_by_person = by_person
        if not everything:
            return
        ocr = entry.get("ocr")
        if ocr is not None and not isinstance(ocr, bool):
            raise OcrdocError("bad-config", reason="field")
        page.ocr = ocr
        words = entry.get("words")
        page.words = None if words is None or not isinstance(words, list) else [
            _word_from(row) for row in words]
        if ocr and page.words is None:
            page.ocr = None  # to be read again

    def config(self) -> dict[str, Any]:
        """The configuration document: input, settings, and per page its filters (the
        suggestion where none was decided), what OCR read, its areas (None while not
        found) and the correction."""
        pages = []
        for n, page in enumerate(self.pages):
            chosen = self.filters(n)
            pages.append({
                "page": n + 1,
                "filters": None if chosen is None else {
                    **chosen.as_dict(), "by": "person" if page.filters_by_person else "auto"},
                "ocr": page.ocr,
                "words": None if page.words is None else [
                    [w.text, w.x0, w.y0, w.x1, w.y1, w.confidence] for w in page.words],
                "layout": None if page.regions is None else {
                    "by": "person" if page.regions_by_person else "auto",
                    "regions": [r.as_dict() for r in page.regions]},
                "correction": page.correction,
            })
        sizes = []
        for n in range(len(self.doc)):
            rect = self.doc[n].rect
            sizes.append({"width": round(rect.width, 3), "height": round(rect.height, 3),
                          "frame": self.frames[n]})
        return {
            "format": FORMAT, "version": FORMAT_VERSION, "made_with": f"ocrdoc {__version__}",
            "input": {"sha256": self.sha256, "bytes": self.size,
                      "suffix": self.source.suffix.lower(), "pages": sizes},
            "options": self.options.as_dict(),
            "reader": self.reader_name(),
            "pages": pages,
        }

    def save(self, path: str | Path) -> Path:
        """Write the configuration document to ``path``; raises "unwritable"."""
        path = Path(path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(config_bytes(self.config()))
        except OSError as e:
            raise OcrdocError("unwritable") from e
        return path

    def close(self) -> None:
        """Release the document."""
        self.doc.close()

    @contextlib.contextmanager
    def _working_folder(self) -> Iterator[Path]:
        """A folder for a moment's file (Camelot reads a PDF only from a path, and writes
        any other input to the temporary folder): inside the results folder (``scratch``)
        where the project has one, so that nothing of a document lands anywhere else; it
        is removed at once, and the results folder too when it was made for it and stays
        empty.  Without one (ocrdoc used as a library), a private temporary folder."""
        if self.scratch is None:
            with tempfile.TemporaryDirectory(prefix="ocrdoc-") as folder:
                yield Path(folder)
            return
        made = not self.scratch.exists()
        work = self.scratch / ".ocrdoc-work"
        try:
            work.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise OcrdocError("unwritable") from e
        try:
            yield work
        finally:
            gc.collect()  # Camelot holds the file open until its objects are collected
            shutil.rmtree(work, ignore_errors=True)
            if made:
                with contextlib.suppress(OSError):
                    self.scratch.rmdir()  # only when nothing else is in it

    # -- the pages -----------------------------------------------------------------------------
    def has_text_layer(self, n: int) -> bool:
        """True when the page carries text of its own (it is not read by OCR)."""
        if n not in self._layer:
            self._layer[n] = read_text_layer(self.doc[n], n).has_text_layer
        return self._layer[n]

    def needs_ocr(self, n: int) -> bool:
        """True when OCR reads the page: it has no text layer, or pictures cover a good
        part of it (a scanned letter in a PDF with a text layer)."""
        if n not in self._needs:
            self._needs[n] = ocrlib.needs_ocr(self.doc[n], read_text_layer(self.doc[n], n))
        return self._needs[n]

    def page_png(self, n: int, dpi: int = 100) -> bytes:
        """The page as it is, as PNG."""
        return self.doc[n].get_pixmap(dpi=dpi, alpha=False).tobytes("png")

    def suggestion(self, n: int) -> Filters:
        """ocrdoc's suggestion for the filters of a page (computed once)."""
        page = self.pages[n]
        if page.suggestion is None:
            page.suggestion = filtering.suggest(self.doc[n])
        return Filters(**page.suggestion.as_dict())

    def filters(self, n: int) -> Filters | None:
        """The filters of a page OCR reads, a copy: as decided, else the suggestion;
        None for a page OCR does not read (:meth:`needs_ocr`)."""
        if not self.needs_ocr(n):
            return None
        page = self.pages[n]
        if page.filters is not None:
            return Filters(**page.filters.as_dict())
        return self.suggestion(n)

    def preview(self, n: int, chosen: Filters, dpi: int = 100) -> bytes:
        """The page as OCR reads it through ``chosen``, as PNG: rendered at ``dpi`` times
        the upscaling (at most 3000 pixels on its longest side), then filtered.  Needs
        OpenCV (:func:`ocrdoc.filters.available`)."""
        import cv2

        factor = max(1, chosen.upscale)
        image, _scale = filtering.render(self.doc[n], dpi * factor, max_pixel=3000)
        run = filtering.pipeline(chosen)
        if run is not None:
            image = run(image)
        done, data = cv2.imencode(".png", image)
        if not done:
            raise OcrdocError("internal", error="imencode")
        return bytes(data.tobytes())

    def set_filters(self, n: int, chosen: Filters, by_person: bool = True) -> None:
        """Decide the filters of a page: a person's choice, or (``by_person`` False)
        ocrdoc's suggestion taken back.  When they change, what OCR read is dropped (the
        page is read again) and so are the areas found; a person's areas and correction
        stay."""
        page = self.pages[n]
        changed = chosen != self.filters(n)
        page.filters = Filters(**chosen.as_dict())
        page.filters_by_person = by_person
        if changed:
            page.words, page.ocr = None, None
            if not page.regions_by_person:
                page.regions = None

    # -- reading -------------------------------------------------------------------------------
    def engine(self) -> ocrlib.OCRBackend | None:
        """The OCR engine of the settings, started once; None for "none" (or no engine
        installed for "auto")."""
        if not self._engine_made:
            self._engine = ocrlib.backend(self.options.reader, self.options.languages,
                                          tables=self.options.tables)
            self._engine_made = True
        return self._engine

    def reader_name(self) -> str | None:
        """The engine that read the pages: as stored, else the engine of the settings
        once it has started."""
        if self._engine_made:
            return self._engine.name if self._engine is not None else None
        if self._stored_reader is not None:
            return self._stored_reader
        return self.options.reader if self.options.reader in ("rapidocr", "tesseract") \
            else None

    def needs_reading(self, n: int) -> bool:
        """True while the page has not been read since its filters last changed."""
        return self.pages[n].ocr is None

    def read(self, n: int) -> None:
        """Read a page: its text layer where that suffices, else OCR on the page's
        rendering through its filters (the words are kept).  Nothing happens to a page
        read already, nor to one OCR would read where there is no engine (it stays
        unread, for an engine installed later)."""
        page = self.pages[n]
        if page.ocr is not None:
            return
        if not self.needs_ocr(n):
            page.ocr, page.words = False, None
            return
        engine = self.engine()
        if engine is None:
            return
        chosen = self.filters(n) or Filters()
        factor = max(1, chosen.upscale)
        words = ocrlib.recognise_words(
            self.doc[n], engine, dpi=self.options.dpi * factor,
            max_pixel=min(ocrlib.MAX_PIXELS * factor, MAX_PIXELS_UPSCALED),
            filter_=filtering.pipeline(chosen) if filtering.available() else None)
        page.words = [_rounded(w) for w in words]
        page.ocr = True

    def read_all(self, progress: Progress | None = None) -> None:
        """Read every page not read yet."""
        for n in range(len(self.pages)):
            if progress is not None:
                progress(n + 1, len(self.pages))
            self.read(n)

    def ocr_text(self, n: int, every_word: bool = False) -> PageText | None:
        """What OCR read on the page, as a page text, without the words in regions that
        are not read (pictures, barcodes, "ignore"), unless ``every_word``; None for a
        page not read by OCR."""
        page = self.pages[n]
        if not page.ocr or page.words is None:
            return None
        words = page.words
        if not every_word and page.regions:
            words = [w for w in words
                     if layout.is_read(page.regions, (w.x0, w.y0, w.x1, w.y1))]
        rect = self.doc[n].rect
        return ocrlib.page_text_from_words(words, n, rect.width, rect.height)

    def text(self, n: int) -> str:
        """The text of a page as it will be: the correction, else what OCR read, else the
        text layer.  Reads the page first."""
        self.read(n)
        page = self.pages[n]
        if page.correction is not None:
            return page.correction
        ocr = self.ocr_text(n)
        return ocr.text if ocr is not None else read_text_layer(self.doc[n], n).text

    def set_correction(self, n: int, text: str) -> None:
        """Keep a person's correction of the OCR text of a page; the text as read (spacing
        at its end aside) takes it back.  Only for pages read by OCR."""
        self.read(n)
        ocr = self.ocr_text(n)
        if ocr is None:
            raise OcrdocError("not-ocr", page=n + 1)
        self.pages[n].correction = None if text.rstrip() == ocr.text.rstrip() else text

    # -- the regions ---------------------------------------------------------------------------
    def finds_tables(self) -> bool:
        """True when tables are found automatically (the setting, and Camelot there)."""
        return self.options.cells and tables.available()

    def regions(self, n: int) -> list[layout.Region]:
        """The regions of a page (copies): as a person set them, else as found (once; the
        page is read first)."""
        page = self.pages[n]
        if page.regions is None:
            page.regions = self.find_regions(n)
            page.regions_by_person = False
        return [layout.copy(r) for r in page.regions]

    def has_regions(self, n: int) -> bool:
        """True when the regions of the page are known (found or set): no work to wait for."""
        return self.pages[n].regions is not None

    def forget_regions(self, n: int) -> None:
        """Forget the regions of a page, a person's too: they are found again."""
        self.pages[n].regions, self.pages[n].regions_by_person = None, False

    def regions_by_person(self, n: int) -> bool:
        """True when a person set the regions of the page."""
        return self.pages[n].regions_by_person

    def set_regions(self, n: int, regions: list[layout.Region]) -> None:
        """A person's regions for a page; raises "bad-config" (reason "field") for a
        region that makes no sense."""
        if not all(r.valid() for r in regions):
            raise OcrdocError("bad-config", reason="field")
        page = self.pages[n]
        page.regions = [layout.rounded(r) for r in regions]
        page.regions_by_person = True

    def leave_out_found_tables(self) -> None:
        """Find no tables from now on, and forget those found (a person's stay)."""
        self.options.cells = False
        for page in self.pages:
            if not page.regions_by_person:
                page.regions = None

    def find_regions(self, n: int) -> list[layout.Region]:
        """The regions ocrdoc finds on a page (read first), in reading order (top to
        bottom, then left to right): its tables with their grids (:meth:`find_tables`),
        and its barcodes, stamps, pictures and handwriting (:mod:`ocrdoc.areas`), as the
        settings ask for them."""
        self.read(n)
        found = self.find_tables(n)
        if self.options.areas and filtering.available():
            found += self._find_marks(n, [r.box for r in found])
        return sorted(found, key=lambda r: (round(r.box[1]), r.box[0]))

    def _find_marks(self, n: int, taken: list[layout.Box]) -> list[layout.Region]:
        """Barcodes, stamps, pictures and handwriting on the page as it is, in its own
        colours, outside ``taken``."""
        image, scale = filtering.render(self.doc[n], self.options.dpi)
        codes = [layout.rounded(r) for r in areas.find_barcodes(image, scale)]
        words = self._area_words(n)
        marks = areas.find_marks(image, scale, words, [*taken, *(c.box for c in codes)])
        return codes + [layout.rounded(r) for r in marks]

    def _area_words(self, n: int) -> list[areas.Word] | None:
        """The words read on a page, every one (with their confidence), for the finders;
        None where nothing was read."""
        page = self.pages[n]
        if page.ocr and page.words is not None:
            return [areas.Word(w.text, (w.x0, w.y0, w.x1, w.y1), w.confidence)
                    for w in page.words]
        text = read_text_layer(self.doc[n], n)
        return [areas.Word(t, box) for t, box in _words_of(text)] or None

    def find_tables(self, n: int) -> list[layout.Region]:
        """The tables of a page with their grids: Camelot on the page with its text, as
        the PDF will carry it; none where tables are not found automatically or finding
        them failed."""
        if not self.finds_tables():
            return []
        single = pymupdf.open()
        try:
            single.insert_pdf(self.doc, from_page=n, to_page=n)
            text = self.ocr_text(n, every_word=True)
            if text is not None:
                textlayer.write_page(single, single[0], text, textlayer.add_font(single))
            with self._working_folder() as folder:
                page = folder / "page.pdf"
                single.save(page)
                found = tables.find_tables(page)
        except OcrdocError:
            raise
        except Exception:  # Camelot's own failure on an unusual page: no regions
            return []
        finally:
            single.close()
        return [layout.rounded(layout.from_table(t)) for t in found.get(0, [])]

    # -- the result ----------------------------------------------------------------------------
    def build(self, progress: Progress | None = None) -> Reading:
        """The result: every page read (where not yet) and its regions found (where not
        yet), its text corrected where a person did; the pages themselves as they came.
        The reading carries the configuration document.  The caller closes it."""
        self.read_all(progress)
        for n in range(len(self.pages)):
            self.regions(n)  # found where not yet, so that the configuration holds them
        doc = pymupdf.open("pdf", self.doc.tobytes())
        pages = [self._page_reading(doc, n) for n in range(len(self.pages))]
        found: dict[int, list[Table]] | None = {s.number: s.tables for s in pages}
        if not self.finds_tables() and not any(s.tables for s in pages):
            found = None  # not looked for
        return Reading(self.source, doc, pages, self.reader_name(), tables=found,
                       config=self.config(), carried=carried(doc), pixels=self.pixels)

    def _page_reading(self, doc: pymupdf.Document, n: int) -> PageReading:
        """One page of the result: its text, and the tables of its table regions made
        from the words of that text (corrected where a person did)."""
        regions = self.regions(n)
        ocr = self.ocr_text(n)
        if ocr is None:
            text = read_text_layer(doc[n], n)
            return PageReading(n, text, False, regions=regions,
                               tables=_tables(regions, text))
        correction = self.pages[n].correction
        text, person = (ocr, [False] * len(ocr.words())) if correction is None \
            else align_correction(correction, ocr)
        found = _tables(regions, text)
        structure = None
        if self.options.structure:
            structure = analyse_page_structure(doc[n], ocr)
            structure.use_tables(ocr, [(r.box, [[c.text for c in row] for row in t.rows])
                                       for r, t in zip([r for r in regions if r.kind == "table"],
                                                       found, strict=True)])
        return PageReading(n, text, True, structure, person, regions=regions, tables=found)

    @property
    def corrected(self) -> list[int]:
        """The pages a person corrected (from 0)."""
        return [n for n, p in enumerate(self.pages) if p.correction is not None]


def carried(doc: pymupdf.Document) -> dict[str, bytes]:
    """The configuration documents of the steps before that a PDF carries (embedded JSON
    files other than ocrdoc's own), by name."""
    found: dict[str, bytes] = {}
    for name in sorted(doc.embfile_names()):
        if name.endswith(".json") and name != EMBEDDED:
            found[name] = doc.embfile_get(name)
    return found


def _has_decisions(entry: Any) -> bool:
    """True when a stored page holds something a person decided."""
    if not isinstance(entry, dict):
        return False
    found, chosen = entry.get("layout"), entry.get("filters")
    return entry.get("correction") is not None or any(
        isinstance(d, dict) and d.get("by") == "person" for d in (found, chosen))


def _words_of(text: PageText) -> list[layout.Word]:
    """The words of a page text with their boxes (the union of their characters')."""
    words: list[layout.Word] = []
    for a, b in text.words():
        boxes = text.rects(a, b)
        if boxes:
            box = boxes[0]
            for r in boxes[1:]:
                box |= r
            words.append((text.text[a:b], (box.x0, box.y0, box.x1, box.y1)))
    return words


def _tables(regions: list[layout.Region], text: PageText) -> list[Table]:
    """The tables the table regions of a page make of its text, in their order."""
    words = _words_of(text)
    return [layout.table_of(r, words) for r in regions if r.kind == "table"]


__all__ = ["EMBEDDED", "FORMAT", "FORMAT_VERSION", "SUFFIX", "Options", "Project",
           "carried", "config_bytes", "load_config"]
