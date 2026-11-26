"""Measure how well ocrdoc finds the areas of a page besides its text: pictures, barcodes,
stamps and handwriting, on the invented letters of ``bench/area_letters.py``, as they were
made (digital), scanned in colour, scanned in grey, and photographed and prepared by optdoc.

    uv run python bench/areas_bench.py <folder> [--models <folder>] [variants …]

makes six letters in ``<folder>`` with the boxes of what was drawn on them, lets ocrdoc
find the areas of each, and counts per kind: how many of the areas drawn were found (a box
of that kind overlapping by half at least), and how many areas were found where none was
drawn ("wrong").  With ``--models`` ocrdoc may use the models that lie in that folder; run
it with and without to see what a model gains over the rules.  The answer is JSON, numbers
only.  The photographed variant needs optdoc installed beside ocrdoc (``uv run --with
<optdoc>[cleanup]``); it is left out without.  Everything measured is made up.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

KINDS = ("image", "barcode", "stamp", "handwriting")
VARIANTS = ("digital", "scan-colour", "scan-grey", "photo")


def _iou(a: Any, b: Any) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    inter = max(0.0, w) * max(0.0, h)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def _letters(folder: Path) -> list[Path]:
    """The six invented letters, made once."""
    spec = importlib.util.spec_from_file_location("area_letters",
                                                  ROOT / "bench" / "area_letters.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    made: list[Path] = module.make(folder / "digital", 6)
    return made


def _source(pdf: Path, variant: str, k: int, work: Path) -> Path | None:
    """The letter as the variant has it; None where the variant cannot be made here."""
    from tests.synthetic import colour_scan, scan

    turn = (-1) ** k * 1.0
    if variant == "digital":
        return pdf
    if variant == "scan-grey":
        return scan(pdf, work / f"{pdf.stem}-grey.pdf", dpi=200, noise=0.01, rotation=turn)
    if variant == "scan-colour":
        return colour_scan(pdf, work / f"{pdf.stem}-colour.pdf", rotation=turn, seed=k)
    if importlib.util.find_spec("optdoc") is None:
        return None
    import cv2
    from optdoc import output
    from optdoc.project import Project as Preparation

    from tests.synthetic import camera_photo

    image, _corners = camera_photo(pdf, pitch=18, yaw=(-1) ** k * 6, roll=2, fill=0.85,
                                   size=(2400, 3200), dpi=220)
    photo = work / f"{pdf.stem}-photo.jpg"
    cv2.imwrite(str(photo), image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    preparation = Preparation.open(photo)
    try:
        prepared = preparation.build()
        try:
            return output.write(prepared, work / f"{pdf.stem}-prepared")["pdf"]
        finally:
            prepared.close()
    finally:
        preparation.close()


def measure(folder: Path, variants: list[str], models: Path | None) -> dict[str, Any]:
    """The figures per variant and kind."""
    from ocrdoc.project import Options, Project

    work = folder / "work"
    work.mkdir(parents=True, exist_ok=True)
    letters = _letters(folder)
    result: dict[str, Any] = {}
    for variant in variants:
        found, drawn, wrong, read = Counter[str](), Counter[str](), Counter[str](), 0
        seconds: list[float] = []
        for k, pdf in enumerate(letters):
            source = _source(pdf, variant, k, work)
            if source is None:
                break
            truth = json.loads(pdf.with_name(pdf.stem + ".areas.json").read_text(encoding="utf-8"))
            project = Project.open(source, Options(cells=False))
            project.models = models
            try:
                project.read(0)
                start = time.monotonic()
                regions = project.find_regions(0)
                seconds.append(time.monotonic() - start)
            finally:
                project.close()
            used: set[int] = set()
            for area in truth:
                drawn[area["kind"]] += 1
                best = max(((_iou(area["box"], r.box), i) for i, r in enumerate(regions)
                            if r.kind == area["kind"] and i not in used), default=(0.0, -1))
                if best[0] >= 0.5:
                    used.add(best[1])
                    found[area["kind"]] += 1
                    read += (area["kind"] == "barcode"
                             and regions[best[1]].content == area["content"])
            for i, r in enumerate(regions):
                if i not in used and r.kind in KINDS:
                    wrong[r.kind] += 1
        if not seconds:
            result[variant] = None  # could not be made here
            continue
        result[variant] = {
            "pages": len(seconds), "seconds_per_page": round(sum(seconds) / len(seconds), 2),
            **{kind: {"drawn": drawn[kind], "found": found[kind], "wrong": wrong[kind]}
               for kind in KINDS},
            "barcodes_read": read,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("variants", nargs="*", choices=[*VARIANTS, []], default=[])
    parser.add_argument("--models", type=Path)
    args = parser.parse_args()
    print(json.dumps(measure(args.folder, args.variants or list(VARIANTS), args.models), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
