"""A picture stays a picture: ocrdoc reads it and hands it on as it came, byte for byte;
the reading, the Markdown and the configuration lie beside it; the reading gives its boxes
in the picture's own pixels, upright; the same picture and document give the same files;
the frames of the step before are read from optdoc's document beside the picture."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest
from doccor import documents

from ocrdoc import layout, loading, output
from ocrdoc import ocr as ocrlib
from ocrdoc.cli import main
from ocrdoc.errors import OcrdocError
from ocrdoc.project import Project

needs_backend = pytest.mark.skipif(not ocrlib.available_backends(),
                                   reason="no OCR engine installed")
FILES = ("document", "reading", "markdown", "config")
FORMATS = {"jpg": "JPEG", "png": "PNG", "tiff": "TIFF", "webp": "WEBP", "heic": "HEIF"}
POINT = 150 / 72  # pixels to a point in the pictures made here


def _picture(report: Path, target: Path, page: int = 0, turned: int = 1, **options: object) -> Path:
    """A page of the invented report as a picture (150 dpi) of the type ``target`` names;
    ``turned`` is the EXIF orientation it is stored with (6: the pixels lie a quarter
    turn anticlockwise and the picture says so)."""
    import pillow_heif
    from PIL import Image

    pillow_heif.register_heif_opener()
    with pymupdf.open(report) as doc:
        pix = doc[page].get_pixmap(dpi=150, alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    if turned == 6:
        exif = Image.Exif()
        exif[0x0112] = 6
        image, options = image.rotate(90, expand=True), {**options, "exif": exif}
    image.save(target, **options)
    return target


def _write(project: Project, folder: Path) -> dict[str, Path]:
    reading = project.build()
    try:
        return output.write(reading, folder)
    finally:
        reading.close()


def _inside(page: dict) -> bool:
    """True when every box of a page of the reading lies in the page."""
    boxes = [w["box"] for w in page["words"] if w["box"]] + [r["box"] for r in page["regions"]]
    return bool(boxes) and all(
        -1 <= x0 < x1 <= page["width"] + 1 and -1 <= y0 < y1 <= page["height"] + 1
        for x0, y0, x1, y1 in boxes)


@needs_backend
@pytest.mark.parametrize("ending", list(FORMATS))
def test_a_picture_is_read_and_stays_as_it_came(tmp_path: Path, report: Path, ending: str,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    """What is written is the picture that came, byte for byte, under its own name, and
    beside it the reading (its boxes in the picture's pixels), the Markdown and the
    configuration; from the picture and the configuration the same files again, without
    OCR running a second time."""
    picture = _picture(report, tmp_path / f"seite.{ending}")
    project = Project.open(picture)
    try:
        assert project.picture and project.pixels == [(1240, 1755)]
        first = _write(project, tmp_path / "a")
    finally:
        project.close()
    assert {p.name for p in (tmp_path / "a").iterdir()} == {
        f"seite.{ending}", "seite.reading.json", "seite.md", "seite.ocrdoc.json"}
    assert first["document"].read_bytes() == picture.read_bytes()
    reading = json.loads(first["reading"].read_text(encoding="utf-8"))
    assert reading["version"] == 2 and reading["input"]["sha256"] == documents.digest(picture)
    page = reading["pages"][0]
    assert (page["unit"], page["width"], page["height"]) == ("px", 1240, 1755)
    assert page["source"] == "ocr" and "Ramipril" in page["text"]
    assert _inside(page)
    word = next(w for w in page["words"] if w["text"] == "Diagnosen:")
    assert word["box"][0] == pytest.approx(56 * POINT, abs=6)  # where it is printed
    assert "Ramipril" in first["markdown"].read_text(encoding="utf-8")
    config = json.loads(first["config"].read_text(encoding="utf-8"))
    assert config["format"] == "ocrdoc-config" and config["pages"][0]["ocr"] is True

    def no_ocr(*args: object, **kwargs: object) -> None:
        raise AssertionError("OCR ran again")

    monkeypatch.setattr(ocrlib, "recognise_words", no_ocr)
    again = Project.open(picture, config=config)
    try:
        second = _write(again, tmp_path / "b")
    finally:
        again.close()
    for key in FILES:
        assert first[key].read_bytes() == second[key].read_bytes(), key


@needs_backend
def test_a_picture_on_its_side_is_read_upright(tmp_path: Path, report: Path) -> None:
    """A phone stores the pixels as its sensor lay and says how to turn them: ocrdoc reads
    the picture upright, and the boxes are in the upright picture's pixels."""
    picture = _picture(report, tmp_path / "foto.jpg", turned=6, quality=90)
    assert loading.pixel_sizes(picture) == [(1240, 1755)]  # stored 1755 wide, 1240 high
    project = Project.open(picture)
    try:
        written = _write(project, tmp_path / "out")
    finally:
        project.close()
    assert written["document"].read_bytes() == picture.read_bytes()
    page = json.loads(written["reading"].read_text(encoding="utf-8"))["pages"][0]
    assert (page["width"], page["height"]) == (1240, 1755) and _inside(page)
    word = next(w for w in page["words"] if w["text"] == "Diagnosen:")
    assert word["box"][0] == pytest.approx(56 * POINT, abs=8)
    assert word["box"][2] - word["box"][0] > word["box"][3] - word["box"][1]  # it lies flat


@needs_backend
def test_every_picture_of_a_file_is_a_page(tmp_path: Path, report: Path) -> None:
    """A TIFF may hold several pictures: each is a page of the reading, in its own
    pixels."""
    from PIL import Image

    first = _picture(report, tmp_path / "eins.png")
    with Image.open(first) as one, Image.open(_picture(report, tmp_path / "zwei.png", 1)) as two:
        small = two.resize((930, 1316))
        one.save(tmp_path / "beide.tiff", save_all=True, append_images=[small],
                 compression="tiff_lzw")
    project = Project.open(tmp_path / "beide.tiff")
    try:
        assert project.pixels == [(1240, 1755), (930, 1316)]
        written = _write(project, tmp_path / "out")
    finally:
        project.close()
    pages = json.loads(written["reading"].read_text(encoding="utf-8"))["pages"]
    assert [(p["page"], p["width"], p["height"]) for p in pages] == [(1, 1240, 1755),
                                                                    (2, 930, 1316)]
    assert "Ramipril" in pages[0]["text"] and "Kontrolle" in pages[1]["text"]
    assert all(_inside(p) for p in pages)


def _beside(picture: Path, frames: list[str], **more: object) -> Path:
    """optdoc's configuration document beside a picture it wrote, with the ``frames``
    given."""
    upstream = {"format": "optdoc-config", "version": 3, **more,
                "pages": [{"page": n + 1, "plan": None, "frame": f}
                          for n, f in enumerate(frames)]}
    beside = picture.with_name(f"{picture.stem}.optdoc.json")
    beside.write_bytes(documents.document_bytes(upstream))
    return beside


@needs_backend
def test_the_frames_lie_beside_a_picture(tmp_path: Path, report: Path) -> None:
    """A PDF carries optdoc's document inside; beside a picture it lies as a file.  When
    optdoc's picture changed but its frame did not, what a person decided stays; when
    the frame changed, it goes; without the document, another picture is another file."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "c").mkdir()
    first = _picture(report, tmp_path / "a" / "foto.png")
    _beside(first, ["frame"])
    project = Project.open(first)
    try:
        assert project.frames == ["frame"]
        ignored = layout.Region("ignore", (60.0, 700.0, 300.0, 760.0))
        project.set_regions(0, [ignored])
        project.set_correction(0, project.text(0) + "\nNachtrag")
        config = project.config()
    finally:
        project.close()
    second = _picture(report, tmp_path / "b" / "foto.png", compress_level=1)  # other bytes
    assert second.read_bytes() != first.read_bytes()
    _beside(second, ["frame"])
    again = Project.open(second, config=config)
    try:
        assert again.dropped == [] and again.regions(0) == [layout.rounded(ignored)]
        assert again.text(0).endswith("Nachtrag")
    finally:
        again.close()
    _beside(second, ["another"])
    changed = Project.open(second, config=config)
    try:
        assert changed.dropped == [0] and changed.pages[0].correction is None
    finally:
        changed.close()
    third = _picture(report, tmp_path / "c" / "foto.png", compress_level=1)
    with pytest.raises(OcrdocError) as caught:  # nothing says the pages are the same
        Project.open(third, config=config)
    assert caught.value.kind == "config-mismatch"


@needs_backend
def test_a_picture_on_the_command_line(tmp_path: Path, report: Path,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    """``run`` on a picture answers with the picture it handed on; written beside the
    picture itself it would replace it, which is refused."""
    picture = _picture(report, tmp_path / "foto.jpg", quality=90)
    assert main(["run", str(picture), "--out", str(tmp_path / "out")]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert answer["document"] == str(tmp_path / "out" / "foto.jpg")
    assert answer["pages"] == 1 and answer["ocr_pages"] == [1] and answer["carried"] == []
    assert Path(answer["document"]).read_bytes() == picture.read_bytes()
    assert main(["run", str(picture), "--out", str(tmp_path / "again"), "--config",
                 answer["config"]]) == 0
    again = json.loads(capsys.readouterr().out)
    for key in FILES:
        assert Path(again[key]).read_bytes() == Path(answer[key]).read_bytes(), key
    assert main(["run", str(picture), "--out", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "same-as-source"


def test_one_page_for_a_phones_jpeg_and_a_tiff_on_its_side(tmp_path: Path, report: Path) -> None:
    """A phone's JPEG may carry a second image beside the photo (a gain map for bright
    screens): it is one picture and one page.  A TIFF stored on its side is read upright,
    and the size named is the upright picture's."""
    from PIL import Image

    from ocrdoc.project import Options

    first = _picture(report, tmp_path / "seite.png")
    with Image.open(first) as page:
        page.convert("RGB").save(tmp_path / "foto.jpg", format="MPO", save_all=True,
                                 append_images=[Image.new("RGB", (310, 438), (128, 128, 128))])
        exif = Image.Exif()
        exif[0x0112] = 6
        page.rotate(90, expand=True).save(tmp_path / "scan.tiff", exif=exif,
                                          compression="tiff_lzw")
    for name in ("foto.jpg", "scan.tiff"):
        project = Project.open(tmp_path / name, Options(reader="none"))
        try:
            assert len(project.pages) == 1 and project.pixels == [(1240, 1755)], name
            rect = project.doc[0].rect
            assert rect.height == pytest.approx(842, abs=0.01) and rect.width < rect.height
        finally:
            project.close()


def test_what_is_no_picture(tmp_path: Path) -> None:
    """A file named a picture that is none is unreadable, whatever its type."""
    for name in ("foto.png", "foto.webp", "foto.tiff", "foto.jpg"):
        broken = tmp_path / name
        broken.write_bytes(b"not a picture at all")
        with pytest.raises(OcrdocError) as caught:
            Project.open(broken)
        assert caught.value.kind == "unreadable", name
