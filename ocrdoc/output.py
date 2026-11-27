"""What a reading leaves behind: a searchable PDF, the reading as JSON, the text as
Markdown, and the configuration that makes it again (:mod:`ocrdoc.project`).

The PDF is the input with its pages as they came; the OCR text is laid invisibly over
the place where it is printed, line by line (:mod:`ocrdoc.textlayer`), so that a reader
can search and select the text of a scan like that of a born-digital document, and a
program that takes the text out gets a printed row as one line.  The JSON names every
word with its box in page points and the engine's confidence; it is meant for programs
in other languages (a records app, a laboratory reader) and says which version of
ocrdoc and which engine made it.

The same input and configuration always give the same bytes: the PDF carries no time
and a file identifier made from the configuration documents of every step that made it.
It carries them too, as embedded files without dates: those of the steps before as the
input had them (``optdoc.json``), and ocrdoc's own (``ocrdoc.json``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf
from doccor import documents

from ocrdoc import __version__, textlayer
from ocrdoc.errors import OcrdocError
from ocrdoc.pagetext import PageText
from ocrdoc.project import EMBEDDED, SUFFIX, config_bytes
from ocrdoc.reading import PageReading, Reading
from ocrdoc.tables import Table

FORMAT = "ocrdoc-reading"
FORMAT_VERSION = 1


def _word_box(page_text: PageText, a: int, b: int) -> pymupdf.Rect | None:
    """The union of the boxes of ``page_text.text[a:b]``, or None without boxes."""
    boxes_found = page_text.rects(a, b)
    if not boxes_found:
        return None
    word = pymupdf.Rect(boxes_found[0])
    for r in boxes_found[1:]:
        word |= r
    return word


def _words(page_text: PageText, person: list[bool] | None = None) -> list[dict[str, Any]]:
    """The words of a page with their boxes and, for OCR, the engine's confidence and
    who wrote the word: "ocr", or "person" where someone corrected it (``person``)."""
    words_of_page = page_text.words()
    confidences = (page_text.confidences
                   if len(page_text.confidences) == len(words_of_page) else [])
    words = []
    for i, (a, b) in enumerate(words_of_page):
        bounds = _word_box(page_text, a, b)
        word: dict[str, Any] = {"text": page_text.text[a:b], "start": a, "end": b,
                                "box": ([round(v, 2) for v in (bounds.x0, bounds.y0, bounds.x1,
                                                               bounds.y1)]
                                        if bounds else None)}
        if confidences:
            word["confidence"] = round(confidences[i], 3)
        if person is not None and len(person) == len(words_of_page):
            word["by"] = "person" if person[i] else "ocr"
        words.append(word)
    return words


def _regions(s: PageReading) -> list[dict[str, Any]]:
    """The regions of a page for the reading, in reading order: kind, box, who set it,
    and for a table the number of its table in the page's ``tables``."""
    regions, table = [], 0
    for r in s.regions:
        d: dict[str, Any] = {"kind": r.kind, "box": [round(v, 2) for v in r.box], "by": r.by}
        if r.kind == "table":
            d["table"] = table
            table += 1
        if r.kind == "barcode" and r.format is not None:
            d["format"], d["content"] = r.format, r.content
        regions.append(d)
    return regions


def _page_as_dict(s: PageReading, tables: list[Table] | None) -> dict[str, Any]:
    """One page of the reading; ``tables`` None when they were not looked for."""
    return {
        "page": s.number + 1,
        "width": round(s.text.width, 2),
        "height": round(s.text.height, 2),
        "source": "ocr" if s.ocr else "text",
        "text": s.text.text,
        "markdown": s.markdown,
        "words": _words(s.text, s.person),
        "regions": _regions(s),
        "tables": [t.as_dict() for t in tables] if tables is not None else None,
    }


def reading_as_dict(reading: Reading) -> dict[str, Any]:
    """The reading as a JSON-ready dictionary."""
    named = (reading.config or {}).get("input", {})
    return {
        "format": FORMAT,
        "version": FORMAT_VERSION,
        "made_with": f"ocrdoc {__version__}",
        "reader": reading.reader,
        "input": {"sha256": named.get("sha256")},
        "pages": [_page_as_dict(s, None if reading.tables is None
                                else reading.tables.get(s.number, []))
                  for s in reading.pages],
    }


def markdown(reading: Reading) -> str:
    """The text of all pages as Markdown, a heading per page."""
    parts = [f"## Page {s.number + 1}\n\n{s.markdown.strip()}\n" for s in reading.pages]
    return "\n".join(parts)


def searchable_pdf(reading: Reading) -> bytes:
    """The input with an invisible text layer on every OCR page, carrying the
    configuration documents of the steps before and ocrdoc's own; its file identifier is
    made from them, so that the same input and configuration give the same bytes."""
    duplicate = pymupdf.open("pdf", reading.doc.tobytes())
    try:
        font = None
        for s in reading.pages:
            if s.ocr:
                font = font or textlayer.add_font(duplicate)
                textlayer.write_page(duplicate, duplicate[s.number], s.text, font)
        if EMBEDDED in duplicate.embfile_names():
            duplicate.embfile_del(EMBEDDED)  # an input ocrdoc wrote before: its own goes
        config = config_bytes(reading.config) if reading.config is not None else b""
        if config:
            documents.embed(duplicate, EMBEDDED, config,
                            "ocrdoc configuration: reads the input of this step again")
        chain = [reading.carried[name] for name in sorted(reading.carried)] + [config]
        return documents.finished_pdf(duplicate, chain, f"ocrdoc {__version__}")
    finally:
        duplicate.close()


def write(reading: Reading, folder: str | Path, stem: str | None = None) -> dict[str, Path]:
    """Write ``<stem>.pdf``, ``<stem>.reading.json``, ``<stem>.md`` and the
    configuration ``<stem>.ocrdoc.json`` (where the reading has one) into ``folder``
    (created when missing); returns the paths by kind ("document": the PDF with its text
    layer; "reading", "markdown", "config").  Nothing is written anywhere else.  Raises
    :class:`~ocrdoc.errors.OcrdocError`: "same-as-source" when the PDF would replace the
    document that was read, "unwritable" when the folder cannot take the files."""
    target = Path(folder)
    stem = stem or reading.source.stem
    paths = {
        "document": target / f"{stem}.pdf",
        "reading": target / f"{stem}.reading.json",
        "markdown": target / f"{stem}.md",
        "config": target / f"{stem}{SUFFIX}",
    }
    if paths["document"].resolve() == reading.source.resolve():
        raise OcrdocError("same-as-source")
    pdf = searchable_pdf(reading)
    try:
        target.mkdir(parents=True, exist_ok=True)
        paths["document"].write_bytes(pdf)
    except OSError as e:
        raise OcrdocError("unwritable") from e
    contents = {
        "reading": json.dumps(reading_as_dict(reading), ensure_ascii=False,
                              indent=1).encode("utf-8"),
        "markdown": markdown(reading).encode("utf-8"),
    }
    if reading.config is not None:
        contents["config"] = config_bytes(reading.config)
    else:
        del paths["config"]
    try:
        for key, data in contents.items():
            paths[key].write_bytes(data)
    except OSError as e:
        raise OcrdocError("unwritable") from e
    return paths
