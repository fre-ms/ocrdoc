"""The results of a reading: searchable PDF, reading as JSON, Markdown, configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest

from ocrdoc import ocr as ocrlib
from ocrdoc import output
from ocrdoc.errors import OcrdocError
from ocrdoc.reading import read
from tests.synthetic import scan

needs_backend = pytest.mark.skipif(not ocrlib.available_backends(),
                                     reason="kein OCR-Backend installiert")


@needs_backend
def test_scan_becomes_searchable(tmp_path: Path, report: Path) -> None:
    """The scan comes back with an invisible text layer on the printed words, the
    reading names every word with its box and who wrote it, the configuration carries the
    filters OCR read the page through."""
    source = scan(report, tmp_path / "scan.pdf")
    reading = read(source)
    try:
        paths = output.write(reading, tmp_path / "out")
        ocr_page_text = reading.pages[0].text
    finally:
        reading.close()
    with pymupdf.open(paths["pdf"]) as d:
        assert "Ramipril" in d[0].get_text() and "Kontrolle" in d[1].get_text()
        found = d[0].search_for("Diagnosen")
        assert d.metadata["producer"].startswith("ocrdoc ")
    a = ocr_page_text.text.index("Diagnosen")
    bounds = ocr_page_text.rects(a, a + len("Diagnosen"))[0]
    assert any(abs(r.x0 - bounds.x0) < 3 and r.y0 < bounds.y1 and r.y1 > bounds.y0
               for r in found), (found, bounds)
    reading_json = json.loads(paths["reading"].read_text(encoding="utf-8"))
    assert reading_json["format"] == "ocrdoc-reading" and reading_json["version"] == 1
    json_page = reading_json["pages"][0]
    assert json_page["source"] == "ocr" and json_page["page"] == 1
    word = next(w for w in json_page["words"] if w["text"] == "Diagnosen:")
    assert len(word["box"]) == 4 and 0 < word["confidence"] <= 1
    assert json_page["text"][word["start"]:word["end"]] == "Diagnosen:"
    assert "## Page 2" in paths["markdown"].read_text(encoding="utf-8")
    config = json.loads(paths["config"].read_text(encoding="utf-8"))
    assert config["pages"][0]["filters"] == {"by": "auto", "upscale": 1, "letter_mode": False,
                                             "remove_colour": False, "remove_lines": False,
                                             "black_white": False}
    assert word["by"] == "ocr"


def test_text_layer_stays_as_it_is(tmp_path: Path, report: Path) -> None:
    reading = read(report)
    try:
        paths = output.write(reading, tmp_path / "out")
    finally:
        reading.close()
    data = json.loads(paths["reading"].read_text(encoding="utf-8"))
    assert [s["source"] for s in data["pages"]] == ["text", "text"]
    assert all("confidence" not in w for w in data["pages"][0]["words"])
    with pymupdf.open(paths["pdf"]) as d:
        assert d[0].get_text().count("Ramipril") == 1  # nothing laid over a text layer


def test_source_is_never_overwritten(tmp_path: Path, report: Path) -> None:
    reading = read(report)
    try:
        with pytest.raises(OcrdocError, match="overwrite"):
            output.write(reading, report.parent)
    finally:
        reading.close()
