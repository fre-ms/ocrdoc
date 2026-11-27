"""The project and its configuration document: the same input and document give the same
result byte for byte; work is resumed where it stopped; a correction reaches the text
layer and is marked as a person's; when the input changed but a page's frame did not,
the person's decisions stay; a document of another file, or a broken one, is refused."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest
from doccor import documents

from ocrdoc import layout, output
from ocrdoc import ocr as ocrlib
from ocrdoc.errors import OcrdocError
from ocrdoc.filters import Filters
from ocrdoc.project import EMBEDDED, SUFFIX, Options, Project, load_config
from tests.synthetic import scan

needs_backend = pytest.mark.skipif(not ocrlib.available_backends(),
                                   reason="no OCR engine installed")
FILES = ("document", "reading", "markdown", "config")


def _write(project: Project, folder: Path) -> dict[str, bytes]:
    """The result of a project, written, as bytes per file."""
    reading = project.build()
    try:
        paths = output.write(reading, folder)
    finally:
        reading.close()
    return {k: paths[k].read_bytes() for k in FILES}


def _prepared(source: Path, target: Path, frames: list[str]) -> Path:
    """``source`` as optdoc would hand it on: carrying a configuration document of its
    own whose pages have the ``frames`` given."""
    upstream = {"format": "optdoc-config", "version": 2,
                "pages": [{"page": n + 1, "frame": f} for n, f in enumerate(frames)]}
    with pymupdf.open(source) as doc:
        documents.embed(doc, "optdoc.json", documents.document_bytes(upstream), "optdoc")
        doc.save(target)
    return target


@needs_backend
def test_same_input_and_document_same_result(tmp_path: Path, report: Path,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """A scan read once, then read again from its configuration document and from the PDF
    that carries it: every file the same, byte for byte, and OCR does not run again."""
    source = scan(report, tmp_path / "scan.pdf")
    project = Project.open(source)
    try:
        first = _write(project, tmp_path / "a")
    finally:
        project.close()
    config = json.loads(first["config"])
    assert config["format"] == "ocrdoc-config" and config["pages"][0]["ocr"] is True
    assert config["pages"][0]["words"] and config["pages"][0]["filters"] is not None
    assert config["pages"][0]["layout"] is not None

    def refuse(*_args: object, **_kwargs: object) -> list[ocrlib.OCRWord]:
        raise AssertionError("OCR must not run when the words are stored")

    monkeypatch.setattr(ocrlib, "recognise_words", refuse)
    for given in (tmp_path / "a" / f"scan{SUFFIX}", tmp_path / "a" / "scan.pdf"):
        again = Project.open(source, config=load_config(given))
        try:
            assert _write(again, tmp_path / given.suffix.strip(".")) == first
        finally:
            again.close()


@needs_backend
def test_the_pages_stay_and_the_chain_is_carried(tmp_path: Path, report: Path) -> None:
    """ocrdoc's PDF has the input's pages as they came, with a text layer over them, and
    carries the documents of the step before as well as its own."""
    source = _prepared(scan(report, tmp_path / "scan.pdf"), tmp_path / "prepared.pdf",
                       ["a", "b"])
    project = Project.open(source)
    try:
        assert project.frames == ["a", "b"]
        reading = project.build()
        try:
            assert sorted(reading.carried) == ["optdoc.json"]
            paths = output.write(reading, tmp_path / "out")
        finally:
            reading.close()
    finally:
        project.close()
    with pymupdf.open(source) as before, pymupdf.open(paths["document"]) as after:
        assert sorted(after.embfile_names()) == ["ocrdoc.json", "optdoc.json"]
        assert after.embfile_get("optdoc.json") == before.embfile_get("optdoc.json")
        for n in range(len(before)):
            assert [i[2:4] for i in after[n].get_images()] == \
                [i[2:4] for i in before[n].get_images()]
        assert "Ramipril" in after[0].get_text() and not before[0].get_text().strip()
    answer = json.loads(paths["reading"].read_text(encoding="utf-8"))
    assert answer["format"] == "ocrdoc-reading" and "source" not in answer
    assert answer["input"]["sha256"] == documents.digest(source)


@needs_backend
def test_resume_and_correct(tmp_path: Path, report: Path) -> None:
    """Work saved half-way comes back as it was: filters chosen by hand, a correction.
    The correction is in the text layer and in the reading, marked as a person's."""
    source = scan(report, tmp_path / "scan.pdf")
    project = Project.open(source)
    try:
        project.set_filters(0, Filters(upscale=2, letter_mode=True))
        text = project.text(0)
        assert "Ramipril" in text
        project.set_correction(0, text.replace("Ramipril", "Ramiprill"))
        saved = project.save(tmp_path / f"scan{SUFFIX}")
        assert project.pages[1].words is None  # page 2 not read yet
    finally:
        project.close()
    again = Project.open(source, config=load_config(saved))
    try:
        assert again.filters(0) == Filters(upscale=2, letter_mode=True)
        assert again.pages[0].correction is not None and "Ramiprill" in again.text(0)
        assert again.corrected == [0] and again.needs_reading(1)
        reading = again.build()
        try:
            paths = output.write(reading, tmp_path / "out")
        finally:
            reading.close()
    finally:
        again.close()
    with pymupdf.open(paths["document"]) as doc:
        assert "Ramiprill" in doc[0].get_text() and doc[0].search_for("Ramiprill")
    words = json.loads(paths["reading"].read_text(encoding="utf-8"))["pages"][0]["words"]
    by = {w["text"].strip(","): w["by"] for w in words}
    assert by["Ramiprill"] == "person" and by["Diagnosen:"] == "ocr"


@needs_backend
def test_new_filters_read_the_page_again(tmp_path: Path, report: Path) -> None:
    """Changing the filters drops what OCR read and the areas found; the correction and
    a person's areas stay; the same filters again change nothing."""
    source = scan(report, tmp_path / "scan.pdf")
    project = Project.open(source)
    try:
        project.set_correction(0, project.text(0) + "\nNachtrag")
        project.set_regions(1, [layout.Region("ignore", (50.0, 50.0, 200.0, 100.0))])
        assert not project.needs_reading(0)
        project.set_filters(0, Filters(remove_lines=True))
        project.set_filters(1, Filters(remove_lines=True))
        assert project.needs_reading(0) and project.pages[0].correction is not None
        assert project.regions_by_person(1) and project.has_regions(1)
        assert project.text(0).endswith("Nachtrag")
        project.set_filters(0, Filters(remove_lines=True))  # the same: nothing to read
        assert not project.needs_reading(0)
    finally:
        project.close()


@needs_backend
def test_a_changed_input_keeps_what_a_person_decided(tmp_path: Path, report: Path) -> None:
    """The step before changed its result (more contrast, say): another file, so its
    configuration names another SHA-256.  Where a page's frame stayed, the areas a person
    drew and the text they corrected stay, and OCR reads the page anew; where the frame
    changed, the page's decisions go, and the project says which page that was."""
    first = _prepared(scan(report, tmp_path / "scan.pdf"), tmp_path / "first.pdf", ["a", "b"])
    project = Project.open(first)
    try:
        ignored = layout.Region("ignore", (60.0, 700.0, 300.0, 760.0))
        project.set_regions(0, [ignored])
        project.set_filters(0, Filters(upscale=2))
        project.set_correction(0, project.text(0) + "\nNachtrag")
        project.set_correction(1, project.text(1) + "\nAuch hier")
        config = project.config()
    finally:
        project.close()
    noisier = scan(report, tmp_path / "noisier.pdf", noise=0.004)
    second = _prepared(noisier, tmp_path / "second.pdf", ["a", "changed"])
    again = Project.open(second, config=config)
    try:
        assert again.dropped == [1]
        assert again.regions_by_person(0) and again.regions(0) == [layout.rounded(ignored)]
        assert again.filters(0) == Filters(upscale=2) and again.filters(1) == Filters()
        assert again.needs_reading(0) and again.text(0).endswith("Nachtrag")
        assert again.pages[1].correction is None and not again.regions_by_person(1)
    finally:
        again.close()
    plain = scan(report, tmp_path / "plain.pdf", noise=0.004)  # no frames: no rebasing
    with pytest.raises(OcrdocError) as caught:
        Project.open(plain, config=config)
    assert caught.value.kind == "config-mismatch"


def test_text_layer_pages(report: Path) -> None:
    """A born-digital PDF: no filters, no OCR, nothing to correct."""
    project = Project.open(report, Options(reader="none"))
    try:
        config = project.config()
        assert [p["filters"] for p in config["pages"]] == [None, None]
        project.read_all()
        assert [p.ocr for p in project.pages] == [False, False]
        assert "Ramipril" in project.text(0)
        with pytest.raises(OcrdocError) as caught:
            project.set_correction(0, "anders")
        assert caught.value.kind == "not-ocr"
    finally:
        project.close()


def test_what_is_neither_a_pdf_nor_a_picture(tmp_path: Path) -> None:
    """A PDF is read, a picture too (``tests/test_pictures.py``); anything else is not."""
    word = tmp_path / "brief.docx"
    word.write_bytes(b"PK")
    with pytest.raises(OcrdocError) as caught:
        Project.open(word)
    assert caught.value.kind == "unsupported" and caught.value.details == {"suffix": ".docx"}
    assert "ocrdoc" in caught.value.message("de")


def test_refused_configurations(tmp_path: Path, report: Path) -> None:
    """Another file's configuration, and broken ones, each by its kind."""
    project = Project.open(report, Options(reader="none"))
    try:
        config = project.config()
    finally:
        project.close()
    other = tmp_path / "other.pdf"
    with pymupdf.open(report) as doc:
        doc[0].insert_text((72, 700), "geändert")
        doc.save(other)
    with pytest.raises(OcrdocError) as caught:
        Project.open(other, config=config)
    assert caught.value.kind == "config-mismatch"
    cases = {
        "page": {**config, "pages": config["pages"][:1]},
        "field": {**config, "pages": [{**config["pages"][0], "ocr": "ja"},
                                      config["pages"][1]]},
    }
    for reason, broken in cases.items():
        with pytest.raises(OcrdocError) as caught:
            Project.open(report, config=broken)
        assert (caught.value.kind, caught.value.details) == ("bad-config", {"reason": reason})
    upscaled = {**config["pages"][0], "filters": {"by": "auto", "upscale": 7}}
    filters = {**config, "pages": [upscaled, config["pages"][1]]}
    with pytest.raises(OcrdocError) as caught:
        Project.open(report, config=filters)
    assert caught.value.details == {"reason": "field"}
    for content, reason in (("[1]", "format"), ("{kaputt", "json"),
                            (json.dumps({**config, "version": 99}), "format"),
                            (json.dumps({**config, "format": "optdoc-config"}), "format")):
        path = tmp_path / "x.ocrdoc.json"
        path.write_text(content, encoding="utf-8")
        with pytest.raises(OcrdocError) as caught:
            load_config(path)
        assert caught.value.details == {"reason": reason}
    with pytest.raises(OcrdocError) as caught:
        load_config(report)  # a PDF without a configuration
    assert caught.value.details == {"reason": "format"}
    assert EMBEDDED == "ocrdoc.json"
